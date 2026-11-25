"""Synthetic regressions for read-only policies, explicit diagnostics and costs."""
import json
import unittest
from metacom_pm.rl1v3.journal.structured_analysis import choose,policy_metrics,parse_diagnostics
from metacom_pm.rl1v3.journal.structured_format_diagnostic import extract

class Analysis(unittest.TestCase):
    def test_visible_rule_uses_only_public_text(self):
        row=dict(model_input=dict(messages=[dict(content='Question\nVisible evidence (reported synthetic): sample')]))
        self.assertEqual(choose('visible_evidence_rule',row),'BASE')
        row['model_input']['messages'][0]['content']='Question only'
        row['gold']='irrelevant';row['task_success']=True
        self.assertEqual(choose('visible_evidence_rule',row),'RAW')
        self.assertEqual(choose('always_BASE',row),'BASE');self.assertEqual(choose('always_RAW',row),'RAW')

    def test_physical_cost_not_rebilled_on_logical_reuse(self):
        row=dict(status='development_scored',request_id='same-physical',output_present=True,
            arm='RAW',score=dict(task_success=True),cost=dict(input_tokens=101,output_tokens=13,generation_seconds=2.5))
        m=policy_metrics([row,dict(row)])
        self.assertEqual(m['successes'],2);self.assertEqual(m['physical_requests'],1)
        self.assertEqual((m['input_tokens'],m['output_tokens'],m['generation_seconds']),(101,13,2.5))

    def test_fences_are_not_silently_valid_json(self):
        ref=dict(value='x',required_literal='synthetic',evidence=dict(text='synthetic',speaker='seeker',reported_date='2030-01-01'))
        text='```json\n{"value":"x"}\n```'
        self.assertFalse(parse_diagnostics(text,ref,'synthetic')['strict_json'])
        self.assertEqual(extract(text)['body'],'{"value":"x"}')

    def test_diagnostic_preserves_inner_bytes_and_outside_text(self):
        text='unparsed prefix\n```json\n {"quote":"wrong ‘quote’"}\n```\ntrailer'
        x=extract(text)
        self.assertEqual(x['body'],' {"quote":"wrong ‘quote’"}')
        self.assertEqual(x['outside_text'],'unparsed prefix\n\ntrailer')
        self.assertIsNone(extract(text+'\n```json\n{}\n```')['body'])

    def test_missing_outputs_are_not_zero_quality(self):
        row=dict(status='pending',request_id='missing',output_present=False,arm='BASE',score=None,
            cost=dict(input_tokens=0,output_tokens=0,generation_seconds=None))
        m=policy_metrics([row]);self.assertIsNone(m['success_rate']);self.assertEqual(m['pending_or_technical'],1)

if __name__=='__main__':unittest.main()
