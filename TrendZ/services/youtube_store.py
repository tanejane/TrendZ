"""Append-only YouTube captures, frozen human audits and fixed video cohorts."""

import csv
import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


def now():
    return datetime.now(timezone.utc).isoformat()


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, allow_nan=False)


SCHEMA = """
CREATE TABLE IF NOT EXISTS youtube_runs (
 run_id TEXT PRIMARY KEY, kind TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 payload TEXT NOT NULL, sha256 TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS youtube_discoveries (
 run_id TEXT NOT NULL REFERENCES youtube_runs(run_id), topic_id TEXT NOT NULL,
 query_id TEXT NOT NULL, query TEXT NOT NULL, market TEXT NOT NULL,
 window_start TEXT NOT NULL, window_end TEXT NOT NULL, page INTEGER NOT NULL,
 position INTEGER NOT NULL, video_id TEXT NOT NULL, retrieved_at TEXT NOT NULL,
 published_at TEXT, payload TEXT NOT NULL,
 PRIMARY KEY(run_id,topic_id,query_id,window_start,page,position));
CREATE TABLE IF NOT EXISTS youtube_audit_candidates (
 candidate_id TEXT PRIMARY KEY, audit_id TEXT NOT NULL, run_id TEXT NOT NULL REFERENCES youtube_runs(run_id),
 topic_id TEXT NOT NULL, query_id TEXT NOT NULL, video_id TEXT NOT NULL,
 rank INTEGER NOT NULL, payload TEXT NOT NULL,
 UNIQUE(audit_id,topic_id,query_id,video_id));
CREATE TABLE IF NOT EXISTS youtube_audit_labels (
 candidate_id TEXT PRIMARY KEY REFERENCES youtube_audit_candidates(candidate_id),
 label TEXT NOT NULL CHECK(label IN ('pending','relevant','partially relevant','irrelevant')),
 notes TEXT NOT NULL, labelled_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS youtube_label_events (
 event_id INTEGER PRIMARY KEY, candidate_id TEXT NOT NULL REFERENCES youtube_audit_candidates(candidate_id),
 label TEXT NOT NULL, notes TEXT NOT NULL, labelled_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS youtube_cohorts (
 cohort_id TEXT PRIMARY KEY, topic_id TEXT NOT NULL, query_id TEXT NOT NULL,
 audit_id TEXT NOT NULL, selected_at TEXT NOT NULL, payload TEXT NOT NULL,
 UNIQUE(topic_id,query_id,audit_id));
CREATE TABLE IF NOT EXISTS youtube_cohort_members (
 cohort_id TEXT NOT NULL REFERENCES youtube_cohorts(cohort_id), video_id TEXT NOT NULL,
 candidate_id TEXT NOT NULL REFERENCES youtube_audit_candidates(candidate_id),
 published_at TEXT NOT NULL, PRIMARY KEY(cohort_id,video_id));
CREATE TABLE IF NOT EXISTS youtube_video_snapshots (
 run_id TEXT NOT NULL REFERENCES youtube_runs(run_id), cohort_id TEXT NOT NULL REFERENCES youtube_cohorts(cohort_id),
 video_id TEXT NOT NULL, published_at TEXT NOT NULL, snapshot_date TEXT NOT NULL,
 retrieved_at TEXT NOT NULL, views INTEGER, likes INTEGER, status TEXT NOT NULL, reason TEXT,
 payload TEXT NOT NULL, PRIMARY KEY(run_id,cohort_id,video_id));
"""


class YouTubeStore:
    def __init__(self, database):
        self.database = database
        with database.connect() as db:
            db.executescript(SCHEMA)
            # The latest-run lookup is derived; raw runs and memberships are never updated.
            for table in ('youtube_runs', 'youtube_discoveries', 'youtube_audit_candidates',
                          'youtube_label_events', 'youtube_cohorts', 'youtube_cohort_members',
                          'youtube_video_snapshots'):
                for action in ('UPDATE', 'DELETE'):
                    db.execute(f"CREATE TRIGGER IF NOT EXISTS immutable_{table}_{action} "
                               f"BEFORE {action} ON {table} BEGIN SELECT RAISE(ABORT,'Immutable YouTube record'); END")

    def save_run(self, payload, kind, run_id=None):
        run_id = run_id or uuid.uuid4().hex
        raw = encoded(payload)
        digest = hashlib.sha256(raw.encode()).hexdigest()
        with self.database.connect() as db:
            old = db.execute('SELECT sha256,kind FROM youtube_runs WHERE run_id=?', (run_id,)).fetchone()
            if old:
                if old['sha256'] != digest or old['kind'] != kind:
                    raise ValueError('Run ID already belongs to different immutable content')
                return run_id
            db.execute('INSERT INTO youtube_runs VALUES (?,?,?,?,?)',
                       (run_id, kind, payload['retrieved_at'], raw, digest))
            captures = payload.get('captures', [payload])
            for capture in captures:
                for window in capture.get('windows', []):
                    for page, response in enumerate(window.get('responses', []), 1):
                        for position, item in enumerate(response.get('items', []), 1):
                            video_id = item.get('id', {}).get('videoId')
                            if video_id:
                                db.execute('INSERT INTO youtube_discoveries VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)',
                                           (run_id, capture['topic_id'], capture['query_id'], capture['query'],
                                            capture['market'], window['start'], window['end_exclusive'], page,
                                            position, video_id, capture['retrieved_at'],
                                            item.get('snippet', {}).get('publishedAt'), encoded(item)))
            for snapshot in payload.get('snapshots', []):
                db.execute('INSERT INTO youtube_video_snapshots VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                           (run_id, snapshot['cohort_id'], snapshot['video_id'], snapshot['published_at'],
                            snapshot['snapshot_date'], snapshot['retrieved_at'], snapshot['views'],
                            snapshot['likes'], snapshot['status'], snapshot['reason'], encoded(snapshot)))
        return run_id

    def export_run(self, run_id, directory):
        with self.database.connect() as db:
            row = db.execute('SELECT * FROM youtube_runs WHERE run_id=?', (run_id,)).fetchone()
        if not row:
            raise ValueError('Unknown run ID')
        target = Path(directory) / (run_id + '.json')
        target.parent.mkdir(parents=True, exist_ok=True)
        artifact = encoded(dict(row))
        if target.exists():
            if target.read_text(encoding='utf-8') != artifact:
                raise ValueError('Refusing to overwrite a different run artifact')
        else:
            with target.open('x', encoding='utf-8') as handle:
                handle.write(artifact)
        return target

    def latest_capture(self, topic_id, query_id):
        with self.database.connect() as db:
            rows = db.execute("SELECT * FROM youtube_runs WHERE kind IN ('retrospective','legacy') "
                              'ORDER BY retrieved_at DESC,rowid DESC').fetchall()
        for row in rows:
            capture = json.loads(row['payload'])
            if capture.get('topic_id') == topic_id and capture.get('query_id') == query_id:
                return row['run_id'], capture
        return None, None

    def freeze_audit(self, audit_id, rows):
        with self.database.connect() as db:
            existing = db.execute('SELECT COUNT(*) FROM youtube_audit_candidates WHERE audit_id=?', (audit_id,)).fetchone()[0]
            if existing:
                return existing
            for row in rows:
                candidate_id = hashlib.sha256(encoded([audit_id, row['topic_id'], row['query_id'], row['video_id']]).encode()).hexdigest()[:24]
                db.execute('INSERT INTO youtube_audit_candidates VALUES (?,?,?,?,?,?,?,?)',
                           (candidate_id, audit_id, row['run_id'], row['topic_id'], row['query_id'],
                            row['video_id'], int(row['rank']), encoded(row)))
        return len(rows)

    def audit_rows(self, audit_id):
        with self.database.connect() as db:
            rows = db.execute("SELECT c.*,COALESCE(l.label,'pending') AS label,COALESCE(l.notes,'') AS notes "
                              'FROM youtube_audit_candidates c LEFT JOIN youtube_audit_labels l USING(candidate_id) '
                              'WHERE audit_id=? ORDER BY topic_id,query_id,rank', (audit_id,)).fetchall()
        return [{**json.loads(row['payload']), 'candidate_id': row['candidate_id'],
                 'label': row['label'], 'notes': row['notes']} for row in rows]

    def export_audit(self, audit_id, path):
        rows = self.audit_rows(audit_id)
        if not rows:
            raise ValueError('No frozen candidates for this audit')
        fields = ['candidate_id','run_id','topic_id','query_id','query','rank','video_id','url','title',
                  'description','published_at','channel_id','channel_name','retrieved_at',
                  'current_views','data_mode','label','notes']
        with Path(path).open('w', encoding='utf-8-sig', newline='') as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction='ignore')
            writer.writeheader()
            writer.writerows(rows)
        return len(rows)

    def import_labels(self, audit_id, path):
        with Path(path).open(encoding='utf-8-sig', newline='') as handle:
            rows = list(csv.DictReader(handle))
        known = {row['candidate_id']: row for row in self.audit_rows(audit_id)}
        seen, changed, stamp = set(), 0, now()
        # Validate the complete file before writing any labels.
        for row in rows:
            identifier = row.get('candidate_id')
            if identifier not in known or identifier in seen:
                raise ValueError('Unknown or duplicate audit candidate')
            seen.add(identifier)
            if row.get('label') not in ('pending','relevant','partially relevant','irrelevant'):
                raise ValueError('Label must be pending, relevant, partially relevant or irrelevant')
            if any(row.get(key) != known[identifier].get(key) for key in ('video_id','topic_id','query_id','run_id')):
                raise ValueError('Candidate provenance changed; edit only label and notes')
        with self.database.connect() as db:
            for row in rows:
                identifier, label, notes = row['candidate_id'], row['label'], row.get('notes','')
                if (known[identifier]['label'], known[identifier]['notes']) == (label, notes):
                    continue
                db.execute('INSERT INTO youtube_audit_labels VALUES (?,?,?,?) ON CONFLICT(candidate_id) '
                           'DO UPDATE SET label=excluded.label,notes=excluded.notes,labelled_at=excluded.labelled_at',
                           (identifier,label,notes,stamp))
                db.execute('INSERT INTO youtube_label_events(candidate_id,label,notes,labelled_at) VALUES (?,?,?,?)',
                           (identifier,label,notes,stamp))
                changed += 1
        return changed

    def precision(self, audit_id):
        groups = defaultdict(list)
        for row in self.audit_rows(audit_id):
            groups[(row['topic_id'],row['query_id'])].append(row)
        result = []
        for (topic, query), rows in groups.items():
            counts = {label: sum(r['label'] == label for r in rows)
                      for label in ('pending','relevant','partially relevant','irrelevant')}
            labelled = len(rows) - counts['pending']
            result.append({'topic_id':topic,'query_id':query,'candidates':len(rows),**counts,
                           'labelled':labelled,'strict_precision':counts['relevant']/labelled if labelled else None,
                           'inclusive_precision':(counts['relevant']+counts['partially relevant'])/labelled if labelled else None,
                           'status':'pending' if not labelled else 'partial' if counts['pending'] else 'complete'})
        return result

    def create_cohorts(self, audit_id, size=5):
        if not 1 <= size <= 10:
            raise ValueError('Cohort size must be 1-10')
        groups = defaultdict(list)
        for row in self.audit_rows(audit_id):
            if row['query_id'] == 'canonical' and row['label'] == 'relevant' and row['data_mode'] == 'real':
                groups[row['topic_id']].append(row)
        created = []
        with self.database.connect() as db:
            for topic, rows in groups.items():
                old = db.execute('SELECT cohort_id FROM youtube_cohorts WHERE topic_id=? AND audit_id=?', (topic,audit_id)).fetchone()
                if old:
                    created.append(old['cohort_id'])
                    continue
                selected = rows[:size]
                cohort_id = uuid.uuid4().hex
                payload = {'selection':'human relevant only, ascending frozen audit rank',
                           'requested_size':size,'members':selected}
                db.execute('INSERT INTO youtube_cohorts VALUES (?,?,?,?,?,?)',
                           (cohort_id,topic,'canonical',audit_id,now(),encoded(payload)))
                for row in selected:
                    db.execute('INSERT INTO youtube_cohort_members VALUES (?,?,?,?)',
                               (cohort_id,row['video_id'],row['candidate_id'],row['published_at']))
                created.append(cohort_id)
        return created

    def cohorts(self, audit_id):
        with self.database.connect() as db:
            rows = [dict(r) for r in db.execute('SELECT * FROM youtube_cohorts WHERE audit_id=?', (audit_id,))]
            for row in rows:
                row['members'] = [dict(r) for r in db.execute('SELECT * FROM youtube_cohort_members WHERE cohort_id=? ORDER BY video_id', (row['cohort_id'],))]
        return rows
