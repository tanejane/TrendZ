"""Deterministic, internal-only gateway. No provider, web route or conversational agent."""
import copy
import json
import secrets
import time
from datetime import datetime, timezone

from .assistant_contracts import SCHEMAS, VERSION, AssistantError, validate
from .assistant_sources import candidate_view, comparison, sanitize
from .campaign_schema import CALCULATION_VERSION, normalize_assumptions
from .creator_candidates import PINS, fingerprint

SECTIONS = ('what_trendz_knows','what_trendz_does_not_know','user_assumptions','scenario_calculation_shows')


class Registry:
    """Canonical bytes are immutable; every read returns a detached JSON value."""
    def __init__(self,guard=lambda:None): self._records,self._guard = {},guard
    def add(self, record):
        self._guard()
        key = record['tool_call_id']
        if key in self._records: raise AssistantError('duplicate_call_id','Tool IDs are immutable')
        self._records[key] = json.dumps(record,sort_keys=True,ensure_ascii=True,allow_nan=False).encode()
        return self.get(key)
    def get(self, key):
        self._guard()
        if key not in self._records: raise AssistantError('unknown_citation','Tool result does not exist')
        return json.loads(self._records[key])
    def records(self):
        self._guard()
        return [json.loads(v) for v in self._records.values()]
    def clear(self): self._records.clear()


def collect(value, keys):
    found = []
    if isinstance(value,dict):
        for key,item in value.items():
            if key in keys:
                if isinstance(item,list): found.extend(str(v) for v in item)
                elif isinstance(item,str): found.append(item)
            found.extend(collect(item,keys))
    elif isinstance(value,list):
        for item in value: found.extend(collect(item,keys))
    return list(dict.fromkeys(found))


def identifiers(value):
    out = {}
    if isinstance(value,dict):
        for key,item in value.items():
            if key in ('evidence_ids','evidence_identifiers','source_ids','review_provenance'):
                out.setdefault(key,[]).append(item)
            for k,items in identifiers(item).items(): out.setdefault(k,[]).extend(items)
    elif isinstance(value,list):
        for item in value:
            for k,items in identifiers(item).items(): out.setdefault(k,[]).extend(items)
    return out


class AssistantTurn:
    def __init__(self, sources, user_query='', clock=time.monotonic, ttl=300, budget=10, max_payload=524288):
        if not isinstance(user_query,str) or len(user_query)>2000: raise AssistantError('query_size','User query is bounded text')
        self.sources, self.clock, self.expires = sources, clock, clock()+ttl
        self.budget, self.max_payload, self.used = budget, max_payload, 0
        self.registry, self._contexts, self._drafts, self._approvals = Registry(self.check), {}, {}, {}
        self._cap, self.closed = object(), False
        self.user_query, self.response = user_query, None

    def controller(self):
        """Trusted host/controller capability. Never included in SCHEMAS or tool payloads."""
        return HumanController(self,self._cap)

    def check(self):
        if self.closed or self.clock()>=self.expires:
            self._contexts.clear(); self._drafts.clear(); self._approvals.clear(); self.registry.clear()
            self.response=None; self.user_query=''
            raise AssistantError('expired_turn','Turn/context expired; bind a new turn explicitly')

    def context(self, handle):
        self.check()
        if handle not in self._contexts: raise AssistantError('stale_context_ref','Unknown, expired or cross-turn context')
        return self._contexts[handle]

    def scope(self, ctx, args):
        for data in ctx['data']:
            scope = data['scope']
            if all(args.get(k)==scope.get(k) for k in ('topic_id','query_id','market')):
                if any(k in args and args[k]!=scope.get(k) for k in ('product_id','creator_id')):
                    continue
                return data
        raise AssistantError('scope_mismatch','Topic/query/market is not authorized by this context')

    def call(self, name, args):
        self.check()
        if self.used>=self.budget: raise AssistantError('tool_budget','Tool-call budget exhausted; no hidden extra calls')
        self.used += 1
        call_id = 't'+str(self.used).zfill(2)
        scope, pins, basis, payload, valid_args, ctx_ref = {}, {}, {'/payload':'upstream_calculated'}, {}, {}, None
        if isinstance(args,dict) and isinstance(args.get('context_ref'),str) and args['context_ref'] in self._contexts:
            ctx_ref=args['context_ref']
        state, code, safe_message = 'success', None, None
        try:
            if name not in SCHEMAS: raise AssistantError('unknown_tool','Tool is not allowlisted')
            if len(json.dumps(args,allow_nan=False).encode())>65536: raise AssistantError('request_size','Tool request exceeds 64KB')
            validate(args,SCHEMAS[name])
            ctx_ref = args['context_ref']; ctx = self.context(ctx_ref)
            valid_args = copy.deepcopy(args)
            if name=='compare_trends':
                requested = args['topics']
                if len({s['topic_id'] for s in requested})!=len(requested): raise AssistantError('duplicate_topic','Comparison topics must be distinct')
                data = [self.scope(ctx,s) for s in requested]
                scope, pins = requested, [d['pins'] for d in data]
                payload = {'topics':[d['trend']['dimensions'] for d in data],
                           'absolute_interest_comparability':comparison(self.sources.comparison_proof(requested),requested,
                               [d['trend']['dimensions']['query'] for d in data],
                               [d['trend']['dimensions']['dimensions']['demand_momentum']['observation_window'] for d in data]),
                           'comparison_scope':'Side-by-side component evidence only; no overall winner or score',
                           'creator_availability':'Requires selected product contexts; topic counts are not global creator merit'}
                basis['/payload/creator_availability']='workflow_request'
            elif name=='evaluate_campaign_scenario':
                ref = args['context_pins']
                data = self.scope(ctx,ref); scope, pins = data['scope'], data['pins']
                if not data.get('campaign',{}).get('scenario_eligible'):
                    raise AssistantError('blocked_candidate','Unavailable/ineligible or nonpositive Product Fit cannot be overridden')
                if data['campaign']['context_ref']!=ref:
                    raise AssistantError('pin_mismatch','Campaign pins differ from captured context')
                approval = self._approvals.get(args['confirmation_ref'])
                normalized = normalize_assumptions(args['assumptions'])
                if not approval or approval['context_ref']!=ctx_ref or approval['used'] or approval['expires']<=self.clock() or approval['hash']!=fingerprint(normalized) or approval['pins']!=ref:
                    raise AssistantError('confirmation_required','Trusted explicit confirmation for these exact assumptions/context is required')
                result = self.sources.evaluate({'schema_version':args['schema_version'],'calculation_version':args['calculation_version'],
                                               'context_ref':ref,'assumptions':normalized})
                approval['used'] = True
                payload = result
                payload['evidence']['creator_candidate'] = candidate_view(payload['evidence']['creator_candidate'])
                basis.update({'/payload/assumptions':'user_assumption','/payload/calculated_outcomes':'derived_scenario',
                              '/payload/sensitivity':'derived_scenario','/payload/break_even':'derived_scenario',
                              '/payload/scenario_explanation':'derived_scenario'})
                for i in range(len(payload['sensitivity'])):
                    basis[f'/payload/sensitivity/{i}/assumed_conversion_rate']='user_assumption'
                basis['/payload/calculated_outcomes/base/assumed_conversion_rate']='user_assumption'
            else:
                data = self.scope(ctx,args); scope, pins = data['scope'], data['pins']
                payload, extra_basis = self.dispatch(name,args,data,ctx)
                basis.update(extra_basis)
            required={
                'get_trend_intelligence':{'topic_id','query_id','market','dimensions','method_version'},
                'compare_trends':{'topics','absolute_interest_comparability'},
                'get_product_fit':{'product_id','fit_state','supporting_evidence','method_version','provenance'},
                'list_positive_product_fits':{'products','pagination'},
                'get_creator_candidates':{'candidates','counts','pagination'},
                'get_creator_candidate_evidence':{'creator_id','candidate_state','evidence','review_basis'},
                'get_campaign_context':{'context_ref','evidence','scenario_eligible'},
                'evaluate_campaign_scenario':{'evidence','assumptions','calculated_outcomes','break_even','sensitivity'},
                'trace_decision':{'trend','product_fit','creator_candidate','campaign','distinction'}}[name]
            if not isinstance(payload,dict) or not required<=set(payload):
                raise AssistantError('invalid_tool_result','Authoritative result shape is malformed; no fabricated fallback')
            warnings = []
            payload = sanitize(payload,self.sources.allowed_hosts,warnings)
            warnings += collect(payload,{'warnings','quality_warnings','explicitness_warning'})
            limitations = collect(payload,{'limitations','scope','comparison_scope'})
            limitations.append('Tools do not establish future campaign reach, endorsement, product use, causal effectiveness or campaign success.')
            unavailable = collect(payload,{'unavailable_reasons','provisional_reasons','missing_evidence'})
            if isinstance(payload,dict) and payload.get('scenario_eligible') is False: state='blocked'
            elif isinstance(payload,dict) and payload.get('data_mode')=='unavailable': state='unavailable'
            if len(json.dumps(payload,ensure_ascii=True,allow_nan=False).encode())>self.max_payload:
                raise AssistantError('result_size','Result exceeds delivery limit; request a bounded projection')
        except Exception as error:
            code = getattr(error,'code','source_error')
            if getattr(error,'status',None)==409 or code in ('stale_context','pin_mismatch'):
                state = 'stale_context'
            else: state = 'blocked' if code in ('confirmation_required','blocked_candidate','manual_acknowledgement_required') else 'error'
            safe_message = str(error) if isinstance(error,AssistantError) or hasattr(error,'code') else 'Tool source/schema unavailable; no fallback'
            payload = {'code':code,'reason':safe_message}
            basis={'/payload':'diagnostic'}
            warnings, limitations, unavailable = [], ['No analytical result was delivered'], [safe_message]
        record = {'tool_contract_version':VERSION,'tool_call_id':call_id,'tool_name':name if name in SCHEMAS else 'rejected_tool',
            'validated_arguments':valid_args,'context_ref':ctx_ref,'scope':scope,'source_pins':pins,'state':state,
            'payload':payload,'payload_sha256':fingerprint(payload),'field_basis':basis,
            'evidence_identifiers':identifiers(payload),'warnings':list(dict.fromkeys(warnings)),
            'unavailable_reasons':list(dict.fromkeys(unavailable)),'limitations':list(dict.fromkeys(limitations)),
            'captured_at':datetime.now(timezone.utc).isoformat()}
        return self.registry.add(record)

    def dispatch(self, name, args, data, ctx):
        scope, extra = data['scope'], {}
        if name=='get_trend_intelligence':
            extra['/payload/dimensions/data_confidence']='diagnostic'
            return copy.deepcopy(data['trend']['dimensions']), extra
        if name=='get_product_fit':
            extra['/payload/supporting_evidence']='observed'
            return self.sources.product(scope),extra
        if name=='list_positive_product_fits':
            topic = self.sources.topic(scope)
            rows = [self.sources.product({**scope,'product_id':p['product_id']}) for p in topic['assessments'] if p['fit_state'] in ('direct_fit','supporting_fit')]
            out=self.page(rows,args,'products')
            out['workflow_request']='Select a positive product explicitly before requesting product-specific creators.'
            extra['/payload/workflow_request']='workflow_request'
            return out,extra
        if name=='get_creator_candidates':
            requirements = {k:args.get(k,v) for k,v in ctx['requirements'].items()}
            if requirements!=ctx['requirements']: raise AssistantError('scope_mismatch','Requirements differ from trusted context')
            rows = self.sources.creators(scope,requirements)
            out = {**self.page([candidate_view(c) for c in rows['candidates']],args,'candidates'),
                   'counts':rows['counts'],'presentation_order':rows['presentation_order']}
            for i in range(len(out['candidates'])): self.candidate_basis(extra,f'/payload/candidates/{i}')
            return out,extra
        if name=='get_creator_candidate_evidence':
            self.candidate_basis(extra,'/payload')
            return candidate_view(self.sources.candidate(scope,ctx['requirements'])),extra
        if name=='get_campaign_context':
            if any(args.get(k,v)!=v for k,v in ctx['requirements'].items()): raise AssistantError('scope_mismatch','Requirement mismatch')
            result = copy.deepcopy(data['campaign'])
            result['evidence']['creator_candidate'] = candidate_view(result['evidence']['creator_candidate'])
            result['workflow_request']='Supply explicit commercial assumptions and confirm them; future reach is not inferred.'
            extra['/payload/workflow_request']='workflow_request'
            self.candidate_basis(extra,'/payload/evidence/creator_candidate')
            return result,extra
        if name=='trace_decision':
            c = self.sources.candidate(scope,ctx['requirements'])
            out = {'trend':data['trend']['dimensions'],'product_fit':self.sources.product(scope),
                   'creator_candidate':candidate_view(c),'campaign':'not_evaluated',
                   'distinction':'Evidence supports scoped candidacy only; endorsement, product use, causal effectiveness and campaign success are not established',
                   'warnings':c['warnings'],'limitations':c['limitations']}
            if 'scenario_result_ref' in args:
                prior = self.registry.get(args['scenario_result_ref'])
                if prior['context_ref']!=args['context_ref'] or prior['tool_name']!='evaluate_campaign_scenario' or prior['state']!='success' or prior['scope']!=scope:
                    raise AssistantError('scope_mismatch','Scenario result is not from this selected context')
                out['campaign'] = prior['payload']
                extra['/payload/campaign/assumptions']='user_assumption'
                extra['/payload/campaign/calculated_outcomes']='derived_scenario'
                extra['/payload/campaign/break_even']='derived_scenario'
                extra['/payload/campaign/sensitivity']='derived_scenario'
            self.candidate_basis(extra,'/payload/creator_candidate')
            return out,extra
        raise AssistantError('unknown_tool','No handler is registered')

    @staticmethod
    def candidate_basis(out,prefix):
        for key in ('review_basis','review_provenance','reviewed_domain','specializations','topic_affinity','profile_support','evidence_sufficiency'):
            out[prefix+'/'+key]='reviewed'
        for key in ('evidence','engagement_evidence'): out[prefix+'/'+key]='observed'

    @staticmethod
    def page(rows,args,key):
        start,limit = args.get('offset',0),args.get('limit',20)
        return {key:rows[start:start+limit],'pagination':{'total':len(rows),'returned':len(rows[start:start+limit]),
                'next_offset':start+limit if start+limit<len(rows) else None,'truncated':start+limit<len(rows)}}

    def export_audit(self):
        self.check()
        records = self.registry.records()
        for record in records:
            if 'confirmation_ref' in record['validated_arguments']: record['validated_arguments']['confirmation_ref']='<redacted capability>'
        return {'label':'Deterministic infrastructure; no AI/model execution','user_query':self.user_query,
                'tools':records,'response':copy.deepcopy(self.response),'conversation_persisted':False,
                'confirmations':[{'capability_sha256':fingerprint(token),'assumptions_sha256':a['hash'],
                    'context_ref':a['context_ref'],'source_pins':a['pins'],'consumed':a['used']}
                    for token,a in self._approvals.items()]}

    def close(self):
        self.closed=True; self.response=None; self.user_query=''
        self._contexts.clear(); self._drafts.clear(); self._approvals.clear(); self.registry.clear(); self.sources.close()
    def __enter__(self): return self
    def __exit__(self,*args): self.close()


class HumanController:
    """Host-only capability, not an HTTP API or a member of the nine tools."""
    def __init__(self,turn,cap): self.turn,self.cap=turn,cap
    def check(self):
        if self.cap is not self.turn._cap: raise AssistantError('untrusted_controller','Controller capability invalid')
        self.turn.check()

    def bind(self,scopes,expected_pins=None,requirements=None):
        self.check(); t=self.turn
        if not isinstance(scopes,list) or not 1<=len(scopes)<=4: raise AssistantError('scope_size','Bind 1-4 explicit scopes')
        if expected_pins is not None and expected_pins!={**PINS,'calculation_version':CALCULATION_VERSION}:
            raise AssistantError('pin_mismatch','Client pins differ from approved versions')
        req={'required_market_evidence':'optional','engagement_requirement':'optional',**(requirements or {})}
        from .assistant_contracts import REQUIREMENTS, obj
        validate(req,obj(REQUIREMENTS))
        rows=[]
        for scope in scopes:
            t.sources.validate_scope(scope)
            trend=t.sources.trend(scope)
            row={'scope':copy.deepcopy(scope),'trend':trend,'pins':{**PINS,'calculation_version':CALCULATION_VERSION,
                'trend_method_version':trend['dimensions']['method_version'],'trend_snapshot_sha256':trend['snapshot_sha256']}}
            if 'product_id' in scope: row['pins']['product_assessment_sha256']=fingerprint(t.sources.product(scope))
            if 'creator_id' in scope:
                row['campaign']=t.sources.campaign(scope,req)
                row['pins']=row['campaign']['context_ref']
            rows.append(row)
        if len({json.dumps(r['scope'],sort_keys=True) for r in rows})!=len(rows): raise AssistantError('duplicate_scope','Scopes must be distinct')
        t._contexts.clear(); t._drafts.clear(); t._approvals.clear()
        t.response=None
        handle=secrets.token_urlsafe(24)
        t._contexts[handle]={'data':rows,'requirements':req}
        return copy.deepcopy({'context_ref':handle,'scopes':scopes,'source_pins':[r['pins'] for r in rows],
                'infrastructure_only':True})

    def prepare_assumptions(self,handle,assumptions):
        self.check(); ctx=self.turn.context(handle)
        if len(ctx['data'])!=1 or 'campaign' not in ctx['data'][0]: raise AssistantError('scope_required','Select one product and creator first')
        campaign=ctx['data'][0]['campaign']
        if not campaign['scenario_eligible']: raise AssistantError('blocked_candidate','Candidate/product cannot enter a scenario')
        a=normalize_assumptions(assumptions)
        record={'assumptions':a,'assumptions_sha256':fingerprint(a),'context_ref':handle,'pins':campaign['context_ref'],
                'units':{'costs':'MYR','population':'explicit people','conversion_rates':'fraction [0,1]',
                         'gross_margin_rate':'fraction [0,1]','aov':'MYR/order','campaign_window':'dates; exclusive end'},
                'state':'draft','manual_required':campaign['evidence']['creator_candidate']['candidate_state']=='manual_review_only'}
        draft=secrets.token_urlsafe(24); self.turn._drafts[draft]=copy.deepcopy(record)
        input_id='i'+str(1+sum(r.get('record_kind')=='user_input' for r in self.turn.registry.records())).zfill(2)
        payload=copy.deepcopy(record)
        self.turn.registry.add({'tool_contract_version':VERSION,'tool_call_id':input_id,'tool_name':'trusted_input',
            'record_kind':'user_input','context_ref':handle,'validated_arguments':{},'scope':ctx['data'][0]['scope'],
            'source_pins':record['pins'], 'state':'draft',
            'payload':payload,'payload_sha256':fingerprint(payload),'field_basis':{'/payload':'user_assumption'},
            'evidence_identifiers':{},'warnings':['Draft user assumptions are not authorization to calculate.'],
            'unavailable_reasons':[],'limitations':['Only the trusted human controller can confirm this draft.']})
        return {'draft_ref':draft,'input_record_id':input_id,**copy.deepcopy(record)}

    def confirm_assumptions(self,draft_ref,displayed_hash,*,approve=False,acknowledge_manual=False,manual_reason=None):
        self.check(); t=self.turn
        draft=t._drafts.get(draft_ref)
        if not draft or approve is not True or draft['assumptions_sha256']!=displayed_hash:
            raise AssistantError('confirmation_required','Explicit approval of the displayed assumptions hash is required')
        t.context(draft['context_ref'])
        if draft['manual_required']:
            ack=draft['assumptions']['manual_candidate_acknowledgement']
            if acknowledge_manual is not True or not isinstance(manual_reason,str) or not manual_reason.strip() or not ack['accepted'] or manual_reason!=ack['reason']:
                raise AssistantError('manual_acknowledgement_required','Manual-only acknowledgement/reason must be explicitly supplied by the human controller')
        token=secrets.token_urlsafe(24)
        t._approvals[token]={'context_ref':draft['context_ref'],'hash':displayed_hash,'pins':copy.deepcopy(draft['pins']),
                            'expires':t.expires,'used':False}
        return {'confirmation_ref':token,'context_pins':copy.deepcopy(draft['pins']),
                'assumptions':copy.deepcopy(draft['assumptions']),'assumptions_sha256':displayed_hash,'state':'confirmed'}
