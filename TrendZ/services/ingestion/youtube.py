"""Official YouTube API adapter. Fixed search cohorts prevent sample churn."""

import hashlib
import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen

from .base import Observation


def request_json(resource, params):
    url = "https://www.googleapis.com/youtube/v3/" + resource + "?" + urlencode(params)
    try:
        with urlopen(url, timeout=20) as response:
            return json.load(response)
    except HTTPError as error:
        # Never include the request URL: it contains the API key.
        raise RuntimeError(f"YouTube HTTP {error.code}; check credentials/quota") from None
    except URLError:
        raise RuntimeError("YouTube network request failed") from None


def normalize_videos(topic, payload, retrieved_at, cohort_ids):
    videos = []
    for item in payload.get("items", []):
        snippet, stats = item.get("snippet", {}), item.get("statistics", {})
        videos.append({
            "id": item["id"], "url": "https://www.youtube.com/watch?v=" + item["id"],
            "views": int(stats["viewCount"]) if "viewCount" in stats else None,
            "likes": int(stats["likeCount"]) if "likeCount" in stats else None,
            "published_at": snippet.get("publishedAt"),
            "channel_id": snippet.get("channelId"), "channel_name": snippet.get("channelTitle"),
            "title": snippet.get("title"),
        })
    if not cohort_ids:
        return []
    cohort = hashlib.sha256(",".join(sorted(cohort_ids)).encode()).hexdigest()[:16]
    metadata = {
        "videos": videos, "cohort_ids": sorted(cohort_ids),
        "matching_video_count": len(videos), "scope": "fixed search sample; not total market",
        "region_scope": "videos viewable in region; viewer nationality unknown",
        "signal": "content_activity", "statistic_time": "retrieval_time_not_publication_time",
    }
    # Missing/deleted videos or hidden statistics invalidate aggregates, not zero-fill.
    rows = []
    for metric, field in (("sampled_views", "views"), ("sampled_likes", "likes")):
        if len(videos) == len(cohort_ids) and all(v[field] is not None for v in videos):
            rows.append(Observation(
                topic["id"], "youtube", topic.get("query_id", "canonical") + ":cohort:" + cohort, topic["market"],
                retrieved_at[:10], retrieved_at, metric,
                sum(v[field] for v in videos), "youtube:" + cohort,
                "https://www.youtube.com/results?search_query=" + topic["query"].replace(" ", "+"),
                metadata,
                query_id=topic.get("query_id", "canonical"), query=topic["query"],
            ))
    return rows


class YouTube:
    def __init__(self, key=None, transport=request_json, clock=None):
        self.key = key or os.environ.get("YOUTUBE_API_KEY")
        self.transport = transport
        self.clock = clock or (lambda: datetime.now(timezone.utc).isoformat())
        if not self.key:
            raise ValueError("YOUTUBE_API_KEY is required for YouTube ingestion")

    def collect(self, topic, previous):
        cohorts = [row for row in previous if row["source"] == "youtube"
                   and row.get("query_id", "canonical") == topic.get("query_id", "canonical")
                   and "cohort_ids" in row["metadata"]]
        ids = cohorts[-1]["metadata"]["cohort_ids"] if cohorts else []
        if not ids:
            search = self.transport("search", {
                "key": self.key, "part": "snippet", "type": "video", "q": topic["query"],
                "regionCode": topic["market"], "maxResults": 50, "order": "relevance",
            })
            ids = sorted({item["id"]["videoId"] for item in search.get("items", [])})
        if not ids:
            return []
        payload = self.transport("videos", {
            "key": self.key, "part": "snippet,statistics", "id": ",".join(ids),
        })
        return normalize_videos(topic, payload, self.clock(), ids)
