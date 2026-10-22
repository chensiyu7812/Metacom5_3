"""Synthetic dependency/financial integration; no live requests or credentials.

The engine integration is skipped on public CPU CI without the preserved private
engine. Portable schedule/decision tests still run there.
"""
from copy import deepcopy
from contextlib import nullcontext
from decimal import Decimal
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1 import feedback_workflow as w, paired_dependencies as d, feedback_prototype as f
from metacom_pm.rl1.schema import digest
BASE=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
HAS_ENGINE=(BASE/'paired_diagnostic_20261019_v1/paired.py').exists()
if HAS_ENGINE:
    sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
    import paired as p


def fixture():
    items={};fixed=[]
    for n in range(1,5):
        for cond in ('OFF','ON') if n%2 else ('ON','OFF'):
            key=f'V{n}_{cond}'
            items[key]=dict(reply=f'Could we discuss option {n}?',evidence=dict(current_date='2026-01-01',
                current_prefix=[dict(id='C:T000',role='seeker',text=f'I plan to talk about option {n} tomorrow.')],legal_past_sessions=[]))
            for component in ('joint','audit'):
                logical=dict(study=f.VERSION,material_id=key,component=component,repetition=1)
                fixed.append(dict(position=len(fixed)+1,slot_id=digest(logical),**logical,dependency=None))
    return items,w.schedule(fixed,items)


class PortableWorkflowTests(unittest.TestCase):
    def test_24_slots_max20_no_repeat_identity_change(self):
        items,rows=fixture()
        self.assertEqual(len(rows),24);self.assertEqual(len({x['slot_id'] for x in rows}),24)
        self.assertEqual([x['component'] for x in rows[:4]],['joint','audit','joint','audit'])
        self.assertEqual(rows,w.schedule([dict((k,v) for k,v in x.items() if k not in ('item_key','reply_identity','evidence_identity')) for x in rows[:16]],items))

    def test_approval_rejected_before_amendment_read(self):
        with patch.object(w.rr,'read',side_effect=AssertionError('no file read')):
            with self.assertRaises(ValueError):w.require_approval({'identity':'x'}, {'status':'PENDING'})

    def test_flags_are_machine_fields_not_q_magnitude(self):
        j=dict(evaluation=dict(model_unknown=False,q=0))
        a=dict(evaluation=dict(value=dict(check=dict(status='checked'),findings=[])))
        self.assertFalse(w.flagged(j,a))
        j['evaluation']['model_unknown']=True;self.assertTrue(w.flagged(j,a))
        j['evaluation']['model_unknown']=False;a['evaluation']['value']['check']['status']='uncertain'
        self.assertTrue(w.flagged(j,a))


@unittest.skipUnless(HAS_ENGINE,'private original engine absent; no downloads')
class WorkflowIntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.items,rows=fixture();self.calls=[]
        self.pr=dict(version=w.VERSION,identity='synthetic-protocol',schedule=rows,
            contexts=[dict(context_id='V'+str(i+1),head=h,resource_tokens=200) for i,h in enumerate(('RS','MP','MS','ME'))],
            limits=dict(max_calls=20,cumulative_cap=305),config=dict(backend='deepseek',model='deepseek-flash',
                thinking='enabled',reasoning_effort='high',top_p=1,temperature=None,response_format='json_object',
                context_tokens=1048576,max_output_tokens=393216,retries=0))
        self.budget=p.DiagnosticBudget(self.root/'ledger.jsonl',trial='synthetic',study=w.VERSION,
            stage_cap=p.s.nanodollars(2),trial_cap=p.s.nanodollars('3.65'),shared_cap=p.s.nanodollars(20),baseline=0,opening=0)
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect',side_effect=AssertionError('network forbidden offline')).start()
        patch('deepseek_access.read_key',side_effect=AssertionError('credentials forbidden offline')).start()
        patch('deepseek_access.management_once',side_effect=AssertionError('account forbidden offline')).start()

    def score(self,item,unknown=False):
        units=p.response_units(item['reply'])
        return dict(status='uncertain' if unknown else 'scored',q=None if unknown else 3,
            q_rationale=dict(current_need='SYNTHETIC',response_unit_ids=[units[0]['id']],source_turn_ids=['C:T000'],reason='SYNTHETIC'),
            assessments=[dict(response_unit_id=u['id'],relation='non_factual',severity=0,source_turn_ids=[],reason='SYNTHETIC') for u in units],
            coverage='SYNTHETIC',uncertainty_reasons=['SYNTHETIC'] if unknown else [])

    def audit(self,item,flag=False):
        u=p.response_units(item['reply'])[0]
        return dict(check=dict(status='checked',claims=[],coverage='SYNTHETIC',uncertainty_reasons=[]),
            findings=[dict(response_unit_id=u['id'],response_quote=u['text'],dimension='interpretation',
                verdict='unresolved',readings=['SYNTHETIC'],evidence=[dict(source_id='C:T000',quote=item['evidence']['current_prefix'][0]['text'])],
                criterion='SYNTHETIC',consequence='SYNTHETIC',reason='SYNTHETIC')] if flag else [],coverage_limitations='SYNTHETIC')

    def execute(self,flag=False,change=None,after=None,mode='mock',baseline=285):
        owner=self
        class Mock:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(deepcopy(request));item=owner.items[request['item_key']]
                value=owner.audit(item,flag) if request['component']=='audit' else owner.score(item)
                raw=dict(transport='deepseek',model='deepseek-flash',system_fingerprint='SYNTHETIC',request_identity=request['request_id'],
                    choices=[dict(message=dict(content=json.dumps(value),reasoning_content='NEVER_AN_ANSWER'),finish_reason='stop')],
                    usage=dict(prompt_tokens=1000,completion_tokens=1000,completion_tokens_details=dict(reasoning_tokens=700)))
                if change:change(request,raw)
                Path(raw_path).write_text('SYNTHETIC')
                return raw
        return d.run(p,self.pr,self.items,self.root/'run',Mock(),self.budget,mode=mode,
            runtime=w.runtime(self.pr,p,'SYNTHETIC FIXED COMMON PROMPT'),global_count=lambda:baseline,
            after_result=after or (lambda *_:None))

    def test_no_flags_16_calls_8_explicit_skips(self):
        out=self.execute();self.assertEqual((out['started'],out['skipped'],out['cumulative']),(16,8,301))
        self.assertEqual(out['status'],'CLOSED');self.assertEqual(len(out['slots']),24)
        self.assertTrue(all(x['final_usable_U'] is None and not x['reward_eligible'] for x in out['endpoints']))
        self.assertEqual(out['natural_updates'],0);self.assertEqual(out['human_reviews'],0)
        self.assertEqual(len(out['paired']),4)
        for pair in out['paired']:
            self.assertAlmostEqual(pair['initial_net'],-200/40960)
            self.assertEqual(pair['numerical_change'],0);self.assertIsNone(pair['final_usable_net'])

    def test_all_flags_first4_only_in_fixed_order(self):
        out=self.execute(flag=True);self.assertEqual((out['started'],out['skipped'],out['cumulative']),(20,4,305))
        self.assertEqual([c['item_key'] for c in self.calls[16:]],['V1_OFF','V1_ON','V2_ON','V2_OFF'])
        self.assertEqual(sum(e['state']=='supplement_proposal_needs_local_review' for e in out['endpoints']),4)
        self.assertEqual(out['known_output_tokens_including_thinking'],20000)  # Not +14000 thinking.

    def test_same_endpoint_full_source_and_outputs_only(self):
        self.execute(flag=True)
        for path in (self.root/'run').glob('*.request.json'):
            req=p.s.read(path);sid=path.name.removesuffix('.request.json');slot=next(s for s in self.pr['schedule'] if s['slot_id']==sid)
            data=json.loads(req['messages'][1]['content']);self.assertEqual(data['legal_evidence'],self.items[slot['item_key']]['evidence'])
            if slot['component']!='joint':
                source=w.find(self.pr,slot['item_key'],'joint')['slot_id']
                self.assertEqual(data['preliminary_score'],p.s.read(self.root/'run'/(source+'.result.json'))['evaluation']['value'])
            self.assertFalse({'human_answers','expected_scores','reviewer_notes'}&set(data))

    def test_unknown_joint_can_be_audited_not_zero(self):
        def change(req,raw):
            if req['component']=='joint' and req['item_key']=='V1_OFF':raw['choices'][0]['message']['content']=json.dumps(self.score(self.items['V1_OFF'],True))
        out=self.execute(change=change);self.assertEqual(out['started'],17);self.assertEqual(out['model_unknown'],1)
        self.assertIsNone(out['endpoints'][0]['initial']['U']);self.assertFalse(out['stop'])

    def test_audit_uncertain_separate_from_score_unknown(self):
        def change(req,raw):
            if req['component']=='audit':
                v=json.loads(raw['choices'][0]['message']['content']);v['check'].update(status='uncertain',uncertainty_reasons=['SYNTHETIC'])
                raw['choices'][0]['message']['content']=json.dumps(v)
        out=self.execute(change=change);self.assertEqual(out['audit_relation_uncertain'],8);self.assertEqual(out['model_unknown'],0)
        self.assertEqual(out['started'],20)

    def test_semantic_error_finding_is_not_technical_stop(self):
        def change(req,raw):
            if req['component']=='audit':
                v=json.loads(raw['choices'][0]['message']['content']);v['findings'][0]['verdict']='identified_error'
                raw['choices'][0]['message']['content']=json.dumps(v)
        out=self.execute(flag=True,change=change);self.assertEqual(out['started'],20);self.assertFalse(out['stop'])

    def test_duplicate_key_stops_and_counts_once(self):
        def change(req,raw):
            c=raw['choices'][0]['message'];c['content']=c['content'][:-1]+',"status":"scored"}'
        out=self.execute(change=change);self.assertEqual((out['started'],out['technical_failed']),(1,1))
        self.assertEqual(self.execute()['started'],1);self.assertEqual(len(self.calls),1)

    def test_truncated_output_never_uses_thinking(self):
        def change(req,raw):raw['choices'][0]['finish_reason']='length'
        out=self.execute(change=change);self.assertEqual(out['started'],1);self.assertTrue(out['stop'])

    def test_illegal_audit_evidence_stops_before_supplement(self):
        def change(req,raw):
            if req['component']=='audit':
                v=json.loads(raw['choices'][0]['message']['content']);v['findings'][0]['evidence'][0]['quote']='NOT_IN_SOURCE'
                raw['choices'][0]['message']['content']=json.dumps(v)
        out=self.execute(flag=True,change=change);self.assertEqual(out['started'],2);self.assertEqual(out['technical_failed'],1)

    def test_unknown_usage_retains_full_reserve_no_retry(self):
        out=self.execute(change=lambda req,raw:raw.pop('usage'))
        self.assertEqual(out['attempt_liability_usd'],'0.786432');self.assertEqual(out['accounted_usd'],'0')
        self.assertEqual(out['usage_incomplete_attempts'],1);self.assertEqual(self.execute()['started'],1)

    def test_service_drift_retains_reserve(self):
        out=self.execute(change=lambda req,raw:raw.update(model='other-service'))
        self.assertEqual(out['started'],1);self.assertEqual(out['attempt_liability_usd'],'0.786432')

    def test_fingerprint_drift_stops_second_request(self):
        def change(req,raw):
            if req['component']=='audit':raw['system_fingerprint']='changed'
        out=self.execute(change=change);self.assertEqual(out['started'],2);self.assertEqual(out['attempt_liability_usd'],'0.786432')

    def test_tail_budget_stops_before_next_call(self):
        self.budget.stage_cap=p.s.nanodollars('.787')
        out=self.execute();self.assertEqual(out['started'],1);self.assertIn('budget reservation',out['stop']['reason'])
        self.assertEqual(len(self.budget.events()),2)

    def test_actual_overreserve_is_recorded_then_stops(self):
        def change(req,raw):raw['usage']['completion_tokens']=1000000
        out=self.execute(change=change);self.assertEqual(out['started'],1)
        self.assertEqual(out['accounted_usd'],'1.2003');self.assertEqual(Decimal(out['attempt_liability_usd']),0)
        self.assertIn('exceeds reserved',out['stop']['reason'])

    def test_sealed_boundary_resume_no_duplicate(self):
        def interrupt(slot,row):
            if slot['position']==3:raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.execute(flag=True,after=interrupt)
        before={str(x):p.s.sha(x) for x in (self.root/'run').glob('*') if x.is_file() and x.name!='.study.lock'}
        out=self.execute(flag=True);self.assertEqual(out['started'],20);self.assertEqual(len(self.calls),20)
        self.assertEqual(len({c['request_id'] for c in self.calls}),20)
        for path,h in before.items():self.assertEqual(p.s.sha(path),h)

    def test_unresolved_started_is_never_reissued(self):
        def fail(req,raw):raise KeyboardInterrupt()
        with self.assertRaises(KeyboardInterrupt):self.execute(change=fail)
        out=self.execute();self.assertEqual(out['started'],1);self.assertEqual(len(self.calls),1)
        self.assertIn('unresolved',out['stop']['reason']);self.assertEqual(out['attempt_liability_usd'],'0.786432')

    def test_orphan_reservation_preserved(self):
        sid=self.pr['schedule'][0]['slot_id'];self.budget.reserve(sid,p.RESERVE,dict(study=w.VERSION))
        out=self.execute();self.assertEqual(out['started'],0);self.assertIn('orphan reservation',out['stop']['reason'])
        self.assertEqual(len(self.budget.events()),1)

    def test_crossversion_cannot_dispatch_again(self):
        self.execute();self.pr['identity']='another-version'
        with self.assertRaises(ValueError):self.execute()
        self.assertEqual(len(self.calls),16)

    def test_sealed_dependency_tampering_rejected(self):
        self.execute();path=next((self.root/'run').glob('*.result.json'))
        value=p.s.read(path);value['elapsed_seconds']=77;path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.execute()

    def test_skip_tampering_rejected_even_after_close(self):
        self.execute();path=next((self.root/'run').glob('*.skip.json'))
        value=p.s.read(path);value['decision']['reason']='tampered';path.write_text(json.dumps(value))
        with self.assertRaises(ValueError):self.execute()

    def test_closed_replay_does_not_change_count_or_cost(self):
        first=self.execute();ledger=self.budget.path.read_bytes();second=self.execute()
        self.assertEqual(first,second);self.assertEqual(ledger,self.budget.path.read_bytes());self.assertEqual(len(self.calls),16)

    def test_cumulative_hard_cap(self):
        out=self.execute(baseline=304);self.assertEqual(out['started'],1);self.assertIn('hard cap',out['stop']['reason'])

    def test_live_without_approval_does_not_create_run(self):
        with self.assertRaises(ValueError):self.execute(mode='live')
        self.assertFalse((self.root/'run').exists());self.assertFalse(self.calls)

    def test_full_input_overflow_is_not_truncated(self):
        key=self.pr['schedule'][0]['item_key'];self.items[key]['reply']='word '*150000
        out=self.execute();self.assertEqual(out['started'],0);self.assertIn('input boundary',out['stop']['reason'])

    def test_launch_preflight_once_clean_resume_and_closed_without_key(self):
        # Synthetic authorization seam: never write APPROVED or activate a contract.
        spec=importlib.util.spec_from_file_location('feedback_entry_mock',PROJECT/'scripts/rl1/119_run_feedback_validation.py')
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        base=self.root/'synthetic_base';base.mkdir();ledger=base/'ledger.jsonl';ledger.write_bytes(b'')
        pr=deepcopy(self.pr);pr.update(run_dir=str(base/'feedback_validation_runs/fixture/live'),public_price_table_identity='synthetic-table',
            financial_baseline=dict(ledger_path=str(ledger),ledger_sha256=p.s.sha(ledger),ledger_bytes=0,
                financial_trial_identity='synthetic',trial_accounted_usd='0'))
        auth=base/'SYNTHETIC_SCOPE_NOT_APPROVAL.json';auth.write_text('{"status":"SYNTHETIC_TEST_ONLY"}')
        managed=[];requests=[];owner=self
        def management(out,name,key):
            managed.append(name)
            body=dict(data=[dict(id='deepseek-flash',name='DeepSeek-V4.1-Flash-1017')]) if name=='models' else dict(
                is_available=True,balance_infos=[dict(currency='USD',total_balance='20')])
            value=dict(status=200,body=body);p.s.save(out/(name.replace('/','_')+'.json'),value);return value
        def public(out,identity):p.s.save(out/'public_service_check.json',dict(identity=identity,synthetic=True))
        class Transport:
            def send(self,messages,schema,*,request,raw_path):
                requests.append(request);item=owner.items[request['item_key']]
                v=owner.audit(item) if request['component']=='audit' else owner.score(item)
                Path(raw_path).write_text('SYNTHETIC')
                return dict(transport='deepseek',model='deepseek-flash',system_fingerprint='SYNTHETIC',request_identity=request['request_id'],
                    choices=[dict(message=dict(content=json.dumps(v)),finish_reason='stop')],usage=dict(prompt_tokens=1000,completion_tokens=1000))
        real_run=d.run;interrupt_once=[True]
        def interrupted(*args,**kwargs):
            def after(slot,row):
                if interrupt_once[0] and slot['position']==3:
                    interrupt_once[0]=False;raise KeyboardInterrupt()
            return real_run(*args,**kwargs,after_result=after)
        with (patch.object(entry,'BASE',base),patch.object(entry,'load',return_value=(pr,self.items,'SYNTHETIC')),
             patch.object(entry,'engine',return_value=p),patch.object(w,'historical_guard',return_value=285),
             patch.object(w,'require_approval',return_value=None),patch.object(w,'RUN_ROOTS',('live_runs','feedback_validation_runs')),
             patch('deepseek_access.read_key',return_value='SYNTHETIC_NON_SECRET') as key,
             patch('deepseek_access.credential_scope',side_effect=lambda _:nullcontext()),
             patch('deepseek_access.management_once',side_effect=management),patch('deepseek_access.visible_paid_writers',return_value=[]),
             patch('live.public_service_check',side_effect=public),patch('adapters.DeepSeekTransport',return_value=Transport()),
             patch.object(d,'run',side_effect=interrupted)):
            with self.assertRaises(KeyboardInterrupt):entry.launch(auth)
            result=entry.launch(auth);self.assertEqual(result['started'],16)
            self.assertEqual(entry.launch(auth)['started'],16)
            self.assertEqual(key.call_count,2)
        self.assertEqual(managed,['models','user/balance']);self.assertEqual(len(requests),16)
        self.assertEqual(len({x['request_id'] for x in requests}),16)


if __name__=='__main__':unittest.main()
