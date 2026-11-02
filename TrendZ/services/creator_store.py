"""Additive creator indexes and immutable derived evidence; raw data stays in youtube_runs."""

import hashlib
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from .youtube_store import encoded


SCHEMA = """
CREATE TABLE IF NOT EXISTS creators (
 creator_id TEXT PRIMARY KEY, platform TEXT NOT NULL, channel_id TEXT NOT NULL,
 display_name TEXT NOT NULL, first_observed_at TEXT NOT NULL, last_observed_at TEXT NOT NULL,
 seed_provenance TEXT NOT NULL, UNIQUE(platform,channel_id));
CREATE TABLE IF NOT EXISTS creator_contents (
 creator_id TEXT NOT NULL REFERENCES creators(creator_id), run_id TEXT NOT NULL REFERENCES youtube_runs(run_id),
 video_id TEXT NOT NULL, source_ref TEXT NOT NULL, sample_scope TEXT NOT NULL,
 PRIMARY KEY(creator_id,run_id,video_id));
CREATE TABLE IF NOT EXISTS creator_profiles (
 profile_revision_id TEXT PRIMARY KEY, creator_id TEXT NOT NULL REFERENCES creators(creator_id),
 created_at TEXT NOT NULL, method_version TEXT NOT NULL, state TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS creator_specializations (
 profile_revision_id TEXT NOT NULL REFERENCES creator_profiles(profile_revision_id),
 specialization TEXT NOT NULL, state TEXT NOT NULL, evidence TEXT NOT NULL,
 PRIMARY KEY(profile_revision_id,specialization));
CREATE TABLE IF NOT EXISTS creator_topic_affinity_runs (
 affinity_run_id TEXT PRIMARY KEY, creator_id TEXT NOT NULL REFERENCES creators(creator_id),
 topic_id TEXT NOT NULL REFERENCES topics(id), query_id TEXT NOT NULL, market TEXT NOT NULL,
 created_at TEXT NOT NULL, method_version TEXT NOT NULL, payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS creator_topic_evidence (
 affinity_run_id TEXT NOT NULL REFERENCES creator_topic_affinity_runs(affinity_run_id),
 creator_id TEXT NOT NULL, run_id TEXT NOT NULL, video_id TEXT NOT NULL,
 evidence TEXT NOT NULL, PRIMARY KEY(affinity_run_id,run_id,video_id),
 FOREIGN KEY(creator_id,run_id,video_id) REFERENCES creator_contents(creator_id,run_id,video_id));
"""


def digest(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


@contextmanager
def readonly(path):
    db = sqlite3.connect(Path(path).resolve().as_uri()+'?mode=ro',uri=True)
    db.row_factory = sqlite3.Row
    try:
        yield db
    finally:
        db.close()


def cohort_seeds(path, topic_ids, audit_id='canonical-160', expected_size=5):
    """Only current relevant, measured canonical cohort members may seed expansion."""
    with readonly(path) as db:
        db.execute('BEGIN')
        rows = db.execute('SELECT c.topic_id,c.query_id,c.cohort_id,c.audit_id,m.*, '
                          'a.run_id,a.payload,l.label,l.labelled_at '
                          'FROM youtube_cohorts c JOIN youtube_cohort_members m USING(cohort_id) '
                          'JOIN youtube_audit_candidates a USING(candidate_id) '
                          'JOIN youtube_audit_labels l USING(candidate_id) WHERE c.audit_id=?',(audit_id,)).fetchall()
        grouped = {}
        topic_counts = {topic:0 for topic in topic_ids}
        for raw in rows:
            row = dict(raw)
            if row['topic_id'] not in topic_counts or row['query_id']!='canonical':
                continue
            candidate = json.loads(row['payload'])
            if row['label']!='relevant' or candidate.get('data_mode')!='real' or not candidate.get('channel_id'):
                raise ValueError('Cohort contains a non-relevant, unmeasured or unidentified seed')
            if any(candidate.get(key)!=row[key] for key in ('topic_id','query_id','video_id','run_id','published_at')):
                raise ValueError('Seed candidate identity/query provenance mismatch')
            run = db.execute('SELECT payload FROM youtube_runs WHERE run_id=?',(row['run_id'],)).fetchone()
            capture = json.loads(run['payload'])
            matching = [v for v in capture.get('videos',[]) if v.get('id')==row['video_id']]
            if not matching or matching[0].get('channelId')!=candidate['channel_id']:
                raise ValueError('Seed channel does not match immutable video provenance')
            event = db.execute('SELECT event_id FROM youtube_label_events WHERE candidate_id=? '
                               'ORDER BY event_id DESC LIMIT 1',(row['candidate_id'],)).fetchone()
            if event is None:
                raise ValueError('Seed label has no revision event')
            channel = candidate['channel_id']
            seed = grouped.setdefault(channel, {'creator_id':'youtube:'+channel,'channel_id':channel,
                'display_name':candidate.get('channel_name',''),'seeds':[]})
            seed['seeds'].append({key:row[key] for key in ('topic_id','query_id','cohort_id','audit_id',
                'candidate_id','video_id','run_id','published_at','labelled_at')})
            seed['seeds'][-1].update(label_event_id=event[0],retrieved_at=candidate['retrieved_at'],label='relevant')
            topic_counts[row['topic_id']] += 1
        if any(count!=expected_size for count in topic_counts.values()):
            raise ValueError('Expected exactly five relevant canonical cohort videos per pilot topic')
    return sorted(grouped.values(),key=lambda s:s['channel_id'])


def existing_content(path, seed):
    """Reuse full stored snippets/counters; keep only latest record per video, with provenance."""
    rows = []
    with readonly(path) as db:
        for run in db.execute("SELECT * FROM youtube_runs WHERE kind IN ('legacy','retrospective') ORDER BY retrieved_at,run_id"):
            payload = json.loads(run['payload'])
            if payload.get('data_mode')!='real':
                continue
            valid_ids = {v['id'] for v in payload.get('videos',[]) if v.get('channelId')==seed['channel_id']}
            details_ids = set()
            for index,video in enumerate(payload.get('present_day_statistics',[])):
                snippet = video.get('snippet',{})
                if video.get('id') not in valid_ids or snippet.get('channelId')!=seed['channel_id']:
                    continue
                details_ids.add(video['id'])
                stats = video.get('statistics',{})
                def count(key):
                    value = stats.get(key)
                    try:
                        return int(value) if value is not None and int(value)>=0 else None
                    except (ValueError,TypeError,OverflowError):
                        return None
                rows.append({'video_id':video['id'],'channel_id':seed['channel_id'],
                    'title':snippet.get('title',''),'description':snippet.get('description',''),
                    'published_at':snippet.get('publishedAt'),'retrieved_at':run['retrieved_at'],
                    'views':count('viewCount'),'likes':count('likeCount'),'comments':count('commentCount'),
                    'sample_scope':'query_selected_legacy','source_query_id':payload['query_id'],
                    'source_ref':{'run_id':run['run_id'],'collection':'present_day_statistics','item_index':index},
                    'url':'https://www.youtube.com/watch?v='+video['id'],
                    'statistics_scope':'retrieval_time_not_historical'})
            for index,video in enumerate(payload.get('videos',[])):
                if video.get('id') not in valid_ids or video['id'] in details_ids:
                    continue
                rows.append({'video_id':video['id'],'channel_id':seed['channel_id'],
                    'title':video.get('title',''),'description':video.get('description',''),
                    'published_at':video.get('publishedAt'),'retrieved_at':run['retrieved_at'],
                    'views':None,'likes':None,'comments':None,'sample_scope':'query_selected_legacy',
                    'source_query_id':payload['query_id'],
                    'source_ref':{'run_id':run['run_id'],'collection':'videos','item_index':index},
                    'url':'https://www.youtube.com/watch?v='+video['id'],
                    'statistics_scope':'retrieval_time_not_historical'})
    latest = {}
    for row in sorted(rows,key=lambda r:(r['retrieved_at'],r['source_ref']['run_id'])):
        latest[row['video_id']] = row
    return list(latest.values())


class CreatorStore:
    def __init__(self, database):
        self.database = database
        with database.connect() as db:
            db.executescript(SCHEMA)
            db.execute("INSERT OR IGNORE INTO migrations(name) VALUES ('creator_evidence_v1')")
            for table in ('creator_contents','creator_profiles','creator_specializations',
                          'creator_topic_affinity_runs','creator_topic_evidence'):
                for action in ('UPDATE','DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} BEFORE {action} ON {table} "
                               "BEGIN SELECT RAISE(ABORT,'Immutable creator evidence'); END")

    def save_analysis(self, seed, result):
        created_at = datetime.now(timezone.utc).isoformat()
        with self.database.connect() as db:
            stamps = [s['retrieved_at'] for s in seed['seeds']]+[v['retrieved_at'] for v in result['videos']]
            db.execute('INSERT INTO creators VALUES (?,?,?,?,?,?,?) ON CONFLICT(creator_id) '
                'DO UPDATE SET first_observed_at=MIN(first_observed_at,excluded.first_observed_at),'
                'last_observed_at=MAX(last_observed_at,excluded.last_observed_at)',
                (seed['creator_id'],'youtube',seed['channel_id'],seed['display_name'],min(stamps),max(stamps),encoded(seed['seeds'])))
            for video in result['videos']:
                reference = video['source_ref']
                raw = db.execute('SELECT payload FROM youtube_runs WHERE run_id=?',(reference['run_id'],)).fetchone()
                if raw is None:
                    raise ValueError('Missing raw creator-video run')
                payload = json.loads(raw['payload'])
                try:
                    if 'request_index' in reference:
                        item = payload['requests'][reference['request_index']]['response']['items'][reference['item_index']]
                    else:
                        item = payload[reference['collection']][reference['item_index']]
                    snippet = item.get('snippet',item)
                    if item['id']!=video['video_id'] or snippet.get('channelId')!=seed['channel_id']:
                        raise ValueError('Raw video/channel does not match creator evidence')
                except (KeyError,IndexError,TypeError):
                    raise ValueError('Invalid raw creator evidence reference') from None
                prior = db.execute('SELECT source_ref,sample_scope FROM creator_contents WHERE creator_id=? AND run_id=? AND video_id=?',
                    (seed['creator_id'],reference['run_id'],video['video_id'])).fetchone()
                if prior and (prior['source_ref']!=encoded(reference) or prior['sample_scope']!=video['sample_scope']):
                    raise ValueError('Existing creator content reference is immutable')
                db.execute('INSERT OR IGNORE INTO creator_contents VALUES (?,?,?,?,?)',
                    (seed['creator_id'],video['source_ref']['run_id'],video['video_id'],
                     encoded(video['source_ref']),video['sample_scope']))
            profile = result['profile']
            profile_id = 'profile-'+digest([seed['creator_id'],profile])
            db.execute('INSERT OR IGNORE INTO creator_profiles VALUES (?,?,?,?,?,?)',
                (profile_id,seed['creator_id'],created_at,result['method_version'],profile['state'],encoded(profile)))
            for specialization in profile['proposed_specializations']:
                db.execute('INSERT OR IGNORE INTO creator_specializations VALUES (?,?,?,?)',
                    (profile_id,specialization,'provisional_screen',encoded(profile['specialization_evidence'][specialization])))
            for topic_id,affinity in result['topics'].items():
                identifier = 'affinity-'+digest([seed['creator_id'],result['method_version'],result['as_of'],affinity])
                db.execute('INSERT OR IGNORE INTO creator_topic_affinity_runs VALUES (?,?,?,?,?,?,?,?)',
                    (identifier,seed['creator_id'],topic_id,'canonical','MY',created_at,result['method_version'],encoded({'as_of':result['as_of'],**affinity})))
                for evidence in affinity['video_evidence']:
                    ref = evidence['source_ref']
                    db.execute('INSERT OR IGNORE INTO creator_topic_evidence VALUES (?,?,?,?,?)',
                        (identifier,seed['creator_id'],ref['run_id'],evidence['video_id'],encoded(evidence)))
