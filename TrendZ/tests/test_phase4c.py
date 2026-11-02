"""Synthetic human judgments in temporary sessions only; never label the real review."""

import copy
import hashlib
import json
import shutil
import sqlite3
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path

from services.product_catalogue import ROOT
from services.product_fit import ProductFit
from services.product_evaluation import evaluate
from services.product_review import ReviewStore, ReviewConflict, FROZEN_FILES, pair_id
from services.product_validation import analyze, validation_report, markdown_report
from scripts.product_review import create_app


class TokenParser(HTMLParser):
    token = None
    def handle_starttag(self,tag,attributes):
        attrs = dict(attributes)
        if tag=='meta' and attrs.get('name')=='review-token':
            self.token = attrs['content']


class ReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in FROZEN_FILES:
            target = self.root/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(ROOT/name,target)
        self.path = self.root/'review.sqlite3'
        self.store = ReviewStore(self.path,self.root)
        self.store.initialize()

    def complete_fixture(self,explanations=True):
        # Test-only synthetic labels: not written to the user's session or fixed JSON.
        with self.store.connect() as db:
            for row in self.store.rows():
                support = False if explanations and row['prediction']['fit_state'] in ('direct_fit','supporting_fit') else None
                db.execute('UPDATE labels SET human_label=?,unsupported_explanation=?,reviewer=?,reviewed_on=? WHERE pair_id=?',
                           (row['prediction']['fit_state'],support,'synthetic-test','2026-10-15',row['pair_id']))

    def test_blank_fixed_pairs_and_provenance(self):
        rows = self.store.rows()
        self.assertEqual(len(rows),256)
        self.assertTrue(all(row['human_label'] is None for row in rows))
        baseline = json.loads((self.root/'data/products/human_review.json').read_text())
        self.assertEqual([r['pair_id'] for r in rows],[pair_id(row) for row in baseline['rows']])
        self.assertTrue(all(row['prediction']['provenance']['catalogue_version']==baseline['catalogue_version'] for row in rows))
        self.assertEqual(self.store.summary()['labelled'],0)

    def test_save_resume_export_preserves_fixed_identity(self):
        row = self.store.rows()[0]
        self.store.save(row['pair_id'],'insufficient_evidence','Manual source check',None,0,'Reviewer')
        resumed = ReviewStore(self.path,self.root)
        resumed.initialize()
        updated = resumed.rows()[0]
        self.assertEqual(updated['human_label'],'insufficient_evidence')
        self.assertEqual(updated['revision'],1)
        self.assertEqual(updated['notes'],'Manual source check')
        export = resumed.export()
        original = resumed.metadata()['baseline']
        for before,after in zip(original['rows'],export['rows']):
            for key in ('topic_id','query_id','product_id','family_id','split','sampling_stratum_machine_only'):
                self.assertEqual(before[key],after[key])
        evaluate(ProductFit(),export)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('UPDATE pairs SET fixed_json=? WHERE pair_id=?',('{}',row['pair_id']))

    def test_only_four_labels_validated_atomically(self):
        row = self.store.rows()[0]
        for label in ('relevant','',None,{},['direct_fit']):
            with self.assertRaises(ValueError):
                self.store.save(row['pair_id'],label,'',None,0)
        with self.assertRaises(ValueError):
            self.store.save(row['pair_id'],'direct_fit','x'*1001,None,0)
        with self.assertRaises(ValueError):
            self.store.save(row['pair_id'],'direct_fit','',1,0)
        self.assertEqual(self.store.rows()[0]['revision'],0)

    def test_all_four_labels_persist_and_no_prediction_copy(self):
        rows = self.store.rows()
        for row,label in zip(rows,('direct_fit','supporting_fit','no_fit','insufficient_evidence')):
            self.store.save(row['pair_id'],label,'Chosen by synthetic reviewer',None,0)
        self.assertEqual([r['human_label'] for r in self.store.rows()[:4]],
                         ['direct_fit','supporting_fit','no_fit','insufficient_evidence'])
        self.assertTrue(all(r['human_label'] is None for r in self.store.rows()[4:]))

    def test_optimistic_concurrency_and_explicit_clear(self):
        row = self.store.rows()[0]
        self.store.save(row['pair_id'],'direct_fit','A',None,0)
        with self.assertRaises(ReviewConflict):
            self.store.save(row['pair_id'],'no_fit','Other tab',None,0)
        with self.assertRaises(ValueError):
            self.store.save(row['pair_id'],None,'',None,1)
        self.store.save(row['pair_id'],None,'',None,1,reset=True)
        self.assertIsNone(self.store.rows()[0]['human_label'])
        self.assertEqual(self.store.rows()[0]['revision'],2)

    def test_changed_method_blocks_writes_and_report_but_preserves_frozen_evidence(self):
        path = self.root/'services/product_fit.py'
        path.write_text(path.read_text()+'\n# synthetic stale-version fixture\n')
        self.assertTrue(self.store.summary()['stale'])
        row = self.store.rows()[0]
        with self.assertRaises(ReviewConflict):
            self.store.save(row['pair_id'],'no_fit','',None,0)
        report = self.store.finalized_report()
        self.assertEqual(report['state'],'pending')
        self.assertIsNone(report['recommendation'])
        self.assertTrue(row['prediction']['supporting_evidence'])
        path.unlink()
        self.assertTrue(self.store.summary()['stale'])
        self.assertTrue(self.store.rows()[0]['prediction']['supporting_evidence'])

    def test_report_gated_on_labels_and_independent_explanation_checks(self):
        self.assertEqual(self.store.finalized_report()['state'],'pending')
        self.complete_fixture(False)
        self.assertEqual(self.store.summary()['labelled'],256)
        self.assertGreater(self.store.summary()['pending_explanation_checks'],0)
        report = self.store.finalized_report()
        self.assertEqual(report['state'],'pending')
        self.assertIsNone(report['metrics'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],0)

    def test_complete_report_and_immutable_report_revisions(self):
        self.complete_fixture()
        report = self.store.finalized_report()
        self.assertEqual(report['state'],'complete')
        self.assertEqual(report['metrics']['pairs'],256)
        self.assertEqual(sum(sum(values.values()) for values in report['metrics']['confusion_matrix']['counts'].values()),256)
        self.assertEqual(report['metrics']['unsupported_match_rate'],0)
        self.assertEqual(len(report['by_topic']),8)
        self.assertEqual(report['recommendation']['state'],'retain_current_baseline_within_tested_scope')
        self.assertEqual(self.store.finalized_report()['revision_hash'],report['revision_hash'])
        row = self.store.rows()[0]
        self.store.save(row['pair_id'],'no_fit','Changed synthetic judgment',None,row['revision'])
        second = self.store.finalized_report()
        self.assertNotEqual(report['revision_hash'],second['revision_hash'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],2)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM reports')
        self.assertIn('Confusion Matrix',markdown_report(second))

    def test_precision_ndcg_recall_confusion_and_error_patterns(self):
        rows = copy.deepcopy(self.store.rows())
        # Synthetic gold: make exactly one predicted match wrong and one withheld pair relevant.
        for row in rows:
            row['human_label'] = row['prediction']['fit_state']
            row['unsupported_explanation'] = False if row['prediction']['fit_state'] in ('direct_fit','supporting_fit') else None
        positive = next(r for r in rows if r['fixed']['topic_id']=='hair-oil' and r['prediction']['fit_state']=='direct_fit')
        positive['human_label'] = 'no_fit'; positive['unsupported_explanation'] = True
        negative = next(r for r in rows if r['fixed']['topic_id']=='hair-oil' and r['prediction']['fit_state']=='insufficient_evidence')
        negative['human_label'] = 'direct_fit'
        report = validation_report(rows,self.store.metadata())
        metrics = report['by_topic']['hair-oil']
        self.assertEqual(metrics['false_positive_count'],1)
        self.assertEqual(metrics['false_negative_count'],1)
        self.assertEqual(metrics['false_negatives_abstained'],1)
        self.assertEqual(metrics['ranking_by_topic']['hair-oil']['precision_at_5'],.6)
        self.assertEqual(metrics['ranking_by_topic']['hair-oil']['catalogue_bounded_recall'],.75)
        self.assertLess(metrics['ranking_by_topic']['hair-oil']['ndcg_at_5'],1)
        self.assertEqual(metrics['unsupported_match_rate'],.25)
        self.assertEqual(metrics['same_category_overmatching']['confirmed_false_positives'],1)
        self.assertEqual(metrics['confusion_matrix']['counts']['no_fit']['direct_fit'],1)
        self.assertTrue(metrics['false_negative_patterns'])
        self.assertEqual(report['recommendation']['state'],'review_adjustments_warranted')

    def test_uncertain_gold_not_counted_as_confirmed_false_positive(self):
        rows = copy.deepcopy(self.store.rows())
        for row in rows:
            row['human_label'] = row['prediction']['fit_state']
            row['unsupported_explanation'] = False if row['prediction']['fit_state'] in ('direct_fit','supporting_fit') else None
        positive = next(r for r in rows if r['prediction']['fit_state']=='direct_fit')
        positive['human_label'] = 'insufficient_evidence'
        report = validation_report(rows,self.store.metadata())
        self.assertEqual(report['metrics']['false_positive_count'],0)
        self.assertEqual(report['metrics']['predicted_positive_human_insufficient_count'],1)

    def test_abstention_missing_evidence_not_claimed_causal(self):
        self.complete_fixture()
        report = self.store.finalized_report()
        tags = {row['pattern'] for row in report['metrics']['abstention_evidence_gaps']}
        self.assertIn('missing_application_area',tags)
        self.assertIn('incomplete_ingredient_evidence',tags)
        self.assertTrue(any('do not establish why' in text for text in report['limitations']))
        self.assertEqual(report['metrics']['abstention_rate'],20/256)

    def test_missing_benefit_diagnostic_is_separate_from_ingredient_gaps(self):
        row = copy.deepcopy(self.store.rows()[0])
        row['human_label'] = 'direct_fit'
        row['prediction']['fit_state'] = 'insufficient_evidence'
        row['prediction']['missing_evidence'] = ['manufacturer_claims is missing or conflicted']
        report = analyze([row],self.store.metadata()['outputs'])
        tags = {value['pattern'] for value in report['abstention_evidence_gaps']}
        self.assertIn('missing_declared_benefits',tags)
        self.assertNotIn('missing_ingredient_evidence',tags)

    def test_final_validation_requires_all_fixed_pairs(self):
        self.complete_fixture()
        with self.assertRaises(ValueError):
            validation_report(self.store.rows()[:-1],self.store.metadata())

    def client(self):
        app = create_app(self.store)
        app.config['TESTING'] = True
        client = app.test_client()
        parser = TokenParser(); parser.feed(client.get('/').get_data(as_text=True))
        return client,{'X-Review-Token':parser.token}

    def test_api_blank_resume_and_export_no_get_writes(self):
        client,headers = self.client()
        summary = client.get('/api/review').json
        self.assertEqual(summary['labelled'],0)
        identifier = summary['pairs'][0]['pair_id']
        row = client.get('/api/review/pair',query_string={'pair_id':identifier}).json
        self.assertIsNone(row['human_label'])
        result = client.post('/api/review/label',json={'pair_id':identifier,'human_label':'supporting_fit',
                              'notes':'Human note','revision':0},headers=headers)
        self.assertEqual(result.status_code,200)
        self.assertEqual(client.get('/api/review/export').json['rows'][0]['human_label'],'supporting_fit')
        self.assertEqual(client.get('/api/review/report').json['state'],'pending')
        self.assertEqual(client.post('/api/review/finalize',json={},headers=headers).status_code,409)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM events').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],0)

    def test_api_loopback_origin_token_and_fixed_metadata_protection(self):
        client,headers = self.client()
        row = self.store.rows()[0]
        payload = {'pair_id':row['pair_id'],'human_label':'no_fit','revision':0}
        self.assertEqual(client.post('/api/review/label',json=payload).status_code,403)
        self.assertEqual(client.post('/api/review/label',json=payload,headers={**headers,'Origin':'https://other.example'}).status_code,403)
        self.assertEqual(client.get('/',environ_overrides={'REMOTE_ADDR':'192.168.1.2'}).status_code,403)
        self.assertEqual(client.get('/',headers={'Host':'attacker.example'}).status_code,403)
        self.assertEqual(client.post('/api/review/label',json={**payload,'product_id':'changed'},headers=headers).status_code,400)
        self.assertEqual(client.get('/api/review/pair?pair_id=missing').status_code,404)
        self.assertEqual(client.get('/').headers['Cache-Control'],'no-store')

    def test_api_complete_report_requires_explicit_finalization(self):
        self.complete_fixture()
        client,headers = self.client()
        self.assertEqual(client.get('/api/review/report').json['state'],'ready')
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],0)
        response = client.post('/api/review/finalize',json={},headers=headers)
        self.assertEqual(response.status_code,200)
        self.assertEqual(response.json['state'],'complete')
        self.assertEqual(response.json['metrics']['pairs'],256)
        self.assertIn('by_topic',response.json)

    def test_actual_fixed_labels_and_matcher_not_modified(self):
        before = {file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in FROZEN_FILES}
        row = self.store.rows()[0]
        self.store.save(row['pair_id'],'no_fit','Synthetic temp DB only',None,0)
        after = {file:hashlib.sha256((ROOT/file).read_bytes()).hexdigest() for file in FROZEN_FILES}
        self.assertEqual(before,after)


if __name__=='__main__':
    unittest.main()
