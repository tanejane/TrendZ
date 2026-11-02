"""Explicit user-authorized application of high-confidence assistance only."""
import argparse
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.creator_review import CreatorReviewStore, CreatorReviewConflict, fingerprint
from scripts.prepare_creator_assists import protected_hashes


def apply_high(store, pack, pack_sha256):
    metadata = store.metadata()
    if any(metadata[k] != pack[k] for k in ('session_id', 'source_sha256')):
        raise ValueError('Assistance session/source mismatch')
    records = {r['fixed']['unit_id']: r for r in store.records()}
    identifiers = [r['unit_id'] for r in pack['rows']]
    if len(identifiers) != len(set(identifiers)) or set(identifiers) != set(records):
        raise ValueError('Drafts must match fixed session units exactly')
    plan, skipped = [], []
    for draft in pack['rows']:
        if draft['confidence'] != 'high':
            continue
        record = records[draft['unit_id']]
        if fingerprint(record['fixed']) != draft['fixed_unit_sha256']:
            raise ValueError('Fixed evidence mismatch: ' + draft['unit_id'])
        if record['review']['human_label'] is not None:
            skipped.append({'unit_id': draft['unit_id'], 'reason': 'Existing saved label preserved'})
            continue
        if (fingerprint(record['review']) != draft['existing_review_sha256'] or
                record['review']['revision'] != draft['based_on_revision']):
            raise CreatorReviewConflict('Pending review changed since draft: ' + draft['unit_id'])
        if draft['review_basis'] != 'assisted_review' or draft['review_status'] != 'needs_human_acceptance':
            raise ValueError('Unsupported assistance provenance')
        provenance = {k: draft[k] for k in ('reason', 'explanation_reason', 'confidence',
            'source_sha256', 'fixed_unit_sha256', 'explanation_audit_target_sha256',
            'based_on_revision', 'existing_review_sha256', 'selected_video_ids',
            'selected_previously_approved_video_ids')}
        provenance['proxy_video_ids'] = draft.get('proxy_video_ids', [])
        provenance.update(assist_pack_sha256=pack_sha256, assist_method=pack['method_version'],
            authority='User explicitly requested application of high-confidence suggestions',
            not_independent_human_gold=True, video_relevance_basis='Assisted approval of selected metadata evidence; no new playback verification')
        payload = {'unit_id': draft['unit_id'], 'revision': record['review']['revision'],
            'human_label': draft['proposed_label'],
            'human_domains': draft.get('proposed_domains', []),
            'human_specializations': draft.get('proposed_specializations', []),
            'selected_video_ids': draft['selected_video_ids'],
            'evidence_sufficiency': draft['evidence_sufficiency'],
            'explanation_support': draft['explanation_support'], 'review_basis': 'assisted_review',
            'reviewer': 'Codex assisted application (user-authorized)',
            'notes': 'USER-AUTHORIZED ASSISTED REVIEW; NOT INDEPENDENT HUMAN GOLD.\n' + json.dumps(provenance, ensure_ascii=True, sort_keys=True)}
        plan.append(payload)
    applied = []
    for payload in plan:
        saved = store.save(payload)
        applied.append({'unit_id': payload['unit_id'], 'label': saved['human_label'],
                        'revision': saved['revision'], 'review_basis': saved['review_basis']})
    return {'applied': applied, 'preserved_existing': skipped,
            'medium_low_written': 0, 'independent_human_gold': False}


def backup(source, target):
    reader = sqlite3.connect(Path(source).resolve().as_uri() + '?mode=ro', uri=True)
    writer = sqlite3.connect(target)
    try:
        reader.backup(writer)
    finally:
        writer.close(); reader.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'data/creators/review_sessions/local.sqlite3')
    parser.add_argument('--pack', type=Path, default=ROOT/'reports/phase5c/assists/preparation-v1/review_assists.json')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/phase5c/assisted-application-v1')
    parser.add_argument('--apply-high-confidence', action='store_true', required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new output directory; do not replace prior application history')
    raw = args.pack.read_bytes(); pack = json.loads(raw)
    digest = hashlib.sha256(raw).hexdigest()
    if sum(r['confidence'] == 'high' for r in pack['rows']) != 48:
        raise ValueError('This authorized batch must contain exactly 48 high-confidence drafts')
    with tempfile.TemporaryDirectory() as temp:
        clone = Path(temp)/'preflight.sqlite3'; backup(args.database, clone)
        apply_high(CreatorReviewStore(clone), pack, digest)
    args.output.mkdir(parents=True)
    backup(args.database, args.output/'session_before.sqlite3')
    protected = protected_hashes(ROOT, args.database)
    db_key = str(args.database.resolve().relative_to(ROOT))
    protected.pop(db_key)
    store = CreatorReviewStore(args.database)
    result = apply_high(store, pack, digest)
    after = protected_hashes(ROOT, args.database); after.pop(db_key)
    result.update(session_id=store.metadata()['session_id'], assist_pack_sha256=digest,
        progress=store.summary(), protected_evidence_unchanged=protected == after,
        protected_sha256=protected, evaluation_generated=False)
    (args.output/'application.json').write_text(json.dumps(result, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    (args.output/'session_after.json').write_text(json.dumps(store.export(), indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    print(json.dumps({'applied': len(result['applied']), 'preserved_existing': len(result['preserved_existing']),
        'progress': result['progress']['by_type'], 'protected_evidence_unchanged': result['protected_evidence_unchanged'],
        'evaluation_generated': False}))


if __name__ == '__main__':
    main()
