import unittest,tempfile,sys,copy,json
from pathlib import Path
from fractions import Fraction
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import noise as n
from noise import p,s
import analysis as a
sys.path.insert(0,str(n.BASE/'paired_diagnostic_20261019_v1/tests'))
from test_paired import raw,score_value

class NoiseTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.proposal=s.read(n.PROPOSAL/'proposal.json');self.items=n.prepared_items()
        self.protocol=dict(identity='MOCK',config=self.proposal['configuration'],
            schedule=[x|dict(item_key=x['endpoint'],component='joint') for x in self.proposal['schedule']])
        self.budget=p.DiagnosticBudget(self.root/'money.jsonl',study=n.STUDY,stage_cap=s.nanodollars('1.25'),
            trial='same-trial',trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),baseline=0,opening=0)
        self.calls=[];self.addCleanup(patch.stopall)
        patch('socket.socket.connect',side_effect=AssertionError('no network')).start()
        patch('noise.read_key',side_effect=AssertionError('no credentials')).start()
    def run_batch(self,change=None,baseline=153,protocol=None):
        owner=self
        class Mock:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request)
                r=raw(score_value(owner.items[request['item_key']]),request['request_id'])
                if change:change(r,request)
                Path(raw_path).write_text('MOCK ONLY')
                return r
        rt=n.runtime();rt['review']=None
        return p.run(protocol or self.protocol,self.items,self.root/'run',Mock(),self.budget,mode='mock',
            global_count=lambda:baseline,runtime=rt)
    def test_48_fixed_draw_slots_no_replay_old_history_preserved(self):
        result=self.run_batch();self.assertEqual((result['started'],result['cumulative']),(48,201))
        self.assertEqual(len({x['slot_id'] for x in self.calls}),48)
        before={str(f):s.sha(f) for f in (self.root/'run').glob('*.json')}
        self.run_batch();self.assertEqual(len(self.calls),48)
        self.assertTrue(all(s.sha(f)==h for f,h in before.items()))
        self.assertTrue(all(not x['result']['reward_eligible'] and x['result']['semantic_revisions_applied']==2 for x in result['slots']))
    def test_payloads_identical_to_proposal(self):
        for e in self.proposal['endpoints']:
            m,sc=n.payload(self.items[e['row_id']],'joint');original=s.read(n.PROPOSAL/e['payload_file'])
            self.assertEqual((m,sc),(original['messages'],original['schema']))
    def test_old_stop_prevents_redispatch_and_is_not_overwritten(self):
        (self.root/'run').mkdir();s.save(self.root/'run/STOP.json',{'reason':'old-stop'})
        before=s.sha(self.root/'run/STOP.json');self.assertEqual(self.run_batch()['started'],0)
        self.assertEqual(s.sha(self.root/'run/STOP.json'),before)
    def test_cross_version_no_redispatch(self):
        self.run_batch();changed=copy.deepcopy(self.protocol);changed['identity']='CHANGED'
        self.run_batch(protocol=changed);self.assertEqual(len(self.calls),48)
    def test_201_hard_stop(self):self.assertEqual(self.run_batch(baseline=200)['started'],1)
    def test_duplicate_keys_twice_stop_no_retry(self):
        x=self.run_batch(lambda r,req:r['choices'][0]['message'].update(content='{"q":1,"q":2}'))
        self.assertEqual(x['started'],2);self.run_batch();self.assertEqual(len(self.calls),2)
    def test_isolated_schema_failure_continues(self):
        def mutate(r,req):
            if req['position']==1:r['choices'][0]['message']['content']='{}'
        x=self.run_batch(mutate);self.assertEqual((x['started'],x['technical_complete']),(48,47))
    def test_illegal_source_id_retained_failure(self):
        def mutate(r,req):
            if req['position']==1:
                value=json.loads(r['choices'][0]['message']['content']);value['q_rationale']['source_turn_ids']=['H999:T000'];r['choices'][0]['message']['content']=s.canonical(value)
        x=self.run_batch(mutate);self.assertEqual(x['started'],48);self.assertFalse(x['slots'][0]['result']['technical_valid'])
    def test_truncated_final_stops_immediately(self):
        x=self.run_batch(lambda r,req:r['choices'][0].update(finish_reason='length'));self.assertEqual(x['started'],1)
    def test_missing_usage_retains_liability_stops(self):
        x=self.run_batch(lambda r,req:r.pop('usage'));self.assertEqual(x['started'],1);self.assertEqual(x['unresolved_liability_usd'],'0.786432')
    def test_model_unknown_continues_null(self):
        def mutate(r,req):r['choices'][0]['message']['content']=s.canonical(score_value(self.items[req['item_key']],True))
        x=self.run_batch(mutate);self.assertEqual(x['model_unknown'],48)
        self.assertTrue(all(r['result']['evaluation']['q'] is None for r in x['slots']))
    def test_semantic_variation_does_not_trigger_diagnostic_stop(self):
        def mutate(r,req):
            v=json.loads(r['choices'][0]['message']['content']);v['q']=2 if req['draw']%2 else 4;r['choices'][0]['message']['content']=s.canonical(v)
        self.assertEqual(self.run_batch(mutate)['started'],48)
    def test_service_drift_immediate_stop(self):
        x=self.run_batch(lambda r,req:r.update(system_fingerprint='changed' if req['position']==2 else 'mock-service'))
        self.assertEqual(x['started'],2)
    def test_stage_trial_shared_budget_reservation(self):
        b=self.budget;b.reserve('a',p.RESERVE,{'study':n.STUDY})
        with self.assertRaises(ValueError):b.reserve('b',p.RESERVE,{'study':n.STUDY})
        with self.assertRaises(ValueError):b.reserve('a',p.RESERVE,{'study':n.STUDY})
        b.settle('a',s.nanodollars('.47'),'mock known usage')
        with self.assertRaises(ValueError):b.reserve('c',p.RESERVE,{'study':n.STUDY})
        b.stage_cap=s.nanodollars(3);b.trial_cap=s.nanodollars(1)
        with self.assertRaises(ValueError):b.reserve('d',p.RESERVE,{'study':n.STUDY})
        b.trial_cap=s.nanodollars(3);b.shared_cap=s.nanodollars(1)
        with self.assertRaises(ValueError):b.reserve('e',p.RESERVE,{'study':n.STUDY})
    def test_no_live_without_exact_approval(self):
        self.protocol['diagnostic_policy']=self.proposal['proposed_dispatch_policy']
        with self.assertRaises(ValueError):n.approved(self.protocol,{})
    def test_disjoint_aggregation_and_no_imputation(self):
        x=a.compare_blocks([Fraction(1),Fraction(0),Fraction(-1),Fraction(0)])
        self.assertEqual(x['single']['absolute_discrepancy'],2)
        self.assertEqual(x['mean_two']['absolute_discrepancy'],1)
        x=a.compare_blocks([Fraction(1),None,Fraction(1),Fraction(1)])
        self.assertTrue(x['single']['complete']);self.assertFalse(x['mean_two']['complete'])
        self.assertIsNone(x['mean_two']['direction_changed'])
    def test_unknown_utility_not_zero(self):
        self.assertIsNone(a.utility({'technical_valid':True,'evaluation':{'model_unknown':True,'q':None,'m':None}}))

if __name__=='__main__':unittest.main()
