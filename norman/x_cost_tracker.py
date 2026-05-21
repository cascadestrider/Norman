"""Per-call cost tracker for the X (Twitter) scout.

Kept separate from norman.token_tracker because X is priced per-post-read
with a flat unit price, not by input/output tokens against MODEL_PRICING.
The orchestrator's run-summary block reads format_line() to surface spend.
"""

from __future__ import annotations

# X v2 recent search pay-as-you-go rate as of 2026-05 ($0.005 per post
# returned to the caller). Updating this single constant if the rate
# changes keeps the math honest without touching the scout.
X_COST_PER_POST_USD = 0.005


class XCostTracker:
    """Accumulates X API call + post-read counts across a Norman run."""

    def __init__(self) -> None:
        self.calls = 0
        self.posts_read = 0

    def record(self, calls: int, posts_read: int) -> None:
        self.calls += calls
        self.posts_read += posts_read

    def estimated_cost_usd(self) -> float:
        return self.posts_read * X_COST_PER_POST_USD

    def format_line(self) -> str:
        """Run-summary line, or "" when no X calls were made this run."""
        if self.calls == 0:
            return ""
        return (
            f"X API cost: {self.calls} calls, {self.posts_read} posts read, "
            f"~${self.estimated_cost_usd():.4f} (estimate)"
        )


# ── Module-level singleton ────────────────────────────────────────────────
x_cost_tracker = XCostTracker()
