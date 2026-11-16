import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import selection as s
import resume_engineering as r
from adapters import MockTransport

class GPUParsing(unittest.TestCase):
    def fixture(self,util=0,free=48551,processes=''):
        return (f'{r.UUID}, NVIDIA RTX A6000, {free}, {util}\n','',f'<nvidia_smi_log><gpu><uuid>{r.UUID}</uuid><processes>{processes}</processes></gpu></nvidia_smi_log>')
    def test_exact_uuid_and_csv_whitespace(self):
        x=list(self.fixture());x[0]='  '+x[0]
        self.assertTrue(r.parse_gpu(*x)['eligible'])
        x[0]=x[0].replace(r.UUID,r.UUID+'-extra')
        self.assertFalse(r.parse_gpu(*x)['eligible'])
    def test_thresholds_unchanged(self):
        self.assertTrue(r.parse_gpu(*self.fixture(free=45000))['eligible'])
        self.assertIn('utilization_not_zero',r.parse_gpu(*self.fixture(util=1))['rejection_reasons'])
        self.assertIn('free_memory_below_45000_MiB',r.parse_gpu(*self.fixture(free=44999))['rejection_reasons'])
    def test_unknown_gpu_and_query_format_reject(self):
        for gpu in ['',f'{r.UUID}, NVIDIA RTX A6000, N/A, 0',f'{r.UUID}, NVIDIA RTX A6000, 48000, N/A']:
            x=list(self.fixture());x[0]=gpu;self.assertFalse(r.parse_gpu(*x)['eligible'])
    def test_process_absence_is_scoped_observation(self):
        x=r.parse_gpu(*self.fixture());self.assertEqual(x['process_visibility'],'queries_succeeded_no_processes_listed')
        self.assertIn('do not prove',x['visibility_limit'])
    def test_process_visibility_unavailable_rejects(self):
        for xml in ['',f'<nvidia_smi_log><gpu><uuid>{r.UUID}</uuid></gpu></nvidia_smi_log>',self.fixture()[2].replace('<processes></processes>','<processes>N/A</processes>')]:
            x=list(self.fixture());x[2]=xml;self.assertFalse(r.parse_gpu(*x)['eligible'])
    def test_colleague_compute_and_graphics_processes_block(self):
        proc='<process_info><pid>1234</pid><type>G</type><process_name>colleague</process_name></process_info>'
        self.assertIn('other_visible_gpu_process',r.parse_gpu(*self.fixture(processes=proc))['rejection_reasons'])
        x=list(self.fixture());x[1]=f'{r.UUID}, 2345, colleague_python, 1200\n'
        self.assertIn('other_visible_gpu_process',r.parse_gpu(*x)['rejection_reasons'])
    def test_resident_allows_only_own_process(self):
        proc='<process_info><pid>1234</pid><type>C</type><process_name>python</process_name></process_info>'
        self.assertTrue(r.parse_gpu(*self.fixture(util=100,free=2000,processes=proc),own_pid=1234)['eligible'])
        self.assertFalse(r.parse_gpu(*self.fixture(processes=proc),own_pid=1235)['eligible'])
    def test_raw_error_receipt_is_saved(self):
        from subprocess import CompletedProcess
        with tempfile.TemporaryDirectory() as t,patch.object(r.subprocess,'run',return_value=CompletedProcess(['query'],1,'RAW OUTPUT','permission denied')):
            x=r.GPUChecks(t).check()
            self.assertFalse(x['eligible']);self.assertTrue((Path(t)/'gpu_check_0001.json').exists())
            self.assertEqual(x['queries'][0]['stdout'],'RAW OUTPUT');self.assertEqual(x['queries'][0]['stderr'],'permission denied')
            self.assertIn('query_0_failed',str(x['rejection_reasons']))
    def test_auxiliary_proc_namespace_permission_is_not_gpu_query_failure(self):
        from subprocess import CompletedProcess
        values=[CompletedProcess(['query'],0,x,'') for x in self.fixture()]
        real_readlink=r.os.readlink
        def readlink(path):
            if path=='/proc/1/ns/pid':raise PermissionError('host policy')
            return real_readlink(path)
        with tempfile.TemporaryDirectory() as t,patch.object(r.subprocess,'run',side_effect=values),patch.object(r.os,'readlink',side_effect=readlink):
            x=r.GPUChecks(t).check()
            self.assertTrue(x['eligible']);self.assertEqual(x['process_visibility_context']['error'],'PermissionError')
    def test_wait_bound_and_block_then_idle(self):
        with tempfile.TemporaryDirectory() as t:
            g=r.GPUChecks(t)
            with self.assertRaises(ValueError):g.wait_idle(301)
            with patch.object(g,'check',side_effect=[dict(eligible=False,check_index=1),dict(eligible=True,check_index=2)]),patch.object(r.time,'sleep'):
                x=g.wait_idle(300)
            self.assertTrue(x['eligible']);self.assertEqual(x['check_indices'],[1,2])

class Continuation(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan=s.load_plan();cls.approval=s.read(s.HERE/'local_engineering_20261015/approval_engineering_AB.json')
    def setup_root(self,t):
        root=Path(t)/'pool';root.mkdir();parent=root/'engineering.AB.stage_result.json'
        s.save(parent,dict(plan_identity=self.plan['identity'],phase='engineering',mode='mock',started=0,attempts=[dict(request_id=x['request_id'],started=False) for x in r.slots(self.plan)]))
        return root,parent
    def run_it(self,root,parent,name,ready=True,fail=False):
        out=root/'continuations'/name;out.mkdir(parents=True)
        plan=self.plan
        class Transport(MockTransport):
            load_seconds=0
            def __init__(self,c):super().__init__(plan);self.config=c
            def gpu_condition(self):return 'mock telemetry'
            def send(self,m,sch,*,request,raw_path):
                if fail and request['candidate']==r.CANDIDATES[0]:
                    Path(raw_path).write_text('{}');raise TimeoutError('test only')
                return super().send(m,sch,request=request,raw_path=raw_path)
        return r.continue_stage(self.plan,root,out,self.approval,parent,mode='mock',wait_fn=lambda:dict(eligible=ready),transport_factory=Transport,static_check=lambda:None)
    def test_blocked_stage_can_continue_without_replacing_history(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);h=s.sha(parent)
            one=self.run_it(root,parent,'blocked',False);self.assertEqual(one['started_this_continuation'],0)
            child=root/'continuations/blocked/continuation_result.json';ch=s.sha(child)
            two=self.run_it(root,child,'continued');self.assertEqual(two['started_this_continuation'],8)
            self.assertEqual(two['history_after']['cumulative_calls'],74)
            self.assertEqual(s.sha(parent),h);self.assertEqual(s.sha(child),ch)
            self.assertEqual([x['request_id'] for x in two['attempts']],[x['request_id'] for x in r.slots(self.plan)])
            self.assertTrue(all(x['candidate'] in r.CANDIDATES for x in two['attempts']))
    def test_second_continuation_never_dispatches_completed(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);self.run_it(root,parent,'first')
            hashes={str(x):s.sha(x) for x in root.rglob('*.started.json')}
            two=self.run_it(root,parent,'second');self.assertEqual(two['started_this_continuation'],0)
            self.assertEqual(two['history_after']['cumulative_calls'],74)
            self.assertEqual(hashes,{str(x):s.sha(x) for x in root.rglob('*.started.json')})
    def test_failed_configuration_stays_stopped_peer_continues(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);one=self.run_it(root,parent,'first',fail=True)
            self.assertEqual(one['started_this_continuation'],5)
            self.assertEqual(one['history_after']['per_configuration'],{r.CANDIDATES[0]:1,r.CANDIDATES[1]:4})
            self.assertEqual(self.run_it(root,parent,'second')['started_this_continuation'],0)
    def test_started_without_result_is_counted_and_never_retried(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);req=r.slots(self.plan)[0]
            s.save(root/req['candidate']/(req['request_id']+'.started.json'),dict(request=req,mode='mock'))
            x=self.run_it(root,parent,'resume')
            self.assertEqual(x['started_this_continuation'],4);self.assertEqual(x['history_after']['cumulative_calls'],71)
            self.assertEqual(x['attempts'][0]['reason'],'existing start/result retained; skip')
    def test_orphan_raw_counts_conservatively(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);req=r.slots(self.plan)[0]
            s.save(root/req['candidate']/(req['request_id']+'.raw.json'),dict(incomplete=True))
            x=self.run_it(root,parent,'resume');self.assertEqual(x['history_after']['cumulative_calls'],71)
            self.assertTrue(x['history_after']['issues'])
    def test_parent_missing_evidence_cannot_reset_count(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);p=s.read(parent);p['attempts'][0]['started']=True
            other=root/'historical.stage_result.json';s.save(other,p)
            with self.assertRaisesRegex(ValueError,'cannot reset'):self.run_it(root,other,'bad')
    def test_identity_tampering_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);req=copy.deepcopy(r.slots(self.plan)[0]);req['seed']+=1
            s.save(root/req['candidate']/(req['request_id']+'.started.json'),dict(request=req,mode='mock'))
            with self.assertRaisesRegex(ValueError,'identity'):self.run_it(root,parent,'bad')
    def test_receipts_never_overwritten(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);self.run_it(root,parent,'first',False)
            with self.assertRaises(FileExistsError):self.run_it(root,parent,'first')
    def test_unknown_extra_attempt_rejected(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);s.save(root/'unknown.started.json',{})
            with self.assertRaisesRegex(ValueError,'unknown attempt'):self.run_it(root,parent,'bad')
    def test_shared_loader_not_retried_as_other_mode(self):
        with tempfile.TemporaryDirectory() as t:
            root,parent=self.setup_root(t);out=root/'resume';out.mkdir()
            calls=[]
            def fail(c):calls.append(c);raise RuntimeError('load failure')
            x=r.continue_stage(self.plan,root,out,self.approval,parent,mode='mock',wait_fn=lambda:dict(eligible=True),transport_factory=fail,static_check=lambda:None)
            self.assertEqual(len(calls),1);self.assertEqual(x['started_this_continuation'],0)

if __name__=='__main__':unittest.main()
