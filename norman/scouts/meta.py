from norman.scouts.base import BaseScout
from norman.models import ScoutResult
from norman.config import META_ACCESS_TOKEN


class MetaScout(BaseScout):
    name = "Meta"
    source = "meta"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        if not META_ACCESS_TOKEN:
            return ScoutResult(
                source=self.source,
                leads=[],
                errors=["Meta scout skipped — no API credentials configured (META_ACCESS_TOKEN missing)"],
            )
        # TODO: Implement when API key is available
        return ScoutResult(source=self.source, leads=[], errors=[])
