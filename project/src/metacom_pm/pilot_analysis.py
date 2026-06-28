from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
from typing import Any
import math

from .artifacts import create_artifact_attestation
from .controls import control_gate_rationale, control_gate_tier
from .io import iter_jsonl, write_json, read_json, sha256_file


def _rate_controls(rows: list[dict[str, Any]]) -> dict[str, Any]:
    passed = 0
    details = []
    by_tier: dict[str, dict[str, Any]] = defaultdict(lambda: {"n": 0, "passed": 0, "details": []})
    for row in rows:
        value = row["validated"]
        expected = row["expected"]
        ok = True
        kind = row["kind"]
        if kind == "response":
            ok = value["preference"] == expected["preference"]
        elif kind == "memory_use":
            assessments = value["source_assessments"]
            if not assessments:
                ok = False
            else:
                agg = {
                    "utilization": max(x["utilization"] for x in assessments),
                    "stale_or_conflicting_use": max(
                        x["stale_or_conflicting_use"] for x in assessments
                    ),
                    "unsupported_personal_claim": max(
                        x["unsupported_personal_claim"] for x in assessments
                    ),
                }
                for key, target in expected.items():
                    if key.endswith("_min"):
                        ok &= agg[key[:-4]] >= target
                    elif key.endswith("_max"):
                        ok &= agg[key[:-4]] <= target
        elif kind == "memory_omission":
            mapping = {
                "omission_appropriateness": value["omission_appropriateness"],
                "missed": value["missed_memory_opportunity_severity"],
            }
            for key, target in expected.items():
                if key.endswith("_min"):
                    ok &= mapping[key[:-4]] >= target
                elif key.endswith("_max"):
                    ok &= mapping[key[:-4]] <= target
        elif kind == "strategy":
            mapping = {
                "relevance": value["strategy_relevance"],
                "utilization": value["strategy_utilization"],
                "premature": value["premature_advice"],
            }
            for key, target in expected.items():
                if key.endswith("_min"):
                    ok &= mapping[key[:-4]] >= target
                elif key.endswith("_max"):
                    ok &= mapping[key[:-4]] <= target
        tier = str(row.get("control_tier") or control_gate_tier(row["control_id"]))
        detail = {
            "control_id": row["control_id"],
            "kind": kind,
            "tier": tier,
            "passed": bool(ok),
            "rationale": row.get("control_rationale")
            or control_gate_rationale(row["control_id"]),
        }
        details.append(detail)
        by_tier[tier]["n"] += 1
        by_tier[tier]["passed"] += int(ok)
        by_tier[tier]["details"].append(detail)
        passed += int(ok)
    tier_summary = {}
    for tier, value in sorted(by_tier.items()):
        n = value["n"]
        tier_summary[tier] = {
            **value,
            "accuracy": value["passed"] / n if n else 0.0,
        }
    return {
        "n": len(rows),
        "passed": passed,
        "accuracy": passed / len(rows) if rows else 0.0,
        "details": details,
        "by_tier": tier_summary,
    }


def _response_diagnostics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base_by_canon: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        base_by_canon[row["canonical_pair_id"]].append(row)
    reversal_total = reversal_ok = 0
    repeat_total = repeat_ok = 0
    ties = 0
    # Position bias: only computed on single-order audit rows (reversal/repeat).
    # For dual-order debiased rows, preference="A"/"B" means action_a/action_b
    # won — not a position label — so mixing them into position_bias is a
    # semantic error.
    audit_position_a = audit_position_b = 0
    # Dual-order debiasing diagnostics (rows produced by the new debiasing path)
    dual_total = dual_agree = dual_disagree_to_tie = 0
    dual_effective_non_tie = 0
    dual_by_type = defaultdict(Counter)
    by_type = defaultdict(Counter)
    for row in rows:
        pref = row["preference"]
        by_type[row["pair_type"]][pref] += 1
        ties += pref == "tie"
        if row.get("dual_order_debiased"):
            dual_total += 1
            dual_by_type[row["pair_type"]][pref] += 1
            dual_effective_non_tie += pref != "tie"
            fwd = row.get("fwd_preference")
            rev_raw = row.get("rev_preference")
            rev_translated = (
                "B" if rev_raw == "A"
                else "A" if rev_raw == "B"
                else "tie"
            )
            if fwd == rev_translated:
                dual_agree += 1
            elif pref == "tie":
                dual_disagree_to_tie += 1
        else:
            # Single-order audit rows: A/B label reflects presentation position.
            audit_position_a += pref == "A"
            audit_position_b += pref == "B"
    for group in base_by_canon.values():
        bases = [x for x in group if not x["is_reversal"] and not x["is_same_order_repeat"]]
        if not bases:
            continue
        base = bases[0]
        base_raw_winner = base.get("fwd_winner_action", base["winner_action"])
        for row in group:
            if row["is_reversal"]:
                reversal_total += 1
                row_raw_winner = row.get("fwd_winner_action", row["winner_action"])
                reversal_ok += row_raw_winner == base_raw_winner
            if row["is_same_order_repeat"]:
                repeat_total += 1
                row_raw_winner = row.get("fwd_winner_action", row["winner_action"])
                repeat_ok += row_raw_winner == base_raw_winner
    audit_non_ties = audit_position_a + audit_position_b
    position_bias = (
        abs(audit_position_a - audit_position_b) / audit_non_ties
        if audit_non_ties else 0.0
    )
    result = {
        "n": len(rows),
        "tie_rate": ties / len(rows) if rows else 0.0,
        "audit_position_distribution": {
            "A": audit_position_a, "B": audit_position_b,
            "note": "Counts from single-order audit rows only (reversal/repeat).",
        },
        "position_bias_abs_rate": position_bias,
        "position_bias_note": (
            "Computed on single-order audit rows only. Dual-order debiased rows "
            "use action-identity labels (A=action_a, B=action_b), not position labels."
        ),
        "reversal_n": reversal_total,
        "reversal_consistency": reversal_ok / reversal_total if reversal_total else None,
        "repeat_n": repeat_total,
        "same_order_repeat_consistency": repeat_ok / repeat_total if repeat_total else None,
        "by_pair_type": {
            key: {
                "n": sum(counter.values()),
                "tie_rate": counter["tie"] / sum(counter.values()),
                "distribution": dict(counter),
            }
            for key, counter in sorted(by_type.items())
        },
    }
    # Dual-order diagnostics are reported separately. In Protocol V3 the raw
    # agreement rate is diagnostic; the debiased effective non-tie rate is the
    # response-training signal hard gate.
    if dual_total > 0:
        result["dual_order_diagnostic"] = {
            "n_dual_pairs": dual_total,
            "n_agree": dual_agree,
            "n_disagree_resolved_to_tie": dual_disagree_to_tie,
            "agreement_rate": dual_agree / dual_total,
            "n_effective_non_tie": dual_effective_non_tie,
            "effective_non_tie_rate": dual_effective_non_tie / dual_total,
            "by_pair_type": {
                key: {
                    "n": sum(counter.values()),
                    "tie_rate": counter["tie"] / sum(counter.values()),
                    "effective_non_tie_rate": (
                        (sum(counter.values()) - counter["tie"]) / sum(counter.values())
                    ),
                    "distribution": dict(counter),
                }
                for key, counter in sorted(dual_by_type.items())
            },
            "note": (
                "Raw disagreement in training-eligible pairs is resolved to "
                "tie by the debiasing layer. Protocol V3 reports raw agreement "
                "diagnostically and uses the resulting effective non-tie rate "
                "as the response-training signal gate. Raw reversal_consistency "
                "uses designated audit reversal pairs and compares them against "
                "the base pair's raw forward verdict."
            ),
        }
    return result


def analyze_judge_pilot(
    pilot_dir: str | Path,
    pair_graph_audit_path: str | Path,
    out_gate_path: str | Path,
    *,
    out_attestation_path: str | Path | None = None,
    min_control_accuracy: float = 0.85,
    min_hard_control_accuracy: float = 1.0,
    min_repeat_consistency: float = 0.80,
    min_dual_order_agreement: float = 0.65,
    min_effective_non_tie_rate: float = 0.25,
    # Protocol V3: raw dual-order agreement, raw reversal, and position bias are
    # diagnostics, not hard gates. Position bias is only meaningful on
    # single-order audit rows. Raw reversal threshold is kept for reference.
    _diagnostic_min_reversal_consistency: float = 0.75,
    _diagnostic_max_position_bias: float = 0.12,
) -> dict[str, Any]:
    pilot_dir = Path(pilot_dir)
    out_gate_path = Path(out_gate_path)
    out_attestation_path = Path(
        out_attestation_path or out_gate_path.parent / "pilot_gate_attestation.json"
    )
    summary = read_json(pilot_dir / "judging_summary.json")
    graph = read_json(pair_graph_audit_path)
    response = list(iter_jsonl(pilot_dir / "response_pair_judgments.jsonl"))
    m1 = list(iter_jsonl(pilot_dir / "memory_opportunity_judgments.jsonl"))
    m2 = list(iter_jsonl(pilot_dir / "memory_use_judgments.jsonl"))
    m0 = list(iter_jsonl(pilot_dir / "memory_omission_judgments.jsonl"))
    strategy = list(iter_jsonl(pilot_dir / "strategy_use_judgments.jsonl"))
    strategy_omission = list(iter_jsonl(pilot_dir / "strategy_omission_judgments.jsonl"))
    controls = list(iter_jsonl(pilot_dir / "heldout_control_judgments.jsonl"))

    response_diag = _response_diagnostics(response)
    control_diag = _rate_controls(controls)
    hard_control_diag = control_diag.get("by_tier", {}).get(
        "hard", {"n": 0, "passed": 0, "accuracy": 0.0, "details": []}
    )
    diagnostic_control_diag = control_diag.get("by_tier", {}).get(
        "diagnostic", {"n": 0, "passed": 0, "accuracy": 0.0, "details": []}
    )
    dual_diag = response_diag.get("dual_order_diagnostic", {})
    dual_agreement = dual_diag.get("agreement_rate")
    effective_non_tie_rate = dual_diag.get("effective_non_tie_rate")
    strategy_by_type = response_diag.get("by_pair_type", {}).get("strategy", {})
    strategy_not_all_tie = (
        strategy_by_type.get("tie_rate", 1.0) < 0.50
        if strategy_by_type else False
    )

    checks = {
        # Hard gates (Protocol V3 — stratified controls + effective signal)
        "judging_complete": summary.get("status") == "COMPLETE",
        "graph_ok": bool(graph.get("ok")),
        "controls_present": bool(controls),
        "hard_control_accuracy": (
            hard_control_diag["n"] > 0
            and hard_control_diag["accuracy"] >= min_hard_control_accuracy
        ),
        "same_order_repeat_consistency": (
            response_diag["same_order_repeat_consistency"] is not None
            and response_diag["same_order_repeat_consistency"] >= min_repeat_consistency
        ),
        "response_training_signal": (
            effective_non_tie_rate is not None
            and effective_non_tie_rate >= min_effective_non_tie_rate
        ),
        "strategy_pairs_have_signal": strategy_not_all_tie,
        # Diagnostic checks (reported but NOT blocking — see Protocol V3 rationale)
        "_diag_heldout_control_accuracy": control_diag["accuracy"] >= min_control_accuracy,
        "_diag_boundary_controls_present": diagnostic_control_diag["n"] > 0,
        "_diag_dual_order_agreement": (
            dual_agreement is not None and dual_agreement >= min_dual_order_agreement
        ),
        "_diag_reversal_consistency": (
            response_diag["reversal_consistency"] is not None
            and response_diag["reversal_consistency"] >= _diagnostic_min_reversal_consistency
        ),
        "_diag_position_bias": (
            response_diag["position_bias_abs_rate"] <= _diagnostic_max_position_bias
        ),
        "m1_complete": len(m1) == summary["expected_m1"],
        "m0_complete": len(m0) == summary["expected_m0"],
        "m2_complete": len(m2) == summary["expected_m2"],
        "strategy_complete": len(strategy) == summary["expected_strategy"],
        "strategy_omission_complete": (
            len(strategy_omission) == summary["expected_strategy_omission"]
        ),
        "response_complete": len(response) == summary["n_pairs"],
    }
    # Only hard gates (not _diag_* keys) determine GO/NO-GO.
    hard_checks = {k: v for k, v in checks.items() if not k.startswith("_diag_")}
    status = (
        "PILOT_GO_FULL_JUDGING"
        if all(hard_checks.values())
        else "PILOT_NO_GO"
    )
    measurement_signature = {
        "input_hashes": summary.get("input_hashes"),
        "judge_protocol_sha256": summary.get("judge_protocol_sha256"),
        "endpoint_model": summary.get("model"),
        "endpoint_family": summary.get("model_family"),
        "endpoint_base_url": summary.get("endpoint_base_url"),
        "judge_pilot_attestation_sha256": sha256_file(
            pilot_dir / "artifact_attestation.json"
        ),
    }
    result = {
        "status": status,
        "checks": checks,
        "thresholds": {
            "min_control_accuracy": min_control_accuracy,
            "min_hard_control_accuracy": min_hard_control_accuracy,
            "min_repeat_consistency": min_repeat_consistency,
            "min_dual_order_agreement": min_dual_order_agreement,
            "min_effective_non_tie_rate": min_effective_non_tie_rate,
            "protocol_version": "V3_stratified_controls_effective_signal",
            "diagnostic_only": {
                "_diagnostic_min_control_accuracy": min_control_accuracy,
                "_diagnostic_min_dual_order_agreement": min_dual_order_agreement,
                "_diagnostic_min_reversal_consistency": _diagnostic_min_reversal_consistency,
                "_diagnostic_max_position_bias": _diagnostic_max_position_bias,
                "note": (
                    "Boundary controls, aggregate control accuracy, raw dual-order "
                    "agreement, raw reversal, and position bias are diagnostics in "
                    "Protocol V3. Position bias is computed only on single-order "
                    "audit rows. See MEASUREMENT_PROTOCOL_V3.md for rationale."
                ),
            },
        },
        "controls": control_diag,
        "response": response_diag,
        "counts": {
            "m1": len(m1),
            "m2": len(m2),
            "m0": len(m0),
            "strategy": len(strategy),
            "strategy_omission": len(strategy_omission),
        },
        "measurement_signature": measurement_signature,
        "pilot_gate_attestation": str(out_attestation_path.resolve()),
        "notes": [
            "Protocol V3: hard gates are data completeness, graph validity, hard "
            "control accuracy, same-order repeat consistency, effective non-tie "
            "response-training signal after dual-order debiasing, and strategy "
            "pair signal. Boundary controls, aggregate control accuracy, raw "
            "dual-order agreement, raw reversal, and position bias are diagnostics.",
            "Tie rate is diagnostic and is not an isolated hard gate.",
            "This gate validates the measurement pipeline, not the PM hypothesis.",
            "Response quality is a non-inferiority constraint (margin=0.05), not a "
            "superiority claim. Memory decision quality comes from M1/M2/M0 labels.",
        ],
    }
    write_json(out_gate_path, result)
    create_artifact_attestation(
        out_attestation_path,
        stage="judge_pilot_gate",
        inputs={
            "judging_summary": pilot_dir / "judging_summary.json",
            "judge_pilot_attestation": pilot_dir / "artifact_attestation.json",
            "pair_graph_audit": pair_graph_audit_path,
            "response_pairs": pilot_dir / "response_pair_judgments.jsonl",
            "memory_opportunity": pilot_dir / "memory_opportunity_judgments.jsonl",
            "memory_use": pilot_dir / "memory_use_judgments.jsonl",
            "memory_omission": pilot_dir / "memory_omission_judgments.jsonl",
            "strategy_use": pilot_dir / "strategy_use_judgments.jsonl",
            "strategy_omission": pilot_dir / "strategy_omission_judgments.jsonl",
            "heldout_controls": pilot_dir / "heldout_control_judgments.jsonl",
        },
        outputs={"pilot_gate": (out_gate_path, False)},
        parameters={
            "min_control_accuracy": min_control_accuracy,
            "min_hard_control_accuracy": min_hard_control_accuracy,
            "min_repeat_consistency": min_repeat_consistency,
            "min_dual_order_agreement": min_dual_order_agreement,
            "min_effective_non_tie_rate": min_effective_non_tie_rate,
            "diag_min_reversal_consistency": _diagnostic_min_reversal_consistency,
            "diag_max_position_bias": _diagnostic_max_position_bias,
            "judge_protocol_sha256": summary.get("judge_protocol_sha256"),
            "judge_pilot_attestation_sha256": sha256_file(
                pilot_dir / "artifact_attestation.json"
            ),
        },
        expected={"status": status, **checks},
        study_freeze_sha256=summary.get("study_freeze_sha256"),
    )
    return result
