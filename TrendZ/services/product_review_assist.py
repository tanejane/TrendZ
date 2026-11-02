"""Review assistance is separate from immutable predictions and human judgments."""

import csv
import hashlib
import io
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

from .product_evaluation import GRADES
from .product_review import ReviewConflict, encoded, fingerprint, pair_id


def initialize(store):
    with store.connect() as db:
        db.executescript('''
            CREATE TABLE IF NOT EXISTS assist_imports (
                import_id TEXT PRIMARY KEY, manifest_json TEXT NOT NULL, imported_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS review_assists (
                pair_id TEXT PRIMARY KEY REFERENCES pairs(pair_id), assist_id TEXT NOT NULL,
                import_id TEXT NOT NULL REFERENCES assist_imports(import_id), assist_json TEXT NOT NULL
            );
            CREATE TRIGGER IF NOT EXISTS assists_no_update BEFORE UPDATE ON review_assists
                BEGIN SELECT RAISE(ABORT,'Review assistance is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS assists_no_delete BEFORE DELETE ON review_assists
                BEGIN SELECT RAISE(ABORT,'Review assistance is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS assist_imports_no_update BEFORE UPDATE ON assist_imports
                BEGIN SELECT RAISE(ABORT,'Assist import provenance is immutable'); END;
            CREATE TRIGGER IF NOT EXISTS assist_imports_no_delete BEFORE DELETE ON assist_imports
                BEGIN SELECT RAISE(ABORT,'Assist import provenance is immutable'); END;
        ''')


def records(store):
    with store.connect() as db:
        exists = db.execute("SELECT 1 FROM sqlite_master WHERE name='review_assists'").fetchone()
        if not exists:
            return {}
        return {row['pair_id']:dict(json.loads(row['assist_json']), assist_id=row['assist_id'],
                                    assist_import_id=row['import_id'])
                for row in db.execute('SELECT * FROM review_assists')}


def plan(store, prescreen, research):
    """Strict triple matching; no fuzzy names, sampling strata or prediction copying."""
    fixed = {row['pair_id']:row for row in store.rows()}
    catalogue_sources = json.loads((store.root/'data/products/catalogue.json').read_text(encoding='utf-8'))['sources']
    suggestions, inputs, checks = {}, [], {}
    for source, path in [('assisted_prescreen', prescreen), ('source_researched', research)]:
        path = Path(path)
        raw = path.read_bytes()
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'), newline='')))
        required = {'topic_id','query_id','product_id'} | (
            {'suggested_human_label','confidence','manual_review_recommended','reason'}
            if source=='assisted_prescreen' else
            {'proposed_human_label','confidence','evidence_summary','primary_source_url',
             'secondary_source_url','unresolved_uncertainty','needs_human_confirmation'})
        if not rows or not required.issubset(rows[0]):
            raise ValueError('Missing required CSV fields: '+source)
        seen, duplicates, unmatched, matched = set(), [], [], 0
        for row in rows:
            if any(not isinstance(row.get(field),str) for field in required):
                raise ValueError('Incomplete CSV row: '+source)
            identity = tuple(row[key] for key in ('topic_id','query_id','product_id'))
            identifier = pair_id(row)
            if identity in seen:
                duplicates.append(identity)
            seen.add(identity)
            current = fixed.get(identifier)
            if current is None or identity != tuple(current['fixed'][key] for key in ('topic_id','query_id','product_id')):
                unmatched.append(identity)
                continue
            matched += 1
            confidence = row['confidence']
            if confidence not in ('high','medium','low'):
                raise ValueError('Invalid assist confidence')
            if source=='assisted_prescreen':
                if row['manual_review_recommended'].lower() not in ('true','false'):
                    raise ValueError('Invalid manual-review flag')
                if row['manual_review_recommended'].lower()!='false' or confidence!='high':
                    continue
                label, evidence, urls, uncertainty = row['suggested_human_label'], row['reason'], [], ''
                source_id = current['prediction']['provenance']['product']['source_id']
                url = catalogue_sources.get(source_id,{}).get('url')
                urls = [url] if url else []
                uncertainty = 'Pre-screen suggestion; catalogue URL is provenance, not additional source-research verification.'
            else:
                if row['needs_human_confirmation'].lower()!='true':
                    raise ValueError('Research suggestions must require human confirmation')
                label, evidence = row['proposed_human_label'], row['evidence_summary']
                urls = list(dict.fromkeys(url for url in (row['primary_source_url'],row['secondary_source_url']) if url))
                uncertainty = row['unresolved_uncertainty']
                for url in urls:
                    parsed = urlsplit(url)
                    if parsed.scheme!='https' or not parsed.hostname or parsed.username or parsed.password:
                        raise ValueError('Assist source URL must be HTTPS without credentials')
            if label not in GRADES or not evidence.strip():
                raise ValueError('Assist label and evidence are required')
            if identifier in suggestions:
                raise ValueError('Overlapping assistance for the same strict pair ID')
            suggestions[identifier] = dict(assist_source=source, assist_label=label, assist_confidence=confidence,
                assist_evidence=evidence, assist_source_urls=urls, assist_uncertainty=uncertainty,
                assist_manual_required=confidence=='low')
        checks[source] = dict(rows=len(rows),matched=matched,duplicates=duplicates,unmatched=unmatched)
        inputs.append(dict(source=source,path=str(path.resolve()),sha256=hashlib.sha256(raw).hexdigest(),rows=rows))
    summary = dict(inputs=checks, rows_matched=len({pair_id(row) for item in inputs for row in item['rows']
                                                  if pair_id(row) in fixed}),
        already_human_labelled=sum(row['human_label'] is not None for row in fixed.values()),
        high_confidence_prescreen=sum(s['assist_source']=='assisted_prescreen' for s in suggestions.values()),
        research_assisted=sum(s['assist_source']=='source_researched' for s in suggestions.values()),
        research_accept_eligible=sum(s['assist_source']=='source_researched' and not s['assist_manual_required']
                                     and fixed[key]['human_label'] is None for key,s in suggestions.items()),
        low_confidence_pending=sum(s['assist_manual_required'] and fixed[key]['human_label'] is None
                                  for key,s in suggestions.items()),
        prescreen_accept_eligible=sum(s['assist_source']=='assisted_prescreen' and fixed[key]['human_label'] is None
                                    for key,s in suggestions.items()))
    if any(check['duplicates'] or check['unmatched'] for check in checks.values()):
        raise ValueError('CSV identity validation failed: '+encoded(summary))
    return summary, suggestions, inputs


def import_assists(store, prescreen, research, apply=False):
    summary, suggestions, inputs = plan(store,prescreen,research)
    summary['applied'] = False
    if not apply:
        return summary
    if store.metadata()['fingerprints'] != store.current_fingerprints():
        raise ReviewConflict('Source or method files changed; assistance import blocked')
    initialize(store)
    manifest = dict(inputs=inputs,session_id=store.metadata()['session_id'])
    import_id = fingerprint(manifest)
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        db.execute('INSERT OR IGNORE INTO assist_imports VALUES (?,?,?)',
                   (import_id,encoded(manifest),datetime.now(timezone.utc).isoformat()))
        for identifier, suggestion in suggestions.items():
            existing = db.execute('SELECT assist_id FROM review_assists WHERE pair_id=?',(identifier,)).fetchone()
            digest = fingerprint(suggestion)
            if existing and existing['assist_id']!=digest:
                raise ReviewConflict('Different assistance already exists; preserve its provenance')
            db.execute('INSERT OR IGNORE INTO review_assists VALUES (?,?,?,?)',
                       (identifier,digest,import_id,encoded(suggestion)))
    return dict(summary,applied=True,import_id=import_id)


def accept(store, approvals, topic=None, reviewer=None):
    """Explicit human action, atomic revision checks, never overwrite a saved label."""
    if store.metadata()['fingerprints'] != store.current_fingerprints():
        raise ReviewConflict('Source or method files changed')
    if not isinstance(approvals,list) or not 1<=len(approvals)<=32:
        raise ValueError('Select 1 to 32 approvals')
    if topic is not None and topic not in store.metadata()['outputs']:
        raise ValueError('Choose a fixed topic')
    if topic is None and len(approvals)!=1:
        raise ValueError('Single-pair acceptance requires exactly one approval')
    if reviewer is not None and (not isinstance(reviewer,str) or len(reviewer)>80):
        raise ValueError('Reviewer must be text of at most 80 characters')
    seen, accepted, skipped = set(), [], []
    with store.connect() as db:
        db.execute('BEGIN IMMEDIATE')
        for approval in approvals:
            if not isinstance(approval,dict) or set(approval)!={'pair_id','revision','assist_id'}:
                raise ValueError('Each approval needs pair ID, revision and assist ID')
            identifier = approval['pair_id']
            if not isinstance(identifier,str) or identifier in seen or type(approval['revision']) is not int:
                raise ValueError('Invalid or duplicate approval')
            seen.add(identifier)
            record = db.execute('SELECT labels.*,fixed_json,assist_json,assist_id,import_id FROM labels '
                                'JOIN pairs USING(pair_id) JOIN review_assists USING(pair_id) WHERE pair_id=?',
                                (identifier,)).fetchone()
            if record is None:
                raise KeyError('Unknown assisted pair')
            suggestion = json.loads(record['assist_json'])
            if topic is not None and (json.loads(record['fixed_json'])['topic_id']!=topic or
                                     suggestion['assist_source']!='assisted_prescreen' or
                                     suggestion['assist_confidence']!='high'):
                raise ValueError('Batch acceptance is only for high-confidence prescreen rows in one topic')
            if suggestion['assist_manual_required']:
                raise ValueError('Low-confidence evidence requires a manual label; quick acceptance is disabled')
            if record['human_label'] is not None:
                skipped.append(identifier)
                continue
            if record['revision']!=approval['revision'] or record['assist_id']!=approval['assist_id']:
                raise ReviewConflict('Review or assistance changed; reload before accepting')
            before = {key:record[key] for key in ('pair_id','human_label','notes','unsupported_explanation','reviewer','reviewed_on','revision')}
            stamp = datetime.now(timezone.utc).isoformat()
            db.execute('UPDATE labels SET human_label=?,reviewer=?,reviewed_on=?,revision=revision+1 WHERE pair_id=?',
                       (suggestion['assist_label'],reviewer,stamp,identifier))
            after = dict(db.execute('SELECT * FROM labels WHERE pair_id=?',(identifier,)).fetchone())
            after['accepted_assist'] = dict(suggestion,assist_id=record['assist_id'],import_id=record['import_id'])
            db.execute('INSERT INTO events(pair_id,before_json,after_json,saved_at) VALUES (?,?,?,?)',
                       (identifier,encoded(before),encoded(after),stamp))
            accepted.append(identifier)
    return dict(accepted=accepted,skipped_already_labelled=skipped)
