"""Local frozen-input integration using synthetic transport; no model calls.

Portable interface checks live in test_rl1_reference_contracts.py. Real stage
artifacts may already be closed; tests of pre-launch absence use temporary paths.
"""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

PROJECT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(PROJECT/'src'))
BASE=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
HAS_LOCAL_ARTIFACTS = ((BASE/'paired_diagnostic_20261019_v1/paired.py').is_file()
                       and (BASE/'task_reference_preparation_20261021_v1/protocol.json').is_file())
if HAS_LOCAL_ARTIFACTS:
    sys.path.insert(0,str(BASE/'paired_diagnostic_20261019_v1'))
    import paired as p
from metacom_pm.rl1 import task_reference as t, relation_reference as r


def score(item,unknown=False):
    units=p.response_units(item['reply']);sid=next(iter(p.evidence_turns(item['evidence'])))
    return dict(status='uncertain' if unknown else 'scored',q=None if unknown else 3,
        q_rationale=dict(current_need='synthetic mock',response_unit_ids=[units[0]['id']],source_turn_ids=[sid],reason='synthetic'),
        assessments=[dict(response_unit_id=u['id'],relation='non_factual',severity=0,source_turn_ids=[],reason='synthetic') for u in units],
        coverage='synthetic only',uncertainty_reasons=['synthetic unknown'] if unknown else [])


@unittest.skipUnless(HAS_LOCAL_ARTIFACTS, 'requires preserved local engine and task inputs')
class TaskReferenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec=importlib.util.spec_from_file_location('task_entry',PROJECT/'scripts/rl1/116_run_task_reference.py')
        cls.entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(cls.entry)
        cls.pr,cls.items,cls.refs,cls.cards,cls.prompt,cls.payloads,cls.runtime_items=cls.entry.load()

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.calls=[];self.addCleanup(patch.stopall)
        patch('socket.socket.connect',side_effect=AssertionError('network forbidden offline')).start()
        patch('deepseek_access.read_key',side_effect=AssertionError('credentials forbidden offline')).start()
        patch('deepseek_access.management_once',side_effect=AssertionError('account requests forbidden offline')).start()
        self.budget=p.DiagnosticBudget(self.root/'ledger.jsonl',trial='synthetic',study=t.VERSION,
            stage_cap=p.s.nanodollars(2),trial_cap=p.s.nanodollars('3.15'),shared_cap=p.s.nanodollars(20),baseline=0,opening=0)

    def execute(self,change=None,protocol=None,baseline=253):
        owner=self
        class Mock:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append((deepcopy(request),deepcopy(messages)))
                raw=dict(transport='deepseek',model='deepseek-flash',system_fingerprint='synthetic-fingerprint',request_identity=request['request_id'],
                    choices=[dict(message=dict(content=json.dumps(score(owner.runtime_items[request['item_key']])),reasoning_content='NOT_AN_ANSWER'),finish_reason='stop')],
                    usage=dict(prompt_tokens=1000,completion_tokens=1000,completion_tokens_details=dict(reasoning_tokens=700)),
                    total_seconds=1,request_started_unix=1792584000)
                if change:change(request,raw)
                Path(raw_path).write_text('synthetic only')
                return raw
        pr=protocol or self.pr
        return p.run(pr,self.runtime_items,self.root/'run',Mock(),self.budget,mode='mock',global_count=lambda:baseline,
            runtime=t.runtime(pr,self.payloads,self.items,self.refs,self.cards,self.prompt,p,lambda *_:None))

    def test_32_distinct_new_requests_no_training_qualification(self):
        out=self.execute()
        self.assertEqual((out['started'],out['cumulative'],out['technical_delivered']),(32,285,32))
        self.assertEqual(len({x[0]['request_id'] for x in self.calls}),32)
        self.assertFalse(out['reward_eligible']);self.assertEqual(out['natural_updates'],0)

    def test_both_arms_same_policy_relation_original_user_schema(self):
        for k,item in self.items.items():
            a,b=self.payloads[k+'__A'],self.payloads[k+'__B']
            self.assertEqual(a['messages'][1],b['messages'][1]);self.assertEqual(a['schema'],b['schema'])
            self.assertTrue(b['messages'][0]['content'].startswith(a['messages'][0]['content']+t.MARKER))
            self.assertEqual(a['messages'][0]['content'],r.make_payload(item,self.refs[k],'B',self.prompt,p)['messages'][0]['content'])
            self.assertEqual(json.loads(b['messages'][1]['content'])['legal_evidence'],item['evidence'])
            p.api_body(self.pr['config'],b['messages'])

    def test_shared_task_card_identical_for_same_context(self):
        seen={}
        for k,item in self.items.items():
            content=self.payloads[k+'__B']['messages'][0]['content'].split(t.MARKER)[1]
            eid=r.digest(item['evidence'])
            if eid in seen:self.assertEqual(seen[eid],content)
            seen[eid]=content
        self.assertEqual(len(seen),5)

    def test_no_score_or_resource_preference_fields(self):
        for field in ('expected_q','human_preference','resource_winner','candidate_reply','m'):
            item=self.items['dev06B'];card=deepcopy(self.cards[r.digest(item['evidence'])]);card[field]=4
            with self.assertRaises(ValueError):t.validate_card(item,card)

    def test_exact_context_source_role_binding(self):
        item=self.items['dev06B']
        for field,value in (('quote','fabricated'),('speaker','stranger'),('source_id','H999:T000')):
            card=deepcopy(self.cards[r.digest(item['evidence'])]);card['source_facts'][0][field]=value
            with self.assertRaises(ValueError):t.validate_card(item,card)

    def test_task_cannot_self_certify_gold(self):
        item=self.items['dev06B'];card=deepcopy(self.cards[r.digest(item['evidence'])]);card['independent_gold']=True
        with self.assertRaises(ValueError):t.validate_card(item,card)

    def test_whole_payload_tampering_fails(self):
        k='dev06B';item=self.items[k];card=self.cards[r.digest(item['evidence'])]
        for mutation in ('extra','source','card'):
            data=deepcopy(self.payloads[k+'__B'])
            if mutation=='extra':data['messages'].append(dict(role='user',content='human score'))
            elif mutation=='source':data['messages'][1]['content']='{}'
            else:data['messages'][0]['content']+=' extra'
            with self.assertRaises(ValueError):t.validate_payload(item,self.refs[k],card,'B',self.prompt,data,p)

    def test_repetition_ids_unique_identical_inputs_all_mother_endpoints(self):
        self.execute()
        for key in ('dev06B','dev06A','context_02_1000','dev04B'):
            for arm in ('A','B'):
                rows=[x for x in self.calls if x[0]['material_id']==key and x[0]['arm']==arm]
                self.assertEqual(len(rows),2);self.assertEqual(rows[0][1],rows[1][1])
                self.assertNotEqual(rows[0][0]['request_id'],rows[1][0]['request_id'])

    def test_matched_repetition_uses_both_new_endpoints(self):
        out=self.execute()
        for c in out['resource_comparisons']:
            if c['pair_id'] in ('mother_RS','mother_ME'):
                self.assertEqual(c['on_draw'],c['off_draw']);self.assertFalse(c['shared_on'])
            if c['pair_id']=='workplace_RS' and c['off_draw']==2:self.assertTrue(c['shared_on'])
            self.assertIsNone(c['direction_correctness'])

    def test_balanced_arm_order_reversed_repeats(self):
        seq=self.pr['schedule'];pairs=[seq[i:i+2] for i in range(0,32,2)]
        self.assertEqual(sum(x[0]['arm']=='A' for x in pairs),8)
        for k in ('dev06B','dev06A','context_02_1000','dev04B'):
            group=[x for x in pairs if x[0]['material_id']==k]
            self.assertEqual([s['arm'] for s in group[0]],[s['arm'] for s in group[1]][::-1])

    def test_invalid_semantic_mock_does_not_trigger_technical_stop(self):
        out=self.execute();self.assertEqual(out['started'],32);self.assertIsNone(out['stop'])

    def test_unknown_not_zero_or_tie_and_does_not_abort(self):
        def change(req,raw):
            if req['position']==1:raw['choices'][0]['message']['content']=json.dumps(score(self.runtime_items[req['item_key']],True))
        out=self.execute(change);self.assertEqual(out['started'],32);self.assertEqual(out['model_unknown'],1)
        ev=out['slots'][0]['result']['evaluation'];self.assertEqual([ev[k] for k in ('q','m','U')],[None,None,None])
        c=next(x for x in out['resource_comparisons'] if x['pair_id']=='mother_ME' and x['arm']=='A' and x['off_draw']==1)
        self.assertFalse(c['comparable']);self.assertIsNone(c['net_reward'])

    def test_duplicate_key_stops_without_repair(self):
        def change(req,raw):raw['choices'][0]['message']['content']='{"status":"scored","status":"scored"}'
        self.assertEqual(self.execute(change)['started'],1)

    def test_truncation_does_not_use_thinking(self):
        def change(req,raw):raw['choices'][0]['finish_reason']='length'
        out=self.execute(change);self.assertEqual(out['started'],1);self.assertFalse(out['slots'][0]['result']['technical_valid'])

    def test_illegal_citation_stops(self):
        def change(req,raw):
            v=json.loads(raw['choices'][0]['message']['content']);v['q_rationale']['source_turn_ids']=['H999:T000']
            raw['choices'][0]['message']['content']=json.dumps(v)
        self.assertEqual(self.execute(change)['started'],1)

    def test_usage_unknown_holds_full_responsibility(self):
        def change(req,raw):raw['usage']=None
        out=self.execute(change);self.assertEqual(out['started'],1);self.assertEqual(out['result_liability_usd'],'0.786432')

    def test_timeout_counts_started_no_retry(self):
        def change(req,raw):raise TimeoutError('synthetic')
        out=self.execute(change);self.assertEqual(out['started'],1)
        old=r.sha(self.root/'run/STOP.json');self.execute();self.assertEqual(len(self.calls),1);self.assertEqual(r.sha(self.root/'run/STOP.json'),old)

    def test_settled_usage_releases_only_unused_reserve(self):
        self.execute();_,_,reserved,settled=self.budget._totals(self.budget.events())
        self.assertEqual(set(reserved),set(settled));self.assertLess(self.budget.stage_total(reserved,settled),p.RESERVE)

    def test_budget_refuses_before_started(self):
        self.budget.stage_cap=p.s.nanodollars('.78');out=self.execute()
        self.assertEqual(out['started'],0);self.assertEqual(self.calls,[])

    def test_trial_tail_exact_boundary_and_one_nanodollar_over(self):
        for extra in (0,1):
            b=p.DiagnosticBudget(self.root/f'tail{extra}.jsonl',trial='synthetic',study=t.VERSION,
                stage_cap=p.s.nanodollars(2),trial_cap=p.s.nanodollars('3.15'),shared_cap=p.s.nanodollars(20),baseline=0,opening=0)
            old=p.s.nanodollars('1.3451256');b.reserve('old',old,dict(study='old-synthetic'));b.settle('old',old,'synthetic')
            cost=p.s.nanodollars('1.0184424')+extra;b.reserve('settled',cost,dict(study=t.VERSION));b.settle('settled',cost,'synthetic')
            if extra:
                with self.assertRaises(ValueError):b.reserve('next',p.RESERVE,dict(study=t.VERSION))
            else:b.reserve('next',p.RESERVE,dict(study=t.VERSION))

    def test_count_cap_prevents_33rd_request(self):
        out=self.execute(baseline=285);self.assertEqual(out['started'],0)

    def test_reentry_preserves_started_and_results(self):
        self.execute();hashes={str(x):r.sha(x) for x in (self.root/'run').glob('*') if x.is_file()}
        self.execute();self.assertEqual(len(self.calls),32)
        self.assertTrue(all(r.sha(x)==h for x,h in hashes.items()))

    def test_protocol_change_does_not_redispatch(self):
        self.execute();pr=deepcopy(self.pr);pr['identity']='changed'
        out=self.execute(protocol=pr);self.assertEqual(len(self.calls),32);self.assertIsNotNone(out['stop'])

    def test_foreign_version_history_blocks(self):
        base=self.root/'base';run=base/'task_reference_runs/current/live'
        pr=deepcopy(self.pr);pr.update(run_dir=str(run),historical_started_hashes={},baseline_cumulative=66,old_stop_hashes={})
        self.assertEqual(t.historical_guard(pr,base),66)
        path=base/'task_reference_runs/other/live/abc.started.json';path.parent.mkdir(parents=True);path.write_text('{}')
        with self.assertRaises(ValueError):t.historical_guard(pr,base)

    def test_pending_denied_before_creds_management_or_live_mkdir(self):
        pending=self.entry.PREP/'APPROVAL_REQUIRED.json'
        self.assertEqual(r.read(pending)['status'],'PENDING')
        pr=deepcopy(self.pr);live=self.root/'pending_live';pr['run_dir']=str(live)
        self.assertFalse(live.exists())
        loaded=(pr,self.items,self.refs,self.cards,self.prompt,self.payloads,self.runtime_items)
        with patch.object(self.entry,'load',return_value=loaded):
            with self.assertRaises(ValueError):self.entry.launch(pending)
        self.assertFalse(live.exists())

    def test_old_approval_cannot_authorize_new_study(self):
        old=r.read(BASE/'relation_reference_authorization_20261021_v1/APPROVED.json')
        with self.assertRaises(ValueError):t.require_approval(self.pr,old)

    def test_valid_shape_without_actual_record_or_activation_denied(self):
        synthetic=dict(self.pr['approval_required'],status='APPROVED',protocol_identity=self.pr['identity'])
        with self.assertRaises(ValueError):t.require_approval(self.pr,synthetic)
        record=self.root/'synthetic_authorization.txt';record.write_text('synthetic mock, never a real approval')
        synthetic.update(researcher_authorization_record=str(record),researcher_record_sha256=r.sha(record))
        with self.assertRaises(ValueError):t.require_approval(self.pr,synthetic)

    def test_history_and_exposure_not_inflated(self):
        activation=Path(self.pr['activation_file'])
        before=activation.read_bytes() if activation.exists() else None
        self.assertEqual(t.historical_guard(self.pr,BASE),253)
        self.assertEqual(self.pr['statistics']['independent_validation_cases'],0)
        self.assertEqual(self.pr['statistics']['distinct_replies'],12)
        self.assertFalse(r.read(self.entry.PREP/'PROPOSED_AMENDMENT.json')['applied'])
        # Reading a historical proposal must not activate, erase or edit a
        # later activation. Its mere existence is valid after stage execution.
        self.assertEqual(activation.read_bytes() if activation.exists() else None,before)


if __name__=='__main__':unittest.main()
