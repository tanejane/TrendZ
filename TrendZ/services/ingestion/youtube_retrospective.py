"""Retrospective publication discovery, separately dated current statistics.

Counts describe currently discoverable published videos, never all uploads.
Each successful uncapped window includes daily zero counts for discovered
matches only. Capped/failed windows are explicitly incomplete, not backfilled.
"""

from collections import Counter
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode

from .base import Observation
from .youtube import YouTube, normalize_videos


class RequestBudgetExceeded(RuntimeError):
    pass


class SearchBudget:
    def __init__(self, limit):
        self.limit, self.used = limit, 0

    def spend(self):
        if self.used >= self.limit:
            raise RequestBudgetExceeded("Search request budget reached; resume collection later")
        self.used += 1


class YouTubeRetrospective(YouTube):
    def __init__(self, start_date, end_date, budget, max_pages=1, **kwargs):
        super().__init__(**kwargs)
        self.start = date.fromisoformat(start_date)
        self.end = date.fromisoformat(end_date)
        if (self.end - self.start).days != 55:
            raise ValueError("Pilot requires exactly 56 inclusive retrospective days")
        if max_pages < 1:
            raise ValueError("max_pages must be positive")
        self.budget, self.max_pages = budget, max_pages

    def discover(self, topic):
        stamp = self.clock()
        window_reports, videos, observations = [], {}, []
        query_id = topic.get("query_id", "canonical")
        request_base = {"part": "snippet", "type": "video", "q": topic["query"],
                        "regionCode": topic["market"], "order": "date", "maxResults": 50}
        request_version = "youtube-discovery:" + topic["id"] + ":" + query_id + ":" + stamp
        for week in range(8):
            start = self.start + timedelta(days=7 * week)
            stop = start + timedelta(days=7)
            params = {**request_base, "publishedAfter": start.isoformat() + "T00:00:00Z",
                      "publishedBefore": stop.isoformat() + "T00:00:00Z"}
            weekly = {}
            token, error, pages, payloads = None, None, 0, []
            try:
                for page in range(self.max_pages):
                    self.budget.spend()
                    payload = self.transport("search", {"key": self.key, **params,
                                             **({"pageToken": token} if token else {})})
                    payloads.append(payload)
                    pages += 1
                    for item in payload.get("items", []):
                        snippet = item.get("snippet", {})
                        video_id = item.get("id", {}).get("videoId")
                        published = snippet.get("publishedAt")
                        if not video_id or not published:
                            continue
                        publication = datetime.fromisoformat(published.replace("Z", "+00:00")).astimezone(timezone.utc).date()
                        if start <= publication < stop:
                            weekly[video_id] = {"id": video_id, **snippet,
                                                "publication_date": publication.isoformat()}
                    token = payload.get("nextPageToken")
                    if not token:
                        break
            except Exception as failure:
                error = str(failure)
            complete = error is None and token is None and pages > 0
            report = {"week": week + 1, "start": start.isoformat(), "end_exclusive": stop.isoformat(),
                      "pages": pages, "complete": complete, "capped": bool(token),
                      "error": error, "discovered_video_count": len(weekly),
                      "request": params, "responses": payloads}
            window_reports.append(report)
            videos.update(weekly)
            if pages:
                counts = Counter(video["publication_date"] for video in weekly.values())
                # Partial/capped daily counts are retained as lower bounds but
                # downstream comparable-series validation blocks their metrics.
                for day in range(7):
                    observed = (start + timedelta(days=day)).isoformat()
                    observations.append(Observation(
                        topic["id"], "youtube", query_id + ":publication-discovery",
                        topic["market"], observed, stamp, "discovered_publications",
                        counts[observed], request_version,
                        "https://www.youtube.com/results?" + urlencode({"search_query": topic["query"]}),
                        {"signal": "content_supply", "request": params,
                         "window_complete": complete, "capped": bool(token),
                         "scope": "currently discoverable public publication sample, not upload census"},
                        query_id=query_id, query=topic["query"],
                    ))
        ranked = sorted(videos.values(), key=lambda row: (row["publishedAt"], row["id"]), reverse=True)
        stats, statistics_error = [], None
        try:
            ids = [row["id"] for row in ranked]
            for offset in range(0, len(ids), 50):
                payload = self.transport("videos", {"key": self.key, "part": "snippet,statistics",
                                                   "id": ",".join(ids[offset:offset + 50])})
                stats.extend(payload.get("items", []))
        except Exception as failure:
            statistics_error = str(failure)
        cohort = [row["id"] for row in ranked[:50]]
        cohort_payload = {"items": [item for item in stats if item["id"] in cohort]}
        snapshots = normalize_videos(topic, cohort_payload, stamp, cohort) if not statistics_error else []
        return {
            "topic_id": topic["id"], "query_id": query_id, "query": topic["query"], "market": topic["market"],
            "retrieved_at": stamp, "windows": window_reports, "videos": ranked,
            "present_day_statistics": stats, "statistics_error": statistics_error, "cohort_ids": cohort,
            "observations": [row.to_dict() for row in [*observations, *snapshots]],
            "data_mode": "real", "signal": "content_supply_and_activity",
        }
