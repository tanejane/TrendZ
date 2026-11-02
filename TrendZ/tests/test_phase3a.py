import csv
import hashlib
import tempfile
import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import app_backend
from services.database import Database
from services.ingestion.base import Observation
from services.youtube_store import YouTubeStore
from services.intelligence_service import IntelligenceService

TOPIC = {'id':'glass-skin','name':'Glass Skin','query':'glass skin','market':'MY','category':'skincare',
         'aliases':[{'id':'routine','query':'glass skin routine'}]}
STAMP = '2026-01-22T00:00:00+00:00'
NAMES = {'demand_momentum','signal_persistence','content_saturation','creator_diversity','engagement_velocity','data_confidence'}


class DimensionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)/'db.sqlite3'
        self.db = Database(self.path)
        self.db.sync_topics([TOPIC])
        self.store = YouTubeStore(self.db)
        self.service = IntelligenceService(self.path,[TOPIC])

    def dimensions(self,query_id='canonical'):
        return self.service.topic(TOPIC['id'],query_id)['dimensions']

    def google(self,values=None,metadata=None,query_id='canonical',series='g1',demo=False,skip=()):
        query = 'glass skin' if query_id=='canonical' else 'glass skin routine'
        values = values if values is not None else [10]*7+[20]*7+[30]*7
        end = date(2026,1,1)+timedelta(days=len(values)-1)
        request = {'query':query,'geo':'MY','timeframe':'2026-01-01 '+end.isoformat(),
                   'timezone':'UTC','term_type':'search_term','category':0,'property':''}
        rows = [Observation(TOPIC['id'],'google_trends',query,'MY',
                            (date(2026,1,1)+timedelta(days=i)).isoformat(),STAMP,'interest_score',value,series,
                            metadata=metadata if metadata is not None else {'request':request},
                            query_id=query_id,query=query,is_demo=demo)
                for i,value in enumerate(values) if i not in skip]
        self.db.ingest(rows)

    def capture(self,capped=False,failed=False,query_id='canonical',missing_channel=False,stamp=STAMP,run_id='r1',demo=False):
        windows,videos = [],[]
        for week in range(3):
            start = date(2026,1,1)+timedelta(days=week*7)
            items = []
            for position in range(2):
                published = (start+timedelta(days=position)).isoformat()+'T12:00:00Z'
                snippet = {'publishedAt':published,'channelId':'' if missing_channel else 'c'+str(position),
                           'title':'Glass skin','channelTitle':'Channel '+str(position)}
                identifier = 'v'+str(week)+str(position)
                items.append({'id':{'videoId':identifier},'snippet':snippet})
                videos.append({'id':identifier,**snippet})
            windows.append({'start':start.isoformat(),'end_exclusive':(start+timedelta(days=7)).isoformat(),
                            'request':{'q':'glass skin' if query_id=='canonical' else 'glass skin routine','regionCode':'MY',
                                       'publishedAfter':start.isoformat()+'T00:00:00Z',
                                       'publishedBefore':(start+timedelta(days=7)).isoformat()+'T00:00:00Z'},
                            'complete':not capped and not failed,'capped':capped,'error':'HTTP 429' if failed else None,
                            'responses':[] if failed else [{'items':items}]})
        capture = {'topic_id':TOPIC['id'],'query_id':query_id,
                   'query':'glass skin' if query_id=='canonical' else 'glass skin routine','market':'MY',
                   'retrieved_at':stamp,'windows':windows,'videos':videos,'data_mode':'demo' if demo else 'real'}
        self.store.save_run(capture,'retrospective',run_id)
        return capture

    def audited_cohort(self,size=2):
        capture = self.capture()
        candidates = [{'run_id':'r1','topic_id':TOPIC['id'],'query_id':'canonical','query':'glass skin',
                       'rank':i+1,'video_id':v['id'],'published_at':v['publishedAt'],'data_mode':'real'}
                      for i,v in enumerate(capture['videos'])]
        self.store.freeze_audit('audit',candidates)
        path = Path(self.temp.name)/'audit.csv'
        self.store.export_audit('audit',path)
        with path.open(encoding='utf-8-sig',newline='') as handle:
            reader = csv.DictReader(handle)
            fields,rows = reader.fieldnames,list(reader)
        with path.open('w',encoding='utf-8',newline='') as handle:
            writer = csv.DictWriter(handle,fieldnames=fields)
            writer.writeheader()
            writer.writerows([{**r,'label':'relevant'} for r in rows])
        self.store.import_labels('audit',path)
        with patch('services.youtube_store.now',return_value=STAMP):
            self.store.create_cohorts('audit',size)
        return self.store.cohorts('audit')[0]

    def snapshot(self,cohort,day=22,views=100,likes=10,omit=(),status='available'):
        stamp = f'2026-01-{day:02d}T00:00:00+00:00'
        snapshots = [{'cohort_id':cohort['cohort_id'],'video_id':m['video_id'],
                      'published_at':m['published_at'],'snapshot_date':stamp[:10],'retrieved_at':stamp,
                      'views':views,'likes':likes,'status':status,'reason':None,'market':'MY','query':'glass skin'}
                     for m in cohort['members'] if m['video_id'] not in omit]
        self.store.save_run({'retrieved_at':stamp,'captures':[],'snapshots':snapshots},'daily','s'+str(day))

    def test_empty_all_dimensions_unavailable_schema(self):
        result = self.dimensions()
        self.assertEqual(set(result),NAMES)
        fields = {'state','components','source','query','query_id','market','observation_window','method_version',
                  'evidence_identifiers','unavailable_reasons','provisional_reasons','quality_warnings','scope','retrieval_window'}
        for dimension in result.values():
            self.assertEqual(dimension['state'],'unavailable')
            self.assertTrue(fields<=set(dimension))
            self.assertTrue(dimension['unavailable_reasons'])

    def test_demand_and_search_persistence_available(self):
        self.google()
        result = self.dimensions()
        demand = result['demand_momentum']
        self.assertEqual(demand['state'],'available')
        self.assertEqual(demand['components']['recent_growth']['value'],50)
        self.assertEqual(demand['components']['acceleration']['value'],-50)
        self.assertEqual(result['signal_persistence']['state'],'available')
        self.assertEqual(result['signal_persistence']['components']['search']['persistence']['value'],1)
        self.assertEqual(demand['evidence_identifiers']['series_ids'],['g1'])

    def test_sparse_search_provisional_not_missing_zero_fill(self):
        self.google([0]*14+[1]*7)
        result = self.dimensions()
        self.assertEqual(result['demand_momentum']['state'],'unavailable')
        self.assertEqual(result['signal_persistence']['state'],'provisional')
        self.assertIn('zero',result['demand_momentum']['components']['recent_growth']['reason'])
        self.assertEqual(result['data_confidence']['components']['google_zero_days'],14)

    def test_sparse_with_positive_baseline_provisional_growth(self):
        self.google([0]*30+[10]*7+[20]*7)
        self.assertEqual(self.dimensions()['demand_momentum']['state'],'provisional')

    def test_gap_blocks_growth_and_persistence(self):
        self.google(skip=(10,))
        self.assertEqual(self.dimensions()['demand_momentum']['state'],'unavailable')
        self.assertEqual(self.dimensions()['signal_persistence']['state'],'unavailable')
        self.assertEqual(self.dimensions()['data_confidence']['components']['google_missing_days'],1)

    def test_bad_google_request_unavailable(self):
        self.google(metadata={})
        self.assertEqual(self.dimensions()['demand_momentum']['state'],'unavailable')

    def test_query_market_request_mismatch_unavailable(self):
        self.google(metadata={'request':{'query':'wrong','geo':'SG','timezone':'UTC','term_type':'search_term',
                                         'timeframe':'2026-01-01 2026-01-21'}})
        self.assertEqual(self.dimensions()['demand_momentum']['state'],'unavailable')

    def test_aliases_and_demo_never_pooled(self):
        self.google(query_id='routine')
        self.capture(query_id='routine')
        self.google(demo=True)
        self.assertEqual(self.dimensions()['demand_momentum']['state'],'unavailable')
        self.assertEqual(self.dimensions()['creator_diversity']['state'],'unavailable')
        self.assertEqual(self.dimensions('routine')['demand_momentum']['state'],'available')
        self.assertEqual(self.dimensions('routine')['creator_diversity']['state'],'provisional')

    def test_unreviewed_supply_proxy_provisional_never_saturation(self):
        self.capture()
        dim = self.dimensions()['content_saturation']
        self.assertEqual(dim['state'],'provisional')
        self.assertEqual(dim['components']['saturation_level']['state'],'unavailable')
        self.assertEqual(dim['components']['supply_recent_growth']['state'],'available')
        self.assertEqual(self.dimensions()['signal_persistence']['state'],'provisional')

    def test_caps_and_failures_block_all_supply_growth(self):
        for capped,failed in ((True,False),(False,True)):
            self.capture(capped=capped,failed=failed,run_id='r'+str(capped),stamp='2026-01-23T00:00:00+00:00')
            dim = self.dimensions()['content_saturation']
            self.assertEqual(dim['state'],'unavailable')
            self.assertIsNone(dim['components']['supply_recent_growth']['value'])
            self.assertEqual(self.dimensions()['signal_persistence']['components']['publication']['persistence']['state'],'unavailable')

    def test_creator_counts_provisional_sample_hhi(self):
        self.capture(capped=True)
        dim = self.dimensions()['creator_diversity']
        self.assertEqual(dim['state'],'provisional')
        self.assertEqual(dim['components']['sample_channel_count'],2)
        self.assertEqual(dim['components']['channel_hhi']['value'],0.5)
        self.assertEqual(dim['scope'],'unreviewed_query_sample')

    def test_audited_creator_sample_available_not_population(self):
        self.audited_cohort()
        dim = self.dimensions()['creator_diversity']
        self.assertEqual(dim['state'],'available')
        self.assertEqual(dim['scope'],'audited_relevant_sample')
        self.assertIn('never population',dim['quality_warnings'][0])

    def test_missing_channel_ids_unavailable(self):
        self.capture(missing_channel=True)
        self.assertEqual(self.dimensions()['creator_diversity']['state'],'unavailable')

    def test_wrong_publication_request_blocks_intelligence(self):
        capture = self.capture()
        capture['retrieved_at']='2026-01-23T00:00:00+00:00'
        capture['windows'][0]['request']['q']='unrelated query'
        self.store.save_run(capture,'retrospective','bad-request')
        self.assertEqual(self.dimensions()['content_saturation']['state'],'unavailable')
        self.assertEqual(self.dimensions()['creator_diversity']['state'],'unavailable')

    def test_snapshot_requires_same_fixed_cohort_and_two_dates(self):
        cohort = self.audited_cohort()
        self.snapshot(cohort)
        self.assertEqual(self.dimensions()['engagement_velocity']['state'],'unavailable')
        self.snapshot(cohort,day=23,views=148,likes=16)
        dim = self.dimensions()['engagement_velocity']
        self.assertEqual(dim['state'],'available')
        self.assertEqual(dim['components']['views_per_hour']['value'],4)
        self.assertEqual(dim['components']['likes_per_hour']['value'],0.5)
        self.assertEqual(dim['evidence_identifiers']['run_ids'],['s22','s23'])
        self.assertEqual(dim['observation_window'],{'start':'2026-01-22','end':'2026-01-23'})

    def test_missing_likes_provisional_no_zero_fill(self):
        cohort = self.audited_cohort()
        self.snapshot(cohort,likes=None)
        self.snapshot(cohort,day=23,views=148,likes=None)
        dim = self.dimensions()['engagement_velocity']
        self.assertEqual(dim['state'],'provisional')
        self.assertIsNone(dim['components']['likes_per_hour']['value'])

    def test_partial_matched_cohort_provisional(self):
        cohort = self.audited_cohort()
        self.snapshot(cohort)
        self.snapshot(cohort,day=23,views=148,omit=(cohort['members'][0]['video_id'],))
        dim = self.dimensions()['engagement_velocity']
        self.assertEqual(dim['state'],'provisional')
        self.assertEqual(dim['components']['paired_view_videos'],1)

    def test_corrected_counters_never_clipped_to_velocity(self):
        cohort = self.audited_cohort()
        self.snapshot(cohort)
        self.snapshot(cohort,day=23,views=50)
        dim = self.dimensions()['engagement_velocity']
        self.assertEqual(dim['state'],'unavailable')
        self.assertIsNone(dim['components']['views_per_hour']['value'])

    def test_different_cohorts_never_form_velocity_pair(self):
        first = self.audited_cohort()
        self.snapshot(first)
        second = {**first,'cohort_id':'second','selected_at':'2026-01-23T00:00:00+00:00'}
        with self.db.connect() as db:
            db.execute('INSERT INTO youtube_cohorts VALUES (?,?,?,?,?,?)',
                       ('second',TOPIC['id'],'canonical','audit-new',second['selected_at'],second['payload']))
            for member in first['members']:
                db.execute('INSERT INTO youtube_cohort_members VALUES (?,?,?,?)',
                           ('second',member['video_id'],member['candidate_id'],member['published_at']))
        self.snapshot(second,day=23,views=148)
        self.assertEqual(self.dimensions()['engagement_velocity']['state'],'unavailable')

    def test_snapshot_before_cohort_selection_unavailable(self):
        cohort = self.audited_cohort()
        self.snapshot(cohort,day=20)
        self.snapshot(cohort,day=21,views=148)
        self.assertEqual(self.dimensions()['engagement_velocity']['state'],'unavailable')

    def test_legacy_sample_totals_do_not_enable_velocity(self):
        self.db.ingest([Observation(TOPIC['id'],'youtube','cohort-old','MY',f'2026-01-{day:02d}',
                                    STAMP,'sampled_views',100,'old',query_id='canonical',query='glass skin')
                       for day in (20,21)])
        self.assertEqual(self.dimensions()['engagement_velocity']['state'],'unavailable')

    def test_unavailable_snapshots_not_measured_as_zero(self):
        cohort = self.audited_cohort()
        self.snapshot(cohort)
        self.snapshot(cohort,day=23,views=None,likes=None,status='unavailable')
        self.assertEqual(self.dimensions()['engagement_velocity']['state'],'unavailable')

    def test_demo_raw_capture_excluded(self):
        self.capture(demo=True)
        self.assertEqual(self.dimensions()['creator_diversity']['state'],'unavailable')

    def test_unknown_topic_and_query(self):
        with self.assertRaises(KeyError):
            self.service.topic('missing')
        with self.assertRaises(ValueError):
            self.service.topic('glass-skin','missing')

    def test_api_schema_errors_and_read_only(self):
        self.google()
        old = dict(app_backend.app.config)
        self.addCleanup(app_backend.app.config.update,old)
        app_backend.app.config.update(TESTING=True,DATABASE_PATH=str(self.path),DATA_MODE='demo')
        digest = hashlib.sha256(self.path.read_bytes()).hexdigest()
        client = app_backend.app.test_client()
        response = client.get('/api/intelligence/glass-skin')
        self.assertEqual(response.status_code,200)
        payload = response.get_json()
        self.assertEqual(payload['data_mode'],'real')
        self.assertEqual(set(payload['dimensions']),NAMES)
        self.assertNotIn('trend_score',payload)
        self.assertNotIn('lifecycle',payload)
        self.assertEqual(client.get('/api/intelligence/no-topic').status_code,404)
        self.assertEqual(client.get('/api/intelligence/glass-skin?query_id=missing').status_code,400)
        self.assertEqual(client.post('/api/intelligence/glass-skin').status_code,405)
        self.assertEqual(digest,hashlib.sha256(self.path.read_bytes()).hexdigest())

    def test_absent_database_is_not_created(self):
        missing = Path(self.temp.name)/'not-created.sqlite3'
        result = IntelligenceService(missing,[TOPIC]).topic('glass-skin')
        self.assertEqual(result['data_mode'],'unavailable')
        self.assertFalse(missing.exists())


if __name__=='__main__':
    unittest.main()
