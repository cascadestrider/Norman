"""Semantic scoring for Norman leads.

Replaces the substring keyword match in scoring.py with cosine similarity
against a hand-written set of first-person customer-voice exemplars.

Why: keyword scoring rewards any page that repeats pain-point vocabulary,
which means competitor product pages and editorial roundups (stuffed with
"glare", "polarized", "eye strain") score as high as real user complaints.
Embedding similarity to real-voice exemplars should separate the two.

Seed exemplars refreshed 2026-04-21 from client pain-point input:
- Golf vision (ball tracking, depth perception, reading greens, water hazards)
- Screen visibility (phone / watch / GPS / HUD with polarized lenses)
- Headaches & sensitivity (post-concussion, photophobia, color distortion,
  99% polarization side-effects)

Fishing exemplars preserved from prior version (client input did not cover
fishing; existing Reddit fishing pain points are still accurate signal).
"""

from __future__ import annotations

import math
from typing import Optional

import voyageai

from norman.config import USE_SEMANTIC_SCORING, VOYAGE_API_KEY


# First-person pain-point exemplars. Written to sound like real Reddit /
# forum posters — not like the keyword table. Distribution across the five
# active segments (golf 5, commuter 3, motorcycle 3, fishing 2, sensitivity 7).
# Sensitivity gets the largest share because the file 3 pain is the most
# emotionally loaded and underserved category per client input.
SEED_EXEMPLARS: list[str] = [
    # Golf — file 1 (5 exemplars)
    "took my sunglasses off on every tee shot because I literally can't track the ball with them on, this is absurd",
    "the greens look completely fake with my polarized lenses, I can't read break anymore and my handicap is suffering",
    "why does every 'golf' sunglass option out there look like something from a ladies boutique with the pink and purple lenses",
    "bought polarized sunglasses specifically for golf and now depth perception feels weird on approach shots, anyone else",
    "water hazards still blast glare right back at me through my polarized, what polarization percentage am I actually supposed to get",

    # Commuter / screen visibility — file 2 (3 exemplars)
    "can't see my phone screen at all with these polarized sunglasses on, have to take them off at every stoplight to check maps",
    "my smartwatch is completely invisible with my sunglasses, what's the point of the watch if I can't glance at it outside",
    "GPS screen goes dark and pixelated the moment I put my polarized sunglasses on, this is genuinely dangerous while driving",

    # Motorcycle / screen visibility — file 2 (3 exemplars)
    "the heads up display on my helmet is completely gone when I put my polarized sunglasses on, makes the HUD useless",
    "riding with polarized sunglasses and my dashboard is pitch black, have to keep lifting them to check speed",
    "need sunglasses that don't kill my phone screen when I'm navigating on the bike, every polarized pair has this problem",

    # Sensitivity — file 3 (7 exemplars)
    "my sunglasses give me an actual headache after 10 minutes of driving, everything feels gray and dreary and wrong",
    "post-concussion and the light sensitivity is brutal, every pair of sunglasses I try either does nothing or makes it worse",
    "eyes hurt after wearing my sunglasses for even a short trip, feels like something is off about how they're filtering the light",
    "I just want to see the world accurately, these polarized lenses make greens look oversaturated and everything else washed out",
    "does anyone else get headaches from polarized sunglasses, I'm starting to think the 99 percent polarization is the actual problem",
    "LED headlights at night still blast glare through my polarized pair, what are these lenses actually doing at this point",
    "dealing with photophobia and every sunglass I buy is either way too dark or not protective enough, need something tunable",

    # Fishing — preserved from prior SEED_EXEMPLARS (2 exemplars)
    "fishing all morning and the glare off the water made it impossible to see fish, what am I doing wrong with my lenses",
    "bought these supposedly polarized sunglasses and my eyes are still killing me after a day on the water, there's still glare everywhere",
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
