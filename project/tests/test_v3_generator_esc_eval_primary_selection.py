from __future__ import annotations

import json
from pathlib import Path


AUTHORITY = Path(__file__).resolve().parents[1] / "data" / "v3_authority"


def _plan() -> dict:
    return json.loads((AUTHORITY / "generator_esc_eval_primary_selection_v1.json").read_text(encoding="utf-8"))


def test_esc_eval_official_seven_dimensions_and_human_primary_are_restored() -> None:
    plan = _plan()
    anchor = plan["official_anchor"]
    assert anchor["official_high_quality_cards"] == {"total": 655, "english": 331, "chinese": 324}
    assert anchor["official_dimensions_0_to_4"] == [
        "Fluency", "Expression", "Empathy", "Information", "Humanoid", "Skill", "Overall"
    ]
    assert "Human annotators" in anchor["paper_primary_evaluation"]
    assert plan["metric_and_decision_hierarchy"]["official_primary"].startswith("Overall")


def test_esc_eval_development_review_is_complete_and_uses_dialogue_as_unit() -> None:
    plan = _plan()
    development = plan["development_selection"]
    assert set(development["candidate_dialogues"].values()) == {24}
    assert sum(development["candidate_dialogues"].values()) == 72
    assert development["assignments"] == 144
    assert development["dimension_ratings"] == 1008
    assert "role card/dialogue" in development["statistical_unit"]


def test_adapted_judges_cannot_replace_or_control_esc_eval_selection() -> None:
    plan = _plan()
    roles = plan["role_of_other_evaluators"]
    assert "cannot replace" in roles["esc_judge_eia"]
    assert "descriptive" in plan["development_selection"]["official_esc_rank_result"]
    assert plan["metric_and_decision_hierarchy"]["no_weighted_quality_risk_cost_composite"] is True
    assert plan["protocol_repair_boundary"]["exact_official_reproduction"] is False
