"""Offline delivery, unchanged acceptance, and same-experiment ledger tests."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metacom_pm.rl1 import strict_audit_delivery as t, score_audit_validation as v, paired_dependencies as d
from metacom_pm.rl1.schema import digest
import test_rl1_score_audit_validation as fixtures


class Portable(unittest.TestCase):
    def test_schema_projection_preserves_local_constraints(self):
        schema=dict(type='object',properties=dict(name=dict(type='string',minLength=1),
            ids=dict(type='array',minItems=1,items=dict(enum=['x','y'])),identity=dict(const='abc')),
            required=['name','ids','identity'],additionalProperties=False)
        old=deepcopy(schema);projected,changes=t.server_schema(schema)
        self.assertEqual(schema,old);self.assertNotIn('minLength',projected['properties']['name'])
        self.assertEqual(projected['properties']['identity'],dict(enum=['abc'],type='string'))
        self.assertEqual(len(changes),3)

    def test_unapproved_fails_before_activation(self):
        with patch.object(t.r,'read',side_effect=AssertionError('no filesystem authorization read')):
            with self.assertRaises(ValueError):t.require_approval({'identity':'x'},{'status':'PENDING'})

    def test_original_slot_identity_and_scheduled_repeat_kept(self):
        old=[dict(slot_id=str(i),repetition=1 if i<6 else 2) for i in range(8)]
        self.assertEqual(t.remaining_schedule(old,{'0':{},'1':{}}),old[2:])
        with self.assertRaises(ValueError):t.remaining_schedule(old,{'unknown':{}})

    def test_stream_fragments_unchanged_usage_and_thinking_separate(self):
        c=t.Collector('req')
        for delta,finish,usage in [({'reasoning_content':'NOT ANSWER'},None,None),
            ({'tool_calls':[{'index':0,'id':'call1','type':'function','function':{'name':t.TOOL,'arguments':'{"a":'}}]},None,None),
            ({'tool_calls':[{'index':0,'function':{'arguments':'1}'}}]},None,None),
            ({},'tool_calls',{'prompt_tokens':10,'completion_tokens':20})]:
            c.feed(('data: '+json.dumps(dict(id='id1',model='deepseek-flash',system_fingerprint='fixed',
                choices=[dict(index=0,delta=delta,finish_reason=finish)],usage=usage))).encode())
        c.feed(b'data: [DONE]');raw=c.complete()
        self.assertEqual(raw['choices'][0]['message']['tool_calls'][0]['function']['arguments'],'{"a":1}')
        self.assertEqual(raw['usage']['completion_tokens'],20)
        self.assertEqual(raw['choices'][0]['message']['content'],'')
        self.assertEqual(raw['choices'][0]['message']['reasoning_content'],'NOT ANSWER')

    def test_unfinished_stream_and_identity_drift_rejected(self):
        c=t.Collector('req');c.feed(b'data: {"id":"one","choices":[]}')
        with self.assertRaises(ValueError):c.complete()
        with self.assertRaises(ValueError):c.feed(b'data: {"id":"two","choices":[]}')


class Integration(unittest.TestCase):
    def setUp(self):
        fixtures.Integration.setUp(self)
        self.value=lambda key,issue=False:fixtures.Integration.value(self,key,issue)
        original=self.pr['schedule'];self.pr.update(version=t.VERSION,baseline_cumulative=304,
            limits=dict(max_calls=6,cumulative_cap=310),schedule=t.remaining_schedule(original,{x['slot_id']:{} for x in original[:2]}))
        self.pr['config']['timeout_seconds']=900
        self.proxy=t.engine_proxy(self.p,self.pr,self.items,self.scores,self.rubric)
        self.budget=t.budget_class(self.p)(self.root/'same_stage.jsonl',trial='synthetic',study=t.VERSION,
            stage_cap=self.p.s.nanodollars(1),trial_cap=self.p.s.nanodollars('3.65'),shared_cap=self.p.s.nanodollars(20),baseline=0,opening=0)
        # Preserve cost already spent by the original two requests.
        old=self.p.DiagnosticBudget(self.root/'same_stage.jsonl',trial='synthetic',study=v.VERSION,
            stage_cap=self.p.s.nanodollars(1),trial_cap=self.p.s.nanodollars('3.65'),shared_cap=self.p.s.nanodollars(20),baseline=0,opening=0)
        old.reserve('old-two',self.p.RESERVE,dict(study=v.VERSION));old.settle('old-two',self.p.s.nanodollars('.0548997'),'MOCK historic sum')

    def raw(self,key):
        return dict(transport='deepseek',delivery=t.DELIVERY,model='deepseek-flash',system_fingerprint='MOCK',
            choices=[dict(finish_reason='tool_calls',message=dict(content='',reasoning_content='DO NOT PARSE',
                tool_calls=[dict(id='call1',type='function',function=dict(name=t.TOOL,arguments=json.dumps(self.value(key))))]))],
            usage=dict(prompt_tokens=1000,completion_tokens=1000,completion_tokens_details=dict(reasoning_tokens=800)))

    def execute(self,change=None,baseline=304,after=lambda *_:None):
        owner=self
        class Mock:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request);raw=owner.raw(request['item_key']);raw['request_identity']=request['request_id']
                if change:change(raw)
                Path(raw_path).write_text('MOCK');return raw
        return d.run(self.proxy,self.pr,self.items,self.root/'run',Mock(),self.budget,mode='mock',
            runtime=t.runtime(self.pr,self.items,self.scores,self.p,self.rubric,self.proxy),
            global_count=lambda:baseline,after_result=after)

    def test_six_remaining_only_no_duplicate_and_original_stop_untouched(self):
        (self.root/'OLD_STOP.json').write_text('preserved');old=(self.root/'OLD_STOP.json').read_bytes()
        out=self.execute();self.assertEqual((out['started'],out['cumulative']),(6,310))
        self.assertEqual([x['position'] for x in self.calls],[3,4,5,6,7,8]);self.assertEqual(self.execute(),out)
        self.assertEqual(len(self.calls),6);self.assertEqual((self.root/'OLD_STOP.json').read_bytes(),old)
        self.assertEqual(out['repairs_dispatched'],0);self.assertFalse(out['reward_eligible'])

    def test_high_auto_strict_only_and_full_original_data(self):
        slot=self.pr['schedule'][0];item=self.items[slot['item_key']]
        msgs,schema=t.payload(slot,item,self.scores,self.p,self.rubric)
        oldmsgs,_=v.payload(slot,item,self.scores,self.p,self.rubric)
        self.assertEqual(msgs[1],oldmsgs[1]);self.assertEqual(msgs[0]['content'],oldmsgs[0]['content']+t.INSTRUCTION)
        body=self.proxy.api_body(self.pr['config'],msgs)
        self.assertEqual(body['thinking'],{'type':'enabled'});self.assertEqual(body['reasoning_effort'],'high')
        self.assertEqual(body['tool_choice'],'auto');self.assertTrue(body['tools'][0]['function']['strict'])
        self.assertNotIn('response_format',body);self.assertEqual(body['max_tokens'],393216)
        self.assertIn('serialized_wire_utf8_bytes',self.proxy.input_guard(msgs))

    def test_bare_content_wrong_tool_multiple_or_mixed_output_never_fallback(self):
        key=self.pr['schedule'][0]['item_key'];item=self.items[key];score=self.scores[key]['evaluation']['value']
        changes=[lambda x:x['choices'][0].update(finish_reason='stop'),
            lambda x:x['choices'][0]['message'].update(content='explanation'),
            lambda x:x['choices'][0]['message']['tool_calls'].append(deepcopy(x['choices'][0]['message']['tool_calls'][0])),
            lambda x:x['choices'][0]['message']['tool_calls'][0]['function'].update(name='other'),
            lambda x:x['choices'][0]['message'].update(tool_calls=[])]
        for change in changes:
            raw=self.raw(key);change(raw);ev=t.evaluate(raw,item,score,self.p)
            self.assertFalse(ev['technical_valid']);self.assertIsNone(ev['value'])

    def test_extra_brace_duplicate_key_truncated_never_repaired(self):
        key=self.pr['schedule'][0]['item_key'];item=self.items[key];score=self.scores[key]['evaluation']['value']
        for edit in (lambda s:s+'}',lambda s:'{"check":{},'+s[1:],lambda s:s[:-1]):
            raw=self.raw(key);f=raw['choices'][0]['message']['tool_calls'][0]['function'];f['arguments']=edit(f['arguments'])
            before=deepcopy(raw);self.assertFalse(t.evaluate(raw,item,score,self.p)['technical_valid']);self.assertEqual(raw,before)

    def test_local_minimum_constraints_and_source_score_links_not_relaxed(self):
        key=self.pr['schedule'][0]['item_key'];item=self.items[key];score=self.scores[key]['evaluation']['value']
        edits=[lambda x:x.update(coverage_limitations=''),
            lambda x:x['score_review']['checks']['quality'].update(score_links=[]),
            lambda x:x['score_review']['checks']['quality']['score_links'][0].update(quote='forged'),
            lambda x:x['check']['claims'].append(dict(claim_id='C001',response_unit_id='R001',response_quote=item['reply'],
                claim_type='assertion',subject='synthetic',time='now',action_stage='attempted',relation='supported',
                evidence=[dict(source_id='C:T000',quote='NOT IN SOURCE')],reason='test'))]
        for edit in edits:
            raw=self.raw(key);value=self.value(key);edit(value);raw['choices'][0]['message']['tool_calls'][0]['function']['arguments']=json.dumps(value)
            self.assertFalse(t.evaluate(raw,item,score,self.p)['technical_valid'])

    def test_technical_stop_no_retry_and_known_usage_settled(self):
        out=self.execute(lambda raw:raw['choices'][0].update(finish_reason='length'))
        self.assertEqual(out['started'],1);self.assertEqual(out['status'],'STOPPED');self.assertEqual(self.execute()['started'],1)
        self.assertEqual(out['slots'][0]['result']['financial']['unsettled_reservation_usd'],'0')

    def test_unknown_usage_retains_full_liability(self):
        out=self.execute(lambda raw:raw.pop('usage'));self.assertEqual(out['started'],1)
        self.assertEqual(out['slots'][0]['result']['financial']['unsettled_reservation_usd'],'0.786432')

    def test_old_spend_not_reset_and_tail_budget_prevents_next_call(self):
        total,trial,reserved,settled=self.budget._totals(self.budget.events())
        self.assertEqual(self.budget.stage_total(reserved,settled),self.p.s.nanodollars('.0548997'))
        self.budget.stage_cap=self.p.RESERVE+self.p.s.nanodollars('.055')
        out=self.execute();self.assertEqual(out['started'],1)

    def test_hard_310(self):
        self.assertEqual(self.execute(baseline=309)['started'],1)

    def test_resume_after_seal_without_repeating(self):
        def halt(slot,row):
            if slot['position']==4:raise RuntimeError('MOCK interruption after seal')
        with self.assertRaises(RuntimeError):self.execute(after=halt)
        self.assertEqual(len(self.calls),2)
        self.assertEqual(self.execute()['started'],6);self.assertEqual(len(self.calls),6)

    def test_mock_http_single_request_beta_no_proxy_no_function_execution(self):
        import urllib.request
        key=self.pr['schedule'][0]['item_key'];slot=self.pr['schedule'][0]
        args=json.dumps(self.value(key));events=[]
        for delta,finish,usage in [({'reasoning_content':'SYNTHETIC'},None,None),
            ({'tool_calls':[dict(index=0,id='call1',type='function',function=dict(name=t.TOOL,arguments=args))]},None,None),
            ({},'tool_calls',dict(prompt_tokens=1000,completion_tokens=1000))]:
            events.append(('data: '+json.dumps(dict(id='MOCK',model='deepseek-flash',system_fingerprint='MOCK',
                choices=[dict(index=0,delta=delta,finish_reason=finish)],usage=usage))+'\n\n').encode())
        events.append(b'data: [DONE]\n\n')
        class Response:
            headers={'Date':'MOCK'}
            def __enter__(self):return self
            def __exit__(self,*_):return None
            def __iter__(self):return iter(events)
        with patch.dict(t.os.environ,{'DEEPSEEK_API_KEY':'SYNTHETIC-NOT-A-CREDENTIAL'}),patch.object(urllib.request,'build_opener') as build:
            build.return_value.open.return_value=Response()
            msgs,schema=t.payload(slot,self.items[key],self.scores,self.p,self.rubric)
            raw=t.Transport(self.pr['config'],self.proxy).send(msgs,schema,
                request={'request_id':'MOCK'},raw_path=self.root/'http.sse')
            self.assertEqual(build.return_value.open.call_count,1)
            req=build.return_value.open.call_args.args[0];self.assertEqual(req.full_url,t.ENDPOINT)
            self.assertEqual(build.call_args.args[0].proxies,{})
            self.assertEqual(raw['choices'][0]['message']['tool_calls'][0]['function']['arguments'],args)
            self.assertNotIn(b'SYNTHETIC-NOT-A-CREDENTIAL',(self.root/'http.sse').read_bytes())

    def test_unknown_and_score_issue_are_records_not_scalar_zero_or_extra_call(self):
        def change(raw):
            fn=raw['choices'][0]['message']['tool_calls'][0]['function'];value=json.loads(fn['arguments'])
            value['check'].update(status='uncertain',uncertainty_reasons=['SYNTHETIC']);fn['arguments']=json.dumps(value)
        out=self.execute(change);self.assertEqual(out['started'],6);self.assertEqual(out['model_check_unknown'],6)
        self.assertTrue(all(x['candidate_routing']['proposed_U'] is None for x in out['slots']))


if __name__=='__main__':unittest.main()
