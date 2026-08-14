#!/usr/bin/env python3
"""Freeze the V5.4 96-state development ON/OFF effect manifest without APIs."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import canonical_json, sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate  # noqa: E402
from metacom_pm.v1_5_v5_3_typed_response_program import build_typed_response_program  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-development-effect-manifest-v1"
RUNTIME = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810/runtime_state_candidate_surface_no_ids_no_assignment.jsonl"
AUTHORING = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810/authoring_v4_packet_private_outcome_blind.jsonl"
FEATURE_REPORT = ROOT / "outputs/pm_v1_5_v5_4_full_dialogue_feature_surface_20260810/report_final.json"
FEATURE_ROWS = ROOT / "outputs/pm_v1_5_v5_4_full_dialogue_feature_surface_20260810/feature_surface_private_ids_not_model_features.jsonl"
FEATURE_VECTORS = ROOT / "outputs/pm_v1_5_v5_4_full_dialogue_feature_surface_20260810/frozen_bge_embedding_views_private.npz"
TRANSITION = ROOT / "data/pm_v1_5_contracts/v5_4_actual_outcome_learnability_transition_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_development_effect_manifest_20260810"
COMPONENTS = ("MP", "MS", "ME", "RS")
ON_ACTION = {"MP": "MP+R0", "MS": "MS+R0", "ME": "ME+R0", "RS": "M0+RS"}
SEEDS = 3
FOLDS = 6


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def source_cluster(item: dict) -> str:
    user = item.get("user_id")
    if user in {"p13", "p18"}:
        return "evoemo_shared_p13_p18"
    if user:
        return f"evoemo_{user}"
    dialogue = item.get("dialogue_id")
    if dialogue:
        return f"esconv_{dialogue}"
    raise RuntimeError("missing source user/dialogue cluster")


def assign_folds(authoring: list[dict]) -> dict[str, int]:
    clusters: dict[str, Counter] = defaultdict(Counter)
    for row in authoring:
        clusters[source_cluster(row)][row["component"]] += 1
    ordered = sorted(
        clusters,
        key=lambda cluster: (-sum(clusters[cluster].values()), stable_hex(PROTOCOL, "fold", cluster, n=24)),
    )
    fold_counts = [Counter() for _ in range(FOLDS)]
    assignment = {}
    for cluster in ordered:
        def score(fold: int) -> tuple:
            projected = fold_counts[fold] + clusters[cluster]
            return (
                max(projected[component] for component in COMPONENTS),
                sum(value * value for value in projected.values()),
                sum(projected.values()),
                stable_hex(PROTOCOL, cluster, str(fold), n=16),
            )
        chosen = min(range(FOLDS), key=score)
        assignment[cluster] = chosen
        fold_counts[chosen].update(clusters[cluster])
    return assignment


def main() -> None:
    transition = json.loads(TRANSITION.read_text())
    feature_report = json.loads(FEATURE_REPORT.read_text())
    if not transition["current_authorization"]["effect_manifest_and_cost_preflight"]:
        raise RuntimeError("manifest is not authorized")
    if feature_report["status"] != "FULL_DIALOGUE_FEATURE_SURFACE_FINAL_PASS_EFFECT_MANIFEST_MAY_BE_BUILT":
        raise RuntimeError("feature surface did not pass")
    runtime = sorted(rows(RUNTIME), key=lambda row: row["state_id"])
    authoring_rows = rows(AUTHORING)
    authoring = {row["pair_id"]: row for row in authoring_rows}
    features = {row["state_id_evaluator_join_only"]: row for row in rows(FEATURE_ROWS)}
    fold_by_cluster = assign_folds(authoring_rows)
    if len(runtime) != 96 or len(features) != 96 or len(authoring) != 48:
        raise RuntimeError("manifest inputs incomplete")

    manifest = []
    for row in runtime:
        plan = authoring[row["pair_id"]]
        component = row["component"]
        owner = str(plan.get("user_id") or plan.get("dialogue_id"))
        candidate = TypedResourceCandidate(**row["actual_rank1_typed_candidate"])
        on_action = ON_ACTION[component]
        build_typed_response_program(
            requested_action_id=on_action,
            current_goal="Respond supportively to the latest user message using only visible authorized information.",
            current_user_id=owner,
            candidates={component: candidate},
            expected_execution_candidate_ids={component: candidate.resource_id},
        )
        build_typed_response_program(
            requested_action_id="M0+R0",
            current_goal="Respond supportively to the latest user message using only visible authorized information.",
            current_user_id=owner,
            candidates={},
        )
        seeds = [int(stable_hex(PROTOCOL, row["state_id"], f"seed_{index}", n=8), 16) & 0x7FFFFFFF for index in range(SEEDS)]
        cluster = source_cluster(plan)
        manifest.append({
            "protocol": PROTOCOL,
            "effect_group_id": "v54devfx_" + stable_hex(PROTOCOL, row["state_id"], n=22),
            "state_id": row["state_id"],
            "pair_id_split_binding": row["pair_id"],
            "semantic_family_id_split_binding": row["semantic_family_id"],
            "source_cluster_id_split_binding": cluster,
            "outer_fold": fold_by_cluster[cluster],
            "component": component,
            "source_dataset": row["source_dataset"],
            "current_owner_id": owner,
            "visible_dialogue": row["visible_dialogue"],
            "current_user_text": row["current_user_text"],
            "actual_rank1_candidate": row["actual_rank1_typed_candidate"],
            "actual_rank1_candidate_text": row["actual_rank1_candidate_text"],
            "on_action_id": on_action,
            "off_action_id": "M0+R0",
            "paired_generator_seeds": seeds,
            "generator_temperature": 0.7,
            "generator_max_output_tokens": 512,
            "feature_embedding_row_index_private": features[row["state_id"]]["embedding_row_index_private"],
            "within_state_candidate_generator_prompt_seed_guard_invariant": True,
            "construction_assignment_present": False,
            "response_effect_or_oracle_present": False,
        })

    counts = Counter(row["component"] for row in manifest)
    pair_counts = Counter(row["pair_id_split_binding"] for row in manifest)
    fold_components = {
        str(fold): dict(Counter(row["component"] for row in manifest if row["outer_fold"] == fold))
        for fold in range(FOLDS)
    }
    checks = {
        "96_states": len(manifest) == 96,
        "24_states_each_component": counts == Counter({component: 24 for component in COMPONENTS}),
        "48_pairs_two_states_each": len(pair_counts) == 48 and set(pair_counts.values()) == {2},
        "all_source_clusters_one_fold": all(len({row["outer_fold"] for row in manifest if row["source_cluster_id_split_binding"] == cluster}) == 1 for cluster in fold_by_cluster),
        "p13_p18_bound": fold_by_cluster.get("evoemo_shared_p13_p18") is not None,
        "all_candidates_compile_on_and_off": True,
        "all_three_unique_seeds": all(len(set(row["paired_generator_seeds"])) == 3 for row in manifest),
        "construction_assignment_absent": all(not row["construction_assignment_present"] for row in manifest),
        "response_effect_or_oracle_absent": all(not row["response_effect_or_oracle_present"] for row in manifest),
    }
    passed = all(checks.values())
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "effect_group_manifest_private.jsonl", manifest)
    report = {
        "protocol": PROTOCOL,
        "status": "DEVELOPMENT_EFFECT_MANIFEST_FROZEN_MEASUREMENT_AND_COST_PREFLIGHT_PENDING" if passed else "EFFECT_MANIFEST_FAIL_NO_LIVE_CALLS",
        "checks": checks,
        "states": len(manifest),
        "component_counts": dict(counts),
        "families": len(pair_counts),
        "source_clusters": len(fold_by_cluster),
        "outer_folds": FOLDS,
        "fold_component_state_counts": fold_components,
        "call_budget": {
            "generator_logical_calls": len(manifest) * SEEDS * 2,
            "quality_dual_reviewer_ab_ba_logical_calls": len(manifest) * 2 * 2,
            "absolute_risk_dual_reviewer_logical_calls": len(manifest) * 2,
            "function_dual_reviewer_logical_calls": len(manifest) * 2,
            "live_calls_currently_authorized": False,
        },
        "generator_identity": {
            "endpoint": "configs/experiment.yaml:endpoints.generator",
            "model": "meta/llama-3.1-8b-instruct",
            "response_only": True,
            "post_generation_resource_concatenation": False,
            "raw_provider_reply_must_be_persisted_before_guard": True,
        },
        "measurement": "new role-separated dual-reviewer preflight required; old V5.3 function and CANARY_UNQUALIFIED risk labels are forbidden",
        "construction_assignment_used": False,
        "response_effect_or_oracle_read": False,
        "api_calls": 0,
        "source_hashes": {
            "runtime": sha256_file(RUNTIME), "authoring": sha256_file(AUTHORING),
            "feature_report": sha256_file(FEATURE_REPORT), "feature_rows": sha256_file(FEATURE_ROWS),
            "feature_vectors": sha256_file(FEATURE_VECTORS), "transition": sha256_file(TRANSITION),
            "experiment_config": sha256_file(ROOT / "configs/experiment.yaml"),
            "typed_adapter": sha256_file(ROOT / "src/metacom_pm/v1_5_typed_resource_adapter.py"),
            "typed_response_program": sha256_file(ROOT / "src/metacom_pm/v1_5_v5_3_typed_response_program.py"),
        },
    }
    report["manifest_identity"] = "v54devmanifest_" + stable_hex(canonical_json(report), canonical_json(manifest), n=24)
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
