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
    GOOGLE_QUERIES,
    SCORE_THRESHOLD,
)


class GoogleScout(BaseScout):
    name = "Google"
    source = "google"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []

        if not SERP_API_KEY:
            errors.append("Google scout skipped — no SERP_API_KEY configured")
            return ScoutResult(source=self.source, leads=leads, errors=errors)

        visited_this_run: set[str] = set()

        for segment, queries in GOOGLE_QUERIES.items():
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
                "q": query,
                "api_key": SERP_API_KEY,
                "num": 5,
            })
            results = search.get_dict()
            for r in results.get("organic_results", []):
                urls.append(r["link"])
        except Exception as e:
            errors.append(f"SerpAPI failed for '{query}': {e}")
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
                source="google",
                platform="web",
                snippet=text[:300],
            )
        except Exception as e:
            errors.append(f"Scrape failed: {url} — {e}")
            return None

    @staticmethod
    def _is_excluded(url: str) -> bool:
        return any(domain in url for domain in EXCLUDED_DOMAINS)
