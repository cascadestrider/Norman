"""Deterministic query rotation.

pick_queries(pool, n, seed) returns n queries from pool, selected
deterministically based on seed. Same (pool, n, seed) always returns
the same queries; different seeds return different slices. Defaults
seed to today's ISO date so the rotation advances once per day.
"""

from __future__ import annotations

import hashlib
import random
from datetime import date


def pick_queries(pool: list[str], n: int, seed: str | None = None) -> list[str]:
    """Deterministically pick n queries from pool based on seed.

    Args:
        pool: The full query pool to sample from.
        n: Number of queries to return.
        seed: Arbitrary seed string. Defaults to today's ISO date.

    Returns:
        A list of n queries (or a copy of the full pool if n >= len(pool)).
    """
    if seed is None:
        seed = date.today().isoformat()
    if n >= len(pool):
        return list(pool)
    digest = hashlib.md5(seed.encode("utf-8")).hexdigest()
    rng = random.Random(digest)
    return rng.sample(pool, n)
