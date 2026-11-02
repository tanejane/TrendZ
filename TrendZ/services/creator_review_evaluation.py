"""Descriptive review validation, not a Creator Fit score or ranking."""
from collections import Counter
import statistics
from .creator_analysis import timestamp


def ratio(n,d):
    return n/d if d else None


def selected_components(row):
    fixed,review=row['fixed'],row['review']
    pool={v['video_id']:v for v in fixed['videos']+fixed.get('prior_videos',[])}
    selected=[pool[x] for x in review['selected_video_ids']]
    dates=sorted(timestamp(v['published_at']) for v in selected)
    current={v['video_id'] for v in fixed['videos']}
    n=sum(v['video_id'] in current for v in selected)
    return {'approved_video_count':len(selected),'approved_current_sample_count':n,
        'sample_denominator':len(current),'sample_share':ratio(n,len(current)),
        'prior_outside_sample_count':len(selected)-n,
        'first_publication':dates[0].isoformat() if dates else None,
        'latest_publication':dates[-1].isoformat() if dates else None,
        'span_days':(dates[-1]-dates[0]).total_seconds()/86400 if dates else None,
        'days_since_latest':(timestamp(fixed['as_of'])-dates[-1]).total_seconds()/86400 if dates else None,
        'coverage':'repeated' if len({d.date() for d in dates})>=2 else 'one_off' if len(dates)==1 else 'clustered' if dates else 'none'}


def group_metrics(records):
    profiles=[r for r in records if r['fixed']['unit_type']=='profile']
    affinities=[r for r in records if r['fixed']['unit_type']=='affinity']
    answered=[r for r in profiles if r['review']['human_label']!='insufficient_evidence']
    comparable=[r for r in answered if r['fixed']['profile_proposal']['proposed_domains'] or r['fixed']['profile_proposal']['proposed_specializations']]
    exact=sum(set(r['fixed']['profile_proposal']['proposed_domains'])==set(r['review']['human_domains']) and
              set(r['fixed']['profile_proposal']['proposed_specializations'])==set(r['review']['human_specializations']) for r in comparable)
    tp=fp=fn=predicted=human=0
    for r in answered:
        a=set(r['fixed']['profile_proposal']['proposed_specializations'])
        b=set(r['review']['human_specializations'])
        tp+=len(a&b);fp+=len(a-b);fn+=len(b-a)
        predicted+=bool(a);human+=bool(b)
    high=[r for r in affinities if r['review']['human_label'] in ('strong_affinity','moderate_affinity')]
    one_video=sum(selected_components(r)['approved_video_count']<2 for r in high)
    explain=Counter(r['review']['explanation_support'] for r in records)
    return {'profiles':len(profiles),'affinities':len(affinities),
        'profile_label_distribution':dict(Counter(r['review']['human_label'] for r in profiles)),
        'affinity_label_distribution':dict(Counter(r['review']['human_label'] for r in affinities)),
        'profile_agreement':{'definition':'Exact domain AND specialization set agreement on non-abstaining rows with a nonempty proposal',
                             'matches':exact,'comparable':len(comparable),'rate':ratio(exact,len(comparable)),
                             'no_profile_proposal':len(answered)-len(comparable)},
        'specializations':{'true_positive':tp,'false_positive':fp,'false_negative':fn,
            'precision':ratio(tp,tp+fp),'human_label_coverage_recall':ratio(tp,tp+fn),
            'proposal_coverage_among_answered_profiles':ratio(predicted,len(answered)),
            'profiles_with_human_specializations':human,'answered_profiles':len(answered)},
        'topic_affinity_agreement':{'state':'unavailable','reason':'Phase 5B assigned no categorical affinity predictions; draft gates are not predictions'},
        'one_video_overmatching':{'high_affinity_labels':len(high),'one_video_high_labels':one_video,
            'rate':ratio(one_video,len(high)),'scope':'Reviewed high-affinity decisions only; not an estimate for unreviewed creators'},
        'abstention':{'profile_count':sum(r['review']['human_label']=='insufficient_evidence' for r in profiles),
                      'profile_rate':ratio(sum(r['review']['human_label']=='insufficient_evidence' for r in profiles),len(profiles)),
                      'affinity_count':sum(r['review']['human_label']=='insufficient_evidence' for r in affinities),
                      'affinity_rate':ratio(sum(r['review']['human_label']=='insufficient_evidence' for r in affinities),len(affinities))},
        'evidence_sufficiency':dict(Counter(r['review']['evidence_sufficiency'] for r in records)),
        'explanation_support':{'counts':dict(explain),'supported_rate_among_decided':ratio(explain['supported'],explain['supported']+explain['unsupported']),
                               'failure_rate_among_decided':ratio(explain['unsupported'],explain['supported']+explain['unsupported'])},
        'review_basis':dict(Counter(r['review']['review_basis'] for r in records))}


def evaluate(records):
    if not records or any(r['review']['human_label'] is None for r in records):
        return {'state':'pending','reason':'Final review is incomplete'}
    profiles=[r for r in records if r['fixed']['unit_type']=='profile']
    affinities=[r for r in records if r['fixed']['unit_type']=='affinity']
    gate_sensitivity={}
    for gate,positives in [('draft_moderate_gate',('strong_affinity','moderate_affinity')),('draft_strong_gate',('strong_affinity',))]:
        table={key:0 for key in ('gate_yes_human_yes','gate_yes_human_no','gate_no_human_yes','gate_no_human_no')}
        for row in affinities:
            if row['review']['human_label']=='insufficient_evidence':
                continue
            yes=row['fixed']['affinity_proposal']['draft_threshold_sensitivity'][gate]['screen_assisted_meets_gate']
            human=row['review']['human_label'] in positives
            table['gate_'+('yes' if yes else 'no')+'_human_'+('yes' if human else 'no')]+=1
        gate_sensitivity[gate]=table
    values=[r['fixed']['engagement']['views']['median'] for r in profiles if r['fixed']['engagement']['views']['median'] is not None]
    cuts=statistics.quantiles(values,n=4,method='inclusive') if len(values)>=2 else []
    strata={}
    for row in profiles:
        value=row['fixed']['engagement']['views']['median']
        key='unknown' if value is None else 'Q'+str(1+sum(value>cut for cut in cuts))
        strata.setdefault(key,[]).append(row['fixed']['creator_id'])
    popularity={key:group_metrics([r for r in records if r['fixed']['creator_id'] in creators]) for key,creators in strata.items()}
    multi=[]
    linked=total=0
    for profile in profiles:
        creator=profile['fixed']['creator_id']
        rows=[r for r in affinities if r['fixed']['creator_id']==creator]
        multi.append({'creator_id':creator,'reviewed_candidate_topics':len(rows),
            'topics_with_positive_human_affinity':sum(r['review']['human_label'] in ('strong_affinity','moderate_affinity','weak_affinity') for r in rows),
            'topics_with_sustained_human_affinity':sum(r['review']['human_label'] in ('strong_affinity','moderate_affinity') for r in rows)})
    details=[]
    for row in records:
        pool={v['video_id']:v for v in row['fixed']['videos']+row['fixed'].get('prior_videos',[])}
        for identifier in row['review']['selected_video_ids']:
            total+=1
            linked+=bool(pool[identifier].get('source_ref',{}).get('run_id'))
        details.append({'unit_id':row['fixed']['unit_id'],'readiness_group':row['fixed']['readiness_group'],
            'human_label':row['review']['human_label'],'evidence_sufficiency':row['review']['evidence_sufficiency'],
            'explanation_support':row['review']['explanation_support'],'notes':row['review']['notes'],
            'components':selected_components(row) if row['fixed']['unit_type']=='affinity' else None})
    return {'state':'complete','method_version':'creator-review-evaluation-v1','independent_gold':False,
        'overall':group_metrics(records),
        'by_readiness':{g:group_metrics([r for r in records if r['fixed']['readiness_group']==g]) for g in ('review_ready','insufficient')},
        'by_topic':{t:group_metrics([r for r in affinities if r['fixed']['topic_id']==t]) for t in sorted({r['fixed']['topic_id'] for r in affinities})},
        'popularity_strata':{'median_view_quartile_boundaries':cuts,'groups':popularity,
                            'interpretation':'Descriptive conditional association only; not causal popularity bias. Missing values are separate; small/tied groups may be empty.'},
        'draft_gate_sensitivity':gate_sensitivity,'multi_topic_behavior':multi,
        'explanation_traceability':{'selected_video_references':total,'linked_to_run':linked,'link_rate':ratio(linked,total),
                                   'scope':'Structural source linkage, not factual verification; see separate human explanation judgments'},
        'details':details,
        'limitations':['Fixed candidate-topic scope is not all 320 pairs or a representative channel sample.',
                      'Review-ready and insufficient groups remain fixed from Phase 5B, not recategorized by outcomes.',
                      'No categorical producer affinity labels exist; categorical agreement cannot be calculated.',
                      'Reviews share creators and are not independent pair samples; no inferential confidence claims.',
                      'No ranking, combined score, recommendations, audience inference or historical engagement reconstruction.']}


def markdown_report(report):
    def number(value):
        return 'Unavailable' if value is None else f'{value:.4f}'
    lines=['# Phase 5C Creator Evidence Review Evaluation','',
        'Human-approved review outcomes with recorded review basis; not automatically independent gold. No ranking or combined creator score.','',
        '## Fixed Evidence Groups','',
        '| Group | Profiles | Affinity pairs | Profile agreement | Specialization precision | Specialization coverage/recall | Profile abstention | Affinity abstention |',
        '| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |']
    for name,result in [('Overall',report['overall']),*report['by_readiness'].items()]:
        values=[result['profile_agreement']['rate'],result['specializations']['precision'],
                result['specializations']['human_label_coverage_recall'],result['abstention']['profile_rate'],result['abstention']['affinity_rate']]
        lines.append(f"| {name} | {result['profiles']} | {result['affinities']} | "+' | '.join(number(v) for v in values)+' |')
    lines+=['','Categorical topic-affinity agreement is unavailable: Phase 5B made no categorical predictions. The JSON contains separate exploratory draft-gate sensitivity comparisons, not categorical model accuracy.','',
        '## Topic Outcomes','','| Topic | Reviewed pairs | Human label distribution | Insufficient evidence |','| --- | ---: | --- | ---: |']
    for topic,result in report['by_topic'].items():
        distribution=', '.join(f'{key}: {value}' for key,value in result['affinity_label_distribution'].items())
        lines.append(f"| {topic} | {result['affinities']} | {distribution} | {result['abstention']['affinity_count']} |")
    lines+=['','## Evidence and Traceability','',
        'One-video high-affinity review errors: '+str(report['overall']['one_video_overmatching']['one_video_high_labels'])+'.',
        'Structural evidence run-link rate: '+number(report['explanation_traceability']['link_rate'])+'. This is not factual explanation verification.',
        'Human explanation-support judgments: '+str(report['overall']['explanation_support']['counts'])+'.',
        '', '## Evidence-sufficiency / Explanation Exceptions', '', '| Review unit | Label | Sufficiency | Explanation | Reviewer notes |','| --- | --- | --- | --- | --- |']
    for row in report['details']:
        if row['evidence_sufficiency']!='sufficient' or row['explanation_support']!='supported':
            lines.append('| '+' | '.join(str(row[key]).replace('|','/').replace('\n',' ') for key in
                ('unit_id','human_label','evidence_sufficiency','explanation_support','notes'))+' |')
    lines+=['','## Limits','',
        'Popularity strata and per-creator multi-topic behavior are in the JSON. View-based strata are descriptive, not a causal popularity-bias result. Positive topical fit is not inferred from engagement. Review-ready and insufficient groups retain their original Phase 5B assignments.','',
        *['- '+text for text in report['limitations']]]
    return '\n'.join(lines)+'\n'
