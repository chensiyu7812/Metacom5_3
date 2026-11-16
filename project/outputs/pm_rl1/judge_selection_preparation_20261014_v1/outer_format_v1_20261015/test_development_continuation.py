"""Only changed scheduling/accounting behavior; no model or GPU access."""
import copy,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import selection as s
import continue_v1 as c
from adapters import MockTransport

class DevelopmentContinuationTests(unittest.TestCase):
    def setUp(self):
        self.plan=s.load_plan();self.p=c.protocol(self.plan,development=True)
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.calls=[]
        s.save(self.root/'engineering.AB.stage_result.json',{'historical':'preserved'})
        # Seed the actual two strict attempts and six interface-v1 attempts as
        # mock accounting records. No output or review is relabelled as live.
        previous=s.read(c.HERE/'protocol.json')
        for r in previous['requests']:
            orig=next(x for x in self.plan['requests'] if x['request_id']==r['original_slot_request_id'])
            old=orig['item_key']=='dev02B';req=orig if old else r
            folder=self.root/req['candidate'] if old else self.root/c.SUBDIR/req['candidate']
            base=folder/req['request_id']
            s.save(base.with_suffix('.started.json'),dict(request=req,mode='mock'))
            result=dict(request=req,mode='mock')
            if not old:result['evaluation']=dict(measurement=dict(measurement_status='measured_candidate'))
            s.save(base.with_suffix('.result.json'),result)
        self.before={str(f):s.sha(f) for f in self.root.rglob('*.json')}

    def run_mock(self,name,*,eligible=True,fail=False,semantic=False):
        outer=self
        class Mock:
            load_seconds=0
            def gpu_condition(self):return 'mock'
            def send(self,messages,schema,*,request,raw_path):
                outer.calls.append(request)
                if fail and request['candidate']==s.CANDIDATES[0]:raise TimeoutError('mock failure')
                orig=next(x for x in outer.plan['requests'] if x['request_id']==request['original_slot_request_id'])
                raw=MockTransport(outer.plan).send(messages,schema,request=orig,raw_path=None)
                raw['request_identity']=request['request_id'];return raw
        def review(req,orig,path):
            return dict(request_id=req['request_id'],item_key=orig['item_key'],response_sha256=s.sha(path),
                explanation='mock scoped test',source_checks=[],material_source_proven_error=semantic and req['candidate']==s.CANDIDATES[0],
                critical_unknown=False,unexplained_equivalence_difference=False)
        out=self.root/name;out.mkdir()
        with patch.object(c,'validate_release',return_value=list(s.CANDIDATES[:2])):
            return c.run(self.plan,self.p,{},self.root,out,mode='mock',preflight=lambda:None,
                wait_idle=lambda:dict(eligible=eligible),transport_factory=lambda _:Mock(),review_fn=review)

    def test_fixed_72_slots_phase_order_repeats_and_146_ceiling(self):
        result=self.run_mock('run')
        self.assertEqual(len(self.calls),72);self.assertEqual(result['history_after']['cumulative_calls'],146)
        expected=[x for x in self.p['requests'] if x['phase']!='engineering']
        self.assertEqual(self.calls,expected)
        for name in s.CANDIDATES[:2]:
            calls=[x for x in self.calls if x['candidate']==name]
            self.assertEqual(len(calls),36)
            self.assertEqual(sum(x['draw']=='repeat-1' for x in calls),4)
            self.assertEqual(sum(x['phase']=='diagnostics' for x in calls),8)
        for f,h in self.before.items():self.assertEqual(s.sha(f),h)
        self.run_mock('again');self.assertEqual(len(self.calls),72)

    def test_gpu_block_can_resume_without_count_reset(self):
        result=self.run_mock('blocked',eligible=False);self.assertEqual(result['history_after']['cumulative_calls'],74)
        old=s.sha(self.root/'blocked/stage_result.json');self.run_mock('resumed')
        self.assertEqual(len(self.calls),72);self.assertEqual(s.sha(self.root/'blocked/stage_result.json'),old)

    def test_failure_counts_stops_only_affected_and_never_retries(self):
        result=self.run_mock('fail',fail=True)
        self.assertEqual(len(self.calls),37);self.assertEqual(result['history_after']['cumulative_calls'],111)
        self.assertEqual(result['history_after']['per_configuration'][s.CANDIDATES[0]],5)
        self.assertEqual(result['history_after']['per_configuration'][s.CANDIDATES[1]],40)
        self.run_mock('again');self.assertEqual(len(self.calls),37)

    def test_semantic_stop_blocks_remaining_primary_and_diagnostics(self):
        result=self.run_mock('semantic',semantic=True)
        self.assertEqual(len(self.calls),37);self.assertIn(s.CANDIDATES[0],result['blocked'])

    def test_duplicate_original_slot_across_versions_rejected(self):
        r=self.p['requests'][0]
        s.save(self.root/self.p['output_subdir']/r['candidate']/(r['request_id']+'.started.json'),dict(request=r,mode='mock'))
        with self.assertRaises(ValueError):c.reconstruct(self.plan,self.p,self.root,'mock')

    def test_started_without_result_is_counted_and_not_retried(self):
        r=next(x for x in self.p['requests'] if x['phase']=='development')
        s.save(self.root/self.p['output_subdir']/r['candidate']/(r['request_id']+'.started.json'),dict(request=r,mode='mock'))
        result=self.run_mock('partial')
        self.assertEqual(result['history_after']['cumulative_calls'],111)
        self.assertNotIn(r,self.calls)

    def test_interface_payload_and_generation_unchanged(self):
        old=s.read(c.HERE/'protocol.json')
        self.assertEqual(self.p['interface'],old['interface'])
        for key,config in self.plan['configs'].items():
            for k,value in config.items():
                if k!='identity':self.assertEqual(self.p['configs'][key][k],value)
        for r in self.p['requests']:
            orig=next(x for x in self.plan['requests'] if x['request_id']==r['original_slot_request_id'])
            messages,schema=s.payload(self.plan,orig)
            self.assertEqual(s.digest(messages),r['messages_identity'])
            self.assertEqual(s.digest(schema),r['schema_identity'])

    def test_scope_or_permission_expansion_rejected(self):
        with self.assertRaises(ValueError):c.validate_release(self.plan,self.p,dict(status='APPROVED',protocol_identity=self.p['identity'],new_calls_limit=73),self.root)

if __name__=='__main__':unittest.main()
