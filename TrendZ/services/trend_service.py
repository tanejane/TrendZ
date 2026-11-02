"""Boundary between measured observations and the legacy demo/scenario data."""

import json
from datetime import datetime, timezone
from pathlib import Path

from .database import Database
from .metrics import calculate_topic


class TrendService:
    def __init__(self, root, db_path, mode):
        if mode not in ("demo", "real"):
            raise ValueError("TRENDZ_DATA_MODE must be demo or real")
        self.mode = mode
        self.root = Path(root)
        self.demo = json.loads((self.root / "data/demo_trends.json").read_text(encoding="utf-8"))
        self.db = Database(db_path)
        topics = json.loads((self.root / "data/tracked_topics.json").read_text(encoding="utf-8"))
        self.db.sync_topics(topics)
        self.db.migrate_watchlist(self.root / "data/watchlist.json")

    def recalculate(self, topic_id):
        observations = self.db.observations(topic_id)
        payload = calculate_topic(observations)
        stamp = datetime.now(timezone.utc).isoformat()
        payload["calculated_at"] = stamp
        self.db.store_metrics(topic_id, stamp, payload)
        return payload

    def ingest(self, adapter, topics=None):
        configured = self.db.topics()
        selected = topics or configured
        if hasattr(adapter, "rows"):
            known = {topic["id"] for topic in configured}
            if any(row.topic_id not in known for row in adapter.rows):
                raise ValueError("CSV contains an unconfigured topic")
        report = []
        for topic in selected:
            try:
                rows = adapter.collect(topic, self.db.observations(topic["id"]))
                self.db.ingest(rows)
                self.recalculate(topic["id"])
                report.append({"topic_id": topic["id"], "state": "collected" if rows else "unavailable",
                               "data_mode": "demo" if rows and all(row.is_demo for row in rows) else "real" if rows else "unavailable",
                               "observations": len(rows), "reason": None if rows else "Source returned no usable observations"})
            except Exception as error:
                report.append({"topic_id": topic["id"], "state": "error", "reason": str(error)})
        return report

    def trends(self):
        if self.mode == "demo":
            return [{**row, "data_mode": "demo", "metrics": None,
                     "intelligence_kind": "demo", "scenario_kind": "assumption_based"} for row in self.demo]
        result = []
        for topic in self.db.topics():
            observations = self.db.observations(topic["id"])
            metrics = self.db.metrics(topic["id"]) or self.recalculate(topic["id"])
            sources = sorted({row["source"] for row in observations})
            result.append({
                **topic, "hashtag": topic["query"].replace(" ", ""), "platform": ", ".join(sources) or "Unavailable",
                "audience": "Unavailable", "data_mode": "real" if observations else "unavailable",
                "reason": None if observations else "No measured observations collected",
                "metrics": metrics, "trend_score": None, "lifecycle": None,
                "roi_score": None, "reach": None, "engagement_rate": None,
                "growth": None, "action": "Review component metrics",
                "intelligence_kind": "measured", "scenario_kind": "unavailable",
                "provenance": [{key: row[key] for key in (
                    "source", "source_identifier", "source_url", "market", "observation_date",
                    "retrieved_at", "metric", "series_id", "query_id", "query")} for row in observations],
            })
        return result

    def watchlist(self):
        trends = {row["id"]: row for row in self.trends()}
        result = []
        for saved in self.db.watchlist():
            trend = trends.get(saved["topic_id"])
            if trend:
                result.append({"trend_id": trend["id"], "trend_name": trend["name"],
                               "added_date": saved["added_at"], "platform": trend["platform"],
                               "lifecycle": trend["lifecycle"] or "Unavailable",
                               "trend_score": trend["trend_score"], "roi_score": trend["roi_score"],
                               "data_mode": trend["data_mode"], "urgency": "LOW",
                               "message": "Saved topic. Automatic alerts are not implemented.",
                               "metrics": trend["metrics"]})
        return result
