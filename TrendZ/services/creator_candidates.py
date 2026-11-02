"""Read-only, sealed Phase 5C/4D evidence provider for the H1 prototype."""

import copy
import hashlib
import json
from collections import Counter
from pathlib import Path

from .creator_candidate_policy import POLICY_VERSION, STATE_ORDER, decide, inspect_evidence

REVIEW_HASH = '9235148176a44bc5ec32721c5d4abfd40928d1845538f979f19619cc75219666'
PINS = {'product_fit_version': 'product-fit-rules-1',
        'catalogue_version': 'my-curated-2026-10-16-evidence-v1',
        'review_revision_hash': REVIEW_HASH, 'creator_policy_version': POLICY_VERSION}
SEALED = {
    'reports/phase5c/final-v1/creator_profile_review_export.json': '995aefeeb756f0e88169af5071651bc3840b68d7db69f7ca9486799ac249fe6c',
    'reports/phase5c/final-v1/creator_affinity_review_export.json': 'b23d915e741a05fea726ce83fc515804b2e5de2cf195149561c6c550648d9f6f',
    'reports/phase4d-lite/predictions_after.json': '3f6e5d9d989bbed51141aec6090693f98f1e10c8e890e58f544def28447c4e8d',
    'reports/phase4d-lite/catalogue_hardened_v1.json': 'e7149ab0a2ce4abdfd3b9cf747847ec4e20e3783c60fcc8acea07bfd49894c04',
}
EXPLICITNESS = 'Reviewed topic evidence is not independent per-video explicit/proxy validation.'
LIMITATIONS = [
    'Evidence-gated prototype policy, not an independently validated selection model.',
    'Reviews comprise 102 assisted and 2 manual units; not independent human gold.',
    EXPLICITNESS,
    'Fixed cohort-derived candidate set only; unreviewed creator-topic pairs are not negatives.',
    'No product use, endorsement, sponsorship or campaign-performance inference.',
    'Channel identity may be an individual, brand, news publisher or republisher; suitability needs role review.',
    'Views, likes and comments describe retrieval-time samples, not historical growth.',
    'Evidence is frozen at the recorded cutoff, not refreshed on request.',
]


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                    separators=(',', ':'), allow_nan=False).encode()).hexdigest()


class CandidateRequestError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


class CreatorCandidates:
    def __init__(self, root=None):
        self.root = Path(root) if root else Path(__file__).resolve().parents[1]
        documents = []
        for name, expected in SEALED.items():
            raw = (self.root / name).read_bytes()
            if hashlib.sha256(raw).hexdigest() != expected:
                raise ValueError('Frozen candidate evidence integrity mismatch: ' + name)
            documents.append(json.loads(raw))
        profiles, affinities, self.products, _ = documents
        if fingerprint(sorted(profiles['rows'] + affinities['rows'], key=lambda r: r['fixed']['unit_id'])) != REVIEW_HASH:
            raise ValueError('Frozen review revision mismatch')
        self.profiles = {r['fixed']['creator_id']: r for r in profiles['rows']}
        self.affinities = affinities['rows']

    def context(self, topic_id):
        if topic_id not in self.products:
            raise CandidateRequestError('No frozen creator candidate context for this topic', 404)
        topic = self.products[topic_id]
        return {'data_mode': 'real', 'pins': dict(PINS), 'topic_id': topic_id,
                'query_id': topic['query_id'], 'market': topic['market'],
                'canonical_topic': topic['canonical_topic'],
                'products': [{'product_id': p['product_id'], 'product_name': p['product_name'],
                              'fit_state': p['fit_state'], 'category': p['provenance']['product']['category']}
                             for p in topic['assessments'] if p['fit_state'] in ('direct_fit', 'supporting_fit')],
                'limitations': list(LIMITATIONS), 'policy_status': 'approved_prototype_not_independent_validation'}

    def query(self, params):
        allowed = set(PINS) | {'topic_id', 'query_id', 'product_id', 'market',
                              'required_market_evidence', 'engagement_requirement'}
        if set(params) - allowed:
            raise CandidateRequestError('Unknown request parameters')
        for key, value in PINS.items():
            if key not in params:
                raise CandidateRequestError('Required version pin missing: ' + key)
            if params[key] != value:
                raise CandidateRequestError('Version pin mismatch: ' + key, 409)
        for key in ('topic_id', 'query_id', 'product_id', 'market'):
            if not params.get(key):
                raise CandidateRequestError('Required context missing: ' + key)
        required = params.get('required_market_evidence', 'optional')
        engagement = params.get('engagement_requirement', 'optional')
        if required not in ('optional', 'verified') or engagement not in ('optional', 'available', 'five_valid_samples'):
            raise CandidateRequestError('Invalid market or engagement requirement')
        context = self.context(params['topic_id'])
        if params['query_id'] != context['query_id'] or params['market'] != context['market']:
            raise CandidateRequestError('Only the frozen canonical query / MY scope is reviewed', 422)
        topic = self.products[params['topic_id']]
        product = next((p for p in topic['assessments'] if p['product_id'] == params['product_id']), None)
        if product is None:
            raise CandidateRequestError('Unknown product in frozen catalogue', 404)
        rows = [self.candidate(self.profiles[a['fixed']['creator_id']], a, product, required, engagement)
                for a in self.affinities if a['fixed']['topic_id'] == params['topic_id']
                and a['fixed']['query_id'] == params['query_id']]
        rows.sort(key=lambda r: (STATE_ORDER.index(r['candidate_state']), r['creator_id']))
        return copy.deepcopy({
            'data_mode': 'real', 'policy_status': 'approved_prototype_not_independent_validation',
            'pins': dict(PINS), 'context': {k: params[k] for k in ('topic_id', 'query_id', 'product_id', 'market')},
            'requirements': {'required_market_evidence': required, 'engagement_requirement': engagement},
            'presentation_order': 'Candidate state then stable creator ID; presentation only, not relative merit.',
            'scope': 'Only reviewed creator-topic pairs in the fixed Phase 5C set.',
            'counts': {s: Counter(r['candidate_state'] for r in rows)[s] for s in STATE_ORDER},
            'candidates': rows, 'limitations': list(LIMITATIONS), 'independent_gold': False})

    def candidate(self, profile, affinity, product, required='optional', engagement='optional'):
        pf, pr = profile['fixed'], profile['review']
        af, ar = affinity['fixed'], affinity['review']
        ev = inspect_evidence(profile, affinity)
        p_pool = {v['video_id']: v for v in pf['videos']}
        def videos(ids, pool):
            return [{k: pool[i].get(k) for k in ('video_id', 'title', 'published_at', 'retrieved_at',
                                                'source_ref', 'sample_scope', 'url')} for i in ids]
        return {
            'creator_id': af['creator_id'], 'channel_id': af['channel_id'], 'creator_name': af['display_name'],
            'channel_url': 'https://www.youtube.com/channel/' + af['channel_id'],
            'reviewed_domain': pr['human_domains'], 'specializations': pr['human_specializations'],
            'topic_affinity': ar['human_label'], 'profile_support': pr['human_label'],
            'evidence_sufficiency': {'profile': pr['evidence_sufficiency'], 'affinity': ar['evidence_sufficiency']},
            **decide(profile, affinity, product, required, engagement),
            'evidence_ids': {'profile': pr['selected_video_ids'], 'affinity': ar['selected_video_ids']},
            'evidence': {'profile': videos(pr['selected_video_ids'], p_pool),
                         'affinity': videos(ar['selected_video_ids'], ev['source_pool'])},
            'topic_distinct_publication_dates': ev['distinct_dates'], 'observation_cutoff': af['as_of'],
            'market_evidence': pf['market_evidence'], 'engagement_evidence': pf['engagement'],
            'engagement_available': ev['engagement_available'],
            'review_provenance': {
                'profile_unit_id': pf['unit_id'], 'affinity_unit_id': af['unit_id'],
                'profile_revision': pr['revision'], 'affinity_revision': ar['revision'],
                'revision_hash': REVIEW_HASH, 'original_readiness_group': af['readiness_group'],
                'profile_rationale': pr['notes'], 'affinity_rationale': ar['notes']},
            'review_basis': {'profile': pr['review_basis'], 'affinity': ar['review_basis']},
            'product_fit_provenance': {
                'topic_id': af['topic_id'], 'query_id': af['query_id'], 'market': 'MY',
                'product_id': product['product_id'], 'product_name': product['product_name'],
                'fit_state': product['fit_state'], 'method_version': product['method_version'],
                'catalogue_version': PINS['catalogue_version'], 'assessment_sha256': fingerprint(product),
                'source_ids': product['provenance']['source_ids'],
                'supporting_evidence': product['supporting_evidence'],
                'missing_evidence': product['missing_evidence'], 'contradictions': product['contradictions'],
                'warnings': product['warnings']},
            'policy_version': POLICY_VERSION, 'explicitness_warning': EXPLICITNESS,
            'limitations': list(LIMITATIONS), 'independent_gold': False,
        }
