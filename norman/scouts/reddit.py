import time
import requests
from norman.scouts.base import BaseScout
from norman.models import Lead, ScoutResult
from norman.scoring_v2 import score_lead
from norman.config import (
    REDDIT_HEADERS,
    REDDIT_SUBREDDITS,
    REDDIT_SEARCH_TERMS,
    SCORE_THRESHOLD,
)


class RedditScout(BaseScout):
    name = "Reddit"
    source = "reddit"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []
        visited_this_run: set[str] = set()

        for segment, subreddits in REDDIT_SUBREDDITS.items():
            for sub in subreddits:
                # Max 2 search terms per subreddit per run
                for term in REDDIT_SEARCH_TERMS[:2]:
                    post_urls = self._search_subreddit(sub, term, errors)
                    for url in post_urls:
                        if url in seen_urls or url in visited_this_run:
                            continue
                        visited_this_run.add(url)
                        lead = self._process_post(url, errors)
                        if lead and lead.score >= SCORE_THRESHOLD:
                            leads.append(lead)
                    time.sleep(1)

        return ScoutResult(source=self.source, leads=leads, errors=errors)

    def _search_subreddit(self, sub: str, term: str, errors: list[str]) -> list[str]:
        urls = []
        api_url = (
            f"https://www.reddit.com/r/{sub}/search.json"
            f"?q={term}&sort=new&limit=5&restrict_sr=1"
        )
        try:
            resp = requests.get(api_url, headers=REDDIT_HEADERS, timeout=10)
            if resp.status_code == 429:
                time.sleep(5)
                resp = requests.get(api_url, headers=REDDIT_HEADERS, timeout=10)
            if resp.status_code == 200:
                posts = resp.json().get("data", {}).get("children", [])
                for post in posts:
                    permalink = post.get("data", {}).get("permalink", "")
                    if permalink:
                        urls.append(f"https://www.reddit.com{permalink}")
            else:
                errors.append(f"r/{sub} search '{term}' failed: {resp.status_code}")
        except Exception as e:
            errors.append(f"r/{sub} search '{term}' failed: {e}")
        return urls

    def _process_post(self, url: str, errors: list[str]) -> Lead | None:
        try:
            json_url = url.rstrip("/") + ".json?limit=50"
            resp = requests.get(json_url, headers=REDDIT_HEADERS, timeout=10)
            if resp.status_code != 200:
                errors.append(f"Reddit post fetch failed: {url} ({resp.status_code})")
                return None
            data = resp.json()
            post_data = data[0]["data"]["children"][0]["data"]
            title = post_data.get("title", "Reddit Post")
            body = post_data.get("selftext", "")

            comments = []
            for comment in data[1]["data"]["children"][:20]:
                c = comment.get("data", {})
                if "body" in c:
                    comments.append(c["body"])

            full_text = f"{title} {body} " + " ".join(comments)
            found_kws, score = score_lead(full_text)

            return Lead(
                url=url,
                title=title,
                score=score,
                keywords=found_kws,
                source="reddit",
                platform="reddit",
                snippet=full_text[:300],
            )
        except Exception as e:
            errors.append(f"Reddit post scrape failed: {url} — {e}")
            return None
