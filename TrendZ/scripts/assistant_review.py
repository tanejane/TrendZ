"""Trusted local operator confirmation demonstration. Not an AI or an exposed tool."""
import argparse
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from services.assistant_sources import AssistantSources
from services.assistant_runtime import AssistantTurn
from services.assistant_grounding import build_response,validate_response


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('topic-id','product-id','creator-id'): parser.add_argument('--'+name,required=True)
    parser.add_argument('--query-id',default='canonical'); parser.add_argument('--market',default='MY')
    parser.add_argument('--database',type=Path,default=ROOT/'reports/phase2-measured/pilot.sqlite3')
    parser.add_argument('--assumptions',type=Path,required=True)
    parser.add_argument('--export',type=Path)
    args=parser.parse_args(argv)
    scope={'topic_id':args.topic_id,'query_id':args.query_id,'market':args.market,
           'product_id':args.product_id,'creator_id':args.creator_id}
    with AssistantTurn(AssistantSources(ROOT,args.database),'Trusted local scenario review demonstration') as turn:
        human=turn.controller(); context=human.bind([scope]); handle=context['context_ref']
        preview=human.prepare_assumptions(handle,json.loads(args.assumptions.read_text(encoding='utf-8')))
        print('TEST/PREVIEW INFRASTRUCTURE ONLY. No AI/provider is connected.')
        print(json.dumps({'scope':scope,'assumptions':preview['assumptions'],'units':preview['units'],
                          'hash':preview['assumptions_sha256']},indent=2,ensure_ascii=True))
        if input('Type CONFIRM '+preview['assumptions_sha256'][:12]+' to approve exactly these inputs: ')!='CONFIRM '+preview['assumptions_sha256'][:12]:
            print('Cancelled. No calculation authorized.'); return
        reason=preview['assumptions']['manual_candidate_acknowledgement']['reason']
        manual=False
        if preview['manual_required']:
            manual=input('Type MANUAL '+str(reason)+' to acknowledge this manual-only context: ')=='MANUAL '+str(reason)
        permit=human.confirm_assumptions(preview['draft_ref'],preview['assumptions_sha256'],approve=True,
                                          acknowledge_manual=manual,manual_reason=reason)
        result=turn.call('evaluate_campaign_scenario',{'context_ref':handle,'context_pins':permit['context_pins'],
            'assumptions':permit['assumptions'],'schema_version':'campaign-scenario-v1','calculation_version':'campaign-economics-v1',
            'confirmation_ref':permit['confirmation_ref']})
        path='/payload/calculated_outcomes/base/modeled_roi' if result['state']=='success' else '/payload/code'
        response=build_response(turn,[(result['tool_call_id'],path)]); validate_response(turn,response)
        print(json.dumps(response,indent=2,ensure_ascii=True))
        if args.export:
            with args.export.open('x',encoding='utf-8') as handle:
                json.dump(turn.export_audit(),handle,indent=2,ensure_ascii=True)


if __name__=='__main__': main()
