"""Apply only the 36 explicitly authorized deeper-pass high-confidence drafts."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.creator_review import CreatorReviewStore
from scripts.apply_creator_assists import apply_high, backup
from scripts.prepare_creator_assists import protected_hashes


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def apply_and_verify(store, pack, digest):
    before = {r['fixed']['unit_id']: r for r in store.records()}
    events_before = store.export()['revision_history']
    targets = {r['unit_id']: r for r in pack['rows'] if r['confidence'] == 'high'}
    result = apply_high(store, pack, digest)
    after = {r['fixed']['unit_id']: r for r in store.records()}
    for identifier, old in before.items():
        current = after[identifier]
        if old['fixed'] != current['fixed']:
            raise RuntimeError('Fixed evidence changed')
        if old['review']['human_label'] is not None or identifier not in targets:
            if old != current:
                raise RuntimeError('A protected existing or untargeted review changed')
            continue
        d = targets[identifier]; saved = current['review']
        expected = {'human_label': d['proposed_label'],
            'human_domains': d.get('proposed_domains', []),
            'human_specializations': d.get('proposed_specializations', []),
            'selected_video_ids': d['selected_video_ids'],
            'evidence_sufficiency': d['evidence_sufficiency'],
            'explanation_support': d['explanation_support'], 'review_basis': 'assisted_review'}
        if any(saved[k] != v for k, v in expected.items()):
            raise RuntimeError('Saved review differs from revised draft')
        if saved['revision'] != old['review']['revision'] + 1 or digest not in saved['notes']:
            raise RuntimeError('Missing revision/provenance')
    events_after = store.export()['revision_history']
    if events_after[:len(events_before)] != events_before:
        raise RuntimeError('Existing revision history changed')
    if len(events_after) != len(events_before) + len(result['applied']):
        raise RuntimeError('Revision history count mismatch')
    result.update(existing_saved_reviews_preserved=sum(r['review']['human_label'] is not None for r in before.values()),
        saved_fields_verified=True, prior_events_preserved=True)
    return result


def main():
    base = ROOT/'reports/phase5c'
    output = base/'deeper-application-v1'
    if output.exists():
        raise ValueError('Application artifacts already exist; inspect rather than replace them')
    original_path = base/'assists/preparation-v1/review_assists.json'
    deeper_path = base/'deeper-pass-v1/revised_suggestions.json'
    evidence_path = base/'deeper-pass-v1/supplemental_evidence.json'
    access_path = base/'deeper-pass-v1/public_access_log.json'
    original = json.loads(original_path.read_text(encoding='utf-8'))
    deeper = json.loads(deeper_path.read_text(encoding='utf-8'))
    revised = {r['unit_id']: r for r in deeper['rows']}
    expected = {r['unit_id'] for r in original['rows'] if r['confidence'] != 'high'}
    if len(revised) != 56 or set(revised) != expected or len(deeper['rows']) != 56:
        raise ValueError('Deeper pass must match the original 56 pending units exactly')
    if sum(r['confidence'] == 'high' for r in revised.values()) != 36:
        raise ValueError('Expected exactly 36 deeper-pass high-confidence suggestions')
    if any(deeper['summary'][k] != original[k] for k in ('session_id', 'source_sha256')):
        raise ValueError('Deeper-pass session/source mismatch')
    provenance = {'deeper_pass_sha256': sha(deeper_path), 'original_assist_sha256': sha(original_path),
        'supplemental_evidence_sha256': sha(evidence_path), 'public_access_log_sha256': sha(access_path),
        'deeper_pass_path': str(deeper_path.relative_to(ROOT)),
        'basis': 'User-authorized assisted application; no independent human gold or playback verification'}
    pack = {**original, 'method_version': 'creator-deeper-pass-application-v1', 'rows': []}
    for original_row in original['rows']:
        if original_row['unit_id'] not in revised:
            d = copy.deepcopy(original_row)
            d['confidence'] = 'excluded_existing_batch'
        else:
            d = copy.deepcopy(revised[original_row['unit_id']])
            d['reason'] += '\nDEEPER_PASS_PROVENANCE: ' + json.dumps({**provenance,
                'original_confidence': d['original_confidence'],
                'original_suggested_label': d['original_suggested_label'],
                'unresolved_uncertainty': d['unresolved_uncertainty'],
                'assist_source': d['assist_source']}, ensure_ascii=True, sort_keys=True)
        pack['rows'].append(d)
    raw = json.dumps(pack, ensure_ascii=True, sort_keys=True).encode()
    digest = hashlib.sha256(raw).hexdigest()
    database = ROOT/'data/creators/review_sessions/local.sqlite3'
    protected = protected_hashes(ROOT, database)
    protected.pop(str(database.relative_to(ROOT)))
    for path in list((ROOT/'services').rglob('*.py')) + [ROOT/'app_backend.py']:
        if path.is_file(): protected[str(path.relative_to(ROOT))] = sha(path)
    with tempfile.TemporaryDirectory() as temp:
        clone = Path(temp)/'preflight.sqlite3'; backup(database, clone)
        preflight = apply_and_verify(CreatorReviewStore(clone), pack, digest)
    output.mkdir(parents=True)
    backup(database, output/'session_before.sqlite3')
    (output/'application_input.json').write_bytes(raw)
    store = CreatorReviewStore(database)
    result = apply_and_verify(store, pack, digest)
    if any(sha(ROOT/path) != value for path, value in protected.items()):
        raise RuntimeError('Protected source or logic changed during application')
    pending = [{k: r['fixed'][k] for k in ('unit_id', 'unit_type', 'creator_id', 'display_name', 'topic_id')}
               for r in store.records() if r['review']['human_label'] is None]
    result.update(progress=store.summary(), pending_rows=pending, provenance=provenance,
        application_input_sha256=digest, protected_files_unchanged=True, protected_sha256=protected,
        evaluation_generated=False, preflight_applied_count=len(preflight['applied']))
    (output/'application.json').write_text(json.dumps(result, indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    (output/'session_after.json').write_text(json.dumps(store.export(), indent=2, ensure_ascii=True)+'\n', encoding='utf-8')
    print(json.dumps({'applied': len(result['applied']), 'previous_saved_preserved': result['existing_saved_reviews_preserved'],
        'progress': result['progress']['by_type'], 'pending': len(pending),
        'protected_files_unchanged': True, 'evaluation_generated': False}))


if __name__ == '__main__': main()
