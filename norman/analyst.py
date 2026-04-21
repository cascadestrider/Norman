import os
from datetime import date
import anthropic
from norman.models import Lead, AnalystLead, AnalystOutput
from norman.config import ANTHROPIC_API_KEY, PRODUCT_FOCUS, SEGMENTS
from norman.token_tracker import token_tracker

# Segment routing keywords. Each lead's title + snippet is checked against
# these keyword lists to determine which segment(s) it belongs to.
# Refreshed 2026-04-21 with sensitivity segment added per client input.
SEGMENT_KEYWORDS = {
    "golf": [
        "golf", "course", "fairway", "putting", "tee", "green", "golfer",
        "ball tracking", "reading greens", "handicap", "tournament",
    ],
    "fishing": [
        "fishing", "angling", "bass", "fly fishing", "water glare", "boat", "fish",
    ],
    "motorcycle": [
        "riding", "motorcycle", "moto", "highway", "helmet", "visor", "rider",
        "hud", "heads up display", "dashboard",
    ],
    "commuter": [
        "driving", "commuting", "road", "traffic", "windshield glare", "commute", "drive",
        "phone screen", "gps", "smartwatch", "watch screen", "pixelation",
    ],
    "sensitivity": [
        "headache", "migraine", "concussion", "tbi", "light sensitivity",
        "photophobia", "post concussion", "eyes hurt", "eye strain",
        "too dark", "color distortion", "color accuracy", "led glare",
        "99 percent polarized", "do i need polarized", "alternatives to polarized",
    ],
}

# Segment-specific positioning for the analyst prompt. Added 2026-04-21
# so the analyst generates segment-appropriate ad copy rather than generic
# positioning. Sensitivity is the most distinct — different vocabulary,
# different emotional register, different product angle.
SEGMENT_POSITIONING = {
    "golf": (
        "Activity-tuned polarization for golf specifically — preserves ball "
        "tracking in flight and depth perception on approach, unlike generic "
        "polarized lenses. Color science that enhances green contrast without "
        "the unnatural pop. An alternative to the pink/purple 'golf lens' "
        "trope that dominates the category."
    ),
    "fishing": (
        "Fishing-tuned polarization optimized for spotting fish through "
        "water glare. Maximum glare cut where it matters, without the "
        "color distortion that compromises other uses."
    ),
    "motorcycle": (
        "Rider-tuned polarization that works with modern motorcycle tech — "
        "phone screens, GPS displays, and helmet HUDs stay visible. Cuts "
        "road glare without blacking out the instruments you actually need."
    ),
    "commuter": (
        "Daily-driver polarization that keeps phone screens, smartwatches, "
        "and GPS visible while still cutting windshield glare. No more "
        "taking sunglasses off at every stoplight to check the map."
    ),
    "sensitivity": (
        "Designed for how your eyes actually work — color-accurate rather "
        "than aggressively dark, with tunable polarization that doesn't "
        "trigger the headaches and eye strain that 99% polarization causes. "
        "Built with post-concussion and photophobia users in mind. Accuracy "
        "over darkness."
    ),
    "general": (
        "Activity-tuned polarization — the right polarization percentage "
        "for your specific use case, rather than the one-size-fits-all "
        "99% approach that causes headaches, kills phone screens, and "
        "distorts color."
    ),
}


def classify_segment(lead: Lead) -> list[str]:
    text = f"{lead.title} {lead.snippet}".lower()
    matched = [seg for seg, kws in SEGMENT_KEYWORDS.items() if any(kw in text for kw in kws)]
    return matched if matched else ["general"]


def run_analyst(leads: list[Lead]) -> AnalystOutput:
    """Take scored leads, classify by segment, generate ad copy for each."""
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    segments: dict[str, list[AnalystLead]] = {s: [] for s in SEGMENTS + ["general"]}
    flagged: list[dict] = []

    for lead in leads:
        if len(lead.snippet.strip()) < 30:
            flagged.append({
                "url": lead.url,
                "error": "Insufficient content to generate strategy — snippet too short",
                "score": lead.score,
            })
            continue

        lead_segments = classify_segment(lead)

        for seg in lead_segments:
            # Generate segment-specific ad copy so each copy instance uses
            # the right positioning for the segment it lands in.
            ad_data = _generate_ad_strategy(client, lead, seg)
            enriched = AnalystLead(
                url=lead.url,
                title=lead.title,
                score=lead.score,
                keywords=lead.keywords,
                source=lead.source,
                platform=lead.platform,
                geo=lead.geo,
                snippet=lead.snippet,
                segment=seg,
                problem_detected=ad_data.get("problem_detected", ""),
                why_we_win=ad_data.get("why_we_win", ""),
                ad_headline=ad_data.get("ad_headline", ""),
                ad_body=ad_data.get("ad_body", ""),
                placement_tip=ad_data.get("placement_tip", ""),
                geo_note=ad_data.get("geo_note"),
            )
            segments.setdefault(seg, []).append(enriched)

    # Sort each segment by score descending
    for seg in segments:
        segments[seg].sort(key=lambda x: x.score, reverse=True)

    # Build top 3 across all segments
    all_leads = [lead for seg_leads in segments.values() for lead in seg_leads]
    all_leads.sort(key=lambda x: x.score, reverse=True)
    # Deduplicate top 3 by URL
    seen = set()
    top_3 = []
    for lead in all_leads:
        if lead.url not in seen:
            seen.add(lead.url)
            top_3.append(lead)
        if len(top_3) == 3:
            break

    total = len({lead.url for seg_leads in segments.values() for lead in seg_leads})

    return AnalystOutput(
        date=str(date.today()),
        total_leads=total,
        segments=segments,
        top_3=top_3,
        flagged=flagged,
    )


def _generate_ad_strategy(client: anthropic.Anthropic, lead: Lead, segment: str = "general") -> dict:
    positioning = SEGMENT_POSITIONING.get(segment, SEGMENT_POSITIONING["general"])

    prompt = f"""You are an ad strategist for Torque Optics.
Product: {PRODUCT_FOCUS}

Segment for this lead: {segment}
Segment-specific positioning: {positioning}

Analyze this lead from {lead.source}:
Title: {lead.title}
Content: {lead.snippet[:1500]}

Respond in EXACTLY this format (one line per field, no extra text):
PROBLEM DETECTED: [One sentence: what specific pain point is this person experiencing?]
WHY WE WIN: [One sentence: which specific Torque Optics feature directly addresses this pain? Use the segment-specific positioning above.]
AD HEADLINE: [Punchy, solution-focused, max 8 words. Address the struggle directly.]
AD BODY: [2-3 sentences. Problem → solution → CTA. Conversational, not corporate. Match the segment voice.]
PLACEMENT TIP: [Where and how to place this ad for maximum relevance — be specific about platform, targeting, ad format.]
GEO NOTE: [If location data present: note location-specific opportunity. Otherwise write: null]

Rules:
- Never mention competitor brand names in ad copy
- Headlines must directly reference the detected problem
- Match the voice of the source platform ({lead.source})
- For the sensitivity segment: lead with empathy, avoid clinical language, emphasize accuracy over darkness
- For golf: reference specific golf problems (ball tracking, greens, depth perception), avoid the pink/purple lens trope
- For commuter / motorcycle: emphasize phone / GPS / HUD / screen compatibility when relevant"""

    model = "claude-sonnet-4-5"
    try:
        response = client.messages.create(
            model=model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        token_tracker.record(
            "analyst",
            model,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        return _parse_ad_response(response.content[0].text)
    except Exception as e:
        return {
            "problem_detected": f"Analysis failed: {e}",
            "why_we_win": "",
            "ad_headline": "",
            "ad_body": "",
            "placement_tip": "",
            "geo_note": None,
        }


def _parse_ad_response(text: str) -> dict:
    result = {
        "problem_detected": "",
        "why_we_win": "",
        "ad_headline": "",
        "ad_body": "",
        "placement_tip": "",
        "geo_note": None,
    }
    field_map = {
        "PROBLEM DETECTED:": "problem_detected",
        "WHY WE WIN:": "why_we_win",
        "AD HEADLINE:": "ad_headline",
        "AD BODY:": "ad_body",
        "PLACEMENT TIP:": "placement_tip",
        "GEO NOTE:": "geo_note",
    }
    for line in text.strip().split("\n"):
        line = line.strip()
        for prefix, key in field_map.items():
            if line.upper().startswith(prefix.upper()):
                value = line[len(prefix):].strip()
                if key == "geo_note" and value.lower() == "null":
                    value = None
                result[key] = value
                break
    return result
