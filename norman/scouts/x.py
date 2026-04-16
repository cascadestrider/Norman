from norman.scouts.base import BaseScout
from norman.models import ScoutResult
from norman.config import X_BEARER_TOKEN


class XScout(BaseScout):
    name = "X"
    source = "x"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        if not X_BEARER_TOKEN:
            return ScoutResult(
                source=self.source,
                leads=[],
                errors=["X/Twitter scout skipped — no API credentials configured (X_BEARER_TOKEN missing)"],
            )
        # TODO: Implement when API key is available
        return ScoutResult(source=self.source, leads=[], errors=[])
