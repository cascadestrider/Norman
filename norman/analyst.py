import os
from datetime import date
import anthropic
from norman.models import Lead, AnalystLead, AnalystOutput
from norman.config import ANTHROPIC_API_KEY, PRODUCT_FOCUS, SEGMENTS
from norman.token_tracker import token_tracker

SEGMENT_KEYWORDS = {
    "golf": ["golf", "course", "fairway", "putting", "tee", "green", "golfer"],
    "fishing": ["fishing", "angling", "bass", "fly fishing", "water glare", "boat", "fish"],
    "motorcycle": ["riding", "motorcycle", "moto", "highway", "helmet", "visor", "rider"],
    "commuter": ["driving", "commuting", "road", "traffic", "windshield glare", "commute", "drive"],
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
        ad_data = _generate_ad_strategy(client, lead)

        for seg in lead_segments:
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


def _generate_ad_strategy(client: anthropic.Anthropic, lead: Lead) -> dict:
    prompt = f"""You are an ad strategist for Torque Optics.
Product: {PRODUCT_FOCUS}

Analyze this lead from {lead.source}:
Title: {lead.title}
Content: {lead.snippet[:1500]}

Respond in EXACTLY this format (one line per field, no extra text):
PROBLEM DETECTED: [One sentence: what specific pain point is this person experiencing?]
WHY WE WIN: [One sentence: which specific Torque Optics feature directly addresses this pain?]
AD HEADLINE: [Punchy, solution-focused, max 8 words. Address the struggle directly.]
AD BODY: [2-3 sentences. Problem → solution → CTA. Conversational, not corporate.]
PLACEMENT TIP: [Where and how to place this ad for maximum relevance — be specific about platform, targeting, ad format.]
GEO NOTE: [If location data present: note location-specific opportunity. Otherwise write: null]

Rules:
- Never mention competitor brand names in ad copy
- Headlines must directly reference the detected problem
- Match the voice of the source platform ({lead.source})"""

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
