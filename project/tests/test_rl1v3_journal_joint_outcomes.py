"""Synthetic outcome arithmetic/privacy regressions; no semantic gold or GPU."""
import unittest
from metacom_pm.rl1v3.journal.joint_outcomes import conjunction,interaction,metrics,paired_difference
from metacom_pm.rl1v3.journal.joint_policies import visible_rule
from metacom_pm.rl1v3.journal.joint_results import validate_support_review

class Outcomes(unittest.TestCase):
    def test_uncertain_not_filled_with_zero(self):
        self.assertEqual(conjunction([[1,1],[0,1]]),[0,1])
        self.assertEqual(conjunction([[0,0],[0,1]]),[0,0])
        self.assertIsNone(conjunction([None,[0,0]]))

    def test_interaction_preserves_interval(self):
        self.assertEqual(interaction(dict(STOP=[0,0],MS=[1,1],RS=[0,1],MS_RS=[1,1])),[-1,0])
        self.assertIsNone(interaction(dict(STOP=None,MS=[1,1],RS=[0,1],MS_RS=[1,1])))

    def test_same_endpoint_uncertainty_cancels_in_policy_difference(self):
        self.assertEqual(paired_difference([0,1],[0,1],same_endpoint=True),[0,0])
        self.assertEqual(paired_difference([0,1],[0,1]),[-1,1])
        self.assertIsNone(paired_difference(None,None,same_endpoint=True))
        with self.assertRaises(ValueError):paired_difference([0,1],[1,1],same_endpoint=True)

    def test_physical_cost_not_recounted(self):
        row=dict(request_id='same',output_present=True,fact_interval=[1,1],support_interval=[0,1],joint_interval=[0,1],
            cost=dict(input_tokens=101,output_tokens=7,generation_seconds=2.0,path_cpu_ms=3.0))
        result=metrics([row,dict(row)])
        self.assertEqual(result['joint']['lower_count'],0);self.assertEqual(result['joint']['upper_count'],2)
        self.assertEqual(result['cost']['input_tokens'],101);self.assertEqual(result['cost']['physical_outputs'],1)

    def test_policy_has_only_query_argument(self):
        self.assertEqual(visible_rule('Earlier, please draft one optional step.'),'MS_RS')
        self.assertEqual(visible_rule('Earlier, I do not want advice. Please draft one line.'),'MS')
        self.assertEqual(visible_rule('Please suggest one practical step.'),'RS')
        self.assertEqual(visible_rule('Hello.'),'STOP')

    def test_wrong_review_identity_rejected_before_content(self):
        response=dict(logical_id='actual');review=dict(logical_id='other')
        with self.assertRaises(ValueError):validate_support_review(review,response,{})

if __name__=='__main__':unittest.main()
