import requests
from norman.scouts.base import BaseScout
from norman.models import Lead, ScoutResult
from norman.scoring_v2 import score_lead
from norman.query_selector import pick_queries
from norman.config import YOUTUBE_API_KEY, YOUTUBE_QUERIES, SCORE_THRESHOLD

YOUTUBE_QUERIES_PER_SEGMENT = 5


class YouTubeScout(BaseScout):
    name = "YouTube"
    source = "youtube"

    def run(self, seen_urls: set[str]) -> ScoutResult:
        leads: list[Lead] = []
        errors: list[str] = []
        notes: list[str] = []

        if not YOUTUBE_API_KEY:
            errors.append("YouTube scout skipped — no YOUTUBE_API_KEY configured")
            return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

        visited_this_run: set[str] = set()
        total_pool = sum(len(q) for q in YOUTUBE_QUERIES.values())
        selected_count = 0

        for segment, queries in YOUTUBE_QUERIES.items():
            selected = pick_queries(queries, YOUTUBE_QUERIES_PER_SEGMENT)
            selected_count += len(selected)
            for term in selected:
                videos = self._search_videos(term, errors)
                if videos is None:
                    # quota exceeded — stop immediately
                    notes.append(
                        f"YouTube: selected {selected_count} of {total_pool} queries today "
                        f"(n={YOUTUBE_QUERIES_PER_SEGMENT}/segment, stopped early on quota)"
                    )
                    return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

                for video_id, title, description in videos:
                    url = f"https://www.youtube.com/watch?v={video_id}"
                    if url in seen_urls or url in visited_this_run:
                        continue
                    visited_this_run.add(url)

                    comment_text = self._fetch_comments(video_id, errors)
                    full_text = f"{title} {description} {comment_text}"
                    found_kws, score = score_lead(full_text)

                    if score >= SCORE_THRESHOLD:
                        leads.append(Lead(
                            url=url,
                            title=title,
                            score=score,
                            keywords=found_kws,
                            source="youtube",
                            platform="youtube",
                            snippet=full_text[:300],
                        ))

        notes.append(
            f"YouTube: selected {selected_count} of {total_pool} queries today "
            f"(n={YOUTUBE_QUERIES_PER_SEGMENT}/segment)"
        )
        return ScoutResult(source=self.source, leads=leads, errors=errors, notes=notes)

    def _search_videos(
        self, term: str, errors: list[str]
    ) -> list[tuple[str, str, str]] | None:
        """Returns list of (videoId, title, description) or None if quota exceeded."""
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/search",
                params={
                    "q": term,
                    "key": YOUTUBE_API_KEY,
                    "part": "snippet",
                    "type": "video",
                    "maxResults": 5,
                    "order": "relevance",
                },
                timeout=10,
            )
            if resp.status_code == 403:
                errors.append(f"quotaExceeded — stopped at '{term}'")
                return None
            if resp.status_code != 200:
                errors.append(f"YouTube search failed for '{term}': {resp.status_code}")
                return []

            videos = []
            for item in resp.json().get("items", []):
                videos.append((
                    item["id"]["videoId"],
                    item["snippet"]["title"],
                    item["snippet"]["description"],
                ))
            return videos
        except Exception as e:
            errors.append(f"YouTube search failed for '{term}': {e}")
            return []

    def _fetch_comments(self, video_id: str, errors: list[str]) -> str:
        try:
            resp = requests.get(
                "https://www.googleapis.com/youtube/v3/commentThreads",
                params={
                    "videoId": video_id,
                    "key": YOUTUBE_API_KEY,
                    "part": "snippet",
                    "maxResults": 50,
                    "order": "relevance",
                },
                timeout=10,
            )
            if resp.status_code == 403:
                errors.append(
                    f"Comments disabled for video {video_id} — scored title/description only"
                )
                return ""
            if resp.status_code != 200:
                return ""

            comments = []
            for item in resp.json().get("items", []):
                text = item["snippet"]["topLevelComment"]["snippet"]["textDisplay"]
                comments.append(text)
            return " ".join(comments)
        except Exception as e:
            errors.append(f"Comment fetch failed for {video_id}: {e}")
            return ""
