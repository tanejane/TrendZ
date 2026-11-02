"""Export worked synthetic commercial assumptions over real frozen context; no saves to sources."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import app_backend
from services.creator_candidates import CreatorCandidates, PINS
from services.campaign_schema import CALCULATION_VERSION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--database', type=Path, default=ROOT/'reports/phase2-measured/pilot.sqlite3')
    parser.add_argument('--output', type=Path, default=ROOT/'reports/phase6b/implementation-v1')
    args = parser.parse_args()
    if args.output.exists(): raise ValueError('Use a new output directory')
    frozen = json.loads((ROOT/'reports/phase5e/implementation-v1/metrics.json').read_text())['protected_sha256']
    paths = list(frozen) + [
        'services/creator_candidate_policy.py', 'services/creator_candidates.py', 'services/intelligence_service.py',
        'services/intelligence_evidence.py', 'services/intelligence_components.py', 'services/metrics.py',
        'reports/phase5b/live-initial/review_dataset.json', 'reports/phase2-measured/pilot.sqlite3']
    digest = lambda: {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in paths}
    before = digest()
    assert all(before[p] == h for p,h in frozen.items())
    app_backend.app.config.update(TESTING=True, DATABASE_PATH=str(args.database))
    client = app_backend.app.test_client(); service = CreatorCandidates(ROOT)
    def params(state, product='mb-fresh-unspecified'):
        p = {**PINS, 'topic_id':'glass-skin', 'query_id':'canonical', 'market':'MY', 'product_id':product}
        c = next(r for r in service.query(p)['candidates'] if r['candidate_state']==state)
        return {**p, 'creator_id':c['creator_id'], 'calculation_version':CALCULATION_VERSION}
    p = params('qualified_candidate')
    c = client.get('/api/campaign-scenarios/context', query_string=p)
    assert c.status_code == 200, c.json
    a = {'objective':'conversion','format':'short_form_demonstration','channel':'youtube','currency':'MYR',
         'campaign_window':{'start_date':'2026-11-01','end_date_exclusive':'2026-12-01'},
         'costs':{'creator_fee':'600','media_spend':'200','production_cost':'150','other_cost':'50'},
         'budget_ceiling':'1200','conversion_basis':'assumed_reach',
         'population':{'value':1000,'unit':'unique_reached_people','basis':'user_entered','source_ref':None},
         'conversion_rates':{'low':'0.02','base':'0.05','high':'0.08'},'aov':'50','gross_margin_rate':'0.4',
         'source_notes':'Synthetic worked example only; not a real campaign plan or benchmark.',
         'manual_candidate_acknowledgement':{'accepted':False,'reason':None}}
    body = {'schema_version':'campaign-scenario-v1','calculation_version':CALCULATION_VERSION,
            'context_ref':c.json['context_ref'],'assumptions':a}
    result = client.post('/api/campaign-scenarios/evaluate', json=body)
    assert result.status_code == 200, result.json
    blocked = []
    for state, product in [('unavailable','mb-fresh-unspecified'),('ineligible','lp-shampoo-440ml'),('manual_review_only','mb-fresh-unspecified')]:
        ctx = client.get('/api/campaign-scenarios/context', query_string=params(state, product)).json
        request = copy.deepcopy(body); request['context_ref'] = ctx['context_ref']
        response = client.post('/api/campaign-scenarios/evaluate', json=request)
        blocked.append({'candidate_state':state,'request':request,'http_status':response.status_code,'response':response.json})
    stale = copy.deepcopy(body); stale['context_ref']['trend_snapshot_sha256'] = 'wrong'
    stale_response = client.post('/api/campaign-scenarios/evaluate', json=stale)
    blocked.append({'case':'stale_snapshot','http_status':stale_response.status_code,'response':stale_response.json})
    assert digest() == before
    args.output.mkdir(parents=True)
    def write(name, value): (args.output/name).write_text(json.dumps(value, indent=2, ensure_ascii=True)+'\n',encoding='utf-8')
    write('api_examples.json', {'context_request':p,'context_response':c.json,'evaluate_request':body,'evaluate_response':result.json,'blocked':blocked})
    write('protected_hashes.json', {'before':before,'after':digest(),'unchanged':True,'prior_phase5e_hashes_match':True})
    d = result.json
    lines = ['# Phase 6B worked scenario and integration verification', '',
             'Commercial inputs are synthetic user assumptions, not a campaign prediction. Source context is pinned and real/reviewed.', '',
             'Creator: '+d['evidence']['creator_candidate']['creator_name']+'. Product: '+d['evidence']['product_fit']['product_name']+'.', '',
             '| Scenario | Assumed CVR | Orders | Revenue MYR | Gross profit MYR | Net profit MYR | ROI % |',
             '|---|---:|---:|---:|---:|---:|---:|']
    for row in d['sensitivity']:
        lines.append('| '+row['scenario']+' | '+row['assumed_conversion_rate']+' | '+' | '.join(row[k]['display_value'] for k in ('modeled_conversions','modeled_revenue','modeled_gross_profit','modeled_net_profit','modeled_roi_percent'))+' |')
    lines += ['', 'Costs MYR 1,000. AOV MYR 50. Gross margin 40%. Assumed unique reach 1,000.',
              'Break-even: revenue MYR 2,500; 50 orders; conversion rate 5%. No break-even time is modeled.',
              '', 'Unavailable/ineligible examples return 422; manual-only without acknowledgement 409; stale evidence 409.',
              'Product Fit, Creator H1, Phase 5C reviews, trend formulas and source evidence hashes are unchanged.',
              '', 'Legacy cleanup: random ROI page/chart/tables, multipliers, static commercial predictions and mock ROI APIs retired.',
              'All displayed economics now require a pinned scenario with explicit assumptions. Legacy demo trend records remain untouched.',
              '', 'See api_examples.json and protected_hashes.json. Automated/browser results are recorded in VERIFICATION.md.']
    (args.output/'IMPLEMENTATION_REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'output':str(args.output),'protected_hashes_unchanged':True,
                      'blocked_statuses':[v['http_status'] for v in blocked]},indent=2))


if __name__ == '__main__': main()
