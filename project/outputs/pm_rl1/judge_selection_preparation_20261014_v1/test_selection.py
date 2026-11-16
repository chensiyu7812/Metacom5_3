import copy
import contextlib
import csv
import io
import json
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import selection as s
from adapters import MockTransport, api_body, billed_peak_nanodollars, final_content, token_accounting, gemma_token_accounting


class SelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = s.load_plan()

    def budget(self,path,cap=1):
        return s.Budget(path,trial='test',trial_cap=s.nanodollars(cap),
            shared_cap=s.nanodollars(20),baseline=0,opening=0)

    def api_request(self):
        return next(r for r in self.plan['requests'] if r['candidate']=='deepseek_flash_high')

    def test_full_dev_inputs_and_distinct_draws(self):
        p=self.plan
        self.assertEqual(len(p['requests']),160)
        self.assertEqual(len({r['request_id'] for r in p['requests']}),160)
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
        r=self.api_request();m,sch=s.payload(self.plan,r)
        raw=MockTransport(self.plan).send(m,sch,request=r,raw_path=None)
        raw['choices'][0]['finish_reason']='length'
        result=s.measured(self.plan,r,raw)
        self.assertEqual(result['measurement_status'],'technical_failure')
        self.assertIsNone(result['candidate_utility'])

    def test_output_duplicate_fields_still_rejected(self):
        r=self.api_request();m,sch=s.payload(self.plan,r)
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
        self.assertEqual(x['thinking'],{'type':'enabled'});self.assertEqual(x['reasoning_effort'],'high')
        y=api_body(self.plan['configs']['deepseek_flash_off'],messages)
        self.assertEqual(y['thinking'],{'type':'disabled'});self.assertEqual(y['temperature'],1.0)
        self.assertNotIn('reasoning_effort',y);self.assertNotIn('top_p',y)
        self.assertEqual(x['messages'],y['messages'])

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

    def test_four_configs_same_items_and_paired_seed(self):
        p=self.plan;self.assertEqual(len({c['identity'] for c in p['configs'].values()}),4)
        for slot in {r['paired_slot'] for r in p['requests']}:
            rr=[r for r in p['requests'] if r['paired_slot']==slot]
            self.assertEqual(len(rr),4)
            self.assertEqual(len({r['messages_identity'] for r in rr}),1)
            self.assertEqual(len({r['schema_identity'] for r in rr}),1)
            self.assertEqual(rr[0]['seed'],rr[1]['seed']);self.assertEqual(rr[2]['seed'],rr[3]['seed'])
        a,b=p['configs'][s.CANDIDATES[0]],p['configs'][s.CANDIDATES[1]]
        self.assertEqual({k for k in a if a[k]!=b[k]},{'enable_thinking','wrapper','label','identity'})

    def test_balanced_order_and_first_four_included(self):
        rows=sorted([r for r in self.plan['requests'] if r['phase']=='engineering'],key=lambda r:r['schedule_position'])
        labels=''.join(self.plan['configs'][r['candidate']]['label'] for r in rows)
        self.assertEqual(labels,'ABCDBADCCDABDCBA')
        for c in s.CANDIDATES:
            rr=[r for r in rows if r['candidate']==c]
            self.assertEqual([r['item_key'] for r in rr],['dev02B','dev15B','dev37A','dev37B'])
            self.assertTrue(all(r['draw']=='primary' for r in rr))

    def test_native_gemma_template_not_prompt_suppression(self):
        from jinja2 import Environment
        template=Environment().from_string((s.HERE/'official_chat_template_707f0a3.jinja').read_text())
        args=dict(messages=[{'role':'system','content':'RUBRIC'},{'role':'user','content':'FULL EVIDENCE'}],
                  add_generation_prompt=True,bos_token='<bos>')
        off=template.render(**args,enable_thinking=False)
        on=template.render(**args,enable_thinking=True)
        self.assertTrue(off.endswith('<|turn>model\n<|channel>thought\n<channel|>'))
        self.assertTrue(on.endswith('<|turn>model\n'))
        self.assertIn('<|think|>',on);self.assertNotIn('<|think|>',off)
        self.assertIn('FULL EVIDENCE',on);self.assertIn('FULL EVIDENCE',off)

    def test_token_partition_and_missing_reasoning_not_free(self):
        class Tokenizer:
            all_special_ids=[10,11,12]
            def encode(self,*a,**kw):return [10,20,21]
            def convert_tokens_to_ids(self,x):return 11
        t=gemma_token_accounting([10,20,21,30,31,11,40,41,12],Tokenizer(),100)
        self.assertEqual((t['thinking'],t['final'],t['format'],t['total_output']),(2,2,5,9))
        self.assertEqual(gemma_token_accounting([40,41,12],Tokenizer(),100)['thinking'],0)
        self.assertIsNone(gemma_token_accounting([10,20,21,30],Tokenizer(),100)['thinking'])
        raw={'transport':'deepseek','usage':{'prompt_tokens':100,'completion_tokens':200}}
        self.assertEqual(token_accounting(raw)['total_output'],200)
        self.assertIsNone(token_accounting(raw)['thinking'])
        self.assertEqual(billed_peak_nanodollars(raw),270000)

    def test_failed_configuration_does_not_stop_authorized_peers(self):
        with tempfile.TemporaryDirectory() as t:
            result=s.run_stage(self.plan,'engineering',Path(t),mode='mock',failures={'deepseek_flash_off':2})
            self.assertEqual(result['started'],14)
            self.assertEqual(set(result['blocked_configurations']),{'deepseek_flash_off'})
            for c in s.CANDIDATES:
                self.assertEqual(len(list((Path(t)/c).glob('*.started.json'))),2 if c=='deepseek_flash_off' else 4)
            self.assertFalse(result['next_phase_started'])

    def test_local_then_api_scopes_and_no_double_attempts(self):
        with tempfile.TemporaryDirectory() as t:
            a=s.run_stage(self.plan,'engineering',Path(t),mode='mock',candidates=s.CANDIDATES[:2])
            b=s.run_stage(self.plan,'engineering',Path(t),mode='mock',candidates=s.CANDIDATES[2:])
            self.assertEqual((a['started'],b['started']),(8,8))
            self.assertEqual(len(list(Path(t).rglob('*.started.json'))),16)
            with self.assertRaises(FileExistsError):s.run_stage(self.plan,'engineering',Path(t),mode='mock',candidates=s.CANDIDATES[:2])

    def test_off_approval_does_not_authorize_thinking_on(self):
        approval=s.read(s.HERE/'approval_template_PENDING.json')
        approval.update(status='APPROVED',confirmation_reference='TEST ONLY',
                        configuration_identities=[self.plan['configs'][s.CANDIDATES[0]]['identity']])
        s.verify_approval(self.plan,s.CANDIDATES[0],'engineering',approval)
        with self.assertRaises(ValueError):s.verify_approval(self.plan,s.CANDIDATES[1],'engineering',approval)

    def test_eight_native_ceilings_do_not_fit_five_dollars(self):
        self.assertGreater(s.API_WORST*8,s.nanodollars(5))
        with tempfile.TemporaryDirectory() as t:
            b=self.budget(Path(t)/'money.jsonl',cap=5)
            for i in range(6):b.reserve(str(i),s.API_WORST,{})
            with self.assertRaises(ValueError):b.reserve('6',s.API_WORST,{})

    def test_pool_comparison_unknown_and_missing_denominators(self):
        from analyze import compare_pool
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            root=Path(t)/'runs';s.run_stage(self.plan,'engineering',root,mode='mock')
            result=compare_pool(root,Path(t)/'analysis',allow_mock=True)
            for group in result['comparisons'].values():
                self.assertEqual(group['scheduled_reply_slots'],40)
                self.assertEqual(group['technical_common'],4);self.assertEqual(group['numeric_common'],0)
                self.assertEqual(group['numeric_pair_common'],0)
            self.assertIsNone(result['winner'])
            self.assertTrue(all(v['not_started']==36 for v in result['configurations'].values()))

    def test_multiple_bound_semantic_review_rows(self):
        from analyze import analyze
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            c=s.CANDIDATES[0];run=Path(t)/'run';s.execute(self.plan,c,'engineering',run,mode='mock')
            rows=[]
            for r in s.stage_requests(self.plan,c,'engineering')[:2]:
                source=self.plan['items'][r['item_key']]['evidence']['current_prefix'][0]
                rows.append(dict(candidate=c,request_id=r['request_id'],dimension='citation_location',
                    verdict='supported',source_ids=source['id'],exact_quote=source['text'],
                    explanation='TEST ONLY valid source binding, not real semantic review',material_error='0',
                    reviewer='MOCK',reviewed_raw_sha256=s.sha(run/(r['request_id']+'.response.json'))))
            path=Path(t)/'review.csv'
            with path.open('w',newline='') as f:
                w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
            summary,_,_=analyze(c,run,Path(t)/'analysis',True,path)
            self.assertEqual(summary['semantic_review_counts']['citation_location']['supported'],2)

    def test_numeric_pairing_retains_failed_slot_and_full_denominators(self):
        from analyze import compare_pool
        with tempfile.TemporaryDirectory() as t,contextlib.redirect_stdout(io.StringIO()):
            root=Path(t)/'runs'
            for r in self.plan['requests']:
                q=3 if r['candidate']==s.CANDIDATES[1] else 2
                failed=r['candidate']==s.CANDIDATES[1] and r['item_key']=='dev37A' and r['draw']=='primary'
                measurement=dict(measurement_status='technical_failure' if failed else 'measured_candidate',
                                 q=None if failed else q,m=None if failed else 0,
                                 candidate_utility=None if failed else q/4,reward_eligible=False)
                s.save(root/r['candidate']/(r['request_id']+'.result.json'),
                    dict(request=r,mode='mock',measurement=measurement,fixture='fabricated numerical test only'))
            result=compare_pool(root,Path(t)/'analysis',allow_mock=True)
            self.assertEqual(result['comparisons']['all_four']['numeric_common'],39)
            self.assertEqual(result['comparisons']['all_four']['numeric_primary_common'],31)
            self.assertEqual(result['comparisons']['all_four']['numeric_pair_common'],15)
            self.assertEqual(result['comparisons']['deepseek_off_on']['numeric_common'],40)
            self.assertFalse(result['configurations'][s.CANDIDATES[1]]['full_coverage'])
            self.assertEqual(result['configurations'][s.CANDIDATES[1]]['technical_failures'],1)
            with (Path(t)/'analysis/paired_configuration_metrics.csv').open() as f:
                rows=list(csv.DictReader(f))
            self.assertEqual({x['on_minus_off_U'] for x in rows if x['group']=='gemma_off_on'}, {'0.25',''})
            self.assertEqual(result['comparisons']['all_four']['scheduled_reply_slots'],40)
            self.assertIsNone(result['winner'])


if __name__=='__main__':unittest.main()
