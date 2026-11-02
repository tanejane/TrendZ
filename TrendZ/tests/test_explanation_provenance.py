"""An explanation-only review must not turn an assisted label into manual gold."""
import json
import unittest
import test_phase4c as fixtures
from services.product_review import encoded


class ExplanationProvenanceTests(unittest.TestCase):
    def setUp(self):
        fixtures.ReviewTests.setUp(self)

    def test_explanation_event_preserves_label_basis_exactly(self):
        row = next(r for r in self.store.rows() if r['prediction']['fit_state']=='direct_fit')
        self.store.save(row['pair_id'],'supporting_fit','Existing label note',None,0,'Original reviewer')
        original = next(r for r in self.store.rows() if r['pair_id']==row['pair_id'])
        with self.store.connect() as db:
            before = dict(db.execute('SELECT * FROM labels WHERE pair_id=?',(row['pair_id'],)).fetchone())
            db.execute('UPDATE labels SET unsupported_explanation=1,revision=revision+1 WHERE pair_id=?',(row['pair_id'],))
            after = dict(db.execute('SELECT * FROM labels WHERE pair_id=?',(row['pair_id'],)).fetchone())
            after.update(event_type='explanation_support_check',label_provenance_snapshot=original['label_provenance'])
            db.execute('INSERT INTO events(pair_id,before_json,after_json,saved_at) VALUES (?,?,?,?)',
                       (row['pair_id'],encoded(before),encoded(after),'synthetic-test'))
        current = next(r for r in self.store.rows() if r['pair_id']==row['pair_id'])
        for field in ('human_label','notes','reviewer','reviewed_on','label_provenance'):
            self.assertEqual(current[field],original[field])
        self.assertTrue(current['unsupported_explanation'])
        self.assertEqual(current['revision'],2)
        exported = next(r for r in self.store.export()['rows'] if r['product_id']==row['fixed']['product_id']
                        and r['topic_id']==row['fixed']['topic_id'])
        self.assertEqual(exported['label_provenance'],original['label_provenance'])


if __name__=='__main__':
    unittest.main()
