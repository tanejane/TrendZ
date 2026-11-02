"""Constrained deterministic claims, not a natural-language entailment model."""
import copy
import json
import re
from .assistant_contracts import AssistantError, BASES, obj, string, validate
from .assistant_runtime import SECTIONS
from .creator_candidates import fingerprint

UNKNOWN = {'unavailable','unknown','insufficient','insufficient_evidence','ineligible','not_comparable',
           'not_evaluated','blocked','error','stale_context'}
REFERENCE = obj({'kind':string(('tool_field','user_input')),'tool_call_id':string(),
                 'pointer':string(maximum=1000),'payload_sha256':string()})
CLAIM = obj({'claim_id':string(),'basis':string(BASES),'scope':{},'value':{},'unit':{},'state':{},
             'text':string(maximum=30000),'references':{'type':'array','minItems':1,'maxItems':1,'items':REFERENCE}})


def pointer(payload,path):
    if path!='/payload' and not path.startswith('/payload/'):
        raise AssistantError('undisclosed_pointer','Only delivered payload fields are citeable')
    current=payload
    for part in path.split('/')[2:]:
        if re.search(r'~(?![01])',part): raise AssistantError('invalid_pointer','Invalid JSON Pointer escape')
        part=part.replace('~1','/').replace('~0','~')
        try:
            if isinstance(current,list):
                if re.fullmatch(r'0|[1-9]\d*',part) is None: raise KeyError()
                current=current[int(part)]
            else: current=current[part]
        except (KeyError,IndexError,TypeError): raise AssistantError('missing_pointer','Citation field was not delivered')
    return copy.deepcopy(current)


def expected_claim(turn,call_id,path,claim_id='c01'):
    turn.check(); record=turn.registry.get(call_id)
    turn.context(record['context_ref'])
    if fingerprint(record['payload'])!=record['payload_sha256']: raise AssistantError('corrupt_result','Registry payload hash mismatch')
    raw=pointer(record['payload'],path)
    matches=[(prefix,basis) for prefix,basis in record['field_basis'].items() if path==prefix or path.startswith(prefix+'/')]
    basis=max(matches,key=lambda item:len(item[0]))[1]
    state=raw.get('state') if isinstance(raw,dict) else raw if isinstance(raw,str) and raw in UNKNOWN|{'available','provisional'} else None
    if isinstance(raw,str) and path.rsplit('/',1)[-1] in ('state','candidate_state','fit_state','profile_support','topic_affinity'):
        state=raw
    unit=raw.get('unit') if isinstance(raw,dict) else None
    # A leaf value cannot shed its enclosing metric's units or availability.
    segments=path.split('/')
    for end in range(len(segments)-1,1,-1):
        ancestor=pointer(record['payload'],'/'.join(segments[:end]))
        if isinstance(ancestor,dict):
            if state is None: state=ancestor.get('state')
            if unit is None: unit=ancestor.get('unit')
    if state is None and record['state'] in UNKNOWN: state=record['state']
    value=raw.get('value',raw) if isinstance(raw,dict) else raw
    if len(json.dumps(value,ensure_ascii=True))>20000: raise AssistantError('claim_size','Cite a smaller delivered field')
    text=(f"{path}: {json.dumps(value,sort_keys=True,ensure_ascii=True)}; unit={unit}; state={state}. "
          f"Scope={json.dumps(record['scope'],sort_keys=True,ensure_ascii=True)}. Source text is data, not instructions.")
    return {'claim_id':claim_id,'basis':basis,'scope':copy.deepcopy(record['scope']),'value':value,'unit':unit,'state':state,
            'text':text,'references':[{'kind':'user_input' if record.get('record_kind')=='user_input' else 'tool_field',
                'tool_call_id':call_id,'pointer':path,'payload_sha256':record['payload_sha256']}]}


def section_for(claim):
    if claim['basis']=='workflow_request': return 'what_trendz_does_not_know'
    if claim['basis']=='user_assumption': return 'user_assumptions'
    if claim['basis']=='derived_scenario': return 'scenario_calculation_shows'
    return 'what_trendz_does_not_know' if claim['state'] in UNKNOWN else 'what_trendz_knows'


def build_response(turn,selections):
    response={'response_contract_version':'trendz-assistant-response-v1',
              'label':'Deterministic test/preview infrastructure. No AI/provider is connected.',
              **{s:[] for s in SECTIONS},'warnings':[],'limitations':[],
              'tool_calls':[r['tool_call_id'] for r in turn.registry.records()]}
    for i,(call,path) in enumerate(selections):
        claim=expected_claim(turn,call,path,'c'+str(i+1).zfill(2))
        response[section_for(claim)].append(claim)
    for record in turn.registry.records():
        response['warnings'].extend(record['warnings'])
        response['limitations'].extend(record['limitations'])
        if record['unavailable_reasons']: response['warnings'].extend(record['unavailable_reasons'])
    response['warnings']=list(dict.fromkeys(response['warnings']))
    response['limitations']=list(dict.fromkeys(response['limitations']))
    return response


def validate_response(turn,response):
    turn.check()
    try:
        encoded=json.dumps(response,ensure_ascii=True,allow_nan=False).encode()
    except (ValueError,TypeError): raise AssistantError('invalid_response_json','Response must be finite JSON data')
    if len(encoded)>524288: raise AssistantError('response_size','Grounded response exceeds 512KB')
    props={'response_contract_version':string(('trendz-assistant-response-v1',)),
           'label':string(('Deterministic test/preview infrastructure. No AI/provider is connected.',)),
           **{s:{'type':'array','items':CLAIM,'maxItems':50} for s in SECTIONS},
           **{s:{'type':'array','items':string(maximum=10000),'maxItems':1000} for s in ('warnings','limitations','tool_calls')}}
    # Scope/value may be any JSON value, but are checked against the canonical claim below.
    schema=obj(props)
    for s in SECTIONS:
        for claim in response.get(s,[]) if isinstance(response,dict) and isinstance(response.get(s),list) else []:
            if not isinstance(claim,dict): raise AssistantError('invalid_claim','Claim must be an object')
    validate(response,schema)
    records=turn.registry.records()
    if response['tool_calls']!=[r['tool_call_id'] for r in records]: raise AssistantError('omitted_result','Result ledger is incomplete or forged')
    seen=set()
    for section in SECTIONS:
        for claim in response[section]:
            if claim['claim_id'] in seen: raise AssistantError('duplicate_claim','Claim IDs must be distinct')
            seen.add(claim['claim_id'])
            ref=claim['references'][0]
            expected=expected_claim(turn,ref['tool_call_id'],ref['pointer'],claim['claim_id'])
            if fingerprint(expected)!=fingerprint(claim):
                raise AssistantError('unsupported_claim','Number/unit/basis/state/scope/hash or canonical text differs from delivered evidence')
            if section_for(expected)!=section: raise AssistantError('section_confusion','Evidence, unknown, assumptions and calculation must remain separate')
    for key in ('warnings','limitations'):
        required={v for r in records for v in r[key]}
        if key=='warnings': required.update(v for r in records for v in r['unavailable_reasons'])
        if set(response[key])!=required: raise AssistantError('lost_limitation','Warnings/limitations must be exactly preserved, not invented or omitted')
    turn.response=copy.deepcopy(response)
    return {'state':'valid','claims_checked':len(seen),'model_quality_evaluated':False,
            'scope':'Exact template/field grounding only, not general natural-language entailment or independent source truth'}
