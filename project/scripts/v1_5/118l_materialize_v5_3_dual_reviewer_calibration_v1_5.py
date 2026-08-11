#!/usr/bin/env python3
"""Freeze a new 64-group, outcome-hidden dual-reviewer calibration packet.

Selection balances only component, candidate subtype, fold, user, redundancy,
and reviewability.  It never reads Q, F, risk, or model predictions to choose a
group.  Reviewer A and B receive identical packets and separate blank ledgers.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-dual-reviewer-calibration-v1"
COMPONENTS = ("MP", "MS", "ME", "RS")
MANIFEST = (
    ROOT
    / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/"
    "effect_group_manifest_private.jsonl"
)
RESULT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809/shards"
PRIOR_AUDIT_PACKET = (
    ROOT
    / "outputs/pm_v1_5_v5_3_blind_semantic_audit_20260809/"
    "private_outcome_key_do_not_open_until_review.jsonl"
)
OUT = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _all_clean(result: dict[str, Any]) -> bool:
    return all(
        generated[arm]["status"] == "clean"
        for generated in result["generated"]
        for arm in ("ON", "OFF")
    )


def _cluster_id(row: dict[str, Any]) -> str:
    return str(row.get("user_id") or row.get("dialogue_id"))


def _select_balanced(
    rows: list[dict[str, Any]], *, count: int
) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    subtype: Counter[str] = Counter()
    fold: Counter[int] = Counter()
    user: Counter[str] = Counter()
    redundant: Counter[bool] = Counter()
    remaining = list(rows)
    while len(selected) < count:
        if not remaining:
            raise RuntimeError(f"only {len(selected)} balanced rows available")

        def key(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
            return (
                subtype[str(row["candidate_type"])],
                fold[int(row["outer_fold"])],
                user[_cluster_id(row)],
                redundant[bool(row["model_features"].get("current_redundant"))],
                stable_hex(PROTOCOL, row["effect_group_id"], n=24),
            )

        chosen = min(remaining, key=key)
        remaining.remove(chosen)
        selected.append(chosen)
        subtype[str(chosen["candidate_type"])] += 1
        fold[int(chosen["outer_fold"])] += 1
        user[_cluster_id(chosen)] += 1
        redundant[bool(chosen["model_features"].get("current_redundant"))] += 1
    return selected


def _blank_judgment(calibration_id: str, replicates: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "protocol": PROTOCOL,
        "calibration_id": calibration_id,
        "reviewer_id": "",
        "candidate_truth": "",
        "candidate_current_evidence_excerpt": "",
        "candidate_resource_evidence_excerpt": "",
        "candidate_rationale": "",
        "replicates": [
            {
                "replicate_id": row["replicate_id"],
                "functional_execution": "",
                "candidate_contribution_excerpt": "",
                "on_response_excerpt": "",
                "owner_time_boundary_correct": "",
                "guard_acceptance": "",
                "response_preference": "",
                "preference_rationale": "",
                "on_absolute_risk_events": [],
                "off_absolute_risk_events": [],
                "resource_risk_attribution": "",
            }
            for row in replicates
        ],
        "reviewer_uncertainty_note": "",
    }


def main() -> None:
    manifests = _jsonl(MANIFEST)
    results: list[dict[str, Any]] = []
    result_paths: list[Path] = []
    for fold_index in range(1, 7):
        path = RESULT_DIR / f"fold_{fold_index}_results.jsonl"
        result_paths.append(path)
        results.extend(_jsonl(path))
    result_by_group = {str(row["effect_group_id"]): row for row in results}
    prior_groups = {
        str(row["effect_group_id"]) for row in _jsonl(PRIOR_AUDIT_PACKET)
    }

    selected: list[dict[str, Any]] = []
    for component in COMPONENTS:
        eligible = [
            row
            for row in manifests
            if row["component"] == component
            and str(row["effect_group_id"]) not in prior_groups
            and _all_clean(result_by_group[str(row["effect_group_id"])])
        ]
        selected.extend(_select_balanced(eligible, count=16))
    if len(selected) != 64 or len({row["effect_group_id"] for row in selected}) != 64:
        raise RuntimeError("exactly 64 unique calibration groups required")

    packet: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []
    templates_a: list[dict[str, Any]] = []
    templates_b: list[dict[str, Any]] = []
    for manifest in selected:
        effect_group_id = str(manifest["effect_group_id"])
        result = result_by_group[effect_group_id]
        calibration_id = "cal_" + stable_hex(PROTOCOL, effect_group_id, n=20)
        replicates = [
            {
                "replicate_id": row["replicate_id"],
                "on_reply": row["ON"]["reply"],
                "off_reply": row["OFF"]["reply"],
            }
            for row in result["generated"]
        ]
        packet.append(
            {
                "protocol": PROTOCOL,
                "calibration_id": calibration_id,
                "component": manifest["component"],
                "candidate_type": manifest["candidate_type"],
                "visible_dialogue": manifest["visible_dialogue"],
                "current_user_text": manifest["current_user_text"],
                "verified_past_panel": {
                    "typed_candidate": manifest["candidate"],
                    "candidate_text": manifest["candidate_text"],
                    "rule": "strictly-prior candidate; do not infer facts absent from this panel or the visible dialogue",
                },
                "replicates": replicates,
            }
        )
        blank = _blank_judgment(calibration_id, replicates)
        templates_a.append({**blank, "reviewer_id": "REVIEWER_A"})
        templates_b.append({**blank, "reviewer_id": "REVIEWER_B"})
        private.append(
            {
                "calibration_id": calibration_id,
                "effect_group_id": effect_group_id,
                "state_id": manifest["state_id"],
                "component": manifest["component"],
                "independent_cluster_id": _cluster_id(manifest),
                "user_id": manifest.get("user_id"),
                "dialogue_id": manifest.get("dialogue_id"),
                "outer_fold": manifest["outer_fold"],
                "candidate_type": manifest["candidate_type"],
                "current_redundant_machine_diagnostic": manifest["model_features"].get(
                    "current_redundant"
                ),
                "original_q_effect": result["quality_effect"],
                "original_function_judgments": result["functional"],
                "original_risk": result["risk"],
                "original_risk_instrument_status": result["risk_instrument_status"],
            }
        )

    packet.sort(key=lambda row: stable_hex(PROTOCOL, "blind_order", row["calibration_id"], n=24))
    order = {row["calibration_id"]: index for index, row in enumerate(packet)}
    templates_a.sort(key=lambda row: order[row["calibration_id"]])
    templates_b.sort(key=lambda row: order[row["calibration_id"]])
    private.sort(key=lambda row: row["calibration_id"])

    OUT.mkdir(parents=True, exist_ok=True)
    packet_path = OUT / "review_packet_blind.jsonl"
    a_path = OUT / "reviewer_A_template_blank.jsonl"
    b_path = OUT / "reviewer_B_template_blank.jsonl"
    private_path = OUT / "private_outcome_key_do_not_open_until_both_reviews_freeze.jsonl"
    write_jsonl(packet_path, packet)
    write_jsonl(a_path, templates_a)
    write_jsonl(b_path, templates_b)
    write_jsonl(private_path, private)

    rubric = """# V5.3 双 reviewer 校准规则（冻结版）

两位 reviewer 独立完成同一 64 组；在两份 judgment 文件完成、验证并哈希冻结前，禁止读取 private key。

- `candidate_truth`：只能填 `VALID_APPLICABLE`、`VALID_REDUNDANT`、`VALID_NOT_USEFUL`、`INVALID_WRONG_OWNER_TIME_EVENT`、`UNRESOLVED`。
- `functional_execution`：只能填 `FUNCTIONAL`、`SURFACE_ECHO_ONLY`、`NOT_USED_FINAL`、`BOUNDARY_FAILURE`、`UNRESOLVED`。FUNCTIONAL 必须指出 candidate contribution 与 ON reply 中承担该功能的 span；主题相似或复述不算。
- `owner_time_boundary_correct`：只能填 `YES`、`NO`、`UNRESOLVED`。
- `guard_acceptance`：这些样本均被 guard 接受；填 `TRUE_ACCEPT`、`FALSE_ACCEPT` 或 `UNRESOLVED`。
- `response_preference`：只比较当前支持回复，填 `ON_BETTER`、`OFF_BETTER`、`TIE`、`UNRESOLVED`；不要因为成本更低或候选被使用就偏好 ON。
- 风险事件：分别记录两臂明确发生的 `WRONG_OWNER`、`FUTURE_OR_PRIVATE_FABRICATION`、`EXPLICIT_BOUNDARY_VIOLATION`、`EXCESSIVE_DIRECTIVENESS_OR_BURDEN`；无事件用空数组。`resource_risk_attribution` 填 `SAFE`、`UNSAFE` 或 `UNRESOLVED`。
- 所有 excerpt 必须逐字来自 packet。证据不足时填 UNRESOLVED，不得猜测。
"""
    (OUT / "REVIEW_RUBRIC_ZH.md").write_text(rubric, encoding="utf-8")
    # The rubric is a newly materialized immutable artifact; scripts never edit
    # existing user data or formal outcomes.

    report = {
        "protocol": PROTOCOL,
        "status": "PACKET_FROZEN_AWAITING_TWO_INDEPENDENT_REVIEWS",
        "groups": len(packet),
        "replicates": sum(len(row["replicates"]) for row in packet),
        "component_counts": dict(Counter(row["component"] for row in packet)),
        "candidate_type_counts": dict(Counter(
            f"{row['component']}:{row['candidate_type']}" for row in packet
        )),
        "prior_single_reviewer_groups_excluded": len(prior_groups),
        "selection_fields_used": [
            "component",
            "candidate_type",
            "outer_fold",
            "user_id",
            "current_redundant_machine_diagnostic",
            "both_arms_clean_for_reviewability"
        ],
        "selection_fields_forbidden_and_not_used": [
            "Q",
            "F",
            "risk",
            "OOF prediction",
            "manual preference",
            "effect sign"
        ],
        "unblinding_gate": "both reviewer ledgers complete, schema-valid, and hash-frozen",
        "agreement_gates": {
            "candidate_clear_applicability": {"raw_agreement_min": 0.80, "cohen_kappa_min": 0.60},
            "functional_qualified": {"raw_agreement_min": 0.80, "cohen_kappa_min": 0.60},
            "response_preference_direction": {"raw_agreement_min": 0.70, "cohen_kappa_min": 0.40}
        },
        "hashes": {
            "review_packet": sha256_file(packet_path),
            "reviewer_A_template_blank": sha256_file(a_path),
            "reviewer_B_template_blank": sha256_file(b_path),
            "private_key": sha256_file(private_path),
            "formal_manifest": sha256_file(MANIFEST),
            **{f"formal_result_fold_{index}": sha256_file(path) for index, path in enumerate(result_paths, start=1)},
        },
        "api_calls": 0,
    }
    write_json(OUT / "manifest.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
