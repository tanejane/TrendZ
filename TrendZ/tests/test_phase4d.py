"""Deterministic evidence-only rerun checks; no API calls or real-session writes."""
import copy
import json
import tempfile
import unittest
from pathlib import Path

from services.product_catalogue import Catalogue, ROOT
from services.product_fit import ProductFit
from scripts.product_evidence_rerun import harden, evaluate_rerun, explanation_signature, verify_method_freeze


class EvidenceHardeningTests(unittest.TestCase):
    def setUp(self):
        self.baseline = json.loads((ROOT/'data/products/catalogue.json').read_text(encoding='utf-8'))
        self.manifest = json.loads((ROOT/'data/products/evidence_hardening_v1.json').read_text(encoding='utf-8'))
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = Path(self.temp.name)/'catalogue.json'
        self.hardened = harden(self.baseline,self.manifest)
        path.write_text(json.dumps(self.hardened),encoding='utf-8')
        self.service = ProductFit(Catalogue(path))

    def product(self,identifier):
        return next(product for product in self.hardened['products'] if product['product_id']==identifier)

    def test_three_area_updates_preserve_scope_and_leave_oil_unresolved(self):
        self.assertEqual(self.product('lp-ha-30ml')['application_area'],['face'])
        self.assertEqual(self.product('lp-ha-15ml')['field_quality']['application_area']['state'],'partial')
        self.assertEqual(self.product('lrp-mela-30ml')['application_area'],['face','neck','decollete'])
        self.assertIsNone(self.product('lp-oil-control-unspecified')['application_area'])

    def test_no_label_ingredient_backfill(self):
        # Published HA INCI does not acquire niacinamide to agree with old approvals.
        outputs = self.service.topic('niacinamide')
        for identifier in ('lp-ha-15ml','lp-ha-30ml'):
            row = next(p for p in outputs['assessments'] if p['product_id']==identifier)
            self.assertEqual(row['fit_state'],'no_fit')
            self.assertNotIn('niacinamide',self.product(identifier)['normalized_ingredients'])

    def test_formula_fields_conflicted_not_verified_absence(self):
        product = self.product('lrp-b5-30ml')
        self.assertIsNone(product['normalized_ingredients'])
        self.assertEqual(product['field_quality']['raw_ingredients']['state'],'conflicted')
        self.assertTrue(product['unresolved_fields']['formula_identity']['observed_raw_ingredients'])
        row = next(p for p in self.service.topic('retinol')['assessments'] if p['product_id']==product['product_id'])
        self.assertEqual(row['fit_state'],'insufficient_evidence')

    def test_quarantine_and_original_inputs_unchanged(self):
        before = copy.deepcopy(self.baseline)
        harden(self.baseline,self.manifest)
        self.assertEqual(before,self.baseline)
        for identifier in ('lp-pink-100ml','lp-pink-30ml'):
            prior = next(p for p in self.baseline['products'] if p['product_id']==identifier)
            current = copy.deepcopy(self.product(identifier)); current['catalogue_version']=prior['catalogue_version']
            self.assertEqual(current,prior)
            prediction = next(p for p in self.service.topic('hair-oil')['assessments'] if p['product_id']==identifier)
            self.assertEqual(prediction['fit_state'],'insufficient_evidence')

    def test_rejects_wrong_baseline_existing_fields_and_regional_promotion(self):
        broken = copy.deepcopy(self.manifest); broken['baseline_catalogue_version']='wrong'
        with self.assertRaises(ValueError): harden(self.baseline,broken)
        broken = copy.deepcopy(self.manifest)
        broken['application_updates'][0]['product_id']='lp-night-50ml'
        with self.assertRaises(ValueError): harden(self.baseline,broken)
        broken = copy.deepcopy(self.manifest)
        broken['application_updates'][0]['source_ids']=['oil-india-4d']
        with self.assertRaises(ValueError): harden(self.baseline,broken)

    def test_new_explanations_do_not_inherit_support_or_mutate_gold(self):
        old = ProductFit()
        prediction = next(p for p in old.topic('skin-barrier')['assessments'] if p['product_id']=='lp-ha-30ml')
        original = [dict(pair_id='skin-barrier/canonical/lp-ha-30ml',
            fixed=dict(topic_id='skin-barrier',query_id='canonical',product_id='lp-ha-30ml',split='evaluation'),
            context={'intent':old.context('skin-barrier','canonical')[2]},prediction=prediction,
            human_label='supporting_fit',notes='Synthetic fixture only',unsupported_explanation=None)]
        snapshot = copy.deepcopy(original)
        outputs = {topic:self.service.topic(topic) for topic in self.service.intents['topics']}
        metrics,pending,transitions = evaluate_rerun(original,outputs)
        self.assertEqual(original,snapshot)
        self.assertEqual(pending,[original[0]['pair_id']])
        self.assertIsNone(metrics['overall']['unsupported_match_rate'])
        self.assertEqual(transitions[0]['after'],'supporting_fit')

    def test_only_version_stamps_are_ignored_in_explanation_identity(self):
        old = ProductFit().topic('retinol')['matched_products'][0]
        current = copy.deepcopy(old)
        current['supporting_evidence'][0]['catalogue_version']='different'
        self.assertEqual(explanation_signature(old),explanation_signature(current))
        current['warnings'].append('New source conflict')
        self.assertNotEqual(explanation_signature(old),explanation_signature(current))

    def test_method_freeze_rejects_changed_hashes(self):
        verify_method_freeze({'method':'same'},{'method':'same'})
        with self.assertRaises(ValueError):
            verify_method_freeze({'method':'changed'},{'method':'same'})


if __name__=='__main__':
    unittest.main()
