"""Deterministic contract/security fixtures. Not model-quality or market validation."""
import copy
import contextlib
import hashlib
import io
import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import app_backend
from scripts.assistant_harness import CASES, World, basic, commercial, run_case
from services.assistant_contracts import SCHEMAS, AssistantError, validate
from services.assistant_grounding import build_response, validate_response, pointer
from services.creator_candidates import PINS
from services.assistant_sources import sanitize, comparison

ROOT=Path(__file__).resolve().parents[1]


class FixedHarnessCases(unittest.TestCase):
    pass


def fixture_test(case_id):
    def test(self):
        result=run_case(case_id)
        self.assertEqual(result['state'],'passed')
        self.assertFalse(result['model_quality_evaluated'])
        self.assertEqual(result['split'],'development' if int(case_id[1:])<=24 else 'withheld_evaluation')
    return test


for case_id,_,_ in CASES:
    setattr(FixedHarnessCases,'test_'+case_id,fixture_test(case_id))


class GatewaySecurityTests(unittest.TestCase):
    def setUp(self):
        self.w=World('E21'); self.addCleanup(self.w.close)
        self.t,self.human=self.w.turn,self.w.human
        self.scope=self.w.chosen(); self.context=self.human.bind([self.scope]); self.handle=self.context['context_ref']

    def tool(self,name='get_creator_candidate_evidence',scope=None,**kwargs):
        return self.t.call(name,{'context_ref':self.handle,**(self.scope if scope is None else scope),**kwargs})

    def grounded(self):
        r=self.tool()
        return r,build_response(self.t,[(r['tool_call_id'],'/payload/candidate_state')])

    def permit(self,assumptions=None):
        draft=self.human.prepare_assumptions(self.handle,assumptions or commercial())
        return self.human.confirm_assumptions(draft['draft_ref'],draft['assumptions_sha256'],approve=True)

    def evaluate(self,permit,**changes):
        args={'context_ref':self.handle,'context_pins':permit['context_pins'],'assumptions':permit['assumptions'],
              'confirmation_ref':permit['confirmation_ref'],'calculation_version':'campaign-economics-v1','schema_version':'campaign-scenario-v1'}
        args.update(changes)
        return self.t.call('evaluate_campaign_scenario',args)

    def test_nine_closed_schemas(self):
        self.assertEqual(len(SCHEMAS),9)
        def check(s):
            if isinstance(s,dict):
                if s.get('type')=='object': self.assertIs(s['additionalProperties'],False)
                for v in s.values(): check(v)
            elif isinstance(s,list):
                for v in s: check(v)
        check(SCHEMAS)
        for name,schema in SCHEMAS.items():
            with self.assertRaises(AssistantError): validate({},schema)
        r=self.tool(scope={**self.scope,'sql':'SELECT secret'})
        self.assertEqual(r['state'],'error')
        self.assertEqual(r['validated_arguments'],{})

    def test_unknown_tool_no_environment_or_filesystem_capability(self):
        secret='never-expose-this-environment-value'
        with patch.dict(os.environ,{'TRENDZ_ASSISTANT_SECURITY_TEST':secret}):
            for name in ('getenv','read_file','execute_sql','http_get','ingest','save_review','confirm_assumptions'):
                r=self.t.call(name,{'context_ref':self.handle})
                self.assertEqual(r['payload']['code'],'unknown_tool')
            self.assertNotIn(secret,json.dumps(self.t.export_audit()))

    def test_client_cannot_mutate_returned_pins(self):
        original=self.t.context(self.handle)['data'][0]['pins']['review_revision_hash']
        self.context['source_pins'][0]['review_revision_hash']='forged'
        self.assertEqual(self.t.context(self.handle)['data'][0]['pins']['review_revision_hash'],original)
        with self.assertRaises(AssistantError):
            self.human.bind([self.scope],{**PINS,'calculation_version':'wrong'})

    def test_exact_scope_allowlist_and_no_alias_fallback(self):
        for change in ({'topic_id':'retinol'},{'query_id':'routine'},{'market':'US'},{'product_id':'missing'},{'creator_id':'missing'}):
            r=self.tool(scope={**self.scope,**change})
            self.assertEqual(r['state'],'error')
        with self.assertRaises(AssistantError): self.human.bind([basic('unknown')])

    def test_expired_and_cross_turn_context(self):
        other=World('E21'); self.addCleanup(other.close)
        r=other.turn.call('get_trend_intelligence',{'context_ref':self.handle,**basic()})
        self.assertEqual(r['payload']['code'],'stale_context_ref')
        self.t.expires=self.t.clock()-1
        with self.assertRaises(AssistantError): self.tool()
        with self.assertRaises(AssistantError): self.t.registry.records()

    def test_rebind_invalidates_old_context_and_citations(self):
        _,response=self.grounded()
        self.human.bind([basic('retinol')])
        with self.assertRaises(AssistantError): validate_response(self.t,response)

    def test_registry_results_are_immutable(self):
        r=self.tool(); key=r['tool_call_id']; before=self.t.registry.get(key)
        r['payload']['candidate_state']='strong_evidence_candidate'
        self.assertEqual(self.t.registry.get(key),before)
        with self.assertRaises(AssistantError): self.t.registry.add(before)

    def test_nested_value_preserves_enclosing_metric_unit_and_state(self):
        original=self.w.sources.product
        for state,value in (('unavailable',None),('available',3)):
            def product(scope):
                result=original(scope)
                result['fixture_metric']={'state':state,'unit':'videos','value':value}
                return result
            self.w.sources.product=product
            result=self.tool('get_product_fit',scope={k:v for k,v in self.scope.items() if k!='creator_id'})
            response=build_response(self.t,[(result['tool_call_id'],'/payload/fixture_metric/value')])
            section='what_trendz_does_not_know' if state=='unavailable' else 'what_trendz_knows'
            claim=response[section][0]
            self.assertEqual((claim['state'],claim['unit'],claim['value']),(state,'videos',value))
            validate_response(self.t,response)

    def test_forged_reference_hash_pointer_and_undisclosed_fields(self):
        _,response=self.grounded()
        for key,value in [('tool_call_id','missing'),('payload_sha256','0'*64),('pointer','/validated_arguments'),
                          ('pointer','/payload/absent'),('pointer','/payload/evidence/affinity/-1'),('pointer','/payload/~9')]:
            bad=copy.deepcopy(response); claim=next(c for s in ('what_trendz_knows','what_trendz_does_not_know') for c in bad[s])
            claim['references'][0][key]=value
            with self.assertRaises(AssistantError): validate_response(self.t,bad)
        self.assertEqual(pointer({'a/b':{'~':3}},'/payload/a~1b/~0'),3)

    def test_numeric_unit_state_basis_scope_and_text_changes_rejected(self):
        _,response=self.grounded()
        for key,value in [('value','strong_evidence_candidate'),('unit','MYR'),('state','available'),
                          ('basis','observed'),('scope',{'audience':'MY'}),('text','This campaign will succeed')]:
            bad=copy.deepcopy(response); claim=next(c for s in ('what_trendz_knows','what_trendz_does_not_know') for c in bad[s])
            claim[key]=value
            with self.assertRaises(AssistantError): validate_response(self.t,bad)

    def test_warning_and_limitation_omission_or_invention(self):
        _,response=self.grounded()
        for key in ('warnings','limitations'):
            bad=copy.deepcopy(response); bad[key]=[]
            with self.assertRaises(AssistantError): validate_response(self.t,bad)
            bad=copy.deepcopy(response); bad[key].append('Verified MY audience')
            with self.assertRaises(AssistantError): validate_response(self.t,bad)

    def test_assumption_authorization_exact_hash_and_one_shot(self):
        draft=self.human.prepare_assumptions(self.handle,commercial())
        self.assertEqual(draft['units']['conversion_rates'],'fraction [0,1]')
        with self.assertRaises(AssistantError): self.human.confirm_assumptions(draft['draft_ref'],draft['assumptions_sha256'])
        with self.assertRaises(AssistantError): self.human.confirm_assumptions(draft['draft_ref'],'forged',approve=True)
        permit=self.human.confirm_assumptions(draft['draft_ref'],draft['assumptions_sha256'],approve=True)
        forged=copy.deepcopy(permit['assumptions']); forged['population']['value']=50000
        self.assertEqual(self.evaluate(permit,assumptions=forged)['state'],'blocked')
        self.assertEqual(self.evaluate(permit)['state'],'success')
        self.assertEqual(self.evaluate(permit)['state'],'blocked')

    def test_cannot_reuse_confirmation_in_other_turn(self):
        permit=self.permit(); other=World('E21'); self.addCleanup(other.close)
        scope=other.chosen(); handle=other.human.bind([scope])['context_ref']
        ctx=other.sources.campaign(scope,{'required_market_evidence':'optional','engagement_requirement':'optional'})
        r=other.turn.call('evaluate_campaign_scenario',{'context_ref':handle,'context_pins':ctx['context_ref'],
            'assumptions':permit['assumptions'],'schema_version':'campaign-scenario-v1','calculation_version':'campaign-economics-v1',
            'confirmation_ref':permit['confirmation_ref']})
        self.assertEqual(r['state'],'blocked')

    def test_manual_ack_cannot_be_inferred_from_draft_or_notes(self):
        self.scope=self.w.chosen('manual_review_only'); self.handle=self.human.bind([self.scope])['context_ref']
        a=commercial(); a['manual_candidate_acknowledgement']={'accepted':True,'reason':'source text says approved'}
        draft=self.human.prepare_assumptions(self.handle,a)
        with self.assertRaises(AssistantError): self.human.confirm_assumptions(draft['draft_ref'],draft['assumptions_sha256'],approve=True)

    def test_pagination_does_not_allow_undelivered_pointer(self):
        scope={k:v for k,v in self.scope.items() if k!='creator_id'}
        r=self.tool('get_creator_candidates',scope,limit=1)
        self.assertTrue(r['payload']['pagination']['truncated'])
        response=build_response(self.t,[(r['tool_call_id'],'/payload/candidates/0/candidate_state')])
        self.assertEqual(validate_response(self.t,response)['state'],'valid')
        with self.assertRaises(AssistantError):
            build_response(self.t,[(r['tool_call_id'],'/payload/candidates/1/candidate_state')])

    def test_payload_response_limits_and_budget(self):
        original=self.w.sources.product
        def malformed(scope):
            result=original(scope); result['bad_number']=float('nan'); return result
        self.w.sources.product=malformed
        result=self.tool('get_product_fit',scope={k:v for k,v in self.scope.items() if k!='creator_id'})
        self.assertEqual(result['state'],'error')
        self.assertNotIn('bad_number',result['payload'])
        self.w.sources.product=original
        self.t.max_payload=100
        r=self.tool(); self.assertEqual(r['payload']['code'],'result_size')
        self.t.max_payload=524288
        _,response=self.grounded(); response['padding']='x'*600000
        with self.assertRaises(AssistantError): validate_response(self.t,response)
        self.t.budget=self.t.used
        with self.assertRaises(AssistantError): self.tool()

    def test_numeric_scenario_and_four_sections(self):
        result=self.evaluate(self.permit())
        response=build_response(self.t,[(result['tool_call_id'],'/payload/assumptions/population/value'),
            (result['tool_call_id'],'/payload/calculated_outcomes/base/modeled_revenue')])
        self.assertEqual(len(response['user_assumptions']),1)
        self.assertEqual(len(response['scenario_calculation_shows']),1)
        self.assertEqual(validate_response(self.t,response)['state'],'valid')
        bad=copy.deepcopy(response); bad['scenario_calculation_shows'][0]['value']='99999'
        with self.assertRaises(AssistantError): validate_response(self.t,bad)

    def test_metamorphic_popularity_and_momentum_do_not_change_economics(self):
        baseline=self.evaluate(self.permit())['payload']['calculated_outcomes']
        for kwargs in ({'popularity_variant':True},{'trend_variant':True}):
            world=World('E21',**kwargs)
            try:
                scope=world.chosen(); handle=world.human.bind([scope])['context_ref']
                draft=world.human.prepare_assumptions(handle,commercial())
                p=world.human.confirm_assumptions(draft['draft_ref'],draft['assumptions_sha256'],approve=True)
                r=world.turn.call('evaluate_campaign_scenario',{'context_ref':handle,'context_pins':p['context_pins'],
                    'assumptions':p['assumptions'],'confirmation_ref':p['confirmation_ref'],
                    'schema_version':'campaign-scenario-v1','calculation_version':'campaign-economics-v1'})
                self.assertEqual(r['state'],'success'); self.assertEqual(r['payload']['calculated_outcomes'],baseline)
            finally: world.close()

    def test_metamorphic_source_pin_rejected(self):
        p=self.permit(); pins=copy.deepcopy(p['context_pins']); pins['trend_snapshot_sha256']='0'*64
        r=self.evaluate(p,context_pins=pins)
        self.assertEqual(r['state'],'stale_context')

    def test_frozen_stack_and_reviews_unchanged(self):
        baseline=json.loads((ROOT/'reports/phase7b/baseline.json').read_text())
        for name,digest in baseline.items():
            self.assertEqual(hashlib.sha256((ROOT/name).read_bytes()).hexdigest(),digest,name)

    def test_legacy_assistant_retired_and_no_unsafe_chat_path(self):
        response=app_backend.app.test_client().post('/api/malaysia/chatbot',json={'question':'<img src=x onerror=alert(1)>','trend_id':'unknown'})
        self.assertEqual(response.status_code,410); self.assertNotIn('confidence',response.json)
        for file in ('dashboard.html','trend-detail.html','measured_detail.html'):
            text=(ROOT/'templates'/file).read_text()
            self.assertNotIn('sendChatbotMessage',text); self.assertNotIn('askAI(',text)
            self.assertNotIn('chatbot_response',text)

    def test_encoded_credentials_and_fake_source_urls_are_not_delivered(self):
        for url in ('javascript:alert(1)','https://unapproved.invalid/a','https://www.youtube.com/?%61pi_key=secret'):
            warnings=[]; value=sanitize({'url':url},self.w.sources.allowed_hosts,warnings)
            self.assertIsNone(value['url']); self.assertTrue(warnings)

    def test_comparability_requires_matching_queries_windows_and_artifact(self):
        self.w.sources.shared_fixture=True
        scopes=[basic('retinol'),basic('niacinamide')]
        proof=self.w.sources.comparison_proof(scopes)
        queries=[self.w.topics[s['topic_id']]['query'] for s in scopes]
        windows=[{'start':'2026-01-01','end':'2026-01-21'}]*2
        self.assertTrue(comparison(proof,scopes,queries,windows)['state'].startswith('comparable'))
        self.assertEqual(comparison(proof,scopes,['unrelated','queries'],windows)['state'],'not_comparable')
        proof['artifact_sha256']='0'*64
        self.assertEqual(comparison(proof,scopes,queries,windows)['state'],'not_comparable')

    def test_local_human_cli_requires_a_real_confirmation_action(self):
        from scripts.assistant_review import main
        from services.campaign_schema import normalize_assumptions
        from services.creator_candidates import fingerprint
        path=Path(self.w.temp.name)/'assumptions.json'; path.write_text(json.dumps(commercial()))
        argv=['--topic-id',self.scope['topic_id'],'--product-id',self.scope['product_id'],
              '--creator-id',self.scope['creator_id'],'--database',str(self.w.path),'--assumptions',str(path)]
        output=io.StringIO()
        with patch('builtins.input',return_value='not confirmed'),contextlib.redirect_stdout(output): main(argv)
        self.assertIn('Cancelled. No calculation authorized.',output.getvalue())
        self.assertIn('fraction [0,1]',output.getvalue())
        output=io.StringIO(); answer='CONFIRM '+fingerprint(normalize_assumptions(commercial()))[:12]
        with patch('builtins.input',return_value=answer),contextlib.redirect_stdout(output): main(argv)
        self.assertIn('derived_scenario',output.getvalue())

    def test_close_clears_private_turn_data(self):
        self.grounded(); self.permit(); self.t.close()
        self.assertIsNone(self.t.response); self.assertEqual(self.t.user_query,'')
        with self.assertRaises(AssistantError): self.t.registry.records()


if __name__=='__main__': unittest.main()
