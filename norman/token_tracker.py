"""
Singleton token-usage tracker for the Norman pipeline.

Accumulates input/output token counts per agent and model across
a single pipeline run, then produces a cost summary.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from norman.config import MODEL_PRICING


@dataclass
class _UsageBucket:
    input_tokens: int = 0
    output_tokens: int = 0


class TokenTracker:
    """Accumulates token usage across an entire Norman run."""

    def __init__(self) -> None:
        self._by_agent: dict[str, _UsageBucket] = {}
        self._by_model: dict[str, _UsageBucket] = {}
        self._total = _UsageBucket()
        # Track (agent, model) pairs so we can compute cost accurately
        self._by_agent_model: dict[tuple[str, str], _UsageBucket] = {}

    # --------------------------------------------------------------------- #
    # Public API
    # --------------------------------------------------------------------- #

    def record(
        self,
        agent_name: str,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> None:
        """Record token usage for one LLM call."""
        for bucket_map, key in [
            (self._by_agent, agent_name),
            (self._by_model, model),
        ]:
            bucket = bucket_map.setdefault(key, _UsageBucket())
            bucket.input_tokens += input_tokens
            bucket.output_tokens += output_tokens

        am_key = (agent_name, model)
        am_bucket = self._by_agent_model.setdefault(am_key, _UsageBucket())
        am_bucket.input_tokens += input_tokens
        am_bucket.output_tokens += output_tokens

        self._total.input_tokens += input_tokens
        self._total.output_tokens += output_tokens

    def summary(self) -> dict:
        """Return a structured summary of all recorded usage.

        Returns
        -------
        dict with keys:
            by_agent  – {agent_name: {input_tokens, output_tokens, cost}}
            by_model  – {model: {input_tokens, output_tokens, cost}}
            total     – {input_tokens, output_tokens, cost}
        """
        return {
            "by_agent": {
                agent: self._bucket_with_cost(agent, self._by_agent_model)
                for agent in self._by_agent
            },
            "by_model": {
                model: {
                    "input_tokens": b.input_tokens,
                    "output_tokens": b.output_tokens,
                    "cost": self._cost(model, b),
                }
                for model, b in self._by_model.items()
            },
            "total": {
                "input_tokens": self._total.input_tokens,
                "output_tokens": self._total.output_tokens,
                "cost": sum(
                    self._cost(model, b) for model, b in self._by_model.items()
                ),
            },
        }

    # --------------------------------------------------------------------- #
    # Internals
    # --------------------------------------------------------------------- #

    def _cost(self, model: str, bucket: _UsageBucket) -> float:
        pricing = MODEL_PRICING.get(model, {"input": 0.0, "output": 0.0})
        return (
            bucket.input_tokens * pricing["input"] / 1_000_000
            + bucket.output_tokens * pricing["output"] / 1_000_000
        )

    def _bucket_with_cost(
        self,
        agent: str,
        am_map: dict[tuple[str, str], _UsageBucket],
    ) -> dict:
        bucket = self._by_agent[agent]
        cost = sum(
            self._cost(model, b)
            for (a, model), b in am_map.items()
            if a == agent
        )
        return {
            "input_tokens": bucket.input_tokens,
            "output_tokens": bucket.output_tokens,
            "cost": cost,
        }


# ── Module-level singleton ────────────────────────────────────────────────
token_tracker = TokenTracker()
