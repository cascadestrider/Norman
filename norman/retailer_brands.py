"""URL-and-title brand extraction for retailer leads.

First-pass extractor expected to refine over weeks of production data. It
covers the common cases by URL signal (native retailer hosts → second-level
domain, title-cased), falls back to title patterns where the URL doesn't
carry the brand (aggregator marketplaces, social platforms), and returns
descriptive sentinels for the edge cases rather than failing.
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from urllib.parse import urlparse


KNOWN_AGGREGATORS: set[str] = {
    "amazon.com",
    "ebay.com",
    "walmart.com",
    "target.com",
    "costco.com",
    "wayfair.com",
    "bestbuy.com",
    "etsy.com",
    "aliexpress.com",
}

KNOWN_SOCIAL: set[str] = {
    "x.com",
    "twitter.com",
    "reddit.com",
    "youtube.com",
    "youtu.be",
    "instagram.com",
    "facebook.com",
    "tiktok.com",
    "pinterest.com",
}

# Cosmetic subdomains (regional / channel / device) we strip before reading
# the second-level domain. Keeps us.mauijim.com → mauijim.com.
_STRIP_SUBDOMAINS: set[str] = {
    "www", "shop", "store", "m", "mobile", "en",
    "us", "uk", "eu", "ca", "au", "de", "fr", "jp",
}

# Title-leading tokens that aren't brand names — we skip past these when
# trying to pull a brand out of the title text.
_TITLE_STOPWORDS: set[str] = {
    "the", "a", "an", "best", "top", "buy", "shop", "new", "review",
    "reviews", "guide", "compare",
}

# Curated multi-word brand display map: SLD → human-readable brand name.
# Title-casing a concatenated SLD (fostergrant → Fostergrant) loses the word
# break, so we look up the SLD here first and fall through to title-case when
# absent. Grows as new multi-word brands surface in production retailer data.
KNOWN_MULTI_WORD: dict[str, str] = {
    "fostergrant": "Foster Grant",
    "wileyx": "Wiley X",
    "warbyparker": "Warby Parker",
    "tifosioptics": "Tifosi Optics",
    "riaeyewear": "RIA Eyewear",
    "fadeddayssunglasses": "Faded Days",
    "mauijim": "Maui Jim",
    "shadyrays": "Shady Rays",
    "smithoptics": "Smith Optics",
    "methodseven": "Method Seven",
    "vonzipper": "Von Zipper",
}

# Future work: the X reseller pattern. Affiliate accounts like @ForemostOnline
# and @BrandFusionLtd post about other people's brands ("Oakley", "Sunwise"),
# so extracting the poster handle captures the reseller identity rather than
# the brand being marketed. When X retailer signal volume grows, refine by
# mining the post body for the actual brand being marketed.


def extract_brand(url: str, title: str = "", snippet: str = "") -> str:
    """Return a best-guess brand label for a retailer lead.

    1. Aggregator host (amazon.com, etc.) → try the title; else "Unknown (via <host>)".
    2. Social host (x.com, reddit.com, etc.) → derive from path or title; else "Social: <host>".
    3. Native retailer host → title-case the second-level domain.
    """
    host = _hostname(url)
    if not host:
        return _brand_from_title(title) or "Unknown"

    if host in KNOWN_AGGREGATORS:
        brand = _brand_from_title(title)
        return brand if brand else f"Unknown (via {host})"

    if host in KNOWN_SOCIAL:
        return _social_brand(host, url, title)

    sld = host.split(".")[0]
    if not sld:
        return "Unknown"
    return KNOWN_MULTI_WORD.get(sld, sld.title())


def _hostname(url: str) -> str:
    """Lowercased hostname with cosmetic subdomains stripped. Empty on parse failure."""
    try:
        parsed = urlparse(url)
    except Exception:
        return ""
    host = (parsed.hostname or "").lower().strip()
    if not host:
        return ""
    parts = host.split(".")
    while len(parts) > 2 and parts[0] in _STRIP_SUBDOMAINS:
        parts = parts[1:]
    return ".".join(parts)


def _brand_from_title(title: str) -> str:
    """Return the first capitalized non-stopword token in the title."""
    if not title:
        return ""
    cleaned = re.sub(r"\s+", " ", title.strip())
    for tok in cleaned.split(" "):
        word = re.sub(r"^[^A-Za-z]+|[^A-Za-z]+$", "", tok)
        if not word:
            continue
        if word.lower() in _TITLE_STOPWORDS:
            continue
        if word[0].isupper():
            return word
    return ""


def _social_brand(host: str, url: str, title: str) -> str:
    """Derive a brand-ish label from a social URL's path; fall back to the title."""
    try:
        parsed = urlparse(url)
        parts = [p for p in parsed.path.split("/") if p]
    except Exception:
        parts = []

    if host in ("x.com", "twitter.com"):
        if parts:
            return f"X: @{parts[0]}"
        return "Social: x.com"

    if host == "reddit.com":
        if len(parts) >= 2 and parts[0].lower() == "r":
            return f"Reddit /r/{parts[1]}"
        return "Social: reddit.com"

    brand = _brand_from_title(title)
    if brand:
        return brand
    return f"Social: {host}"


# ---------------------------------------------------------------------------
# Novel-vs-recurring brand tracking
# ---------------------------------------------------------------------------

def known_brands_before(conn: sqlite3.Connection, before_date: str) -> set[str]:
    """Set of brands resolved from retailer leads with date_found < before_date.

    Computed by scanning the leads table and running extract_brand against
    each historical row. The daily report should call this once per run and
    pass the resulting set into a tight loop, rather than calling
    is_brand_novel per lead (which would re-scan each time).
    """
    rows = conn.execute(
        "SELECT url, title FROM leads "
        "WHERE source_type = 'retailer' AND date_found < ?",
        (before_date,),
    ).fetchall()
    return {extract_brand(url, title or "") for url, title in rows}


def is_brand_novel(brand: str, conn: sqlite3.Connection) -> bool:
    """True when no retailer lead from a prior date resolves to this brand.

    Convenience wrapper around known_brands_before for one-off lookups.
    Bulk callers should use known_brands_before directly to avoid repeated
    full-table scans.
    """
    today = date.today().isoformat()
    return brand not in known_brands_before(conn, today)
