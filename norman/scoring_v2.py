"""Semantic scoring for Norman leads.

Replaces the substring keyword match in scoring.py with cosine similarity
against a hand-written set of first-person customer-voice exemplars.

Why: keyword scoring rewards any page that repeats pain-point vocabulary,
which means competitor product pages and editorial roundups (stuffed with
"glare", "polarized", "eye strain") score as high as real user complaints.
Embedding similarity to real-voice exemplars should separate the two.
"""

from __future__ import annotations

import math
from typing import Optional

import voyageai

from norman.config import USE_SEMANTIC_SCORING, VOYAGE_API_KEY


# First-person pain-point exemplars. Written to sound like real Reddit /
# forum posters — not like the keyword table. Deliberately varied across
# activities (driving, fishing, golf, riding) and failure modes (glare,
# fog, strain, distortion, fit).
SEED_EXEMPLARS: list[str] = [
    "driving home yesterday I literally could not see the road, the sun was hitting the windshield and my sunglasses did nothing",
    "bought these supposedly polarized sunglasses and my eyes are still killing me after a day on the water, there's still glare everywhere",
    "anyone else get a splitting headache after a long drive into the sun? my current shades aren't cutting it",
    "fishing all morning and the glare off the water made it impossible to see fish, what am I doing wrong with my lenses",
    "I wear glasses for golf and the contrast on the greens is terrible, everything looks washed out with most tints",
    "rode for 4 hours today and my eyes are burning, wind getting behind the lens and bright sun both roasting me",
    "every pair of sunglasses I own fogs up the second I stop moving, this is the third brand I've tried",
    "looking for actual honest reviews not sponsored garbage, need sunglasses that handle bright snow glare",
    "the distortion at the edges of these lenses is making me nauseous when I turn my head while riding",
    "why does no one make sunglasses that actually block glare from wet pavement, I keep almost getting into accidents",
    "my wife says I'm squinting constantly and getting wrinkles, my current sunglasses clearly aren't dark enough",
    "I need ANSI rated shooting glasses that don't feel like safety goggles, every option looks terrible",
    "switched to polarized last year and honestly I can't tell the difference, still getting eye strain by 3pm",
    "sunglasses kept slipping off my face every time I leaned over the boat, need something that actually stays put",
    "driving into a low winter sun with these shades on and I might as well be blind, dangerous honestly",
    "got prescription sunglasses from the eye doctor and the glare is WORSE than my $20 gas station pair, what",
    "anyone find sunglasses that work for both early morning fishing and midday when the sun is overhead",
    "the edges of my sunglasses let so much side light in that I basically can't use them while driving",
    "3 hours on the motorcycle and I got home with a pounding headache right behind my eyes, sun was brutal",
    "literally every sunglasses review on YouTube is a sponsored ad, where do real people talk about what actually works",
]


_client: Optional[voyageai.Client] = None
_seed_vectors: Optional[list[list[float]]] = None


def _get_client() -> voyageai.Client:
    global _client
    if _client is None:
        if not VOYAGE_API_KEY:
            raise RuntimeError(
                "VOYAGE_API_KEY not configured — set it in the environment "
                "or fall back to norman.scoring (keyword) by unsetting "
                "USE_SEMANTIC_SCORING."
            )
        _client = voyageai.Client(api_key=VOYAGE_API_KEY)
    return _client


def embed_text(text: str) -> list[float]:
    """Return a voyage-3-lite embedding vector for `text`."""
    client = _get_client()
    result = client.embed([text], model="voyage-3-lite", input_type="document")
    return result.embeddings[0]


def _ensure_seed_cache() -> list[list[float]]:
    """Compute seed embeddings on first call and cache for subsequent calls."""
    global _seed_vectors
    if _seed_vectors is None:
        client = _get_client()
        # Batch embed all seeds in a single request.
        result = client.embed(
            SEED_EXEMPLARS, model="voyage-3-lite", input_type="document"
        )
        _seed_vectors = result.embeddings
    return _seed_vectors


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def score_semantic(text: str) -> tuple[int, str]:
    """Score `text` by max cosine similarity against the seed exemplars.

    Returns (score_0_to_100, best_matching_exemplar).

    Cosine on voyage-3-lite vectors of English text typically sits in
    roughly [0.2, 0.9] for any two real sentences. We linearly map the raw
    cosine [0, 1] to [0, 100]; the relative ranking is what matters for
    the threshold comparison, not the absolute calibration.
    """
    if not text or not text.strip():
        return 0, ""

    # Truncate very long scraped pages — voyage-3-lite has a 32k context
    # but we gain nothing from embedding a whole article for scoring, and
    # noisy boilerplate can dominate the vector. First ~1500 chars is plenty.
    trimmed = text[:1500]

    seeds = _ensure_seed_cache()
    query_vec = embed_text(trimmed)

    best_sim = -1.0
    best_exemplar = ""
    for seed_text, seed_vec in zip(SEED_EXEMPLARS, seeds):
        sim = _cosine(query_vec, seed_vec)
        if sim > best_sim:
            best_sim = sim
            best_exemplar = seed_text

    score = max(0, min(100, int(round(best_sim * 100))))
    return score, best_exemplar


def score_lead(text: str) -> tuple[list[str], int]:
    """Unified scoring entry point for scouts.

    Dispatches based on USE_SEMANTIC_SCORING so the scouts can keep the
    `(keywords, score)` shape they already use in Lead construction. When
    semantic scoring is enabled we stash the best-matching exemplar in
    the keywords field (single-element list) so it shows up in downstream
    logs / Discord output; otherwise we fall through to the substring
    keyword scorer.
    """
    if USE_SEMANTIC_SCORING:
        score, exemplar = score_semantic(text)
        # Truncate the exemplar so it renders sanely in the existing UI —
        # downstream code joins keywords with commas.
        tag = f"sem:{exemplar[:60]}" if exemplar else "sem:"
        return [tag], score

    # Lazy import so scoring_v2 can be imported without pulling in the
    # keyword table when only semantic scoring is needed.
    from norman.scoring import score_text
    return score_text(text)
