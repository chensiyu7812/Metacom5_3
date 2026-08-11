#!/usr/bin/env python3
"""Build the zero-API Paper 1 semantic/retrieval/execution root-cause audit."""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "outputs" / "pm_v1_5_paper1_system_semantic_execution_root_cause_audit_20260811"


def read_json(relative: str) -> Any:
    return json.loads((ROOT / relative).read_text(encoding="utf-8"))


def read_jsonl(relative: str) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in (ROOT / relative).read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def file_hash(relative: str) -> str:
    return sha256((ROOT / relative).read_bytes()).hexdigest()


def percent(numerator: int | float, denominator: int | float) -> float:
    return 100.0 * float(numerator) / float(denominator)


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def only(rows: Iterable[dict[str, Any]], **matches: Any) -> list[dict[str, Any]]:
    return [
        row
        for row in rows
        if all(row.get(key) == value for key, value in matches.items())
    ]


def sql_literal(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    return "'" + str(value).replace("'", "''") + "'"


def values_sql(rows: list[dict[str, Any]], fields: list[str]) -> str:
    values = ",\n  ".join(
        "(" + ", ".join(sql_literal(row[field]) for field in fields) + ")"
        for row in rows
    )
    aliases = ", ".join(fields)
    return f"SELECT * FROM (VALUES\n  {values}\n) AS evidence({aliases})"


def main() -> None:
    authority_path = "data/pm_v1_5_contracts/active_method_authority_v1.json"
    surface_path = "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811/report.json"
    ms_oof_path = "outputs/pm_v1_5_paper1_v3_ms_atomic_teacher_logo_oof_20260811/report.json"
    ms_fit_path = "outputs/pm_v1_5_paper1_v3_ms_atomic_teacher_full_fit_20260811/report.json"
    mp_oof_path = "outputs/pm_v1_5_paper1_v3_mp_consensus_diagnostic_logo_oof_20260811/report.json"
    old_heads_path = "outputs/pm_v1_5_paper1_source_annotated_grouped_learnability_20260810/report.json"
    mechanical_path = "outputs/pm_v1_5_paper1_v3_ms_executor_mechanical_audit_20260811/report.json"
    closeout_path = "data/pm_v1_5_contracts/paper1_v3_rs_ms_pi_adjudicated_closeout_v1.json"
    human_b_path = "outputs/pm_v1_5_paper1_v3_rs_ms_two_human_freeze_20260811/human_B_raw_frozen.json"
    quality_path = "outputs/pm_v1_5_paper1_v3_rs_ms_two_human_freeze_20260811/unblinded_quality_raw.jsonl"
    policy_path = "outputs/pm_v1_5_paper1_v3_rs_ms_same_stack_baseline_plan_20260811/policy_actions_private.jsonl"
    mapping_path = "outputs/pm_v1_5_paper1_v3_ms_executor_measurement_packet_20260811/private_mapping.jsonl"
    recovered_path = "outputs/pm_v1_5_paper1_v3_ms_executor_trace_recovery_20260811/recovered_first_response_results_private.jsonl"
    gemini_reviews_path = "outputs/pm_v1_5_paper1_v3_ms_executor_function_budget_bound_reviews_20260811/reviews.jsonl"
    function_gold_path = "outputs/pm_v1_5_paper1_v3_ms_executor_function_proxy_preflight_20260811/fresh_control_gold_private.jsonl"
    primary_rule_path = "data/pm_v1_5_contracts/paper1_component_general_v3_primary_success_rule_v1.json"
    r0_diagnostic_path = "outputs/pm_v1_5_paper1_v3_r0_function_closure_diagnostic_20260811/report.json"
    r0_private_path = "outputs/pm_v1_5_paper1_v3_r0_function_closure_diagnostic_20260811/r0_function_private_key.jsonl"
    preflight_runner_path = "scripts/v1_5/230l_materialize_paper1_v3_ms_executor_qualification_preflight_v1_5.py"
    live_runner_path = "scripts/v1_5/232l_run_paper1_v3_ms_executor_qualification_v1_5.py"

    authority = read_json(authority_path)
    surface = read_json(surface_path)
    ms_oof = read_json(ms_oof_path)
    ms_fit = read_json(ms_fit_path)
    mp_oof = read_json(mp_oof_path)
    old_heads = read_json(old_heads_path)["head_metrics"]
    mechanical = read_json(mechanical_path)
    closeout = read_json(closeout_path)
    human_b = read_json(human_b_path)
    quality = read_jsonl(quality_path)
    policies = read_jsonl(policy_path)
    mappings = read_jsonl(mapping_path)
    recovered = read_jsonl(recovered_path)
    gemini_reviews = {row["blind_item_id"]: row for row in read_jsonl(gemini_reviews_path)}
    function_gold = {row["blind_item_id"]: row for row in read_jsonl(function_gold_path)}
    primary_rule = read_json(primary_rule_path)
    r0_diagnostic = read_json(r0_diagnostic_path)
    r0_private = read_jsonl(r0_private_path)

    generic_meaning_cue = (
        "Interpret the single strictly past user-owned source supplied below as a "
        "tentative continuity cue; do not treat it as current or quote it."
    )
    generic_allowed_change = (
        "If it materially helps, use the past meaning to acknowledge continuity or ask "
        "a more informed current-oriented question."
    )
    for runner_path in (preflight_runner_path, live_runner_path):
        runner_text = (ROOT / runner_path).read_text(encoding="utf-8")
        assert "Interpret the single strictly past user-owned source supplied below" in runner_text
        assert "tentative continuity cue; do not treat it as current or quote it." in runner_text
        assert generic_allowed_change in runner_text

    learned_policy = only(policies, policy="rs_fixed_on_plus_learned_ms")
    learned_on_states = {
        row["state_id"] for row in learned_policy if row["ms_selected_on"]
    }
    assert len(learned_policy) == 16
    assert len(learned_on_states) == 7

    quality_all_b = Counter(row["directions"]["HUMAN_B"] for row in quality)
    quality_on_b = Counter(
        row["directions"]["HUMAN_B"]
        for row in quality
        if row["state_id"] in learned_on_states
    )
    quality_on_a = Counter(
        row["directions"]["HUMAN_A"]
        for row in quality
        if row["state_id"] in learned_on_states
    )

    rs_function_map = {
        row["state_id"]: row["function_blind_item_id"]
        for row in mappings
        if row["rs_condition"] == "RS"
    }
    answers_b = human_b["answers"]
    learned_source_availability = Counter(
        answers_b[rs_function_map[state_id]]["source_availability"]
        for state_id in learned_on_states
    )
    all_source_availability = Counter(
        answers_b[function_id]["source_availability"]
        for function_id in rs_function_map.values()
    )

    ms_rs_results = {
        row["state_id"]: row
        for row in recovered
        if row["requested_action_id"] == "MS+RS"
    }
    learned_claimed = sum(
        bool(ms_rs_results[state_id]["generator_claimed"]["MS"])
        for state_id in learned_on_states
    )
    all_claimed = sum(
        bool(row["generator_claimed"]["MS"])
        for row in ms_rs_results.values()
    )
    assert len(ms_rs_results) == 16

    usable_states = {
        state_id
        for state_id, function_id in rs_function_map.items()
        if answers_b[function_id]["source_availability"] == "USABLE"
    }
    retrieval_panel_tp = len(learned_on_states & usable_states)
    retrieval_panel_fn = len(usable_states - learned_on_states)
    retrieval_panel_fp = len(learned_on_states - usable_states)
    retrieval_panel_tn = 16 - retrieval_panel_tp - retrieval_panel_fn - retrieval_panel_fp
    panel_recall = retrieval_panel_tp / (retrieval_panel_tp + retrieval_panel_fn)
    panel_specificity = retrieval_panel_tn / (retrieval_panel_tn + retrieval_panel_fp)

    gemini_exact = sum(
        gemini_reviews[item_id]["label"] == gold["gold_label"]
        for item_id, gold in function_gold.items()
        if item_id in gemini_reviews
    )
    gemini_missing = sorted(set(function_gold) - set(gemini_reviews))
    gemini_mismatch = sorted(
        item_id
        for item_id in set(function_gold) & set(gemini_reviews)
        if gemini_reviews[item_id]["label"] != function_gold[item_id]["gold_label"]
    )

    head_rows = [
        {
            "component": "RS",
            "candidate_surface": "six-card bank on ESConv/EvoEmo dialogue",
            "available_pct": 100.0,
            "bounded_oof": round(100 * old_heads["RS"]["balanced_accuracy"], 1),
            "oof_n": old_heads["RS"]["n"],
            "groups": old_heads["RS"]["groups"],
            "current_status": "selector signal carried; current 16-state panel fixed RS ON",
        },
        {
            "component": "MP",
            "candidate_surface": "profile field with current lexical scope match",
            "available_pct": round(100 * surface["counts"]["components"]["MP"]["availability_rate"], 1),
            "bounded_oof": round(100 * mp_oof["primary_metrics"]["balanced_accuracy_at_0_5"], 1),
            "oof_n": mp_oof["denominator"]["rows"],
            "groups": mp_oof["denominator"]["groups"],
            "current_status": "exact-consensus diagnostic only; CI/label route not formal",
        },
        {
            "component": "MS",
            "candidate_surface": "BGE-M3 Rank-1 over strictly-past same-owner seeker turns",
            "available_pct": round(100 * surface["counts"]["components"]["MS"]["availability_rate"], 1),
            "bounded_oof": round(100 * ms_oof["primary_metrics"]["balanced_accuracy_at_0_5"], 1),
            "oof_n": ms_oof["denominator"]["resolved_rows"],
            "groups": ms_oof["denominator"]["groups"],
            "current_status": "teacher suitability learnable; PI verified Function 0/7",
        },
        {
            "component": "ME",
            "candidate_surface": "typed lexical Rank-1 action-result memory",
            "available_pct": round(100 * surface["counts"]["components"]["ME"]["availability_rate"], 1),
            "bounded_oof": round(100 * old_heads["ME"]["balanced_accuracy"], 1),
            "oof_n": old_heads["ME"]["n"],
            "groups": old_heads["ME"]["groups"],
            "current_status": "sparse candidate surface and failed historical OOF",
        },
    ]

    stage_rows = [
        {"stage": "MS candidate present", "value_pct": round(100 * surface["counts"]["components"]["MS"]["availability_rate"], 1), "cohort": "4,689 EvoEmo states", "meaning": "retrieval capacity"},
        {"stage": "MS teacher-label OOF BA", "value_pct": round(100 * ms_oof["primary_metrics"]["balanced_accuracy_at_0_5"], 1), "cohort": "201 rows / 17 groups", "meaning": "bounded teacher suitability prediction"},
        {"stage": "Learned-ON source usable", "value_pct": percent(len(learned_source_availability), len(learned_on_states)), "cohort": "7 learned-ON RS states", "meaning": "PI source availability"},
        {"stage": "Generator claimed MS", "value_pct": percent(learned_claimed, len(learned_on_states)), "cohort": "7 learned-ON RS states", "meaning": "untrusted telemetry"},
        {"stage": "PI verified Function", "value_pct": 0.0, "cohort": "7 learned-ON RS states", "meaning": "human source-attributable contribution"},
    ]

    quality_rows = [
        {"review": "PI final B", "direction": "MS+RS better", "count": quality_on_b["MS_ON_BETTER"], "n": 7},
        {"review": "PI final B", "direction": "RS-only better", "count": quality_on_b["RS_ONLY_BETTER"], "n": 7},
        {"review": "Human A sensitivity", "direction": "MS+RS better", "count": quality_on_a["MS_ON_BETTER"], "n": 7},
        {"review": "Human A sensitivity", "direction": "RS-only better", "count": quality_on_a["RS_ONLY_BETTER"], "n": 7},
        {"review": "Human A sensitivity", "direction": "tie", "count": quality_on_a["EQUIVALENT"], "n": 7},
    ]

    architecture_rows = [
        {"layer": "1. Unified state surface", "current": "present", "target": "one state ID and one connected-group fold shared by all heads"},
        {"layer": "2. Component Rank-1", "current": "present", "target": "separate MP/MS/ME/RS candidate and features per state"},
        {"layer": "3. Four independent heads", "current": "partial", "target": "four binary probabilities; independent OFF/abstain; no shared label"},
        {"layer": "4. 16-action compiler", "current": "implemented", "target": "combine four bits; no one-memory cap"},
        {"layer": "5. Joint response program", "current": "implemented, MS human Function failed in RS slice", "target": "one coherent reply; multiple resources may support one response act"},
        {"layer": "6. Offline responsibility", "current": "implemented in measurement, not yet full external", "target": "separate retrieval, selector, executor, generator, Quality/Risk/Cost"},
    ]

    endpoint_rows = [
        {
            "endpoint": "Claude Haiku 4.5",
            "local_observation": "204/204 MS suitability calls completed; multi-empty-string Function schema suffered semantic field shifting",
            "diagnosis": "schema/serialization contract failure, not evidence of semantic incapacity",
            "minimal_fix": "native structured output or strict tool schema; discriminated evidence array/span IDs; no parallel empty evidence strings; 3-control pilot",
        },
        {
            "endpoint": "Gemini 2.5 Flash",
            "local_observation": f"{gemini_exact}/{len(gemini_reviews)} completed controls exact; {len(gemini_mismatch)} mismatch; {len(gemini_missing)} unresolved control missing after hidden-thought truncation",
            "diagnosis": "promising semantics, unqualified transport/budget wrapper",
            "minimal_fix": "verify wire thinkingBudget=0 and native JSON schema; 3-control pilot including UNRESOLVED; stop if thought budget still uncontrolled",
        },
    ]

    availability_rows = [
        {
            "component": component,
            "available_pct": round(
                100 * surface["counts"]["components"][component]["availability_rate"],
                1,
            ),
        }
        for component in ("MP", "MS", "ME")
    ]
    widget_sources = {
        "candidate_availability": values_sql(
            availability_rows, ["component", "available_pct"]
        ),
        "ms_evidence_ladder": values_sql(
            stage_rows, ["stage", "value_pct", "cohort", "meaning"]
        ),
        "head_status": values_sql(
            head_rows,
            [
                "component",
                "candidate_surface",
                "available_pct",
                "bounded_oof",
                "oof_n",
                "groups",
                "current_status",
            ],
        ),
        "architecture": values_sql(architecture_rows, ["layer", "current", "target"]),
        "endpoints": values_sql(
            endpoint_rows,
            ["endpoint", "local_observation", "diagnosis", "minimal_fix"],
        ),
    }

    def widget_source(dataset: str, description: str) -> dict[str, Any]:
        return {
            "id": f"{dataset}_sql",
            "label": description,
            "path": str((OUT / "analysis.json").relative_to(ROOT)),
            "query": {
                "language": "sql",
                "engine": "DuckDB-compatible VALUES snapshot",
                "sql": widget_sources[dataset],
                "description": description,
                "tables_used": [str((OUT / "analysis.json").relative_to(ROOT))],
                "filters": ["frozen zero-API evidence only"],
                "metric_definitions": [
                    "Values are copied from the hash-bound analysis snapshot generated by this script."
                ],
            },
        }

    authority_conflict = {
        "active_v3_phase": authority["active_v3_phase"]["id"],
        "active_v3_status": authority["active_v3_phase"]["status"],
        "stale_nested_current_phase": authority["current_phase"]["id"],
        "stale_nested_status": authority["current_phase"]["status"],
        "assessment": "The top-level active_v3_phase is current, but the same authority file still exposes an older terminal current_phase. This is a real machine-routing hazard and must be normalized before any new runner is authorized.",
    }

    analysis = {
        "protocol": "pm-v1.5-paper1-system-semantic-execution-root-cause-audit-v1",
        "date": "2026-08-11",
        "status": "ROOT_CAUSE_LOCALIZED_PAPER1_IMPLEMENTABLE_EXTERNAL_FINAL_NOT_READY",
        "api_calls": 0,
        "headline": "The four-head/16-action design remains correct, and Paper 1 success is now frozen as RS plus at least two passing memory heads among MP/MS/ME. Current MS failure is not general retrieval absence: in the learned-MS-ON RS slice all 7 Rank-1 sources were PI-usable and 6/7 were generator-claimed, yet human verified Function was 0/7. The runner also supplied only a generic meaning instruction rather than a candidate-specific semantic proposition and response-change plan.",
        "primary_success_rule": primary_rule["primary_success_predicate"],
        "semantic_understanding_definition": {
            "what_it_is": "bounded candidate retrieval plus low-capacity component-specific suitability prediction",
            "what_it_is_not": "a general human-intent or full language-understanding model",
            "measurable_proportions": {
                "RS_grouped_oof_balanced_accuracy": old_heads["RS"]["balanced_accuracy"],
                "MS_teacher_label_oof_balanced_accuracy": ms_oof["primary_metrics"]["balanced_accuracy_at_0_5"],
                "MS_teacher_label_oof_ci95": ms_oof["owner_cluster_bootstrap_95_ci"]["balanced_accuracy"],
                "MP_consensus_diagnostic_balanced_accuracy": mp_oof["primary_metrics"]["balanced_accuracy_at_0_5"],
                "ME_historical_balanced_accuracy": old_heads["ME"]["balanced_accuracy"],
                "warning": "These are construct-specific cross-group prediction metrics, not percentages of human utterances understood.",
            },
            "runtime_nonunderstanding_behavior": {
                "candidate_absent_or_structurally_invalid": "turn that component OFF",
                "probability_below_threshold": "turn that component OFF",
                "formal_runtime_uncertainty_band": "not implemented",
                "all_four_off": "M0+R0",
                "partial_off": "preserve remaining components and compile the corresponding one of 16 actions",
            },
        },
        "retrieval_and_execution": {
            "candidate_availability": surface["counts"]["components"],
            "co_presence": surface["counts"]["co_presence"],
            "ms_panel_source_discrimination_descriptive": {
                "tp": retrieval_panel_tp,
                "fn": retrieval_panel_fn,
                "fp": retrieval_panel_fp,
                "tn": retrieval_panel_tn,
                "recall": panel_recall,
                "specificity": panel_specificity,
                "balanced_accuracy": (panel_recall + panel_specificity) / 2,
                "claim_limit": "small, deliberately selected 16-state development panel; not a generalization estimate",
            },
            "learned_on_rs_slice": {
                "states": 7,
                "source_usable": learned_source_availability["USABLE"],
                "generator_claimed_ms": learned_claimed,
                "pi_verified_function": 0,
                "pi_quality_ms_better": quality_on_b["MS_ON_BETTER"],
                "pi_quality_rs_only_better": quality_on_b["RS_ONLY_BETTER"],
                "absorption_harm_rate_identifiable": False,
                "forced_ms_arm_quality_loss_rate": quality_on_b["RS_ONLY_BETTER"] / 7,
                "reason_not_identifiable": "There are zero human-verified Function cases, so Quality losses cannot be attributed to successful memory absorption.",
            },
            "all_rs_slice": {
                "states": 16,
                "source_usable": all_source_availability["USABLE"],
                "generator_claimed_ms": all_claimed,
                "pi_verified_function": 0,
                "pi_quality": dict(quality_all_b),
            },
            "literal_splice": {
                "active_v3_exact_full_source_copies": mechanical["literal_splice_checks"]["exact_full_source_copies"],
                "active_v3_mean_token_jaccard_suitable": mechanical["literal_splice_checks"]["mean_unique_token_jaccard_suitable"],
                "legacy_v2_hard_splice_code_still_present": True,
                "active_v3_path_requires_literal_or_lexical_overlap": False,
            },
            "meaning_cue_implementation": {
                "candidate_specific_semantic_proposition_supplied": False,
                "candidate_specific_response_change_plan_supplied": False,
                "actual_meaning_cue": generic_meaning_cue,
                "actual_allowed_response_change": generic_allowed_change,
                "raw_exact_source_also_supplied": True,
                "diagnosis": "V3 removed forced literal splice, but the promised semantic adapter was not implemented: the generator still had to infer both the source meaning and its useful role from raw text.",
            },
            "existing_r0_diagnostic": {
                **r0_diagnostic["r0_function"],
                "all_sources_matched_PI_usable": all(
                    row["PI_source_availability_from_matched_RS_slice"] == "USABLE"
                    for row in r0_private
                ),
                "formal_labels_pending": True,
            },
        },
        "four_head_architecture": {
            "design": "one unified base state/fold table; four component-specific candidate views and binary heads; combine four bits into 16 actions; execute jointly",
            "current_realization": "partial: RS has carried OOF evidence, MS has a teacher-suitability checkpoint, MP is diagnostic, ME is weak; current 16-state system panel fixed RS ON and varied MS only",
            "head_rows": head_rows,
            "architecture_rows": architecture_rows,
        },
        "root_causes": [
            "Evidence stages were repeatedly conflated: candidate availability, proxy-label predictability, generator telemetry, human Function, and response Quality are different estimands.",
            "Historical MS labels used source-session lineage while runtime acted on an atomic turn; the target unit was wrong.",
            "Actual Rank-1 quality and suitability were not separated; low-information/current-echo candidates were sometimes treated as positive memory.",
            "Legacy V2 forced literal use and lexical trace; active V3 removes this, but legacy code remains a routing hazard.",
            "Current V3 generator can decline a resource, yet the RS-fixed-on slice produced no human-verifiable MS contribution even when the source was usable; RS crowd-out versus general executor nonuse is unresolved.",
            "The V3 runner populated meaning_cue and allowed_response_change with identical generic templates for every candidate. It did not materialize the candidate-specific semantic proposition, current-goal relation, boundary, or concrete response change promised by the architecture.",
            "LLM measurement endpoints were overpromoted despite schema, token-budget, order, and attribution failures; proxy 12/12 Function later became PI 0/7 in the relevant slice.",
            "The authority file itself exposes both a current V3 phase and a stale terminal current_phase.",
        ],
        "endpoint_compatibility": {
            "rows": endpoint_rows,
            "gemini_control_evidence": {
                "completed": len(gemini_reviews),
                "exact": gemini_exact,
                "mismatch_ids": gemini_mismatch,
                "missing_ids": gemini_missing,
            },
        },
        "minimum_repair_route": [
            "Normalize one machine authority pointer and forbid legacy V2 imports in all active runners.",
            "Add per-head three-way runtime accounting: ON, OFF, UNCERTAIN_AS_OFF. Learn/calibrate uncertainty only on outer-train; do not map one uncertain head to global M0+R0.",
            "Complete the already materialized 7-item existing-arm MS+R0 Function review and the separate 2-item M0+R0 versus M0+RS closure review; neither requires API calls, refitting, or threshold changes.",
            "If MS+R0 has any verified Function, quantify RS crowd-out and repair joint response planning. If it remains 0/7, implement the missing bounded semantic-use-plan adapter before any new head fit: candidate proposition, current-goal relation, exact response change, owner/time boundary, and nonuse condition.",
            "After MS execution is repaired, develop MP and ME under the same independent-head/joint-execution discipline. The primary system requires at least two passing memory heads; one memory head is not sufficient.",
            "Run one transport-only Claude/Gemini compatibility pilot with three controls. Endpoint choice is a measurement implementation decision, not a new scientific model search.",
            "Then run a versioned external development smoke test. After one predeclared repair, freeze and execute cross-fitted ESConv, ES-MemEval, and EvoEmo reports with same-stack baselines.",
        ],
        "hf_model_decision": {
            "decision": "DO_NOT_ADD_A_NEW_GENERAL_INTENT_MODEL_NOW",
            "reason": "The learned-on panel already selected usable sources 7/7; the observed break is downstream realization. Another encoder cannot repair a response that ignores an already usable source.",
            "conditional_future": "Only if the retrieval-oracle decomposition shows actual Rank-1 is the dominant bottleneck, pre-register one cross-encoder reranker challenger against BGE-M3. Do not run an open-ended Hugging Face model search.",
        },
        "authority_conflict": authority_conflict,
        "source_hashes": {
            path: file_hash(path)
            for path in [
                authority_path,
                surface_path,
                ms_oof_path,
                ms_fit_path,
                mp_oof_path,
                old_heads_path,
                mechanical_path,
                closeout_path,
                human_b_path,
                quality_path,
                policy_path,
                mapping_path,
                recovered_path,
                gemini_reviews_path,
                function_gold_path,
                primary_rule_path,
                r0_diagnostic_path,
                r0_private_path,
                preflight_runner_path,
                live_runner_path,
            ]
        },
    }

    now = datetime.now().astimezone().isoformat(timespec="seconds")
    artifact = {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": "PM 第一篇：语义、召回、四头与执行链根因审计",
            "description": "Zero-API technical audit separating candidate coverage, bounded suitability prediction, generator uptake, verified Function, and response outcomes.",
            "generatedAt": now,
            "sources": [
                {
                    "id": "root_cause_analysis",
                    "label": "Frozen local evidence audit",
                    "path": str((OUT / "analysis.json").relative_to(ROOT)),
                    "query": {
                        "language": "python",
                        "engine": "hash-bound local artifact join",
                        "description": "Joins frozen candidate-surface, OOF, executor trace, PI adjudication, policy binding, and endpoint-control artifacts.",
                        "tables_used": list(analysis["source_hashes"]),
                        "filters": ["zero API", "no refit", "no threshold change", "PI HUMAN_B final; HUMAN_A sensitivity"],
                        "metric_definitions": [
                            "Candidate availability is structural capacity, not understanding.",
                            "OOF balanced accuracy predicts the named component-specific label, not general human-language comprehension.",
                            "Verified Function requires a source-attributable contribution not explainable by current dialogue alone.",
                        ],
                    },
                }
            ],
            "charts": [
                {
                    "id": "candidate_availability",
                    "title": "公共纵向表面的候选覆盖",
                    "subtitle": "同一 4,689 个 EvoEmo states；覆盖不等于适用或做功",
                    "type": "bar",
                    "dataset": "candidate_availability",
                    "sourceId": "root_cause_analysis",
                    "source": widget_source(
                        "candidate_availability",
                        "Candidate availability derived from the frozen G3 surface audit.",
                    ),
                    "layout": "full",
                    "encodings": {
                        "x": {"field": "component", "type": "nominal", "label": "组件"},
                        "y": {"field": "available_pct", "type": "quantitative", "label": "候选存在率 (%)"},
                        "color": {"field": "component", "type": "nominal", "label": "组件"},
                    },
                    "valueFormat": ".1f",
                    "maxRows": 3,
                    "question": "记忆头首先有没有可供判断的候选？",
                    "rationale": "Candidate coverage must be shown separately from suitability and execution.",
                    "emptyState": "No candidate surface metrics are available.",
                },
                {
                    "id": "ms_evidence_ladder",
                    "title": "MS 证据链为何在最后一段断掉",
                    "subtitle": "分母不同，不能当单一漏斗；每根柱子的 cohort 在标签中明确",
                    "type": "bar",
                    "dataset": "ms_evidence_ladder",
                    "sourceId": "root_cause_analysis",
                    "source": widget_source(
                        "ms_evidence_ladder",
                        "Stage-specific MS evidence with explicit, non-pooled denominators.",
                    ),
                    "layout": "full",
                    "encodings": {
                        "x": {"field": "stage", "type": "nominal", "label": "证据阶段"},
                        "y": {"field": "value_pct", "type": "quantitative", "label": "比例/BA (%)"},
                        "color": {"field": "meaning", "type": "nominal", "label": "测量含义"},
                    },
                    "valueFormat": ".1f",
                    "maxRows": 5,
                    "question": "MS 是在召回、选择、generator 使用，还是人类确认做功处失败？",
                    "rationale": "The adjacent bars expose the estimand shift instead of pooling incompatible denominators.",
                    "emptyState": "No MS stage evidence is available.",
                },
            ],
            "tables": [
                {
                    "id": "head_status",
                    "title": "四个 head 的真实状态",
                    "subtitle": "同一 base state/split，可分别训练；当前并非四头全 fit",
                    "dataset": "head_status",
                    "density": "spacious",
                    "sourceId": "root_cause_analysis",
                    "source": widget_source(
                        "head_status",
                        "Component-specific candidate, OOF, and evidence-boundary snapshot.",
                    ),
                    "layout": "full",
                    "columns": [
                        {"field": "component", "label": "Head", "type": "text"},
                        {"field": "candidate_surface", "label": "Rank-1 逻辑", "type": "text"},
                        {"field": "available_pct", "label": "候选覆盖 %", "format": ".1f"},
                        {"field": "bounded_oof", "label": "有界 OOF BA %", "format": ".1f"},
                        {"field": "oof_n", "label": "n", "format": "number"},
                        {"field": "groups", "label": "groups", "format": "number"},
                        {"field": "current_status", "label": "当前证据边界", "type": "text"},
                    ],
                },
                {
                    "id": "architecture",
                    "title": "统一训练面、独立四头、联合 16 动作",
                    "subtitle": "设计正确；实现只完成到部分 head 与局部同栈验证",
                    "dataset": "architecture",
                    "density": "spacious",
                    "sourceId": "root_cause_analysis",
                    "source": widget_source(
                        "architecture",
                        "Current versus target state of the unified-state/four-head/16-action architecture.",
                    ),
                    "layout": "full",
                    "columns": [
                        {"field": "layer", "label": "层", "type": "text"},
                        {"field": "current", "label": "当前", "type": "text"},
                        {"field": "target", "label": "冻结目标", "type": "text"},
                    ],
                },
                {
                    "id": "endpoints",
                    "title": "Claude / Gemini 兼容性结论",
                    "subtitle": "只修 transport/schema，不把换 endpoint 当科学改进",
                    "dataset": "endpoints",
                    "density": "spacious",
                    "sourceId": "root_cause_analysis",
                    "source": widget_source(
                        "endpoints",
                        "Local endpoint compatibility observations and minimal transport fixes.",
                    ),
                    "layout": "full",
                    "columns": [
                        {"field": "endpoint", "label": "Endpoint", "type": "text"},
                        {"field": "local_observation", "label": "本地事实", "type": "text"},
                        {"field": "diagnosis", "label": "诊断", "type": "text"},
                        {"field": "minimal_fix", "label": "最小修复", "type": "text"},
                    ],
                },
            ],
            "blocks": [
                {"id": "title", "type": "markdown", "body": "# PM 第一篇：语义、召回、四头与执行链根因审计", "layout": "full"},
                {"id": "summary", "type": "markdown", "body": "## 技术结论\n\n**第一篇仍然可以实现，但不能把当前结果叫做完整 PM 及格。** 成功判据现已锁定为：RS通过，且MP/MS/ME至少两个记忆头通过；最多一个记忆头可固定OFF，四头与16种requested action全部保留。当前最关键的新证据是：learned MS 开启的7个RS状态里，PI确认7/7来源可用，generator有6/7自报使用，但人评可归因Function是0/7。因此这次不是一般性的‘召回不到’。进一步代码审计发现，runner并未生成候选特定的语义命题和use plan，只给了原始旧句与统一说明；断点主要在语义适配、联合回复动作和generator实现，而不是需要再加一个通用意图模型。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "availability_text", "type": "markdown", "body": "## 现在的语义理解到底是什么\n\n系统没有一个总的‘理解用户意图’模块。它先构造组件候选：MS用BGE-M3在同一owner严格过去的seeker turns里取cosine Rank-1；MP用profile字段的冻结scope词表；ME用typed lexical匹配并要求action-result compiler合法；RS从六张策略卡取共享Rank-1。然后每个head只判断自己的候选是否值得开启。OOF分数只能解释成‘对该有界标签的跨组预测能力’，不能解释成‘理解了多少人类语言’。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "candidate_chart", "type": "chart", "chartId": "candidate_availability", "layout": "full"},
                {"id": "head_table", "type": "table", "tableId": "head_status", "layout": "full"},
                {"id": "uncertainty", "type": "markdown", "body": "## 如果理解不了，当前会怎样\n\n结构缺失或owner/time/compiler非法时，只关闭对应组件；概率低于0.5也关闭对应组件。其余bits继续组合，所以不确定MS不等于全局M0+R0：可能是M0+RS、MP+R0或其他合法动作。四bit全OFF才是M0+R0。当前缺少正式runtime abstain区间，所以系统还不能可靠识别‘我不确定但分数碰巧很高’。最小修复是每个head独立记录ON/OFF/UNCERTAIN_AS_OFF，置信规则只在outer-train校准。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "ladder_text", "type": "markdown", "body": "## MS 为什么看起来会、最后却没及格\n\n候选覆盖、teacher-label OOF、generator自报与人类Function属于不同层。MS teacher OOF BA=74.5%说明低容量模型能预测那位合格teacher的prospective suitability；它不证明generator会正确使用。小panel上selector实际把7/8可用来源打开、8/8不可用来源关闭，描述性BA=93.8%，但7个已打开来源仍没有一条在人评中形成过去来源独立贡献。这个结果把主要责任从selector转移到joint executor/response-act interaction。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "ladder_chart", "type": "chart", "chartId": "ms_evidence_ladder", "layout": "full"},
                {"id": "splice", "type": "markdown", "body": "## 没有逐字硬拼接，但也没有真正完成语义吸收\n\n旧V2代码仍要求exact prior-user statement、词面重合和强制use，仍留在仓库里，是版本路由风险。当前V3路径已删除这些义务：32条MS-ON回复exact source整段复制为0，safe non-use也不再触发固定句。然而runner把每条候选的meaning_cue都写成同一句通用指令，把allowed_response_change也写成同一句通用建议；它没有提供候选特定的语义命题、当前目标关系、owner/time边界和具体回复改变。因此当前不是‘字面硬拼’，而是‘把原始旧句交给generator临场猜怎样用’，仍未达到设计中的meaning absorption。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "harm", "type": "markdown", "body": "## ‘吸收后反而变差’目前是错误归因\n\nPI终值在7个learned-ON状态上是MS+RS 5胜、RS-only 2胜；若只看请求臂，较差是2/7=28.6%。但Function为0/7，没有任何一条证明记忆真正进入并改变了回复，所以不能称‘吸收后变差’。责任必须分层：来源是否可用（本7条均可用）、semantic use plan是否存在（当前缺失）、generator是否实现（未被人工确认）、RS/R0是否选对、以及最终Quality/Risk。只有Function先成立，才有资格计算真正的absorption harm。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "architecture_text", "type": "markdown", "body": "## 统一数据、独立四头、联合16动作是正确方案\n\n统一的是state ID、当前上下文、owner group和outer fold；不统一的是四个head的候选、特征和标签。每个state可产生四条component-view训练行，四个binary head分别输出概率，再组合成16种requested action。joint planner必须允许多个记忆同时存在，并将它们组织到一条连贯回复中；cost只在四头输出后的投影/比较中使用。第一篇的最低成功不是RS+单一记忆，而是RS通过且MP/MS/ME至少两个通过；最多一个记忆头可固定OFF。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "architecture_table", "type": "table", "tableId": "architecture", "layout": "full"},
                {"id": "endpoints_text", "type": "markdown", "body": "## Claude 和 Gemini 不是同一个问题\n\nClaude已经完整完成204条MS suitability调用，Function失败发生在多空字符串字段的tool schema语义串位；应改为判别式evidence数组或span ID，而不是手修输出。Gemini对已完成controls是10/11 exact，表现并非不能胜任；失败来自hidden thinking吞掉JSON预算且漏掉UNRESOLVED control。官方文档目前支持Gemini 2.5 Flash structured output并允许thinkingBudget=0，也支持Claude Haiku 4.5 structured output/strict tool use。因此先核对wire payload和极小compatibility pilot，不能继续盲目抬token cap。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "endpoint_table", "type": "table", "tableId": "endpoints", "layout": "full"},
                {"id": "version", "type": "markdown", "body": "## 版本控制仍有一个真实缺口\n\nactive_method_authority顶层active_v3_phase指向PI裁定后的V3，但同一文件的current_phase仍指向旧MS_SESSION_ALIGNED_FINAL_OOF_V2 terminal。人读时能分辨，runner若只读current_phase就可能回退。任何新外部执行前必须把权威指针正规化，并对active runner做禁止导入V2 memory modules的机器测试。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "route", "type": "markdown", "body": "## 最短成功路线\n\n1. 已把RS+至少两个记忆头的成功判据写入活动权威，保留四头与16动作。\n2. 已零API物化现成7个learned-MS-ON的MS+R0 Function包，以及2个closure状态的M0+R0 vs M0+RS包；只等PI按既有锚点裁定。\n3. 若R0出现Function，量化RS crowd-out并修联合规划；若仍为0/7，先补上缺失的候选特定semantic use plan：语义命题、当前目标关系、具体回复改变、owner/time边界、自然不用条件。\n4. 在冻结小切片验证MS真正做功后，再用同一纪律推进MP和ME；最终MP/MS/ME至少两个必须通过。\n5. 然后进入版本化外部development smoke；冻结后再做ESConv、ES-MemEval、EvoEmo cross-fitted正式报告。\n\n现在不引入新的Hugging Face通用意图模型。只有后续oracle分解证明Rank-1仍是主瓶颈时，才预注册一个cross-encoder reranker挑战BGE-M3。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "limitations", "type": "markdown", "body": "## 限制与稳健性\n\n16-state panel是刻意选择的development slice，不能把93.8%描述性source-usability分类当外部泛化分数。MS OOF标签来自单一合格LLM teacher，不是人工gold。PI Function 0/7是当前最关键的人评证据，但只覆盖RS-fixed-on；它不能判定MS+R0是否也失败。MP OOF只来自exact-consensus子群，ME候选仅23个unique action-result，均不能冒充正式head pass。", "layout": "full", "sourceId": "root_cause_analysis"},
                {"id": "questions", "type": "markdown", "body": "## 当前只需人工回答九条，不再生成\n\n- 7条现有MS+R0回复：过去来源是否真正产生source-attributable Function？其中7条来源已确认可用，但generator仅3条自报使用。\n- 2条closure A/B：M0+R0是否比继续RS提问更符合relief+closure阶段？\n\n这两组必须分开：前者定MS执行责任，后者定RS/回复阶段路由。无API、无重训、无调阈值。", "layout": "full"},
            ],
        },
        "snapshot": {
            "version": 1,
            "generatedAt": now,
            "status": "ready",
            "datasets": {
                "candidate_availability": availability_rows,
                "ms_evidence_ladder": stage_rows,
                "head_status": head_rows,
                "architecture": architecture_rows,
                "endpoints": endpoint_rows,
                "quality_learned_on": quality_rows,
            },
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "analysis.json", analysis)
    write_json(OUT / "artifact.json", artifact)
    print(json.dumps({
        "status": analysis["status"],
        "output": str(OUT),
        "learned_on_sources_usable": learned_source_availability["USABLE"],
        "learned_on_generator_claimed": learned_claimed,
        "learned_on_pi_functional": 0,
        "gemini_controls": {"exact": gemini_exact, "completed": len(gemini_reviews), "planned": len(function_gold)},
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
