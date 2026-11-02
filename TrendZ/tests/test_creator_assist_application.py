import copy
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from services.creator_review import CreatorReviewStore, CreatorReviewConflict
from services.creator_review_assists import prepare_pack
from scripts.apply_creator_assists import apply_high
from tests.test_creator_review import snapshot
from tests import test_creator_review_assists as assist_fixtures


class AssistApplicationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(); self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        source = root/'source.json'; source.write_text(json.dumps(snapshot()))
        self.store = CreatorReviewStore(root/'review.sqlite3'); self.store.initialize(source)
        fixture = assist_fixtures.CreatorAssistTests(); fixture.setUp()
        fixture.decisions['source_sha256'] = self.store.metadata()['source_sha256']
        self.pack = prepare_pack(self.store.metadata(), self.store.records(), fixture.decisions)
        self.pack['rows'][0]['confidence'] = 'high'
        self.digest = hashlib.sha256(json.dumps(self.pack).encode()).hexdigest()

    def test_apply_only_high_with_provenance_history(self):
        result = apply_high(self.store, self.pack, self.digest)
        self.assertEqual(len(result['applied']), 1)
        identifier = result['applied'][0]['unit_id']; row = self.store.record(identifier)
        self.assertEqual(row['review']['review_basis'], 'assisted_review')
        self.assertIn(self.digest, row['review']['notes'])
        self.assertIn('NOT INDEPENDENT HUMAN GOLD', row['review']['notes'])
        self.assertEqual(len(self.store.history(identifier)), 1)
        self.assertEqual(sum(r['review']['human_label'] is not None for r in self.store.records()), 1)
        self.assertFalse(self.store.summary()['ready'])

    def test_idempotent_preserves_existing_saved_labels(self):
        apply_high(self.store, self.pack, self.digest)
        before = self.store.export()
        result = apply_high(self.store, self.pack, self.digest)
        self.assertEqual(result['applied'], [])
        self.assertEqual(len(result['preserved_existing']), 1)
        self.assertEqual(self.store.export(), before)

    def test_human_approval_not_overwritten(self):
        d = self.pack['rows'][0]
        self.store.save({'unit_id': d['unit_id'], 'revision': 0, 'human_label': 'insufficient_evidence',
            'human_domains': [], 'human_specializations': [], 'selected_video_ids': [],
            'evidence_sufficiency': 'insufficient', 'explanation_support': 'insufficient_evidence',
            'review_basis': 'human_evidence_review', 'reviewer': 'Actual human', 'notes': 'My independent review'})
        before = self.store.export()
        apply_high(self.store, self.pack, self.digest)
        self.assertEqual(self.store.export(), before)

    def test_stale_pending_rejected(self):
        self.pack['rows'][0]['existing_review_sha256'] = 'stale'
        with self.assertRaises(CreatorReviewConflict): apply_high(self.store, self.pack, self.digest)
        self.assertTrue(all(r['review']['human_label'] is None for r in self.store.records()))

    def test_fixed_provenance_or_session_mismatch_rejected(self):
        for field in ('session_id', 'source_sha256'):
            pack = copy.deepcopy(self.pack); pack[field] = 'wrong'
            with self.assertRaises(ValueError): apply_high(self.store, pack, self.digest)
        self.pack['rows'][0]['fixed_unit_sha256'] = 'wrong'
        with self.assertRaises(ValueError): apply_high(self.store, self.pack, self.digest)


if __name__ == '__main__':
    unittest.main()
