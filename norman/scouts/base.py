from abc import ABC, abstractmethod
from typing import Optional
from urllib.parse import urlparse, urlunparse

from norman.events import TournamentEvent
from norman.models import Lead, ScoutResult


def suffix_host_match(url: str, blocked: frozenset[str]) -> bool:
    """Return True if the URL's hostname equals or is a subdomain of any entry
    in `blocked`. Matches by hostname suffix on dot boundaries, so
    "groups.facebook.com" matches "facebook.com" but "notfacebook.com" does
    not. Used to skip auth-walled domains (config.BLOCKED_DOMAINS) that
    reliably fail to scrape unauthenticated.
    """
    try:
        host = (urlparse(url).hostname or "").lower()
    except ValueError:
        return False
    if not host:
        return False
    for domain in blocked:
        if host == domain or host.endswith("." + domain):
            return True
    return False


def title_matches_error_pattern(title: str, patterns: frozenset[str]) -> bool:
    """Return True if `title` looks like a scrape failure / auth wall.

    Matches when the lowercased, stripped title exactly equals a pattern, or
    (for short titles < 50 chars) contains a pattern as a substring. The
    short-title guard prevents long, genuine titles that happen to contain a
    word like "error" mid-sentence from being dropped. See
    config.ERROR_TITLE_PATTERNS — this catches failures that slipped past the
    domain-level blocklist (network errors, Cloudflare, sudden content blocks).
    """
    t = (title or "").lower().strip()
    if not t:
        return False
    if t in patterns:
        return True
    if len(t) < 50 and any(p in t for p in patterns):
        return True
    return False


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
    def run(
        self,
        seen_urls: set[str],
        event_queries: Optional[list[str]] = None,
        active_event: Optional[TournamentEvent] = None,
    ) -> ScoutResult:
        """Execute the scout and return leads + errors.

        Args:
            seen_urls: URLs already visited in previous runs (for dedup).
            event_queries: Optional event-specific search queries. Phase 1
                scouts that don't consume them (everything except Reddit)
                may ignore both this and active_event.
            active_event: Optional active TournamentEvent during this run.

        Returns:
            ScoutResult with leads above threshold and any errors.
        """
        ...
