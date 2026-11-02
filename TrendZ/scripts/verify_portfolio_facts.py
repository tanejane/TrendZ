"""Derive bounded portfolio facts from saved artifacts, never supplied claims."""
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def main():
    sources={}
    def read(path):
        raw=(ROOT/path).read_bytes();sources[path]=hashlib.sha256(raw).hexdigest()
        return json.loads(raw)
    pilot=read('data/pilot_phase2.json')
    catalogue=read('reports/phase4d-lite/catalogue_hardened_v1.json')
    expanded=read('reports/phase5b/live-initial/review_dataset.json')
    profiles=read('reports/phase5c/final-v1/creator_profile_review_export.json')
    affinities=read('reports/phase5c/final-v1/creator_affinity_review_export.json')
    rerun=read('reports/phase4d-lite/rerun.json')
    methods=read('reports/phase4d-lite/metrics_summary.json')
    explanations=read('reports/phase4d-lite/explanation_support_final.json')
    review=read('reports/phase5c/final-v1/validation-9235148176a44bc5.json')
    predictions=read('reports/phase4d-lite/predictions_after.json')
    from services.assistant_contracts import SCHEMAS
    from services.creator_candidates import CreatorCandidates
    candidates=CreatorCandidates(ROOT)
    ids={c['creator_id'] for c in expanded['creators']}
    videos={v['video_id'] for c in expanded['creators'] for v in c['videos']}
    product_ids={p['product_id'] for p in catalogue['products']}
    pairs=sum(len(topic['assessments']) for topic in predictions.values())
    if not(len(ids)==len(profiles['rows'])==40 and len(videos)==747 and len(product_ids)==32 and pairs==256):
        raise ValueError('Unexpected evidence count; inspect rather than publishing an assumed fact.')
    path=ROOT/'reports/phase2-measured/pilot.sqlite3'
    sources['reports/phase2-measured/pilot.sqlite3']=hashlib.sha256(path.read_bytes()).hexdigest()
    with sqlite3.connect(path.as_uri()+'?mode=ro',uri=True) as db:
        coverage=[{'source':s,'observations':n,'first_date':start,'last_date':end}
                  for s,n,start,end in db.execute('SELECT source,COUNT(*),MIN(observation_date),MAX(observation_date) FROM source_observations WHERE is_demo=0 GROUP BY source')]
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        immutable_runs=db.execute('SELECT COUNT(*) FROM youtube_runs').fetchone()[0] if 'youtube_runs' in tables else None
    tests=unittest.defaultTestLoader.discover(str(ROOT/'tests')).countTestCases()
    facts={'pilot_topics':len(pilot['topic_ids']),'pilot_topic_ids':pilot['topic_ids'],
           'configured_topics':len(read('data/tracked_topics.json')),
           'creator_profiles':len(ids),'sampled_public_creator_video_ids':len(videos),
           'catalogue_products':len(product_ids),'fixed_product_review_pairs':pairs,
           'creator_profile_review_units':len(profiles['rows']),'creator_affinity_review_units':len(affinities['rows']),
           'creator_review_units':len(profiles['rows'])+len(affinities['rows']),
           'creator_review_basis':review['overall']['review_basis'],
           'python_tests_discovered':tests,'assistant_internal_tools':len(SCHEMAS),
           'measured_source_coverage':coverage,'immutable_youtube_runs_in_pilot_db':immutable_runs,
           'product_evidence_cleanup_metrics':methods['overall'],
           'product_explanation_audit':{'expanded_checks':explanations['summary'],'original_cohort':explanations['original_cohort']},
           'creator_profile_agreement':review['overall']['profile_agreement'],
           'creator_specializations':review['overall']['specializations'],
           'creator_original_readiness_groups':{k:v['profiles'] for k,v in review['by_readiness'].items()},
           'product_method_unchanged':not rerun['semantic_method_changed'],
           'product_pins':candidates.context('glass-skin')['pins'],
           'independent_validation':False,'live_llm_provider':'intentionally_deferred',
           'campaign_economics':'deterministic, assumption-based ROI / sensitivity / break-even',
           'source_sha256':sources}
    verification=ROOT/'reports/phase8a/final_verification.json'
    if verification.exists():
        checked=read('reports/phase8a/final_verification.json')
        facts['executed_verification']={k:checked[k] for k in ('python','javascript_unit_tests','assistant_harness','browser_checks')}
    out=ROOT/'showcase/demo/verified_facts.json'
    out.write_text(json.dumps(facts,indent=2,ensure_ascii=True)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in facts.items() if k not in ('source_sha256','product_evidence_cleanup_metrics')},indent=2))


if __name__=='__main__':main()
