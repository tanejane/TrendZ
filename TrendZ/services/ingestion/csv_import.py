"""Import the normalized CSV contract, including original source provenance."""

import csv
import json
from pathlib import Path

from .base import Observation


def normalize_row(row):
    required = ("topic_id", "source", "source_identifier", "market",
                "observation_date", "retrieved_at", "metric", "value", "series_id")
    missing = [key for key in required if not row.get(key)]
    if missing:
        raise ValueError("Missing CSV fields: " + ", ".join(missing))
    flag = row.get("is_demo", "false").lower()
    if flag not in ("true", "false", "1", "0"):
        raise ValueError("is_demo must be true/false or 1/0")
    return Observation(
        topic_id=row["topic_id"], source=row["source"],
        source_identifier=row["source_identifier"], source_url=row.get("source_url", ""),
        market=row["market"], observation_date=row["observation_date"],
        retrieved_at=row["retrieved_at"], metric=row["metric"],
        value=float(row["value"]), series_id=row["series_id"],
        metadata=json.loads(row.get("metadata") or "{}"), is_demo=flag in ("true", "1"),
        query_id=row.get("query_id") or "canonical", query=row.get("query") or "",
    )


class CSVImport:
    def __init__(self, path):
        # Validate the complete file before any row is saved.
        with Path(path).open(encoding="utf-8-sig", newline="") as handle:
            self.rows = [normalize_row(row) for row in csv.DictReader(handle)]
        keys = [(r.topic_id, r.source, r.source_identifier, r.market,
                 r.observation_date, r.metric, r.series_id) for r in self.rows]
        if len(keys) != len(set(keys)):
            raise ValueError("CSV contains duplicate observation keys")

    def collect(self, topic, previous):
        return [row for row in self.rows if row.topic_id == topic["id"]]
