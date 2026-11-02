import json
import tempfile
import unittest
from dataclasses import replace
from datetime import date, datetime, timezone
from pathlib import Path

from services.database import Database
from services.ingestion.base import Observation
from services.ingestion.google_trends import GoogleTrends
from services.ingestion.youtube_retrospective import SearchBudget, YouTubeRetrospective, RequestBudgetExceeded
from services.metrics import calculate_topic
from services.pilot_fixtures import fixture_google, fixture_youtube
from services.pilot_report import build_report, export_csv, validate_series
from services.topics import query_variants
from scripts.pilot_phase2 import audit_rows

ROOT = Path(__file__).resolve().parents[1]
CONFIG = json.loads((ROOT / "data/pilot_phase2.json").read_text())
TOPICS = json.loads((ROOT / "data/tracked_topics.json").read_text())
TOPIC = next(t for t in TOPICS if t["id"] == "niacinamide")


class AliasTests(unittest.TestCase):
    def test_canonical_preserved_and_seventeen_queries(self):
        pilot = [t for t in TOPICS if t["id"] in CONFIG["topic_ids"]]
        self.assertEqual(len(pilot), 8)
        self.assertEqual(sum(len(query_variants(t)) for t in pilot), 17)
        self.assertEqual(query_variants(TOPIC)[0]["query"], "niacinamide serum")
        self.assertEqual(query_variants(TOPIC)[1]["query"], "niacinamide")

    def test_duplicate_alias_rejected(self):
        with self.assertRaises(ValueError):
            query_variants({**TOPIC, "aliases": [{"id": "canonical", "query": "other"}]})

    def test_sqlite_and_metrics_keep_aliases_separate(self):
        with tempfile.TemporaryDirectory() as temp:
            db = Database(Path(temp) / "test.sqlite3")
            db.sync_topics([TOPIC])
            rows = []
            for i, query in enumerate(query_variants(TOPIC)):
                rows.extend(Observation(**{**r, "is_demo": False}) for r in fixture_google(query, CONFIG, i))
            db.ingest(rows)
            metrics = calculate_topic(db.observations(TOPIC["id"]))
            self.assertEqual(len(metrics["series"]), 2)
            self.assertEqual({s["query_id"] for s in metrics["series"]}, {"canonical", "broad"})
            self.assertEqual(metrics["cross_source_confirmation"]["state"], "unavailable")
            self.assertEqual(len(db.topics()[0]["aliases"]), 1)


class DiscoveryTests(unittest.TestCase):
    def topic(self):
        return query_variants(TOPIC)[0]

    def test_eight_week_bounds_and_present_day_stats(self):
        calls = []
        def transport(resource, params):
            calls.append((resource, params))
            if resource == "search":
                return {"items": [{"id": {"videoId": params["publishedAfter"][:10]},
                    "snippet": {"publishedAt": params["publishedAfter"],
                                "title": "Fixture", "channelId": "c", "channelTitle": "C"}}]}
            return {"items": [{"id": i, "snippet": {"publishedAt": "2026-08-19T00:00:00Z"},
                              "statistics": {"viewCount": "200", "likeCount": "10"}}
                             for i in params["id"].split(",")]}
        collector = YouTubeRetrospective(CONFIG["start_date"], CONFIG["end_date"], SearchBudget(8),
                                        key="fixture", transport=transport,
                                        clock=lambda: "2026-10-14T00:00:00+00:00")
        capture = collector.discover(self.topic())
        search = [params for resource, params in calls if resource == "search"]
        self.assertEqual(len(search), 8)
        self.assertEqual(search[0]["publishedAfter"], "2026-08-19T00:00:00Z")
        self.assertEqual(search[-1]["publishedBefore"], "2026-10-14T00:00:00Z")
        self.assertEqual(sum(r["value"] for r in capture["observations"] if r["metric"] == "discovered_publications"), 8)
        snapshots = [r for r in capture["observations"] if r["metric"] == "sampled_views"]
        self.assertEqual(snapshots[0]["observation_date"], "2026-10-14")
        self.assertEqual(len(audit_rows(capture)), 8)

    def test_boundary_filter_and_missing_week_not_zero(self):
        calls = 0
        def transport(resource, params):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise RuntimeError("fixture failure")
            return {"items": [{"id": {"videoId": "outside"}, "snippet": {"publishedAt": "2026-01-01T00:00:00Z"}}]}
        capture = YouTubeRetrospective(CONFIG["start_date"], CONFIG["end_date"], SearchBudget(8),
                                      key="fixture", transport=transport,
                                      clock=lambda: "2026-10-14T00:00:00Z").discover(self.topic())
        publication = [r for r in capture["observations"] if r["metric"] == "discovered_publications"]
        self.assertEqual(len(publication), 49)
        self.assertEqual(capture["videos"], [])
        self.assertEqual(capture["windows"][0]["error"], "fixture failure")

    def test_capped_series_blocks_metrics(self):
        topic = query_variants(next(t for t in TOPICS if t["id"] == "hair-oil"))[0]
        capture = fixture_youtube(topic, CONFIG, 7)
        rows = [r for r in capture["observations"] if r["metric"] == "discovered_publications"]
        dates = [(date(2026, 8, 19) + __import__("datetime").timedelta(days=i)).isoformat() for i in range(56)]
        self.assertEqual(validate_series(rows, "youtube", dates)["state"], "invalid")

    def test_budget_enforced(self):
        budget = SearchBudget(1)
        budget.spend()
        with self.assertRaises(RequestBudgetExceeded):
            budget.spend()


class ReportTests(unittest.TestCase):
    def test_fixed_google_request_parameters(self):
        class Frame:
            empty = True
        class Client:
            def build_payload(self, terms, **kwargs):
                self.terms, self.params = terms, kwargs
            def interest_over_time(self):
                return Frame()
        client = Client()
        adapter = GoogleTrends(client, lambda: datetime(2026, 10, 14, tzinfo=timezone.utc),
                               CONFIG["start_date"], CONFIG["end_date"])
        self.assertEqual(adapter.collect(query_variants(TOPIC)[1], []), [])
        self.assertEqual(client.terms, ["niacinamide"])
        self.assertEqual(client.params["timeframe"], "2026-08-19 2026-10-13")
        self.assertEqual(client.params["geo"], "MY")
        self.assertEqual(client.params["gprop"], "")
        with self.assertRaises(ValueError):
            GoogleTrends(client, start_date="2026-08-19")

    def test_mixed_google_requests_invalid(self):
        query = query_variants(TOPIC)[0]
        rows = fixture_google(query, CONFIG, 0)
        rows[0]["series_id"] = "another-request"
        dates = [r["observation_date"] for r in rows]
        self.assertEqual(validate_series(rows, "google_trends", dates)["state"], "invalid")

    def test_empty_measured_report_has_no_fixture_metrics(self):
        query = query_variants(TOPIC)[0]
        fixture = fixture_google(query, CONFIG, 0)
        with tempfile.TemporaryDirectory() as temp:
            report = build_report(CONFIG, [query], fixture, {}, temp)
            self.assertEqual(report["data_mode"], "unavailable")
            self.assertTrue(all(r["observation_count"] == 0 for r in report["rows"]))
            self.assertTrue(all(r["components"]["recent_growth"]["value"] is None for r in report["rows"]))

    def test_fixture_report_and_manual_relevance(self):
        query = query_variants(TOPIC)[0]
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "relevance_audit.csv"
            export_csv(path, [
                {"topic_id": query["id"], "query_id": "canonical", "label": "relevant"},
                {"topic_id": query["id"], "query_id": "canonical", "label": "irrelevant"},
                {"topic_id": query["id"], "query_id": "canonical", "label": "pending"},
            ], ["topic_id", "query_id", "label"])
            report = build_report(CONFIG, [query], fixture_google(query, CONFIG, 0), {}, temp, include_demo=True)
            row = report["rows"][0]
            self.assertEqual(row["data_mode"], "demo")
            self.assertEqual(row["query_relevance"]["state"], "unavailable")
            self.assertEqual(report["rows"][1]["query_relevance"]["relevant_fraction_of_decided"], 0.5)
            self.assertEqual(report["rows"][1]["query_relevance"]["pending"], 1)
            self.assertEqual(row["comparable_series"]["state"], "valid")
            self.assertEqual(row["covered_days"], 56)
            self.assertEqual(row["source_level_direction"], "positive")
            self.assertTrue((Path(temp) / "analysis.csv").exists())


if __name__ == "__main__":
    unittest.main()
