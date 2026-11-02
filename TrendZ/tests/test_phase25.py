import csv
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from contextlib import redirect_stdout
from unittest.mock import patch

from services.database import Database
from services.youtube_store import YouTubeStore
from services.ingestion.youtube_daily import YouTubeDaily
from scripts.youtube_phase25 import main


STAMP = '2026-10-14T04:00:00+00:00'
TOPIC = {'id':'retinol','query_id':'canonical','query':'retinol skincare','market':'MY'}


def capture():
    video = {'id':{'videoId':'v1'},'snippet':{'publishedAt':'2026-10-13T10:00:00Z','title':'Retinol'}}
    return {'topic_id':'retinol','query_id':'canonical','query':'retinol skincare',
            'market':'MY','retrieved_at':STAMP,'data_mode':'real',
            'windows':[{'start':'2026-10-13','end_exclusive':'2026-10-14',
                        'responses':[{'items':[video,video]}]}]}


class Phase25Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.db = Database(self.root/'test.sqlite3')
        self.store = YouTubeStore(self.db)
        self.store.save_run(capture(),'legacy','r1')
        self.store.freeze_audit('audit',[{'run_id':'r1','topic_id':'retinol','query_id':'canonical',
                                        'query':'retinol skincare','rank':1,'video_id':'v1',
                                        'published_at':'2026-10-13T10:00:00Z','data_mode':'real'}])

    def label(self,label='relevant'):
        path = self.root/'audit.csv'
        self.store.export_audit('audit',path)
        with path.open(encoding='utf-8-sig',newline='') as handle:
            reader = csv.DictReader(handle)
            fields, rows = reader.fieldnames, list(reader)
        rows[0]['label'] = label
        with path.open('w',encoding='utf-8',newline='') as handle:
            writer = csv.DictWriter(handle,fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def test_runs_immutable_and_identical_replay_idempotent(self):
        self.assertEqual(self.store.save_run(capture(),'legacy','r1'),'r1')
        modified = capture()
        modified['market'] = 'US'
        with self.assertRaises(ValueError):
            self.store.save_run(modified,'legacy','r1')
        self.store.save_run(modified,'legacy','r2')
        with self.db.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM youtube_runs').fetchone()[0],2)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE youtube_runs SET kind='changed' WHERE run_id='r1'")
        target = self.store.export_run('r1',self.root/'raw')
        self.assertEqual(json.loads(json.loads(target.read_text())['payload'])['market'],'MY')

    def test_duplicate_occurrences_keep_api_positions(self):
        with self.db.connect() as db:
            rows = db.execute('SELECT video_id,page,position FROM youtube_discoveries ORDER BY position').fetchall()
        self.assertEqual([(r['video_id'],r['page'],r['position']) for r in rows],[('v1',1,1),('v1',1,2)])

    def test_labels_persist_and_precision_pending_is_not_zero(self):
        self.assertIsNone(self.store.precision('audit')[0]['strict_precision'])
        path = self.label('partially relevant')
        self.assertEqual(self.store.import_labels('audit',path),1)
        self.assertEqual(self.store.import_labels('audit',path),0)
        reopened = YouTubeStore(Database(self.root/'test.sqlite3'))
        summary = reopened.precision('audit')[0]
        self.assertEqual(summary['strict_precision'],0)
        self.assertEqual(summary['inclusive_precision'],1)
        self.assertEqual(reopened.create_cohorts('audit'),[])

    def test_invalid_labels_atomic(self):
        path = self.label('made up')
        with self.assertRaises(ValueError):
            self.store.import_labels('audit',path)
        self.assertEqual(self.store.audit_rows('audit')[0]['label'],'pending')

    def test_cohort_is_relevant_only_and_frozen(self):
        self.assertEqual(self.store.create_cohorts('audit'),[])
        self.store.import_labels('audit',self.label())
        first = self.store.create_cohorts('audit')
        self.store.import_labels('audit',self.label('irrelevant'))
        self.assertEqual(self.store.create_cohorts('audit'),[])
        self.assertEqual(self.store.cohorts('audit')[0]['cohort_id'],first[0])
        self.assertEqual(len(self.store.cohorts('audit')[0]['members']),1)

    def test_daily_deduplicates_and_separates_snapshot_date(self):
        self.store.import_labels('audit',self.label())
        self.store.create_cohorts('audit')
        calls = []
        def transport(resource,params):
            calls.append((resource,params))
            if resource == 'search':
                return capture()['windows'][0]['responses'][0]
            return {'items':[{'id':'v1','statistics':{'viewCount':'25'}}]}
        adapter = YouTubeDaily(key='fake',transport=transport,clock=lambda:STAMP)
        payload = adapter.collect_day([TOPIC],self.store.cohorts('audit'),'2026-10-13','audit')
        self.assertEqual(payload['requests'],{'search':1,'videos':1})
        self.assertEqual(payload['captures'][0]['windows'][0]['discovered_video_count'],1)
        snap = payload['snapshots'][0]
        self.assertEqual(snap['published_at'],'2026-10-13T10:00:00Z')
        self.assertEqual(snap['snapshot_date'],'2026-10-14')
        self.assertIsNone(snap['likes'])
        self.assertEqual(snap['status'],'partial')
        self.store.save_run(payload,'daily','daily1')
        self.store.save_run(payload,'daily','daily1')
        second = {**payload,'retrieved_at':'2026-10-15T04:00:00+00:00',
                  'snapshots':[{**snap,'snapshot_date':'2026-10-15','retrieved_at':'2026-10-15T04:00:00+00:00','views':30}]}
        self.store.save_run(second,'daily','daily2')
        with self.db.connect() as db:
            rows = db.execute('SELECT snapshot_date,views FROM youtube_video_snapshots ORDER BY snapshot_date').fetchall()
        self.assertEqual([(r['snapshot_date'],r['views']) for r in rows],[('2026-10-14',25),('2026-10-15',30)])
        with self.assertRaises(ValueError):
            adapter.collect_day([TOPIC],[],'2026-10-14','audit')

    def test_daily_failures_and_caps_not_fabricated(self):
        def failing(resource,params):
            raise RuntimeError('YouTube HTTP 429')
        payload = YouTubeDaily(key='fake',transport=failing,clock=lambda:STAMP).collect_day([TOPIC],[],'2026-10-13','audit')
        result = payload['captures'][0]
        self.assertEqual(result['data_mode'],'unavailable')
        self.assertIsNone(result['windows'][0]['discovered_video_count'])
        self.assertFalse(result['windows'][0]['complete'])
        def capped(resource,params):
            return {'items':[],'nextPageToken':'more'}
        payload = YouTubeDaily(key='fake',transport=capped,clock=lambda:STAMP).collect_day([TOPIC],[],'2026-10-13','audit')
        self.assertTrue(payload['captures'][0]['windows'][0]['capped'])

    def test_eight_topics_request_budget_and_missing_video(self):
        self.store.import_labels('audit',self.label())
        self.store.create_cohorts('audit')
        calls = []
        def transport(resource,params):
            calls.append(resource)
            return {'items':[]}
        topics = [{**TOPIC,'id':str(index)} for index in range(7)] + [TOPIC]
        payload = YouTubeDaily(key='fake',transport=transport,clock=lambda:STAMP).collect_day(
            topics,self.store.cohorts('audit'),'2026-10-13','audit')
        self.assertEqual(payload['requests'],{'search':8,'videos':1})
        self.assertEqual(payload['snapshots'][0]['status'],'unavailable')
        self.assertIsNone(payload['snapshots'][0]['views'])

    def test_daily_command_repeat_skips_requests(self):
        payload = {'retrieved_at':STAMP,'captures':[],'snapshots':[],
                   'requests':{'search':8,'videos':0}}
        output = self.root/'cli'
        arguments = ['youtube_phase25.py','daily','--output',str(output),'--date','2026-10-13']
        with patch('sys.argv',arguments), patch('scripts.youtube_phase25.YouTubeDaily') as adapter:
            adapter.return_value.collect_day.return_value = payload
            with redirect_stdout(io.StringIO()):
                main()
                main()
            self.assertEqual(adapter.return_value.collect_day.call_count,1)
        with patch('sys.argv',arguments+['--retry']), patch('scripts.youtube_phase25.YouTubeDaily') as adapter:
            adapter.return_value.collect_day.return_value = payload
            with redirect_stdout(io.StringIO()):
                main()
            self.assertEqual(adapter.return_value.collect_day.call_count,1)
        with Database(output/'pilot.sqlite3').connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM youtube_runs').fetchone()[0],2)


if __name__ == '__main__':
    unittest.main()
