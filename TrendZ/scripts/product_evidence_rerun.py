"""Evidence-only Product Fit v1 rerun; never writes the original catalogue/review DB."""
import argparse
import copy
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.product_catalogue import Catalogue
from services.product_fit import ProductFit, METHOD
from services.product_validation import analyze
from services.product_review import fingerprint

RULE_FILES = ('services/product_fit.py','services/product_catalogue.py','services/product_evaluation.py',
              'services/product_validation.py','data/product_intents.json','data/tracked_topics.json')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_method_freeze(actual,expected):
    if actual!=expected:
        raise ValueError('Frozen Product Fit v1 method differs; a new independent holdout is required before semantic changes')


def render_report(result):
    def number(value):
        return 'Unavailable' if value is None else f'{value:.4f}'
    lines = ['# Phase 4D-lite: Catalogue Evidence Hardening','',
        '**Evidence-only rerun. Product Fit v1 semantics are frozen and unchanged.**','',
        f"Original catalogue: `{result['original_catalogue_version']}`. Hardened snapshot: `{result['hardened_catalogue_version']}`.",
        '', 'The same 256 Phase 4C reviewed labels and family-disjoint dev/evaluation assignments were reused without edits. These are mixed human/assisted labels, not a new independent holdout. Source decisions were fixed before the rerun; evidence was not selected to match evaluation labels.',
        '', '## Source Decisions','',
        '- HA 30ml: face established by the exact Malaysian product heading. HA 15ml: face retained as partial, explicitly linked MY size-family evidence (reciprocal selectors, same B242774/1 formula). No neck area was added.',
        '- MELA B3: face, neck and upper chest established by MY indexed serum directions; serum-specific Malaysian retailer directions corroborate face/neck. No ingredient or benefit field was broadened.',
        '- Oil Control: MY use section still does not name an application area. Regional face/neck guidance is logged but not promoted; the field remains unknown.',
        '- Hyalu B5: current formula identity could not be reconciled. Raw/normalized ingredient fields are explicitly conflicted and withheld; original observed values remain in unresolved_fields. Published manufacturer-benefit language is retained only as attributed claims, not efficacy or a resolved formula.',
        '- Existing face/neck or face directions for Water Night Cream, Aura Day/Night and Glycolic Peel were rechecked without changing them.',
        '- Pink Oil quarantine and all its evidence fields are preserved; only the new catalogue-version stamp differs.',
        '', '## Overall Comparison','',
        '| Metric | Phase 4C | Evidence cleanup | Delta |','| --- | ---: | ---: | ---: |']
    before,after = result['before']['overall'],result['after']['overall']
    for metric in ('precision_at_5','ndcg_at_5','catalogue_bounded_recall'):
        a,b = before['macro_ranking'][metric],after['macro_ranking'][metric]
        lines.append(f'| Macro {metric} | {number(a)} | {number(b)} | {b-a:+.4f} |')
    for name in ('false_positive_count','false_negative_count','abstention_rate'):
        a,b = before[name],after[name]
        lines.append(f'| {name} | {number(a)} | {number(b)} | {b-a:+.4f} |')
    lines += [f"| Unsupported explanation rate | {number(before['unsupported_match_rate'])} | Unavailable: re-audit pending | Not comparable |",'',
        'Ranking gains come solely from the evidence snapshot; method hashes are identical. Abstentions fall from 20/256 to 14/256, despite four additional conservative B5 ingredient-topic abstentions after conflicting formula fields were withheld.',
        '', '## Dev / Evaluation Separately','',
        '| Split | Metric | Before | After |','| --- | --- | ---: | ---: |']
    for split in ('dev','evaluation'):
        for metric in ('precision_at_5','ndcg_at_5','catalogue_bounded_recall'):
            a = result['before']['by_split'][split]['macro_ranking'][metric]
            b = result['after']['by_split'][split]['macro_ranking'][metric]
            lines.append(f'| {split} | Macro {metric} | {number(a)} | {number(b)} |')
        for metric in ('false_positive_count','false_negative_count','abstention_rate'):
            lines.append(f"| {split} | {metric} | {number(result['before']['by_split'][split][metric])} | {number(result['after']['by_split'][split][metric])} |")
    lines += ['', 'Undefined topic nDCG/recall are excluded from macro averages: dev has four defined positive topics and evaluation seven, unchanged from Phase 4C. P@5 retains the original denominator of five. Gains occur in evaluation; they are descriptive evidence-cleanup effects, not independent generalization or authorization to tune semantic rules.',
        '', '## Per-topic Ranking','',
        '| Topic | P@5 before / after | nDCG before / after | Recall before / after | FN before / after |',
        '| --- | ---: | ---: | ---: | ---: |']
    for topic in result['after']['by_topic']:
        a,b = result['before']['by_topic'][topic],result['after']['by_topic'][topic]
        ra,rb = a['ranking_by_topic'][topic],b['ranking_by_topic'][topic]
        values = [f"{number(ra[key])} / {number(rb[key])}" for key in ('precision_at_5','ndcg_at_5','catalogue_bounded_recall')]
        lines.append('| '+' | '.join([topic,*values,f"{a['false_negative_count']} / {b['false_negative_count']}"])+' |')
    lines += ['', '## Exact Prediction-state Changes','',
        '| Pair | Split | Before | After | Unchanged reviewed label |','| --- | --- | --- | --- | --- |']
    for row in result['transitions']:
        lines.append('| '+' | '.join([row['pair_id'],row['split'],row['before'],row['after'],row['reviewed_label']])+' |')
    lines += ['', 'The HA niacinamide decisions change from abstention to no_fit because the complete published HA list does not include niacinamide. Their preserved direct_fit review labels are therefore questionable evidence/scope judgments, not targets for ingredient fabrication. The existing Aura Night serum-vs-cream discrepancy and Deepavali format restrictions also remain untouched.',
        '', '## Explanation-support Boundary','',
        f"{len(result['explanation_support']['pending_pairs'])} newly returned or changed explanations require fresh checks. Phase 4C audit booleans are carried only when explanation content is identical apart from version/timestamp metadata. Old failed B5 explanations have changed, not been declared fixed. Overall post-cleanup unsupported rate remains unavailable until these are checked.",
        '', *['- `'+identifier+'`' for identifier in result['explanation_support']['pending_pairs']],
        '', '## Reproduction and Freeze','',
        'Run `.\\.venv\\Scripts\\python.exe scripts\\product_evidence_rerun.py` from the repository. The command verifies original Phase 4C fingerprints, reproduces its metrics exactly, uses the existing ProductFit(Catalogue(path)) interface and existing analyze/ranking functions, and refuses to overwrite different frozen outputs.',
        '', 'See product_fit_v1_freeze.json for method, intent, evaluator, catalogue, frozen-review and original DB hashes. Reruns enforce the method hash lock. Future semantic changes require a new independently adjudicated holdout showing a genuine rule problem; none were made here.',
        '', '## Deployment and Limitations','',result['deployment'],
        '', 'The hardened snapshot is an explicit backend rerun artifact, not an automatic change to the current website. This preserves the completed Phase 4C session without making its provenance stale.',
        '', *['- '+limitation for limitation in result['limitations']],
        '- Source verification records page statements, not clinical truth, package inspection or live stock.',
        '', 'Source URLs, retrieval scope and partial/unresolved decisions are in source_verification.json; all metrics, matrices and field transitions are in rerun.json.']
    return '\n'.join(lines)+'\n'


def harden(baseline, manifest):
    """Materialize only source-reviewed fields; review labels are deliberately not accepted."""
    if baseline['catalogue_version']!=manifest['baseline_catalogue_version']:
        raise ValueError('Evidence manifest belongs to a different baseline catalogue')
    result = copy.deepcopy(baseline)
    result.update(catalogue_version=manifest['catalogue_version'],verified_on=manifest['verified_on'],
                  evidence_parent_version=baseline['catalogue_version'])
    products = {product['product_id']:product for product in result['products']}
    if len(products)!=len(result['products']):
        raise ValueError('Duplicate catalogue product IDs')
    for identifier,source in manifest['sources'].items():
        if identifier in result['sources'] or not source['url'].startswith('https://'):
            raise ValueError('New source IDs and HTTPS URLs required')
        result['sources'][identifier] = dict(source,verified_on=manifest['verified_on'],
            timestamp_precision='day',retrieved_at=manifest['retrieved_at'])
    seen = set()
    for update in manifest['application_updates']:
        product = products[update['product_id']]
        if product['product_id'] in seen or product['application_area'] is not None:
            raise ValueError('Application updates must uniquely target missing fields')
        seen.add(product['product_id'])
        if update['state'] not in ('verified','partial') or not update['value']:
            raise ValueError('Application evidence must declare its actual scope')
        evidence = []
        for source_id in update['source_ids']:
            source = result['sources'][source_id]
            if source['source_type'] not in ('official_my_brand','my_retailer'):
                raise ValueError('Regional sources cannot establish MY application fields')
            evidence.append(dict(source_id=source_id,basis=update['basis']))
        product['application_area'] = update['value']
        product['field_quality']['application_area'] = dict(state=update['state'],
            reason=None if update['state']=='verified' else update['basis'],evidence=evidence)
        product['quality_warnings'] = [warning for warning in product['quality_warnings']
            if 'application area' not in warning.lower()]
        if update['state']=='partial':
            product['quality_warnings'].append('Application area uses explicitly linked MY size-family corroboration, not standalone 15ml directions')
        if product['product_id']=='lrp-mela-30ml':
            product['quality_warnings'].append('MY indexed application directions retained; current package unverified; retinyl palmitate is not retinol')
        product['verified_on'] = manifest['verified_on']
    unresolved = manifest['unresolved_application']
    product = products[unresolved['product_id']]
    if product['application_area'] is not None:
        raise ValueError('Do not overwrite an existing application field as missing')
    product['field_quality']['application_area']['reason'] = unresolved['reason']
    product['unresolved_fields'] = {'application_area':dict(reason=unresolved['reason'],
                                                          checked_source_ids=unresolved['source_ids'])}
    for identifier in manifest['formula_conflicts']:
        product = products[identifier]
        product['unresolved_fields'] = {'formula_identity':dict(state='unresolved',source_id='b5-my-4d',
            conflict='Alcohol-free wording versus ALCOHOL DENAT in the same new-formula PDP',
            observed_raw_ingredients=product['raw_ingredients'],
            observed_normalized_ingredients=product['normalized_ingredients'])}
        for field in ('raw_ingredients','normalized_ingredients'):
            product[field] = None
            product['field_quality'][field] = dict(state='conflicted',
                reason='Current formula identity unresolved; observed source list retained separately, not asserted as verified formula',
                evidence=[dict(source_id='b5-my-4d',basis='Same MY PDP contains contradictory formula claims')])
        product['ingredient_completeness'] = 'unknown'
        product['quality_warnings'].append('Current formula identity unresolved; ingredient fields withheld. Benefit language remains source-declared, not verified efficacy.')
        product['verified_on'] = manifest['verified_on']
    for check in manifest['confirmed_without_change']:
        if products[check['product_id']]['application_area']!=check['application_area']:
            raise ValueError('Confirmed existing application differs from source check')
    for product in result['products']:
        product['catalogue_version'] = result['catalogue_version']
    original = {product['product_id']:product for product in baseline['products']}
    for identifier in manifest['preserve_quarantine']:
        clean = copy.deepcopy(products[identifier]); clean['catalogue_version'] = baseline['catalogue_version']
        if clean!=original[identifier] or not clean['requires_review']:
            raise ValueError('Pink Oil quarantine must be preserved verbatim except catalogue stamp')
    return result


def explanation_signature(prediction):
    """Ignore version stamps only; changed facts, sources, caveats or warnings need re-audit."""
    def content(value):
        if isinstance(value,dict):
            return {key:content(item) for key,item in value.items() if key not in ('catalogue_version','verified_on','retrieved_at')}
        if isinstance(value,list):
            return [content(item) for item in value]
        return value
    return fingerprint(content({key:prediction[key] for key in
        ('fit_state','dimensions','supporting_evidence','missing_evidence','contradictions','warnings')}))


def evaluate_rerun(original, outputs):
    """Reuse labels/splits, not support judgments for new or changed explanations."""
    rebuilt, pending, transitions = [], [], []
    for row in original:
        current = copy.deepcopy(row)
        topic = row['fixed']['topic_id']
        current['prediction'] = next(p for p in outputs[topic]['assessments'] if p['product_id']==row['fixed']['product_id'])
        before,after = row['prediction'],current['prediction']
        if before['fit_state']!=after['fit_state']:
            transitions.append(dict(pair_id=row['pair_id'],before=before['fit_state'],after=after['fit_state'],
                split=row['fixed']['split'],reviewed_label=row['human_label'],
                missing_before=before['missing_evidence'],missing_after=after['missing_evidence']))
        if after['fit_state'] in ('direct_fit','supporting_fit'):
            if explanation_signature(before)!=explanation_signature(after) or before['fit_state'] not in ('direct_fit','supporting_fit'):
                current['unsupported_explanation'] = None
                pending.append(row['pair_id'])
        else:
            current['unsupported_explanation'] = None
        rebuilt.append(current)
    metrics = dict(overall=analyze(rebuilt,outputs),
        by_split={split:analyze([r for r in rebuilt if r['fixed']['split']==split],outputs) for split in ('dev','evaluation')},
        by_topic={topic:analyze([r for r in rebuilt if r['fixed']['topic_id']==topic],outputs) for topic in outputs})
    return metrics,pending,transitions


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=ROOT/'reports/phase4d-lite')
    args = parser.parse_args()
    args.output.mkdir(parents=True,exist_ok=True)
    manifest_path = ROOT/'data/products/evidence_hardening_v1.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    baseline_path = ROOT/'data/products/catalogue.json'
    baseline = json.loads(baseline_path.read_text(encoding='utf-8'))
    rules = {name:sha(ROOT/name) for name in RULE_FILES}
    freeze_path = args.output/'product_fit_v1_freeze.json'
    if freeze_path.exists():
        verify_method_freeze(rules,json.loads(freeze_path.read_text(encoding='utf-8'))['rule_sha256'])
    audit = json.loads((ROOT/'reports/phase4c/explanation_support_audit.json').read_text(encoding='utf-8'))
    for name,digest in audit['protected_hashes'].items():
        if sha(ROOT/name)!=digest:
            raise ValueError('Original Phase 4C evidence/evaluator changed: '+name)
    baseline_report_path = ROOT/'reports/phase4c/validation-fef15bfe98946a1700eb-4d8b138671fd.json'
    baseline_report = json.loads(baseline_report_path.read_text(encoding='utf-8'))
    for name,digest in baseline_report['fingerprints'].items():
        if sha(ROOT/name)!=digest:
            raise ValueError('Phase 4C baseline or rules changed: '+name)
    review_path = ROOT/'reports/phase4c/final_review_export.json'
    reviewed = json.loads(review_path.read_text(encoding='utf-8'))
    fixed = { '/'.join(row[key] for key in ('topic_id','query_id','product_id')):row for row in reviewed['rows'] }
    if len(fixed)!=256 or any(row['human_label'] is None for row in fixed.values()):
        raise ValueError('Exactly 256 frozen reviewed pairs required')
    database = ROOT/'data/products/review_sessions/local.sqlite3'
    review_db_hash = sha(database)
    with sqlite3.connect(database.resolve().as_uri()+'?mode=ro',uri=True) as db:
        meta = json.loads(db.execute("SELECT value FROM metadata WHERE key='session'").fetchone()[0])
        original = []
        for identifier,fixed_json,prediction_json,context_json in db.execute('SELECT pair_id,fixed_json,prediction_json,context_json FROM pairs ORDER BY position'):
            label = fixed[identifier]
            current = dict(pair_id=identifier,fixed=json.loads(fixed_json),prediction=json.loads(prediction_json),context=json.loads(context_json),
                           human_label=label['human_label'],notes=label.get('notes') or '',unsupported_explanation=label['unsupported_explanation'])
            for key in ('topic_id','query_id','product_id','family_id','split'):
                if current['fixed'][key]!=label[key]:
                    raise ValueError('Frozen review identity/split mismatch')
            original.append(current)
    before = dict(overall=analyze(original,meta['outputs']),by_split=baseline_report['by_split'],by_topic=baseline_report['by_topic'])
    if before['overall']!=baseline_report['metrics']:
        raise ValueError('Frozen Phase 4C metrics cannot be reproduced exactly')
    hardened = harden(baseline,manifest)
    hardened_path = args.output/'catalogue_hardened_v1.json'
    def write(path,value):
        serialized = json.dumps(value,indent=2,ensure_ascii=True)+'\n'
        if path.exists() and path.read_text(encoding='utf-8')!=serialized:
            raise ValueError('Refusing to overwrite a different frozen artifact: '+str(path))
        path.write_text(serialized,encoding='utf-8')
    write(hardened_path,hardened)
    service = ProductFit(Catalogue(hardened_path))
    outputs = {topic:service.topic(topic) for topic in service.intents['topics']}
    after,pending,transitions = evaluate_rerun(original,outputs)
    for row in original:
        product = next(p for p in service.catalogue.products if p['product_id']==row['fixed']['product_id'])
        if product['family_id']!=row['fixed']['family_id']:
            raise ValueError('Family identity changed')
    source_changes = []
    for previous,current in zip(baseline['products'],hardened['products']):
        fields = [key for key in current if key!='catalogue_version' and previous.get(key)!=current[key]]
        if fields:
            source_changes.append(dict(product_id=current['product_id'],changed_fields=fields))
    result = dict(state='evidence_only_rerun_complete',method_version=METHOD,independent_validation=False,
        original_catalogue_version=baseline['catalogue_version'],hardened_catalogue_version=hardened['catalogue_version'],
        semantic_method_changed=False,labels_changed=False,splits_changed=False,
        intervention='Evidence decisions frozen before rerun; no semantic rule, allowlist, threshold or ranking changes.',
        review_transfer='Same 256 Phase 4C decisions/provenance, explicitly reused across catalogue versions, not relabelled as fresh gold.',
        before=before,after=after,transitions=transitions,catalogue_field_changes=source_changes,
        explanation_support=dict(state='requires_reaudit' if pending else 'available',pending_pairs=pending,
            before_rate=before['overall']['unsupported_match_rate'],after_rate=after['overall']['unsupported_match_rate'],
            reason='New/changed explanations do not inherit Phase 4C support labels. No support improvement is claimed from dropping or changing evidence.'),
        preserved_pink_quarantine=manifest['preserve_quarantine'],
        deployment='Isolated hardened catalogue snapshot used by explicit ProductFit(Catalogue(path)); existing app/default catalogue and original review session remain on Phase 4C evidence.',
        limitations=['Descriptive comparison against assisted labels, not a new independent holdout.',
                    'HA15 facial area is partial linked-family evidence, not standalone directions.',
                    'Oil Control MY application area and B5 formula identity remain unresolved.',
                    'No new fit-score formula, classifier or recommendation added.'])
    write(args.output/'rerun.json',result)
    write(args.output/'predictions_after.json',outputs)
    write(args.output/'source_verification.json',manifest)
    freeze = dict(status='frozen',method_version=METHOD,policy='Do not change Product Fit v1 semantics without a new independent holdout demonstrating a genuine rule problem.',
        rule_sha256=rules,manifest_sha256=sha(manifest_path),baseline_catalogue_sha256=sha(baseline_path),
        hardened_catalogue_sha256=sha(hardened_path),frozen_review_sha256=sha(review_path),
        original_review_db_sha256=review_db_hash,baseline_report_sha256=sha(baseline_report_path))
    write(args.output/'product_fit_v1_freeze.json',freeze)
    compact = dict(method_version=METHOD,semantic_method_changed=False,independent_validation=False,
        before_catalogue=baseline['catalogue_version'],after_catalogue=hardened['catalogue_version'],
        overall={name:{**data['overall']['macro_ranking'],
            'false_positives':data['overall']['false_positive_count'],'false_negatives':data['overall']['false_negative_count'],
            'abstention_rate':data['overall']['abstention_rate'],'unsupported_rate':data['overall']['unsupported_match_rate']}
            for name,data in (('before',before),('after',after))},
        by_split={split:{name:data['by_split'][split]['macro_ranking'] for name,data in (('before',before),('after',after))}
                  for split in ('dev','evaluation')},
        pending_explanation_reaudits=len(pending),live_catalogue_changed=False)
    write(args.output/'metrics_summary.json',compact)
    markdown = render_report(result)
    report_path = args.output/'comparison.md'
    if report_path.exists() and report_path.read_text(encoding='utf-8')!=markdown:
        raise ValueError('Refusing to overwrite different frozen comparison')
    report_path.write_text(markdown,encoding='utf-8')
    if sha(database)!=review_db_hash or {name:sha(ROOT/name) for name in RULE_FILES}!=rules:
        raise ValueError('Protected review or rules changed during rerun')
    print(json.dumps(dict(before=before['overall']['macro_ranking'],after=after['overall']['macro_ranking'],
        false_negatives=[before['overall']['false_negative_count'],after['overall']['false_negative_count']],
        abstentions=[before['overall']['abstention_rate'],after['overall']['abstention_rate']],
        changed_pairs=len(transitions),pending_explanation_checks=len(pending)),indent=2))


if __name__=='__main__':
    main()
