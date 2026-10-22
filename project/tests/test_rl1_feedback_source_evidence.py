"""Offline source_evidence and continuation tests; no credential or network use."""
from copy import deepcopy
from contextlib import nullcontext
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metacom_pm.rl1 import feedback_source_evidence as c, feedback_workflow as w, paired_dependencies as d
from metacom_pm.rl1.schema import digest
import test_rl1_feedback_workflow as fixtures
p=fixtures.p if fixtures.HAS_ENGINE else None


class SourceEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.items,self.rows=fixtures.fixture();self.item=self.items['V1_OFF'];self.calls=[]
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect',side_effect=AssertionError('offline network forbidden')).start()
    def score(self,item):return fixtures.WorkflowIntegrationTests.score(self,item)
    def audit(self,item,flag=False):
        value=fixtures.WorkflowIntegrationTests.audit(self,item,True)
        finding=value['findings'][0];finding['source_evidence']=finding.pop('evidence')
        if not flag:finding['verdict']='no_issue_identified'
        return value
    def raw(self,value):
        return dict(transport='deepseek',model='deepseek-flash',system_fingerprint='SYNTHETIC',
            choices=[dict(message=dict(content=json.dumps(value),reasoning_content='NOT_AN_ANSWER'),finish_reason='stop')],
            usage=dict(prompt_tokens=1000,completion_tokens=1000))
    def test_new_field_strict_and_old_interface_unchanged(self):
        v=self.audit(self.item);self.assertEqual(c.validate_audit(v,self.item,p),v)
        with self.assertRaises(Exception):w.f.validate_audit(v,self.item,p)
        v['findings'][0]['evidence']=v['findings'][0].pop('source_evidence')
        with self.assertRaises(Exception):c.validate_audit(v,self.item,p)
    def test_both_keys_not_tolerated(self):
        v=self.audit(self.item);v['findings'][0]['evidence']=v['findings'][0]['source_evidence']
        self.assertFalse(c.evaluate_audit(self.raw(v),self.item,p)['technical_valid'])
    def test_exact_schema_is_sent_without_changing_sources(self):
        messages,schema=c.audit_payload(self.item,self.score(self.item),p)
        self.assertTrue(messages[0]['content'].endswith(json.dumps(schema,ensure_ascii=False)))
        data=json.loads(messages[1]['content']);self.assertEqual(data['legal_evidence'],self.item['evidence'])
        self.assertEqual(data['reply'],self.item['reply']);p.input_guard(messages)
        self.assertIn('evidence',schema['properties']['check']['properties']['claims']['items']['required'])
    def test_illegal_source_id_and_quote_fail(self):
        for field,value in [('source_id','C:T999'),('quote','not in source')]:
            v=self.audit(self.item);v['findings'][0]['source_evidence'][0][field]=value
            self.assertFalse(c.evaluate_audit(self.raw(v),self.item,p)['technical_valid'])
    def test_duplicate_and_truncation_fail_without_using_thinking(self):
        raw=self.raw(self.audit(self.item));raw['choices'][0]['finish_reason']='length'
        self.assertFalse(c.evaluate_audit(raw,self.item,p)['technical_valid'])
        raw=self.raw(self.audit(self.item));raw['choices'][0]['message']['content']=raw['choices'][0]['message']['content'].replace('{','{"check":{},',1)
        self.assertFalse(c.evaluate_audit(raw,self.item,p)['technical_valid'])
    def prepare(self):
        config=dict(backend='deepseek',model='deepseek-flash',thinking='enabled',reasoning_effort='high',
            top_p=1,temperature=None,response_format='json_object',context_tokens=1048576,max_output_tokens=393216,retries=0)
        oldpr=dict(version=w.VERSION,identity='synthetic-old',schedule=self.rows,contexts=[],config=config,
            limits=dict(max_calls=20,cumulative_cap=305),run_dir=str(self.root/'old'))
        budget=p.DiagnosticBudget(self.root/'ledger.jsonl',trial='synthetic',study=w.VERSION,stage_cap=p.s.nanodollars(2),
            trial_cap=p.s.nanodollars('3.65'),shared_cap=p.s.nanodollars(20),baseline=0,opening=0)
        owner=self
        class Old:
            def send(self,messages,schema,*,request,raw_path):
                item=owner.items[request['item_key']]
                v=fixtures.WorkflowIntegrationTests.audit(owner,item) if request['component']=='audit' else owner.score(item)
                if request['position']==6:v=owner.audit(item)
                raw=owner.raw(v);raw['request_identity']=request['request_id'];Path(raw_path).write_text('SYNTHETIC');return raw
        out=d.run(p,oldpr,self.items,oldpr['run_dir'],Old(),budget,mode='mock',runtime=w.runtime(oldpr,p,'SYNTHETIC'))
        self.assertEqual(out['started'],6);self.assertEqual(out['technical_failed'],1)
        path=self.root/'prior_protocol.json';p.s.save(path,oldpr)
        starts,results=p.replay(oldpr['run_dir'],oldpr)
        self.pr=dict(version=c.VERSION,identity='synthetic-new',schedule=[x for x in self.rows if x['slot_id'] not in starts],
            full_schedule=self.rows,prior_protocol_path=str(path),inherited_started_ids=list(starts),
            inherited_failed_ids=[s for s in results if not results[s]['technical_valid']],
            inherited_receipt_hashes={str(f):p.s.sha(f) for f in Path(oldpr['run_dir']).iterdir() if f.is_file()},
            prior_protocol_identity=oldpr['identity'],contexts=[],config=config,limits=dict(max_calls=14,cumulative_cap=305))
        self.budget=c.budget_class(p)(self.root/'ledger.jsonl',trial='synthetic',study=c.VERSION,stage_cap=p.s.nanodollars(2),
            trial_cap=p.s.nanodollars('3.65'),shared_cap=p.s.nanodollars(20),baseline=0,opening=0)
        return starts,results
    def execute(self,flag=False,change=None,baseline=291):
        owner=self
        class New:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request);item=owner.items[request['item_key']]
                value=owner.audit(item,flag) if request['component']=='audit' else owner.score(item)
                raw=owner.raw(value);raw['request_identity']=request['request_id']
                if change:change(request,raw)
                Path(raw_path).write_text('SYNTHETIC');return raw
        return d.run(p,self.pr,self.items,self.root/'new',New(),self.budget,mode='mock',
            runtime=c.runtime(self.pr,p,'SYNTHETIC'),global_count=lambda:baseline)
    def test_stop_continuation_skips_old6_and_failed_dependency(self):
        starts,results=self.prepare();out=self.execute()
        self.assertEqual(out['started'],16);self.assertEqual(out['new_started'],10)
        self.assertEqual(out['technical_failed'],1);self.assertEqual(out['status'],'CLOSED')
        self.assertFalse(set(starts)&{s['slot_id'] for s in self.calls})
        failed_repair=next(x for x in out['slots'] if x['item_key']=='V2_ON' and x['component']=='repair')
        self.assertEqual(failed_repair['skip']['decision']['reason'],'prior_failed_audit_preserved_no_retry')
        c.inherited(self.pr,p);self.assertEqual(self.execute(),out);self.assertEqual(len(self.calls),10)
    def test_conditional_order_and_total20(self):
        self.prepare();out=self.execute(flag=True)
        self.assertEqual(out['started'],20);self.assertEqual(out['new_started'],14)
        self.assertEqual([s['material_id'] for s in self.calls if s['component']=='repair'],['V2_OFF','V3_OFF','V3_ON','V4_ON'])
        self.assertFalse(out['reward_eligible']);self.assertEqual(out['natural_updates'],0)
    def test_new_technical_failure_stops_no_retry(self):
        self.prepare()
        def change(req,raw):
            if req['component']=='audit':raw['choices'][0]['finish_reason']='length'
        out=self.execute(change=change);self.assertEqual(out['new_started'],2);self.assertTrue(out['stop'])
        self.assertEqual(self.execute()['new_started'],2);self.assertEqual(len(self.calls),2)
    def test_old_cost_and_liability_not_reset(self):
        self.prepare();_,_,reserved,settled=self.budget._totals(self.budget.events())
        self.assertEqual(self.budget.stage_total(reserved,settled),p.s.nanodollars('.009'))
        self.budget.stage_cap=p.RESERVE+p.s.nanodollars('.008')
        out=self.execute();self.assertEqual(out['new_started'],0)
    def test_hard_cap305(self):
        self.prepare();out=self.execute(baseline=304)
        self.assertEqual(out['new_started'],1);self.assertIn('cap',out['stop']['reason'])
    def test_old_stop_tampering_fails_before_dispatch(self):
        self.prepare();(self.root/'old/STOP.json').write_text('{}')
        with self.assertRaises(ValueError):self.execute()
        self.assertFalse(self.calls)
    def test_unknown_usage_keeps_liability(self):
        self.prepare();out=self.execute(change=lambda request,raw:raw.pop('usage'))
        self.assertEqual(out['new_started'],1);self.assertEqual(out['attempt_liability_usd'],'0.786432')

    @unittest.skipUnless(fixtures.HAS_LEGACY_TRANSPORT,'historical private credential/transport adapter')
    def test_launcher_reuses_management_and_stops_replay_before_credentials(self):
        sys.path.insert(0,str(fixtures.BASE/'paired_diagnostic_20261019_v1'))
        import paired, live
        self.prepare();project=Path(__file__).resolve().parents[1]
        spec=importlib.util.spec_from_file_location('continuation_entry_test',project/'scripts/rl1/121_continue_feedback_source_evidence.py')
        entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
        ledger=self.root/'ledger.jsonl';preflight=self.root/'prior_management.json'
        p.s.save(preflight,dict(management_hashes={},available_tariff_equivalent_usd='20',opening_trial_usd='0'))
        self.pr.update(run_dir=str(self.root/'new'),prior_management_preflight=str(preflight),public_price_table_identity='synthetic',
            inherited_fingerprint='SYNTHETIC',financial_baseline=dict(ledger_path=str(ledger),ledger_sha256=p.s.sha(ledger),
            ledger_bytes=ledger.stat().st_size,financial_trial_identity='synthetic'))
        auth=self.root/'SYNTHETIC_NOT_APPROVAL.json';p.s.save(auth,dict(status='TEST_ONLY'))
        owner=self
        class Transport:
            def __init__(self,*_):pass
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request);item=owner.items[request['item_key']]
                value=owner.audit(item) if request['component']=='audit' else owner.score(item)
                raw=owner.raw(value);raw['request_identity']=request['request_id'];Path(raw_path).write_text('SYNTHETIC');return raw
        with (patch.object(entry,'BASE',self.root),patch.object(entry,'load',return_value=(self.pr,self.items,'SYNTHETIC')),
              patch.object(c,'require_approval'),patch.object(c,'historical_guard',return_value=291),
              patch('deepseek_access.read_key',return_value='SYNTHETIC') as keys,
              patch('deepseek_access.credential_scope',side_effect=lambda _:nullcontext()),
              patch('deepseek_access.visible_paid_writers',return_value=[]),
              patch('live.public_service_check') as public,patch('adapters.DeepSeekTransport',Transport)):
            first=entry.launch(auth);second=entry.launch(auth)
            self.assertEqual(first,second);self.assertEqual(first['new_started'],10)
            self.assertEqual(keys.call_count,1);self.assertEqual(public.call_count,1)


if __name__=='__main__':unittest.main()
