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
from urllib.parse import urlparse

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
from norman.retailer_brands import extract_brand, known_brands_before
from norman.token_tracker import token_tracker

# Use the same segment positioning the analyst uses so per-lead and weekly
# outputs speak the same vocabulary.
from norman.analyst import SEGMENT_POSITIONING

_MODEL = "claude-sonnet-4-5"
_MIN_LEADS = 50
# Retailer synthesis uses a lower floor — retailer lead volume is naturally
# smaller than customer-voice (the daily classifier sends most leads down the
# customer-voice path) but is still meaningful at 20+ leads/week.
_RETAILER_MIN_LEADS = 20
_SAMPLE_CAP = 800
# Score floor for the "always include" tier of score-weighted sampling.
# Leads at or above this score bypass random sampling entirely; leads
# below it only fill the remaining budget if slots are left.
_HIGH_SCORE_THRESHOLD = 60
_MAX_OUTPUT_TOKENS = 8192


def run_weekly_synthesis(
    window_start_override: Optional[date] = None,
    window_end_override: Optional[date] = None,
) -> Optional[SynthesisOutput]:
    """Cluster customer_voice leads into pain-point themes.

    Default behavior: last 7 days by last_seen (the live weekly synthesis).
    When both window_start_override and window_end_override are provided,
    runs scoped to that explicit historical range, filtering on date_found
    instead — so a past week can be re-synthesized from leads as they were
    discovered, not as they were last touched.

    Returns None when there's insufficient data (fewer than 50 leads) or
    when the model response can't be parsed after a single retry.
    """
    override = window_start_override is not None and window_end_override is not None
    if override:
        window_start = window_start_override
        window_end = window_end_override
    else:
        today = date.today()
        window_start = today - timedelta(days=7)
        window_end = today
    week_of = window_start.isoformat()

    if override:
        rows = _fetch_weekly_leads(start=window_start, end=window_end)
    else:
        rows = _fetch_weekly_leads()

    if len(rows) < _MIN_LEADS:
        scope = (
            f"in {window_start} to {window_end}"
            if override
            else "in past 7 days"
        )
        print(
            f"insufficient data for synthesis — need 50+ customer_voice leads "
            f"{scope}, got {len(rows)}"
        )
        return None

    leads = [_lead_digest(row) for row in rows]

    sampled_note: Optional[str] = None
    if len(leads) > _SAMPLE_CAP:
        iso_year, iso_week, _ = window_end.isocalendar()
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
        window_start, window_end, EVENT_PRE_DAYS, EVENT_POST_DAYS
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


def _fetch_weekly_leads(
    start: Optional[date] = None,
    end: Optional[date] = None,
    source_type: str = "customer_voice",
) -> list[tuple]:
    """Fetch leads of a given source_type for synthesis.

    Default: last 7 days by last_seen (live weekly). When start and end
    are both provided, filters on date_found BETWEEN start AND end — the
    historical scope filters on when leads were discovered, not last
    touched. source_type defaults to 'customer_voice' to preserve existing
    callers; pass 'retailer' for the retailer synthesis flow.
    """
    conn = init_db()
    try:
        if start is not None and end is not None:
            return conn.execute(
                """
                SELECT url, title, score, source, source_type, strategy,
                       event_name, event_window
                FROM leads
                WHERE source_type = ?
                  AND date_found BETWEEN ? AND ?
                ORDER BY score DESC
                """,
                (source_type, start.isoformat(), end.isoformat()),
            ).fetchall()
        return conn.execute(
            """
            SELECT url, title, score, source, source_type, strategy,
                   event_name, event_window
            FROM leads
            WHERE source_type = ?
              AND last_seen >= date('now', '-7 days')
            ORDER BY score DESC
            """,
            (source_type,),
        ).fetchall()
    finally:
        conn.close()


def _lead_digest(row: tuple) -> dict:
    url, title, score, source, _source_type, strategy, event_name, event_window = row
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
    digest = {
        "url": url,
        "title": title_trimmed,
        "score": score,
        "source": source,
        "segment": segment,
        "snippet": snippet or title_trimmed,
    }
    if event_window and event_name:
        digest["event_flagged"] = f"True (during {event_name})"
    return digest


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


# ---------------------------------------------------------------------------
# Weekly retailer synthesis
# ---------------------------------------------------------------------------

def run_weekly_retailer_synthesis(
    window_start_override: Optional[date] = None,
    window_end_override: Optional[date] = None,
) -> Optional[SynthesisOutput]:
    """Cluster retailer / brand promotional content into recurring themes.

    Parallels run_weekly_synthesis but with retailer-specific framing: every
    retailer lead in the corpus matched a Torque-relevant search term or
    pain point by construction, so the universe is pre-filtered to retailers
    operating in Torque's market space.

    Returns None when there's insufficient data (fewer than _RETAILER_MIN_LEADS)
    or when the model response can't be parsed after a single retry.
    """
    override = window_start_override is not None and window_end_override is not None
    if override:
        window_start = window_start_override
        window_end = window_end_override
    else:
        today = date.today()
        window_start = today - timedelta(days=7)
        window_end = today
    week_of = window_start.isoformat()

    if override:
        rows = _fetch_weekly_leads(
            start=window_start, end=window_end, source_type="retailer"
        )
    else:
        rows = _fetch_weekly_leads(source_type="retailer")

    if len(rows) < _RETAILER_MIN_LEADS:
        scope = (
            f"in {window_start} to {window_end}"
            if override
            else "in past 7 days"
        )
        print(
            f"insufficient data for retailer synthesis — need "
            f"{_RETAILER_MIN_LEADS}+ retailer leads {scope}, got {len(rows)}"
        )
        return None

    # Canonical-URL dedup (strip query string + fragment, keep highest-scoring
    # instance per canonical URL). Mirrors run_retailer_report's dedup. Same
    # upstream root cause: orchestrator's in-run dedup treats ?srsltid=A and
    # ?srsltid=B as distinct leads. Proper fix is URL canonicalization at
    # save_lead time; until then, presentation/synthesis layers dedup.
    deduped_rows: dict[str, tuple] = {}
    for row in sorted(rows, key=lambda r: r[2], reverse=True):  # row[2] = score
        canonical = _canonical_url(row[0])
        if canonical not in deduped_rows:
            deduped_rows[canonical] = row
    rows = list(deduped_rows.values())

    leads = [_retailer_lead_digest(row) for row in rows]

    # Group by brand for the prompt — brands ordered by lead count desc so
    # the heaviest competitors lead the JSON the model sees.
    leads_by_brand: dict[str, list[dict]] = {}
    for lead in leads:
        leads_by_brand.setdefault(lead["brand"], []).append(lead)
    leads_by_brand = dict(
        sorted(leads_by_brand.items(), key=lambda kv: len(kv[1]), reverse=True)
    )

    # Novel brands: brands in this window not present in any prior retailer
    # lead. Prior-week stats: lead count + brand count for the immediately
    # preceding 7-day window, used as comparison context in the prompt.
    conn = init_db()
    try:
        prior_known = known_brands_before(conn, window_start.isoformat())
        prior_window_start = window_start - timedelta(days=7)
        prior_window_end = window_start - timedelta(days=1)
        prior_rows = _fetch_weekly_leads(
            start=prior_window_start,
            end=prior_window_end,
            source_type="retailer",
        )
    finally:
        conn.close()
    novel_brands = sorted(b for b in leads_by_brand if b not in prior_known)
    prior_brands = {extract_brand(r[0], r[1] or "") for r in prior_rows}

    events_overlapping = events_in_range(
        window_start, window_end, EVENT_PRE_DAYS, EVENT_POST_DAYS
    )
    events_in_window = [_format_event_label(e) for e in events_overlapping]

    prompt = _build_retailer_prompt(
        week_of=week_of,
        leads_by_brand=leads_by_brand,
        novel_brands=novel_brands,
        prior_lead_count=len(prior_rows),
        prior_brand_count=len(prior_brands),
        events_in_window=events_in_window,
    )
    data = _call_with_retry(prompt)
    if data is None:
        return None

    try:
        return _to_synthesis_output(
            data,
            fallback_week_of=week_of,
            leads_analyzed=len(leads),
            sampled_note=None,
            events_in_window=events_in_window,
        )
    except Exception as e:
        print(f"retailer synthesis output shaping failed: {e}")
        return None


def _retailer_lead_digest(row: tuple) -> dict:
    """Per-lead dict for the retailer prompt: title, score, source, brand.

    Skips segment/snippet extraction from `strategy` because retailer leads
    are stored with empty strategy (the analyst doesn't enrich them). Brand
    is computed via the URL-and-title extractor.
    """
    url, title, score, source, _source_type, _strategy, _event_name, _event_window = row
    title_trimmed = (title or "")[:150]
    return {
        "url": url,
        "title": title_trimmed,
        "score": score,
        "source": source,
        "brand": extract_brand(url, title or ""),
    }


def _canonical_url(url: str) -> str:
    """Return scheme://netloc/path — query string + fragment stripped.
    Duplicated intentionally with delivery._canonical_url to avoid a
    synthesizer → delivery import (delivery already imports from
    synthesizer's output types).
    """
    try:
        parsed = urlparse(url)
        return f"{parsed.scheme}://{parsed.netloc}{parsed.path}"
    except Exception:
        return url


def _build_retailer_prompt(
    week_of: str,
    leads_by_brand: dict[str, list[dict]],
    novel_brands: list[str],
    prior_lead_count: int,
    prior_brand_count: int,
    events_in_window: Optional[list[str]] = None,
) -> str:
    total_brands = len(leads_by_brand)
    total_leads = sum(len(v) for v in leads_by_brand.values())

    segments_block = "\n".join(
        f"- {seg}: {positioning}"
        for seg, positioning in SEGMENT_POSITIONING.items()
    )
    leads_block = json.dumps(leads_by_brand, ensure_ascii=False)

    novel_block = (
        f"Brands appearing for the first time in retailer data this week "
        f"(not seen before {week_of}): {', '.join(novel_brands)}.\n\n"
        if novel_brands
        else "No first-time brands this week — every brand has appeared "
        "in prior retailer data.\n\n"
    )

    # Baseline-comparison guidance. When the prior week's count is below
    # the threshold for reliable comparison, the current week is a baseline-
    # establishment period (e.g. immediately after a classifier landed),
    # NOT a growth event. The prompt must steer the model away from causal
    # attribution that the data doesn't support.
    _BASELINE_RELIABILITY_FLOOR = 10
    if prior_lead_count < _BASELINE_RELIABILITY_FLOOR:
        prior_block = (
            f"Prior week: {prior_lead_count} retailer leads across "
            f"{prior_brand_count} brands. Current week: {total_leads} leads "
            f"across {total_brands} brands.\n\n"
            f"NOTE on baseline: the prior-week count of {prior_lead_count} is "
            f"below the threshold for reliable comparison. Treat the current "
            f"week as a BASELINE-ESTABLISHMENT period for retailer-classification "
            f"reporting, NOT as evidence of growth or surge. When discussing "
            f"week-over-week change in `summary`, use framing like \"no comparable "
            f"baseline; first reportable week after the classification pipeline "
            f"became reliable\" rather than \"surge from X to Y\" or \"growth "
            f"of N%\". Do NOT attribute the current-week volume to external "
            f"factors (tournament overlap, seasonal trends, holidays) when the "
            f"prior-week baseline is unreliable — the volume reflects what "
            f"Norman's classifier observed this week, not a change in retailer "
            f"activity itself. Tournament context (below, if present) may be "
            f"mentioned descriptively as background but is NOT a credible "
            f"causal driver for volume change in this case.\n\n"
        )
    else:
        prior_block = (
            f"Prior week: {prior_lead_count} retailer leads across "
            f"{prior_brand_count} brands. Current week: {total_leads} leads "
            f"across {total_brands} brands.\n\n"
        )

    if events_in_window:
        event_context = (
            f"Tournament context: this week overlapped "
            f"{', '.join(events_in_window)}. Some retailer ad copy may be "
            f"event-themed.\n\n"
        )
    else:
        event_context = ""

    return f"""You are the weekly retailer-intelligence analyst for Torque Optics.

You are analyzing one week of retailer / brand promotional content that Norman captured because it matched Torque Optics-relevant search terms or pain points. Every retailer in this dataset is operating in a market space adjacent to Torque's positioning. The corpus is pre-filtered — there are no off-topic retailers here, only ones competing for an audience Torque cares about.

Product:
{PRODUCT_FOCUS}

Torque segment positioning (use when reasoning about positioning overlap and whitespace):
{segments_block}

{prior_block}{novel_block}{event_context}For the week of {week_of}, produce a structured analysis. Output-field semantics:

- `summary` is a 4-6 sentence executive synthesis covering sections (1), (3), (4), and (5) below in prose. Be specific about brand names and pain points. Write paragraphs, not bullets.
- `themes` is the structured cluster output for section (2). 3-6 themes total, clustering retailer ad copy by underlying pain point similarity.

Sections to weave into `summary`:
1. Retailer activity overview — total brands, total leads, dominant brands by volume, week-over-week change vs the prior-week numbers above.
3. Notable new entrants — the first-time brands listed above. What category and positioning each occupies.
4. Positioning overlap with Torque — which Torque segments (sensitivity, golf, fishing, motorcycle, commuter, screen visibility, tinted-window distortion) retailers are most heavily competing in. Name specific retailers and their angles.
5. Whitespace observation — Torque segments NOT well-represented in this week's retailer messaging. Reason from the segment positioning above; do not invent customer-voice claims.

Section 2 — themes — clustering rules:
- Cluster by PAIN POINT, not by brand. A theme like "glare on the green" can span multiple retailers — that is good.
- Prefer themes that recur across MULTIPLE brands over single-brand niche claims. A theme supported by 1 brand is weak; a theme supported by 5+ brands is strong.
- `name` is a short theme label, 3-5 words.
- `pain_point` is a one-sentence description of the underlying problem.
- `segment_breakdown` maps Torque customer-segment name (golf, fishing, motorcycle, commuter, sensitivity, general) to count of BRANDS in the theme targeting that segment. Example: {{"golf": 5, "commuter": 2}}.
- `urgency_score` is an integer 1-10 describing how saturated the theme is in retailer messaging (10 = many brands competing aggressively, 1 = barely one brand claiming it).
- `representative_quotes` should be 3-5 entries, one per supporting brand where possible. Each `quote` MUST be a literal excerpt from a retailer title in the data below — no paraphrasing. Use empty string "" when no quotable text exists; the `summary` field then carries the observation. The `segment` field on each quote holds the BRAND NAME (the retailer-side analog of customer segment).
- `creative_angles` (exactly 3) describe Torque's COUNTER-POSITIONING for this theme: where this theme is saturated, what angle differentiates Torque; where the theme reveals partial whitespace, what first-mover angle Torque could claim.

Output ONLY the JSON object below. No preamble. No markdown fences. No trailing commentary.

Schema:
{{
  "week_of": "{week_of}",
  "leads_analyzed": {total_leads},
  "summary": "4-6 sentence executive synthesis covering sections 1, 3, 4, 5",
  "themes": [
    {{
      "name": "short theme name, 3-5 words",
      "pain_point": "one-sentence description of the underlying problem",
      "segment_breakdown": {{"golf": 5, "commuter": 2}},
      "urgency_score": 7,
      "representative_quotes": [
        {{"quote": "verbatim excerpt from a retailer title — must be literal",
          "summary": "what this retailer is positioning, in third-person clinical voice",
          "source_url": "https://...",
          "segment": "Tifosi Optics"}}
      ],
      "creative_angles": [
        {{"angle": "Torque's counter-positioning angle", "hook": "headline-level hook", "proof_point": "what Torque feature supports this counter-position"}}
      ]
    }}
  ]
}}

Retailer leads grouped by brand (JSON object, brands ordered by lead count descending):
{leads_block}
"""
