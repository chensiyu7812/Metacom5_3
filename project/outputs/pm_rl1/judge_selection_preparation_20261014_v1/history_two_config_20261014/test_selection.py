import copy
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import selection as s
from adapters import MockTransport, api_body, billed_peak_nanodollars, final_content


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = s.load_plan()

    def budget(self,path,cap=1):
        return s.Budget(path,trial='test',trial_cap=s.nanodollars(cap),
            shared_cap=s.nanodollars(20),baseline=0,opening=0)

    def test_full_dev_inputs_and_distinct_draws(self):
        p=self.plan
        self.assertEqual(len(p['requests']),80)
        self.assertEqual(len({r['request_id'] for r in p['requests']}),80)
        self.assertEqual(len({i['pair_id'] for i in p['items'].values()}),16)
        for c in p['configs']:
            self.assertEqual([len(s.stage_requests(p,c,x)) for x in s.STAGES],[4,28,8])
            self.assertEqual(len({r['item_key'] for r in p['requests'] if r['candidate']==c and r['draw']=='primary'}),32)
        for r in p['requests']:
            msgs,sch=s.payload(p,r)
            self.assertEqual(set(json.loads(msgs[1]['content'])),{'legal_evidence','reply','response_units'})
            self.assertEqual(msgs[0]['content'],s.judge.RUBRIC)

    def test_sealed_phase_rejected_before_file_access(self):
        with patch('pathlib.Path.read_text',side_effect=AssertionError('must not open')):
            with self.assertRaises(ValueError):
                s.stage_requests(self.plan,'deepseek_flash_high','sealed')

    def test_config_tampering(self):
        p=copy.deepcopy(self.plan);p['configs']['deepseek_flash_high']['reasoning_effort']='low'
        with self.assertRaises(ValueError):s.config_for(p,'deepseek_flash_high')

    def test_payload_tampering(self):
        p=copy.deepcopy(self.plan);r=p['requests'][0]
        p['items'][r['item_key']]['reply']+=' tamper'
        with self.assertRaises(ValueError):s.payload(p,r)

    def test_unknown_not_zero_or_tie(self):
        r=self.plan['requests'][0];m,sch=s.payload(self.plan,r)
        raw=MockTransport(self.plan).send(m,sch,request=r,raw_path=None)
        result=s.measured(self.plan,r,raw)
        self.assertEqual(result['measurement_status'],'semantic_uncertainty')
        self.assertIsNone(result['q']);self.assertIsNone(result['m'])
        self.assertIsNone(result['candidate_utility']);self.assertFalse(result['reward_eligible'])

    def test_length_is_technical_not_low_reward(self):
        r=self.plan['requests'][0];m,sch=s.payload(self.plan,r)
        raw=MockTransport(self.plan).send(m,sch,request=r,raw_path=None)
        raw['choices'][0]['finish_reason']='length'
        result=s.measured(self.plan,r,raw)
        self.assertEqual(result['measurement_status'],'technical_failure')
        self.assertIsNone(result['candidate_utility'])

    def test_output_duplicate_fields_still_rejected(self):
        r=self.plan['requests'][0];m,sch=s.payload(self.plan,r)
        raw=MockTransport(self.plan).send(m,sch,request=r,raw_path=None)
        raw['choices'][0]['message']['content']='{"status":"uncertain",'+raw['choices'][0]['message']['content'][1:]
        self.assertEqual(s.measured(self.plan,r,raw)['measurement_status'],'parse_or_evidence_failure')

    def test_thinking_billed_once_and_missing_usage_unknown(self):
        x={'usage':{'prompt_tokens':100,'completion_tokens':200,
                    'completion_tokens_details':{'reasoning_tokens':150}}}
        self.assertEqual(billed_peak_nanodollars(x),270000)
        self.assertIsNone(billed_peak_nanodollars({}))

    def test_inflight_blocks_next_reservation(self):
        with tempfile.TemporaryDirectory() as t:
            b=self.budget(Path(t)/'money.jsonl')
            b.reserve('1',s.API_WORST,{})
            with self.assertRaises(ValueError):b.reserve('2',s.API_WORST,{})
            self.assertFalse(b.settle('1',None,'timeout'))
            with self.assertRaises(ValueError):b.reserve('2',s.API_WORST,{})
            b.settle('1',s.nanodollars('.01'),'SUCCEEDED');b.reserve('2',s.API_WORST,{})

    def test_atomic_concurrent_reservations(self):
        with tempfile.TemporaryDirectory() as t:
            def attempt(i):
                try:self.budget(Path(t)/'money.jsonl').reserve(str(i),s.API_WORST,{});return True
                except ValueError:return False
            with ThreadPoolExecutor(max_workers=4) as pool:
                self.assertEqual(sum(pool.map(attempt,range(4))),1)

    def test_shared_liability_and_old_cap(self):
        with tempfile.TemporaryDirectory() as t:
            with self.assertRaises(ValueError):
                s.Budget(Path(t)/'negative.jsonl',trial='test',trial_cap=1,shared_cap=20,
                         baseline=0,opening=0,external_liability=-1)
            b=self.budget(Path(t)/'money.jsonl',cap=5);b.external_liability=s.nanodollars('19.5')
            with self.assertRaises(ValueError):b.reserve('1',s.API_WORST,{})
            b.external_liability=0;b.old_cap=s.nanodollars('.5')
            with self.assertRaises(ValueError):b.reserve('1',s.API_WORST,{})

    def test_failure_stops_and_retains_raw_attempt_and_reservation(self):
        with tempfile.TemporaryDirectory() as t:
            result=s.execute(self.plan,'deepseek_flash_high','engineering',t,mode='mock',fail_at=2)
            self.assertEqual(result['started'],2);self.assertTrue(result['stopped'])
            self.assertEqual(len(list(Path(t).glob('*.started.json'))),2)
            self.assertEqual(len(list(Path(t).glob('*.result.json'))),2)
            ev=[json.loads(x) for x in (Path(t)/'mock_money.jsonl').read_text().splitlines()]
            self.assertEqual([e['event'] for e in ev],['RESERVED','SETTLED','RESERVED'])
            self.assertTrue(any('incomplete stream' in p.read_text() for p in Path(t).glob('*.raw.json')))
            with self.assertRaises(ValueError):s.execute(self.plan,'deepseek_flash_high','engineering',t,mode='mock')

    def test_mock_cannot_release_live_stage(self):
        with tempfile.TemporaryDirectory() as t:
            s.execute(self.plan,'deepseek_flash_high','engineering',t,mode='mock')
            with self.assertRaises(ValueError):s.check_stage_gate(self.plan,'deepseek_flash_high','development',Path(t))

    def test_missing_freeze_and_approval_cannot_execute(self):
        with tempfile.TemporaryDirectory() as t:
            with patch('adapters.DeepSeekTransport',side_effect=AssertionError('no transport before approval')):
                with self.assertRaises(ValueError):s.execute(self.plan,'deepseek_flash_high','engineering',t,mode='live',approval={})

    def test_derived_observation_not_doubled(self):
        ref=s.read(s.HERE/'human_and_historical_reference_private.json')
        self.assertEqual(len(ref),32)
        self.assertTrue(all(r['human_observations']==1 and r['human_q'] is None for r in ref))
        self.assertEqual(len({r['pair_id'] for r in ref}),16)

    def test_api_field_whitelist(self):
        r=self.plan['requests'][0];messages,_=s.payload(self.plan,r)
        x=api_body(self.plan['configs']['deepseek_flash_high'],messages)
        self.assertNotIn('temperature',x);self.assertNotIn('seed',x)
        self.assertEqual(x['max_tokens'],393216)
        self.assertNotIn('human_preference',json.dumps(x))
        self.assertNotIn('Chen',json.dumps(x))

    def test_gemma_final_channel_only(self):
        raw={'transport':'gemma','natural_eos':True,'native_parsed':{'thinking':'private reasoning','content':'{}'}}
        self.assertEqual(final_content(raw),('{}','natural_stop'))
        raw['natural_eos']=False
        self.assertEqual(final_content(raw)[1],'non_natural_stop')
        raw['native_parsed']['tool_calls']=[{}]
        with self.assertRaises(ValueError):final_content(raw)

    def test_mock_gemma_end_to_end(self):
        with tempfile.TemporaryDirectory() as t:
            result=s.execute(self.plan,'gemma4_12b_bf16','engineering',t,mode='mock')
            self.assertEqual(result['started'],4);self.assertFalse(result['stopped'])
            self.assertFalse((Path(t)/'mock_money.jsonl').exists())

    def test_analysis_rejects_mock_as_real(self):
        from analyze import analyze
        with tempfile.TemporaryDirectory() as t:
            run=Path(t)/'run';s.execute(self.plan,'deepseek_flash_high','engineering',run,mode='mock')
            with self.assertRaises(ValueError):analyze('deepseek_flash_high',run,Path(t)/'analysis')

    def test_result_binding_tamper_rejected(self):
        from analyze import analyze
        with tempfile.TemporaryDirectory() as t:
            run=Path(t)/'run';s.execute(self.plan,'deepseek_flash_high','engineering',run,mode='mock')
            file=next(run.glob('*.result.json'));row=s.read(file)
            row['request']['configuration_identity']='wrong';file.write_text(json.dumps(row))
            with self.assertRaises(ValueError):analyze('deepseek_flash_high',run,Path(t)/'analysis',allow_mock=True)

    def test_bound_technical_failure_does_not_become_score(self):
        with tempfile.TemporaryDirectory() as t:
            original=MockTransport.send
            def wrong(obj,*a,**kw):
                result=original(obj,*a,**kw);result['request_identity']='wrong';return result
            with patch.object(MockTransport,'send',wrong):
                result=s.execute(self.plan,'deepseek_flash_high','engineering',t,mode='mock')
            self.assertEqual(result['started'],1);self.assertTrue(result['stopped'])
            row=s.read(next(Path(t).glob('*.result.json')))
            self.assertIsNone(row['measurement']['candidate_utility'])

    def test_old_cap_change_needs_explicit_amendment(self):
        approval=s.read(s.HERE/'approval_template_PENDING.json')
        approval.update(status='APPROVED',confirmation_reference='MOCK',cumulative_calls_limit=146,new_calls_limit=80)
        with self.assertRaises(ValueError):s.verify_approval(self.plan,'deepseek_flash_high','engineering',approval)


if __name__=='__main__':unittest.main()
