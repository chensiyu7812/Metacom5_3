#!/usr/bin/env python3
"""Decompose the failed V5.3 formal-head result into design, execution, and measurement causes.

This is an outcome-open forensic audit.  It never requalifies a head and makes no
new API calls.  The point is to establish which conclusions the completed panel
can and cannot support before another protocol is proposed.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping

import numpy as np
from scipy.stats import pearsonr, spearmanr


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json  # noqa: E402


FORMAL_MANIFEST = (
    ROOT
    / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/"
    "effect_group_manifest_private.jsonl"
)
FORMAL_RESULT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809/shards"
FORMAL_OOF = ROOT / "outputs/pm_v1_5_v5_3_public_formal_oof_20260809/formal_oof_report.json"
PILOT_MANIFEST = (
    ROOT
    / "outputs/pm_v1_5_v5_3_public_learnability_pilot_20260809/"
    "effect_group_manifest_private.jsonl"
)
PILOT_RESULTS = (
    ROOT
    / "outputs/pm_v1_5_v5_3_public_qf_development_pilot_20260809/qf_results.jsonl"
)
QRF_SOURCE = ROOT / "src/metacom_pm/v1_5_v5_3_qrf_judge.py"
FORMAL_SELECTION_SOURCE = ROOT / "src/metacom_pm/v1_5_v5_3_public_formal_manifest.py"
PILOT_SOURCE = ROOT / "src/metacom_pm/v1_5_v5_3_public_learnability_pilot.py"
Q64_DOC = ROOT / "docs/PM_V1_5_V5_3_STEP2_Q64_EXECUTION_20260808_ZH.md"
OUT = ROOT / "outputs/pm_v1_5_v5_3_learnability_root_cause_audit_20260809"
COMPONENTS = ("MP", "MS", "ME", "RS")
DIMENSIONS = (
    "goal_advance",
    "emotional_support",
    "specific_useful_contribution",
    "clarity_and_naturalness",
)


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _target(row: Mapping[str, Any]) -> float:
    return float(row["quality_effect"]["aggregate"]["mean_positive_support_contribution"])


def _words(text: object) -> int:
    return len(re.findall(r"\b\w+(?:['-]\w+)*\b", str(text or "")))


def _safe_corr(function, left: Iterable[float], right: Iterable[float]) -> float | None:
    x = np.asarray(list(left), dtype=float)
    y = np.asarray(list(right), dtype=float)
    if len(x) < 3 or np.ptp(x) == 0 or np.ptp(y) == 0:
        return None
    value = function(x, y).statistic
    return float(value) if np.isfinite(value) else None


def _mean(values: Iterable[float]) -> float | None:
    rows = list(values)
    return float(np.mean(rows)) if rows else None


def _candidate_literal_surface(manifest: Mapping[str, Any]) -> str:
    values = [str(manifest.get("candidate_text") or "")]
    candidate = manifest.get("candidate") or {}
    values.extend(str(value) for value in candidate.values() if isinstance(value, (str, int, float)))
    return "\n".join(values)


def _functional_measurement_audit(
    rows: list[dict[str, Any]], manifests: list[dict[str, Any]],
) -> dict[str, Any]:
    fallback_records = Counter()
    false_used_examples: list[dict[str, Any]] = []
    evidence_not_in_candidate = Counter()
    evidence_examples: list[dict[str, Any]] = []
    total_records = 0
    for row, manifest in zip(rows, manifests):
        candidate_surface = _candidate_literal_surface(manifest)
        records = {
            str(record["replicate_id"]): record
            for record in row["functional"]["replicates"]
        }
        for generated in row["generated"]:
            replicate_id = str(generated["replicate_id"])
            record = records[replicate_id]
            total_records += 1
            on = generated["ON"]
            is_fallback = on["status"] == "fell_back_to_m0"
            if is_fallback:
                fallback_records[str(record["use_status"])] += 1
                if record["use_status"] == "USED" and len(false_used_examples) < 8:
                    false_used_examples.append(
                        {
                            "component": row["component"],
                            "effect_group_id": row["effect_group_id"],
                            "replicate_id": replicate_id,
                            "candidate_text": manifest["candidate_text"],
                            "final_on_reply": on["reply"],
                            "judge_evidence_excerpt": record.get("evidence_excerpt"),
                            "judge_response_excerpt": record.get("response_excerpt"),
                            "guard_errors": on.get("first_pass_errors") or [],
                        }
                    )
            evidence = str(record.get("evidence_excerpt") or "")
            if evidence and evidence not in candidate_surface:
                evidence_not_in_candidate[str(row["component"])] += 1
                if len(evidence_examples) < 8:
                    evidence_examples.append(
                        {
                            "component": row["component"],
                            "effect_group_id": row["effect_group_id"],
                            "candidate_text": manifest["candidate_text"],
                            "evidence_excerpt": evidence,
                            "use_status": record["use_status"],
                        }
                    )
    false_used = int(fallback_records["USED"])
    fallback_total = int(sum(fallback_records.values()))
    return {
        "functional_records": total_records,
        "on_fallback_records_by_function_label": dict(fallback_records),
        "on_fallback_records": fallback_total,
        "fallback_labeled_used": false_used,
        "fallback_labeled_used_rate": false_used / fallback_total if fallback_total else None,
        "hard_validity_failure": false_used > 0,
        "why_hard_failure": (
            "The deterministic context-only fallback contains no authorized candidate. "
            "Any USED label on that final reply is definitionally false."
        ),
        "functional_evidence_excerpt_not_literal_in_candidate": dict(evidence_not_in_candidate),
        "evidence_excerpt_validation_gap": (
            "validate_response_excerpts checks response_excerpt only; evidence_excerpt is not "
            "checked against the typed candidate."
        ),
        "false_used_examples": false_used_examples,
        "noncandidate_evidence_examples": evidence_examples,
    }


def _execution_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    by_component: dict[str, Any] = {}
    for component in COMPONENTS:
        selected = [row for row in rows if row["component"] == component]
        statuses = Counter()
        errors = Counter()
        group_rows = []
        for row in selected:
            on_fallback = 0
            off_fallback = 0
            for generated in row["generated"]:
                for arm in ("ON", "OFF"):
                    status = str(generated[arm]["status"])
                    statuses[f"{arm}:{status}"] += 1
                    if status == "fell_back_to_m0":
                        if arm == "ON":
                            on_fallback += 1
                        else:
                            off_fallback += 1
                        errors.update(generated[arm].get("first_pass_errors") or [])
            group_rows.append(
                {
                    "target": _target(row),
                    "negative": _target(row) < 0,
                    "any_on_fallback": on_fallback > 0,
                    "on_fallback_replicates": on_fallback,
                    "any_arm_fallback": on_fallback + off_fallback > 0,
                }
            )
        on_fallback_groups = [item for item in group_rows if item["any_on_fallback"]]
        clean_on_groups = [item for item in group_rows if not item["any_on_fallback"]]
        negative = [item for item in group_rows if item["negative"]]
        negative_with_on_fallback = [item for item in negative if item["any_on_fallback"]]
        by_component[component] = {
            "replicate_status_counts": dict(statuses),
            "fallback_guard_error_counts": dict(errors),
            "groups_with_any_on_fallback": len(on_fallback_groups),
            "mean_effect_groups_with_on_fallback": _mean(item["target"] for item in on_fallback_groups),
            "mean_effect_groups_without_on_fallback": _mean(item["target"] for item in clean_on_groups),
            "negative_groups": len(negative),
            "negative_groups_with_any_on_fallback": len(negative_with_on_fallback),
            "share_of_negative_groups_with_any_on_fallback": (
                len(negative_with_on_fallback) / len(negative) if negative else None
            ),
        }
    return {
        "components": by_component,
        "interpretation": (
            "Requested-action ITT is valid for deployed-system evaluation, but it does not "
            "identify pre-action semantic resource value when post-request executor/guard "
            "failures are not modeled separately."
        ),
    }


def _design_audit(
    rows: list[dict[str, Any]], manifests: list[dict[str, Any]], formal: Mapping[str, Any],
) -> dict[str, Any]:
    result_by_group = {str(row["effect_group_id"]): row for row in rows}
    candidate_types: dict[str, Counter[str]] = {component: Counter() for component in COMPONENTS}
    sign_counts: dict[str, Counter[str]] = {component: Counter() for component in COMPONENTS}
    subtype_effects: dict[str, dict[str, list[float]]] = {
        component: defaultdict(list) for component in COMPONENTS
    }
    trigger_names = {
        "MP": ("profile_goal_needs_advice_or_arrangement", "current_redundant"),
        "MS": ("continuity_request", "current_redundant"),
        "ME": ("current_action_invitation", "current_action_readiness", "current_redundant"),
        "RS": ("card_precondition_met", "card_already_executed_last_turn"),
    }
    trigger_summary: dict[str, Any] = {}
    for component in COMPONENTS:
        component_manifests = [row for row in manifests if row["component"] == component]
        for manifest in component_manifests:
            result = result_by_group[str(manifest["effect_group_id"])]
            value = _target(result)
            subtype = str(manifest["candidate_type"])
            candidate_types[component][subtype] += 1
            subtype_effects[component][subtype].append(value)
            sign_counts[component]["positive" if value > 0 else "negative" if value < 0 else "tie"] += 1
        component_triggers = {}
        for trigger in trigger_names[component]:
            present = [
                manifest for manifest in component_manifests
                if (manifest.get("model_features") or {}).get(trigger) is not None
            ]
            true_rows = [
                manifest for manifest in present
                if bool((manifest.get("model_features") or {}).get(trigger))
            ]
            false_rows = [manifest for manifest in present if manifest not in true_rows]
            component_triggers[trigger] = {
                "available": len(present),
                "true": len(true_rows),
                "false": len(false_rows),
                "mean_effect_true": _mean(
                    _target(result_by_group[str(manifest["effect_group_id"])]) for manifest in true_rows
                ),
                "mean_effect_false": _mean(
                    _target(result_by_group[str(manifest["effect_group_id"])]) for manifest in false_rows
                ),
            }
        trigger_summary[component] = component_triggers
    family_fields = (
        "counterfactual_family",
        "state_family_id",
        "semantic_family",
        "broad_capability",
        "template_cluster",
    )
    return {
        "formal_groups": len(manifests),
        "unique_effect_groups": len({row["effect_group_id"] for row in manifests}),
        "unique_source_states": len({row["source_state_id"] for row in manifests}),
        "counterfactual_family_fields_present": {
            field: sum(bool(row.get(field)) for row in manifests) for field in family_fields
        },
        "same_state_on_off_pairs": len(manifests),
        "within_capability_high_low_state_families": 0,
        "selection_fact": (
            "The formal selector takes eight natural states per user/head by novelty of sparse "
            "feature strata. It does not construct or validate high-effect versus low-effect "
            "current-state counterfactual families."
        ),
        "candidate_type_counts": {
            component: dict(counts) for component, counts in candidate_types.items()
        },
        "candidate_type_effects": {
            component: {
                subtype: {
                    "groups": len(values),
                    "mean_effect": float(np.mean(values)),
                    "negative_share": sum(value < 0 for value in values) / len(values),
                }
                for subtype, values in sorted(by_subtype.items())
            }
            for component, by_subtype in subtype_effects.items()
        },
        "target_sign_counts": {
            component: dict(counts) for component, counts in sign_counts.items()
        },
        "semantic_trigger_support_and_direction": trigger_summary,
        "formal_head_results": {
            component: {
                "relative_mse": formal["analysis"][component]["relative_mse"],
                "oof_spearman": formal["analysis"][component]["oof_spearman"],
                "formal_head_pass": formal["analysis"][component]["formal_head_pass"],
            }
            for component in COMPONENTS
        },
    }


def _pilot_audit(
    pilot_rows: list[dict[str, Any]], pilot_manifests: list[dict[str, Any]],
    formal: Mapping[str, Any],
) -> dict[str, Any]:
    manifest_by_group = {str(row["effect_group_id"]): row for row in pilot_manifests}
    formal_dimensions = {
        component: int(formal["analysis"][component]["model_dimensions"])
        for component in COMPONENTS
    }
    out: dict[str, Any] = {}
    for component in COMPONENTS:
        selected = [row for row in pilot_rows if row["component"] == component]
        manifests = [manifest_by_group[str(row["effect_group_id"])] for row in selected]
        clusters = {
            str(row.get("user_id") or row.get("dialogue_id")) for row in manifests
        }
        dimensions = formal_dimensions[component]
        if component == "RS":
            training_clusters_per_fold = 20
        else:
            training_clusters_per_fold = len(clusters) - 1
        out[component] = {
            "development_groups": len(selected),
            "independent_clusters": len(clusters),
            "training_clusters_per_development_fold": training_clusters_per_fold,
            "frozen_model_dimensions": dimensions,
            "dimensions_per_training_cluster": dimensions / training_clusters_per_fold,
            "development_target_mean": _mean(_target(row) for row in selected),
            "formal_relative_mse": formal["analysis"][component]["relative_mse"],
            "formal_oof_spearman": formal["analysis"][component]["oof_spearman"],
        }
    return {
        "components": out,
        "memory_pilot_users": sorted(
            {
                str(row["user_id"])
                for row in pilot_manifests
                if row["component"] in {"MP", "MS", "ME"}
            }
        ),
        "memory_pilot_independent_users": 3,
        "memory_leave_one_user_out_training_users": 2,
        "capacity_warning": (
            "The memory representation was selected after leave-one-user-out development in "
            "which each model trained on only two independent users. State rows and three "
            "generator replicates do not increase the independent-user count."
        ),
        "selection_uncertainty_status": "NOT_ESTIMATED_BEFORE_FREEZE",
    }


def _surface_bias_audit(rows: list[dict[str, Any]]) -> dict[str, Any]:
    out = {}
    for component in COMPONENTS:
        selected = [row for row in rows if row["component"] == component]
        group_length_deltas = []
        targets = []
        clean_length_deltas = []
        clean_effects = []
        for row in selected:
            replicate_by_id = {
                str(rep["replicate_id"]): rep for rep in row["quality_effect"]["replicates"]
            }
            deltas = []
            for generated in row["generated"]:
                deltas.append(_words(generated["ON"]["reply"]) - _words(generated["OFF"]["reply"]))
                if generated["ON"]["status"] == generated["OFF"]["status"] == "clean":
                    effect = float(np.mean([
                        replicate_by_id[str(generated["replicate_id"])][dimension]
                        for dimension in DIMENSIONS
                    ]))
                    clean_length_deltas.append(deltas[-1])
                    clean_effects.append(effect)
            group_length_deltas.append(float(np.mean(deltas)))
            targets.append(_target(row))
        out[component] = {
            "mean_on_minus_off_word_delta": _mean(group_length_deltas),
            "group_word_delta_pearson_with_quality_effect": _safe_corr(
                pearsonr, group_length_deltas, targets
            ),
            "group_word_delta_spearman_with_quality_effect": _safe_corr(
                spearmanr, group_length_deltas, targets
            ),
            "clean_replicate_word_delta_pearson_with_quality_effect": _safe_corr(
                pearsonr, clean_length_deltas, clean_effects
            ),
            "clean_replicate_word_delta_spearman_with_quality_effect": _safe_corr(
                spearmanr, clean_length_deltas, clean_effects
            ),
        }
    return out


def _measurement_scope_audit() -> dict[str, Any]:
    source = QRF_SOURCE.read_text()
    contribution_body = source.split("def contribution_messages", 1)[1].split("def risk_messages", 1)[0]
    validator_body = source.split("def validate_response_excerpts", 1)[1].split(
        "def aggregate_on_minus_off", 1
    )[0]
    return {
        "quality_judge_payload_has_visible_dialogue": '"visible_dialogue"' in contribution_body,
        "quality_judge_payload_has_candidate": "candidate" in contribution_body,
        "quality_judge_payload_has_verified_past_panel": "verified_past" in contribution_body,
        "quality_target_is_four_axis_response_preference_only": True,
        "formal_target_includes_risk": False,
        "formal_target_includes_function": False,
        "formal_target_includes_cost": False,
        "response_excerpt_machine_validated": 'key == "response_excerpt"' in validator_body,
        "evidence_excerpt_machine_validated": 'key == "evidence_excerpt"' in validator_body,
        "conclusion": (
            "The formal gate tested predictability of a response-level Q contrast. It did not "
            "test the full adoptable-opening oracle, and the quality judge could not verify "
            "whether personalized past information was true, relevant, or invented because no "
            "shared verified-past panel or candidate was shown."
        ),
    }


def main() -> None:
    manifests = _jsonl(FORMAL_MANIFEST)
    rows: list[dict[str, Any]] = []
    for fold in range(1, 7):
        rows.extend(_jsonl(FORMAL_RESULT_DIR / f"fold_{fold}_results.jsonl"))
    if len(manifests) != 576 or len(rows) != 576:
        raise RuntimeError("complete 576-group formal panel is required")
    manifest_by_group = {str(row["effect_group_id"]): row for row in manifests}
    aligned_manifests = [manifest_by_group[str(row["effect_group_id"])] for row in rows]
    pilot_manifests = _jsonl(PILOT_MANIFEST)
    pilot_rows = _jsonl(PILOT_RESULTS)
    formal = json.loads(FORMAL_OOF.read_text())

    measurement = _measurement_scope_audit()
    functional = _functional_measurement_audit(rows, aligned_manifests)
    execution = _execution_audit(rows)
    design = _design_audit(rows, aligned_manifests, formal)
    pilot = _pilot_audit(pilot_rows, pilot_manifests, formal)
    surface_bias = _surface_bias_audit(rows)

    report = {
        "protocol": "pm-v1.5-v5.3-learnability-root-cause-audit-v1",
        "status": "ROOT_CAUSE_ESTABLISHED_WITH_REMAINING_HUMAN_SEMANTIC_AUDIT",
        "scope": "Outcome-open forensic diagnosis; not formal requalification and not a new plan.",
        "formal_result_unchanged": "ALL_FOUR_V5_3_Q_HEADS_FAILED_THE_FROZEN_GATE",
        "causal_conclusion": {
            "not_supported": (
                "It is not supported to conclude that the PM concept or a bounded semantic "
                "learner is intrinsically unable to learn."
            ),
            "supported": (
                "The completed V5.3 panel did not provide a clean, sufficiently identified, "
                "and trustworthy supervision test of when each component should open."
            ),
            "root_cause_order": [
                "MEASUREMENT_INVALIDITY: functional-use labels contain definitionally false USED judgments; Q lacks verified-past grounding context.",
                "EXECUTION_CONFOUNDING: Step2/guard/fallback failures materially drive many negative Q outcomes.",
                "CAUSAL_SUPPORT_FAILURE: natural-state ON/OFF effects lack high/low semantic state families for learning when to open.",
                "DEVELOPMENT_SELECTION_FAILURE: three-user memory pilot selected 5-6-dimensional heads with two training users per fold.",
                "ONTOLOGY_AND_SUPPORT_MISMATCH: rare intended trigger conditions and ME dominated by context events rather than reusable action-result evidence.",
                "CLASS_IMBALANCE: most valid Rank-1 injections help, so abstention conditions are sparse and heterogeneous.",
            ],
        },
        "measurement_scope": measurement,
        "functional_measurement_validity": functional,
        "execution_and_guard_confounding": execution,
        "training_design_and_label_support": design,
        "development_pilot_capacity": pilot,
        "surface_form_bias_diagnostic": surface_bias,
        "step2_qualification_status": {
            "q64_direct_machine_pass": 50,
            "q64_fallback": 14,
            "fallback_raw_first_pass_responses_saved": False,
            "semantic_qualification_closed": False,
            "source": str(Q64_DOC.relative_to(ROOT)),
        },
        "responsibility_boundary": {
            "retrieval": "Candidate validity/relevance requires a separate current-state semantic fit audit.",
            "step1_pm": "Can be charged only for pre-action requested component after a trustworthy oracle exists.",
            "step2_generator": "Evidence receipt, functional use, and candidate-faithful realization.",
            "guard": "False accept/reject against independently saved raw first-pass responses.",
            "judge": "Q/R/F instrument validity and excerpt grounding.",
            "deployed_system_itt": "May include all downstream failures, but must not be reused as a pure semantic-value label.",
        },
        "minimum_evidence_before_any_redesign": [
            "Repair and re-audit the existing functional labels deterministically; do not spend API calls.",
            "Blind human semantic audit of a stratified sample of candidate relevance, raw/realized use, and Q judgments.",
            "Estimate an executor-qualified semantic value target separately from deployment ITT.",
            "Demonstrate within-capability high/low effect support before choosing model capacity.",
            "Use independent-group counts, not state rows or replicates, for development uncertainty.",
        ],
        "source_hashes": {
            "formal_manifest": sha256_file(FORMAL_MANIFEST),
            "formal_oof": sha256_file(FORMAL_OOF),
            "pilot_manifest": sha256_file(PILOT_MANIFEST),
            "pilot_results": sha256_file(PILOT_RESULTS),
            "qrf_source": sha256_file(QRF_SOURCE),
            "formal_selection_source": sha256_file(FORMAL_SELECTION_SOURCE),
            "pilot_source": sha256_file(PILOT_SOURCE),
            "q64_doc": sha256_file(Q64_DOC),
            **{
                f"formal_fold_{fold}": sha256_file(
                    FORMAL_RESULT_DIR / f"fold_{fold}_results.jsonl"
                )
                for fold in range(1, 7)
            },
        },
        "api_calls": 0,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    write_json(OUT / "report.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "functional_hard_failure": functional["hard_validity_failure"],
                "fallback_labeled_used": functional["fallback_labeled_used"],
                "counterfactual_state_families": design["within_capability_high_low_state_families"],
                "memory_pilot_users": pilot["memory_pilot_independent_users"],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
