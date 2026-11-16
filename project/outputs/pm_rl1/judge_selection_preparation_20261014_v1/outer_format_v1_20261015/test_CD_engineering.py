"""Offline CD dispatch/finance tests; no credentials, HTTP or GPU access."""
import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import continue_v1 as c
import selection as s
from adapters import MockTransport,api_body
from deepseek_access import read_key,cost_from_usage,AccountBudget

class CDTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.plan=s.load_plan();self.p=c.protocol(self.plan,api_engineering=True);self.calls=[]
        actual=s.HERE/'live_runs'
        for f in actual.rglob('*.json'):
            if not (f.name.endswith(('.started.json','.result.json')) or f.name=='STOP.json' or f.name=='engineering.AB.stage_result.json'):continue
            value=s.read(f)
            if 'mode'in value:value['mode']='mock'
            s.save(self.root/f.relative_to(actual),value)
        self.before={str(f):s.sha(f) for f in self.root.rglob('*.json')}

    def run_stage(self,name,*,technical=False,hard=False,missing=False,drift=False,cap='2'):
        owner=self
        class Transport:
            def __init__(self,config):self.config=config
            def gpu_condition(self):pass
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request)
                if technical and request['candidate']==s.CANDIDATES[2]:raise TimeoutError('synthetic only')
                orig=next(x for x in owner.plan['requests'] if x['request_id']==request['original_slot_request_id'])
                raw=MockTransport(owner.plan).send(messages,schema,request=orig,raw_path=raw_path)
                raw.update(request_identity=request['request_id'],model='deepseek-flash',request_started_unix=1792065600,total_seconds=1)
                if missing:raw.pop('usage')
                if drift and request['candidate']==s.CANDIDATES[3]:raw['system_fingerprint']='changed'
                return raw
        def review(req,orig,response):
            return dict(request_id=req['request_id'],item_key=orig['item_key'],response_sha256=s.sha(response),
                explanation='synthetic unknown, not a research judgment',source_checks=[],critical_unknown=True,
                material_source_proven_error=hard and req['candidate']==s.CANDIDATES[2],unexplained_equivalence_difference=False,
                hard_stop_evidence=[dict(claim='synthetic',source='synthetic',criterion='synthetic')])
        budget=AccountBudget(self.root/'money.jsonl',trial=self.p['identity'],trial_cap=s.nanodollars(cap),
            shared_cap=s.nanodollars(20),opening=0,baseline=0,account_available_usd='2.8785')
        out=self.root/name;out.mkdir()
        with patch.object(c,'validate_release',return_value=list(s.CANDIDATES[2:])):
            return c.run(self.plan,self.p,{},self.root,out,mode='mock',preflight=lambda:None,
                wait_idle=lambda:self.fail('GPU guard must not run'),transport_factory=Transport,review_fn=review,budget=budget)

    def test_fixed_eight_to107_unknown_continues_old_history_and_no_replay(self):
        result=self.run_stage('one')
        self.assertEqual(result['history_after']['cumulative_calls'],107)
        labels={x:s for x,s in zip(s.CANDIDATES,'ABCD')}
        self.assertEqual([labels[x['candidate']]+x['item_key'][3:] for x in self.calls],['C02B','D02B','D15B','C15B','C37A','D37A','D37B','C37B'])
        self.assertEqual(result['shared_residence_seconds'],0)
        for path,sha in self.before.items():self.assertEqual(s.sha(path),sha)
        decisions=[s.read(p) for p in (self.root/'one').glob('*.diagnostic.json')]
        self.assertTrue(all(x['model_unknown'] and x['reviewer_unresolved_ambiguity'] and not x['reward_eligible'] and x['q']is None for x in decisions))
        self.run_stage('two');self.assertEqual(len(self.calls),8)

    def test_technical_failure_stops_affected_no_retry_other_four_continue(self):
        result=self.run_stage('one',technical=True);self.assertEqual(len(self.calls),5)
        self.assertEqual(result['history_after']['cumulative_calls'],104)
        self.run_stage('two');self.assertEqual(len(self.calls),5)
        events=s.read(self.root/'one/stage_result.json');self.assertIn(s.CANDIDATES[2],events['blocked'])

    def test_unknown_plus_material_still_stops(self):
        self.run_stage('one',hard=True);self.assertEqual(len(self.calls),5)

    def test_missing_usage_retains_full_reserves(self):
        self.run_stage('one',missing=True);self.assertEqual(len(self.calls),2)
        events=[json.loads(x) for x in (self.root/'money.jsonl').read_text().splitlines()]
        self.assertEqual([x['event'] for x in events],['RESERVED','RESERVED'])
        self.assertEqual(sum(s.nanodollars(x['maximum_cost_usd']) for x in events),2*s.API_WORST)

    def test_insufficient_next_liability_prevents_dispatch(self):
        self.run_stage('one',technical=True,cap='1');self.assertEqual(len(self.calls),1)

    def test_service_drift_stops_affected_and_known_usage_accounts(self):
        self.run_stage('one',drift=True);self.assertEqual(len(self.calls),5)

    def test_fixed_body_and_no_forbidden_fields(self):
        for req in self.p['requests']:
            orig=next(x for x in self.plan['requests'] if x['request_id']==req['original_slot_request_id'])
            messages,_=s.payload(self.plan,orig);body=api_body(self.p['configs'][req['candidate']],messages)
            self.assertEqual(body['messages'],messages);self.assertEqual(body['max_tokens'],393216)
            self.assertEqual(body['model'],'deepseek-flash');self.assertTrue(body['stream'])
            if req['candidate']==s.CANDIDATES[2]:self.assertNotIn('reasoning_effort',body);self.assertNotIn('top_p',body)
            else:self.assertNotIn('temperature',body);self.assertEqual(body['reasoning_effort'],'high')

    def test_credential_literal_only_and_no_other_variable(self):
        path=self.root/'fake.env';path.write_text('OTHER_KEY=must-not-be-used\nDEEPSEEK_API_KEY="synthetic-key" # comment\n')
        self.assertEqual(read_key(path),'synthetic-key')
        for text in ['DEEPSEEK_API_KEY=$(touch impossible)','DEEPSEEK_API_KEY=`echo x`','DEEPSEEK_API_KEY=one\nDEEPSEEK_API_KEY=two','OTHER_KEY=value']:
            path.write_text(text)
            with self.assertRaises(ValueError):read_key(path)

    def test_usage_total_thinking_not_double_counted(self):
        raw=dict(usage=dict(prompt_tokens=1000,prompt_cache_hit_tokens=800,prompt_cache_miss_tokens=200,
            completion_tokens=500,completion_tokens_details={'reasoning_tokens':400}),request_started_unix=1792065600,total_seconds=1)
        cost=cost_from_usage(raw);self.assertEqual(cost['accounted_upper_nanodollars'],900000)
        self.assertFalse(cost['invoice_confirmed'])

if __name__=='__main__':unittest.main()
