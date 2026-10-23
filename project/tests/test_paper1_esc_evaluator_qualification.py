from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from metacom_pm.paper1.evaluator_qualification import (
    DIMENSIONS,
    OFFICIAL_RUBRIC_DIMENSION_ORDER,
    analyze_candidate,
    assert_blind_payload,
    blocked_result,
    grouped_residual_bias,
    human_reliability,
    mean_absolute_deviation,
    quadratic_weighted_kappa,
    spearman_rho,
    validate_single_overall_adjudication,
)


ROOT = Path(__file__).resolve().parents[1]


def _scores(value: int) -> dict[str, int]:
    return {dimension: value for dimension in DIMENSIONS}


def _load_builder():
    path = ROOT / "scripts" / "paper1" / "30_build_esc_evaluator_qualification_package.py"
    spec = importlib.util.spec_from_file_location("esc_builder", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_analyzer():
    path = ROOT / "scripts" / "paper1" / "30_analyze_esc_evaluator_qualification.py"
    spec = importlib.util.spec_from_file_location("esc_analyzer", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_blind_payload_recursively_rejects_pm_and_topk_fields():
    assert_blind_payload({"blind_item_id": "x", "dialogue": ["safe"]})
    with pytest.raises(ValueError, match="forbidden fields"):
        assert_blind_payload({"dialogue": [{"metadata": {"k": 4}}]})
    with pytest.raises(ValueError, match="forbidden fields"):
        assert_blind_payload({"pm_identity": "Ours"})


def test_ordinal_metrics_have_expected_exact_and_reversed_behavior():
    exact = [0, 1, 2, 3, 4]
    reversed_values = [4, 3, 2, 1, 0]
    assert quadratic_weighted_kappa(exact, exact) == pytest.approx(1.0)
    assert quadratic_weighted_kappa(exact, reversed_values) == pytest.approx(-1.0)
    assert spearman_rho(exact, exact) == pytest.approx(1.0)
    assert spearman_rho(exact, reversed_values) == pytest.approx(-1.0)
    assert mean_absolute_deviation(exact, reversed_values) == pytest.approx(2.4)


def test_spearman_returns_none_for_constant_vector():
    assert spearman_rho([1, 1, 1], [0, 1, 2]) is None


def test_targeted_overall_adjudication_is_blind_and_item_bound():
    row = {
        "status": "ADJUDICATION_COMPLETE",
        "blind_item_id": "x",
        "dimension": "Overall",
        "adjudicated_score": 4,
        "adjudication_completed": True,
        "identity_blinded": True,
        "original_rater_scores_shown_to_adjudicator": False,
    }
    assert validate_single_overall_adjudication(row, expected_item_id="x")[
        "adjudicated_score"
    ] == 4
    with pytest.raises(ValueError, match="identity mismatch"):
        validate_single_overall_adjudication(row, expected_item_id="y")
    with pytest.raises(ValueError, match="must not see"):
        validate_single_overall_adjudication(
            {**row, "original_rater_scores_shown_to_adjudicator": True},
            expected_item_id="x",
        )


def test_two_human_reliability_requires_exact_two_rater_coverage():
    item_ids = ["a", "b", "c"]
    rows = [
        {"blind_item_id": item, "rater_id": rater, "scores": _scores(index)}
        for rater in ("R1", "R2")
        for index, item in enumerate(item_ids)
    ]
    result = human_reliability(rows, item_ids)
    assert result["rater_ids"] == ["R1", "R2"]
    assert result["items"] == 3
    assert result["major_disagreement"]["items_overall"] == 0
    assert result["per_dimension"]["Overall"]["exact_agreement_rate"] == 1.0
    assert result["per_dimension"]["Overall"]["quadratic_weighted_kappa"] == 1.0
    with pytest.raises(ValueError, match="cover every frozen"):
        human_reliability(rows[:-1], item_ids)


def test_candidate_analysis_reports_agreement_dynamic_range_bias_latency_and_cost():
    items = [{"blind_item_id": item} for item in ("a", "b", "c", "d")]
    adjudicated = [
        {"blind_item_id": item, "scores": _scores(score)}
        for item, score in zip(("a", "b", "c", "d"), (1, 3, 2, 4), strict=True)
    ]
    judge_rows = [
        {
            "candidate_id": "J",
            "blind_item_id": item,
            "scores": _scores(score),
            "parse_valid": True,
            "latency_seconds": 2.0,
            "cost_usd": 0.01,
        }
        for item, score in zip(("a", "b", "c", "d"), (1, 2, 2, 4), strict=True)
    ]
    pairs = [
        {
            "pair_id": "p1",
            "pair_kind": "natural_system_pair",
            "control_item_id": "a",
            "variant_item_id": "b",
        },
        {
            "pair_id": "p2",
            "pair_kind": "controlled_verbosity",
            "control_item_id": "c",
            "variant_item_id": "d",
        },
    ]
    report = analyze_candidate(
        candidate_id="J",
        item_rows=items,
        adjudicated_rows=adjudicated,
        candidate_rows=judge_rows,
        pair_rows=pairs,
    )
    assert report["valid_parse_rate"] == 1.0
    assert report["per_dimension"]["Overall"]["dynamic_range"] == 3
    assert report["pairwise"]["controlled_verbosity"]["winner_agreement"] == 1.0
    assert report["pairwise"]["controlled_verbosity"]["mean_variant_minus_control_overall"] == 2.0
    assert report["latency_seconds"]["mean"] == 2.0
    assert report["cost_usd"]["total"] == pytest.approx(0.04)


def test_candidate_analysis_counts_unparseable_trace_without_dropping_item():
    items = [{"blind_item_id": "a"}, {"blind_item_id": "b"}]
    adjudicated = [
        {"blind_item_id": "a", "scores": _scores(1)},
        {"blind_item_id": "b", "scores": _scores(3)},
    ]
    judge_rows = [
        {
            "candidate_id": "J",
            "blind_item_id": "a",
            "scores": _scores(1),
            "parse_valid": True,
            "latency_seconds": 1.0,
            "cost_usd": 0.0,
        },
        {
            "candidate_id": "J",
            "blind_item_id": "b",
            "scores": {dimension: None for dimension in DIMENSIONS},
            "parse_valid": False,
            "latency_seconds": 1.0,
            "cost_usd": 0.0,
        },
    ]
    report = analyze_candidate(
        candidate_id="J",
        item_rows=items,
        adjudicated_rows=adjudicated,
        candidate_rows=judge_rows,
        pair_rows=[],
    )
    assert report["valid_parse_rate"] == 0.5
    assert report["per_dimension"]["Overall"]["valid_items"] == 1


def test_grouped_residual_bias_joins_hidden_group_only_after_scoring():
    reference = {"a": _scores(2), "b": _scores(2)}
    candidate = {"a": _scores(3), "b": _scores(1)}
    result = grouped_residual_bias(
        reference_scores=reference,
        candidate_scores=candidate,
        item_groups={"a": "family_a", "b": "family_b"},
    )
    assert result["mean_candidate_minus_human_by_group"] == {
        "family_a": 1.0,
        "family_b": -1.0,
    }
    assert result["max_minus_min_group_residual"] == 2.0


def test_controlled_probe_keeps_identical_semantic_atoms_within_each_pair():
    builder = _load_builder()
    items, audit, pairs = builder._controlled_items()
    assert len(items) == 18
    assert len(pairs) == 9
    audit_by_id = {row["blind_item_id"]: row for row in audit}
    item_by_id = {row["blind_item_id"]: row for row in items}
    topical_anchors = {
        "work": ({"work"}, {"task", "workload"}),
        "friend": ({"friend"}, {"argument", "friend"}),
        "appointment": ({"appointment"}, {"tomorrow", "appointment"}),
    }
    assert {row["pair_kind"] for row in pairs} == {
        "controlled_verbosity",
        "controlled_redundant_suggestions",
        "controlled_format_list_style",
    }
    for pair in pairs:
        left = audit_by_id[pair["control_item_id"]]
        right = audit_by_id[pair["variant_item_id"]]
        assert left["semantic_atoms_sha256"] == right["semantic_atoms_sha256"]
        assert left["probe_factor"] == right["probe_factor"]
        assert left["probe_topic"] == right["probe_topic"]
        assert left["context_sha256"] == right["context_sha256"]
        assert left["probe_condition"] == "control"
        assert right["probe_condition"] == "variant"
        topic = left["probe_topic"]
        context_words, response_words = topical_anchors[topic]
        control_dialogue = item_by_id[pair["control_item_id"]]["dialogue"]
        variant_dialogue = item_by_id[pair["variant_item_id"]]["dialogue"]
        assert control_dialogue[0] == variant_dialogue[0]
        assert any(word in control_dialogue[0].lower() for word in context_words)
        assert any(word in control_dialogue[1].lower() for word in response_words)
        assert any(word in variant_dialogue[1].lower() for word in response_words)


def test_human_instrument_binds_official_humanoid_and_skillful_by_name():
    builder = _load_builder()
    prompts = [f"PROMPT_{dimension}" for dimension in OFFICIAL_RUBRIC_DIMENSION_ORDER]
    instrument = builder._human_instrument(prompts)
    by_dimension = {
        row["paper_dimension"]: row["official_rubric_text"]
        for row in instrument["dimensions"]
    }
    assert instrument["protocol"] == "pm-paper1-esc-evaluator-human-instrument-v2"
    assert by_dimension["Humanoid"] == "PROMPT_Humanoid"
    assert by_dimension["Skillful"] == "PROMPT_Skillful"
    assert instrument["correction"]["raw_submissions_are_immutable"] is True


def test_v1_human_submission_normalization_only_swaps_two_rubric_labels():
    path = ROOT / "scripts" / "paper1" / "31_ingest_esc_evaluator_human_reviews.py"
    spec = importlib.util.spec_from_file_location("esc_human_ingest", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    item = {"blind_item_id": "x", "dialogue": ["User: x", "AI assistant: y"]}
    payload = {
        "meta": {"item_count": 1, "dimensions": list(DIMENSIONS)},
        "submission": [
            {
                "blind_item_id": "x",
                "Fluency": 0,
                "Expression": 1,
                "Empathy": 2,
                "Information": 3,
                "Skillful": 1,
                "Humanoid": 4,
                "Overall": 2,
                "notes": "kept",
                "human_completed": True,
            }
        ],
    }
    rows = module.normalize_submission(payload, rater_id="RATER_A", frozen_items={"x": item})
    assert rows[0]["scores"] == {
        "Fluency": 0,
        "Expression": 1,
        "Empathy": 2,
        "Information": 3,
        "Skillful": 4,
        "Humanoid": 1,
        "Overall": 2,
    }
    assert rows[0]["notes"] == "kept"
    assert rows[0]["normalization"]["judgment_values_changed"] is False


def test_corrected_instrument_preserves_rubric_text_and_repairs_only_names():
    path = ROOT / "scripts" / "paper1" / "31_ingest_esc_evaluator_human_reviews.py"
    spec = importlib.util.spec_from_file_location("esc_human_ingest_instrument", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    historical = {
        "source": {"score_py_sha256": "x"},
        "blind_to": ["PM identity"],
        "dimensions": [
            {"paper_dimension": dimension, "official_rubric_text": f"RAW_{dimension}"}
            for dimension in DIMENSIONS
        ],
    }
    corrected = module.corrected_instrument(historical)
    by_dimension = {
        row["paper_dimension"]: row["official_rubric_text"]
        for row in corrected["dimensions"]
    }
    assert by_dimension["Humanoid"] == "RAW_Skillful"
    assert by_dimension["Skillful"] == "RAW_Humanoid"
    assert by_dimension["Empathy"] == "RAW_Empathy"


def test_blocked_result_never_fabricates_a_winner_or_outcome():
    result = blocked_result(blockers=["no GPU"], evidence={"judge_calls": 0})
    assert result["status"] == "BLOCKED"
    assert result["recommendation"] is None
    assert result["formal_ESC_Eval"] is False
    assert result["formal_outcome_calls"] == 0


def test_analyzer_scope_keeps_official_anchor_without_unfreezing_proxies():
    analyzer = _load_analyzer()
    registry = {
        "candidates": [
            {"candidate_id": "ESC_RANK", "status": "FROZEN", "identity_sha256": "x"},
            {"candidate_id": "QWEN_GENERAL_JUDGE", "status": "BLOCKED", "identity_sha256": None},
        ]
    }
    assert analyzer._scoped_candidates(registry, "ESC_RANK") == [registry["candidates"][0]]
    assert analyzer._scoped_candidates(registry, None) == registry["candidates"]
    with pytest.raises(RuntimeError, match="absent"):
        analyzer._scoped_candidates(registry, "MISSING")
