"""Synthetic bounded audit study; all network/credential/account entry points blocked."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from metacom_pm.rl1 import score_audit_validation as v, paired_dependencies as d
from metacom_pm.rl1.schema import digest
import test_rl1_feedback_workflow as f
import test_rl1_feedback_score_audit as a


class Portable(unittest.TestCase):
    def test_approval_rejected_before_activation_or_credentials(self):
        with patch.object(v.r,'read',side_effect=AssertionError('no activation read')):
            with self.assertRaises(ValueError):v.require_approval({'identity':'x'},{'status':'PENDING'})

    def test_cross_version_new_directory_does_not_hide_a_started_slot(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp);old=base/v.RUN_ROOTS[-1]/'old';old.mkdir(parents=True)
            receipt=old/'slot.started.json';receipt.write_text('{"slot_id":"same"}')
            pr=dict(run_dir=str(base/v.RUN_ROOTS[-1]/'new'),baseline_cumulative=67,
                historical_started_hashes={str(receipt):v.r.sha(receipt)},old_stop_hashes={})
            self.assertEqual(v.historical_guard(pr,base),67)
            alias=base/v.RUN_ROOTS[-1]/'other_version';alias.mkdir();(alias/'slot.started.json').write_bytes(receipt.read_bytes())
            with self.assertRaises(ValueError):v.historical_guard(pr,base)


@unittest.skipUnless(f.HAS_ENGINE,'preserved engine absent')
class Integration(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.p=f.p;self.calls=[]
        item=f.fixture()[0]['V1_OFF'];self.items={k:deepcopy(item) for k,_ in v.ORDER}
        self.scores={k:dict(technical_valid=True,request_identity='historical-'+k,
            evaluation=dict(technical_valid=True,model_unknown=False,U=.75,q=3,m=0,
                value=f.WorkflowIntegrationTests.score(self,item))) for k in self.items}
        self.rubric='SYNTHETIC reference\nQUALITY q (integer):\nMISUSE m:\n0.25 for a localized error'
        self.pr=dict(version=v.VERSION,identity='test-only',schedule=v.schedule(self.items,self.scores),
            baseline_cumulative=302,limits=dict(max_calls=8,cumulative_cap=310),
            config=dict(model='deepseek-flash',thinking='enabled',reasoning_effort='high',top_p=1,
                        temperature=None,response_format='json_object',max_output_tokens=393216,retries=0))
        self.budget=self.p.DiagnosticBudget(self.root/'ledger.jsonl',trial='synthetic',study=v.VERSION,
            stage_cap=self.p.s.nanodollars(1),trial_cap=self.p.s.nanodollars('3.65'),shared_cap=self.p.s.nanodollars(20),baseline=0,opening=0)
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect',side_effect=AssertionError('network forbidden')).start()
        patch('deepseek_access.read_key',side_effect=AssertionError('credentials forbidden')).start()
        patch('deepseek_access.management_once',side_effect=AssertionError('account forbidden')).start()

    def value(self,key,issue=False):
        z=f.WorkflowIntegrationTests.audit(self,self.items[key],False)
        score=self.scores[key]['evaluation']['value']
        def check(path):return dict(status='supported',score_links=[dict(path=path,quote='SYNTHETIC')],criterion='SYNTHETIC',reason='SYNTHETIC')
        z['score_review']=dict(preliminary_score_sha256=digest(score),findings=[],
            checks=dict(quality=check('/q_rationale/reason'),severity=check('/assessments/0/reason'),coverage=check('/coverage')))
        if issue:z['score_review']['checks']['quality']['status']='score_issue'
        return z

    def run_stage(self,change=None,after=None,baseline=302,issue=False):
        owner=self
        class Transport:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request)
                raw=dict(transport='deepseek',model='deepseek-flash',system_fingerprint='MOCK',request_identity=request['request_id'],
                    choices=[dict(message=dict(content=json.dumps(owner.value(request['item_key'],issue)),reasoning_content='NOT FINAL'),finish_reason='stop')],
                    usage=dict(prompt_tokens=1000,completion_tokens=1000,completion_tokens_details=dict(reasoning_tokens=800)))
                if change:change(request,raw)
                Path(raw_path).write_text('MOCK ONLY');return raw
        return d.run(self.p,self.pr,self.items,self.root/'run',Transport(),self.budget,mode='mock',
            runtime=v.runtime(self.pr,self.scores,self.p,self.rubric),global_count=lambda:baseline,after_result=after or (lambda *_:None))

    def test_all_eight_independent_repetitions_and_no_numeric_rescoring(self):
        old=deepcopy(self.scores);out=self.run_stage()
        self.assertEqual((out['started'],out['cumulative']),(8,310));self.assertEqual(out['status'],'CLOSED')
        self.assertEqual(len({x['slot_id'] for x in self.calls}),8)
        self.assertEqual([x['item_key'] for x in self.calls],[x[0] for x in v.ORDER])
        self.assertEqual(self.run_stage(),out);self.assertEqual(len(self.calls),8);self.assertEqual(old,self.scores)
        self.assertFalse(out['reward_eligible']);self.assertEqual(out['repairs_dispatched'],0)

    def test_semantic_error_is_result_not_automatic_phase_stop(self):
        out=self.run_stage(issue=True);self.assertEqual(out['started'],8)
        self.assertTrue(all(x['candidate_routing']['action']=='supplement_candidate' for x in out['slots']))
        self.assertEqual(len(self.calls),8)  # No conditional ninth call.

    def test_full_rubric_and_only_same_reply_score_sent(self):
        slot=self.pr['schedule'][0];messages,schema=v.payload(slot,self.items[slot['item_key']],self.scores,self.p,self.rubric)
        data=json.loads(messages[1]['content']);self.assertEqual(data['rubric_reference']['text'],self.rubric)
        self.assertEqual(data['rubric_reference']['identity'],digest(self.rubric))
        self.assertEqual(data['legal_evidence'],self.items[slot['item_key']]['evidence'])
        self.assertNotIn('expected_q',json.dumps(schema));self.assertNotIn('human_reference',data)
        self.assertTrue(messages[0]['content'].endswith(json.dumps(schema,ensure_ascii=False)))
        with self.assertRaises(ValueError):v.payload(slot,self.items[slot['item_key']],self.scores,self.p,'missing anchors')
        with self.assertRaises(ValueError):v.payload(slot,self.items[slot['item_key']]|{'human_label':0},self.scores,self.p,self.rubric)

    def test_preliminary_score_or_source_tampering_stops_before_send(self):
        self.scores['V3_OFF']['evaluation']['value']['q']=4
        out=self.run_stage();self.assertEqual(out['started'],0);self.assertFalse(self.calls)

    def test_interruption_after_seal_continues_suffix_without_repeating(self):
        def stop(slot,row):
            if slot['position']==3:raise RuntimeError('synthetic interruption')
        with self.assertRaises(RuntimeError):self.run_stage(after=stop)
        self.assertEqual(len(self.calls),3);out=self.run_stage();self.assertEqual(out['started'],8);self.assertEqual(len(self.calls),8)

    def test_technical_failure_and_unfinished_output_stop_without_retry(self):
        out=self.run_stage(change=lambda req,raw:raw['choices'][0].update(finish_reason='length'))
        self.assertEqual(out['started'],1);before=(self.root/'run/STOP.json').read_bytes()
        self.assertEqual(self.run_stage()['started'],1);self.assertEqual(len(self.calls),1)
        self.assertEqual((self.root/'run/STOP.json').read_bytes(),before)

    def test_unknown_usage_keeps_full_responsibility(self):
        out=self.run_stage(change=lambda req,raw:raw.pop('usage'));self.assertEqual(out['started'],1)
        self.assertEqual(out['slots'][0]['result']['financial']['unsettled_reservation_usd'],'0.786432')
        self.assertEqual(self.run_stage()['started'],1)

    def test_reserve_tail_stops_before_next_start(self):
        self.budget.stage_cap=self.p.RESERVE+self.p.s.nanodollars('.001')
        out=self.run_stage();self.assertEqual(out['started'],1)

    def test_global_cap_and_changed_protocol_do_not_reset_count(self):
        out=self.run_stage(baseline=309);self.assertEqual(out['started'],1)
        self.pr['identity']='different-version'
        with self.assertRaises(ValueError):self.run_stage(baseline=309)
        self.assertEqual(len(self.calls),1)

    def test_duplicate_keys_and_bad_source_not_repaired(self):
        def bad(req,raw):raw['choices'][0]['message']['content']='{"check":{},'+raw['choices'][0]['message']['content'][1:]
        self.assertEqual(self.run_stage(change=bad)['started'],1)

    def test_model_unknown_is_missing_and_not_score_zero(self):
        def change(req,raw):
            z=json.loads(raw['choices'][0]['message']['content']);z['check'].update(status='uncertain',uncertainty_reasons=['SYNTHETIC unknown'])
            raw['choices'][0]['message']['content']=json.dumps(z)
        out=self.run_stage(change=change);self.assertEqual(out['started'],8);self.assertEqual(out['model_check_unknown'],8)
        self.assertTrue(all(x['candidate_routing']['proposed_U'] is None for x in out['slots']))


if __name__=='__main__':unittest.main()
