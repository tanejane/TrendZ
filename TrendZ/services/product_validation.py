"""Descriptive human validation only. Diagnostic tags are not causal conclusions."""

from collections import Counter

from .product_evaluation import GRADES, ranking_metrics

STATES = tuple(GRADES)
POSITIVE = {'direct_fit','supporting_fit'}


def diagnostic_tags(row):
    prediction, context = row['prediction'], row['context']
    tags = []
    missing = ' '.join(prediction['missing_evidence']).lower()
    for text, tag in [('normalized_ingredients','missing_ingredient_evidence'),
                      ('incomplete inci','incomplete_ingredient_evidence'),
                      ('manufacturer_claims','missing_declared_benefits'),
                      ('application_area','missing_application_area'),
                      ('product_format','missing_product_format'),
                      ('quarantined','quarantined_source')]:
        if text in missing:
            tags.append(tag)
    for field in ('format_compatibility','application_area_compatibility','subcategory_compatibility'):
        if prediction['dimensions'][field]['compatible'] is False:
            tags.append(field+'_disagreement')
    kind = context['intent']['kind']
    if kind in ('look','occasion'):
        tags.append(kind+'_proxy_intent')
    if kind == 'ingredient' and prediction['dimensions']['ingredient_agreement']['completeness'] != 'complete':
        tags.append('partial_or_unknown_INCI')
    if row['fixed']['topic_id']=='skin-barrier' and not prediction['dimensions']['declared_benefit_agreement']['matched']:
        tags.append('barrier_supporting_proxy_without_primary_claim')
    return tags or ['no_specific_recorded_pattern']


def patterns(rows):
    counts = Counter(tag for row in rows for tag in diagnostic_tags(row))
    return [{'pattern':tag,'pair_count':count,
             'pair_ids':[row['pair_id'] for row in rows if tag in diagnostic_tags(row)]}
            for tag,count in counts.most_common()]


def analyze(rows, outputs):
    topics = {row['fixed']['topic_id'] for row in rows}
    rankings = {}
    for topic in sorted(topics):
        subset = [row for row in rows if row['fixed']['topic_id']==topic]
        gold = {row['prediction']['product_id']:row['human_label'] for row in subset}
        predicted = [p['product_id'] for p in outputs[topic]['matched_products'] if p['product_id'] in gold]
        rankings[topic] = ranking_metrics(predicted,gold)
    confusion = {gold:{predicted:0 for predicted in STATES} for gold in STATES}
    for row in rows:
        confusion[row['human_label']][row['prediction']['fit_state']] += 1
    matches = [r for r in rows if r['prediction']['fit_state'] in POSITIVE]
    false_positives = [r for r in matches if r['human_label']=='no_fit']
    uncertain_positives = [r for r in matches if r['human_label']=='insufficient_evidence']
    false_negatives = [r for r in rows if r['human_label'] in POSITIVE and r['prediction']['fit_state'] not in POSITIVE]
    abstained = [r for r in rows if r['prediction']['fit_state']=='insufficient_evidence']
    same_category_negatives = [r for r in rows if r['human_label']=='no_fit' and
                              r['prediction']['provenance']['product']['category'] in r['context']['intent']['categories']]
    same_category_fp = [r for r in same_category_negatives if r['prediction']['fit_state'] in POSITIVE]
    support = [r['unsupported_explanation'] for r in matches]
    means = {}
    for metric in ('precision_at_5','ndcg_at_5','catalogue_bounded_recall'):
        values = [metrics[metric] for metrics in rankings.values() if metrics is not None and metrics[metric] is not None]
        means[metric] = sum(values)/len(values) if values else None
        means[metric+'_topics_defined'] = len(values)
    return {'pairs':len(rows),'ranking_by_topic':rankings,'macro_ranking':means,
            'confusion_matrix':{'rows':'human_label','columns':'predicted_fit_state','counts':confusion},
            'unsupported_match_rate':sum(support)/len(support) if support and all(type(value) is bool for value in support) else None,
            'unsupported_match_denominator':len(support),
            'abstention_rate':len(abstained)/len(rows) if rows else None,
            'human_insufficient_evidence_rate':sum(r['human_label']=='insufficient_evidence' for r in rows)/len(rows) if rows else None,
            'false_positive_count':len(false_positives),
            'predicted_positive_human_insufficient_count':len(uncertain_positives),
            'false_negative_count':len(false_negatives),
            'false_negatives_abstained':sum(r['prediction']['fit_state']=='insufficient_evidence' for r in false_negatives),
            'false_positive_patterns':patterns(false_positives),
            'false_negative_patterns':patterns(false_negatives),
            'positive_with_insufficient_gold_patterns':patterns(uncertain_positives),
            'abstention_evidence_gaps':patterns(abstained),
            'same_category_overmatching':{'confirmed_false_positives':len(same_category_fp),
                'human_no_fit_same_category_candidates':len(same_category_negatives),
                'false_positive_rate_among_same_category_negatives':len(same_category_fp)/len(same_category_negatives) if same_category_negatives else None,
                'state':'observed_errors' if same_category_fp else 'none_observed_in_reviewed_pool' if same_category_negatives else 'unavailable_no_same_category_negatives'},
            'errors':[{'pair_id':r['pair_id'],'topic_id':r['fixed']['topic_id'],
                       'product_id':r['fixed']['product_id'],'predicted':r['prediction']['fit_state'],
                       'human_label':r['human_label'],'notes':r['notes'],
                       'missing_evidence':r['prediction']['missing_evidence'],
                       'contradictions':r['prediction']['contradictions'], 'diagnostic_tags':diagnostic_tags(r)}
                      for r in rows if r['human_label']!=r['prediction']['fit_state']]}


def validation_report(rows, metadata):
    if not rows or any(row['human_label'] not in GRADES for row in rows):
        raise ValueError('Complete human labels required before validation')
    if any(row['prediction']['fit_state'] in POSITIVE and type(row['unsupported_explanation']) is not bool for row in rows):
        raise ValueError('Complete separate explanation-support judgments required')
    expected = {(row['topic_id'],row['query_id'],row['product_id']) for row in metadata['baseline']['rows']}
    actual = [(r['fixed']['topic_id'],r['fixed']['query_id'],r['fixed']['product_id']) for r in rows]
    if len(actual)!=len(set(actual)) or set(actual)!=expected:
        raise ValueError('All fixed review pairs are required, without duplicates')
    outputs = metadata['outputs']
    report = {'state':'complete','session_id':metadata['session_id'],
              'catalogue_version':metadata['catalogue_version'],'method_version':metadata['method_version'],
              'intent_version':metadata['intent_version'],'fingerprints':metadata['fingerprints'],
              'metrics':analyze(rows,outputs),
              'by_split':{split:analyze([r for r in rows if r['fixed']['split']==split],outputs)
                          for split in ('dev','evaluation')},
              'by_topic':{topic:analyze([r for r in rows if r['fixed']['topic_id']==topic],outputs)
                          for topic in outputs},
              'limitations':['Human judgments validate only the fixed catalogue/query scope, not efficacy or market truth',
                             'Full-catalogue results are descriptive; family-disjoint evaluation results remain separate from dev',
                             'Diagnostic patterns describe recorded evidence; they do not establish why the reviewer chose a label',
                             'One reviewer and source/index freshness remain limitations; no inter-rater agreement is measured',
                             'No matching rules were changed during validation']}
    errors = report['metrics']['errors']
    unsupported = report['metrics']['unsupported_match_rate']
    report['recommendation'] = {
        'state':'review_adjustments_warranted' if errors or (unsupported is not None and unsupported>0) else 'retain_current_baseline_within_tested_scope',
        'reason':'Inspect confirmed disagreements and unsupported explanations before proposing targeted changes; do not tune on held-out evaluation data' if errors or unsupported else
                 'No reviewed disagreements or unsupported explanations observed; this does not prove generalization',
        'priority_patterns':report['by_split']['dev']['false_positive_patterns'][:3]+report['by_split']['dev']['false_negative_patterns'][:3],
        'automatic_rule_changes':False}
    return report


def markdown_report(report):
    if report['state']!='complete':
        raise ValueError('No final validation report until review is complete')
    lines = ['# Phase 4C Product Fit Validation','',
             'Session: '+report['session_id'], 'Catalogue: '+report['catalogue_version'],
             'Method: '+report['method_version'],'',
             '## Per-topic Results','',
             '| Topic | P@5 | nDCG@5 | Bounded recall | Unsupported | Abstention | FP | FN |',
             '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    def number(value):
        return 'Unavailable' if value is None else f'{value:.4f}'
    for topic,metrics in report['by_topic'].items():
        ranking = metrics['ranking_by_topic'][topic]
        values = [number(ranking[k]) for k in ('precision_at_5','ndcg_at_5','catalogue_bounded_recall')]
        lines.append('| '+' | '.join([topic,*values,number(metrics['unsupported_match_rate']),
                      number(metrics['abstention_rate']),str(metrics['false_positive_count']),str(metrics['false_negative_count'])])+' |')
    lines += ['', '## Confusion Matrix (Human Rows, Prediction Columns)', '',
              '| Human / Predicted | '+' | '.join(STATES)+' |','| --- | ---: | ---: | ---: | ---: |']
    for state,counts in report['metrics']['confusion_matrix']['counts'].items():
        lines.append('| '+state+' | '+' | '.join(str(counts[s]) for s in STATES)+' |')
    for title,key in [('False-positive Patterns','false_positive_patterns'),('False-negative Patterns','false_negative_patterns'),
                      ('Abstention Evidence Gaps','abstention_evidence_gaps')]:
        lines += ['', '## '+title,'']
        lines += [f"- {row['pattern']}: {row['pair_count']} pairs" for row in report['metrics'][key]] or ['None observed.']
    lines += ['', '## Same-category Overmatching','',
              json_text(report['metrics']['same_category_overmatching']), '',
              '## Recommendation (After Completed Human Review Only)','',
              report['recommendation']['state']+': '+report['recommendation']['reason'],
              '', 'See the JSON companion for per-topic/split matrices, evidence-gap IDs and all disagreements with notes.',
              '', '## Limitations','', *['- '+text for text in report['limitations']]]
    return '\n'.join(lines)+'\n'


def json_text(value):
    import json
    return '```json\n'+json.dumps(value,indent=2)+'\n```'
