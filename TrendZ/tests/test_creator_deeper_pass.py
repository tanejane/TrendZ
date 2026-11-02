import copy
import hashlib
import json
from pathlib import Path
import unittest

from services.creator_review import build_units, blank_review
from scripts.prepare_creator_deeper_pass import revise
from scripts.phase5c_deeper_decisions import deeper_changes


class DeeperPassTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        root=Path(__file__).resolve().parents[1]
        source=root/'reports/phase5b/live-initial/review_dataset.json'
        original=root/'reports/phase5c/assists/preparation-v1/review_assists.json'
        if not source.exists() or not original.exists():
            raise unittest.SkipTest('Pinned measured metadata is not distributed')
        cls.records=[{'fixed':u,'review':blank_review()} for u in build_units(json.loads(source.read_text(encoding='utf-8')))]
        cls.original=json.loads(original.read_text(encoding='utf-8'))
        cls.session={'session_id':cls.original['session_id'], 'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest()}
        cls.rows=revise(cls.session,cls.records,cls.original)

    def find(self,channel,topic):
        return next(r for r in self.rows if r['display_name'].strip()==channel and r['topic_id']==topic)

    def test_exact_56_no_original_high_units(self):
        intended={r['unit_id'] for r in self.original['rows'] if r['confidence']!='high'}
        self.assertEqual({r['unit_id'] for r in self.rows}, intended)
        self.assertEqual(len(self.rows),56)
        self.assertTrue(all(r['application_state']=='not_applied_part_b' for r in self.rows))

    def test_no_review_or_fixed_mutation_and_no_gold(self):
        before=copy.deepcopy(self.records)
        revise(self.session,self.records,self.original)
        self.assertEqual(before,self.records)
        self.assertTrue(all(r['review']['human_label'] is None for r in self.records))
        self.assertTrue(all(r['review_basis']=='assisted_review' and r['human_approval_required'] for r in self.rows))

    def test_same_tutorial_is_one_off_not_repeat(self):
        r=self.find('Dhivya Sri','deepavali-glam')
        self.assertEqual(r['proposed_label'],'weak_affinity')
        self.assertEqual(r['selected_video_ids'],['jc6ng3ObJ1M'])
        self.assertIn('8y09OX4ZDrM',r['proxy_video_ids'])

    def test_retinal_named_retinol_not_second_core_example(self):
        r=self.find('Dr Nicole J','retinol')
        self.assertEqual(r['proposed_label'],'weak_affinity')
        self.assertNotIn('X0tcQZW2lRU',r['selected_video_ids'])
        self.assertIn('X0tcQZW2lRU',r['proxy_video_ids'])

    def test_full_description_can_recover_missed_explicit_scalp(self):
        r=self.find('Yuvaap Root Cause | Skin Glow & Inner Health','hair-scalp-care')
        self.assertEqual(r['selected_video_ids'],['R21sk5h8Sts'])
        self.assertEqual(r['proposed_label'],'weak_affinity')

    def test_no_fabricated_prior_seed_for_glass_skin(self):
        r=next(r for r in self.rows if r['creator_id']=='youtube:UCJpVY3GZISFU-CLRN96ZZcQ' and r['topic_id']=='glass-skin')
        self.assertEqual(r['prior_approved_relevant_video_ids'],[])
        self.assertEqual(r['proposed_label'],'insufficient_evidence')

    def test_reposting_does_not_establish_original_specialization(self):
        r=self.find('SiPalingSkincare',None)
        self.assertEqual(r['proposed_specializations'],[])
        self.assertEqual(r['confidence'],'medium')
        self.assertIn('Reposting',r['reason'])

    def test_popularity_never_affects_deeper_decisions(self):
        records=copy.deepcopy(self.records)
        for r in records:
            r['fixed']['engagement']={'views':{'median':999999999},'likes':{'median':1}}
            for v in r['fixed']['videos']:v.update(views=0,likes=0,comments=0)
        self.assertEqual(deeper_changes(records),deeper_changes(self.records))


if __name__=='__main__':unittest.main()
