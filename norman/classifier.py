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
- customer_voice: First-person user voice. Reddit threads, forum posts, YouTube comments, blog rants, tweets — where actual users describe their own experience, complaint, or question.
- retailer: Brand or retailer product pages selling sunglasses/eyewear. Examples: Wiley X, Oakley, Ray-Ban, Amazon product listings, DTC brand sites, manufacturer pages.
- editorial_roundup: Third-person "best of" list, buyer's guide, review roundup, or affiliate-style ranking. Examples: Wirecutter, GearJunkie, Forbes Vetted, "The 10 Best Sunglasses for X" articles.
- unknown: None of the above, or the content is ambiguous / insufficient.

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
