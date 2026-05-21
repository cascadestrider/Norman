"""X (Twitter) scout against the v2 recent search endpoint.

Day-one scope is intentionally narrow because X is pay-per-use: 6 of ~10
terms rotated per run, 25 posts/query, 48-hour lookback. Cost is tracked
per call so the operator can see real spend in the run summary.

event_queries / active_event are accepted to match BaseScout but ignored;
event-aware X querying (tournament hashtags, etc.) is Phase 2.x work.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

import requests

from norman.events import TournamentEvent
from norman.models import Lead, ScoutResult
from norman.query_selector import pick_queries
from norman.scoring_v2 import score_lead
from norman.scouts.base import BaseScout
from norman.x_cost_tracker import x_cost_tracker
from norman.config import (
    SCORE_THRESHOLD,
    X_BEARER_TOKEN,
    X_LOOKBACK_HOURS,
    X_MAX_RESULTS_PER_QUERY,
    X_QUERIES_PER_RUN,
    X_SEARCH_TERMS,
)

X_RECENT_SEARCH_URL = "https://api.x.com/2/tweets/search/recent"


class XScout(BaseScout):
    name = "X"
    source = "x"

    def __init__(self) -> None:
        # Per-run counters consumed by the cost tracker (Task 4).
        self.call_count = 0
        self.posts_read = 0

    def run(
        self,
        seen_urls: set[str],
        event_queries: Optional[list[str]] = None,
        active_event: Optional[TournamentEvent] = None,
    ) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []
        notes: list[str] = []
        visited_this_run: set[str] = set()

        if not X_BEARER_TOKEN:
            errors.append(
                "X scout skipped — no API credentials configured (X_BEARER_TOKEN missing)"
            )
            return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

        selected_terms = pick_queries(X_SEARCH_TERMS, X_QUERIES_PER_RUN)
        if not selected_terms:
            return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

        start_time = (
            datetime.now(timezone.utc) - timedelta(hours=X_LOOKBACK_HOURS)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        headers = {"Authorization": f"Bearer {X_BEARER_TOKEN}"}

        total_posts = 0
        for term in selected_terms:
            posts, err = self._search(term, start_time, headers)
            if err == "AUTH_FAILED":
                # Mirrors YouTube's quotaExceeded short-circuit — stop
                # immediately so we don't keep burning calls against a bad
                # token. Already-collected leads (if any) are returned.
                errors.append(
                    "X auth failed (401/403) — stopped early to avoid burning credit"
                )
                break
            if err == "RATE_LIMITED":
                errors.append(
                    f"X rate-limited (429) after {self.call_count} calls — "
                    f"remaining queries skipped"
                )
                break
            if err:
                errors.append(err)
                continue

            total_posts += len(posts)
            for post in posts:
                url = post["url"]
                if url in seen_urls or url in visited_this_run:
                    continue
                visited_this_run.add(url)

                text = post["text"]
                found_kws, score = score_lead(text)
                if score < SCORE_THRESHOLD:
                    continue

                leads.append(Lead(
                    url=url,
                    title=text,        # full post text → classifier reads it
                    score=score,
                    keywords=found_kws,
                    source="x",
                    platform="x",
                    snippet=text[:300],
                ))

        notes.append(
            f"X recent search: {len(selected_terms)} of {len(X_SEARCH_TERMS)} "
            f"terms cycled, {self.call_count} calls, {total_posts} posts returned"
        )

        x_cost_tracker.record(self.call_count, self.posts_read)

        return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

    def _search(
        self,
        term: str,
        start_time: str,
        headers: dict[str, str],
    ) -> tuple[list[dict], Optional[str]]:
        """Run one v2 recent search call.

        Returns (posts, error). `posts` is a list of dicts with keys
        url/text. `error` is None on success; "AUTH_FAILED" or
        "RATE_LIMITED" trigger the caller's short-circuit; any other
        string is appended to errors and the caller continues.
        """
        params = {
            "query": f"{term} -is:retweet lang:en",
            "max_results": X_MAX_RESULTS_PER_QUERY,
            "start_time": start_time,
            "tweet.fields": "created_at,public_metrics,author_id",
            "expansions": "author_id",
            "user.fields": "username",
        }

        try:
            self.call_count += 1
            resp = requests.get(
                X_RECENT_SEARCH_URL, headers=headers, params=params, timeout=15
            )
        except Exception as e:
            return [], f"X search '{term}' failed: {e}"

        if resp.status_code in (401, 403):
            return [], "AUTH_FAILED"
        if resp.status_code == 429:
            return [], "RATE_LIMITED"
        if resp.status_code != 200:
            return [], f"X search '{term}' failed: {resp.status_code}"

        try:
            body = resp.json()
        except Exception as e:
            return [], f"X search '{term}' parse failed: {e}"

        data = body.get("data") or []
        users = {u["id"]: u for u in body.get("includes", {}).get("users", [])}
        self.posts_read += len(data)

        posts: list[dict] = []
        for tweet in data:
            tweet_id = tweet.get("id")
            text = tweet.get("text", "")
            author_id = tweet.get("author_id")
            user = users.get(author_id, {})
            username = user.get("username")
            if not tweet_id or not username or not text:
                continue
            url = f"https://x.com/{username}/status/{tweet_id}"
            posts.append({"url": url, "text": text})
        return posts, None
