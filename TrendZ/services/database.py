"""SQLite persistence with atomic writes and explicit observation provenance."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from .topics import query_variants

SCHEMA = """
CREATE TABLE IF NOT EXISTS topics (
 id TEXT PRIMARY KEY, name TEXT NOT NULL, query TEXT NOT NULL,
 category TEXT NOT NULL, market TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS source_observations (
 id INTEGER PRIMARY KEY, topic_id TEXT NOT NULL REFERENCES topics(id),
 source TEXT NOT NULL, source_identifier TEXT NOT NULL, source_url TEXT NOT NULL,
 market TEXT NOT NULL, observation_date TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 metric TEXT NOT NULL, value REAL NOT NULL CHECK(value >= 0),
 series_id TEXT NOT NULL, metadata TEXT NOT NULL, is_demo INTEGER NOT NULL DEFAULT 0,
 UNIQUE(topic_id,source,source_identifier,market,observation_date,metric,series_id));
CREATE INDEX IF NOT EXISTS observation_topic ON source_observations(topic_id, observation_date);
CREATE TABLE IF NOT EXISTS trend_metrics (
 topic_id TEXT PRIMARY KEY REFERENCES topics(id), calculated_at TEXT NOT NULL,
 formula_version TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS watchlist (
 topic_id TEXT PRIMARY KEY REFERENCES topics(id), added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS migrations (name TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS topic_queries (
 topic_id TEXT NOT NULL REFERENCES topics(id), query_id TEXT NOT NULL,
 query TEXT NOT NULL, PRIMARY KEY(topic_id,query_id));
"""


class Database:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript(SCHEMA)
            columns = {row["name"] for row in db.execute("PRAGMA table_info(source_observations)")}
            if "query_id" not in columns:
                db.execute("ALTER TABLE source_observations ADD COLUMN query_id TEXT NOT NULL DEFAULT 'canonical'")
                db.execute("ALTER TABLE source_observations ADD COLUMN query TEXT NOT NULL DEFAULT ''")
                db.execute("DELETE FROM trend_metrics")

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        try:
            with db:
                yield db
        finally:
            db.close()

    def sync_topics(self, topics):
        with self.connect() as db:
            db.executemany(
                "INSERT INTO topics VALUES (:id,:name,:query,:category,:market) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name, query=excluded.query, "
                "category=excluded.category, market=excluded.market", topics)
            for topic in topics:
                for variant in query_variants(topic):
                    db.execute("INSERT INTO topic_queries VALUES (?,?,?) ON CONFLICT(topic_id,query_id) "
                               "DO UPDATE SET query=excluded.query",
                               (topic["id"], variant["query_id"], variant["query"]))

    def topics(self):
        with self.connect() as db:
            topics = [dict(row) for row in db.execute("SELECT * FROM topics ORDER BY name")]
            for topic in topics:
                topic["aliases"] = [dict(row) for row in db.execute(
                    "SELECT query_id AS id,query FROM topic_queries WHERE topic_id=? AND query_id!='canonical' ORDER BY query_id",
                    (topic["id"],))]
            return topics

    def observations(self, topic_id, include_demo=False):
        with self.connect() as db:
            rows = [dict(row) for row in db.execute(
                "SELECT * FROM source_observations WHERE topic_id=? "
                + ("" if include_demo else "AND is_demo=0 ") +
                "ORDER BY observation_date,retrieved_at", (topic_id,))]
        for row in rows:
            row["metadata"] = json.loads(row["metadata"])
        return rows

    def ingest(self, observations):
        with self.connect() as db:
            for observation in observations:
                row = observation.to_dict()
                known = db.execute("SELECT market FROM topics WHERE id=?", (row["topic_id"],)).fetchone()
                if not known or known["market"] != row["market"]:
                    raise ValueError("Observation topic/market does not match configuration")
                configured = db.execute("SELECT query FROM topic_queries WHERE topic_id=? AND query_id=?",
                                        (row["topic_id"], row["query_id"])).fetchone()
                if not configured or (row["query"] and row["query"] != configured["query"]):
                    raise ValueError("Observation query provenance does not match configuration")
                row["metadata"] = json.dumps(row["metadata"], allow_nan=False)
                existing = db.execute(
                    "SELECT is_demo,query_id FROM source_observations WHERE topic_id=? AND source=? "
                    "AND source_identifier=? AND market=? AND observation_date=? AND metric=? AND series_id=?",
                    tuple(row[key] for key in ("topic_id", "source", "source_identifier", "market",
                                               "observation_date", "metric", "series_id")),
                ).fetchone()
                if existing and bool(existing["is_demo"]) != row["is_demo"]:
                    raise ValueError("Cannot relabel an existing observation between demo and measured")
                if existing and existing["query_id"] != row["query_id"]:
                    raise ValueError("Alias observations require distinct source identifiers")
                db.execute(
                    "INSERT INTO source_observations "
                    "(topic_id,source,source_identifier,source_url,market,observation_date,"
                    "retrieved_at,metric,value,series_id,metadata,is_demo,query_id,query) VALUES "
                    "(:topic_id,:source,:source_identifier,:source_url,:market,:observation_date,"
                    ":retrieved_at,:metric,:value,:series_id,:metadata,:is_demo,:query_id,:query) "
                    "ON CONFLICT DO UPDATE SET value=excluded.value,metadata=excluded.metadata,"
                    "retrieved_at=excluded.retrieved_at,query_id=excluded.query_id,query=excluded.query "
                    "WHERE excluded.retrieved_at >= source_observations.retrieved_at", row)
                db.execute("DELETE FROM trend_metrics WHERE topic_id=?", (row["topic_id"],))

    def store_metrics(self, topic_id, calculated_at, payload):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO trend_metrics VALUES (?,?,?,?)",
                       (topic_id, calculated_at, "daily-windows-v1", json.dumps(payload)))

    def metrics(self, topic_id):
        with self.connect() as db:
            row = db.execute("SELECT * FROM trend_metrics WHERE topic_id=?", (topic_id,)).fetchone()
            return json.loads(row["payload"]) if row else None

    def watchlist(self):
        with self.connect() as db:
            return [dict(row) for row in db.execute("SELECT * FROM watchlist ORDER BY added_at")]

    def add_watch(self, topic_id, added_at):
        with self.connect() as db:
            db.execute("INSERT INTO watchlist VALUES (?,?)", (topic_id, added_at))

    def remove_watch(self, topic_id):
        with self.connect() as db:
            return db.execute("DELETE FROM watchlist WHERE topic_id=?", (topic_id,)).rowcount

    def migrate_watchlist(self, path):
        path = Path(path)
        with self.connect() as db:
            if db.execute("SELECT 1 FROM migrations WHERE name='json_watchlist'").fetchone():
                return
            items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if not isinstance(items, list):
                raise ValueError("Legacy watchlist must be a JSON array")
            for item in items:
                topic_id = item.get("trend_id") or item.get("id")
                if db.execute("SELECT 1 FROM topics WHERE id=?", (topic_id,)).fetchone():
                    db.execute("INSERT OR IGNORE INTO watchlist VALUES (?,?)",
                               (topic_id, item.get("added_date") or "1970-01-01T00:00:00+00:00"))
            db.execute("INSERT INTO migrations VALUES ('json_watchlist')")
