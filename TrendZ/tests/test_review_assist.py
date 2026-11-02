"""Deterministic assistance tests; all writes target disposable review sessions."""
import csv
import json
import unittest

import test_phase4c as fixtures
from services.product_review import ReviewConflict
from services.product_review_assist import import_assists, accept
from scripts.product_review import create_app


class AssistanceTests(unittest.TestCase):
    def setUp(self):
        fixtures.ReviewTests.setUp(self)
        self.rows = self.store.rows()[:3]
        self.prescreen = self.root/'prescreen.csv'
        self.research = self.root/'research.csv'
        self.make_inputs()

    def write(self,path,rows):
        with path.open('w',encoding='utf-8-sig',newline='') as handle:
            writer = csv.DictWriter(handle,fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    def make_inputs(self):
        self.pre = []
        self.res = []
        for index,row in enumerate(self.rows):
            identity = {key:row['fixed'][key] for key in ('topic_id','query_id','product_id')}
            self.pre.append(dict(identity,suggested_human_label='no_fit',confidence='high' if index==0 else 'medium',
                                 manual_review_recommended='false' if index==0 else 'true',reason='Synthetic prescreen evidence'))
            if index:
                self.res.append(dict(identity,proposed_human_label='supporting_fit',confidence='medium' if index==1 else 'low',
                    evidence_summary='<img src=x> Synthetic source evidence',primary_source_url='https://example.org/product',
                    secondary_source_url='',unresolved_uncertainty='Synthetic uncertainty',needs_human_confirmation='true'))
        self.write(self.prescreen,self.pre)
        self.write(self.research,self.res)

    def load(self):
        return import_assists(self.store,self.prescreen,self.research,True)

    def approval(self,index):
        row = self.store.rows()[index]
        return {key:row[key] for key in ('pair_id','revision','assist_id')}

    def test_dry_run_no_writes_and_import_keeps_human_labels_blank(self):
        before = self.store.export()
        preview = import_assists(self.store,self.prescreen,self.research)
        self.assertFalse(preview['applied'])
        self.assertIsNone(self.store.rows()[0]['assist_source'])
        self.assertEqual(preview['research_accept_eligible'],1)
        self.assertEqual(preview['low_confidence_pending'],1)
        self.load()
        self.assertEqual(self.store.export(),before)
        self.assertEqual(self.store.rows()[0]['assist_label'],'no_fit')
        self.assertEqual(self.store.rows()[1]['review_status'],'needs_human_acceptance')
        self.assertEqual(self.store.rows()[2]['review_status'],'manual_review_required')
        self.assertEqual(self.store.finalized_report()['state'],'pending')

    def test_existing_human_labels_notes_checks_and_revisions_survive(self):
        row = self.rows[0]
        support = False if row['prediction']['fit_state'] in ('direct_fit','supporting_fit') else None
        self.store.save(row['pair_id'],'insufficient_evidence','Existing human note',support,0,'Human')
        before = self.store.export()
        self.load()
        self.assertEqual(self.store.export(),before)
        result = accept(self.store,[self.approval(0)],row['fixed']['topic_id'])
        self.assertEqual(result['accepted'],[])
        self.assertEqual(self.store.rows()[0]['revision'],1)

    def test_idempotent_import_and_immutable_provenance(self):
        first = self.load()
        self.assertEqual(first['import_id'],self.load()['import_id'])
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assist_imports').fetchone()[0],1)
        self.pre[0]['reason'] = 'Different evidence'
        self.write(self.prescreen,self.pre)
        with self.assertRaises(ReviewConflict): self.load()
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM assist_imports').fetchone()[0],1)

    def test_duplicates_unmatched_and_aliases_are_rejected_without_partial_import(self):
        self.write(self.research,self.res+[self.res[0]])
        with self.assertRaises(ValueError): self.load()
        self.res[0]['query_id'] = 'broad'
        self.write(self.research,self.res)
        with self.assertRaises(ValueError): self.load()
        self.make_inputs()
        self.pre[1].update(confidence='high',manual_review_recommended='false')
        self.write(self.prescreen,self.pre)
        with self.assertRaises(ValueError): self.load()
        self.assertIsNone(self.store.rows()[0]['assist_source'])

    def test_acceptance_does_not_fill_explanation_check_and_logs_assist(self):
        self.load()
        approved = accept(self.store,[self.approval(0)],self.rows[0]['fixed']['topic_id'],'Human')
        self.assertEqual(len(approved['accepted']),1)
        row = self.store.rows()[0]
        self.assertEqual(row['human_label'],'no_fit')
        self.assertIsNone(row['unsupported_explanation'])
        with self.store.connect() as db:
            event = json.loads(db.execute('SELECT after_json FROM events').fetchone()[0])
        self.assertEqual(event['accepted_assist']['assist_source'],'assisted_prescreen')
        self.assertEqual(event['accepted_assist']['assist_id'],row['assist_id'])

    def test_medium_research_accepts_and_low_confidence_requires_manual_save(self):
        self.load()
        accept(self.store,[self.approval(1)])
        self.assertEqual(self.store.rows()[1]['human_label'],'supporting_fit')
        with self.assertRaises(ValueError): accept(self.store,[self.approval(2)])
        row = self.store.rows()[2]
        self.assertIsNone(row['human_label'])
        self.store.save(row['pair_id'],'insufficient_evidence','Explicit manual decision',None,0)
        self.assertEqual(self.store.rows()[2]['review_status'],'human_approved')

    def test_batch_only_prescreen_and_atomic_revision_failure(self):
        self.load()
        with self.assertRaises(ValueError):
            accept(self.store,[self.approval(0),self.approval(1)],self.rows[0]['fixed']['topic_id'])
        self.assertIsNone(self.store.rows()[0]['human_label'])
        bad = dict(self.approval(0),revision=9)
        with self.assertRaises(ReviewConflict): accept(self.store,[bad])
        bad = dict(self.approval(0),assist_id='changed')
        with self.assertRaises(ReviewConflict): accept(self.store,[bad])
        self.assertEqual(self.store.summary()['labelled'],0)

    def test_invalid_sources_and_overlapping_suggestions_fail(self):
        self.res[0]['primary_source_url'] = 'javascript:alert(1)'
        self.write(self.research,self.res)
        with self.assertRaises(ValueError): self.load()

    def test_label_basis_survives_export_and_manual_revision_replaces_basis(self):
        self.load()
        accept(self.store,[self.approval(1)],reviewer='user_authorized_assisted_application')
        row = self.store.rows()[1]
        provenance = row['label_provenance']
        self.assertEqual(provenance['source'],'source_researched_assistance')
        self.assertFalse(provenance['independently_hand_reviewed'])
        self.assertTrue(provenance['accepted_assist']['import_id'])
        exported = self.store.export()['rows'][1]
        self.assertEqual(exported['label_provenance'],provenance)
        self.assertEqual(row['review_status'],'assisted_label_applied')
        self.store.save(row['pair_id'],'no_fit','Later manual revision',None,row['revision'])
        self.assertEqual(self.store.rows()[1]['label_provenance']['source'],'existing_human_approval')

    def test_accept_endpoint_token_and_no_prediction_in_payload(self):
        self.load()
        client = create_app(self.store).test_client()
        parser = fixtures.TokenParser(); parser.feed(client.get('/').text)
        payload = dict(approvals=[self.approval(1)])
        self.assertEqual(client.post('/api/review/accept-assist',json=payload).status_code,403)
        headers = {'X-Review-Token':parser.token}
        self.assertEqual(client.post('/api/review/accept-assist',json=dict(payload,human_label='direct_fit'),headers=headers).status_code,400)
        self.assertEqual(client.post('/api/review/accept-assist',json=payload,headers=headers).status_code,200)
        self.assertEqual(client.post('/api/review/accept-assist',json=dict(approvals=[self.approval(2)]),headers=headers).status_code,400)


if __name__=='__main__':
    unittest.main()
