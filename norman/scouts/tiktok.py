from norman.scouts.base import BaseScout
from norman.models import ScoutResult
from norman.config import TIKTOK_ACCESS_TOKEN


class TikTokScout(BaseScout):
    name = "TikTok"
    source = "tiktok"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        if not TIKTOK_ACCESS_TOKEN:
            return ScoutResult(
                source=self.source,
                leads=[],
                errors=["TikTok scout skipped — no API credentials configured (TIKTOK_ACCESS_TOKEN missing)"],
            )
        # TODO: Implement when API key is available
        return ScoutResult(source=self.source, leads=[], errors=[])
