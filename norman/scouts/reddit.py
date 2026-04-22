import time
from itertools import cycle
import requests
from norman.scouts.base import BaseScout
from norman.models import Lead, ScoutResult
from norman.scoring_v2 import score_lead
from norman.query_selector import pick_queries
from norman.config import (
    REDDIT_HEADERS,
    REDDIT_SUBREDDITS,
    REDDIT_SEARCH_TERMS,
    SCORE_THRESHOLD,
)

REDDIT_SEARCH_TERMS_PER_RUN = 8


class RedditScout(BaseScout):
    name = "Reddit"
    source = "reddit"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []
        notes: list[str] = []
        visited_this_run: set[str] = set()

        all_subs = [
            sub for subs in REDDIT_SUBREDDITS.values() for sub in subs
        ]

        # Mode 1: /new discovery — fresh posts change daily, defeats dedup
        # convergence. Score directly from listing response (title + selftext);
        # no per-post comment fetch so we stay at ~23 calls for this mode.
        new_scanned = 0
        new_qualified = 0
        for sub in all_subs:
            new_leads = self._fetch_new_posts(sub, errors)
            new_scanned += len(new_leads)
            for lead in new_leads:
                if lead.url in seen_urls or lead.url in visited_this_run:
                    continue
                visited_this_run.add(lead.url)
                if lead.score >= SCORE_THRESHOLD:
                    leads.append(lead)
                    new_qualified += 1
            time.sleep(1)
        notes.append(
            f"Reddit /new: scanned {len(all_subs)} subs, "
            f"{new_scanned} posts seen, {new_qualified} passed threshold"
        )

        # Mode 2: search — broader recall via daily-rotated term selection.
        # One call per subreddit (terms cycled) to keep total volume flat.
        selected_terms = pick_queries(REDDIT_SEARCH_TERMS, REDDIT_SEARCH_TERMS_PER_RUN)
        notes.append(
            f"Reddit search: {len(selected_terms)} of {len(REDDIT_SEARCH_TERMS)} "
            f"terms cycled across {len(all_subs)} subs → {len(all_subs)} search calls"
        )

        term_cycle = cycle(selected_terms) if selected_terms else None
        for sub in all_subs:
            if term_cycle is None:
                break
            term = next(term_cycle)
            post_urls = self._search_subreddit(sub, term, errors)
            for url in post_urls:
                if url in seen_urls or url in visited_this_run:
                    continue
                visited_this_run.add(url)
                lead = self._process_post(url, errors)
                if lead and lead.score >= SCORE_THRESHOLD:
                    leads.append(lead)
            time.sleep(1)

        return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

    def _fetch_new_posts(self, sub: str, errors: list[str]) -> list[Lead]:
        """Fetch /new listing for a subreddit and score every post returned.

        Scores from title + selftext only (no comment fetch), keeping this
        mode to one HTTP call per subreddit.
        """
        out: list[Lead] = []
        api_url = f"https://old.reddit.com/r/{sub}/new.json?limit=25"
        try:
            resp = requests.get(api_url, headers=REDDIT_HEADERS, timeout=10)
            if resp.status_code == 429:
                time.sleep(5)
                resp = requests.get(api_url, headers=REDDIT_HEADERS, timeout=10)
            if resp.status_code != 200:
                errors.append(f"r/{sub} /new failed: {resp.status_code}")
                return out
            posts = resp.json().get("data", {}).get("children", [])
            for post in posts:
                data = post.get("data", {})
                if data.get("stickied"):
                    continue
                permalink = data.get("permalink", "")
                if not permalink:
                    continue
                url = f"https://www.reddit.com{permalink}"
                title = data.get("title", "Reddit Post")
                body = data.get("selftext", "")
                text = f"{title} {body}"
                found_kws, score = score_lead(text)
                out.append(Lead(
                    url=url,
                    title=title,
                    score=score,
                    keywords=found_kws,
                    source="reddit",
                    platform="reddit",
                    snippet=text[:300],
                ))
        except Exception as e:
            errors.append(f"r/{sub} /new failed: {e}")
        return out

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
