"""Read-only, transaction-consistent evidence access. No migrations or cache writes."""

import json
import sqlite3
from pathlib import Path


def read_evidence(path, topic, query):
    result = {'observations': [], 'runs': [], 'audit': [], 'cohorts': [], 'snapshots': []}
    path = Path(path)
    if not path.exists():
        return result
    connection = sqlite3.connect(path.resolve().as_uri() + '?mode=ro', uri=True)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute('BEGIN')
        tables = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        if 'source_observations' in tables:
            rows = connection.execute('SELECT * FROM source_observations WHERE topic_id=? AND query_id=? '
                                      'AND market=? AND is_demo=0', (topic['id'],query['query_id'],topic['market']))
            for row in rows:
                row = dict(row)
                if row['query'] != query['query']:
                    continue
                row['metadata'] = json.loads(row['metadata'])
                result['observations'].append(row)
        if 'youtube_runs' in tables:
            for run in connection.execute('SELECT * FROM youtube_runs ORDER BY retrieved_at,run_id'):
                payload = json.loads(run['payload'])
                for capture in payload.get('captures',[payload]):
                    if (capture.get('topic_id'),capture.get('query_id'),capture.get('query'),capture.get('market')) != (
                            topic['id'],query['query_id'],query['query'],topic['market']):
                        continue
                    if capture.get('data_mode') not in ('real','unavailable'):
                        continue
                    if run['kind'] not in ('legacy','retrospective','daily'):
                        continue
                    result['runs'].append({'run_id':run['run_id'],'kind':run['kind'],
                                           'sha256':run['sha256'],'capture':capture})
        if {'youtube_audit_candidates','youtube_audit_labels'} <= tables:
            rows = connection.execute("SELECT c.*,COALESCE(l.label,'pending') AS label FROM youtube_audit_candidates c "
                                      'LEFT JOIN youtube_audit_labels l USING(candidate_id) '
                                      'WHERE topic_id=? AND query_id=?', (topic['id'],query['query_id']))
            for row in rows:
                row = dict(row)
                payload = json.loads(row['payload'])
                if payload.get('query') == query['query'] and payload.get('data_mode') == 'real':
                    result['audit'].append(row)
        if {'youtube_cohorts','youtube_cohort_members','youtube_video_snapshots'} <= tables:
            for cohort in connection.execute('SELECT * FROM youtube_cohorts WHERE topic_id=? AND query_id=? '
                                              'ORDER BY selected_at,cohort_id', (topic['id'],query['query_id'])):
                cohort = dict(cohort)
                cohort['payload'] = json.loads(cohort['payload'])
                selected = cohort['payload'].get('members',[])
                matching_runs = {r['run_id'] for r in result['runs']}
                if not selected or any(r.get('query') != query['query'] or r.get('label') != 'relevant'
                                       or r.get('data_mode') != 'real' or r.get('run_id') not in matching_runs for r in selected):
                    continue
                cohort['members'] = [dict(r) for r in connection.execute(
                    'SELECT * FROM youtube_cohort_members WHERE cohort_id=?',(cohort['cohort_id'],))]
                if {r['video_id'] for r in cohort['members']} != {r['video_id'] for r in selected}:
                    continue
                result['cohorts'].append(cohort)
                for row in connection.execute('SELECT * FROM youtube_video_snapshots WHERE cohort_id=?',
                                              (cohort['cohort_id'],)):
                    row = dict(row)
                    payload = json.loads(row['payload'])
                    if payload.get('market') == topic['market'] and payload.get('query') == query['query']:
                        result['snapshots'].append(row)
        return result
    finally:
        connection.close()
