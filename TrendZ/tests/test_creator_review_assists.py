import copy
import json
from pathlib import Path
import tempfile
import unittest

from services.creator_review import CreatorReviewStore, blank_review, build_units, fingerprint
from services.creator_review_assists import prepare_pack, markdown_pack
from scripts.prepare_creator_assists import read_session
from scripts.phase5c_assist_decisions import author_decisions, SOURCE_SHA256
from tests.test_creator_review import snapshot


class CreatorAssistTests(unittest.TestCase):
    def setUp(self):
        self.records = [{'fixed': u, 'review': blank_review()} for u in build_units(snapshot())]
        self.session = {'session_id': 'fixture', 'source_sha256': 'fixture-source'}
        rows = []
        for r in self.records:
            f = r['fixed']; p = f['unit_type'] == 'profile'
            multiple = len(f['videos']) > 1
            rows.append({'unit_id': f['unit_id'],
                'proposed_label': ('supported' if multiple else 'partially_supported') if p else ('moderate_affinity' if multiple else 'weak_affinity'),
                'selected_video_ids': [v['video_id'] for v in f['videos']],
                'proposed_domains': ['beauty'] if p else [],
                'proposed_specializations': ['skincare'] if p else [],
                'confidence': 'medium', 'evidence_sufficiency': 'sufficient' if multiple else 'partial',
                'explanation_support': 'supported', 'explanation_reason': 'Fixture source describes the topic.',
                'reason': 'Fixture repeated or limited content, not a final review.'})
        self.decisions = {'source_sha256': 'fixture-source', 'rows': rows}

    def pack(self):
        return prepare_pack(self.session, self.records, self.decisions)

    def test_pure_transform_preserves_every_human_field(self):
        self.records[0]['review'].update(human_label='unsupported', revision=3, reviewer='Original human')
        before = copy.deepcopy(self.records)
        pack = self.pack()
        self.assertEqual(before, self.records)
        self.assertTrue(pack['rows'][0]['existing_human_label_present'])
        self.assertEqual(pack['rows'][0]['based_on_revision'], 3)
        self.assertTrue(all('human_label' not in r for r in pack['rows']))
        self.assertTrue(all(r['review_basis'] == 'assisted_review' for r in pack['rows']))
        self.assertTrue(all(r['review_status'] == 'needs_human_acceptance' for r in pack['rows']))

    def test_snapshot_mismatch_rejected(self):
        self.session['source_sha256'] = 'other'
        with self.assertRaises(ValueError): self.pack()

    def test_duplicate_missing_or_unknown_units_rejected(self):
        for change in ('duplicate', 'missing', 'unknown'):
            with self.subTest(change=change):
                d = copy.deepcopy(self.decisions)
                if change == 'duplicate': d['rows'].append(d['rows'][0])
                elif change == 'missing': d['rows'].pop()
                else: d['rows'][0]['unit_id'] = 'unknown'
                with self.assertRaises(ValueError): prepare_pack(self.session, self.records, d)

    def test_two_distinct_date_guards_profile_and_affinity(self):
        for kind, label in [('profile', 'supported'), ('affinity', 'strong_affinity'), ('affinity', 'moderate_affinity')]:
            for same_date in (False, True):
                with self.subTest(kind=kind, label=label, same_date=same_date):
                    records = copy.deepcopy(self.records); d = copy.deepcopy(self.decisions)
                    row = next(r for r in records if r['fixed']['unit_type'] == kind and len(r['fixed']['videos']) == 2)
                    draft = next(x for x in d['rows'] if x['unit_id'] == row['fixed']['unit_id'])
                    draft['proposed_label'] = label
                    if same_date:
                        row['fixed']['videos'][1]['published_at'] = row['fixed']['videos'][0]['published_at']
                    else:
                        draft['selected_video_ids'] = draft['selected_video_ids'][:1]
                    with self.assertRaises(ValueError): prepare_pack(self.session, records, d)

    def test_drafts_never_approve_new_video_relevance(self):
        pack = self.pack()
        for r in pack['rows']:
            self.assertEqual(r['newly_approved_video_count'], 0)
            self.assertFalse(r['sustained_affinity_validated'])
            self.assertTrue(r['human_approval_required'])
            if r['proposed_label'] == 'moderate_affinity':
                self.assertTrue(r['proposed_label_is_conditional'])
                self.assertIn('approve', r['acceptance_requirements'])

    def test_proxy_cannot_count_toward_relevant_selection(self):
        self.decisions['rows'][0]['proxy_video_ids'] = self.decisions['rows'][0]['selected_video_ids'][:1]
        with self.assertRaises(ValueError): self.pack()

    def test_unknown_or_duplicate_video_rejected(self):
        for selected in (['unknown'], ['v1-0', 'v1-0']):
            self.decisions['rows'][0]['selected_video_ids'] = selected
            with self.assertRaises(ValueError): self.pack()

    def test_profile_affinity_independent(self):
        row = next(r for r in self.decisions['rows'] if r['unit_id'].startswith('affinity/'))
        row['proposed_domains'] = ['beauty']
        with self.assertRaises(ValueError): self.pack()

    def test_prior_video_not_in_current_share_denominator(self):
        f = next(r['fixed'] for r in self.records if r['fixed']['unit_type'] == 'affinity')
        old = {**f['videos'][0], 'video_id': 'old', 'sample_scope': 'prior_seed_outside_sample'}
        f['prior_videos'] = [old]
        row = next(d for d in self.decisions['rows'] if d['unit_id'] == f['unit_id'])
        row.update(proposed_label='weak_affinity', selected_video_ids=['old'], evidence_sufficiency='partial')
        out = next(r for r in self.pack()['rows'] if r['unit_id'] == f['unit_id'])
        self.assertEqual(out['proposed_components']['proposed_sample_share'], 0)
        self.assertEqual(out['proposed_components']['selected_prior_outside_sample'], ['old'])

    def test_manual_queue_and_fingerprints(self):
        pack = self.pack()
        self.assertEqual(pack['rows'][0]['fixed_unit_sha256'], fingerprint(self.records[0]['fixed']))
        self.assertTrue(all(r['deeper_manual_review_required'] for r in pack['rows']))
        self.assertIn('Deeper Manual Queue', markdown_pack(pack))

    def test_read_only_session_preparation_keeps_db_bytes_and_history(self):
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp)/'source.json'; source.write_text(json.dumps(snapshot()))
            store = CreatorReviewStore(Path(temp)/'review.sqlite3'); store.initialize(source)
            before = store.path.read_bytes()
            session, records, counts = read_session(store.path)
            d = copy.deepcopy(self.decisions); d['source_sha256'] = session['source_sha256']
            prepare_pack(session, records, d)
            self.assertEqual(store.path.read_bytes(), before)
            self.assertEqual(counts['events'], 0)
            self.assertEqual(counts['reports'], 0)
            self.assertTrue(all(r['review']['human_label'] is None for r in store.records()))

    def test_exact_frozen_104_decisions_validate(self):
        source = Path(__file__).resolve().parents[1]/'reports/phase5b/live-initial/review_dataset.json'
        if not source.exists(): self.skipTest('Local measured snapshot not distributed')
        records = [{'fixed': f, 'review': blank_review()} for f in build_units(json.loads(source.read_text(encoding='utf-8')))]
        pack = prepare_pack({'source_sha256': SOURCE_SHA256, 'session_id': 'frozen-fixture'}, records, author_decisions(records))
        self.assertEqual(len(pack['rows']), 104)
        self.assertEqual(sum(r['unit_type'] == 'profile' for r in pack['rows']), 40)
        self.assertEqual(sum(r['unit_type'] == 'affinity' for r in pack['rows']), 64)
        self.assertFalse(any(r['sustained_affinity_validated'] for r in pack['rows']))


if __name__ == '__main__':
    unittest.main()
