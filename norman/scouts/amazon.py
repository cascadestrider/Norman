from serpapi import GoogleSearch
from norman.scouts.base import BaseScout
from norman.models import Lead, ScoutResult
from norman.scoring import score_text
from norman.config import SERP_API_KEY, SCORE_THRESHOLD

# Competitor-focused queries first (highest value) — buyers who already
# purchased and were disappointed are the exact ad target.
# Category searches follow for high-intent buyers still deciding.
AMAZON_QUERIES = [
    # Competitor product reviews
    "Oakley polarized sunglasses fishing",
    "Costa Del Mar polarized sunglasses",
    "Maui Jim polarized sunglasses golf",
    "Oakley sunglasses motorcycle riding",
    "polarized sunglasses driving glare",
    # Category searches
    "best polarized sunglasses fishing",
    "best sunglasses for golf",
    "motorcycle sunglasses UV protection",
    "polarized sunglasses for driving",
    "anti-glare sunglasses outdoor",
]

# Amazon-specific extra keywords — review/complaint language not in shared table
AMAZON_EXTRA_KEYWORDS = {
    "fogging": 5,
    "scratched": 3,
    "disappointed": 3,
}


def _score_amazon_text(text: str) -> tuple[list[str], int]:
    """Score using shared keywords + Amazon-specific complaint keywords."""
    found_kws, base_score = score_text(text)
    text_lower = text.lower()
    extra_score = 0
    for kw, weight in AMAZON_EXTRA_KEYWORDS.items():
        count = text_lower.count(kw)
        if count > 0:
            found_kws.append(kw)
            extra_score += weight * min(count, 3)
    return found_kws, min(base_score + extra_score, 100)


class AmazonScout(BaseScout):
    """Mines Amazon competitor product reviews via SerpAPI Amazon engine.

    Does NOT scrape amazon.com directly — all data comes from SerpAPI results.
    Competitor reviews (Oakley, Costa, Maui Jim) are highest-value signals:
    buyers who already purchased and were disappointed are prime ad targets.
    """

    name = "Amazon"
    source = "amazon"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []

        if not SERP_API_KEY:
            errors.append("Amazon scout skipped — no SERP_API_KEY configured")
            return ScoutResult(source=self.source, leads=leads, errors=errors)

        seen_asins: set[str] = set()

        for query in AMAZON_QUERIES:
            products = self._search(query, errors)
            for product in products:
                asin = product.get("asin", "")
                if not asin or asin in seen_asins:
                    continue

                url = f"https://www.amazon.com/dp/{asin}"
                if url in seen_urls:
                    continue

                seen_asins.add(asin)

                # Score review snippets + title returned directly by SerpAPI
                title = product.get("title", "Amazon Product")
                snippet_parts = [title]

                # Pull any review/description text SerpAPI returns in the result
                for field in ("reviews", "description", "snippet", "extensions"):
                    val = product.get(field)
                    if isinstance(val, str):
                        snippet_parts.append(val)
                    elif isinstance(val, list):
                        snippet_parts.extend(str(v) for v in val)
                    elif isinstance(val, dict):
                        snippet_parts.extend(str(v) for v in val.values())

                combined_text = " ".join(snippet_parts)
                found_kws, score = _score_amazon_text(combined_text)

                if score >= SCORE_THRESHOLD:
                    leads.append(Lead(
                        url=url,
                        title=title,
                        score=score,
                        keywords=found_kws,
                        source="amazon",
                        platform="amazon",
                        snippet=combined_text[:300],
                    ))

        return ScoutResult(source=self.source, leads=leads, errors=errors)

    def _search(self, query: str, errors: list[str]) -> list[dict]:
        try:
            search = GoogleSearch({
                "engine": "amazon",
                "amazon_domain": "amazon.com",
                "q": query,
                "api_key": SERP_API_KEY,
            })
            results = search.get_dict()
            return results.get("organic_results", [])[:5]
        except Exception as e:
            errors.append(f"SerpAPI Amazon failed for '{query}': {e}")
            return []
