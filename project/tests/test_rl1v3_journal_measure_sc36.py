"""Finite synthetic technical-accounting tests; no generation or real source."""
import importlib.util
from pathlib import Path
import unittest

path=Path(__file__).parents[1]/'scripts/rl1v3/journal_measure_sc36.py'
spec=importlib.util.spec_from_file_location('measure_sc36_tested',path)
M=importlib.util.module_from_spec(spec);spec.loader.exec_module(M)

class Measurement(unittest.TestCase):
    def setUp(self):
        self.row={'model_input':{'input_ids':[7],'decode':{'max_new_tokens':320,'eos_token_id':[1,106,50]}}}
        self.output=dict(token_ids=[9,106],text='synthetic',finish_reason='eos',input_tokens=1,seconds=0.2,
            constraint_measurement=dict(mask_calls=2,cpu_mask_seconds=0.05))
    def test_nested_timing_and_exact_token_length(self):
        r=M.output_cost(self.row,self.output,constrained=True)
        self.assertEqual(r['output_tokens'],2);self.assertEqual(r['generation_seconds'],0.2)
        self.assertEqual(r['grammar_cpu_mask_seconds'],0.05)
    def test_mask_call_mismatch_rejected(self):
        o=dict(self.output,constraint_measurement=dict(mask_calls=3,cpu_mask_seconds=0.05))
        with self.assertRaises(ValueError):M.output_cost(self.row,o,constrained=True)
    def test_nested_cpu_time_cannot_exceed_generation(self):
        o=dict(self.output,constraint_measurement=dict(mask_calls=2,cpu_mask_seconds=0.3))
        with self.assertRaises(ValueError):M.output_cost(self.row,o,constrained=True)
    def test_original_outputs_need_no_new_mask_fields(self):
        o={k:v for k,v in self.output.items() if k!='constraint_measurement'}
        self.assertEqual(M.output_cost(self.row,o,constrained=False)['output_tokens'],2)
        with self.assertRaises(ValueError):M.output_cost(self.row,o,constrained=True)

if __name__=='__main__':unittest.main()
