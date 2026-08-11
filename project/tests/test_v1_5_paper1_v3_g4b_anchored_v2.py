from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from metacom_pm.v1_5_g4b_anchored_review_v2 import (  # noqa: E402
    WORKED_ANCHORS,
    build_fresh_v2_controls,
    prompt_messages,
)


class G4BAnchoredV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.design = json.loads(
            (ROOT / "data/pm_v1_5_contracts/paper1_v3_g4_nonexclusive_suitability_design_v1.json").read_text()
        )
        cls.a, cls.b, cls.gold = build_fresh_v2_controls(cls.design)

    def test_fresh_control_denominators_and_balance(self) -> None:
        self.assertEqual((len(self.a), len(self.b), len(self.gold)), (36, 36, 36))
        for component in ("MP", "MS", "ME"):
            values = [row["gold_decision"] for row in self.gold if row["component"] == component]
            self.assertEqual(values.count("SUITABLE"), 5)
            self.assertEqual(values.count("NOT_SUITABLE"), 5)
            self.assertEqual(values.count("SEMANTIC_ABSTAIN"), 2)

    def test_provider_prompt_contains_component_specific_worked_anchors(self) -> None:
        for component in ("MP", "MS", "ME"):
            item = next(row for row in self.a if row["component"] == component)
            system = prompt_messages(item, "REVIEWER_A")[0]["content"]
            self.assertIn(f"WORKED TRAINING ANCHORS FOR {component}", system)
            for decision in ("SUITABLE", "NOT_SUITABLE", "SEMANTIC_ABSTAIN"):
                self.assertIn(decision, system)
            self.assertEqual(len(WORKED_ANCHORS[component]), 3)

    def test_prompt_preserves_nonexclusive_component_decisions(self) -> None:
        system = prompt_messages(self.a[0], "REVIEWER_A")[0]["content"]
        self.assertIn("Multiple components at the same state may all be SUITABLE", system)
        self.assertIn("never output four axis labels", system)


if __name__ == "__main__":
    unittest.main()
