"""Synthetic rule oracles and read-only integration checks, not human relevance gold."""

import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_backend
from services.product_fit import ProductFit
from services.product_catalogue import Catalogue, normalize_ingredient
from services.product_evaluation import evaluate, ranking_metrics
from scripts.product_fit_report import create_review
from scripts.youtube_phase25 import daily_summary
from services.ingestion.youtube_daily import YouTubeDaily


class ProductFitTests(unittest.TestCase):
    def setUp(self):
        self.service = ProductFit()

    def row(self, topic, product, query_id='canonical'):
        return next(row for row in self.service.topic(topic,query_id)['assessments'] if row['product_id']==product)

    def fixture_product(self):
        return copy.deepcopy(next(p for p in self.service.catalogue.products if p['product_id']=='lrp-retinol-30ml'))

    def test_catalogue_size_fields_and_sources(self):
        catalogue = self.service.catalogue
        self.assertEqual(len(catalogue.products),32)
        self.assertEqual({p['category'] for p in catalogue.products},{'skincare','makeup','haircare'})
        for product in catalogue.products:
            self.assertTrue(product['verified_on'])
            self.assertIn(product['source_id'],catalogue.sources)

    def test_exact_ingredient_direct(self):
        row = self.row('niacinamide','lrp-retinol-30ml')
        self.assertEqual(row['fit_state'],'direct_fit')
        self.assertEqual(row['dimensions']['ingredient_agreement']['matched'],['niacinamide'])

    def test_benefit_supporting_and_direct(self):
        self.assertEqual(self.row('skin-barrier','lp-night-50ml')['fit_state'],'supporting_fit')
        self.assertEqual(self.row('skin-barrier','lrp-b5-30ml')['fit_state'],'direct_fit')

    def test_same_category_negative(self):
        self.assertEqual(self.row('lip-tint','mb-fresh-unspecified')['fit_state'],'no_fit')
        self.assertEqual(self.row('hair-oil','lp-shampoo-440ml')['fit_state'],'no_fit')

    def test_missing_ingredients_abstains(self):
        product = self.fixture_product()
        product['normalized_ingredients'] = None
        product['ingredient_completeness'] = 'unknown'
        product['field_quality']['normalized_ingredients'] = {'state':'unknown','evidence':[]}
        intent = self.service.context('niacinamide','canonical')[2]
        row = self.service.assess(product,intent)
        self.assertEqual(row['fit_state'],'insufficient_evidence')
        self.assertTrue(row['missing_evidence'])

    def test_conflicting_source_quarantined(self):
        self.assertEqual(self.row('hair-oil','lp-pink-100ml')['fit_state'],'insufficient_evidence')

    def test_conflicting_required_field_abstains(self):
        product = self.fixture_product()
        product['field_quality']['product_format']['state'] = 'conflict'
        row = self.service.assess(product,self.service.context('niacinamide','canonical')[2])
        self.assertEqual(row['fit_state'],'insufficient_evidence')
        self.assertFalse(any(ref['field']=='product_format' for ref in row['supporting_evidence']))

    def test_no_retinoid_derivative_equivalence(self):
        self.assertNotEqual(normalize_ingredient('RETINYL PALMITATE'),'retinol')
        product = self.fixture_product()
        product['normalized_ingredients'] = ['retinyl palmitate']
        product['ingredient_completeness'] = 'complete'
        self.assertEqual(self.service.assess(product,self.service.context('retinol','canonical')[2])['fit_state'],'no_fit')

    def test_aliases_do_not_aggregate(self):
        self.assertEqual(self.row('niacinamide','lp-night-50ml')['fit_state'],'no_fit')
        self.assertEqual(self.row('niacinamide','lp-night-50ml','broad')['fit_state'],'direct_fit')
        self.assertEqual(self.row('lip-tint','mb-teddy-unspecified')['fit_state'],'direct_fit')
        self.assertEqual(self.row('lip-tint','mb-teddy-unspecified','stain')['fit_state'],'no_fit')
        self.assertEqual(self.service.topic('lip-tint','stain')['query'],'lip stain')

    def test_unknown_topic_and_query(self):
        for topic,query in [('unknown','canonical'),('retinol','unknown')]:
            with self.assertRaises(KeyError):
                self.service.topic(topic,query)
        with self.assertRaises(KeyError):
            self.service.resolve('unmatched hashtag')

    def test_occasion_never_automatically_direct(self):
        result = self.service.topic('deepavali-glam')
        self.assertTrue(result['matched_products'])
        self.assertTrue(all(row['fit_state']=='supporting_fit' for row in result['matched_products']))
        self.assertTrue(all(not row['dimensions']['occasion_agreement']['explicit_match'] for row in result['matched_products']))

    def test_provenance_explanations_use_literal_fields_only(self):
        for topic in self.service.intents['topics']:
            for row in self.service.topic(topic)['matched_products']:
                self.assertTrue(row['supporting_evidence'])
                for ref in row['supporting_evidence']:
                    self.assertEqual(ref['value'],row['provenance']['product'][ref['field']])
                    self.assertEqual(ref['source'],self.service.catalogue.sources[ref['source_id']])
                    self.assertEqual(ref['catalogue_version'],self.service.catalogue.version)
                    self.assertTrue(ref['basis'])
                for claim in row['provenance']['product']['manufacturer_claims'] or []:
                    self.assertIs(claim['independently_verified'],False)

    def test_unsupported_injected_ingredient_cannot_match(self):
        product = self.fixture_product()
        product['normalized_ingredients'] = ['retinol']
        product['ingredient_completeness'] = 'partial'
        product['field_quality']['normalized_ingredients'] = {'state':'unknown','evidence':[]}
        self.assertEqual(self.service.assess(product,self.service.context('retinol','canonical')[2])['fit_state'],'insufficient_evidence')

    def test_catalogue_rejects_unprovenanced_values(self):
        with tempfile.TemporaryDirectory() as directory:
            document = copy.deepcopy(self.service.catalogue.document)
            document['products'][0]['field_quality']['brand']['evidence'] = []
            path = Path(directory)/'bad.json'
            path.write_text(json.dumps(document))
            with self.assertRaises(ValueError):
                Catalogue(path)

    def test_api_readonly_all_topics_and_legacy_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            database = Path(directory)/'must-not-exist.sqlite3'
            before = hashlib.sha256(self.service.catalogue.path.read_bytes()).hexdigest()
            with patch.dict(app_backend.app.config,{'DATABASE_PATH':str(database),'DATA_MODE':'real'}):
                with patch.object(app_backend,'trend_service',side_effect=AssertionError('Must not initialize trend DB')):
                    client = app_backend.app.test_client()
                    for topic in self.service.intents['topics']:
                        response = client.get('/api/product-fit/'+topic)
                        self.assertEqual(response.status_code,200)
                        self.assertEqual(response.json['catalogue_version'],self.service.catalogue.version)
                    self.assertEqual(client.post('/api/product-fit/retinol').status_code,405)
                    self.assertEqual(client.get('/api/product-fit/unknown').status_code,404)
                    self.assertEqual(client.get('/api/product-fit/retinol?query_id=unknown').status_code,404)
                    self.assertEqual(client.get('/api/malaysia/hashtag-products/nonsense').status_code,404)
                    self.assertEqual(client.get('/api/malaysia/product-mapping').status_code,200)
                    payload = client.get('/api/malaysia/hashtag-products/glassskin').json['recommendations']
                    for field in ('hashtag','total_products','target_audience','look_style','estimated_cost','estimated_total_cost'):
                        self.assertIn(field,payload)
                    self.assertIsNone(payload['estimated_cost'])
                    self.assertIsNone(payload['opportunity_score'])
            self.assertFalse(database.exists())
            self.assertEqual(before,hashlib.sha256(self.service.catalogue.path.read_bytes()).hexdigest())

    def test_unknown_category_cannot_fallback(self):
        mapping = app_backend.product_mapping_for_trend({'id':'not-a-topic','name':'Unknown','category':'unknown','data_mode':'real'})
        self.assertEqual(mapping['data_mode'],'unavailable')
        self.assertEqual(mapping['recommended_products'],[])

    def test_human_evaluation_pending_and_disjoint(self):
        review = create_review(self.service)
        self.assertEqual(len(review['rows']),256)
        report = evaluate(self.service,review)
        self.assertTrue(all(row['human_label'] is None for row in review['rows']))
        for topic in self.service.intents['topics']:
            self.assertEqual(report['human_review'][topic]['evaluation']['state'],'unavailable')
            self.assertIsNone(report['human_review'][topic]['evaluation']['metrics'])
            self.assertEqual(report['mechanical_checks'][topic]['explanation_reference_traceability'],1)

    def test_evaluation_rejects_missing_pairs_and_invalid_labels(self):
        review = create_review(self.service)
        review['rows'].pop()
        with self.assertRaises(ValueError):
            evaluate(self.service,review)
        review = create_review(self.service)
        review['rows'][0]['human_label'] = 'excellent'
        with self.assertRaises(ValueError):
            evaluate(self.service,review)

    def test_synthetic_ranking_math_not_real_human_results(self):
        labels = {'a':'direct_fit','b':'supporting_fit','c':'no_fit','d':'insufficient_evidence'}
        result = ranking_metrics(['a','b'],labels)
        self.assertEqual(result['precision_at_5'],.4)
        self.assertEqual(result['ndcg_at_5'],1)
        self.assertEqual(result['catalogue_bounded_recall'],1)
        self.assertIsNone(ranking_metrics(['a'],{'a':None}))


class DailySummaryTests(unittest.TestCase):
    def collect(self,failed=False):
        def transport(endpoint,params):
            if endpoint == 'search':
                return {'items':[]}
            if failed:
                raise RuntimeError('Fixture API failure')
            return {'items':[{'id':'v1','statistics':{'viewCount':'8'}}]}
        adapter = YouTubeDaily(transport=transport,key='fixture',clock=lambda:'2026-10-15T00:00:00+00:00')
        topics = [{'id':'retinol','query':'retinol skincare','market':'MY'}]
        cohorts = [{'cohort_id':'c1','topic_id':'retinol','query_id':'canonical',
                    'members':[{'video_id':'v1','published_at':'2026-10-01T00:00:00Z'}]}]
        return adapter.collect_day(topics,cohorts,'2026-10-14','fixture-audit')

    def test_daily_summary_partial_like_not_failed_request(self):
        summary = daily_summary(self.collect())
        self.assertEqual(summary['discovery_searches_completed'],1)
        self.assertEqual(summary['cohort_stats_requests_completed'],1)
        self.assertEqual(summary['cohort_videos_snapshotted'],1)
        self.assertEqual(summary['requests_failed'],0)
        self.assertEqual(summary['video_records_partial'],1)
        self.assertEqual(summary['snapshot_dates'],['2026-10-15'])

    def test_daily_summary_failure_not_counted_snapshot(self):
        summary = daily_summary(self.collect(True))
        self.assertEqual(summary['requests_failed'],1)
        self.assertEqual(summary['cohort_stats_requests_completed'],0)
        self.assertEqual(summary['cohort_videos_snapshotted'],0)
        self.assertEqual(summary['video_records_unavailable'],1)


if __name__ == '__main__':
    unittest.main()
