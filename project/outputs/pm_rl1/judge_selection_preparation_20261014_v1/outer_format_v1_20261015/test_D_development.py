"""Only synthetic transport; immutable 107-attempt history copied to temp."""
import contextlib,io,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import continue_v1 as c
import selection as s
from adapters import MockTransport,api_body
from deepseek_access import AccountBudget
class DTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.plan=s.load_plan();self.p=c.protocol(self.plan,api_development=True);self.calls=[]
        actual=s.HERE/'live_runs'
        for f in actual.rglob('*.json'):
            if not(f.name.endswith(('.started.json','.result.json')) or f.name in ('STOP.json','engineering.AB.stage_result.json')):continue
            val=s.read(f)
            if 'mode'in val:val['mode']='mock'
            s.save(self.root/f.relative_to(actual),val)
        self.before={str(f):s.sha(f) for f in self.root.rglob('*.json')}
        self.money=AccountBudget(self.root/'money.jsonl',trial=self.p['financial_trial_identity'],trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),opening=0,baseline=0,account_available_usd='2.85')
        self.money.reserve('prior-CD',s.nanodollars('.0691662'),{})
        self.money.settle('prior-CD',s.nanodollars('.0691662'),'historical')
    def run_stage(self,name,hard=False,technical=False,drift=False):
        owner=self
        class Transport:
            def __init__(self,config):self.config=config
            def gpu_condition(self):pass
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request)
                if technical:raise TimeoutError('synthetic')
                orig=next(x for x in owner.plan['requests'] if x['request_id']==request['original_slot_request_id'])
                raw=MockTransport(owner.plan).send(messages,schema,request=orig,raw_path=raw_path)
                raw.update(request_identity=request['request_id'],model='deepseek-flash',system_fingerprint='changed' if drift else 'previous',request_started_unix=1792065600,total_seconds=1)
                return raw
        def review(req,orig,response):
            return dict(request_id=req['request_id'],item_key=orig['item_key'],response_sha256=s.sha(response),explanation='synthetic only',source_checks=[],critical_unknown=True,material_source_proven_error=hard,unexplained_equivalence_difference=False,hard_stop_evidence=[dict(claim='synthetic',source='synthetic',criterion='synthetic')])
        out=self.root/name;out.mkdir();s.save(out/'service_identity.json',dict(model='deepseek-flash',system_fingerprint='previous'))
        with patch.object(c,'validate_release',return_value=[s.CANDIDATES[3]]),contextlib.redirect_stdout(io.StringIO()):
            return c.run(self.plan,self.p,{},self.root,out,mode='mock',preflight=lambda:None,wait_idle=lambda:self.fail('no GPU'),transport_factory=Transport,review_fn=review,budget=self.money)
    def test_full36_to143_order_repeats_no_replay_and_history_preserved(self):
        result=self.run_stage('one');self.assertEqual(result['history_after']['cumulative_calls'],143)
        self.assertEqual(len(self.calls),36);self.assertTrue(all(r['candidate']==s.CANDIDATES[3] for r in self.calls))
        actual=c.reconstruct(self.plan,self.p,s.HERE/'live_runs')['slot_owners']
        self.assertEqual([r['original_slot_request_id'] for r in self.calls],[r['original_slot_request_id'] for r in self.p['requests'] if r['original_slot_request_id'] not in actual])
        self.assertEqual(len(set(r['original_slot_request_id'] for r in self.calls)),36)
        for p,h in self.before.items():self.assertEqual(s.sha(p),h)
        decisions=[s.read(p) for p in (self.root/'one').glob('*.diagnostic.json')]
        self.assertTrue(all(x['model_unknown'] and x['reviewer_unresolved_ambiguity'] and not x['hard_stop'] and not x['reward_eligible'] for x in decisions))
        self.run_stage('two');self.assertEqual(len(self.calls),36)
        self.assertGreater(self.money._totals(self.money.events())[1],s.nanodollars('.0691662'))
    def test_unknown_and_material_stops_no_retry(self):
        self.assertEqual(self.run_stage('one',hard=True)['history_after']['cumulative_calls'],108)
        self.run_stage('two');self.assertEqual(len(self.calls),1)
    def test_technical_stops_retains_liability(self):
        self.run_stage('one',technical=True);self.assertEqual(len(self.calls),1)
        _,trial,res,sett=self.money._totals(self.money.events());self.assertEqual(trial,s.nanodollars('.0691662')+s.API_WORST)
        self.assertEqual(len(set(res)-set(sett)),1)
    def test_service_fingerprint_drift_stops_first(self):
        self.run_stage('one',drift=True);self.assertEqual(len(self.calls),1)
    def test_trial_cannot_reset_when_protocol_changes(self):
        self.assertNotEqual(self.p['identity'],self.p['financial_trial_identity'])
        self.money.reserve('remaining',s.nanodollars('1.2'),{})
        with self.assertRaises(ValueError):self.money.reserve('next',s.API_WORST,{})
    def test_payloads_frozen_and_no_ab_c(self):
        self.assertEqual(len(self.p['requests']),40)
        for req in self.p['requests']:
            orig=next(x for x in self.plan['requests'] if x['request_id']==req['original_slot_request_id'])
            messages,_=s.payload(self.plan,orig);body=api_body(self.p['configs'][req['candidate']],messages)
            self.assertEqual(body,api_body(self.plan['configs'][req['candidate']],messages));self.assertEqual(body['max_tokens'],393216)
        self.assertEqual(self.p['allowed_live_candidates'],[s.CANDIDATES[3]])
if __name__=='__main__':unittest.main()
