"""Synthetic arithmetic + frozen-context safety oracles; not campaign validation."""
import copy
import hashlib
import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

import app_backend
from services.campaign_context import CampaignContext
from services.campaign_schema import normalize_assumptions, ScenarioError, CALCULATION_VERSION
from services.campaign_economics import calculate
from services.campaign_scenarios import evaluate
from services.creator_candidates import CreatorCandidates, PINS
from services.database import Database
from services.ingestion.base import Observation

ROOT = Path(__file__).resolve().parents[1]


def assumptions():
    return {'objective': 'conversion', 'format': 'short_form_demonstration', 'channel': 'youtube', 'currency': 'MYR',
            'campaign_window': {'start_date': '2026-11-01', 'end_date_exclusive': '2026-12-01'},
            'costs': {'creator_fee': '600', 'media_spend': '200', 'production_cost': '150', 'other_cost': '50'},
            'budget_ceiling': '1200', 'conversion_basis': 'assumed_reach',
            'population': {'value': 1000, 'unit': 'unique_reached_people', 'basis': 'user_entered', 'source_ref': None},
            'conversion_rates': {'low': '0.02', 'base': '0.05', 'high': '0.08'},
            'aov': '50', 'gross_margin_rate': '0.4',
            'manual_candidate_acknowledgement': {'accepted': False, 'reason': None}}


class EconomicsTests(unittest.TestCase):
    def run_case(self, a=None):
        return calculate(normalize_assumptions(a or assumptions()))

    def test_exact_base_formulas(self):
        d = self.run_case()['calculated_outcomes']
        self.assertEqual(Decimal(d['total_cost']['value']), 1000)
        self.assertEqual(Decimal(d['budget_headroom']['value']), 200)
        for key, expected in [('modeled_conversions', 50), ('modeled_revenue', 2500),
                              ('modeled_gross_profit', 1000), ('modeled_net_profit', 0), ('modeled_roi', 0)]:
            self.assertEqual(Decimal(d['base'][key]['value']), expected)

    def test_low_base_high(self):
        rows = self.run_case()['sensitivity']
        self.assertEqual([Decimal(r['modeled_roi']['value']) for r in rows], [Decimal('-.6'), Decimal(0), Decimal('.6')])
        self.assertEqual([Decimal(r['modeled_revenue']['value']) for r in rows], [1000, 2500, 4000])
        self.assertTrue(all(r['changed_variable'] == 'assumed_conversion_rate' for r in rows))

    def test_break_even(self):
        b = self.run_case()['break_even']
        for key, expected in [('revenue', 2500), ('conversions', 50), ('minimum_whole_orders', 50), ('conversion_rate', Decimal('.05'))]:
            self.assertEqual(Decimal(b[key]['value']), expected)

    def test_zero_cost_has_no_infinite_roi(self):
        a = assumptions(); a['costs'] = {k: '0' for k in a['costs']}
        d = self.run_case(a)
        self.assertEqual(d['calculated_outcomes']['base']['modeled_roi']['state'], 'unavailable')
        self.assertEqual(Decimal(d['break_even']['revenue']['value']), 0)
        self.assertEqual(Decimal(d['calculated_outcomes']['base']['modeled_net_profit']['value']), 1000)

    def test_zero_population(self):
        a = assumptions(); a['population']['value'] = 0
        d = self.run_case(a)
        self.assertEqual(Decimal(d['calculated_outcomes']['base']['modeled_roi']['value']), -1)
        self.assertEqual(d['break_even']['conversion_rate']['state'], 'unavailable')

    def test_zero_aov_or_margin(self):
        for field in ('aov', 'gross_margin_rate'):
            a = assumptions(); a[field] = '0'
            d = self.run_case(a)
            self.assertEqual(Decimal(d['calculated_outcomes']['base']['modeled_roi']['value']), -1)
            self.assertEqual(d['break_even']['conversions']['state'], 'unavailable')

    def test_missing_not_zero(self):
        for field in ('population', 'aov', 'gross_margin_rate', 'conversion_rates', 'costs'):
            a = assumptions()
            if field == 'population': a[field]['value'] = None
            elif field == 'conversion_rates': a[field]['base'] = None
            elif field == 'costs': del a[field]['other_cost']
            else: a[field] = None
            self.assertEqual(self.run_case(a)['calculated_outcomes']['base']['modeled_roi']['state'], 'unavailable')

    def test_base_only_does_not_invent_low_high(self):
        a = assumptions(); a['conversion_rates'] = {'base': '0.05'}
        d = self.run_case(a)
        self.assertEqual([r['modeled_roi']['state'] for r in d['sensitivity']], ['unavailable', 'available', 'unavailable'])

    def test_awareness_and_consideration_cost_only(self):
        for objective in ('awareness', 'consideration'):
            a = assumptions(); a['objective'] = objective
            d = self.run_case(a)
            self.assertEqual(d['calculated_outcomes']['total_cost']['state'], 'available')
            self.assertEqual(d['calculated_outcomes']['base']['modeled_roi']['state'], 'unavailable')

    def test_infeasible_rate_not_clamped(self):
        a = assumptions(); a['population']['value'] = 1
        b = self.run_case(a)['break_even']
        self.assertEqual(b['feasibility'], 'infeasible_under_assumptions')
        self.assertEqual(Decimal(b['conversion_rate']['value']), 50)

    def test_rounding_only_display_and_whole_orders(self):
        a = assumptions(); a['aov'] = '33.335'
        d = self.run_case(a)
        self.assertEqual(d['calculated_outcomes']['base']['modeled_revenue']['display_value'], '1666.75')
        self.assertEqual(Decimal(d['break_even']['minimum_whole_orders']['value']), 75)
        a['costs']['creator_fee'] = '600.005'
        self.assertEqual(self.run_case(a)['calculated_outcomes']['total_cost']['display_value'], '1000.01')

    def test_invalid_numerics(self):
        for bad in ('-1', 'NaN', 'Infinity', '1e3', True, 1.1, '1000000000001', []):
            a = assumptions(); a['costs']['creator_fee'] = bad
            with self.assertRaises(ScenarioError): normalize_assumptions(a)

    def test_percentage_bounds_and_range(self):
        for field in ('gross_margin_rate', 'base'):
            a = assumptions()
            if field == 'base': a['conversion_rates'][field] = '1.01'
            else: a[field] = '1.01'
            with self.assertRaises(ScenarioError): normalize_assumptions(a)
        a = assumptions(); a['conversion_rates']['low'] = '0.9'
        with self.assertRaises(ScenarioError): normalize_assumptions(a)

    def test_population_units_and_sources(self):
        for change in ({'value': -1}, {'value': 1.5}, {'unit': 'views'}, {'basis': 'external_planning', 'source_ref': None}, {'basis': 'external_planning', 'source_ref': '   '}):
            a = assumptions(); a['population'].update(change)
            with self.assertRaises(ScenarioError): normalize_assumptions(a)
        a = assumptions(); a['conversion_basis'] = 'target_population'; a['population']['unit'] = 'target_people'
        self.assertEqual(Decimal(self.run_case(a)['calculated_outcomes']['base']['modeled_conversions']['value']), 50)

    def test_dates_enums_unknown_fields(self):
        for change in ({'objective': ''}, {'format': 'viral'}, {'channel': 'instagram'}, {'currency': 'USD'},
                       {'campaign_window': {'start_date': '2026-12-01', 'end_date_exclusive': '2026-11-01'}},
                       {'campaign_window': {'start_date': '20261101', 'end_date_exclusive': '20261201'}}, {'ctr': '0.1'}):
            a = assumptions(); a.update(change)
            with self.assertRaises(ScenarioError): normalize_assumptions(a)


class ScenarioAPITests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidates = CreatorCandidates(ROOT)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'test.sqlite3'
        self.db = Database(self.path)
        self.db.sync_topics(json.loads((ROOT / 'data/tracked_topics.json').read_text()))
        self.context = CampaignContext(self.candidates, self.path, ROOT)
        old = dict(app_backend.app.config); self.addCleanup(app_backend.app.config.update, old)
        app_backend.app.config.update(TESTING=True, DATABASE_PATH=str(self.path))
        self.client = app_backend.app.test_client()

    def params(self, state='qualified_candidate', product='mb-fresh-unspecified', topic='glass-skin'):
        args = {**PINS, 'topic_id': topic, 'query_id': 'canonical', 'market': 'MY', 'product_id': product}
        rows = self.candidates.query(args)['candidates']
        args.update(creator_id=next(r['creator_id'] for r in rows if r['candidate_state'] == state), calculation_version=CALCULATION_VERSION)
        return args

    def body(self, state='qualified_candidate', product='mb-fresh-unspecified', topic='glass-skin'):
        context = self.context.resolve(self.params(state, product, topic))
        return {'schema_version': 'campaign-scenario-v1', 'context_ref': context['context_ref'],
                'calculation_version': CALCULATION_VERSION, 'assumptions': assumptions()}

    def post(self, body):
        return self.client.post('/api/campaign-scenarios/evaluate', json=body)

    def test_pinned_api_success_classification(self):
        response = self.post(self.body())
        self.assertEqual(response.status_code, 200)
        d = response.json
        for key in ('evidence', 'assumptions', 'calculated_outcomes', 'sensitivity', 'break_even', 'warnings', 'provenance', 'limitations'):
            self.assertIn(key, d)
        self.assertEqual(d['output_kind'], 'assumption_based'); self.assertFalse(d['is_prediction'])
        self.assertEqual(Decimal(d['calculated_outcomes']['base']['modeled_revenue']['value']), 2500)

    def test_all_pins_required_and_wrong_versions(self):
        body = self.body()
        for key in body['context_ref']:
            missing = copy.deepcopy(body); del missing['context_ref'][key]
            self.assertIn(self.post(missing).status_code, (400, 409))
        for key in (*PINS, 'trend_snapshot_sha256', 'product_assessment_sha256', 'candidate_sha256', 'context_sha256'):
            changed = copy.deepcopy(body); changed['context_ref'][key] = 'wrong'
            self.assertEqual(self.post(changed).status_code, 409)
        body['calculation_version'] = 'wrong'
        self.assertEqual(self.post(body).status_code, 409)
        del body['calculation_version']
        self.assertEqual(self.post(body).status_code, 400)

    def test_manual_gate_visible_ack_does_not_promote(self):
        body = self.body('manual_review_only')
        self.assertEqual(self.post(body).status_code, 409)
        body['assumptions']['manual_candidate_acknowledgement'] = {'accepted': True, 'reason': 'User explicitly considers limited evidence'}
        response = self.post(body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json['evidence']['creator_candidate']['candidate_state'], 'manual_review_only')
        self.assertTrue(any('Manual-review-only' in w for w in response.json['warnings']))

    def test_unavailable_ineligible_and_quarantine_block(self):
        for state, product, topic in [('unavailable', 'mb-fresh-unspecified', 'glass-skin'), ('ineligible', 'lp-shampoo-440ml', 'glass-skin'), ('unavailable', 'lp-pink-100ml', 'hair-oil')]:
            body = self.body(state, product, topic)
            body['assumptions']['manual_candidate_acknowledgement'] = {'accepted': True, 'reason': 'Cannot override'}
            response = self.post(body)
            self.assertEqual(response.status_code, 422)
            self.assertNotIn('calculated_outcomes', response.json)

    def test_indirect_warning_and_direct_context(self):
        d = self.post(self.body()).json
        self.assertTrue(any('indirect compatibility' in w for w in d['warnings']))
        args = {**PINS, 'topic_id': 'retinol', 'query_id': 'canonical', 'market': 'MY', 'product_id': 'lrp-retinol-30ml'}
        creator = next(r for r in self.candidates.query(args)['candidates'] if r['candidate_state'] == 'strong_evidence_candidate')
        context = self.context.resolve({**args, 'creator_id': creator['creator_id'], 'calculation_version': CALCULATION_VERSION})
        body = self.body(); body['context_ref'] = context['context_ref']
        self.assertEqual(self.post(body).json['evidence']['product_fit']['fit_state'], 'direct_fit')

    def test_stale_evidence_rejected(self):
        body = self.body()
        topic = next(t for t in json.loads((ROOT / 'data/tracked_topics.json').read_text()) if t['id'] == 'glass-skin')
        self.db.ingest([Observation('glass-skin', 'google_trends', topic['query'], 'MY', '2026-01-01',
                        '2026-01-02T00:00:00Z', 'interest_score', 20, 'fixture', query=topic['query'])])
        response = self.post(body)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json['code'], 'stale_context')

    def test_missing_reach_no_inference(self):
        body = self.body(); body['assumptions']['population']['value'] = None
        d = self.post(body).json
        self.assertEqual(d['scenario_state'], 'partial')
        self.assertIsNone(d['assumptions']['population']['value'])
        self.assertEqual(d['calculated_outcomes']['base']['modeled_revenue']['state'], 'unavailable')

    def test_repeated_requests_deterministic_except_created_time(self):
        body = self.body(); a, b = self.post(body).json, self.post(body).json
        del a['provenance']['created_at']; del b['provenance']['created_at']
        self.assertEqual(a, b)

    def test_no_popularity_trend_or_duration_effect_on_economics(self):
        body = self.body(); expected = self.post(body).json['calculated_outcomes']
        altered = copy.deepcopy(self.candidates)
        for profile in altered.profiles.values():
            profile['fixed']['engagement'].update(state='unavailable', views={'median': 10**15}, likes={'median': 0}, like_view_ratio={})
        service = CampaignContext(altered, self.path, ROOT)
        original = service.trend
        def changed_trend(*args):
            d = original(*args); d['dimensions']['dimensions']['demand_momentum']['components'] = {'not_used': 99999}
            d['snapshot_sha256'] = 'fixture-different-evidence'; return d
        with patch.object(service, 'trend', side_effect=changed_trend):
            context = service.resolve(self.params())
            body['context_ref'] = context['context_ref']
            body['assumptions']['campaign_window']['end_date_exclusive'] = '2027-12-01'
            self.assertEqual(evaluate(body, service)['calculated_outcomes'], expected)

    def test_unknown_audience_optional_not_inferred_and_required_blocks(self):
        body = self.body(); d = self.post(body).json
        self.assertEqual(d['evidence']['creator_candidate']['market_evidence']['audience_geography']['state'], 'unknown')
        args = self.params(); args['required_market_evidence'] = 'verified'
        c = self.context.resolve(args); body['context_ref'] = c['context_ref']
        self.assertEqual(self.post(body).status_code, 422)

    def test_query_text_scope_conflict_rejected(self):
        trend = self.context.trend('glass-skin', 'canonical')
        trend['dimensions']['query'] = 'unreviewed different query'
        with patch.object(self.context, 'trend', return_value=trend):
            with self.assertRaisesRegex(ScenarioError, 'conflicts'):
                self.context.resolve(self.params())

    def test_no_upstream_or_source_mutation(self):
        protected = json.loads((ROOT / 'reports/phase5e/implementation-v1/metrics.json').read_text())['protected_sha256']
        protected = {p: digest for p, digest in protected.items()}
        for p in ('services/intelligence_service.py', 'services/intelligence_evidence.py', 'services/intelligence_components.py', 'services/creator_candidate_policy.py'):
            protected[p] = hashlib.sha256((ROOT / p).read_bytes()).hexdigest()
        source_hash = hashlib.sha256(self.path.read_bytes()).hexdigest()
        self.post(self.body())
        for p, digest in protected.items():
            self.assertEqual(hashlib.sha256((ROOT / p).read_bytes()).hexdigest(), digest, p)
        self.assertEqual(hashlib.sha256(self.path.read_bytes()).hexdigest(), source_hash)

    def test_bad_requests_and_duplicate_context(self):
        self.assertEqual(self.client.post('/api/campaign-scenarios/evaluate', data='no JSON').status_code, 400)
        args = list(self.params().items()); args.append(('market', 'MY'))
        self.assertEqual(self.client.get('/api/campaign-scenarios/context', query_string=args).status_code, 400)
        body = self.body(); body['unexpected_score'] = 9
        self.assertEqual(self.post(body).status_code, 400)

    def test_no_response_aliasing_and_budget_warning(self):
        body = self.body(); body['assumptions']['budget_ceiling'] = '10'
        d = self.post(body).json
        self.assertTrue(any('budget ceiling' in w for w in d['warnings']))
        d['evidence']['creator_candidate']['specializations'].append('not_real')
        self.assertNotIn('not_real', self.post(body).json['evidence']['creator_candidate']['specializations'])

    def test_legacy_retired_and_pages_have_no_random_calculator(self):
        for route in ('/api/business-value', '/api/roi-prediction'):
            self.assertEqual(self.client.get(route).status_code, 410)
        for route in ('/roi-insights', '/roi-insights?topic_id=glass-skin', '/campaign-scenario'):
            response = self.client.get(route)
            self.assertEqual(response.status_code, 200)
            self.assertNotIn('Math.random', response.get_data(as_text=True))
        text = (ROOT / 'templates/trend-detail.html').read_text()
        self.assertNotIn('trend.predicted_roi', text)
        self.assertNotIn('trend.revenue_potential', text)


if __name__ == '__main__':
    unittest.main()
