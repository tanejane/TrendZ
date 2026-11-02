"""Human review metrics; deterministic rule outputs must never become human gold."""

import math
from collections import defaultdict

GRADES = {'direct_fit':2, 'supporting_fit':1, 'no_fit':0, 'insufficient_evidence':0}


def ranking_metrics(predicted_ids, labels):
    """Closed candidate pool: P@5 denominator 5, recall over labelled pool only."""
    if not labels or any(value not in GRADES for value in labels.values()):
        return None
    top = predicted_ids[:5]
    relevant = {identifier for identifier, label in labels.items() if GRADES[label] > 0}
    dcg = sum((2**GRADES[labels[identifier]]-1)/math.log2(rank+2)
              for rank,identifier in enumerate(top))
    ideal = sorted([GRADES[label] for label in labels.values()],reverse=True)[:5]
    idcg = sum((2**grade-1)/math.log2(rank+2) for rank,grade in enumerate(ideal))
    return {'precision_at_5':len(set(top)&relevant)/5,
            'ndcg_at_5':dcg/idcg if idcg else None,
            'catalogue_bounded_recall':len(set(predicted_ids)&relevant)/len(relevant) if relevant else None}


def evaluate(service, review):
    if review['catalogue_version'] != service.catalogue.version or review['method_version'] != 'product-fit-rules-1':
        raise ValueError('Review belongs to a different catalogue or method; do not silently relabel it')
    expected = {(topic,p['product_id']) for topic in service.intents['topics'] for p in service.catalogue.products}
    keys = [(row['topic_id'],row['product_id']) for row in review['rows']]
    if len(set(keys)) != len(keys) or set(keys) != expected:
        raise ValueError('Fixed review must contain each canonical topic/product pair exactly once')
    families = defaultdict(set)
    for row in review['rows']:
        if row['query_id'] != 'canonical' or row['split'] not in ('dev','evaluation'):
            raise ValueError('Unexpected query or split')
        if row['human_label'] is not None and row['human_label'] not in GRADES:
            raise ValueError('Invalid human label')
        if row['unsupported_explanation'] not in (None, True, False):
            raise ValueError('Unsupported explanation must be a human boolean or null')
        product = next(p for p in service.catalogue.products if p['product_id']==row['product_id'])
        if product['family_id'] != row['family_id']:
            raise ValueError('Family changed')
        families[row['family_id']].add(row['split'])
    if any(len(splits)>1 for splits in families.values()):
        raise ValueError('Product-family leakage between dev and evaluation')
    outputs = {topic:service.topic(topic) for topic in service.intents['topics']}
    report = {'catalogue_version':service.catalogue.version, 'human_review':{}, 'mechanical_checks':{}}
    for topic, output in outputs.items():
        assessments = output['assessments']
        refs = [ref for row in output['matched_products'] for ref in row['supporting_evidence']]
        valid = sum(ref['catalogue_version']==service.catalogue.version and bool(ref['source']['url'])
                    and ref['value'] is not None and bool(ref['basis']) for ref in refs)
        report['mechanical_checks'][topic] = {
            'insufficient_evidence_rate':sum(a['fit_state']=='insufficient_evidence' for a in assessments)/len(assessments),
            'explanation_reference_traceability':valid/len(refs) if refs else None,
            'scope':'Schema/reference integrity, not a human factual-support evaluation'}
        report['human_review'][topic] = {}
        for split in ('dev','evaluation'):
            rows = [r for r in review['rows'] if r['topic_id']==topic and r['split']==split]
            labels = {row['product_id']:row['human_label'] for row in rows}
            predicted = [p['product_id'] for p in output['matched_products'] if p['product_id'] in labels]
            metrics = ranking_metrics(predicted,labels)
            support = [row['unsupported_explanation'] for row in rows if row['product_id'] in predicted]
            report['human_review'][topic][split] = {
                'state':'available' if metrics is not None else 'unavailable',
                'reason':None if metrics is not None else 'Manual Product Fit labels pending; no inferred gold labels',
                'labelled':sum(value is not None for value in labels.values()), 'total':len(rows),
                'metrics':metrics,
                'unsupported_match_rate':sum(support)/len(support) if support and all(v is not None for v in support) else None,
                'unsupported_match_reason':'Requires separate manual explanation-support judgments; reference integrity is not semantic validation',
                'candidate_scope':'Fixed '+split+' family-disjoint catalogue subset; not market-wide recall'}
    return report
