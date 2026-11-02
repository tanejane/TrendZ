"""Local human review storage. Fixed identities/predictions are never edited by labels."""

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from contextlib import contextmanager

from .product_catalogue import ROOT
from .product_evaluation import GRADES, evaluate
from .product_fit import ProductFit, METHOD

FROZEN_FILES = ('data/products/human_review.json', 'data/products/catalogue.json',
                'data/product_intents.json', 'data/tracked_topics.json',
                'services/product_fit.py', 'services/product_catalogue.py')


def encoded(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(',', ':'))


def fingerprint(value):
    return hashlib.sha256(encoded(value).encode()).hexdigest()


def pair_id(row):
    return '/'.join(row[key] for key in ('topic_id', 'query_id', 'product_id'))


class ReviewConflict(ValueError):
    pass


class ReviewStore:
    def __init__(self, path, root=ROOT):
        self.path, self.root = Path(path), Path(root)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def current_fingerprints(self):
        result = {}
        for name in FROZEN_FILES:
            try:
                result[name] = hashlib.sha256((self.root/name).read_bytes()).hexdigest()
            except FileNotFoundError:
                result[name] = None
        return result

    def initialize(self):
        """Explicit startup only: seed labels from existing HUMAN fields, never predictions."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        from .product_review_assist import initialize
        initialize(self)
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS metadata (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS pairs (
                    pair_id TEXT PRIMARY KEY, position INTEGER UNIQUE NOT NULL,
                    fixed_json TEXT NOT NULL, prediction_json TEXT NOT NULL, context_json TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS labels (
                    pair_id TEXT PRIMARY KEY REFERENCES pairs(pair_id),
                    human_label TEXT CHECK(human_label IS NULL OR human_label IN
                        ('direct_fit','supporting_fit','no_fit','insufficient_evidence')),
                    notes TEXT NOT NULL, unsupported_explanation INTEGER CHECK(unsupported_explanation IN (0,1)),
                    reviewer TEXT, reviewed_on TEXT, revision INTEGER NOT NULL DEFAULT 0
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY, pair_id TEXT NOT NULL,
                    before_json TEXT NOT NULL, after_json TEXT NOT NULL, saved_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS reports (
                    revision_hash TEXT PRIMARY KEY, report_json TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TRIGGER IF NOT EXISTS pairs_no_update BEFORE UPDATE ON pairs
                    BEGIN SELECT RAISE(ABORT,'Fixed review pairs are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS pairs_no_delete BEFORE DELETE ON pairs
                    BEGIN SELECT RAISE(ABORT,'Fixed review pairs are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT,'Review events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS events_no_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT,'Review events are append-only'); END;
                CREATE TRIGGER IF NOT EXISTS metadata_no_update BEFORE UPDATE ON metadata
                    BEGIN SELECT RAISE(ABORT,'Session provenance is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS metadata_no_delete BEFORE DELETE ON metadata
                    BEGIN SELECT RAISE(ABORT,'Session provenance is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS reports_no_update BEFORE UPDATE ON reports
                    BEGIN SELECT RAISE(ABORT,'Validation reports are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS reports_no_delete BEFORE DELETE ON reports
                    BEGIN SELECT RAISE(ABORT,'Validation reports are immutable'); END;
            ''')
            db.execute('BEGIN IMMEDIATE')
            if db.execute("SELECT 1 FROM metadata WHERE key='session'").fetchone():
                return
            service = ProductFit()
            baseline = json.loads((self.root/'data/products/human_review.json').read_text(encoding='utf-8'))
            evaluate(service, baseline)  # Existing fixed-set/schema/family validation.
            outputs = {topic:service.topic(topic) for topic in service.intents['topics']}
            meta = {'created_at':datetime.now(timezone.utc).isoformat(),
                    'catalogue_version':service.catalogue.version, 'method_version':METHOD,
                    'intent_version':service.intents['version'], 'fingerprints':self.current_fingerprints(),
                    'baseline':baseline, 'outputs':outputs}
            meta['session_id'] = fingerprint({key:meta[key] for key in ('fingerprints','created_at')})[:20]
            db.execute('INSERT INTO metadata VALUES (?,?)',('session',encoded(meta)))
            for position, row in enumerate(baseline['rows']):
                topic = outputs[row['topic_id']]
                prediction = next(p for p in topic['assessments'] if p['product_id']==row['product_id'])
                context = {key:topic[key] for key in ('topic_id','canonical_topic','query_id','query','market','intent','intent_version')}
                db.execute('INSERT INTO pairs VALUES (?,?,?,?,?)',
                           (pair_id(row),position,encoded(row),encoded(prediction),encoded(context)))
                support = row.get('unsupported_explanation')
                db.execute('INSERT INTO labels VALUES (?,?,?,?,?,?,0)',
                           (pair_id(row),row['human_label'],row.get('notes') or '',support,
                            row.get('reviewer'),row.get('reviewed_on')))

    def metadata(self):
        with self.connect() as db:
            return json.loads(db.execute("SELECT value FROM metadata WHERE key='session'").fetchone()[0])

    def rows(self):
        from .product_review_assist import records
        assistance = records(self)
        with self.connect() as db:
            records = db.execute('SELECT pairs.*,labels.human_label,labels.notes,labels.unsupported_explanation, '
                                 'labels.reviewer,labels.reviewed_on,labels.revision FROM pairs JOIN labels USING(pair_id) '
                                 'ORDER BY position').fetchall()
            latest_events = {}
            for event in db.execute('SELECT event_id,pair_id,after_json FROM events ORDER BY event_id'):
                latest_events[event['pair_id']] = (event['event_id'],json.loads(event['after_json']))
        result = []
        for record in records:
            row = dict(record)
            row['fixed'] = json.loads(row.pop('fixed_json'))
            row['prediction'] = json.loads(row.pop('prediction_json'))
            row['context'] = json.loads(row.pop('context_json'))
            row.update(assist_source=None, assist_label=None, assist_confidence=None,
                       assist_evidence=None, assist_source_urls=[], assist_uncertainty='',
                       assist_manual_required=False, assist_id=None)
            row.update(assistance.get(row['pair_id'], {}))
            row['label_provenance'] = None
            if row['human_label'] is not None:
                event_id, event = latest_events.get(row['pair_id'], (None,{}))
                accepted = event.get('accepted_assist') if event.get('revision')==row['revision'] else None
                source = ({'assisted_prescreen':'pre_screen_assistance',
                           'source_researched':'source_researched_assistance'}.get(accepted['assist_source'])
                          if accepted else 'existing_human_approval')
                row['label_provenance'] = dict(source=source,event_id=event_id,
                    review_basis='assisted_not_individually_independent' if accepted else 'human_approval',
                    independently_hand_reviewed=False if accepted else None,
                    accepted_assist=accepted,reviewer=row['reviewer'],reviewed_on=row['reviewed_on'])
                if (event.get('revision')==row['revision'] and event.get('event_type')=='explanation_support_check'):
                    row['label_provenance'] = event['label_provenance_snapshot']
            row['review_status'] = ('human_approved' if row['human_label'] is not None else
                                    'manual_review_required' if row['assist_manual_required'] else
                                    'needs_human_acceptance' if row['assist_source'] else 'pending')
            if row['label_provenance'] and row['label_provenance']['accepted_assist']:
                row['review_status'] = 'assisted_label_applied'
            if row['unsupported_explanation'] is not None:
                row['unsupported_explanation'] = bool(row['unsupported_explanation'])
            result.append(row)
        return result

    def summary(self):
        rows, meta = self.rows(), self.metadata()
        missing_support = sum(row['prediction']['fit_state'] in ('direct_fit','supporting_fit')
                              and row['unsupported_explanation'] is None for row in rows)
        labelled = sum(row['human_label'] is not None for row in rows)
        stale = meta['fingerprints'] != self.current_fingerprints()
        return {'session_id':meta['session_id'], 'catalogue_version':meta['catalogue_version'],
                'method_version':meta['method_version'], 'total':len(rows), 'labelled':labelled,
                'pending':len(rows)-labelled, 'pending_explanation_checks':missing_support,
                'stale':stale, 'ready':labelled==len(rows) and missing_support==0 and not stale,
                'topics':[{'topic_id':topic,'name':output['canonical_topic'],
                           'total':sum(r['fixed']['topic_id']==topic for r in rows),
                           'labelled':sum(r['fixed']['topic_id']==topic and r['human_label'] is not None for r in rows)}
                          for topic,output in meta['outputs'].items()],
                'pairs':[{'pair_id':r['pair_id'],'topic_id':r['fixed']['topic_id'],
                          'product_name':r['prediction']['product_name'],
                          'predicted_fit_state':r['prediction']['fit_state'],
                          'human_label':r['human_label'],'revision':r['revision'],
                          **{key:r[key] for key in ('assist_source','assist_label','assist_confidence',
                              'assist_evidence','assist_source_urls','assist_uncertainty',
                              'assist_manual_required','assist_id','review_status','label_provenance')},
                          'pending_explanation':r['prediction']['fit_state'] in ('direct_fit','supporting_fit')
                              and r['unsupported_explanation'] is None} for r in rows]}

    def save(self, identifier, label, notes, support, revision, reviewer=None, reset=False):
        if self.metadata()['fingerprints'] != self.current_fingerprints():
            raise ReviewConflict('Source or method files changed. Keep this session; do not mix review versions.')
        if (not isinstance(label,str) or label not in GRADES) and not (reset and label is None):
            raise ValueError('Choose one of the four human fit labels')
        if not isinstance(identifier,str) or not identifier or len(identifier)>512:
            raise ValueError('A fixed pair ID is required')
        if not isinstance(notes,str) or len(notes)>1000:
            raise ValueError('Notes must be text of at most 1000 characters')
        if support is not None and type(support) is not bool:
            raise ValueError('Explanation support must be pending, supported or unsupported')
        if type(revision) is not int or revision<0:
            raise ValueError('A valid revision is required')
        if reviewer is not None and (not isinstance(reviewer,str) or len(reviewer)>80):
            raise ValueError('Reviewer must be text of at most 80 characters')
        if reset and (label is not None or notes or support is not None):
            raise ValueError('Reset must clear label, notes and explanation check together')
        stamp = datetime.now(timezone.utc).isoformat()
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            before = db.execute('SELECT * FROM labels WHERE pair_id=?',(identifier,)).fetchone()
            if before is None:
                raise KeyError('Unknown fixed review pair')
            if before['revision'] != revision:
                raise ReviewConflict('This pair changed in another tab. Reload before saving.')
            predicted = json.loads(db.execute('SELECT prediction_json FROM pairs WHERE pair_id=?',(identifier,)).fetchone()[0])
            if predicted['fit_state'] not in ('direct_fit','supporting_fit') and support is not None:
                raise ValueError('Explanation support is assessed only for predicted matches')
            db.execute('UPDATE labels SET human_label=?,notes=?,unsupported_explanation=?,reviewer=?,reviewed_on=?,revision=revision+1 '
                       'WHERE pair_id=?',(label,notes,support,reviewer,stamp,identifier))
            after = dict(db.execute('SELECT * FROM labels WHERE pair_id=?',(identifier,)).fetchone())
            db.execute('INSERT INTO events(pair_id,before_json,after_json,saved_at) VALUES (?,?,?,?)',
                       (identifier,encoded(dict(before)),encoded(after),stamp))
        return after

    def export(self):
        document = json.loads(encoded(self.metadata()['baseline']))
        by_id = {row['pair_id']:row for row in self.rows()}
        for fixed in document['rows']:
            current = by_id[pair_id(fixed)]
            for key in ('human_label','notes','unsupported_explanation','reviewer','reviewed_on'):
                fixed[key] = current[key]
            fixed['label_provenance'] = current['label_provenance']
        document['review_basis_notice'] = ('Labels may include user-authorized assistance. Inspect row label_provenance; '
                                          'assisted labels are not independently hand-reviewed gold.')
        return document

    def finalized_report(self):
        summary = self.summary()
        if not summary['ready']:
            return {'state':'pending','reason':'Complete all 256 human labels and separate predicted-match explanation checks; unchanged evidence/method required',
                    'progress':{key:summary[key] for key in ('labelled','pending','pending_explanation_checks','stale')},
                    'metrics':None,'recommendation':None}
        from .product_validation import validation_report
        meta = self.metadata()
        rows = self.rows()
        revision = fingerprint([{key:r[key] for key in ('pair_id','human_label','notes','unsupported_explanation','revision')} for r in rows])
        with self.connect() as db:
            cached = db.execute('SELECT report_json FROM reports WHERE revision_hash=?',(revision,)).fetchone()
            if cached:
                return json.loads(cached[0])
        report = validation_report(rows,meta)
        from collections import Counter
        report['label_provenance_summary'] = dict(Counter(
            row['label_provenance']['source'] for row in rows))
        if any(row['label_provenance']['accepted_assist'] for row in rows):
            report['limitations'].append('This review includes user-authorized assisted labels, not independently '
                                        'hand-reviewed gold; agreement metrics are descriptive and not independent validation.')
        report.update(revision_hash=revision,generated_at=datetime.now(timezone.utc).isoformat())
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            if meta['fingerprints'] != self.current_fingerprints():
                raise ReviewConflict('Source or method changed while generating report')
            current = [dict(r) for r in db.execute('SELECT pair_id,human_label,notes,unsupported_explanation,revision FROM labels ORDER BY pair_id')]
            for row in current:
                if row['unsupported_explanation'] is not None:
                    row['unsupported_explanation'] = bool(row['unsupported_explanation'])
            expected = sorted([{key:r[key] for key in ('pair_id','human_label','notes','unsupported_explanation','revision')} for r in rows],key=lambda r:r['pair_id'])
            if encoded(current) != encoded(expected):
                raise ReviewConflict('Labels changed while generating report; try again')
            db.execute('INSERT OR IGNORE INTO reports VALUES (?,?,?)',(revision,encoded(report),report['generated_at']))
        return report
