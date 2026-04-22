import requests
from bs4 import BeautifulSoup
from serpapi import GoogleSearch
from norman.scouts.base import BaseScout, reddit_fetch_url
from norman.models import Lead, ScoutResult
from norman.scoring_v2 import score_lead
from norman.query_selector import pick_queries
from norman.config import (
    SERP_API_KEY,
    WEB_HEADERS,
    EXCLUDED_DOMAINS,
    GOOGLE_QUERIES,
    SCORE_THRESHOLD,
)

GOOGLE_QUERIES_PER_SEGMENT = 10


class GoogleScout(BaseScout):
    name = "Google"
    source = "google"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []
        notes: list[str] = []

        if not SERP_API_KEY:
            errors.append("Google scout skipped — no SERP_API_KEY configured")
            return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

        visited_this_run: set[str] = set()
        total_pool = sum(len(q) for q in GOOGLE_QUERIES.values())
        selected_count = 0

        for segment, queries in GOOGLE_QUERIES.items():
            selected = pick_queries(queries, GOOGLE_QUERIES_PER_SEGMENT)
            selected_count += len(selected)
            for query in selected:
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

        notes.append(
            f"Google: selected {selected_count} of {total_pool} queries today "
            f"(n={GOOGLE_QUERIES_PER_SEGMENT}/segment)"
        )
        return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

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
            fetch_url = reddit_fetch_url(url)
            resp = requests.get(fetch_url, headers=WEB_HEADERS, timeout=10)
            soup = BeautifulSoup(resp.text, "html.parser")
            text = " ".join(
                p.get_text() for p in soup.find_all(["p", "div"]) if len(p.get_text()) > 30
            )
            title = soup.title.string if soup.title else "Unknown"
            found_kws, score = score_lead(text)

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
