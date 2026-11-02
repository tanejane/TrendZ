"""Deterministic synthetic captures. Not historical evidence or real metrics."""

from datetime import date, datetime, timedelta, timezone

from .ingestion.google_trends import GoogleTrends
from .ingestion.youtube import normalize_videos
from .ingestion.youtube_retrospective import SearchBudget, YouTubeRetrospective


def fixture_google(topic, config, index):
    start = date.fromisoformat(config["start_date"])
    class Frame:
        empty = False
        def iterrows(self):
            return iter([(datetime.combine(start + timedelta(days=i), datetime.min.time()),
                          {topic["query"]: 12 + index + (i // 7) * (index % 3 + 1) + (i % 3),
                           "isPartial": False}) for i in range(56)])
    class Client:
        def build_payload(self, *args, **kwargs):
            pass
        def interest_over_time(self):
            return Frame()
        def related_queries(self):
            return {}
    stamp = datetime.fromisoformat("2026-10-14T00:00:00+00:00")
    rows = GoogleTrends(Client(), lambda: stamp, config["start_date"], config["end_date"]).collect(topic, [])
    return [{**row.to_dict(), "is_demo": True} for row in rows]


def fixture_youtube(topic, config, index):
    videos = {}
    prefix = topic["id"] + "-" + topic["query_id"]
    def transport(resource, params):
        if resource == "search":
            day = date.fromisoformat(params["publishedAfter"][:10])
            week = (day - date.fromisoformat(config["start_date"])).days // 7
            items = []
            for i in range(2 + (index + week) % 3):
                video_id = prefix + f"-w{week}-v{i}"
                snippet = {"publishedAt": (day + timedelta(days=i)).isoformat() + "T12:00:00Z",
                           "title": "SYNTHETIC " + topic["query"] + " example",
                           "description": "Fixture only; requires no relevance interpretation",
                           "channelId": "fixture-channel", "channelTitle": "Fixture channel"}
                videos[video_id] = {"id": video_id, "snippet": snippet,
                                    "statistics": {"viewCount": str(100 + index + i), "likeCount": "10"}}
                items.append({"id": {"videoId": video_id}, "snippet": snippet})
            return {"items": items, **({"nextPageToken": "fixture-capped"} if topic["id"] == "hair-oil" and week == 7 else {})}
        return {"items": [videos[video_id] for video_id in params["id"].split(",")]}
    collector = YouTubeRetrospective(config["start_date"], config["end_date"], SearchBudget(8),
                                    key="fixture-key", transport=transport,
                                    clock=lambda: "2026-10-14T00:00:00+00:00")
    result = collector.discover(topic)
    cohort = result["cohort_ids"]
    # Demonstrate forward snapshots with synthetic dates, never backdated views.
    initial = date(2026, 10, 14)
    observations = [row for row in result["observations"] if row["metric"] == "discovered_publications"]
    for day in range(28):
        payload = {"items": [{**videos[video_id],
                    "statistics": {"viewCount": str(100 + index + day * (index % 4 + 1)),
                                   "likeCount": str(10 + day)}} for video_id in cohort]}
        stamp = (initial + timedelta(days=day)).isoformat() + "T00:00:00+00:00"
        observations.extend(row.to_dict() for row in normalize_videos(topic, payload, stamp, cohort))
    result["observations"] = [{**row, "is_demo": True} for row in observations]
    result["data_mode"] = "demo"
    return result
