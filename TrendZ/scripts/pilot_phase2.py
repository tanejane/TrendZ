"""Explicit Phase 2 collection/report pilot. Nothing is scheduled implicitly."""

import argparse
import hashlib
import json
import os
import sys
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.database import Database
from services.ingestion.base import Observation
from services.ingestion.csv_import import CSVImport
from services.ingestion.google_trends import GoogleTrends
from services.ingestion.youtube import YouTube, normalize_videos
from services.ingestion.youtube_retrospective import SearchBudget, YouTubeRetrospective
from services.pilot_fixtures import fixture_google, fixture_youtube
from services.pilot_report import build_report, export_csv
from services.topics import query_variants
from services.youtube_store import YouTubeStore, encoded


def audit_rows(capture):
    current = {item["id"]: item for item in capture["present_day_statistics"]}
    return [{"topic_id": capture["topic_id"], "query_id": capture["query_id"], "query": capture["query"],
             "rank": index + 1, "video_id": video["id"], "url": "https://www.youtube.com/watch?v=" + video["id"],
             "title": video["title"], "description": video.get("description", ""),
             "published_at": video["publishedAt"], "channel_id": video.get("channelId"),
             "channel_name": video.get("channelTitle"), "retrieved_at": capture["retrieved_at"],
             "current_views": current.get(video["id"], {}).get("statistics", {}).get("viewCount"),
             "data_mode": capture["data_mode"], "label": "pending", "notes": ""}
            for index, video in enumerate(capture["videos"][:20])]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", choices=["none", "google", "youtube", "csv"], default="none")
    parser.add_argument("--config", default=str(ROOT / "data/pilot_phase2.json"))
    parser.add_argument("--output", help="Defaults to reports/phase2-measured or phase2-fixture")
    parser.add_argument("--db")
    parser.add_argument("--fixture", action="store_true", help="Synthetic Google and YouTube demonstration only")
    parser.add_argument("--file", help="Normalized CSV import")
    parser.add_argument("--topic")
    parser.add_argument("--query-id")
    parser.add_argument("--max-queries", type=int)
    parser.add_argument("--max-search-requests", type=int, default=64)
    parser.add_argument("--max-pages-per-week", type=int, default=1)
    parser.add_argument("--snapshot", action="store_true", help="YouTube fixed cohorts only; no retrospective search")
    parser.add_argument("--request-delay", type=float, default=2.0, help="Delay between Google query requests")
    parser.add_argument("--resume", action="store_true", help="Skip query discovery captures that completed all eight windows")
    args = parser.parse_args()
    config = json.loads(Path(args.config).read_text(encoding="utf-8"))
    if (date.fromisoformat(config["end_date"]) - date.fromisoformat(config["start_date"])).days != 55:
        parser.error("Experiment must contain exactly 56 inclusive days")
    configured = json.loads((ROOT / "data/tracked_topics.json").read_text(encoding="utf-8"))
    topics = [topic for topic in configured if topic["id"] in config["topic_ids"]]
    if len(topics) != 8 or any(topic["market"] != config["market"] for topic in topics):
        parser.error("Pilot requires eight configured topics in the configured market")
    queries = [query for topic in topics for query in query_variants(topic)]
    queries.sort(key=lambda query: (query["query_id"] != "canonical", config["topic_ids"].index(query["id"]), query["query_id"]))
    chosen = [q for q in queries if (not args.topic or q["id"] == args.topic)
              and (not args.query_id or q["query_id"] == args.query_id)]
    if not chosen:
        parser.error("No matching topic/query")
    if args.max_queries is not None:
        chosen = chosen[:args.max_queries]
    output = Path(args.output or ROOT / "reports" / ("phase2-fixture" if args.fixture else "phase2-measured"))
    output.mkdir(parents=True, exist_ok=True)
    mode_file = output / "mode.json"
    mode = "demo" if args.fixture else "measured"
    request_scope = {key: config[key] for key in ("experiment_id", "start_date", "end_date", "market", "google", "topic_ids")}
    fingerprint = hashlib.sha256(json.dumps(request_scope, sort_keys=True).encode()).hexdigest()
    if mode_file.exists():
        stored = json.loads(mode_file.read_text())
        if stored["mode"] != mode:
            parser.error("Fixture and measured outputs must use separate directories")
        if stored.get("experiment_fingerprint", fingerprint) != fingerprint:
            parser.error("Changed experiment parameters require a new output directory")
    mode_file.write_text(json.dumps({"mode": mode, "experiment_fingerprint": fingerprint}), encoding="utf-8")
    db = Database(args.db or output / "pilot.sqlite3")
    db.sync_topics(configured)
    youtube_store = YouTubeStore(db)
    invocation_id = uuid.uuid4().hex
    manifest_file = output / "collection.json"
    manifest = json.loads(manifest_file.read_text(encoding="utf-8")) if manifest_file.exists() else {}
    raw = output / "raw"
    raw.mkdir(exist_ok=True)
    budget = SearchBudget(args.max_search_requests)
    if args.source == "csv":
        if not args.file:
            parser.error("--file required")
        rows = CSVImport(args.file).rows
        if any(row.is_demo != args.fixture for row in rows):
            parser.error("CSV classification must match fixture/measured output mode")
        db.ingest(rows)
        for row in rows:
            manifest[row.topic_id + "/" + row.query_id + "/" + row.source] = {"state": "csv_imported", "reason": None}
    for index, query in enumerate(chosen):
        sources = ["google_trends", "youtube"] if args.fixture and args.source == "none" else (
            ["google_trends"] if args.source == "google" else ["youtube"] if args.source == "youtube" else [])
        for source in sources:
            key = query["id"] + "/" + query["query_id"] + "/" + source
            capture_path = raw / (query["id"] + "--" + query["query_id"] + "--" + source + ".json")
            try:
                if source == "google_trends":
                    if args.resume and capture_path.exists() and manifest.get(key, {}).get("state") == "collected":
                        continue
                    if not args.fixture:
                        time.sleep(max(0, args.request_delay))
                    rows = fixture_google(query, config, index) if args.fixture else [
                        row.to_dict() for row in GoogleTrends(
                            start_date=config["start_date"], end_date=config["end_date"],
                            category=config["google"]["category"], property=config["google"]["property"]
                        ).collect(query, db.observations(query["id"]))]
                    capture_path.write_text(json.dumps({"observations": rows}, indent=2), encoding="utf-8")
                else:
                    _, stored_capture = youtube_store.latest_capture(query['id'], query['query_id'])
                    if stored_capture is None and capture_path.exists():
                        stored_capture = json.loads(capture_path.read_text(encoding='utf-8'))
                        stored_capture['archive_origin'] = 'surviving legacy capture; earlier overwritten payloads are unavailable'
                        legacy_id = 'legacy-' + hashlib.sha256(encoded(stored_capture).encode()).hexdigest()[:24]
                        youtube_store.save_run(stored_capture, 'legacy', legacy_id)
                        youtube_store.export_run(legacy_id, output / 'youtube_runs')
                    if args.snapshot:
                        if stored_capture is None:
                            raise ValueError("No discovery cohort stored; run retrospective discovery first")
                        capture = stored_capture
                        if capture["data_mode"] != "real":
                            raise ValueError("Cannot snapshot a synthetic cohort as measured")
                        adapter = YouTube()
                        ids = capture["cohort_ids"]
                        if not ids:
                            raise ValueError("Discovery returned no cohort")
                        payload = adapter.transport("videos", {"key": adapter.key, "part": "snippet,statistics", "id": ",".join(ids)})
                        snapshot_stamp = adapter.clock()
                        rows = [row.to_dict() for row in normalize_videos(query, payload, snapshot_stamp, ids)]
                        snapshot_run = youtube_store.save_run({
                            'retrieved_at': snapshot_stamp, 'topic_id': query['id'], 'query_id': query['query_id'],
                            'query': query['query'], 'market': query['market'], 'cohort_ids': ids,
                            'raw_response': payload, 'observations': rows,
                            'scope': 'legacy discovery sample, not a human relevance-audited cohort'}, 'legacy_snapshot')
                        youtube_store.export_run(snapshot_run, output / 'youtube_runs')
                    else:
                        if args.resume and stored_capture is not None:
                            old = stored_capture
                            if all(w["complete"] for w in old["windows"]):
                                continue
                        if not args.fixture and budget.limit - budget.used < 8 * args.max_pages_per_week:
                            raise ValueError("Insufficient remaining search budget for eight windows; resume later")
                        capture = fixture_youtube(query, config, index) if args.fixture else YouTubeRetrospective(
                            config["start_date"], config["end_date"], budget, max_pages=args.max_pages_per_week
                        ).discover(query)
                        capture['collection_invocation_id'] = invocation_id
                        run_id = youtube_store.save_run(capture, 'retrospective',
                                                        invocation_id + '--' + query['id'] + '--' + query['query_id'])
                        youtube_store.export_run(run_id, output / 'youtube_runs')
                        rows = capture["observations"]
                db.ingest([Observation(**row) for row in rows])
                incomplete = source == "youtube" and not args.snapshot and any(not w["complete"] for w in capture["windows"])
                reasons = sorted({w["error"] for w in capture["windows"] if w.get("error")}) if incomplete else []
                manifest[key] = {"state": "fixture" if args.fixture else "partial" if incomplete else "collected" if rows else "unavailable",
                                 "reason": "; ".join(reasons) if reasons else "Capped discovery windows" if incomplete else None if rows else "No usable observations",
                                 "observations": len(rows)}
            except Exception as error:
                manifest[key] = {"state": "blocked", "reason": str(error)}
            manifest_file.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    # Regenerate the candidate audit while preserving human labels by video/query ID.
    audit_path = output / "relevance_audit.csv"
    existing = {}
    if audit_path.exists():
        import csv
        with audit_path.open(encoding="utf-8-sig", newline="") as handle:
            existing = {(r["topic_id"], r["query_id"], r["video_id"]): r for r in csv.DictReader(handle)}
    audit = []
    for query in queries:
        _, capture = youtube_store.latest_capture(query['id'], query['query_id'])
        if capture is None:
            capture_path = raw / (query['id'] + '--' + query['query_id'] + '--youtube.json')
            if not capture_path.exists():
                continue
            capture = json.loads(capture_path.read_text(encoding='utf-8'))
        for row in audit_rows(capture):
            old = existing.get((row["topic_id"], row["query_id"], row["video_id"]), {})
            row.update({k: old[k] for k in ("label", "notes") if k in old})
            audit.append(row)
    export_csv(audit_path, audit, ["topic_id", "query_id", "query", "rank", "video_id", "url", "title", "description",
                                 "published_at", "channel_id", "channel_name", "retrieved_at",
                                 "current_views", "data_mode", "label", "notes"])
    all_rows = [row for topic in topics for row in db.observations(topic["id"], include_demo=args.fixture)]
    snapshots = [row["observation_date"] for row in all_rows if row["metric"] == "sampled_views"]
    stamp = datetime.now(timezone.utc).date().isoformat()
    # Fixture dates may extend into a synthetic future; measured expectations end today.
    config["snapshot_start"] = min(snapshots) if snapshots else stamp
    config["snapshot_end"] = max(snapshots) if args.fixture and snapshots else stamp
    status = {tuple(key.split("/")): value for key, value in manifest.items()}
    report = build_report(config, queries, all_rows, status, output, include_demo=args.fixture)
    print(json.dumps({"output": str(output), "data_mode": report["data_mode"],
                      "topics": len(topics), "queries": len(queries),
                      "observations": len(all_rows), "search_requests_used": budget.used}, indent=2))


if __name__ == "__main__":
    main()
