"""Expand only the 40 cohort channels; raw request captures and derived reviews stay separate."""

import argparse
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.database import Database
from services.youtube_store import YouTubeStore, encoded
from services.creator_store import CreatorStore, cohort_seeds, existing_content, readonly, digest
from services.ingestion.creator_youtube import CreatorYouTube, normalize_capture
from services.creator_analysis import analyze_creator, timestamp
from services.creator_report import export


def guard_hashes():
    paths = list((ROOT/'reports/phase4c').glob('*.*'))+list((ROOT/'reports/phase4d-lite').glob('*.*'))
    paths += [ROOT/name for name in ('services/product_fit.py','services/product_catalogue.py',
        'services/product_evaluation.py','services/product_validation.py','data/products/catalogue.json',
        'data/products/human_review.json','data/product_intents.json','data/tracked_topics.json',
        'data/products/review_sessions/local.sqlite3')]
    return {str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in paths if path.is_file()}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['plan','reuse-existing','collect'])
    parser.add_argument('--db',type=Path,default=ROOT/'reports/phase2-measured/pilot.sqlite3')
    parser.add_argument('--output',type=Path)
    parser.add_argument('--batch-id',default='phase5b-initial')
    parser.add_argument('--max-videos',type=int,default=20)
    parser.add_argument('--scan-limit',type=int,default=50)
    parser.add_argument('--as-of',help='Timezone-aware cutoff; defaults to now UTC')
    parser.add_argument('--retry',action='store_true',help='Explicit new requests even for completed channel captures')
    args=parser.parse_args()
    if not 1<=args.max_videos<=args.scan_limit<=50:
        parser.error('Require 1 <= --max-videos <= --scan-limit <= 50')
    if not args.db.is_file():
        parser.error('Measured database missing; refusing to create an empty substitute')
    before=guard_hashes()
    config=json.loads((ROOT/'data/pilot_phase2.json').read_text(encoding='utf-8'))
    vocab=json.loads((ROOT/'data/creator_evidence_v1.json').read_text(encoding='utf-8'))
    seeds=cohort_seeds(args.db,config['topic_ids'])
    if len(seeds)!=40:
        raise ValueError('This pilot requires exactly the existing 40 unique cohort channels')
    as_of=timestamp(args.as_of).isoformat() if args.as_of else datetime.now(timezone.utc).isoformat()
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    output=args.output or ROOT/'reports/phase5b'/(args.command+'-'+stamp)
    if args.command!='plan' and any((output/name).exists() for name in ('review_dataset.json','metrics.json','report.md')):
        raise ValueError('Output already contains a review/report; select a fresh --output directory')
    policy={'max_videos':args.max_videos,'scan_limit':args.scan_limit}
    manifest={'batch_id':args.batch_id,'seed_fingerprint':digest(seeds),'policy':policy,
              'as_of':as_of,'source_database':str(args.db.resolve()),'vocabulary_version':vocab['version'],
              'vocabulary_sha256':hashlib.sha256((ROOT/'data/creator_evidence_v1.json').read_bytes()).hexdigest(),
              'source_run_ids':[],'new_request_count':0}
    if args.command=='plan':
        print(json.dumps({**manifest,'creator_count':len(seeds),'maximum_requests':120,
                          'channel_ids':[seed['channel_id'] for seed in seeds]},indent=2))
        return
    adapter=CreatorYouTube() if args.command=='collect' else None
    # Snapshot all previous raw-run digests before the additive migration/collection.
    with readonly(args.db) as db:
        old_runs={row['run_id']:row['sha256'] for row in db.execute('SELECT run_id,sha256 FROM youtube_runs')}
    database=Database(args.db)
    youtube=YouTubeStore(database)
    store=CreatorStore(database)
    creators=[]
    blocked_reason=None
    failed_streak=0
    for index,seed in enumerate(seeds,1):
        channel_metadata=None
        if adapter:
            key=digest([args.batch_id,manifest['seed_fingerprint'],seed['channel_id'],policy])
            payload,run_id=None,None
            with database.connect() as db:
                for raw in db.execute("SELECT * FROM youtube_runs WHERE kind='creator_expansion' ORDER BY rowid DESC"):
                    candidate=json.loads(raw['payload'])
                    if candidate.get('collection_key')==key and candidate.get('state') in ('available','partial'):
                        payload,run_id=candidate,raw['run_id']
                        break
            if payload is None or args.retry:
                if blocked_reason:
                    payload={'channel_id':seed['channel_id'],'retrieved_at':datetime.now(timezone.utc).isoformat(),
                        'state':'unavailable','reason':blocked_reason,'data_mode':'unavailable','requests':[],
                        'selected_ids':[],'excluded':[],'policy':policy}
                else:
                    payload=adapter.collect(seed['channel_id'],**policy)
                    failed_streak=failed_streak+1 if payload['state']=='unavailable' else 0
                    if any(r.get('http_status') in (401,403,429) for r in payload['requests']):
                        blocked_reason='Collection halted after authorization/quota/rate-limit failure; retry later explicitly'
                    elif failed_streak>=3:
                        blocked_reason='Collection halted after three consecutive failed channels; retry later explicitly'
                payload.update(collection_key=key,batch_id=args.batch_id,seed_fingerprint=manifest['seed_fingerprint'])
                run_id=youtube.save_run(payload,'creator_expansion','creator-'+uuid.uuid4().hex)
                manifest['new_request_count']+=len(payload['requests'])
            youtube.export_run(run_id,output/'raw')
            manifest['source_run_ids'].append(run_id)
            videos=normalize_capture(payload,run_id)
            for request in payload['requests']:
                if request['resource']=='channels':
                    channel_metadata=next((item for item in request.get('response',{}).get('items',[]) if item.get('id')==seed['channel_id']),None)
            collection={'scope':'bounded_uploads','state':payload['state'],'reason':payload['reason'],
                'run_id':run_id,'selected_count':len(videos),'excluded':payload['excluded'],
                'scanned_video_count':len(payload.get('scanned_video_ids',[])),
                'details_returned_count':sum(len(r.get('response',{}).get('items',[])) for r in payload['requests'] if r['resource']=='videos'),
                'channel_source_ref':{'run_id':run_id,'request_index':0} if payload['requests'] else None,
                'channel_retrieved_at':payload['requests'][0]['retrieved_at'] if payload['requests'] else None,
                'playlist_has_more':payload.get('playlist_has_more'), 'policy':payload['policy']}
        else:
            videos=existing_content(args.db,seed)
            collection={'scope':'query_selected_legacy','state':'not_live_expanded',
                        'reason':'Existing evidence reuse only; no new API content retrieved',
                        'selected_count':len(videos)}
        # Cutoff for a new live result must include actual API response timestamps.
        cutoff=as_of if args.as_of else max([as_of]+[v['retrieved_at'] for v in videos]+
            ([collection['channel_retrieved_at']] if collection.get('channel_retrieved_at') else []))
        result=analyze_creator(seed,videos,vocab,cutoff,collection,channel_metadata)
        manifest['source_run_ids'].extend(v['source_ref']['run_id'] for v in result['videos'])
        store.save_analysis(seed,result)
        creators.append(result)
        print(f"{index}/40 {seed['channel_id']}: {len(result['videos'])} videos ({collection['state']})",file=sys.stderr,flush=True)
    status=('Live bounded YouTube evidence expansion; all new text matches/profiles remain provisional.' if adapter else
            'EXISTING-DATA REUSE ONLY. No recent-content API collection has been performed by this run. Do not treat this as completed live expansion.')
    manifest['analysis_cutoff_range']={'first':min(c['as_of'] for c in creators),'last':max(c['as_of'] for c in creators)}
    manifest['source_run_ids']=sorted(set(manifest['source_run_ids']))
    with readonly(args.db) as db:
        manifest['source_run_sha256']={identifier:db.execute('SELECT sha256 FROM youtube_runs WHERE run_id=?',
            (identifier,)).fetchone()[0] for identifier in manifest['source_run_ids']}
    summary=export(output,creators,status,manifest)
    with readonly(args.db) as db:
        for identifier,sha in old_runs.items():
            assert db.execute('SELECT sha256 FROM youtube_runs WHERE run_id=?',(identifier,)).fetchone()[0]==sha
    if guard_hashes()!=before:
        raise RuntimeError('Protected Product Fit files changed during creator expansion')
    print(json.dumps({'output':str(output),'new_requests':manifest['new_request_count'],**summary},indent=2))


if __name__=='__main__':
    main()
