"""Synthetic finite-pair admission checks; no model, source or gold."""
import ast,copy,inspect,unittest
from metacom_pm.rl1v3.journal import selective_memory_validation_run as R,joint_run
from metacom_pm.rl1v3.io import object_sha256

class SelectiveMemoryAdmission(unittest.TestCase):
    def setUp(self):
        self.frozen=[dict(domain='selective_memory_validation',task_id=f't{i:02}',arm=arm,
            logical_id=f'selective-memory-validation:t{i:02}:{arm}',request_id=f'synthetic-{i}-{arm}')
            for i in range(15) for arm in ('STOP','MS')]
    def batch(self,n):
        rows=self.frozen[:16] if n==1 else self.frozen[16:]
        return dict(batch_number=n,task_ids=list(dict.fromkeys(r['task_id'] for r in rows)),max_calls=len(rows),logical_requests=len(rows)),rows
    def test_complete_sixteen_and_fourteen(self):
        for n in (1,2):
            plan,rows=self.batch(n);R.validate_pairing(plan,rows,rows,self.frozen)
    def test_missing_or_duplicate_arm_rejected(self):
        plan,rows=self.batch(1)
        with self.assertRaises(ValueError):R.validate_pairing(plan,rows[:-1],rows[:-1],self.frozen)
        bad=copy.deepcopy(self.frozen);bad[1]['arm']='STOP'
        with self.assertRaises(ValueError):R.validate_pairing(plan,bad[:16],bad[:16],bad)
    def test_reselection_and_duplicate_payload_rejected(self):
        plan,rows=self.batch(1)
        with self.assertRaises(ValueError):R.validate_pairing(plan,self.frozen[2:18],self.frozen[2:18],self.frozen)
        bad=copy.deepcopy(self.frozen);bad[1]['request_id']=bad[0]['request_id']
        with self.assertRaises(ValueError):R.validate_pairing(plan,bad[:16],bad[:16],bad)
    def test_old_approval_cannot_transfer(self):
        plan=dict(protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,max_calls=16)
        auth=dict(protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,authorized=True,plan_sha256=object_sha256(plan),
            max_calls=16,max_model_loads=1,researcher='synthetic',decision_evidence='test-only')
        R.admit(plan,auth)
        for override in ({'authorized':False},{'protocol':joint_run.RUN_PROTOCOL},{'job_kind':joint_run.JOB_KIND},
            {'plan_sha256':'other'},{'max_calls':30},{'max_model_loads':2}):
            with self.assertRaises(ValueError):R.admit(plan,dict(auth,**override))
    def test_bounded_driver_function_unchanged(self):
        self.assertEqual(ast.dump(ast.parse(inspect.getsource(R.run))),ast.dump(ast.parse(inspect.getsource(joint_run.run))))

if __name__=='__main__':unittest.main()
