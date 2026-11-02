"""Reproduce approved H1 prototype counts and API examples without altering inputs."""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from services.creator_candidates import CreatorCandidates, PINS, SEALED
from services.creator_candidate_policy import STATE_ORDER


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/phase5e/implementation-v1')
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('Use a new output directory')
    service = CreatorCandidates(ROOT)
    protected = list(SEALED) + ['data/creators/review_sessions/local.sqlite3', 'data/products/review_sessions/local.sqlite3']
    protected += list(json.loads((ROOT / 'reports/phase4d-lite/product_fit_v1_freeze.json').read_text())['rule_sha256'])
    digest = lambda: {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in protected}
    before = digest()
    positive, all_contexts, by_topic = Counter(), Counter(), {}
    examples = []
    for topic_id, topic in service.products.items():
        topic_counts = Counter()
        for product in topic['assessments']:
            params = {**PINS, 'topic_id': topic_id, 'query_id': 'canonical', 'market': 'MY', 'product_id': product['product_id']}
            result = service.query(params)
            all_contexts.update(result['counts'])
            if product['fit_state'] in ('direct_fit', 'supporting_fit'):
                positive.update(result['counts'])
                topic_counts.update(result['counts'])
                if not any(e['request']['topic_id'] == topic_id for e in examples):
                    examples.append({'request': params, 'response': result})
        by_topic[topic_id] = {state: topic_counts[state] for state in STATE_ORDER}
    if before != digest():
        raise ValueError('Protected input changed')
    report = {'pins': PINS, 'policy_status': 'approved_prototype_not_independent_validation',
              'positive_product_context_counts': dict(positive), 'all_product_context_counts': dict(all_contexts),
              'by_topic_positive_contexts': by_topic, 'independent_gold': False,
              'review_basis': {'assisted_review': 102, 'human_evidence_review': 2},
              'protected_sha256': before, 'protected_inputs_unchanged': True,
              'note': 'Counts are creator-topic-product contexts, not unique creators. Presentation is not relative merit.'}
    args.output.mkdir(parents=True)
    for name, value in [('metrics.json', report), ('api_examples.json', examples)]:
        (args.output / name).write_text(json.dumps(value, indent=2, ensure_ascii=True) + '\n', encoding='utf-8')
    rows = ['# Phase 5E H1 prototype reproduction', '',
            'Assisted review, not independent human gold. No combined score or global ranking.', '',
            '| Topic | Strong evidence | Qualified | Manual review | Unavailable | Ineligible |',
            '|---|---:|---:|---:|---:|---:|']
    rows += ['| ' + topic + ' | ' + ' | '.join(str(counts[s]) for s in STATE_ORDER) + ' |' for topic, counts in by_topic.items()]
    rows += ['', 'Positive product-linked context counts: `' + json.dumps(dict(positive)) + '`.',
             '', 'These reproduce frozen H1. They do not establish independent candidate quality.',
             'Protected Product Fit and review inputs remained unchanged. See metrics.json and api_examples.json.']
    (args.output / 'IMPLEMENTATION_REPORT.md').write_text('\n'.join(rows) + '\n', encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
