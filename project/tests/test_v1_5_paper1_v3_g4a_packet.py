from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from metacom_pm.v1_5_g4_nonexclusive_suitability_packet import (  # noqa: E402
    build_fresh_controls,
    select_cases,
)


def _jsonl(path: Path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


class G4APacketTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.design = json.loads(
            (ROOT / "data/pm_v1_5_contracts/paper1_v3_g4_nonexclusive_suitability_design_v1.json").read_text(encoding="utf-8")
        )
        cls.diagnostics = _jsonl(
            ROOT
            / "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811/candidate_surface_diagnostics_unlabeled.jsonl"
        )
        cls.selected, cls.shared = select_cases(cls.diagnostics)

    def test_exact_component_denominators(self) -> None:
        counts = {
            component: sum(row["component"] == component for row in self.selected)
            for component in ("MP", "MS", "ME")
        }
        self.assertEqual(counts, {"MP": 204, "MS": 204, "ME": 99})

    def test_all_three_shared_states_are_selected_three_times(self) -> None:
        selected = {(row["state_id"], row["component"]) for row in self.selected}
        self.assertEqual(len(self.shared), 14)
        for state_id in self.shared.values():
            self.assertTrue(
                all((state_id, component) in selected for component in ("MP", "MS", "ME"))
            )

    def test_all_ms_proxy_hard_negative_surfaces_are_retained(self) -> None:
        selected = {row["state_id"] for row in self.selected if row["component"] == "MS"}
        flagged = {
            row["state_id"]
            for row in self.diagnostics
            if row["component"] == "MS"
            and row["candidate_present"]
            and (row.get("low_information_rank1") or row.get("exact_or_containment_current_echo"))
        }
        self.assertTrue(flagged <= selected)

    def test_fresh_controls_have_three_class_component_balance(self) -> None:
        control_a, control_b, key = build_fresh_controls(self.design)
        self.assertEqual(len(control_a), 36)
        self.assertEqual(len(control_b), 36)
        self.assertEqual(len(key), 36)
        for component in ("MP", "MS", "ME"):
            decisions = [row["gold_decision"] for row in key if row["component"] == component]
            self.assertEqual(decisions.count("SUITABLE"), 5)
            self.assertEqual(decisions.count("NOT_SUITABLE"), 5)
            self.assertEqual(decisions.count("SEMANTIC_ABSTAIN"), 2)

    def test_controls_do_not_emit_four_axis_fields(self) -> None:
        control_a, _control_b, _key = build_fresh_controls(self.design)
        text = json.dumps(control_a, ensure_ascii=False)
        for retired in (
            "current_target_fit",
            "specific_increment_available",
            "component_minimum_possible_now",
            "current_boundary_permits",
        ):
            self.assertNotIn(retired, text)

    def test_mp_positive_controls_do_not_repeat_profile_value(self) -> None:
        control_a, _control_b, key = build_fresh_controls(self.design)
        gold_by_id = {row["reviewer_a_item_id"]: row for row in key}
        for item in control_a:
            gold = gold_by_id[item["review_item_id"]]
            if item["component"] != "MP" or gold["gold_decision"] != "SUITABLE":
                continue
            visible = " ".join(span["content"].lower() for span in item["visible_spans"])
            candidate = item["candidate_spans"][0]["content"].split(":", 1)[-1].strip().lower()
            self.assertNotIn(candidate, visible)


if __name__ == "__main__":
    unittest.main()
