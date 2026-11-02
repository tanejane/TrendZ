"""Explicit archive, audit, cohort and daily collection commands (no scheduler)."""

import argparse
import csv
import hashlib
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.database import Database
from services.youtube_store import YouTubeStore, encoded
from services.ingestion.youtube_daily import YouTubeDaily


def daily_summary(payload):
    """HTTP success is separate from missing counters or capped discovery windows."""
    outcomes = payload.get('request_outcomes', [])
    snapshots = payload['snapshots']
    dates = sorted({row['snapshot_date'] for row in snapshots})
    return {'discovery_searches_completed':sum(o['endpoint']=='search' and o['completed'] for o in outcomes),
            'cohort_stats_requests_completed':sum(o['endpoint']=='videos' and o['completed'] for o in outcomes),
            'requests_failed':sum(not o['completed'] for o in outcomes),
            'cohort_videos_snapshotted':sum(row['raw_response'] is not None for row in snapshots),
            'video_records_unavailable':sum(row['status']=='unavailable' for row in snapshots),
            'video_records_partial':sum(row['status']=='partial' for row in snapshots),
            'capped_discovery_windows':sum(w['capped'] for c in payload['captures'] for w in c['windows']),
            'snapshot_dates':dates, 'publication_day':payload.get('publication_day'),
            'outcome_tracking_available':bool(outcomes)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['archive-legacy','audit-export','audit-import','audit-summary','cohort-create','daily'])
    parser.add_argument('--output',type=Path,default=ROOT/'reports/phase2-measured')
    parser.add_argument('--audit-id',default='canonical-160')
    parser.add_argument('--file',type=Path)
    parser.add_argument('--size',type=int,default=5)
    parser.add_argument('--date',help='Completed UTC publication day; defaults to yesterday UTC')
    parser.add_argument('--retry',action='store_true',help='Explicit extra immutable daily run; consumes API quota again')
    args = parser.parse_args()
    configured = json.loads((ROOT/'data/tracked_topics.json').read_text(encoding='utf-8'))
    config = json.loads((ROOT/'data/pilot_phase2.json').read_text(encoding='utf-8'))
    args.output.mkdir(parents=True,exist_ok=True)
    db = Database(args.output/'pilot.sqlite3')
    db.sync_topics(configured)
    store = YouTubeStore(db)
    path = args.file or args.output/'canonical_relevance_audit.csv'
    result = {}
    if args.command == 'archive-legacy':
        runs, candidates = {}, []
        for file in sorted((args.output/'raw').glob('*--youtube.json')):
            capture = json.loads(file.read_text(encoding='utf-8'))
            capture['archive_origin'] = 'surviving legacy capture; earlier overwritten payloads are unavailable'
            run_id = 'legacy-'+hashlib.sha256(encoded(capture).encode()).hexdigest()[:24]
            store.save_run(capture,'legacy',run_id)
            store.export_run(run_id,args.output/'youtube_runs')
            runs[(capture['topic_id'],capture['query_id'])] = (run_id,capture)
        # Freeze exactly the existing canonical 20-per-topic sample, not a new sample.
        with (args.output/'relevance_audit.csv').open(encoding='utf-8-sig',newline='') as handle:
            for row in csv.DictReader(handle):
                if row['query_id'] == 'canonical' and row['topic_id'] in config['topic_ids']:
                    row['run_id'] = runs[(row['topic_id'],row['query_id'])][0]
                    candidates.append(row)
        if len(candidates) != 160 or any(sum(r['topic_id']==t for r in candidates)!=20 for t in config['topic_ids']):
            raise ValueError('Expected the existing 160 canonical candidates, 20 per topic')
        count = store.freeze_audit(args.audit_id,candidates)
        exported = store.export_audit(args.audit_id,path) if not path.exists() else 'existing file preserved'
        result = {'archived_runs':len(runs),'frozen_candidates':count,
                  'exported_candidates':exported,'file':str(path)}
    elif args.command == 'audit-export':
        # Avoid replacing edits that have not been imported yet.
        if path.exists():
            raise ValueError('Output exists; use --file with a new filename to preserve unsaved edits')
        result = {'candidates':store.export_audit(args.audit_id,path),'file':str(path)}
    elif args.command == 'audit-import':
        result = {'changed_labels':store.import_labels(args.audit_id,path),'precision':store.precision(args.audit_id)}
    elif args.command == 'audit-summary':
        result = store.precision(args.audit_id)
    elif args.command == 'cohort-create':
        result = {'cohort_ids':store.create_cohorts(args.audit_id,args.size),
                  'cohorts':store.cohorts(args.audit_id),
                  'note':'No manually relevant measured candidates means no cohort, not an automatic substitute'}
    elif args.command == 'daily':
        day = args.date or (datetime.now(timezone.utc).date()-timedelta(days=1)).isoformat()
        topics = [t for identifier in config['topic_ids'] for t in configured if t['id']==identifier]
        cohorts = store.cohorts(args.audit_id)
        # Once per publication date/configuration; retries require an explicit flag.
        scope = hashlib.sha256(encoded([day,topics,cohorts,args.audit_id]).encode()).hexdigest()[:24]
        run_id = 'daily-'+scope
        with db.connect() as connection:
            old = connection.execute('SELECT run_id FROM youtube_runs WHERE run_id=?',(run_id,)).fetchone()
        if old and not args.retry:
            result = {'run_id':run_id,'status':'already_collected','requests':0}
        else:
            adapter = YouTubeDaily()
            payload = adapter.collect_day(topics,cohorts,day,args.audit_id)
            identifier = store.save_run(payload,'daily',None if args.retry else run_id)
            result = {'run_id':identifier,'archive':str(store.export_run(identifier,args.output/'youtube_runs')),
                      'requests':payload['requests'],'discovered_counts':[
                          {'topic_id':c['topic_id'],**{k:c['windows'][0][k] for k in ('discovered_video_count','complete','capped','error')}}
                          for c in payload['captures']], 'snapshots':len(payload['snapshots']),
                      'post_run_summary':daily_summary(payload)}
            summary = result['post_run_summary']
            print(f"{summary['discovery_searches_completed']} discovery searches completed; "
                  f"{summary['cohort_stats_requests_completed']} cohort stats requests completed; "
                  f"{summary['cohort_videos_snapshotted']} cohort videos snapshotted; "
                  f"{summary['requests_failed']} requests failed; "
                  f"snapshot date(s): {', '.join(summary['snapshot_dates']) or 'none'}", file=sys.stderr)
    if args.command in ('archive-legacy','audit-import','audit-summary'):
        summary = store.precision(args.audit_id)
        (args.output/'relevance_precision.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))


if __name__ == '__main__':
    main()
