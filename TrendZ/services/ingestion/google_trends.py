"""Optional Google Trends adapter using an injected client or optional pytrends.

Each request is a separate normalized series. Never merge independently scaled
requests. Related-query failures do not discard successful interest observations.
"""

from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from urllib.parse import urlencode

from .base import Observation


def normalize_interest(topic, rows, retrieved_at, series_id, related=None, request=None, is_demo=False):
    if any(not 0 <= float(row["value"]) <= 100 for row in rows):
        raise ValueError("Google interest scores must be between 0 and 100")
    return [
        Observation(
            topic["id"], "google_trends", topic["query"], topic["market"],
            row["date"], retrieved_at, "interest_score", float(row["value"]), series_id,
            "https://trends.google.com/trends/explore?" + urlencode({"geo": topic["market"], "q": topic["query"]}),
            {"related_queries": related or {}, "scale": "request-relative 0-100",
             "request": request or {}, "signal": "demand_search",
             "partial_rows_excluded": sum(bool(r.get("is_partial")) for r in rows)},
            is_demo=is_demo, query_id=topic.get("query_id", "canonical"), query=topic["query"],
        )
        for row in rows if not row.get("is_partial", False)
    ]


class GoogleTrends:
    def __init__(self, client=None, clock=None, start_date=None, end_date=None, category=0, property=""):
        if bool(start_date) != bool(end_date):
            raise ValueError("Provide both fixed start_date and end_date")
        if start_date and date.fromisoformat(start_date) > date.fromisoformat(end_date):
            raise ValueError("start_date must precede end_date")
        self.start_date, self.end_date = start_date, end_date
        self.category, self.property = category, property
        if client is None:
            try:
                from pytrends.request import TrendReq
            except ImportError:
                raise ValueError("Optional pytrends is not installed; use CSV import instead") from None
            client = TrendReq(hl="en-US", tz=0, timeout=(10, 20))
        self.client = client
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def collect(self, topic, previous):
        now = self.clock()
        end = date.fromisoformat(self.end_date) if self.end_date else now.date() - timedelta(days=1)
        start = date.fromisoformat(self.start_date) if self.start_date else end - timedelta(days=27)
        timeframe = f"{start.isoformat()} {end.isoformat()}"
        request = {"query": topic["query"], "query_id": topic.get("query_id", "canonical"),
                   "geo": topic["market"], "timeframe": timeframe,
                   "category": self.category, "property": self.property,
                   "timezone": "UTC", "term_type": "search_term"}
        self.client.build_payload([topic["query"]], geo=topic["market"], timeframe=timeframe,
                                  cat=self.category, gprop=self.property)
        frame = self.client.interest_over_time()
        if frame.empty:
            return []
        rows = [{"date": index.date().isoformat(), "value": row[topic["query"]],
                 "is_partial": bool(row.get("isPartial", False))}
                for index, row in frame.iterrows()]
        related = {}
        try:
            result = self.client.related_queries().get(topic["query"], {})
            related = {kind: table.to_dict("records") if table is not None else []
                       for kind, table in result.items()}
        except Exception:
            related = {"unavailable_reason": "Related/rising query request failed"}
        stamp = now.isoformat()
        fingerprint = hashlib.sha256(json.dumps(request, sort_keys=True).encode()).hexdigest()[:16]
        return normalize_interest(topic, rows, stamp,
                                  f"google:{topic['id']}:{fingerprint}:{stamp}", related, request)
