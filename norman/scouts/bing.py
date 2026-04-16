import requests
from bs4 import BeautifulSoup
from serpapi import GoogleSearch
from norman.scouts.base import BaseScout
from norman.models import Lead, ScoutResult
from norman.scoring import score_text
from norman.config import (
    SERP_API_KEY,
    WEB_HEADERS,
    EXCLUDED_DOMAINS,
    SCORE_THRESHOLD,
)

# Bing surfaces different content than Google — more forum threads and
# hobbyist communities, skewing 35-65 demographic (golf/fishing alignment).
BING_QUERIES = {
    "fishing": [
        "polarized sunglasses fishing glare site:forum OR site:reddit OR review",
        "fishing sunglasses eye strain water glare",
        "best polarized fishing sunglasses comparison",
    ],
    "golf": [
        "golf sunglasses glare reduction review",
        "best sunglasses for golfing bright sun",
        "anti-glare sunglasses golfers forum",
    ],
    "motorcycle": [
        "motorcycle sunglasses UV glare protection review",
        "best riding sunglasses sun glare forum",
        "motorbike sunglasses eye protection",
    ],
    "commuter": [
        "best driving sunglasses glare review",
        "sunglasses for driving into sun",
        "eye strain driving bright sunlight forum",
        "polarized sunglasses blinded glare",
        "anti-glare sunglasses outdoor activities",
    ],
}


class BingScout(BaseScout):
    """Discovers and scores web content via Bing (SerpAPI Bing engine).

    Complements GoogleScout — Bing surfaces different forum threads and
    review sites. Same scrape-and-score pattern as google.py.
    Reuses SERP_API_KEY (shared quota with Google and Amazon scouts).
    """

    name = "Bing"
    source = "bing"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []

        if not SERP_API_KEY:
            errors.append("Bing scout skipped — no SERP_API_KEY configured")
            return ScoutResult(source=self.source, leads=leads, errors=errors)

        visited_this_run: set[str] = set()

        for segment, queries in BING_QUERIES.items():
            for query in queries:
                urls = self._search(query, errors)
                for url in urls:
                    if url in seen_urls or url in visited_this_run:
                        continue
                    if self._is_excluded(url):
                        continue
                    visited_this_run.add(url)
                    lead = self._scrape_and_score(url, errors)
                    if lead and lead.score >= SCORE_THRESHOLD:
                        leads.append(lead)

        return ScoutResult(source=self.source, leads=leads, errors=errors)

    def _search(self, query: str, errors: list[str]) -> list[str]:
        urls = []
        try:
            search = GoogleSearch({
                "engine": "bing",
                "q": query,
                "api_key": SERP_API_KEY,
                "count": 5,
            })
            results = search.get_dict()
            for r in results.get("organic_results", []):
                link = r.get("link") or r.get("url", "")
                if link:
                    urls.append(link)
        except Exception as e:
            errors.append(f"SerpAPI Bing failed for '{query}': {e}")
        return urls

    def _scrape_and_score(self, url: str, errors: list[str]) -> Lead | None:
        try:
            resp = requests.get(url, headers=WEB_HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            text = " ".join(
                p.get_text() for p in soup.find_all(["p", "div"]) if len(p.get_text()) > 30
            )
            title = soup.title.string if soup.title else "Unknown"
            found_kws, score = score_text(text)

            return Lead(
                url=url,
                title=title,
                score=score,
                keywords=found_kws,
                source="bing",
                platform="web",
                snippet=text[:300],
            )
        except Exception as e:
            errors.append(f"Scrape failed: {url} — {e}")
            return None

    @staticmethod
    def _is_excluded(url: str) -> bool:
        return any(domain in url for domain in EXCLUDED_DOMAINS)
