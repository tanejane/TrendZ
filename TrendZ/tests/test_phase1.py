import json
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path

import app_backend
from services.database import Database
from services.ingestion.base import Observation
from services.ingestion.csv_import import CSVImport, normalize_row
from services.ingestion.google_trends import GoogleTrends, normalize_interest
from services.ingestion.youtube import YouTube, normalize_videos
from services.metrics import calculate_topic
from services.trend_service import TrendService

ROOT = Path(__file__).resolve().parents[1]
STAMP = "2026-01-22T00:00:00+00:00"
TOPIC = {"id": "glass-skin", "name": "Glass Skin", "query": "glass skin",
         "category": "skincare", "market": "MY"}


def history(source="google_trends", metric="interest_score", values=None, series="one"):
    values = values if values is not None else [10] * 7 + [20] * 7 + [30] * 7
    return [Observation("glass-skin", source, "fixture-origin", "MY",
                        (date(2026, 1, 1) + timedelta(days=i)).isoformat(),
                        STAMP, metric, value, series).to_dict() for i, value in enumerate(values)]


class NormalizationTests(unittest.TestCase):
    def test_csv_provenance(self):
        row = history()[0]
        row["is_demo"] = "false"
        row["metadata"] = "{}"
        normalized = normalize_row(row)
        self.assertEqual(normalized.source_identifier, "fixture-origin")
        self.assertEqual(normalized.market, "MY")
        self.assertEqual(normalized.retrieved_at, STAMP)

    def test_invalid_value_and_timezone(self):
        row = history()[0]
        for changes in ({"value": float("nan")}, {"value": -1}, {"retrieved_at": "2026-01-01T00:00:00"}):
            with self.assertRaises(ValueError):
                Observation(**{**row, **changes})

    def test_google_partial_and_related(self):
        rows = normalize_interest(TOPIC, [
            {"date": "2026-01-01", "value": 10},
            {"date": "2026-01-02", "value": 20, "is_partial": True},
        ], STAMP, "request-1", {"rising": [{"query": "glass skin serum", "value": 150}]})
        self.assertEqual(len(rows), 1)
        self.assertIn("rising", rows[0].metadata["related_queries"])

    def test_youtube_fixture(self):
        payload = json.loads((ROOT / "tests/fixtures/youtube.json").read_text())
        rows = normalize_videos(TOPIC, payload, STAMP, ["video-one"])
        self.assertEqual([row.value for row in rows], [120, 12])
        self.assertEqual(rows[0].metadata["videos"][0]["channel_id"], "channel-one")

    def test_youtube_missing_likes_not_zero(self):
        payload = json.loads((ROOT / "tests/fixtures/youtube.json").read_text())
        del payload["items"][0]["statistics"]["likeCount"]
        rows = normalize_videos(TOPIC, payload, STAMP, ["video-one"])
        self.assertEqual([row.metric for row in rows], ["sampled_views"])
        self.assertEqual(normalize_videos(TOPIC, payload, STAMP, ["video-one", "deleted"]), [])

    def test_youtube_fixed_cohort_and_mock_transport(self):
        calls = []
        payload = json.loads((ROOT / "tests/fixtures/youtube.json").read_text())
        def transport(resource, params):
            calls.append(resource)
            return payload
        adapter = YouTube(key="test-key", transport=transport, clock=lambda: STAMP)
        previous = [{"source": "youtube", "metadata": {"cohort_ids": ["video-one"]}}]
        self.assertEqual(len(adapter.collect(TOPIC, previous)), 2)
        self.assertEqual(calls, ["videos"])

    def test_csv_missing_field_and_google_invalid_score(self):
        with self.assertRaises(ValueError):
            normalize_row({"topic_id": "glass-skin"})
        with self.assertRaises(ValueError):
            normalize_interest(TOPIC, [{"date": "2026-01-01", "value": 101}], STAMP, "invalid")

    def test_optional_google_with_injected_client(self):
        from datetime import datetime, timezone
        class Frame:
            empty = False
            def iterrows(self):
                return iter([(datetime(2026, 1, 1), {"glass skin": 25, "isPartial": False})])
        class Client:
            def build_payload(self, terms, **kwargs):
                self.terms = terms
            def interest_over_time(self):
                return Frame()
            def related_queries(self):
                raise RuntimeError("fixture unavailable")
        adapter = GoogleTrends(client=Client(), clock=lambda: datetime(2026, 1, 22, tzinfo=timezone.utc))
        rows = adapter.collect(TOPIC, [])
        self.assertEqual(rows[0].value, 25)
        self.assertIn("unavailable_reason", rows[0].metadata["related_queries"])


class MetricTests(unittest.TestCase):
    def test_formulas(self):
        metrics = calculate_topic(history())
        series = metrics["series"][0]
        self.assertEqual(series["recent_growth"]["value"], 50)
        self.assertEqual(series["acceleration"]["value"], -50)
        self.assertEqual(series["persistence"]["value"], 1)
        self.assertEqual(series["volatility"]["value"], 0)
        self.assertIsNone(metrics["trend_score"])
        self.assertIsNone(metrics["lifecycle"])

    def test_insufficient_and_gap(self):
        for rows in (history(values=[10] * 6), history()[:10] + history()[11:]):
            metrics = calculate_topic(rows)["series"][0]
            self.assertEqual(metrics["recent_growth"]["state"], "unavailable")
            self.assertIsNone(metrics["recent_growth"]["value"])

    def test_zero_baseline(self):
        series = calculate_topic(history(values=[0] * 14 + [10] * 7))["series"][0]
        self.assertEqual(series["recent_growth"]["reason"], "Previous window mean is zero")
        self.assertEqual(series["acceleration"]["state"], "unavailable")

    def test_nonconstant_volatility(self):
        series = calculate_topic(history(values=[1, 2, 3, 4, 5, 6, 7]))["series"][0]
        self.assertEqual(series["volatility"]["value"], 0.5)

    def test_cross_source_confirmation_and_alignment(self):
        rows = history() + history(source="youtube", metric="sampled_views")
        self.assertEqual(calculate_topic(rows)["cross_source_confirmation"]["value"], 1)
        rows[-1]["observation_date"] = "2026-01-22"
        self.assertEqual(calculate_topic(rows)["cross_source_confirmation"]["state"], "unavailable")

    def test_demo_excluded_and_rescaling_separate(self):
        rows = history()
        for row in rows:
            row["is_demo"] = True
        self.assertEqual(calculate_topic(rows)["series"], [])
        old = history(values=[10] * 10, series="old")
        new = history(values=[20] * 6, series="new")
        for row in new:
            row["retrieved_at"] = "2026-01-23T00:00:00+00:00"
        metrics = calculate_topic(old + new)["series"][0]
        self.assertEqual(metrics["history_days"], 6)
        self.assertEqual(metrics["recent_growth"]["state"], "unavailable")


class APIAndStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "test.sqlite3"
        app_backend.app.config.update(TESTING=True, DATA_MODE="real", DATABASE_PATH=str(self.path))
        app_backend.app.extensions.pop("trend_service", None)
        self.client = app_backend.app.test_client()
        # Tests use only their temporary database, independent of local saved topics.
        db = app_backend.trend_service().db
        for saved in db.watchlist():
            db.remove_watch(saved["topic_id"])

    def tearDown(self):
        app_backend.app.extensions.pop("trend_service", None)
        app_backend.app.config.update(DATA_MODE="demo")
        self.temp.cleanup()

    def test_empty_real_never_demo(self):
        payload = self.client.get("/api/trends").json
        self.assertEqual(payload["data_mode"], "unavailable")
        self.assertEqual(len(payload["trends"]), 18)
        for row in payload["trends"]:
            self.assertIsNone(row["trend_score"])
            self.assertIsNone(row["lifecycle"])
            self.assertIsNone(row["roi_score"])
        self.assertIsNone(self.client.get("/api/summary").json["total_reach"])

    def test_ingest_idempotence_and_api(self):
        service = app_backend.trend_service()
        observations = [Observation(**row) for row in history()]
        service.db.ingest(observations)
        service.db.ingest(observations)
        self.assertEqual(len(service.db.observations("glass-skin")), 21)
        payload = self.client.get("/api/trends/glass-skin").json
        self.assertEqual(payload["data_mode"], "real")
        self.assertEqual(payload["trend"]["metrics"]["series"][0]["recent_growth"]["value"], 50)
        self.assertEqual(self.client.get("/api/trends/glass-skin/observations").json["observations"][0]["source"], "google_trends")
        self.assertEqual(self.client.get("/trend-detail/glass-skin").status_code, 200)
        self.assertEqual(self.client.get("/api/chart-data").json["data_mode"], "real")

    def test_watchlist_persists_and_validates(self):
        self.assertEqual(self.client.post("/api/watchlist/add", json=[]).status_code, 400)
        self.assertEqual(self.client.post("/api/watchlist/add", json={"trend_id": "bad"}).status_code, 404)
        self.assertEqual(self.client.post("/api/watchlist/add", json={"trend_id": "glass-skin"}).status_code, 200)
        self.assertEqual(self.client.post("/api/watchlist/add", json={"trend_id": "glass-skin"}).status_code, 409)
        app_backend.app.extensions.pop("trend_service", None)
        self.assertEqual(self.client.get("/api/watchlist").json["total_count"], 1)
        self.assertEqual(self.client.post("/api/watchlist/remove", json={"trend_id": "glass-skin"}).status_code, 200)

    def test_modes_and_scenarios(self):
        scenario = self.client.get("/api/trends?scope=scenario").json
        self.assertEqual(scenario["data_mode"], "demo")
        self.assertEqual(scenario["output_kind"], "assumption_based")
        self.assertEqual(self.client.get("/api/advanced-forecasting").json["data_mode"], "unavailable")
        app_backend.app.config["DATA_MODE"] = "demo"
        self.assertEqual(self.client.get("/api/trends").json["data_mode"], "demo")

    def test_all_existing_pages_render_in_both_modes(self):
        for mode in ("real", "demo"):
            app_backend.app.config["DATA_MODE"] = mode
            for path in ("/", "/roi-insights", "/watchlist", "/hashtag-products",
                         "/influencer-collaboration", "/trend-detail/glass-skin"):
                with self.subTest(mode=mode, path=path):
                    self.assertEqual(self.client.get(path).status_code, 200)

    def test_legacy_migration_once(self):
        legacy = Path(self.temp.name) / "watchlist.json"
        legacy.write_text(json.dumps([{"trend_id": "glass-skin", "added_date": STAMP}]))
        db = Database(Path(self.temp.name) / "migration.sqlite3")
        db.sync_topics([TOPIC])
        db.migrate_watchlist(legacy)
        db.remove_watch("glass-skin")
        db.migrate_watchlist(legacy)
        self.assertEqual(db.watchlist(), [])

    def test_fixture_csv_cannot_enter_real_metrics(self):
        service = app_backend.trend_service()
        report = service.ingest(CSVImport(ROOT / "data/examples/observations.csv"), [TOPIC])
        self.assertEqual(report[0]["state"], "collected")
        self.assertEqual(service.db.observations("glass-skin"), [])

    def test_csv_ingestion_end_to_end_and_duplicate_validation(self):
        import csv
        path = Path(self.temp.name) / "measured.csv"
        rows = history()
        with path.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            for row in rows:
                writer.writerow({**row, "is_demo": "false", "metadata": "{}"})
        report = app_backend.trend_service().ingest(CSVImport(path), [TOPIC])
        self.assertEqual(report[0]["observations"], 21)
        self.assertEqual(self.client.get("/api/trends/glass-skin").json["trend"]["metrics"]["series"][0]["recent_growth"]["value"], 50)
        with path.open("a", newline="") as handle:
            csv.DictWriter(handle, fieldnames=list(rows[0])).writerow({**rows[0], "is_demo": "false", "metadata": "{}"})
        with self.assertRaises(ValueError):
            CSVImport(path)

    def test_atomic_market_validation_and_failed_collection(self):
        service = app_backend.trend_service()
        valid = Observation(**history()[0])
        wrong = Observation(**{**history()[1], "market": "US"})
        with self.assertRaises(ValueError):
            service.db.ingest([valid, wrong])
        self.assertEqual(service.db.observations("glass-skin"), [])
        class Failure:
            def collect(self, topic, previous):
                raise RuntimeError("fixture failure")
        report = service.ingest(Failure(), [TOPIC])
        self.assertEqual(report[0]["state"], "error")
        self.assertEqual(self.client.get("/api/trends/glass-skin").json["data_mode"], "unavailable")

    def test_older_import_does_not_overwrite(self):
        db = app_backend.trend_service().db
        row = history()[0]
        db.ingest([Observation(**row)])
        db.ingest([Observation(**{**row, "value": 999, "retrieved_at": "2026-01-21T00:00:00Z"})])
        self.assertEqual(db.observations("glass-skin")[0]["value"], 10)

    def test_demo_cannot_overwrite_measured_observation(self):
        db = app_backend.trend_service().db
        row = history()[0]
        db.ingest([Observation(**row)])
        with self.assertRaises(ValueError):
            db.ingest([Observation(**{**row, "is_demo": True, "value": 999})])
        self.assertEqual(db.observations("glass-skin")[0]["value"], 10)


if __name__ == "__main__":
    unittest.main()
