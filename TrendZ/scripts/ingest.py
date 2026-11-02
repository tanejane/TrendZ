"""Explicit collection command. HTTP requests never trigger external ingestion."""

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from services.trend_service import TrendService
from services.ingestion.csv_import import CSVImport
from services.ingestion.google_trends import GoogleTrends
from services.ingestion.youtube import YouTube


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", choices=["csv", "google", "youtube"])
    parser.add_argument("--file")
    parser.add_argument("--topic", help="Single configured topic ID; defaults to all")
    parser.add_argument("--start-date", help="Google fixed window YYYY-MM-DD")
    parser.add_argument("--end-date", help="Google fixed window YYYY-MM-DD")
    args = parser.parse_args()
    if args.source == "csv" and not args.file:
        parser.error("--file is required for CSV import")
    service = TrendService(ROOT, os.environ.get("TRENDZ_DB_PATH", ROOT / "data/trendz.sqlite3"), "real")
    topics = [topic for topic in service.db.topics() if topic["id"] == args.topic] if args.topic else None
    if args.topic and not topics:
        parser.error("Unknown topic")
    try:
        adapter = CSVImport(args.file) if args.source == "csv" else GoogleTrends(start_date=args.start_date, end_date=args.end_date) if args.source == "google" else YouTube()
        report = service.ingest(adapter, topics)
    except (ValueError, OSError) as error:
        parser.exit(1, str(error) + "\n")
    print(json.dumps(report, indent=2))
    return 1 if any(row["state"] == "error" for row in report) else 0


if __name__ == "__main__":
    raise SystemExit(main())
