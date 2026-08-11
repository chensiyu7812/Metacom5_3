from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import runpy
from types import SimpleNamespace

import pytest

from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate
from metacom_pm.v1_5_v5_3_typed_response_program import build_typed_response_program


ROOT = Path(__file__).resolve().parents[1]


def _rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def test_actual_outcome_transition_preserves_sixteen_action_architecture() -> None:
    contract = json.loads((ROOT / "data/pm_v1_5_contracts/v5_4_actual_outcome_learnability_transition_v1.json").read_text())
    assert contract["current_authorization"]["effect_manifest_and_cost_preflight"] is True
    assert contract["current_authorization"]["live_response_effect_calls"] is False
    assert contract["development_effect_feasibility"]["states"] == 96
    assert contract["development_effect_feasibility"]["generator_calls"] == 576
    assert contract["why_assignment_prediction_is_retired_as_a_hard_gate"]["correct_value_evidence"] == "randomized same-state requested-action outcomes"


def test_full_dialogue_feature_surface_is_complete_and_outcome_blind() -> None:
    directory = ROOT / "outputs/pm_v1_5_v5_4_full_dialogue_feature_surface_20260810"
    report = json.loads((directory / "report_final.json").read_text())
    rows = _rows(directory / "feature_surface_private_ids_not_model_features.jsonl")
    assert report["status"] == "FULL_DIALOGUE_FEATURE_SURFACE_FINAL_PASS_EFFECT_MANIFEST_MAY_BE_BUILT"
    assert len(rows) == 96
    assert Counter(row["component_split_head_only"] for row in rows) == Counter({"MP": 24, "MS": 24, "ME": 24, "RS": 24})
    assert all(not row["construction_assignment_present"] for row in rows)
    assert all(not row["response_effect_or_oracle_present"] for row in rows)
    assert all(len(row["model_feature_values"]) == 16 for row in rows)


def test_effect_manifest_binds_pairs_sources_candidates_and_seeds() -> None:
    directory = ROOT / "outputs/pm_v1_5_v5_4_development_effect_manifest_20260810"
    report = json.loads((directory / "report.json").read_text())
    rows = _rows(directory / "effect_group_manifest_private.jsonl")
    assert report["status"] == "DEVELOPMENT_EFFECT_MANIFEST_FROZEN_MEASUREMENT_AND_COST_PREFLIGHT_PENDING"
    assert len(rows) == 96
    assert Counter(row["component"] for row in rows) == Counter({"MP": 24, "MS": 24, "ME": 24, "RS": 24})
    assert set(Counter(row["pair_id_split_binding"] for row in rows).values()) == {2}
    cluster_folds: dict[str, set[int]] = defaultdict(set)
    for row in rows:
        cluster_folds[row["source_cluster_id_split_binding"]].add(row["outer_fold"])
        assert len(set(row["paired_generator_seeds"])) == 3
        assert row["construction_assignment_present"] is False
        assert row["response_effect_or_oracle_present"] is False
        candidate = TypedResourceCandidate(**row["actual_rank1_candidate"])
        build_typed_response_program(
            requested_action_id=row["on_action_id"],
            current_goal="Respond supportively to the latest user message using only visible authorized information.",
            current_user_id=row["current_owner_id"],
            candidates={row["component"]: candidate},
            expected_execution_candidate_ids={row["component"]: candidate.resource_id},
        )
    assert all(len(folds) == 1 for folds in cluster_folds.values())
    assert "evoemo_shared_p13_p18" in cluster_folds


def test_canary_runner_persists_raw_structured_reply_before_guard(tmp_path: Path) -> None:
    module = runpy.run_path(str(ROOT / "scripts/v1_5/159l_run_v5_4_effect_canary_generation_v1_5.py"))
    schema = module["GeneratorSchema"]

    class FakeClient:
        def chat(self, messages, **kwargs):
            return (
                SimpleNamespace(
                    request_hash="a" * 64,
                    usage={"prompt_tokens": 10, "completion_tokens": 5},
                    latency_ms=1.0,
                    normalized_finish_reason="stop",
                ),
                schema(reply="raw reply", used_evidence_ids=[], realized_response_act="reflection"),
            )

    raw_rows: dict[str, dict] = {}
    wrapper = module["RawPersistingClient"](FakeClient(), call_key="call-1", seed=7, raw_rows=raw_rows, out_dir=tmp_path)
    _result, parsed = wrapper.chat([{"role": "user", "content": "hello"}], response_schema=schema)
    assert parsed.reply == "raw reply"
    saved = _rows(tmp_path / "raw_provider_attempts_before_guard.jsonl")
    assert saved[0]["raw_structured_provider_reply_before_guard"]["reply"] == "raw reply"


def test_transport_continuation_replaces_only_no_completion_calls() -> None:
    base = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_generation_20260810"
    continuation = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_transport_continuation_20260810"
    base_rows = _rows(base / "generator_arm_results.jsonl")
    raw_rows = _rows(base / "raw_provider_attempts_before_guard.jsonl")
    continued = _rows(continuation / "continuation_results.jsonl")
    merged = _rows(continuation / "merged_generator_arm_results_for_measurement.jsonl")
    successful_base = {row["call_id"] for row in raw_rows if row["succeeded"]}
    continued_ids = {row["original_call_id"] for row in continued}
    assert len(base_rows) == len(merged) == 48
    assert len(continued) == 7
    assert continued_ids.isdisjoint(successful_base)
    assert all(row["status"] == "clean" for row in continued)
    assert all(row["status"] == "clean" for row in merged)
    assert all(row["requested_action_id"] == row["realized_action_id"] for row in merged)


def test_canary_measurement_gate_does_not_masquerade_as_pm_pass() -> None:
    gate = json.loads((ROOT / "data/pm_v1_5_contracts/v5_4_effect_canary_measurement_gate_v1.json").read_text())
    assert gate["status"] == "FROZEN_BEFORE_DUAL_MEASUREMENT_RESULTS"
    assert "not a PM passing score" in gate["scope"]
    assert gate["role_separation"]["disagreement"].startswith("UNRESOLVED")
    assert "always-off" in gate["three_distinct_decisions"]["final_pm_pass"]
    assert gate["final_pm_pass_rule_freezing"]["sealed_evaluation"].startswith("never tune")


def test_canary_measurement_prompts_and_literal_validation_are_role_separated() -> None:
    module = runpy.run_path(str(ROOT / "scripts/v1_5/160l_run_v5_4_effect_canary_dual_measurement_v1_5.py"))
    canary, generated = module["grouped_generation"]()
    group_id = sorted(canary)[0]
    item = canary[group_id]
    group_generation = generated[group_id]

    forward = module["quality_messages"](item, group_generation, reverse=False, reviewer="REVIEWER_A")
    reverse = module["quality_messages"](item, group_generation, reverse=True, reviewer="REVIEWER_A")
    assert "Do not subtract risk" in forward[0]["content"]
    forward_payload = json.loads(forward[1]["content"])
    reverse_payload = json.loads(reverse[1]["content"])
    assert forward_payload["blinded_response_pairs"][0]["response_A"] == reverse_payload["blinded_response_pairs"][0]["response_B"]

    quality_schema = module["QualityBatch"]
    quality_items = []
    for index in range(1, 4):
        response_a = group_generation[f"r{index}_ON"]["final_reply"]
        response_b = group_generation[f"r{index}_OFF"]["final_reply"]
        quality_items.append({
            "replicate_id": f"r{index}",
            "preferred_response": "TIE",
            "goal_advance_delta_a_minus_b": 0,
            "emotional_attunement_delta_a_minus_b": 0,
            "specific_positive_support_delta_a_minus_b": 0,
            "clarity_naturalness_delta_a_minus_b": 0,
            "response_a_excerpt": response_a[: min(12, len(response_a))],
            "response_b_excerpt": response_b[: min(12, len(response_b))],
            "concise_reason": "test"
        })
    parsed = quality_schema(effect_group_id=group_id, replicates=quality_items)
    module["validate_quality"](parsed, item, group_generation, reverse=False)


def test_canary_measurement_v4_span_ids_are_exact_and_schema_complete() -> None:
    module = runpy.run_path(str(ROOT / "scripts/v1_5/163l_run_v5_4_effect_canary_dual_measurement_v4_v1_5.py"))
    for schema_name in ("QualityBatchSpan", "RiskBatchSpan", "FunctionBatchSpan"):
        assert module[schema_name].model_json_schema()["additionalProperties"] is False
    text = "First exact sentence. Second exact sentence!"
    spans = module["span_map"](text, "A")
    assert spans == {"A0": "First exact sentence.", "A1": "Second exact sentence!"}
    assert " ".join(spans.values()) == text


def test_absolute_quality_repair_is_arm_blind_and_openai_strict() -> None:
    module = runpy.run_path(str(ROOT / "scripts/v1_5/167l_run_v5_4_effect_canary_absolute_quality_v1_5.py"))
    schema = module["AbsoluteQualityBatch"].model_json_schema()

    def assert_required(node: object) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert set(node.get("properties", {})) == set(node.get("required", []))
            for value in node.values():
                assert_required(value)
        elif isinstance(node, list):
            for value in node:
                assert_required(value)

    assert_required(schema)
    canary, generation = module["grouped"]()
    group_id = sorted(canary)[0]
    cases, private = module["build_cases"]("REVIEWER_A", group_id, generation[group_id])
    assert len(cases) == len(private) == 6
    assert all("arm" not in case and "replicate" not in case for case in cases)
    assert {row["arm"] for row in private} == {"ON", "OFF"}


def test_dual_human_calibration_packet_is_balanced_blind_and_empty() -> None:
    out = ROOT / "outputs/pm_v1_5_v5_4_human_measurement_calibration_v2_20260810"
    manifest = json.loads((out / "manifest.json").read_text())
    qa = json.loads((out / "qa_report.json").read_text())
    assert manifest["status"] == "V2_ANCHORED_DUAL_HUMAN_BLIND_PACKETS_READY_NOT_YET_ANNOTATED"
    assert manifest["underlying_items"] == {"QUALITY": 24, "FUNCTION": 24, "RISK": 48}
    assert manifest["risk"]["private_intended_family_counts"] == {
        "WRONG_OWNER_OR_IDENTITY": 4,
        "FUTURE_OR_UNVERIFIED_PRESENT_ASSERTION": 4,
        "UNSUPPORTED_PERSONAL_FACT_OR_CAUSE": 4,
        "EXPLICIT_BOUNDARY_VIOLATION": 4,
        "EXCESSIVE_DIRECTIVENESS_OR_BURDEN": 4,
        "INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE": 4,
    }
    assert qa["status"] == "HUMAN_CALIBRATION_PACKET_QA_PASS_READY_FOR_TWO_INDEPENDENT_HUMANS"
    assert all(qa["checks"].values())
    assert qa["diagnostics"]["forbidden_public_key_intersection"] == []
    assert qa["diagnostics"]["same_underlying_item_at_same_position"] <= 5
    assert manifest["quality"]["primary_effect_quantity"].startswith("within-rater ON minus OFF")
    assert manifest["rater_controls"]["blank_risk_is_missing_not_safe"] is True


def test_human_submission_validator_accepts_complete_evidence_bound_rows(tmp_path: Path) -> None:
    module = runpy.run_path(str(ROOT / "scripts/v1_5/171l_validate_and_prepare_v5_4_human_measurement_adjudication_v1_5.py"))
    builder = runpy.run_path(str(ROOT / "scripts/v1_5/169l_build_v5_4_human_measurement_calibration_packet_v1_5.py"))
    out = ROOT / "outputs/pm_v1_5_v5_4_human_measurement_calibration_v2_20260810"
    public_rows = _rows(out / "human_a_blind_packet.jsonl")
    completed = []
    for item in public_rows:
        decision: dict[str, object]
        if item["task"] == "QUALITY":
            decision = {
                "assessment_status": "RESOLVED",
                "goal_advance": 3,
                "emotional_attunement": 3,
                "specific_positive_support": 3,
                "clarity_naturalness": 3,
                "evidence_ids": next(iter(item["response_spans"])),
            }
        elif item["task"] == "FUNCTION":
            decision = {
                "candidate_contribution_present": "YES",
                "required_response_act_realized": "YES",
                "candidate_boundary_respected": "YES",
                "candidate_evidence_ids": next(iter(item["candidate_spans"])),
                "response_evidence_ids": next(iter(item["response_spans"])),
            }
        else:
            decision = {"assessment_status": "RESOLVED"}
            for family in builder["RISK_FAMILIES"]:
                decision[f"risk_{family}_severity"] = 0
                decision[f"risk_{family}_response_id"] = ""
                decision[f"risk_{family}_evidence_id"] = ""
        completed.append({
            "protocol": builder["PROTOCOL"],
            "reviewer_role": "HUMAN_A",
            "task": item["task"],
            "blind_item_id": item["blind_item_id"],
            "annotator_id": "test_human_a",
            "rubric_version_ack": "V2_ANCHORED_RUBRIC_READ",
            "completed": True,
            "decision": decision,
            "notes": "",
        })
    path = tmp_path / "completed.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in completed) + "\n")
    public = {row["blind_item_id"]: row for row in public_rows}
    validated = module["validate_submission"](path, "HUMAN_A", public, builder["RISK_FAMILIES"])
    assert len(validated) == 96
    assert module["function_projection"]({
        "candidate_contribution_present": "YES",
        "required_response_act_realized": "YES",
        "candidate_boundary_respected": "YES",
    }) == "FUNCTIONAL"
    assert module["quality_direction"](0.49, 0.5) == "TIE"
    assert module["quality_direction"](0.5, 0.5) == "ON_BETTER"
    assert module["quality_direction"](-0.5, 0.5) == "OFF_BETTER"
    assert module["parse_ids"]("null") == []
    assert module["parse_ids"]("R1,R2") == ["R1", "R2"]
    duplicate_person = {"only": {"annotator_id": "same_human"}}
    with pytest.raises(ValueError, match="distinct annotator_id"):
        module["ensure_distinct_annotators"]({"HUMAN_A": duplicate_person, "HUMAN_B": duplicate_person})
    missing_provenance = module["validate_human_provenance"](
        tmp_path / "missing.json", "HUMAN_A", "test_human_a", builder["PROTOCOL"]
    )
    assert missing_provenance["verified_human"] is False
    provenance_path = tmp_path / "provenance.json"
    provenance_path.write_text(json.dumps({
        "protocol": builder["PROTOCOL"],
        "reviewer_role": "HUMAN_A",
        "annotator_id": "test_human_a",
        "annotator_type": "human",
        "is_ai_model": False,
        "independence_attestation": True,
        "rubric_read_attestation": True,
    }))
    verified = module["validate_human_provenance"](
        provenance_path, "HUMAN_A", "test_human_a", builder["PROTOCOL"]
    )
    assert verified["verified_human"] is True
