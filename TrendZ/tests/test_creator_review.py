import copy
import json
import re
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.creator_review import CreatorReviewStore, CreatorReviewConflict, build_units
from services.creator_review_evaluation import evaluate, selected_components, markdown_report
from scripts.creator_review import create_app


def snapshot():
    creators=[]
    for number,ready in [(1,True),(2,False)]:
        videos=[{'video_id':f'v{number}-{i}','title':'Retinol sample','description':'Source text',
            'published_at':f'2026-10-{day:02}T00:00:00Z','retrieved_at':'2026-10-16T06:00:00Z',
            'source_ref':{'run_id':'run'+str(number),'request_index':2,'item_index':i},
            'views':100,'likes':10,'comments':1} for i,day in enumerate([1,15] if ready else [10])]
        creators.append({'creator_id':'youtube:c'+str(number),'channel_id':'c'+str(number),
            'display_name':'Creator '+str(number),'as_of':'2026-10-16T07:00:00Z','method_version':'fixture-v1',
            'profile':{'evidence_ready_for_profile_review':ready,'proposed_domains':['beauty'] if ready else [],
                'proposed_specializations':['skincare'] if ready else [],'sample_span':{'span_days':14 if ready else 0},
                'evidence_references':[v['source_ref'] for v in videos]},
            'engagement':{'views':{'median':100 if ready else 100000}},'market_evidence':{'audience_geography':{'state':'unknown'}},
            'videos':videos,'seed_provenance':[],'collection':{'scope':'bounded_uploads'},
            'topics':{'retinol':{'proposed_relevant_count':1,'prior_confirmed_video_ids':[],
                'draft_threshold_sensitivity':{'draft_moderate_gate':{'screen_assisted_meets_gate':False},
                                               'draft_strong_gate':{'screen_assisted_meets_gate':False}}}}})
    return {'creators':creators,'manifest':{'source_run_sha256':{'run1':'fixture','run2':'fixture'}}}


class CreatorReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.source=self.root/'source.json'
        self.source.write_text(json.dumps(snapshot()))
        self.store=CreatorReviewStore(self.root/'review.sqlite3')
        self.store.initialize(self.source)

    def payload(self,unit='profile/youtube:c1',label='supported'):
        fixed=self.store.record(unit)['fixed']
        profile=fixed['unit_type']=='profile'
        insuff=label=='insufficient_evidence'
        return {'unit_id':unit,'revision':self.store.record(unit)['review']['revision'],
            'human_label':label,'human_domains':['beauty'] if profile and not insuff else [],
            'human_specializations':['skincare'] if profile and not insuff else [],
            'selected_video_ids':[] if insuff or label=='no_affinity' else [v['video_id'] for v in fixed['videos']],
            'evidence_sufficiency':'insufficient' if insuff else 'sufficient','explanation_support':'supported',
            'review_basis':'human_evidence_review','notes':'Inspected cited content','reviewer':'Fixture reviewer'}

    def complete(self):
        for row in self.store.records():
            fixed=row['fixed']
            label=('supported' if fixed['readiness_group']=='review_ready' else 'insufficient_evidence') if fixed['unit_type']=='profile' else ('moderate_affinity' if fixed['readiness_group']=='review_ready' else 'weak_affinity')
            self.store.save(self.payload(fixed['unit_id'],label))

    def test_two_distinct_fixed_units_and_blank_labels(self):
        records=self.store.records()
        self.assertEqual(len(records),4)
        self.assertEqual(len({r['fixed']['unit_id'] for r in records}),4)
        self.assertTrue(all(r['review']['human_label'] is None for r in records))
        self.assertFalse(self.store.summary()['ready'])

    def test_initialization_idempotent(self):
        self.store.save(self.payload())
        self.store.initialize(self.source)
        self.assertEqual(self.store.record('profile/youtube:c1')['review']['human_label'],'supported')
        self.assertEqual(len(self.store.records()),4)

    def test_different_snapshot_rejected_without_overwriting(self):
        changed=snapshot();changed['creators'][0]['display_name']='Changed'
        self.source.write_text(json.dumps(changed))
        with self.assertRaises(CreatorReviewConflict):
            self.store.initialize(self.source)
        self.assertEqual(self.store.record('profile/youtube:c1')['fixed']['display_name'],'Creator 1')

    def test_duplicate_creator_snapshot_rejected(self):
        source=snapshot();source['creators'].append(source['creators'][0])
        with self.assertRaises(ValueError):build_units(source)

    def test_fixed_units_and_events_immutable(self):
        self.store.save(self.payload())
        with self.store.connect() as db:
            for statement in ('DELETE FROM units','UPDATE events SET saved_at=\'changed\'','DELETE FROM metadata'):
                with self.assertRaises(sqlite3.IntegrityError):db.execute(statement)

    def test_stale_revision_rejected(self):
        value=self.payload();self.store.save(value)
        with self.assertRaises(CreatorReviewConflict):self.store.save(value)
        self.assertEqual(len(self.store.history(value['unit_id'])),1)

    def test_reset_retains_history(self):
        first=self.store.save(self.payload())
        self.store.save({'unit_id':'profile/youtube:c1','revision':first['revision'],'reviewer':'Second','reset':True})
        self.assertIsNone(self.store.record('profile/youtube:c1')['review']['human_label'])
        self.assertEqual(len(self.store.history('profile/youtube:c1')),2)

    def test_unknown_or_duplicate_evidence_rejected(self):
        for ids in (['unknown'],['v1-0','v1-0']):
            value=self.payload();value['selected_video_ids']=ids
            with self.assertRaises(ValueError):self.store.save(value)

    def test_invalid_labels_and_injected_prediction_fields(self):
        for key,value in [('human_label','high_score'),('prediction',{'score':100}),('revision',True)]:
            payload=self.payload();payload[key]=value
            with self.assertRaises(ValueError):self.store.save(payload)

    def test_human_review_metadata_required(self):
        for key,value in [('reviewer',''),('notes',''),('review_basis',None),('explanation_support',None),('evidence_sufficiency',None)]:
            payload=self.payload();payload[key]=value
            with self.assertRaises(ValueError):self.store.save(payload)

    def test_one_video_cannot_support_stable_profile(self):
        value=self.payload('profile/youtube:c2')
        with self.assertRaisesRegex(ValueError,'One video'):self.store.save(value)

    def test_one_video_cannot_establish_moderate_or_strong_affinity(self):
        for label in ('strong_affinity','moderate_affinity'):
            with self.assertRaisesRegex(ValueError,'multiple relevant videos'):
                self.store.save(self.payload('affinity/youtube:c2/retinol',label))

    def test_single_video_can_have_weak_affinity_without_profile_approval(self):
        self.store.save(self.payload('affinity/youtube:c2/retinol','weak_affinity'))
        self.assertIsNone(self.store.record('profile/youtube:c2')['review']['human_label'])

    def test_distinct_dates_required_for_sustained_affinity(self):
        changed=snapshot();changed['creators'][0]['videos'][1]['published_at']=changed['creators'][0]['videos'][0]['published_at']
        path=self.root/'same-day.json';path.write_text(json.dumps(changed))
        other=CreatorReviewStore(self.root/'same-day.sqlite3');other.initialize(path)
        with self.assertRaisesRegex(ValueError,'distinct dates'):
            other.save(self.payload('affinity/youtube:c1/retinol','moderate_affinity'))

    def test_specializations_require_beauty(self):
        value=self.payload();value['human_domains']=['fashion']
        with self.assertRaises(ValueError):self.store.save(value)

    def test_affinity_cannot_edit_profile(self):
        value=self.payload('affinity/youtube:c1/retinol','moderate_affinity');value['human_domains']=['beauty']
        with self.assertRaises(ValueError):self.store.save(value)

    def test_abstention_does_not_finalize_classifications(self):
        value=self.payload(label='insufficient_evidence');value['human_domains']=['beauty']
        with self.assertRaises(ValueError):self.store.save(value)

    def test_no_affinity_cannot_also_approve_positive_video(self):
        value=self.payload('affinity/youtube:c1/retinol','no_affinity');value['selected_video_ids']=['v1-0']
        with self.assertRaises(ValueError):self.store.save(value)

    def test_profile_and_topic_exports_are_separate(self):
        self.assertEqual(len(self.store.export('profile')['rows']),2)
        self.assertTrue(all(r['fixed']['unit_type']=='affinity' for r in self.store.export('affinity')['rows']))

    def test_export_preserves_revision_history_and_review_basis(self):
        value=self.payload();value['review_basis']='assisted_review';self.store.save(value)
        exported=self.store.export('profile')
        self.assertEqual(len(exported['revision_history']),1)
        self.assertEqual(exported['revision_history'][0]['after']['review_basis'],'assisted_review')
        self.assertEqual(exported['revision_history'][0]['after']['revision'],1)

    def test_finalization_pending_until_both_units_complete(self):
        self.store.save(self.payload())
        self.assertEqual(self.store.finalize()['state'],'pending')
        with self.store.connect() as db:self.assertEqual(db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],0)

    def test_completed_report_separates_groups_and_has_no_false_categorical_agreement(self):
        self.complete();report=self.store.finalize()
        self.assertEqual(report['state'],'complete')
        self.assertEqual(report['by_readiness']['review_ready']['profiles'],1)
        self.assertEqual(report['by_readiness']['insufficient']['profiles'],1)
        self.assertEqual(report['overall']['topic_affinity_agreement']['state'],'unavailable')
        self.assertEqual(report['overall']['one_video_overmatching']['one_video_high_labels'],0)
        self.assertEqual(report['overall']['specializations']['precision'],1)
        self.assertFalse(report['independent_gold'])
        self.assertEqual(report['explanation_traceability']['link_rate'],1)

    def test_report_is_immutable_and_repeatable(self):
        self.complete();first=self.store.finalize();second=self.store.finalize()
        self.assertEqual(first,second)
        with self.store.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM reports').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):db.execute('DELETE FROM reports')

    def test_popularity_does_not_change_affinity_decisions(self):
        self.complete();records=self.store.records();report=evaluate(records)
        modified=copy.deepcopy(records)
        for row in modified:row['fixed']['engagement']['views']['median']=0
        self.assertEqual(report['overall'],evaluate(modified)['overall'])

    def test_all_abstentions_have_null_not_zero_accuracy(self):
        for row in self.store.records():self.store.save(self.payload(row['fixed']['unit_id'],'insufficient_evidence'))
        report=self.store.finalize()
        self.assertIsNone(report['overall']['profile_agreement']['rate'])
        self.assertIsNone(report['overall']['specializations']['precision'])
        self.assertIsNone(report['overall']['one_video_overmatching']['rate'])
        self.assertEqual(report['overall']['abstention']['affinity_rate'],1)

    def test_corrected_specialization_counts_false_positive_and_negative(self):
        self.complete();value=self.payload();value['human_specializations']=['makeup'];self.store.save(value)
        report=self.store.finalize()
        self.assertEqual(report['overall']['specializations']['false_positive'],1)
        self.assertEqual(report['overall']['specializations']['false_negative'],1)
        self.assertEqual(report['overall']['profile_agreement']['rate'],0)
        self.assertIn('Categorical topic-affinity agreement is unavailable',markdown_report(report))

    def test_missing_session_is_not_silently_recreated(self):
        missing=CreatorReviewStore(self.root/'does-not-exist.sqlite3')
        with self.assertRaises(sqlite3.OperationalError):missing.records()
        self.assertFalse(missing.path.exists())

    def test_prior_seed_excluded_from_current_sample_share(self):
        row=self.store.record('affinity/youtube:c1/retinol')
        prior=copy.deepcopy(row['fixed']['videos'][0]);prior['video_id']='prior'
        row['fixed']['prior_videos']=[prior];row['review']['selected_video_ids']=['v1-0','prior']
        result=selected_components(row)
        self.assertEqual(result['approved_video_count'],2)
        self.assertEqual(result['sample_share'],0.5)
        self.assertEqual(result['prior_outside_sample_count'],1)


class CreatorReviewApiTests(unittest.TestCase):
    payload=CreatorReviewTests.payload

    def setUp(self):
        CreatorReviewTests.setUp(self);self.app=create_app(self.store);self.client=self.app.test_client()
        page=self.client.get('/')
        self.token=re.search('name="review-token" content="([^"]+)"',page.text).group(1)

    def test_loopback_and_host_guard(self):
        self.assertEqual(self.client.get('/api/review',environ_base={'REMOTE_ADDR':'8.8.8.8'}).status_code,403)
        self.assertEqual(self.client.get('/api/review',headers={'Host':'evil.test'}).status_code,403)

    def test_csrf_and_cross_origin(self):
        self.assertEqual(self.client.post('/api/review/save',json=self.payload()).status_code,403)
        self.assertEqual(self.client.post('/api/review/save',json=self.payload(),headers={'X-Review-Token':self.token,'Origin':'https://evil.test'}).status_code,403)

    def test_api_explicit_save_and_conflict(self):
        headers={'X-Review-Token':self.token};value=self.payload()
        self.assertEqual(self.client.post('/api/review/save',json=value,headers=headers).status_code,200)
        self.assertEqual(self.client.post('/api/review/save',json=value,headers=headers).status_code,409)

    def test_get_does_not_generate_report(self):
        self.assertEqual(self.client.get('/api/review/evaluation').json['state'],'pending')
        response=self.client.post('/api/review/evaluate',json={},headers={'X-Review-Token':self.token})
        self.assertEqual(response.status_code,409)

    def test_missing_unit_and_schema_errors(self):
        self.assertEqual(self.client.get('/api/review/unit?unit_id=missing').status_code,404)
        self.assertEqual(self.client.post('/api/review/save',json=[],headers={'X-Review-Token':self.token}).status_code,400)

    def test_export_and_security_headers(self):
        response=self.client.get('/api/review/export/affinity')
        self.assertEqual(len(response.json['rows']),2)
        self.assertEqual(response.headers['Cache-Control'],'no-store')
        self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        self.assertIn('<option value="review_ready">',self.client.get('/').text)


if __name__=='__main__':unittest.main()
