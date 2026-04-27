"""Weekly synthesis: cluster customer-voice leads into recurring pain-point
themes instead of generating per-lead ad copy.

Reads the DB's customer_voice leads from the past 7 days, extracts segment
from each lead's stored analyst strategy (if any), and prompts Sonnet once
for 3-5 clustered themes with directional creative angles per theme.
"""

from __future__ import annotations

import json
import random
import sqlite3
from datetime import date, timedelta
from typing import Optional

import anthropic

from norman.config import (
    ANTHROPIC_API_KEY,
    EVENT_POST_DAYS,
    EVENT_PRE_DAYS,
    PRODUCT_FOCUS,
)
from norman.db import init_db
from norman.events import TournamentEvent, events_in_range
from norman.models import (
    CreativeAngle,
    RepresentativeQuote,
    SynthesisOutput,
    ThemeOutput,
)
from norman.token_tracker import token_tracker

# Use the same segment positioning the analyst uses so per-lead and weekly
# outputs speak the same vocabulary.
from norman.analyst import SEGMENT_POSITIONING

_MODEL = "claude-sonnet-4-5"
_MIN_LEADS = 50
_SAMPLE_CAP = 800
# Score floor for the "always include" tier of score-weighted sampling.
# Leads at or above this score bypass random sampling entirely; leads
# below it only fill the remaining budget if slots are left.
_HIGH_SCORE_THRESHOLD = 60
_MAX_OUTPUT_TOKENS = 8192


def run_weekly_synthesis() -> Optional[SynthesisOutput]:
    """Cluster last 7 days of customer_voice leads into pain-point themes.

    Returns None when there's insufficient data (fewer than 50 leads) or
    when the model response can't be parsed after a single retry.
    """
    today = date.today()
    window_start = today - timedelta(days=7)
    week_of = window_start.isoformat()

    rows = _fetch_weekly_leads()

    if len(rows) < _MIN_LEADS:
        print(
            f"insufficient data for synthesis — need 50+ customer_voice leads "
            f"in past 7 days, got {len(rows)}"
        )
        return None

    leads = [_lead_digest(row) for row in rows]

    sampled_note: Optional[str] = None
    if len(leads) > _SAMPLE_CAP:
        iso_year, iso_week, _ = today.isocalendar()
        rng = random.Random(f"{iso_year}-W{iso_week}")

        high_score = [l for l in leads if l["score"] >= _HIGH_SCORE_THRESHOLD]
        low_score = [l for l in leads if l["score"] < _HIGH_SCORE_THRESHOLD]

        if len(high_score) >= _SAMPLE_CAP:
            # High-score pool already exceeds the budget — random-sample
            # within it rather than keeping a biased top slice.
            leads_for_prompt = rng.sample(high_score, _SAMPLE_CAP)
            sampled_note = (
                f"Sampled {_SAMPLE_CAP} of {len(leads)} leads: "
                f"{_SAMPLE_CAP} from {len(high_score)}-lead high-score pool "
                f"(score ≥ {_HIGH_SCORE_THRESHOLD}), "
                f"seeded on {iso_year}-W{iso_week:02d}."
            )
        else:
            # Keep all high-score leads, random-fill from the low-score pool.
            fill_count = _SAMPLE_CAP - len(high_score)
            fill = rng.sample(low_score, fill_count)
            leads_for_prompt = high_score + fill
            sampled_note = (
                f"Sampled {_SAMPLE_CAP} of {len(leads)} leads: "
                f"{len(high_score)} kept (score ≥ {_HIGH_SCORE_THRESHOLD}) + "
                f"{fill_count} random fill, "
                f"seeded on {iso_year}-W{iso_week:02d}."
            )
    else:
        leads_for_prompt = leads

    events_overlapping = events_in_range(
        window_start, today, EVENT_PRE_DAYS, EVENT_POST_DAYS
    )
    events_in_window = [_format_event_label(e) for e in events_overlapping]

    prompt = _build_prompt(week_of, leads_for_prompt, events_in_window)
    data = _call_with_retry(prompt)
    if data is None:
        return None

    try:
        return _to_synthesis_output(
            data,
            fallback_week_of=week_of,
            leads_analyzed=len(leads_for_prompt),
            sampled_note=sampled_note,
            events_in_window=events_in_window,
        )
    except Exception as e:
        print(f"synthesis output shaping failed: {e}")
        return None


def _format_event_label(event: TournamentEvent) -> str:
    """Render an event as 'PGA Championship (May 14-17)' for prompt + markdown."""
    start = event.start_date
    end = event.end_date
    if start.month == end.month:
        return f"{event.name} ({start.strftime('%b %d')}-{end.strftime('%d')})"
    return (
        f"{event.name} "
        f"({start.strftime('%b %d')}-{end.strftime('%b %d')})"
    )


def _fetch_weekly_leads() -> list[tuple]:
    conn = init_db()
    try:
        return conn.execute(
            """
            SELECT url, title, score, source, source_type, strategy
            FROM leads
            WHERE source_type = 'customer_voice'
              AND last_seen >= date('now', '-7 days')
            ORDER BY score DESC
            """
        ).fetchall()
    finally:
        conn.close()


def _lead_digest(row: tuple) -> dict:
    url, title, score, source, _source_type, strategy = row
    segment = "general"
    snippet = ""
    if strategy:
        try:
            parsed = json.loads(strategy)
            segment = parsed.get("segment") or "general"
            snippet = (
                parsed.get("problem_detected")
                or parsed.get("ad_headline")
                or ""
            )
        except (json.JSONDecodeError, TypeError):
            pass
    title_trimmed = (title or "")[:150]
    return {
        "url": url,
        "title": title_trimmed,
        "score": score,
        "source": source,
        "segment": segment,
        "snippet": snippet or title_trimmed,
    }


def _build_prompt(
    week_of: str,
    leads: list[dict],
    events_in_window: Optional[list[str]] = None,
) -> str:
    segments_block = "\n".join(
        f"- {seg}: {positioning}"
        for seg, positioning in SEGMENT_POSITIONING.items()
    )
    leads_json = json.dumps(leads, ensure_ascii=False)

    if events_in_window:
        event_context = (
            f"Context: the data below covers a week that included activity "
            f"around the following tournament(s): "
            f"{', '.join(events_in_window)}. Some leads in this corpus may "
            f"have been surfaced specifically by event-related queries "
            f"(these will skew toward golf-segment pain-points connected to "
            f"tournament viewing or play). When you cluster, consider "
            f"whether a distinct tournament-related theme emerges; do not "
            f"force one if the signal is thin.\n\n"
        )
    else:
        event_context = ""

    return f"""{event_context}You are the weekly synthesis analyst for Torque Optics.

Product:
{PRODUCT_FOCUS}

Segment positioning (use these when reasoning about creative angles):
{segments_block}

Task: read the week's customer-voice leads below and cluster them into 3-5 recurring pain-point themes. Each theme is a cluster of leads that share the same underlying problem — even if they come from different segments.

Instructions:
- Cluster by PAIN POINT, not by segment. A theme like "phones go black with polarized lenses" can span commuter and motorcycle segments — that is good.
- Prefer themes that recur across MANY leads over one-off niche complaints. A theme supported by 3 leads is weak; a theme supported by 30 is strong.
- creative_angles must be DIRECTIONAL — proposed angles to test, not finished ad copy. hooks are headline-level one-liners, not full ad bodies.
- Never mention competitor brand names in any field.
- Produce 3-5 themes total. No more, no fewer.
- Each theme must have exactly 3-5 representative_quotes (short excerpts from the lead titles/snippets below) and exactly 3 creative_angles.
- quote MUST be a literal excerpt copied directly from the lead's title text. Do not paraphrase. Do not summarize. Do not rewrite in third person. If the lead's title does not contain a quotable phrase that captures the pain (e.g., titles that read like "User experiencing X"), set quote to empty string "" and rely on the summary field alone.
- summary describes what the lead is about in your own words. This is where you synthesize — the quote is where you cite. Both fields are required (quote may be empty; summary must be populated).
- urgency_score is an integer 1-10 describing how pressing the underlying pain feels (10 = acute distress, 1 = nice-to-have curiosity).
- segment_breakdown maps segment name to count of supporting leads for that theme.

Output ONLY the JSON object below. No preamble. No markdown fences. No trailing commentary.

Schema (use this exact shape; fill with real values):
{{
  "week_of": "{week_of}",
  "leads_analyzed": {len(leads)},
  "summary": "2-3 sentence executive summary of the week's signal",
  "themes": [
    {{
      "name": "short theme name, 3-5 words",
      "pain_point": "one-sentence description of the underlying problem",
      "segment_breakdown": {{"golf": 5, "sensitivity": 12}},
      "urgency_score": 7,
      "representative_quotes": [
        {{"quote": "verbatim excerpt from the lead's title — must be literal text, no paraphrasing or rewording",
          "summary": "what this lead is fundamentally about, in third-person clinical voice",
          "source_url": "https://...",
          "segment": "golf"}}
      ],
      "creative_angles": [
        {{"angle": "one-line creative direction", "hook": "headline-level hook", "proof_point": "what Torque Optics feature supports this"}}
      ]
    }}
  ]
}}

Leads (JSON array):
{leads_json}
"""


def _call_with_retry(prompt: str) -> Optional[dict]:
    if not ANTHROPIC_API_KEY:
        print("synthesis skipped — ANTHROPIC_API_KEY not set")
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    messages = [{"role": "user", "content": prompt}]

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_OUTPUT_TOKENS,
            messages=messages,
        )
        token_tracker.record(
            "synthesizer",
            _MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        first_text = response.content[0].text.strip()
    except Exception as e:
        print(f"synthesis API call failed: {e}")
        return None

    parsed = _try_parse_json(first_text)
    if parsed is not None:
        return parsed

    # Retry once with the prior assistant turn included so the model can
    # see its own malformed output.
    messages.append({"role": "assistant", "content": first_text})
    messages.append({
        "role": "user",
        "content": "your previous response was not valid JSON, return only valid JSON matching the schema exactly.",
    })

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=_MAX_OUTPUT_TOKENS,
            messages=messages,
        )
        token_tracker.record(
            "synthesizer",
            _MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        retry_text = response.content[0].text.strip()
    except Exception as e:
        print(
            f"synthesis retry call failed: {e}. "
            f"First response (first 500 chars): {first_text[:500]}"
        )
        return None

    parsed = _try_parse_json(retry_text)
    if parsed is None:
        print(
            f"synthesis JSON parse failed after retry. "
            f"Retry response (first 500 chars): {retry_text[:500]}"
        )
    return parsed


def _try_parse_json(text: str) -> Optional[dict]:
    """Parse JSON, tolerating ```json fences the model might add despite
    being told not to."""
    t = text.strip()
    if t.startswith("```"):
        lines = t.split("\n")
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        t = "\n".join(lines).strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError:
        return None


def _to_synthesis_output(
    data: dict,
    fallback_week_of: str,
    leads_analyzed: int,
    sampled_note: Optional[str],
    events_in_window: Optional[list[str]] = None,
) -> SynthesisOutput:
    themes: list[ThemeOutput] = []
    for t in data.get("themes", []) or []:
        quotes = [
            RepresentativeQuote(
                quote=str(q.get("quote", "")),
                summary=str(q.get("summary", "")),
                source_url=str(q.get("source_url", "")),
                segment=str(q.get("segment", "general")),
            )
            for q in (t.get("representative_quotes") or [])
        ]
        angles = [
            CreativeAngle(
                angle=str(a.get("angle", "")),
                hook=str(a.get("hook", "")),
                proof_point=str(a.get("proof_point", "")),
            )
            for a in (t.get("creative_angles") or [])
        ]
        breakdown_raw = t.get("segment_breakdown") or {}
        breakdown = {
            str(k): int(v) for k, v in breakdown_raw.items()
            if _coerce_int(v) is not None
        }
        themes.append(ThemeOutput(
            name=str(t.get("name", "")),
            pain_point=str(t.get("pain_point", "")),
            segment_breakdown=breakdown,
            urgency_score=_coerce_int(t.get("urgency_score")) or 0,
            representative_quotes=quotes,
            creative_angles=angles,
        ))

    return SynthesisOutput(
        week_of=str(data.get("week_of") or fallback_week_of),
        leads_analyzed=_coerce_int(data.get("leads_analyzed")) or leads_analyzed,
        summary=str(data.get("summary", "")),
        themes=themes,
        sampled_note=sampled_note,
        events_in_window=events_in_window or [],
    )


def _coerce_int(value) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
