"""Package explicitly authored assistance, never write human reviews or predictions."""
from collections import Counter
from datetime import datetime, timezone

from .creator_review import (PROFILE_LABELS, AFFINITY_LABELS, DOMAINS,
                             SPECIALIZATIONS, SUFFICIENCY, EXPLANATIONS, fingerprint)

VERSION = 'creator-review-assist-v1'


def date_of(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00')).astimezone(timezone.utc)


def prepare_pack(session, records, decisions):
    """Pure transform: no DB, producer, evaluator, collection, or label-save calls.

    Decisions are individually authored frozen-sample judgments, not a new matching
    algorithm. Selected relevance is only proposed; approved counts remain separate.
    """
    if decisions['source_sha256'] != session['source_sha256']:
        raise ValueError('Assistance belongs to another source snapshot')
    fixed = {r['fixed']['unit_id']: r for r in records}
    items = decisions['rows']
    ids = [d['unit_id'] for d in items]
    if len(ids) != len(set(ids)) or set(ids) != set(fixed):
        raise ValueError('Assistance must cover each fixed unit exactly once')
    output = []
    for decision in items:
        record = fixed[decision['unit_id']]
        unit, review = record['fixed'], record['review']
        profile = unit['unit_type'] == 'profile'
        label = decision['proposed_label']
        if label not in (PROFILE_LABELS if profile else AFFINITY_LABELS):
            raise ValueError('Invalid suggested label')
        for key, choices in [('confidence', ('high', 'medium', 'low')),
                             ('evidence_sufficiency', SUFFICIENCY),
                             ('explanation_support', EXPLANATIONS)]:
            if decision[key] not in choices:
                raise ValueError('Invalid ' + key)
        if not decision['reason'].strip() or not decision['explanation_reason'].strip():
            raise ValueError('A substantive judgment and explanation reason are required')
        domains = decision.get('proposed_domains', [])
        specs = decision.get('proposed_specializations', [])
        if not set(domains) <= set(DOMAINS) or not set(specs) <= set(SPECIALIZATIONS):
            raise ValueError('Invalid classification')
        if not profile and (domains or specs):
            raise ValueError('Affinity cannot assign a profile')
        if specs and 'beauty' not in domains:
            raise ValueError('Beauty specialization needs beauty domain')
        if label == 'insufficient_evidence':
            if decision['evidence_sufficiency'] != 'insufficient' or domains or specs:
                raise ValueError('Abstention cannot finalize classifications')
        elif decision['evidence_sufficiency'] == 'insufficient':
            raise ValueError('Non-abstaining label needs evidence')
        if profile and label in ('supported', 'partially_supported') and not domains:
            raise ValueError('Profile support needs a classification')
        videos = {v['video_id']: v for v in unit['videos'] + unit.get('prior_videos', [])}
        selected = decision['selected_video_ids']
        proxy = decision.get('proxy_video_ids', [])
        if len(selected) != len(set(selected)) or len(proxy) != len(set(proxy)):
            raise ValueError('Duplicate video evidence')
        if not (set(selected) | set(proxy)) <= set(videos):
            raise ValueError('Evidence outside fixed unit')
        if set(selected) & set(proxy):
            raise ValueError('Proxy evidence cannot count as relevant selection')
        dates = sorted({date_of(videos[i]['published_at']).date().isoformat()
                        for i in selected if videos[i].get('published_at')})
        sustained = label == 'supported' if profile else label in ('strong_affinity', 'moderate_affinity')
        if sustained and (len(selected) < 2 or len(dates) < 2):
            raise ValueError('Stable/sustained suggestion requires two videos on distinct dates')
        if (label == 'weak_affinity' or profile and label == 'partially_supported') and not selected:
            raise ValueError('Limited support still requires selected evidence')
        if label == 'no_affinity' and selected:
            raise ValueError('No-affinity cannot select relevant videos')
        current = {v['video_id'] for v in unit['videos']}
        selected_current = set(selected) & current
        times = sorted(date_of(videos[i]['published_at']) for i in selected
                       if videos[i].get('published_at'))
        inherited = set(unit.get('affinity_proposal', {}).get('prior_confirmed_video_ids', []))
        all_inherited = {s['video_id'] for s in unit['seed_provenance']}
        def evidence(identifier):
            v = videos[identifier]
            return {k: v.get(k) for k in ('video_id', 'title', 'description', 'published_at',
                    'retrieved_at', 'url', 'source_ref', 'sample_scope')}
        explanation_target = unit['profile_proposal'] if profile else unit['affinity_proposal']
        output.append({**decision, 'session_id': session['session_id'],
            'unit_type': unit['unit_type'], 'creator_id': unit['creator_id'],
            'display_name': unit['display_name'], 'topic_id': unit['topic_id'],
            'query_id': unit.get('query_id'), 'readiness_group': unit['readiness_group'],
            'review_basis': 'assisted_review', 'review_status': 'needs_human_acceptance',
            'assist_source': 'frozen_metadata_inspection', 'method_version': VERSION,
            'source_sha256': session['source_sha256'], 'fixed_unit_sha256': fingerprint(unit),
            'based_on_revision': review['revision'], 'existing_review_sha256': fingerprint(review),
            'existing_human_label_present': review['human_label'] is not None,
            'human_approval_required': True,
            'deeper_manual_review_required': decision['confidence'] != 'high',
            'evidence_scope': 'frozen titles/descriptions/dates and inherited reviewed seeds; no playback verification',
            'selected_evidence': [evidence(i) for i in selected],
            'proxy_evidence': [evidence(i) for i in proxy],
            'explicit_topic_video_ids': selected if not profile else [],
            'prior_approved_relevant_video_ids': sorted(inherited),
            'selected_previously_approved_video_ids': sorted(set(selected) & (all_inherited if profile else inherited)),
            'newly_approved_video_count': 0,
            'sustained_affinity_validated': False,
            'proposed_label_is_conditional': sustained,
            'acceptance_requirements': (
                'Explicitly approve at least two selected relevant videos on distinct publication dates before accepting sustained affinity.'
                if sustained and not profile else
                'Explicitly approve the classification and at least two selected supporting videos on distinct publication dates before accepting a stable profile.'
                if sustained else 'Explicit human inspection and acceptance; never auto-finalize.'),
            'proposed_components': {'selected_count': len(selected),
                'distinct_publication_dates': dates,
                'selected_current_sample_count': len(selected_current),
                'sample_video_count': len(current),
                'proposed_sample_share': len(selected_current) / len(current) if current else None,
                'selected_prior_outside_sample': sorted(set(selected) - current),
                'first_publication': times[0].isoformat() if times else None,
                'latest_publication': times[-1].isoformat() if times else None,
                'span_days': (times[-1] - times[0]).total_seconds() / 86400 if times else None,
                'days_since_latest': (date_of(unit['as_of']) - times[-1]).total_seconds() / 86400 if times else None,
                'coverage': 'repeated_candidate_not_approved' if len(dates) >= 2 else 'one_date_or_no_candidate'},
            'explanation_audit_target': 'fixed profile_proposal' if profile else 'fixed affinity_proposal',
            'explanation_audit_target_sha256': fingerprint(explanation_target),
            'explanation_scope': 'Stored screening claims and their substantive classification/relevance support; not medical efficacy or video truth.',
        })
    counts = {kind: dict(Counter(r['confidence'] for r in output if r['unit_type'] == kind))
              for kind in ('profile', 'affinity')}
    return {'method_version': VERSION, 'session_id': session['session_id'],
        'source_sha256': session['source_sha256'], 'decisions_sha256': fingerprint(decisions),
        'review_basis': 'assisted_review', 'status': 'drafts_only_no_human_labels_written',
        'scope_notice': 'Assistance is not gold. Every row needs explicit human acceptance. No rankings or validation conclusions.',
        'confidence_meaning': 'Certainty in the proposed scoped judgment, not creator expertise or validated affinity.',
        'confidence_counts': counts, 'rows': output}


def markdown_pack(pack):
    lines = ['# Phase 5C Assisted Review Drafts', '', pack['scope_notice'], '',
        'Frozen metadata only: no video/audio playback or new source collection. Suggested relevant videos are not newly approved.',
        'Open the existing local workspace at http://127.0.0.1:5016/ to inspect/edit and explicitly save a review. This pack never saves labels.', '',
        'All rows need human acceptance. Medium/low rows need deeper manual inspection. Confidence is not an affinity score.', '',
        '| Unit type | High | Medium | Low |', '| --- | ---: | ---: | ---: |']
    for kind, counts in pack['confidence_counts'].items():
        lines.append(f"| {kind} | {counts.get('high',0)} | {counts.get('medium',0)} | {counts.get('low',0)} |")
    lines += ['', '## Deeper Manual Queue', '', '| Creator | Unit/topic | Confidence | Reason |', '| --- | --- | --- | --- |']
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ')
    for row in pack['rows']:
        if row['deeper_manual_review_required']:
            lines.append('| ' + ' | '.join(cell(v) for v in (row['display_name'], row['topic_id'] or 'profile', row['confidence'], row['reason'])) + ' |')
    for kind in ('profile', 'affinity'):
        lines += ['', '## ' + kind.title() + ' Drafts']
        for r in (r for r in pack['rows'] if r['unit_type'] == kind):
            lines += ['', '### ' + r['display_name'] + (' / ' + r['topic_id'] if r['topic_id'] else ''),
                '', '`' + r['unit_id'] + '`', '',
                f"Draft: **{r['proposed_label']}**; confidence **{r['confidence']}**; sufficiency `{r['evidence_sufficiency']}`.",
                'Reason: ' + r['reason']]
            if kind == 'profile':
                lines += ['Proposed domains: ' + ', '.join(r['proposed_domains']) + '; specializations: ' + ', '.join(r['proposed_specializations']) + '.']
            c = r['proposed_components']
            lines += [f"Selected candidate videos: {c['selected_count']}; distinct dates: {len(c['distinct_publication_dates'])}; current-sample candidates: {c['selected_current_sample_count']}/{c['sample_video_count']}. These counts are not approved relevance.",
                r['acceptance_requirements'],
                f"Explanation draft: `{r['explanation_support']}`. " + r['explanation_reason'],
                'Supporting videos:']
            for v in r['selected_evidence']:
                lines.append('- [' + v['video_id'] + '](' + (v['url'] or 'https://www.youtube.com/watch?v='+v['video_id']) + ') ' +
                    (v['published_at'] or 'date unavailable')[:10] + ': ' + (v['title'] or '[prior human-reviewed seed; title absent in fixed snapshot]'))
            if not r['selected_evidence']:
                lines.append('- None selected; abstention is not a verified negative.')
            if r['proxy_evidence']:
                lines += ['Proxy/context only, excluded from selected relevance:']
                for v in r['proxy_evidence']:
                    lines.append('- [' + v['video_id'] + '](https://www.youtube.com/watch?v='+v['video_id']+') '+(v['title'] or '[prior seed]'))
            if r.get('manual_question'):
                lines.append('Manual question: ' + r['manual_question'])
            lines.append('Original group: `' + r['readiness_group'] + '`; `review_basis=assisted_review`; **not accepted**.')
    return '\n'.join(lines) + '\n'
