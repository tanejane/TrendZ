import copy
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from services.database import Database
from services.youtube_store import YouTubeStore
from services.creator_store import CreatorStore, cohort_seeds, existing_content
from services.creator_analysis import analyze_creator, counters, hits
from services.creator_report import summarize, export
from services.ingestion.creator_youtube import CreatorYouTube, normalize_capture

STAMP='2026-10-16T04:00:00+00:00'
ROOT=Path(__file__).resolve().parents[1]
VOCAB=json.loads((ROOT/'data/creator_evidence_v1.json').read_text())


def seed(channel='c1'):
    return {'creator_id':'youtube:'+channel,'channel_id':channel,'display_name':'Example',
        'seeds':[{'topic_id':'retinol','query_id':'canonical','video_id':'v1','candidate_id':'candidate',
            'cohort_id':'cohort','run_id':'original','retrieved_at':'2026-10-14T04:00:00+00:00',
            'labelled_at':'2026-10-15T04:00:00+00:00','label':'relevant','label_event_id':1}]}


def video(identifier='v1',published='2026-10-01T00:00:00Z',title='Retinol skincare routine'):
    return {'id':identifier,'snippet':{'channelId':'c1','channelTitle':'Example','title':title,
        'description':'','publishedAt':published},'statistics':{'viewCount':'100','likeCount':'10','commentCount':'2'},
        'status':{'privacyStatus':'public'}}


def transport(items=None, more=False):
    items=items if items is not None else [video()]
    def request(resource,params):
        if resource=='channels':
            return {'items':[{'id':'c1','snippet':{'country':'MY'},'contentDetails':{'relatedPlaylists':{'uploads':'uploads'}}}]}
        if resource=='playlistItems':
            return {'items':[{'contentDetails':{'videoId':v['id']}} for v in items],**({'nextPageToken':'more'} if more else {})}
        return {'items':items}
    return request


def capture(items=None):
    return CreatorYouTube(key='fixture-secret',transport=transport(items),clock=lambda:STAMP).collect('c1')


def analyze(rows,creator=None,scope='bounded_uploads',metadata=None):
    return analyze_creator(creator or seed(),rows,VOCAB,STAMP,{'scope':scope,'state':'available'},metadata)


class CollectionTests(unittest.TestCase):
    def test_bounded_three_requests_no_search_or_credentials_in_archive(self):
        result=capture([video('v'+str(i)) for i in range(50)])
        self.assertEqual(len(result['selected_ids']),20)
        self.assertEqual([r['resource'] for r in result['requests']],['channels','playlistItems','videos'])
        self.assertNotIn('fixture-secret',json.dumps(result))
        self.assertIsNone(result['region_code'])

    def test_invalid_limits(self):
        for maximum,scan in [(0,50),(51,50),(20,10),(20,51)]:
            with self.assertRaises(ValueError):
                CreatorYouTube(key='fake',transport=transport()).collect('c1',maximum,scan)

    def test_missing_key(self):
        from unittest.mock import patch
        with patch.dict('os.environ',{},clear=True),self.assertRaises(ValueError):
            CreatorYouTube()

    def test_missing_channel(self):
        result=CreatorYouTube(key='fake',transport=lambda r,p:{'items':[]},clock=lambda:STAMP).collect('c1')
        self.assertEqual(result['state'],'unavailable')
        self.assertEqual(len(result['requests']),1)

    def test_transport_failure_sanitized(self):
        def fail(r,p):
            raise RuntimeError('https://example.test?key=fixture-secret')
        result=CreatorYouTube(key='fixture-secret',transport=fail,clock=lambda:STAMP).collect('c1')
        self.assertNotIn('fixture-secret',json.dumps(result))
        self.assertEqual(result['state'],'unavailable')

    def test_quota_status_retained_without_exception_url(self):
        def fail(r,p):
            raise RuntimeError('YouTube HTTP 403; fixture-secret')
        result=CreatorYouTube(key='fixture-secret',transport=fail,clock=lambda:STAMP).collect('c1')
        self.assertEqual(result['requests'][0]['http_status'],403)
        self.assertNotIn('fixture-secret',json.dumps(result))

    def test_malformed_items_preserved_as_unavailable(self):
        result=CreatorYouTube(key='fake',transport=lambda r,p:{'items':[None]},clock=lambda:STAMP).collect('c1')
        self.assertEqual(result['state'],'unavailable')
        self.assertEqual(result['requests'][0]['response']['items'],[None])

    def test_public_identity_date_checks(self):
        items=[video('good'),video('private'),video('other'),video('future','2027-01-01T00:00:00Z')]
        items[1]['status']['privacyStatus']='private'
        items[2]['snippet']['channelId']='different'
        result=capture(items)
        self.assertEqual(result['selected_ids'],['good'])
        self.assertEqual(len(result['excluded']),3)
        self.assertEqual(result['state'],'partial')

    def test_duplicate_ids_and_statistics_dates(self):
        result=capture([video(),video()])
        rows=normalize_capture(result,'r1')
        analysis=analyze(rows)
        self.assertEqual(len(analysis['videos']),1)
        self.assertEqual(analysis['videos'][0]['published_at'],'2026-10-01T00:00:00Z')
        self.assertEqual(analysis['videos'][0]['retrieved_at'],STAMP)
        self.assertEqual(analysis['engagement']['velocity']['state'],'unavailable')

    def test_missing_hidden_counters_are_null(self):
        v=video()
        v['statistics']={'viewCount':'0','likeCount':'bad','commentCount':'-1'}
        row=normalize_capture(capture([v]),'r1')[0]
        self.assertEqual(row['views'],0)
        self.assertIsNone(row['likes'])
        self.assertIsNone(row['comments'])
        self.assertIsNone(counters([row])['like_view_ratio']['median_of_video_ratios'])


class AnalysisTests(unittest.TestCase):
    def rows(self,items):
        return normalize_capture(capture(items),'r1')

    def test_aliases_and_word_boundaries(self):
        self.assertTrue(hits({'title':'NICOTINAMIDE skin care'},VOCAB['topics']['niacinamide']['aliases']))
        self.assertFalse(hits({'title':'retinoldummy'},VOCAB['topics']['retinol']['aliases']))
        self.assertTrue(hits({'title':'new lip-stain'},VOCAB['topics']['lip-tint']['aliases']))

    def test_retinal_not_retinol_and_proxy_not_glass_skin(self):
        result=analyze(self.rows([video('x',title='Retinal and dewy skin')]),seed())
        self.assertEqual(result['topics']['retinol']['proposed_relevant_count'],0)
        self.assertEqual(result['topics']['glass-skin']['proposed_relevant_count'],0)
        self.assertTrue(result['topics']['retinol']['video_evidence'][0]['supporting_hits'])

    def test_deepavali_requires_makeup_context(self):
        result=analyze(self.rows([video('x',title='Diwali outfits shopping')]))
        self.assertEqual(result['topics']['deepavali-glam']['proposed_relevant_count'],0)
        result=analyze(self.rows([video('x',title='Diwali makeup glam')]))
        self.assertEqual(result['topics']['deepavali-glam']['proposed_relevant_count'],1)

    def test_single_video_not_stable_classification(self):
        result=analyze(self.rows([video()]))
        self.assertFalse(result['profile']['evidence_ready_for_profile_review'])
        self.assertEqual(result['profile']['proposed_specializations'],[])
        self.assertIsNone(result['profile']['human_domain'])
        self.assertIsNone(result['topics']['retinol']['strength_state'])
        self.assertEqual(result['topics']['retinol']['confirmed_sample_relevant_count'],1)

    def test_repeated_content_proposals_remain_provisional(self):
        rows=self.rows([video('v1','2026-09-01T00:00:00Z'),video('v2','2026-09-20T00:00:00Z'),video('v3','2026-10-01T00:00:00Z')])
        result=analyze(rows)
        self.assertIn('skincare',result['profile']['proposed_specializations'])
        self.assertEqual(result['topics']['retinol']['coverage'],'repeated_screened')
        self.assertEqual(result['topics']['retinol']['confirmed_sample_relevant_count'],1)
        self.assertTrue(result['topics']['retinol']['draft_threshold_sensitivity']['draft_strong_gate']['screen_assisted_meets_gate'])
        self.assertFalse(result['topics']['retinol']['draft_threshold_sensitivity']['draft_strong_gate']['confirmed_only_meets_gate'])
        self.assertIsNone(result['topics']['retinol']['strength_state'])
        self.assertFalse(result['independent_gold'])

    def test_clustered_publications_do_not_pass_span(self):
        result=analyze(self.rows([video('a'),video('b'),video('c')]))
        self.assertFalse(result['profile']['evidence_ready_for_profile_review'])
        self.assertFalse(result['topics']['retinol']['draft_threshold_sensitivity']['draft_moderate_gate']['screen_assisted_meets_gate'])

    def test_legacy_share_is_unavailable(self):
        result=analyze(self.rows([video()]),scope='query_selected_legacy')
        self.assertIsNone(result['topics']['retinol']['proposed_topic_share'])

    def test_seed_not_in_sample_does_not_leak_into_sample_denominator(self):
        result=analyze(self.rows([video('new',title='Skincare cleanser')]))
        topic=result['topics']['retinol']
        self.assertEqual(topic['confirmed_sample_relevant_count'],0)
        self.assertEqual(topic['prior_confirmed_outside_sample'],['v1'])
        self.assertEqual(topic['proposed_topic_share'],0)

    def test_cutoff_excludes_future_retrieval_and_labels(self):
        rows=self.rows([video()])
        rows[0]['retrieved_at']='2026-10-17T00:00:00Z'
        s=seed()
        s['seeds'][0]['labelled_at']='2026-10-17T00:00:00Z'
        result=analyze(rows,s)
        self.assertEqual(result['videos'],[])
        self.assertEqual(result['topics']['retinol']['prior_confirmed_video_ids'],[])

    def test_market_never_infers_audience(self):
        result=analyze(self.rows([video()]),metadata={'snippet':{'country':'MY'}})
        self.assertEqual(result['market_evidence']['state'],'partial')
        self.assertEqual(result['market_evidence']['audience_geography']['state'],'unknown')
        self.assertIsNone(result['market_evidence']['expansion_region_code'])

    def test_population_variability_and_ratio_formula(self):
        rows=self.rows([video('a'),video('b')])
        rows[0].update(views=100,likes=10)
        rows[1].update(views=300,likes=60)
        result=counters(rows)
        self.assertEqual(result['views']['median'],200)
        self.assertEqual(result['views']['population_stddev'],100)
        self.assertAlmostEqual(result['like_view_ratio']['median_of_video_ratios'],0.15)

    def test_publication_recency_uses_utc_not_offset_string_order(self):
        items=[video('a','2026-10-01T01:00:00+02:00'),video('b','2026-10-01T00:00:00Z')]
        result=analyze(self.rows(items))
        self.assertEqual(result['videos'][0]['video_id'],'b')


class StoreTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.db=Database(Path(self.temp.name)/'pilot.sqlite3')
        self.db.sync_topics([{'id':t,'name':t,'query':t,'category':'beauty','market':'MY'} for t in VOCAB['topics']])
        self.raw=YouTubeStore(self.db)
        self.store=CreatorStore(self.db)
        self.payload=capture()
        self.raw.save_run(self.payload,'creator_expansion','r1')
        self.result=analyze(normalize_capture(self.payload,'r1'))

    def test_additive_immutable_idempotent_storage(self):
        self.store.save_analysis(seed(),self.result)
        self.store.save_analysis(seed(),self.result)
        with self.db.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM creators').fetchone()[0],1)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM creator_topic_affinity_runs').fetchone()[0],8)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM youtube_runs').fetchone()[0],1)
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute("UPDATE creator_profiles SET state='verified'")
            with self.assertRaises(sqlite3.IntegrityError):
                db.execute('DELETE FROM creator_contents')

    def test_wrong_raw_video_reference_rejected_atomically(self):
        self.result['videos'][0]['video_id']='invented'
        with self.assertRaises(ValueError):
            self.store.save_analysis(seed(),self.result)
        with self.db.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM creators').fetchone()[0],0)

    def test_different_payload_cannot_overwrite_run(self):
        different=copy.deepcopy(self.payload)
        different['selected_ids']=[]
        with self.assertRaises(ValueError):
            self.raw.save_run(different,'creator_expansion','r1')

    def test_empty_profile_revisions_do_not_collide_between_creators(self):
        for channel in ('one','two'):
            self.store.save_analysis(seed(channel),analyze([],seed(channel)))
        with self.db.connect() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM creator_profiles').fetchone()[0],2)

    def test_summary_failed_collection_not_counted_as_expanded(self):
        result=analyze([])
        result['collection']['state']='unavailable'
        summary=summarize([result])
        self.assertEqual(summary['live_expanded_creators'],0)
        self.assertEqual(summary['unavailable_collections'],1)

    def test_review_export_blank_labels_and_does_not_overwrite_edits(self):
        target=Path(self.temp.name)/'report'
        export(target,[self.result],'Fixture test',{})
        data=json.loads((target/'review_dataset.json').read_text())
        self.assertIsNone(data['creators'][0]['human_profile_label'])
        self.assertIsNone(data['creators'][0]['topics']['retinol']['video_evidence'][0]['human_label'])
        (target/'review_dataset.json').write_text('human edits')
        with self.assertRaises(ValueError):
            export(target,[self.result],'Fixture test',{})

    def test_seed_selection_reuses_only_current_relevant_cohort_identity(self):
        payload={'topic_id':'retinol','query_id':'canonical','query':'retinol','market':'MY',
                 'retrieved_at':STAMP,'data_mode':'real','videos':[{'id':'v1','channelId':'c1'}],
                 'present_day_statistics':[video()]}
        self.raw.save_run(payload,'legacy','original')
        self.raw.freeze_audit('audit',[{'run_id':'original','topic_id':'retinol','query_id':'canonical',
            'query':'retinol','video_id':'v1','rank':1,'channel_id':'c1','channel_name':'Example',
            'published_at':'2026-10-01T00:00:00Z','retrieved_at':STAMP,'data_mode':'real'}])
        candidate=self.raw.audit_rows('audit')[0]['candidate_id']
        with self.db.connect() as db:
            db.execute('INSERT INTO youtube_audit_labels VALUES (?,?,?,?)',(candidate,'relevant','fixture',STAMP))
            db.execute('INSERT INTO youtube_label_events(candidate_id,label,notes,labelled_at) VALUES (?,?,?,?)',
                       (candidate,'relevant','fixture',STAMP))
        self.raw.create_cohorts('audit',size=1)
        selected=cohort_seeds(self.db.path,['retinol'],'audit',expected_size=1)
        self.assertEqual(selected[0]['channel_id'],'c1')
        self.assertEqual(len(existing_content(self.db.path,selected[0])),1)
        with self.db.connect() as db:
            db.execute("UPDATE youtube_audit_labels SET label='irrelevant'")
        with self.assertRaises(ValueError):
            cohort_seeds(self.db.path,['retinol'],'audit',expected_size=1)

    def test_full_command_resumes_forty_channels_without_new_requests(self):
        import contextlib
        import io
        from unittest.mock import patch
        from scripts import creator_phase5b as cli
        root=Path(self.temp.name)/'project'
        (root/'data').mkdir(parents=True)
        (root/'data/pilot_phase2.json').write_text(json.dumps({'topic_ids':list(VOCAB['topics'])}))
        (root/'data/creator_evidence_v1.json').write_text(json.dumps(VOCAB))
        seeds=[seed('channel'+str(i)) for i in range(40)]
        class FakeAdapter:
            calls=0
            def collect(self,channel_id,**policy):
                self.calls+=1
                payload=capture()
                payload['channel_id']=channel_id
                payload['requests'][0]['response']['items'][0]['id']=channel_id
                payload['requests'][2]['response']['items'][0]['snippet']['channelId']=channel_id
                return payload
        adapter=FakeAdapter()
        for name in ('first','resume'):
            argv=['creator_phase5b.py','collect','--db',str(self.db.path),'--output',str(root/name),'--as-of',STAMP]
            with patch.object(cli,'ROOT',root),patch.object(cli,'cohort_seeds',return_value=seeds), \
                    patch.object(cli,'CreatorYouTube',return_value=adapter),patch('sys.argv',argv), \
                    contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
                cli.main()
        self.assertEqual(adapter.calls,40)
        metrics=json.loads((root/'resume/metrics.json').read_text())
        self.assertEqual(metrics['manifest']['new_request_count'],0)
        self.assertEqual(metrics['creator_count'],40)
        self.assertEqual(metrics['sample_video_records'],40)
        with self.db.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM youtube_runs WHERE run_id LIKE 'creator-%'").fetchone()[0],40)
            self.assertEqual(db.execute('SELECT COUNT(*) FROM youtube_video_snapshots').fetchone()[0],0)
        class QuotaAdapter:
            calls=0
            def collect(self,channel_id,**policy):
                self.calls+=1
                payload=capture()
                payload.update(channel_id=channel_id,state='unavailable',reason='Request failed',selected_ids=[])
                payload['requests']=payload['requests'][:1]
                payload['requests'][0].pop('response')
                payload['requests'][0].update(http_status=403,error='Request failed')
                return payload
        quota=QuotaAdapter()
        argv=['creator_phase5b.py','collect','--db',str(self.db.path),'--output',str(root/'quota'),
              '--as-of',STAMP,'--batch-id','quota-fixture']
        with patch.object(cli,'ROOT',root),patch.object(cli,'cohort_seeds',return_value=seeds), \
                patch.object(cli,'CreatorYouTube',return_value=quota),patch('sys.argv',argv), \
                contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            cli.main()
        self.assertEqual(quota.calls,1)
        metrics=json.loads((root/'quota/metrics.json').read_text())
        self.assertEqual(metrics['manifest']['new_request_count'],1)
        self.assertEqual(metrics['unavailable_collections'],40)


if __name__=='__main__':
    unittest.main()
