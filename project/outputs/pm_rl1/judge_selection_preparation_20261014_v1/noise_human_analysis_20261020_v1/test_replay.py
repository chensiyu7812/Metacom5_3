import copy
import unittest
from fractions import Fraction
import replay


class ReplayChecks(unittest.TestCase):
    def test_zero_is_tie_not_unknown(self):
        self.assertEqual(replay.direction(Fraction(0)), "tie")
        self.assertEqual(replay.direction(Fraction(-1, 8)), "B")

    def test_cost_not_in_human_quality_comparison(self):
        # Same quality and different acquisition cost: human quality remains tie.
        self.assertEqual(replay.direction(Fraction(0)), "tie")
        self.assertEqual(replay.direction(Fraction(0) - Fraction(193, 40960)), "B")

    def test_duplicates_and_wrong_sides_rejected(self):
        h, p = replay.read(replay.HUMAN), replay.read(replay.PACKET / "packet_metadata.json")
        bad = copy.deepcopy(h)
        bad["answers"][1] = copy.deepcopy(bad["answers"][0])
        with self.assertRaises(AssertionError):
            replay.validate_submission(bad, p)
        bad = copy.deepcopy(h)
        bad["answers"][0]["left_reply_identity"] = bad["answers"][0]["right_reply_identity"]
        with self.assertRaises(AssertionError):
            replay.validate_submission(bad, p)

    def test_unknown_retained_outside_agreement_denominator(self):
        rows = [{"human_direction": "unknown", "mean": "A"},
                {"human_direction": "tie", "mean": None},
                {"human_direction": "A", "mean": "A"}]
        s = replay.summarize(rows, "mean")
        self.assertEqual((s["human_unknown"], s["missing_measurement"], s["agreement"]), (1, 1, 1))
        self.assertEqual(s["complete_comparable_pairs"], 1)

    def test_actual_join_and_preservation_repeatable(self):
        a, b = replay.analyze(), replay.analyze()
        self.assertEqual(a, b)
        self.assertEqual(a["new_distribution"], {"tie": 6, "A": 1})
        self.assertEqual([a["new_seven_readout"][k]["agreement"]
                          for k in ("single_1", "single_3", "mean_12", "mean_34")], [6, 7, 4, 4])
        p3 = next(r for r in a["pairs"] if r["pair_id"] == "P03")
        self.assertEqual(p3["human_direction"], "tie")
        self.assertEqual(p3["mean_U_A_minus_B"], ["-3/8", "1/8"])
        self.assertEqual(a["new_model_calls"], 0)


if __name__ == "__main__":
    unittest.main()
