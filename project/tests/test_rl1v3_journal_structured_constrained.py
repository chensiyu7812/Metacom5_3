"""Synthetic admission/format-only invariants, without real source or gold."""
import unittest,tempfile,json
from pathlib import Path
from unittest.mock import patch
from metacom_pm.rl1v3.journal.structured_constrained import SCHEMA
from metacom_pm.rl1v3.journal.structured_constrained_run import admit,constrained_request_id,RUN_PROTOCOL,JOB_KIND
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.generator import limited_run as L
from metacom_pm.rl1v3.journal.structured_constrained_results import diagnose

class Constrained(unittest.TestCase):
    def test_schema_has_no_answer_enumeration(self):
        self.assertEqual(set(SCHEMA['properties']),set(SCHEMA['required']))
        for value in SCHEMA['properties'].values():self.assertEqual(set(value),{'type'})
        self.assertFalse(SCHEMA['additionalProperties'])
    def test_new_id_changes_with_constraint_and_payload(self):
        self.assertNotEqual(constrained_request_id({'payload_sha256':'x'},'a'),constrained_request_id({'payload_sha256':'x'},'b'))
        self.assertNotEqual(constrained_request_id({'payload_sha256':'x'},'a'),constrained_request_id({'payload_sha256':'y'},'a'))
    def test_approvals_cannot_transfer(self):
        p={'fake_plan':'synthetic'}
        good=dict(authorized=True,protocol=RUN_PROTOCOL,job_kind=JOB_KIND,plan_sha256=object_sha256(p),
            max_calls=18,max_model_loads=1,researcher='synthetic-test',decision_evidence='synthetic-only')
        admit(p,good)
        for update in ({'authorized':False},{'protocol':'pmrl1-j-structured-paired-run-v1'},
            {'job_kind':'JOURNAL_STRUCTURED_PAIRED'},{'max_calls':36},{'max_model_loads':2},{'plan_sha256':'other'}):
            with self.assertRaises(Exception):admit(p,dict(good,**update))
    def test_original_claim_guard_forbids_duplicate_diagnostic_calls(self):
        with tempfile.TemporaryDirectory() as td:
            root=Path(td);(root/'tokkio_projects/pmrl1-validation/limited-g0e-claims').mkdir(parents=True)
            plan=dict(job_kind=JOB_KIND,requests_sha256='synthetic',ordered_request_ids=['synthetic'],baseline_sha256='synthetic')
            with patch.object(L,'DATA',root):
                L.claim_request_set(plan,{'authorized':True,'synthetic_test':True})
                with self.assertRaises(FileExistsError):L.claim_request_set(plan,{'authorized':True,'synthetic_test':'different-receipt'})
    def test_parse_failure_is_not_semantic_failure_vector(self):
        result=diagnose('```json\n{}\n```',{},arm='BASE',delivered_text='',technical_status='eos')
        self.assertEqual(result['format_status'],'fail')
        self.assertFalse(result['semantic_fields_assessed'])
        self.assertTrue(all(x is None for x in result['field_diagnostics'].values()))
    def test_original_semantic_failure_survives_valid_json(self):
        ref=dict(value='booked',required_delivered_quotes=['reserved a place'],required_literal='reserved',
            evidence=dict(text='I reserved a place.',speaker='seeker',reported_date='2001-01-01'))
        answer=dict(value='attended',certainty='supported',quote='reserved a place',speaker='seeker',reported_date='2001-01-01')
        result=diagnose(json.dumps(answer),ref,arm='RAW',delivered_text=ref['evidence']['text'],technical_status='eos')
        self.assertEqual(result['format_status'],'pass');self.assertFalse(result['strict_score']['task_success'])
        self.assertFalse(result['field_diagnostics']['value_correct']);self.assertTrue(result['field_diagnostics']['speaker_source_match'])
    def test_incomplete_remains_unassessed(self):
        result=diagnose('{',{},arm='BASE',delivered_text='',technical_status='length')
        self.assertIsNone(result['strict_score']);self.assertEqual(result['format_status'],'unassessed')
    def test_compliant_unknown_does_not_create_source_attribution_errors(self):
        ref=dict(value='booked',required_delivered_quotes=['reserved a place'],required_literal='reserved',
            evidence=dict(text='I reserved a place.',speaker='seeker',reported_date='2001-01-01'))
        answer=dict(value='unknown',certainty='unknown',quote='',speaker='unknown',reported_date=None)
        result=diagnose(json.dumps(answer),ref,arm='BASE',delivered_text='',technical_status='eos')
        self.assertFalse(result['strict_score']['task_success'])
        self.assertTrue(result['strict_score']['epistemic_compliance'])
        fields=result['field_diagnostics']
        self.assertFalse(fields['value_correct'])
        self.assertTrue(fields['unknown_contract'])
        self.assertTrue(fields['compliant_abstention_without_required_evidence'])
        for name in ('quote_exact_source_substring','quote_supplied','required_literal_in_quote',
            'speaker_source_match','reported_date_source_match'):
            self.assertIsNone(fields[name])

if __name__=='__main__':unittest.main()
