"""Export separate assisted drafts. Opens the fixed review database in read-only mode."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.creator_review_assists import prepare_pack, markdown_pack
from scripts.phase5c_assist_decisions import author_decisions


def read_session(path):
    db = sqlite3.connect(Path(path).resolve().as_uri() + '?mode=ro', uri=True)
    try:
        db.execute('BEGIN')
        session = json.loads(db.execute("SELECT payload FROM metadata WHERE key='session'").fetchone()[0])
        records = [{'fixed': json.loads(f), 'review': json.loads(r)} for f, r in db.execute(
            'SELECT units.payload,reviews.payload FROM units JOIN reviews USING(unit_id) ORDER BY unit_id')]
        counts = {t: db.execute('SELECT COUNT(*) FROM ' + t).fetchone()[0]
                  for t in ('units', 'reviews', 'events', 'reports')}
        return session, records, counts
    finally:
        db.close()


def protected_hashes(root, review_db):
    paths = {Path(review_db).resolve(), root/'reports/phase2-measured/pilot.sqlite3',
             root/'services/creator_review.py', root/'services/creator_review_evaluation.py',
             root/'data/creator_evidence_v1.json'}
    paths.update((root/'services').glob('product*.py'))
    paths.update((root/'services').glob('creator_analysis*.py'))
    for name in ('data/products', 'reports/phase4b', 'reports/phase4c',
                 'reports/phase4d-lite', 'reports/phase5b/live-initial'):
        paths.update(p for p in (root/name).rglob('*') if p.is_file())
    return {str(p.relative_to(root)) if p.is_relative_to(root) else str(p):
            hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths) if p.is_file()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'data/creators/review_sessions/local.sqlite3')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/phase5c/assists/preparation-v1')
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        raise ValueError('Use a new output directory; existing assistance is not overwritten')
    before = protected_hashes(ROOT, args.database)
    session, records, table_counts = read_session(args.database)
    source = Path(session['source_path'])
    if hashlib.sha256(source.read_bytes()).hexdigest() != session['source_sha256']:
        raise ValueError('Pinned Phase 5B source changed')
    decisions = author_decisions(records)
    pack = prepare_pack(session, records, decisions)
    after = protected_hashes(ROOT, args.database)
    if before != after:
        raise ValueError('Protected data changed during preparation; retry against a stable session')
    output.mkdir(parents=True)
    def write(name, value):
        with (output/name).open('x', encoding='utf-8', newline='\n') as handle:
            handle.write(value if isinstance(value, str) else json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False)+'\n')
    write('decisions.json', decisions)
    write('review_assists.json', pack)
    for kind in ('profile', 'affinity'):
        write(kind+'_suggestions.json', {**{k: v for k, v in pack.items() if k != 'rows'},
                                       'rows': [r for r in pack['rows'] if r['unit_type'] == kind]})
    write('REVIEW_DRAFTS.md', markdown_pack(pack))
    write('verification.json', {'session_id': session['session_id'],
        'confidence_counts': pack['confidence_counts'], 'fixed_unit_count': len(records),
        'human_labels_before': sum(r['review']['human_label'] is not None for r in records),
        'human_labels_written': 0, 'table_counts': table_counts,
        'protected_files_unchanged': before == after, 'protected_sha256': before,
        'deeper_manual_units': [r['unit_id'] for r in pack['rows'] if r['deeper_manual_review_required']],
        'all_rows_need_human_acceptance': True})
    print(json.dumps({'output': str(output), 'confidence_counts': pack['confidence_counts'],
                      'human_labels_written': 0, 'protected_files_unchanged': True}))


if __name__ == '__main__':
    main()
