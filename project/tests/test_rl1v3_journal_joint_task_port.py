"""Synthetic query/privacy guards plus optional frozen 96-path CPU receipts."""
import ast
import json
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from metacom_pm.rl1v3.journal.joint_task_port import JointTaskPort,TaskTokenizer
from metacom_pm.rl1v3.journal import joint_run,structured_run
from metacom_pm.rl1v3.io import object_sha256

class Joint(unittest.TestCase):
    def test_retrieval_query_is_visible_task_not_anchor_text(self):
        records=[SimpleNamespace(record_id='rec-a',reading_text='orchard basket',source_rank=1),
                 SimpleNamespace(record_id='rec-b',reading_text='station ticket',source_rank=2)]
        p=JointTaskPort.__new__(JointTaskPort);p.query='orchard';p.query_sha256='visible-query';p.prefix='station secret anchor'
        p.private_rankings={};p.ms=SimpleNamespace(bank_version='bank',index_version='index',
            bank=SimpleNamespace(candidates=lambda h,prefix:records))
        ranked=p._search_ms('MS');self.assertEqual(ranked.ranked[0].record_id,'rec-a')
        self.assertEqual(ranked.ranked[0].score,1)

    def test_public_observation_allowlist_hides_anchor_and_scores(self):
        p=JointTaskPort.__new__(JointTaskPort);p.task_id='synthetic';p.turns=({'role':'seeker','text':'visible question'},)
        p.prefix='secret original dialogue';p.private_rankings={'scores':'hidden'}
        p._context=lambda acquired:((),(),10);p.availability=lambda:dict(MS=1,RS=1,MP=0,ME=0)
        p.action_mask=lambda acquired:('GET_MS','GET_RS','STOP')
        obs=p.public_observation();text=json.dumps(obs)
        self.assertNotIn('secret original dialogue',text);self.assertNotIn('hidden',text)
        self.assertEqual(obs['visible_turns'][0]['text'],'visible question')

    def test_mask_uses_measurement_without_successful_read(self):
        source=Path(__import__('metacom_pm.rl1v3.journal.joint_task_port',fromlist=['x']).__file__).read_text()
        tree=ast.parse(source);cls=next(n for n in tree.body if isinstance(n,ast.ClassDef) and n.name=='JointTaskPort')
        for name in ('action_mask','unit_tokens'):
            fn=next(n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name==name)
            calls=[n.func.attr for n in ast.walk(fn) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute)]
            self.assertIn('measure',calls);self.assertNotIn('read',calls)

    def test_old_approval_rejected_and_worker_guards_preserved(self):
        p=dict(protocol=joint_run.RUN_PROTOCOL,job_kind=joint_run.JOB_KIND,max_calls=16)
        a=dict(authorized=True,protocol=structured_run.RUN_PROTOCOL,job_kind=structured_run.JOB_KIND,
            max_calls=16,max_model_loads=1,plan_sha256=object_sha256(p),researcher='fixture',decision_evidence='fixture')
        with self.assertRaises(Exception):joint_run.admit(p,a)
        def run_ast(path):
            tree=ast.parse(Path(path).read_text());return ast.dump(next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run'))
        self.assertEqual(run_ast(joint_run.__file__),run_ast(structured_run.__file__))

    @unittest.skipUnless(os.environ.get('JOURNAL_JOINT_PACKAGE'),'private CPU receipt not provided')
    def test_actual96_read_paths_and_nonzero_stop_cost(self):
        p=Path(os.environ['JOURNAL_JOINT_PACKAGE'])
        rows=[json.loads(x) for x in (p/'READ_CHECKS.private.jsonl').read_text().splitlines()]
        self.assertEqual(len(rows),96)
        expected={'STOP':0,'MS':1,'RS':1,'MS_RS':2}
        for row in rows:
            self.assertEqual(row['private_cost']['read_calls'],expected[row['arm']])
            self.assertGreater(row['online_path_cpu_ms'],0)
            self.assertTrue(row['MP_ME_masked']);self.assertTrue(row['after_stop_rejected'])
            self.assertTrue(row['pending_reward']);self.assertLessEqual(row['actual_input_tokens']+320,16384)
        for n in range(1,7):
            plan,physical,_=joint_run.check(p/f'batch-{n:02d}/PLAN.json')
            self.assertEqual(plan['logical_requests'],16);self.assertEqual(len(physical),16)

if __name__=='__main__':unittest.main()
