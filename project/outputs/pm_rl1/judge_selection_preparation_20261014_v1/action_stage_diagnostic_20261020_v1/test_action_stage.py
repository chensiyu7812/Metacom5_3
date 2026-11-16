import unittest,sys,tempfile,copy
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parent))
import action_stage as a
from action_stage import p,s
sys.path.insert(0,str(a.BASE/'paired_diagnostic_20261019_v1/tests'))
from test_paired import score_value,raw

class ActionStageTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
        self.items=s.read(a.BASE/'paired_diagnostic_20261019_v1/package/items.json')
        self.proposal=s.read(a.PROPOSAL/'proposal.json')
        self.protocol=dict(identity='MOCK',config=self.proposal['config'],schedule=[x|dict(item_key=x['item'],component='joint') for x in self.proposal['schedule']])
        self.budget=p.DiagnosticBudget(self.root/'money.jsonl',study=a.STUDY,trial='old-trial',trial_cap=s.nanodollars(2),shared_cap=s.nanodollars(20),baseline=0,opening=0)
        self.calls=[]
        self.addCleanup(patch.stopall)
        patch('socket.socket.connect',side_effect=AssertionError('no network')).start()
        patch('action_stage.read_key',side_effect=AssertionError('no credentials')).start()
    def execute(self,change=None,review=None,baseline=144,protocol=None):
        owner=self
        class Mock:
            def send(self,messages,schema,*,request,raw_path):
                owner.calls.append(request)
                r=raw(score_value(owner.items[request['item_key']],getattr(owner,'model_unknown',False)),request['request_id'])
                if change:change(r)
                Path(raw_path).write_text('MOCK ONLY')
                return r
        return p.run(protocol or self.protocol,self.items,self.root/'run',Mock(),self.budget,mode='mock',
            global_count=lambda:baseline,runtime=a.runtime(review))
    def test_all_slots_repeats_and_no_replay(self):
        result=self.execute();self.assertEqual((result['started'],result['cumulative']),(12,156))
        self.assertEqual(sum(x['item_key']=='dev06B' for x in self.calls),2)
        self.assertEqual(len({x['slot_id'] for x in self.calls}),12)
        snapshots={f:s.sha(f) for f in (self.root/'run').glob('*.json')}
        self.execute();self.assertEqual(len(self.calls),12)
        self.assertTrue(all(s.sha(f)==h for f,h in snapshots.items()))
        self.assertTrue(all(r['result']['semantic_revisions_applied']==2 and not r['result']['joint_prompt_unchanged'] and not r['result']['reward_eligible'] for r in result['slots']))
    def test_original_payloads_exact_and_authorization_required(self):
        for row in self.proposal['schedule']:
            messages,schema=a.payload(self.items[row['item']],'joint')
            original=s.read(a.PROPOSAL/'payloads'/f"{row['position']:02d}_{row['item']}.json")
            self.assertEqual(messages,original['messages']);self.assertEqual(schema,original['schema'])
        with self.assertRaises(ValueError):a.approved(self.protocol,{})
    def test_first_failure_stops_and_retains_unknown_liability(self):
        r=self.execute(lambda r:r.pop('usage'));self.assertEqual(r['started'],1)
        self.assertEqual(r['unresolved_liability_usd'],'0.786432')
        self.execute();self.assertEqual(len(self.calls),1)
    def test_duplicate_json_and_truncation_stop_first(self):
        r=self.execute(lambda r:r['choices'][0]['message'].update(content='{"q":1,"q":2}'))
        self.assertEqual(r['started'],1);self.assertFalse(r['slots'][0]['result']['technical_valid'])
    def test_semantic_review_stop_no_following_dispatch(self):
        r=self.execute(review=lambda *args:'source-proved error MOCK')
        self.assertEqual(r['started'],1);self.assertEqual(r['stop']['reason'],'source-proved error MOCK')
    def test_unknown_is_valid_null_not_zero_and_may_continue(self):
        self.model_unknown=True
        result=self.execute(review=lambda *args:None)
        self.assertEqual(result['started'],12);self.assertEqual(result['model_unknown'],12)
        self.assertTrue(all(x['result']['evaluation']['q'] is None and x['result']['evaluation']['m'] is None for x in result['slots']))
    def test_count_and_stage_budget_stop(self):
        self.assertEqual(self.execute(baseline=156)['started'],0)
        with self.assertRaises(ValueError):self.budget.reserve('huge',s.nanodollars('1.1'),{'study':a.STUDY})
    def test_cross_version_does_not_redispatch(self):
        self.execute();new=copy.deepcopy(self.protocol);new['identity']='DIFFERENT'
        self.execute(protocol=new);self.assertEqual(len(self.calls),12)

if __name__=='__main__':unittest.main()
