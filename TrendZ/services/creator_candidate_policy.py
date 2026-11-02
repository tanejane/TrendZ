"""Approved prototype H1 gates, ported from Phase 5D; no popularity ordering."""

import json
from datetime import datetime

POLICY_VERSION = 'creator-candidate-h1-v1'
STATES = {'A': 'strong_evidence_candidate', 'B': 'qualified_candidate',
          'C': 'manual_review_only', 'abstain': 'unavailable', 'ineligible': 'ineligible'}
STATE_ORDER = list(STATES.values())
SPECIALIZATION = {key: key for key in ('skincare', 'makeup', 'haircare', 'fragrance')}


def timestamp(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))


def inspect_evidence(profile, affinity):
    pf, pr = profile['fixed'], profile['review']
    af, ar = affinity['fixed'], affinity['review']
    pool = {v['video_id']: v for v in af['videos'] + af.get('prior_videos', [])}
    ids = ar['selected_video_ids']
    dates = {timestamp(pool[i]['published_at']).date() for i in ids}
    proxy = []
    if '\n' in ar['notes']:
        try:
            proxy = json.loads(ar['notes'].split('\n', 1)[1]).get('proxy_video_ids', [])
        except ValueError:
            pass
    p_pool = {v['video_id']: v for v in pf['videos']}
    p_dates = {timestamp(p_pool[i]['published_at']).date() for i in pr['selected_video_ids']}
    eng = pf['engagement']
    return {
        'selected_ids': ids, 'distinct_dates': len(dates),
        'references_linked': bool(ids) and all(pool[i].get('source_ref', {}).get('run_id') for i in ids),
        'known_proxy_overlap': sorted(set(ids) & set(proxy)),
        'profile_distinct_dates': len(p_dates), 'source_pool': pool,
        'engagement_available': eng.get('state') == 'available'
        and eng.get('views', {}).get('median') is not None
        and eng.get('like_view_ratio', {}).get('median_of_video_ratios') is not None,
        'engagement_samples': eng.get('like_view_ratio', {}).get('valid_denominators', 0),
        'audience': pf['market_evidence'].get('audience_geography', {}),
    }


def decide(profile, affinity, product, required_market_evidence='optional', engagement_requirement='optional'):
    """H1 unchanged; optional requirements use the tested H5/H6/H7 scenario gates."""
    pr, ar = profile['review'], affinity['review']
    ev = inspect_evidence(profile, affinity)
    wanted = {SPECIALIZATION[c] for c in [product['provenance']['product']['category']] if c in SPECIALIZATION}
    matched = sorted(set(pr['human_specializations']) & wanted)
    reasons, warnings = [], []

    def result(band, reason):
        return {'candidate_state': STATES[band], 'reasons': reasons + [reason],
                'warnings': warnings, 'matched_specialization': matched,
                'product_required_specialization': sorted(wanted)}

    if product['fit_state'] == 'no_fit':
        return result('ineligible', 'Frozen Product Fit reports no_fit for this topic/product')
    if product['fit_state'] not in ('direct_fit', 'supporting_fit'):
        return result('abstain', 'Product Fit evidence is insufficient')
    if product['provenance']['product'].get('requires_review'):
        return result('abstain', 'Product identity/evidence is quarantined')
    reasons.append('Product context is ' + product['fit_state'] + '; not creator use/endorsement or commercial attractiveness')
    if ar['human_label'] == 'insufficient_evidence' or pr['human_label'] == 'insufficient_evidence':
        return result('abstain', 'Reviewed creator profile or topic affinity abstains')
    if ar['human_label'] == 'no_affinity' or pr['human_label'] == 'unsupported':
        return result('ineligible', 'Reviewed topic/profile explicitly unsupported for this scope')
    if pr['evidence_sufficiency'] == 'insufficient' or ar['evidence_sufficiency'] == 'insufficient':
        return result('abstain', 'Reviewed evidence sufficiency is insufficient')
    if not ev['references_linked'] or ev['known_proxy_overlap'] or not ar['notes'].strip():
        return result('abstain', 'Selected topic evidence is absent, unlinked, contradicts saved proxy exclusion, or lacks rationale')
    high = ar['human_label'] in ('moderate_affinity', 'strong_affinity')
    if high and (len(ev['selected_ids']) < 2 or ev['distinct_dates'] < 2):
        return result('abstain', 'Reviewed moderate/strong decision violates distinct-video/date minimum')
    if pr['human_label'] == 'supported' and (len(pr['selected_video_ids']) < 2 or ev['profile_distinct_dates'] < 2):
        return result('abstain', 'Supported profile violates distinct-video/date minimum')
    audience = ev['audience']
    verified_my = audience.get('state') == 'verified' and (
        audience.get('value') == 'MY' or isinstance(audience.get('value'), list) and 'MY' in audience['value'])
    if not verified_my:
        warnings.append('MY audience is not verified; search region and channel country do not establish audience')
    if required_market_evidence == 'verified' and not verified_my:
        return result('abstain', 'This scenario explicitly requires verified MY audience evidence')
    if not ev['engagement_available']:
        warnings.append('Descriptive engagement is unavailable; no topical penalty by default')
    minimum = 5 if engagement_requirement == 'five_valid_samples' else 1
    if engagement_requirement != 'optional' and (not ev['engagement_available'] or ev['engagement_samples'] < minimum):
        return result('abstain', 'This scenario explicitly requires descriptive engagement availability/sample coverage')
    if pr['explanation_support'] != 'supported' or ar['explanation_support'] != 'supported':
        warnings.append('Original screening explanation is unsupported/unresolved; this does not automatically invalidate corrected final profile fields')
    if 'beauty' not in pr['human_domains'] or not matched:
        return result('C', 'No reviewed relevant beauty domain/specialization for this product category; do not infer expertise')
    if high and pr['human_label'] == 'supported' and matched and pr['evidence_sufficiency'] == 'sufficient' and ar['evidence_sufficiency'] == 'sufficient':
        return result('A', 'Supported relevant profile, moderate/strong reviewed affinity, both sufficient and linked repeated-topic evidence')
    return result('B', 'Relevant reviewed profile and selected topic evidence; limited affinity or evidence remains qualified')
