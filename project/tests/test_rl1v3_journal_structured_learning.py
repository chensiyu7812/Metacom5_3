"""Finite substantive field and isolated-admission regressions; no model calls."""
import ast
from copy import deepcopy
import json
from pathlib import Path
import unittest
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.journal.structured_learning import evaluate
from metacom_pm.rl1v3.journal import structured_run as R


def reference():
    return dict(value='booked',required_literal='ticket booked',required_delivered_quotes=['ticket booked'],
        evidence=dict(text='I have a ticket booked for the weekend.',speaker='seeker',reported_date='2024-10-30'))


def answer(**updates):
    a=dict(value='booked',certainty='supported',quote='I have a ticket booked for the weekend.',speaker='seeker',reported_date='2024-10-30')
    a.update(updates);return json.dumps(a)


class Structured(unittest.TestCase):
    def score(self,text,ref=None,delivered=None):
        return evaluate(text,ref or reference(),arm='RAW',delivered_text=delivered if delivered is not None else reference()['evidence']['text'])

    def test_correct_value_and_evidence(self):
        self.assertTrue(self.score(answer())['task_success'])

    def test_quote_and_format_do_not_rescue_wrong_stage(self):
        score=self.score(answer(value='attended'))
        self.assertEqual(score['structural_status'],'pass');self.assertTrue(score['evidence_correct'])
        self.assertFalse(score['value_correct']);self.assertFalse(score['task_success'])

    def test_correct_value_without_evidence_fails(self):
        s=self.score(answer(),delivered='No historical record supplied.')
        self.assertTrue(s['value_correct']);self.assertFalse(s['task_success'])
        self.assertFalse(s['epistemic_compliance'])

    def test_wrong_speaker_date_or_source_fails(self):
        for change in [dict(speaker='supporter'),dict(reported_date='2024-11-02'),dict(quote='I attended the retreat.')]:
            with self.subTest(change=change):self.assertFalse(self.score(answer(**change))['task_success'])

    def test_source_context_required(self):
        ref=reference();ref['required_delivered_quotes'].append('Alex owns the ticket')
        self.assertFalse(self.score(answer(),ref)['task_success'])

    def test_unknown_is_not_closed_world_negative(self):
        ref=reference();ref['value']='unknown'
        valid=answer(value='unknown',certainty='unknown',quote='',speaker='unknown',reported_date=None)
        self.assertTrue(self.score(valid,ref)['task_success'])
        self.assertFalse(self.score(answer(value='did_not_attend'),ref)['task_success'])
        self.assertFalse(self.score(answer(value='unknown'),ref)['task_success'])

    def test_abstention_when_missing_is_compliant_but_not_answer_success(self):
        text=answer(value='unknown',certainty='unknown',quote='',speaker='unknown',reported_date=None)
        score=self.score(text,delivered='No source provided.')
        self.assertTrue(score['epistemic_compliance']);self.assertFalse(score['task_success'])
        self.assertFalse(score['value_correct'])

    def test_no_output_repair_and_no_extra_fields(self):
        for text in ['```json\n'+answer()+'\n```',answer()[:-1]+',"extra":1}',json.dumps([])]:
            self.assertFalse(self.score(text)['task_success'])

    def test_approval_not_transferable(self):
        plan=dict(protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,max_calls=18)
        auth=dict(authorized=True,protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,max_calls=18,max_model_loads=1,
            plan_sha256=object_sha256(plan),researcher='CPU fixture',decision_evidence='test only')
        R.admit(plan,auth)
        for update in [dict(authorized=False),dict(protocol='pmrl1-j-memory-repr18-run-v1'),dict(max_calls=36),dict(plan_sha256='wrong')]:
            invalid=dict(auth,**update)
            with self.assertRaises(Exception):R.admit(plan,invalid)

    def test_task_and_natural_terminal_cannot_be_substituted(self):
        from metacom_pm.rl1v3.journal.structured_endpoints import bind_endpoint,validate_result_binding,PROTOCOL
        payload=dict(messages=[dict(role='user',content='Synthetic field task')],input_ids=[1,2],decode={})
        request=dict(task_id='synthetic-A',logical_id='structured:synthetic-A:BASE',arm='BASE',request_id='r',
            model_input=payload,payload_sha256=object_sha256(payload),renderer_id='renderer',baseline_sha256='baseline')
        ref=dict(task_id='synthetic-A');task=dict(task_id='synthetic-A',question='Synthetic field task')
        port=dict(task_id='synthetic-A',binding_sha256='source-port',prefix_id='original-dialogue')
        endpoint=bind_endpoint(request,ref,task,port,'evaluation-sha')
        result=dict(protocol=PROTOCOL,endpoint_id=endpoint['endpoint_id'],binding=endpoint['binding'])
        validate_result_binding(endpoint,result)
        with self.assertRaises(ValueError):bind_endpoint(request,dict(task_id='synthetic-B'),task,port,'evaluation-sha')
        with self.assertRaises(ValueError):validate_result_binding(endpoint,dict(result,protocol='natural-C0-terminal'))
        changed=deepcopy(result);changed['binding']['renderer_id']='other-renderer'
        with self.assertRaises(ValueError):validate_result_binding(endpoint,changed)

    def test_run_body_identical_to_preserved_memory_guards(self):
        from metacom_pm.rl1v3.journal import memory_run
        def body(path):
            tree=ast.parse(Path(path).read_text());node=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run')
            return ast.dump(node,include_attributes=False)
        self.assertEqual(body(R.__file__),body(memory_run.__file__))


if __name__=='__main__':unittest.main()
