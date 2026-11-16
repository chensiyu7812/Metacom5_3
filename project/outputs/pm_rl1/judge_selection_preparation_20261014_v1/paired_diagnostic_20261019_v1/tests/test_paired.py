"""Synthetic transport outputs only; never human/semantic validation."""
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import paired as p
from paired import s


def check_value(item,unknown=False):
    u=p.response_units(item['reply'])[0]
    return dict(status='uncertain' if unknown else 'checked',claims=[dict(claim_id='C001',
        response_unit_id=u['id'],response_quote=u['text'],claim_type='tentative',
        subject='synthetic possibly wrong actor',time='unknown',action_stage='unknown',
        relation='uncertain' if unknown else 'non_factual',evidence=[],reason='mock only')],
        coverage='mock only',uncertainty_reasons=['mock ambiguity'] if unknown else [])


def score_value(item,unknown=False):
    units=p.response_units(item['reply']);ids=list(p.evidence_turns(item['evidence']))
    return dict(status='uncertain' if unknown else 'scored',q=None if unknown else 3,
        q_rationale=dict(current_need='mock only',response_unit_ids=[units[0]['id']],source_turn_ids=[ids[0]],reason='mock only'),
        assessments=[dict(response_unit_id=u['id'],relation='non_factual',severity=0,source_turn_ids=[],reason='mock only') for u in units],
        coverage='mock only',uncertainty_reasons=['mock ambiguity'] if unknown else [])


def raw(value,request_id='synthetic'):
    return dict(transport='deepseek',model='deepseek-flash',system_fingerprint='mock-service',request_identity=request_id,
        choices=[dict(message=dict(content=s.canonical(value),reasoning_content='DO NOT FORWARD THINKING'),finish_reason='stop')],
        usage=dict(prompt_tokens=1000,completion_tokens=1000,completion_tokens_details={'reasoning_tokens':700}),
        total_seconds=1,request_started_unix=1792368000)


class PairedTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        packet=s.read(p.BASE/'reference_preparation_20261016_v1/materials/packet.json')
        self.items={key:dict(reply=x['reply'],evidence=packet['contexts'][x['context_id']],context_id=x['context_id'])
                    for key,x in zip(p.ITEM_KEYS,packet['items'])}
        self.protocol=dict(identity='mock-protocol',config=s.read(p.BASE/'configs.json')['deepseek_flash_high'],schedule=p.schedule(self.items))
        self.calls=[];self.budget=p.DiagnosticBudget(self.root/'money.jsonl',trial='same-old-trial',trial_cap=s.nanodollars(2),
            shared_cap=s.nanodollars(20),baseline=0,opening=0,account_opening=s.nanodollars(10))
        # No socket/credential read may occur in any mock test.
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect',side_effect=AssertionError('network forbidden in offline tests')).start()
        patch('deepseek_access.read_key',side_effect=AssertionError('credential read forbidden')).start()

    def execute(self,mutator=None,baseline=120,protocol=None):
        owner=self
        class Fake:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append((request,copy.deepcopy(messages)))
                item=owner.items[request['item_key']]
                v=check_value(item) if request['component']=='extract' else score_value(item)
                r=raw(v,request['request_id'])
                if mutator:mutator(request,messages,r)
                Path(raw_path).write_text('synthetic SSE; no network\n')
                return r
        return p.run(protocol or self.protocol,self.items,self.root/'run',Fake(),self.budget,
            mode='mock',global_count=lambda:baseline)

    def test_all_24_requests_16_flows_and_second_invocation_no_replay(self):
        x=self.execute();self.assertEqual((x['started'],x['cumulative'],x['paired_technically_complete']),(24,144,8))
        self.assertEqual(len(x['flows']),16);before={str(f):s.sha(f) for f in (self.root/'run').glob('*') if f.is_file()}
        self.execute();self.assertEqual(len(self.calls),24)
        for f,h in before.items():self.assertEqual(s.sha(f),h)
        self.assertEqual([x[0]['component'] for x in self.calls[:6]],['joint','extract','score','extract','score','joint'])

    def test_joint_prompt_and_schema_are_exact_original(self):
        for item in self.items.values():
            self.assertEqual(p.payload(item,'joint'),s.judge.messages_and_schema(item['evidence'],item['reply']))

    def test_full_original_sources_preserved_and_private_fields_absent(self):
        self.execute()
        for req,msg in self.calls:
            v=json.loads(msg[1]['content']);item=self.items[req['item_key']]
            self.assertEqual(v['legal_evidence'],item['evidence']);self.assertEqual(v['reply'],item['reply'])
            self.assertEqual(set(v),{'legal_evidence','reply','response_units'}|({'preliminary_check'} if req['component']=='score' else set()))
            self.assertNotIn('DO NOT FORWARD THINKING',s.canonical(msg))

    def test_semantically_wrong_valid_extract_is_passed_to_score(self):
        self.execute()
        scores=[json.loads(m[1]['content']) for r,m in self.calls if r['component']=='score']
        self.assertEqual(len(scores),8)
        self.assertTrue(all(x['preliminary_check']['claims'][0]['subject']=='synthetic possibly wrong actor' for x in scores))

    def test_unknown_extract_continues_and_unknown_final_does_not_become_zero(self):
        def change(req,msg,r):
            item=self.items[req['item_key']]
            r['choices'][0]['message']['content']=s.canonical(check_value(item,True) if req['component']=='extract' else score_value(item,True))
        x=self.execute(change);self.assertEqual(x['started'],24)
        self.assertTrue(all(f['technical_complete'] and f['model_unknown'] and f['q'] is None and f['m'] is None for f in x['flows']))

    def test_single_extract_mechanical_failure_skips_second_only(self):
        def change(req,msg,r):
            if req['item_key']=='dev04A' and req['component']=='extract':r['choices'][0]['message']['content']='{"status":'
        x=self.execute(change);self.assertEqual(x['started'],23)
        f=next(f for f in x['flows'] if f['item_key']=='dev04A' and f['arm']=='split')
        self.assertFalse(f['technical_complete']);self.assertEqual(f['dispatched_components'],1)
        self.assertEqual(x['paired_technically_complete'],7)

    def test_single_joint_failure_does_not_disqualify_other_flows(self):
        def change(req,msg,r):
            if req['item_key']=='dev04A' and req['component']=='joint':r['choices'][0]['finish_reason']='length'
        self.assertEqual(self.execute(change)['started'],24)

    def test_duplicate_keys_rejected_in_both_interfaces(self):
        item=self.items['dev04A']
        for component in ('extract','joint','score'):
            r=raw({});r['choices'][0]['message']['content']='{"status":"checked","status":"checked"}'
            self.assertFalse(p.evaluate(item,component,r,'mock','mock')['technical_valid'])

    def test_bad_exact_quote_and_unknown_source_rejected(self):
        item=self.items['dev04A'];value=check_value(item)
        for evidence in ([{'source_id':'C:T000','quote':'NOT IN SOURCE'}],[{'source_id':'C:T999','quote':'Hi'}]):
            v=copy.deepcopy(value);v['claims'][0].update(relation='supported',evidence=evidence)
            self.assertFalse(p.evaluate(item,'extract',raw(v),'mock','mock')['technical_valid'])
        v=score_value(item);v['q_rationale']['source_turn_ids']=['C:T999']
        self.assertFalse(p.evaluate(item,'joint',raw(v),'mock','mock')['technical_valid'])

    def test_duplicate_claim_and_wrong_response_quote_rejected(self):
        item=self.items['dev04A'];v=check_value(item);v['claims']*=2
        self.assertFalse(p.evaluate(item,'extract',raw(v),'mock','mock')['technical_valid'])
        v=check_value(item);v['claims'][0]['response_quote']='not in original'
        self.assertFalse(p.evaluate(item,'extract',raw(v),'mock','mock')['technical_valid'])

    def test_no_thinking_fallback_or_truncation_repair(self):
        item=self.items['dev04A'];r=raw(check_value(item));r['choices'][0]['message']['content']=''
        r['choices'][0]['message']['reasoning_content']=s.canonical(check_value(item))
        self.assertFalse(p.evaluate(item,'extract',r,'mock','mock')['technical_valid'])
        r=raw(check_value(item));r['choices'][0]['finish_reason']='length'
        self.assertFalse(p.evaluate(item,'extract',r,'mock','mock')['technical_valid'])

    def test_only_original_outer_envelope_allowed(self):
        item=self.items['dev04A'];r=raw(check_value(item));body=r['choices'][0]['message']['content']
        for wrapper,valid in [('```json\n'+body+'\n```',True),('Explanation\n'+body,False),('```json\n'+body+'\n```\n```json\n{}\n```',False)]:
            r['choices'][0]['message']['content']=wrapper
            self.assertEqual(p.evaluate(item,'extract',r,'mock','mock')['technical_valid'],valid)

    def test_two_global_consecutive_technical_failures_stop(self):
        def bad(req,msg,r):r['choices'][0]['message']['content']='broken'
        self.assertEqual(self.execute(bad)['started'],2)

    def test_component_failures_not_masked_by_other_component_success(self):
        def bad(req,msg,r):
            if req['component']=='joint':r['choices'][0]['message']['content']='broken'
        x=self.execute(bad);self.assertEqual(x['started'],6)
        self.assertTrue((self.root/'run/STOP.json').exists())

    def test_unknown_usage_keeps_reservation_and_no_retry(self):
        def change(req,msg,r):r.pop('usage')
        x=self.execute(change);self.assertEqual(x['started'],1)
        ev=self.budget.events();self.assertEqual([r['event'] for r in ev],['RESERVED'])
        self.assertEqual(self.budget._totals(ev)[1],p.RESERVE)
        self.execute();self.assertEqual(len(self.calls),1)

    def test_partial_usage_stays_unknown_not_zero(self):
        def change(req,msg,r):r['usage']['completion_tokens']=None
        x=self.execute(change)
        self.assertEqual((x['known_usage_requests'],x['usage_missing_requests']),(0,1))
        self.assertEqual(x['unresolved_liability_usd'],s.usd(p.RESERVE))
        self.assertIsNone(x['slots'][0]['financial']['accounted_upper_usd'])

    def test_failed_settlement_retains_full_liability(self):
        with patch.object(self.budget,'settle',side_effect=ValueError('synthetic accounting failure')):
            x=self.execute()
        self.assertEqual(x['started'],1)
        self.assertEqual(x['unresolved_liability_usd'],s.usd(p.RESERVE))
        self.assertIsNone(x['slots'][0]['financial']['accounted_upper_usd'])
        self.assertIsNotNone(x['slots'][0]['financial']['usage_upper_usd'])

    def test_stage_trial_and_shared_caps_apply(self):
        for attribute,value in [('stage_cap','.7'),('trial_cap','.7'),('shared_cap','.7'),('account_opening','.7')]:
            old=getattr(self.budget,attribute);setattr(self.budget,attribute,s.nanodollars(value))
            with self.assertRaises(ValueError):self.budget.reserve(attribute,p.RESERVE,{'study':p.STUDY})
            setattr(self.budget,attribute,old)

    def test_prior_trial_spend_not_reset_by_new_study(self):
        self.budget._append({'event':'RESERVED','reservation_id':'old','selection_trial':'same-old-trial','maximum_cost_usd':'1.4','binding':{'study':'old'}})
        with self.assertRaisesRegex(ValueError,'USD2'):self.budget.reserve('new',p.RESERVE,{'study':p.STUDY})

    def test_budget_duplicate_reservation_forbidden(self):
        self.budget.reserve('x',p.RESERVE,{'study':p.STUDY})
        with self.assertRaises(ValueError):self.budget.reserve('x',p.RESERVE,{'study':p.STUDY})

    def test_actual_exceeds_reservation_recorded_and_stops(self):
        def change(req,msg,r):r['usage']['completion_tokens']=1000000
        x=self.execute(change);self.assertEqual(x['started'],1)
        self.assertEqual(self.budget.events()[-1]['event'],'SETTLED')
        self.assertGreater(self.budget._totals(self.budget.events())[1],p.RESERVE)

    def test_reasoning_subset_not_double_charged(self):
        r=raw({});self.assertEqual(p.billed_peak_nanodollars(r),1500000)

    def test_cumulative_144_hard_limit(self):
        x=self.execute(baseline=143);self.assertEqual((x['started'],x['cumulative']),(1,144))

    def test_cross_version_does_not_replay_existing_slots(self):
        self.execute();old={str(f):s.sha(f) for f in (self.root/'run').glob('*.result.json')}
        newer=copy.deepcopy(self.protocol);newer['identity']='new-version'
        self.execute(protocol=newer);self.assertEqual(len(self.calls),24)
        for f,h in old.items():self.assertEqual(s.sha(f),h)

    def test_incomplete_started_is_preserved_and_blocks_not_retried(self):
        slot=self.protocol['schedule'][0];root=self.root/'run'
        s.save(root/(slot['slot_id']+'.started.json'),dict(slot=slot,protocol_identity='mock-protocol',request_identity='x',mode='mock'))
        x=self.execute();self.assertEqual(x['started'],1);self.assertEqual(len(self.calls),0)

    def test_orphan_result_rejected(self):
        s.save(self.root/'run'/'orphan.result.json',{})
        with self.assertRaises(ValueError):self.execute()

    def test_service_change_stops_immediately(self):
        def change(req,msg,r):
            if req['position']==2:r['system_fingerprint']='changed'
        self.assertEqual(self.execute(change)['started'],2)

    def test_request_identity_mismatch_stops_immediately(self):
        def change(req,msg,r):r['request_identity']='wrong-request'
        self.assertEqual(self.execute(change)['started'],1)

    def test_concurrent_money_reservations_cannot_exceed_stage_cap(self):
        from concurrent.futures import ThreadPoolExecutor
        def reserve(i):
            try:self.budget.reserve(str(i),p.RESERVE,{'study':p.STUDY});return True
            except ValueError:return False
        with ThreadPoolExecutor(max_workers=2) as pool:
            accepted=list(pool.map(reserve,[1,2]))
        self.assertEqual(sum(accepted),1)

    def test_public_table_change_is_detected_without_network(self):
        from live import table_identity
        doc=(p.HERE/'public_docs/pricing.html').read_bytes()
        self.assertNotEqual(table_identity(doc),table_identity(doc.replace(b'1.2',b'9.2')))

    def test_unapproved_live_mode_fails_before_send_or_key(self):
        with self.assertRaises(ValueError):p.run(self.protocol,self.items,self.root/'live',None,self.budget,mode='live',auth={'status':'PENDING'})

    def test_preflight_failure_receipt_preserves_stop_and_hides_uncontrolled_details(self):
        import live
        with patch.object(p,'BASE',self.root),patch.object(p,'approved'),patch.object(live,'_launch',side_effect=RuntimeError('do-not-log-synthetic-secret')):
            for _ in range(2):
                with self.assertRaises(SystemExit):live.launch(self.protocol,self.items,{})
        root=self.root/'paired_diagnostic_runs'/p.STUDY/'live'
        self.assertEqual(len(list(root.glob('launch_failure_*.json'))),2)
        self.assertFalse(list(root.glob('*.started.json')))
        self.assertNotIn('do-not-log-synthetic-secret',(root/'STOP.json').read_text())

    def test_transition_candidates_do_not_claim_semantic_correction(self):
        item=self.items['dev04A'];v=check_value(item);v['claims'][0]['relation']='unsupported'
        t=p.transition_candidates(v,score_value(item))
        self.assertIsNone(t['first_claims'][0]['correction_confirmed'])
        self.assertEqual(t['first_claims'][0]['candidate_class'],'changed_or_omitted_within_unit')
        self.assertTrue(t['new_judgment_candidates'])

    def test_full_input_screen_never_truncates(self):
        msg=[{'role':'system','content':'x'*700000},{'role':'user','content':'full'}];before=copy.deepcopy(msg)
        with self.assertRaises(ValueError):p.input_guard(msg)
        self.assertEqual(msg,before)


if __name__=='__main__':unittest.main(verbosity=2)
