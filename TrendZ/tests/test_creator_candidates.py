"""Deterministic policy parity/safety tests; no live API calls or review writes."""

import copy
import hashlib
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest.mock import patch

import app_backend
from services.creator_candidates import CreatorCandidates, PINS, SEALED
from services.creator_candidate_policy import decide, STATE_ORDER, STATES

ROOT = Path(__file__).resolve().parents[1]


def load(name):
    return json.loads((ROOT / name).read_text(encoding='utf-8'))


def fixture():
    videos = [{'video_id': 'v0', 'published_at': '2026-10-01T00:00:00Z', 'source_ref': {'run_id': 'r'}},
              {'video_id': 'v1', 'published_at': '2026-10-15T00:00:00Z', 'source_ref': {'run_id': 'r'}}]
    p = {'fixed': {'videos': videos, 'engagement': {'state': 'available', 'views': {'median': 100},
         'likes': {'median': 10}, 'like_view_ratio': {'median_of_video_ratios': .1, 'valid_denominators': 2}},
         'market_evidence': {'audience_geography': {'state': 'unknown', 'value': None}}},
         'review': {'human_label': 'supported', 'human_domains': ['beauty'],
         'human_specializations': ['skincare'], 'selected_video_ids': ['v0', 'v1'],
         'evidence_sufficiency': 'sufficient', 'explanation_support': 'supported', 'notes': 'Reviewed profile'}}
    a = {'fixed': {'videos': copy.deepcopy(videos), 'prior_videos': []},
         'review': {'human_label': 'weak_affinity', 'selected_video_ids': ['v0'],
         'evidence_sufficiency': 'partial', 'explanation_support': 'supported', 'notes': 'Explicit scoped evidence'}}
    product = {'fit_state': 'direct_fit', 'provenance': {'product': {'category': 'skincare', 'requires_review': False}}}
    return p, a, product


class CandidatePolicyTests(unittest.TestCase):
    def setUp(self):
        self.p, self.a, self.product = fixture()

    def state(self, **kwargs):
        return decide(self.p, self.a, self.product, **kwargs)['candidate_state']

    def high(self):
        self.a['review'].update(human_label='moderate_affinity', selected_video_ids=['v0', 'v1'], evidence_sufficiency='sufficient')

    def test_weak_is_qualified_not_strong(self):
        self.assertEqual(self.state(), 'qualified_candidate')

    def test_strong_gate(self):
        self.high()
        self.assertEqual(self.state(), 'strong_evidence_candidate')

    def test_one_video_and_one_date_fail(self):
        self.high()
        self.a['review']['selected_video_ids'] = ['v0']
        self.assertEqual(self.state(), 'unavailable')
        self.a['review']['selected_video_ids'] = ['v0', 'v1']
        self.a['fixed']['videos'][1]['published_at'] = self.a['fixed']['videos'][0]['published_at']
        self.assertEqual(self.state(), 'unavailable')

    def test_partial_profile_not_strong(self):
        self.high()
        self.p['review']['human_label'] = 'partially_supported'
        self.assertEqual(self.state(), 'qualified_candidate')

    def test_insufficient_is_not_ineligible(self):
        self.a['review']['human_label'] = 'insufficient_evidence'
        self.assertEqual(self.state(), 'unavailable')
        self.a['review']['human_label'] = 'no_affinity'
        self.assertEqual(self.state(), 'ineligible')

    def test_product_blocks_precede_creator_gates(self):
        self.a['review']['human_label'] = 'insufficient_evidence'
        self.product['fit_state'] = 'no_fit'
        self.assertEqual(self.state(), 'ineligible')
        self.product['fit_state'] = 'insufficient_evidence'
        self.assertEqual(self.state(), 'unavailable')

    def test_product_quarantine(self):
        self.product['provenance']['product']['requires_review'] = True
        self.assertEqual(self.state(), 'unavailable')

    def test_market_unknown_not_penalty_until_required(self):
        self.assertEqual(self.state(), 'qualified_candidate')
        self.assertEqual(self.state(required_market_evidence='verified'), 'unavailable')
        self.p['fixed']['market_evidence']['audience_geography'] = {'state': 'verified', 'value': ['MY']}
        self.assertEqual(self.state(required_market_evidence='verified'), 'qualified_candidate')

    def test_engagement_optional_and_sample_requirements(self):
        self.assertEqual(self.state(engagement_requirement='available'), 'qualified_candidate')
        self.assertEqual(self.state(engagement_requirement='five_valid_samples'), 'unavailable')
        self.p['fixed']['engagement']['state'] = 'unavailable'
        self.assertEqual(self.state(), 'qualified_candidate')
        self.assertEqual(self.state(engagement_requirement='available'), 'unavailable')

    def test_missing_specialization_manual_only(self):
        self.product['provenance']['product']['category'] = 'makeup'
        self.assertEqual(self.state(), 'manual_review_only')

    def test_corrected_profile_not_vetoed_by_original_explanation(self):
        self.p['review']['explanation_support'] = 'unsupported'
        self.assertEqual(self.state(), 'qualified_candidate')

    def test_unlinked_proxy_and_no_rationale_abstain(self):
        for change in ('unlinked', 'proxy', 'rationale'):
            self.setUp()
            if change == 'unlinked': self.a['fixed']['videos'][0]['source_ref'] = {}
            if change == 'proxy': self.a['review']['notes'] = 'Assisted\n{"proxy_video_ids":["v0"]}'
            if change == 'rationale': self.a['review']['notes'] = ''
            self.assertEqual(self.state(), 'unavailable')


class CandidateIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.service = CreatorCandidates(ROOT)
        cls.golden = load('reports/phase5d/design-v1/opportunity_candidates.json')['rows']
        cls.client = app_backend.app.test_client()

    def params(self, topic='glass-skin', product='mb-fresh-unspecified', **kwargs):
        return {**PINS, 'topic_id': topic, 'query_id': 'canonical', 'market': 'MY', 'product_id': product, **kwargs}

    def test_all_264_frozen_positive_contexts_exact_h1_parity(self):
        actual = {}
        for topic, pred in self.service.products.items():
            for product in pred['assessments']:
                if product['fit_state'] not in ('direct_fit', 'supporting_fit'): continue
                for row in self.service.query(self.params(topic, product['product_id']))['candidates']:
                    actual[(topic, product['product_id'], row['creator_id'])] = row
        self.assertEqual(len(actual), 264)
        for frozen in self.golden:
            row = actual[(frozen['topic_id'], frozen['product_id'], frozen['creator_id'])]
            self.assertEqual(row['candidate_state'], STATES[frozen['hypothesis_band']])
            self.assertEqual(row['reasons'], frozen['reasons'])
            self.assertEqual(row['warnings'], frozen['quality_warnings'])
            self.assertEqual(row['matched_specialization'], frozen['matched_specializations'])
        self.assertEqual(Counter(r['candidate_state'] for r in actual.values()),
                         Counter(strong_evidence_candidate=29, qualified_candidate=119, manual_review_only=54, unavailable=62))

    def test_all_1784_blocked_contexts_parity(self):
        cache = {}
        for frozen in load('reports/phase5d/design-v1/blocked_product_contexts.json'):
            key = (frozen['topic_id'], frozen['product_id'])
            if key not in cache:
                cache[key] = {r['creator_id']: r for r in self.service.query(self.params(*key))['candidates']}
            self.assertEqual(cache[key][frozen['creator_id']]['candidate_state'], frozen['candidate_state'])

    def test_sarthak_product_specific_behavior(self):
        def state(product):
            return next(r['candidate_state'] for r in self.service.query(self.params(product=product))['candidates'] if r['creator_name'] == 'Sarthak')
        self.assertEqual(state('mb-fresh-unspecified'), 'qualified_candidate')
        self.assertEqual(state('lp-ha-15ml'), 'manual_review_only')

    def test_popularity_invariance_all_positive_contexts(self):
        altered = copy.deepcopy(self.service)
        for p in altered.profiles.values():
            p['fixed']['engagement'].update(state='unavailable', views={'median': None}, likes={'median': 10**20}, like_view_ratio={})
        for frozen in self.golden:
            a = next(a for a in altered.affinities if a['fixed']['creator_id'] == frozen['creator_id'] and a['fixed']['topic_id'] == frozen['topic_id'])
            product = next(p for p in altered.products[frozen['topic_id']]['assessments'] if p['product_id'] == frozen['product_id'])
            self.assertEqual(altered.candidate(altered.profiles[frozen['creator_id']], a, product)['candidate_state'], STATES[frozen['hypothesis_band']])

    def test_stable_order_not_popularity(self):
        rows = self.service.query(self.params())['candidates']
        self.assertEqual(rows, sorted(rows, key=lambda r: (STATE_ORDER.index(r['candidate_state']), r['creator_id'])))

    def test_unknown_my_audience_all_unavailable_when_required(self):
        rows = self.service.query(self.params(required_market_evidence='verified'))['candidates']
        self.assertEqual({r['candidate_state'] for r in rows}, {'unavailable'})

    def test_bad_missing_and_duplicate_pins(self):
        for key in PINS:
            for mode, code in [('missing', 400), ('bad', 409)]:
                args = self.params()
                if mode == 'missing': del args[key]
                else: args[key] = 'wrong'
                self.assertEqual(self.client.get('/api/creator-candidates', query_string=args).status_code, code)
        args = list(self.params().items()) + [('market', 'MY')]
        self.assertEqual(self.client.get('/api/creator-candidates', query_string=args).status_code, 400)

    def test_validation_and_no_alias_or_market_fallback(self):
        for args, code in [(self.params(query_id='alias'), 422), (self.params(market='US'), 422),
                           (self.params(product='missing'), 404), (self.params(topic='missing'), 404),
                           (self.params(required_market_evidence='true'), 400),
                           (self.params(engagement_requirement='1000_views'), 400), (self.params(score='x'), 400)]:
            self.assertEqual(self.client.get('/api/creator-candidates', query_string=args).status_code, code)

    def test_read_only_api_schema_no_score_or_rank_field(self):
        response = self.client.get('/api/creator-candidates', query_string=self.params())
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body['data_mode'], 'real')
        self.assertEqual(body['pins'], PINS)
        def check(value):
            if isinstance(value, dict):
                for key, item in value.items():
                    self.assertFalse('score' in key.lower() or 'rank' in key.lower(), key)
                    check(item)
            elif isinstance(value, list):
                for item in value: check(item)
        check(body)
        self.assertEqual(self.client.post('/api/creator-candidates').status_code, 405)

    def test_no_protected_file_or_review_mutation_and_no_return_aliasing(self):
        paths = list(SEALED) + ['data/creators/review_sessions/local.sqlite3', 'reports/phase2-measured/pilot.sqlite3',
                              'data/products/review_sessions/local.sqlite3']
        paths += list(load('reports/phase4d-lite/product_fit_v1_freeze.json')['rule_sha256'])
        before = {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths}
        result = self.service.query(self.params())
        result['candidates'][0]['specializations'].append('mutated')
        self.assertNotIn('mutated', self.service.query(self.params())['candidates'][0]['specializations'])
        for topic in self.service.products:
            self.client.get('/api/creator-candidates/context/' + topic)
        self.client.get('/api/creator-candidates', query_string=self.params())
        self.assertEqual(before, {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths})

    def test_frozen_integrity_failure_is_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            first = next(iter(SEALED))
            (root / first).parent.mkdir(parents=True)
            (root / first).write_text('{}')
            with self.assertRaisesRegex(ValueError, 'integrity mismatch'):
                CreatorCandidates(root)
        with patch('app_backend.creator_candidate_service', side_effect=ValueError('bad digest')):
            self.assertEqual(self.client.get('/api/creator-candidates', query_string=self.params()).status_code, 503)

    def test_context_bootstrap_is_positive_frozen_and_versioned(self):
        body = self.client.get('/api/creator-candidates/context/glass-skin').get_json()
        self.assertEqual(body['pins'], PINS)
        self.assertEqual(len(body['products']), 10)
        self.assertTrue(all(p['fit_state'] in ('direct_fit', 'supporting_fit') for p in body['products']))

    def test_existing_product_fit_unchanged(self):
        freeze = load('reports/phase4d-lite/product_fit_v1_freeze.json')
        for path, digest in freeze['rule_sha256'].items():
            self.assertEqual(hashlib.sha256((ROOT / path).read_bytes()).hexdigest(), digest)
        body = self.client.get('/api/product-fit/glass-skin').get_json()
        self.assertEqual(body['catalogue_version'], 'my-curated-2026-10-15-v1')

    def test_detail_integration_in_both_demo_and_measured_without_db_writes(self):
        demo = {**app_backend.TRENDS[0], 'data_mode': 'demo'}
        measured = {'id': 'glass-skin', 'name': 'Glass Skin', 'data_mode': 'real', 'market': 'MY',
                    'metrics': {'series': [], 'cross_source_confirmation': {'state': 'unavailable', 'reason': 'No history'}},
                    'provenance': []}
        for trend in (demo, measured):
            with patch('app_backend.find_trend', return_value=trend):
                response = self.client.get('/trend-detail/glass-skin')
            self.assertEqual(response.status_code, 200)
            html = response.get_data(as_text=True)
            self.assertEqual(html.count('data-creator-topic="glass-skin"'), 1)
            self.assertIn('creator-candidates.js', html)
            self.assertIn('Select a positive product', html)


if __name__ == '__main__':
    unittest.main()
