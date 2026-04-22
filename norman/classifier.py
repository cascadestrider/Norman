"""Source-type classifier for Norman leads.

Tags each lead as customer_voice, retailer, editorial_roundup, or unknown
based on title + snippet + URL. Runs once per lead between the scouts and
the analyst so that retailer / editorial pages never reach ad-copy
generation.
"""

from __future__ import annotations

from typing import Literal

import anthropic

from norman.config import ANTHROPIC_API_KEY
from norman.token_tracker import token_tracker


SourceType = Literal["customer_voice", "retailer", "editorial_roundup", "unknown"]

VALID_LABELS: set[str] = {
    "customer_voice",
    "retailer",
    "editorial_roundup",
    "unknown",
}

_MODEL = "claude-haiku-4-5"

_PROMPT_TEMPLATE = """You are classifying a web page found by a lead-research pipeline into one of four source types.

Definitions:
- customer_voice: First-person user voice. Reddit/forum threads, YouTube comments, personal blog posts, tweets, Q&A/support boards — real people describing their own experience, question, or complaint. Also includes medical/informational pages where people research their own condition (photophobia, light sensitivity, concussion/TBI, migraine, post-surgery recovery).
- retailer: Brand or retailer product pages selling sunglasses/eyewear (Oakley, Ray-Ban, Warby Parker, Maui Jim, Costa, Smith, Wiley X, Amazon product listings, DTC brand sites).
- editorial_roundup: Third-person "best of" list, buyer's guide, review roundup, or affiliate-style ranking (Wirecutter, GearJunkie, Forbes Vetted, "10 Best Sunglasses for X").
- unknown: Genuinely no signal — rare. Prefer another label when URL or snippet hints.

URL signals are authoritative. When URL and snippet conflict (e.g., a reddit.com thread whose snippet reads promotionally), the URL wins — URL is harder to fake than extracted page text.
- Host matches reddit.com, stackexchange.com, quora.com, or contains "forum" / ".forum" / "/forums/" → customer_voice.
- Host is a medical or informational domain (.edu, .gov, mayoclinic.org, webmd.com, completeconcussions.com, healthline.com, and similar health/medical sites) AND topic touches light sensitivity, photophobia, concussion/TBI, migraine, or post-surgery recovery → customer_voice (real people researching their own condition).
- Path contains /review/, /reviews/, /best-, /top-, /vs/, /gear-guide/, /roundup/, /comparison/, /ranked/ → editorial_roundup.
- Host is any eyewear brand or single-brand eyewear/optics retailer (examples: oakley.com, ray-ban.com, warbyparker.com, maui-jim.com, costa.com, smith-optics.com, wileyx.com — treat as examples, not an exhaustive list; julbo.com, tifosi.com, persol.com, and similar direct-to-consumer eyewear sites also qualify) OR path contains /product/, /shop/, /p/, /buy/, /dp/ → retailer.
Only output "unknown" when URL and snippet together give no signal. If you have partial URL signal but low confidence (e.g., unfamiliar domain with a commerce-adjacent path, or an unknown host under a forum-shaped URL), commit to the best-fit label rather than falling back to unknown.

Lead:
URL: {url}
Title: {title}
Snippet: {snippet}

Respond with EXACTLY one of these four words and nothing else: customer_voice, retailer, editorial_roundup, unknown"""


def classify_source_type(title: str, snippet: str, url: str) -> SourceType:
    """Classify a lead's source type using claude-haiku-4-5.

    On API error or malformed response returns "unknown" so the pipeline
    keeps moving — the caller can decide how to treat unknowns.
    """
    if not ANTHROPIC_API_KEY:
        return "unknown"

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    prompt = _PROMPT_TEMPLATE.format(
        url=url or "",
        title=(title or "")[:200],
        snippet=(snippet or "")[:1500],
    )

    try:
        response = client.messages.create(
            model=_MODEL,
            max_tokens=16,
            messages=[{"role": "user", "content": prompt}],
        )
        token_tracker.record(
            "classifier",
            _MODEL,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        raw = response.content[0].text.strip().lower()
    except Exception:
        return "unknown"

    # The model may add trailing punctuation or whitespace — take the first
    # recognized token out of the response.
    for token in raw.replace(",", " ").split():
        token = token.strip(".:;\"'`")
        if token in VALID_LABELS:
            return token  # type: ignore[return-value]

    return "unknown"
