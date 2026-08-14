from __future__ import annotations

import importlib.util
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = (
    ROOT
    / "scripts/v1_5/204l_validate_paper1_v3_g4_nonexclusive_suitability_design_v1_5.py"
)


def _load_validator():
    spec = importlib.util.spec_from_file_location("g4_design_validator", SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError("could not load G4 design validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class G4NonexclusiveSuitabilityDesignTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.report = _load_validator().validate()

    def test_design_passes_all_machine_checks(self) -> None:
        self.assertEqual(
            self.report["status"],
            "G4_NONEXCLUSIVE_SUITABILITY_DESIGN_PASS_G4A_PACKET_PHASE_MAY_BE_DESIGNED",
        )
        self.assertEqual(self.report["failed_checks"], [])

    def test_three_components_are_not_one_choice(self) -> None:
        checks = self.report["checks"]
        self.assertTrue(checks["decision_grain_is_nonexclusive"])
        self.assertTrue(checks["all_three_co_presence_is_preserved"])

    def test_checklist_is_not_four_training_labels(self) -> None:
        self.assertTrue(
            self.report["checks"]["checklist_does_not_recreate_four_labels"]
        )

    def test_packet_has_grouped_bidirectional_capacity(self) -> None:
        self.assertEqual(self.report["observed_capacity"]["MP_groups"], 17)
        self.assertEqual(self.report["observed_capacity"]["MS_groups"], 17)
        self.assertEqual(self.report["observed_capacity"]["ME_cap7_capacity"], 99)

    def test_design_creates_no_labels_or_execution(self) -> None:
        self.assertEqual(self.report["api_calls"], 0)
        self.assertEqual(self.report["labels_created"], 0)
        self.assertFalse(self.report["packet_materialization_authorized"])


if __name__ == "__main__":
    unittest.main()
