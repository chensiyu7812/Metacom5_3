#!/usr/bin/env python3
"""Freeze a fresh 64-group role-decomposed V5.3 calibration V2.

The selection excludes every group used by the earlier 32-group audit and
64-group combined calibration.  It uses only pre-treatment manifest fields.
Four role packets are then materialized so candidate suitability, functional
execution, quality preference, and absolute risk cannot influence one another.
ON/OFF identity is randomized for quality/risk and kept only in the private
key, which must remain closed until all reviewer ledgers are hash-frozen.
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import re
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402


PROTOCOL = "pm-v1.5-v5.3-role-decomposed-calibration-v2"
COMPONENTS = ("MP", "MS", "ME", "RS")
MANIFEST = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/effect_group_manifest_private.jsonl"
RESULT_DIR = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809/shards"
PRIOR_32 = ROOT / "outputs/pm_v1_5_v5_3_blind_semantic_audit_20260809/private_outcome_key_do_not_open_until_review.jsonl"
PRIOR_64 = ROOT / "outputs/pm_v1_5_v5_3_dual_reviewer_calibration_20260810/private_outcome_key_do_not_open_until_both_reviews_freeze.jsonl"
OUT = ROOT / "outputs/pm_v1_5_v5_3_role_decomposed_calibration_v2_20260810"


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _cluster_id(row: dict[str, Any]) -> str:
    return str(row.get("user_id") or row.get("dialogue_id"))


def _diagnostic_stratum(row: dict[str, Any]) -> str:
    features = row["model_features"]
    if bool(features.get("current_redundant")):
        return "EXPECTED_DO_NOT_OPEN_LIKE"
    component = str(row["component"])
    if component == "MP":
        signal = features.get("preference_applies_to_response_act")
        if signal is None:
            signal = features.get("profile_goal_needs_advice_or_arrangement")
    elif component == "MS":
        signal = features.get("continuity_request")
    elif component == "ME":
        signal = features.get("current_action_invitation")
    else:
        signal = features.get("card_precondition_met")
    if signal is True:
        return "EXPECTED_OPEN_LIKE"
    if signal is False:
        return "EXPECTED_DO_NOT_OPEN_LIKE"
    return "EXPECTED_AMBIGUOUS"


def _select(rows: list[dict[str, Any]], *, count: int) -> list[dict[str, Any]]:
    selected: list[dict[str, Any]] = []
    subtype: Counter[str] = Counter()
    fold: Counter[int] = Counter()
    cluster: Counter[str] = Counter()
    stratum: Counter[str] = Counter()
    remaining = list(rows)
    while len(selected) < count:
        if not remaining:
            raise RuntimeError(f"only {len(selected)} rows available")

        def key(row: dict[str, Any]) -> tuple[int, int, int, int, str]:
            return (
                stratum[_diagnostic_stratum(row)],
                subtype[str(row["candidate_type"])],
                fold[int(row["outer_fold"])],
                cluster[_cluster_id(row)],
                stable_hex(PROTOCOL, row["effect_group_id"], n=24),
            )

        chosen = min(remaining, key=key)
        remaining.remove(chosen)
        selected.append(chosen)
        stratum[_diagnostic_stratum(chosen)] += 1
        subtype[str(chosen["candidate_type"])] += 1
        fold[int(chosen["outer_fold"])] += 1
        cluster[_cluster_id(chosen)] += 1
    return selected


def _sentences(text: str, *, prefix: str) -> list[dict[str, str]]:
    pieces = [
        match.group(0).strip()
        for match in re.finditer(r"[^.!?]+(?:[.!?]+|$)", text)
        if match.group(0).strip()
    ]
    return [{"evidence_id": f"{prefix}_{index}", "text": value} for index, value in enumerate(pieces, start=1)]


def _dialogue_turns(dialogue: list[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "evidence_id": f"TURN_{index}",
            "role": str(turn["role"]),
            "text": str(turn["content"]),
        }
        for index, turn in enumerate(dialogue, start=1)
    ]


def main() -> None:
    manifests = _jsonl(MANIFEST)
    prior_groups = {
        str(row["effect_group_id"])
        for path in (PRIOR_32, PRIOR_64)
        for row in _jsonl(path)
    }
    selected: list[dict[str, Any]] = []
    available_strata: dict[str, dict[str, int]] = {}
    for component in COMPONENTS:
        eligible = [
            row for row in manifests
            if row["component"] == component
            and str(row["effect_group_id"]) not in prior_groups
        ]
        available_strata[component] = dict(Counter(_diagnostic_stratum(row) for row in eligible))
        selected.extend(_select(eligible, count=16))
    if len(selected) != 64 or len({row["effect_group_id"] for row in selected}) != 64:
        raise RuntimeError("exactly 64 fresh unique groups required")

    result_paths = [RESULT_DIR / f"fold_{fold}_results.jsonl" for fold in range(1, 7)]
    results = [row for path in result_paths for row in _jsonl(path)]
    by_group = {str(row["effect_group_id"]): row for row in results}
    if not {str(row["effect_group_id"]) for row in selected}.issubset(by_group):
        raise RuntimeError("selected group missing result")

    candidate_packet: list[dict[str, Any]] = []
    function_packet: list[dict[str, Any]] = []
    quality_packet: list[dict[str, Any]] = []
    risk_packet: list[dict[str, Any]] = []
    selection_audit: list[dict[str, Any]] = []
    private: list[dict[str, Any]] = []

    for manifest in selected:
        effect_group_id = str(manifest["effect_group_id"])
        result = by_group[effect_group_id]
        calibration_id = "rdcal_" + stable_hex(PROTOCOL, effect_group_id, n=20)
        turns = _dialogue_turns(manifest["visible_dialogue"])
        candidate = {
            "evidence_id": "CANDIDATE_TEXT",
            "component": manifest["component"],
            "candidate_type": manifest["candidate_type"],
            "text": manifest["candidate_text"],
            "typed_metadata": manifest["candidate"],
        }
        base = {
            "protocol": PROTOCOL,
            "calibration_id": calibration_id,
            "component": manifest["component"],
        }
        candidate_packet.append({
            **base,
            "visible_dialogue": turns,
            "candidate": candidate,
            "instruction_boundary": "judge current applicability only; no replies or outcomes are present",
        })

        function_replicates = []
        quality_replicates = []
        risk_replicates = []
        arm_map: dict[str, Any] = {}
        for generated in result["generated"]:
            replicate_id = str(generated["replicate_id"])
            on_reply = str(generated["ON"]["reply"])
            off_reply = str(generated["OFF"]["reply"])
            function_replicates.append({
                "replicate_id": replicate_id,
                "candidate": candidate,
                "response_sentences": _sentences(on_reply, prefix="RESPONSE_SENTENCE"),
                "instruction_boundary": "judge whether this response functionally realizes the candidate; no OFF reply or preference task is present",
            })
            swap = int(stable_hex(PROTOCOL, "blind_arm", calibration_id, replicate_id, n=8), 16) % 2 == 1
            response_a, response_b = (off_reply, on_reply) if swap else (on_reply, off_reply)
            a_arm, b_arm = ("OFF", "ON") if swap else ("ON", "OFF")
            blinded = {
                "replicate_id": replicate_id,
                "RESPONSE_A": _sentences(response_a, prefix="A_SENTENCE"),
                "RESPONSE_B": _sentences(response_b, prefix="B_SENTENCE"),
            }
            quality_replicates.append({
                **blinded,
                "instruction_boundary": "compare positive support contribution only; arm identity, function, risk, and cost labels are hidden",
            })
            risk_replicates.append({
                **blinded,
                "instruction_boundary": "record absolute events for each response before any resource attribution; no quality task is present",
            })
            arm_map[replicate_id] = {
                "RESPONSE_A": a_arm,
                "RESPONSE_B": b_arm,
                "on_status": generated["ON"]["status"],
                "off_status": generated["OFF"]["status"],
            }

        function_packet.append({**base, "replicates": function_replicates})
        verified = {
            "visible_dialogue": turns,
            "verified_candidate_fact": candidate,
            "rule": "use only this visible dialogue and verified typed fact for grounding checks; do not infer private or future facts",
        }
        quality_packet.append({**base, "verified_past_panel": verified, "replicates": quality_replicates})
        risk_packet.append({**base, "verified_past_panel": verified, "replicates": risk_replicates})
        selection_audit.append({
            "protocol": PROTOCOL,
            "calibration_id": calibration_id,
            "component": manifest["component"],
            "candidate_type": manifest["candidate_type"],
            "outer_fold": manifest["outer_fold"],
            "independent_cluster_hash": stable_hex(
                PROTOCOL, "cluster", _cluster_id(manifest), n=20
            ),
            "selection_diagnostic_stratum_not_gold": _diagnostic_stratum(manifest),
        })
        private.append({
            "protocol": PROTOCOL,
            "calibration_id": calibration_id,
            "effect_group_id": effect_group_id,
            "state_id": manifest["state_id"],
            "component": manifest["component"],
            "independent_cluster_id": _cluster_id(manifest),
            "outer_fold": manifest["outer_fold"],
            "candidate_type": manifest["candidate_type"],
            "selection_diagnostic_stratum_not_gold": _diagnostic_stratum(manifest),
            "blind_arm_map": arm_map,
            "historical_outcomes": {
                "quality_effect": result["quality_effect"],
                "functional": result["functional"],
                "risk": result["risk"],
                "risk_instrument_status": result["risk_instrument_status"],
            },
        })

    order = {
        row["calibration_id"]: stable_hex(PROTOCOL, "packet_order", row["calibration_id"], n=24)
        for row in candidate_packet
    }
    for rows in (candidate_packet, function_packet, quality_packet, risk_packet):
        rows.sort(key=lambda row: order[row["calibration_id"]])
    selection_audit.sort(key=lambda row: row["calibration_id"])
    private.sort(key=lambda row: row["calibration_id"])

    OUT.mkdir(parents=True, exist_ok=True)
    paths = {
        "candidate": OUT / "candidate_suitability_packet_blind.jsonl",
        "function": OUT / "functional_execution_packet_blind.jsonl",
        "quality": OUT / "quality_preference_packet_blind.jsonl",
        "risk": OUT / "absolute_risk_packet_blind.jsonl",
        "selection_audit": OUT / "selection_audit_outcome_blind.jsonl",
        "private": OUT / "private_key_do_not_open_until_all_role_reviews_freeze.jsonl",
    }
    write_jsonl(paths["candidate"], candidate_packet)
    write_jsonl(paths["function"], function_packet)
    write_jsonl(paths["quality"], quality_packet)
    write_jsonl(paths["risk"], risk_packet)
    write_jsonl(paths["selection_audit"], selection_audit)
    write_jsonl(paths["private"], private)

    rubric = """# V5.3 role-decomposed calibration V2（冻结）

同一 reviewer family 的四个角色也必须分开调用；任何 role prompt/response 都不得包含其他 role 的判断。

- Candidate：只见当前对话和 candidate，输出 VALID_APPLICABLE / VALID_REDUNDANT / VALID_NOT_USEFUL / INVALID_WRONG_OWNER_TIME_EVENT / UNRESOLVED。
- Function：只见 candidate 和一个 ON response，按组件最低功能标准输出 FUNCTIONAL / SURFACE_ECHO_ONLY / NOT_USED_FINAL / BOUNDARY_FAILURE / UNRESOLVED，并绑定 exact evidence IDs。
- Quality：只见 verified-past panel 与随机化 RESPONSE_A/B，比较 positive support contribution，输出 A_BETTER / B_BETTER / TIE / UNRESOLVED；不得读取 function/risk/cost。
- Risk：先分别记录 A/B 的绝对 WRONG_OWNER / FUTURE_OR_PRIVATE_FABRICATION / EXPLICIT_BOUNDARY_VIOLATION / EXCESSIVE_DIRECTIVENESS_OR_BURDEN，再在 private key 打开后确定资源归因；不得读取 quality。
- 所有不确定保持 UNRESOLVED；多数票不是 gold；只有一致或冻结 adjudication 可 resolved。
"""
    (OUT / "ROLE_RUBRICS_ZH.md").write_text(rubric, encoding="utf-8")

    report = {
        "protocol": PROTOCOL,
        "status": "CANDIDATE_ROLE_PREFLIGHT_READY_WITH_PRETREATMENT_OPENLIKE_SUPPORT_DEFICIT_PRIVATE_KEY_CLOSED",
        "groups": 64,
        "replicates": 192,
        "component_counts": dict(Counter(row["component"] for row in candidate_packet)),
        "candidate_type_counts": dict(Counter(f"{row['component']}:{row['candidate']['candidate_type']}" for row in candidate_packet)),
        "diagnostic_stratum_counts_not_gold": dict(Counter(row["selection_diagnostic_stratum_not_gold"] for row in private)),
        "unused_pool_diagnostic_strata_not_gold": available_strata,
        "diagnostic_support_interpretation": "the frozen natural panel has zero MP, only five MS, and only one ME expected-open-like unused groups under current pre-treatment heuristics; the selected packet takes all available MS/ME open-like rows and a balanced RS subset, but cannot satisfy the planned 8/8 diagnostic balance",
        "excluded_prior_groups": len(prior_groups),
        "prior_overlap": 0,
        "selection_read_fields": [
            "component", "candidate_type", "outer_fold", "user_or_dialogue_cluster",
            "current_redundant", "component_specific_readiness_or_precondition"
        ],
        "selection_forbidden_fields_not_read": [
            "quality_effect", "functional_judgment", "risk", "OOF_prediction", "effect_sign", "reply_text"
        ],
        "role_isolation": {
            "candidate_sees_replies": False,
            "function_sees_off_or_preference": False,
            "quality_sees_function_or_risk_or_cost_labels": False,
            "risk_sees_quality_labels": False,
            "quality_and_risk_arm_identity_hidden": True,
        },
        "staged_gate": "run and freeze the two candidate-suitability reviewer ledgers first; continue to function/quality/risk roles only if candidate agreement and resolved bidirectional support justify the expense",
        "unblinding_gate": "all completed reviewer-family x role ledgers schema-valid and hash-frozen; the historical private key remains closed through candidate-only preflight",
        "hashes": {name: sha256_file(path) for name, path in paths.items()},
        "source_hashes": {
            "manifest": sha256_file(MANIFEST),
            "prior_32": sha256_file(PRIOR_32),
            "prior_64": sha256_file(PRIOR_64),
            **{f"result_fold_{index}": sha256_file(path) for index, path in enumerate(result_paths, start=1)},
        },
        "api_calls": 0,
    }
    write_json(OUT / "manifest.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
