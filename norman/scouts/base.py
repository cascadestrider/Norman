from abc import ABC, abstractmethod
from urllib.parse import urlparse, urlunparse

from norman.models import Lead, ScoutResult


def reddit_fetch_url(url: str) -> str:
    """Return the URL to fetch for scraping, rewriting reddit.com hosts to
    old.reddit.com. The old frontend serves real thread titles in the initial
    HTML; the new frontend loads them via JS. The original URL is preserved
    for storage and dedup.
    """
    try:
        parsed = urlparse(url)
    except ValueError:
        return url
    if parsed.netloc in ("www.reddit.com", "reddit.com", "m.reddit.com"):
        return urlunparse(parsed._replace(netloc="old.reddit.com"))
    return url


class BaseScout(ABC):
    """Base class for all Norman scout agents."""

    name: str = "base"
    source: str = "base"

    @abstractmethod
    def run(self, seen_urls: set[str]) -> ScoutResult:
        """Execute the scout and return leads + errors.

        Args:
            seen_urls: URLs already visited in previous runs (for dedup).

        Returns:
            ScoutResult with leads above threshold and any errors.
        """
        ...
