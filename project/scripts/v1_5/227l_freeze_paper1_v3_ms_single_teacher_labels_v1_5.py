#!/usr/bin/env python3
"""Freeze atomic-MS single-teacher labels, with exact zero-API alias recovery."""

from __future__ import annotations

from collections import Counter, defaultdict
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_g4b_anchored_review_v2 import G4BSuitabilityReview, validate_review  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_single_teacher_label_freeze_phase_v1.json"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811/reviewer_a_packet.jsonl"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811/private_case_key.jsonl"
G3 = ROOT / "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811/candidate_surface_diagnostics_unlabeled.jsonl"
LIVE = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_reviews_20260811"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811"

ALIAS_MAP = {
    "ALREADY_VISIBLE": "CURRENT_ECHO_OR_CONTAINMENT",
    "ALREADY_VISIBLE_OR_ALREADY_CHOSEN": "CURRENT_ECHO_OR_CONTAINMENT",
}


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def require_authority() -> dict[str, Any]:
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_SINGLE_TEACHER_LABEL_FREEZE":
        raise RuntimeError("MS single-teacher label freeze is not active")
    binding = active["active_phase_manifest"]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != sha256_file(PHASE):
        raise RuntimeError("MS label-freeze phase binding drifted")
    phase = read(PHASE)
    for item in phase["input_bindings"]:
        if sha256_file(ROOT / item["path"]) != item["sha256"]:
            raise RuntimeError(f"bound artifact drifted: {item['path']}")
    if phase["alias_projection"] != ALIAS_MAP:
        raise RuntimeError("alias projection drifted")
    return phase


def main() -> None:
    phase = require_authority()
    if OUT.exists():
        raise RuntimeError("MS label-freeze output exists; refusing overwrite")

    packet = {row["review_item_id"]: row for row in rows(PACKET) if row["component"] == "MS"}
    private = {row["reviewer_a_item_id"]: row for row in rows(PRIVATE) if row["component"] == "MS"}
    diagnostics = {
        (row["state_id"], row["actual_rank1_id"]): row
        for row in rows(G3)
        if row["component"] == "MS" and row["candidate_present"]
    }
    accepted = {row["review_item_id"]: row for row in rows(LIVE / "teacher_reviews.jsonl")}
    raw = {row["review_item_id"]: row for row in rows(LIVE / "raw_physical_attempts.jsonl")}
    if not (len(packet) == len(private) == len(raw) == 204 and len(accepted) == 199):
        raise RuntimeError("frozen MS denominator drifted")
    if set(packet) != set(private) or set(packet) != set(raw):
        raise RuntimeError("MS identifiers are not one-to-one")

    recovered: list[dict[str, Any]] = []
    alias_counts: Counter[str] = Counter()
    for review_item_id in sorted(packet, key=lambda key: int(packet[key]["review_position"])):
        item = packet[review_item_id]
        if review_item_id in accepted:
            review = dict(accepted[review_item_id])
            review["freeze_source"] = "LIVE_VALIDATED"
        else:
            raw_row = raw[review_item_id]
            parsed_payload = json.loads(raw_row["provider_text"])
            old_reason = parsed_payload["primary_reason_code"]
            if parsed_payload["decision"] != "NOT_SUITABLE" or old_reason not in ALIAS_MAP:
                raise RuntimeError(f"nonrecoverable raw review: {review_item_id}")
            parsed_payload["primary_reason_code"] = ALIAS_MAP[old_reason]
            validated = validate_review(G4BSuitabilityReview.model_validate(parsed_payload), item)
            review = {
                **validated,
                "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-review-result-v1",
                "reviewer_id": "REVIEWER_A",
                "component": "MS",
                "call_stage": "MS_TEACHER",
                "endpoint_key": raw_row["endpoint_key"],
                "model": raw_row["model"],
                "request_hash": raw_row["request_hash"],
                "review_position": int(item["review_position"]),
                "freeze_source": "ZERO_API_EXACT_REASON_ALIAS",
                "provider_reason_code": old_reason,
            }
            alias_counts[f"{old_reason}->{ALIAS_MAP[old_reason]}"] += 1
        recovered.append(review)

    labels: list[dict[str, Any]] = []
    class_by_group: dict[str, Counter[str]] = defaultdict(Counter)
    strata = defaultdict(lambda: Counter(total=0, suitable=0, not_suitable=0, abstain=0))
    for review in recovered:
        key = private[review["review_item_id"]]
        diagnostic = diagnostics[(key["state_id"], key["actual_rank1_id"])]
        decision = review["decision"]
        label = 1 if decision == "SUITABLE" else 0 if decision == "NOT_SUITABLE" else None
        row = {
            "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-label-v1",
            "case_key": key["case_key"],
            "review_item_id": review["review_item_id"],
            "component": "MS",
            "state_id": key["state_id"],
            "actual_rank1_id": key["actual_rank1_id"],
            "runtime_owner_key": key["runtime_owner_key"],
            "split_group_key": key["split_group_key"],
            "outer_fold": int(key["outer_fold"]),
            "teacher_decision": decision,
            "binary_suitability_label": label,
            "primary_reason_code": review["primary_reason_code"],
            "freeze_source": review["freeze_source"],
            "teacher_is_human_gold": False,
            "selection_score": float(diagnostic["selection_score"]),
            "top1_top2_margin": float(diagnostic["top1_top2_margin"]),
            "candidate_age_sessions": int(diagnostic["candidate_age_sessions"]),
            "candidate_word_count": int(diagnostic["candidate_word_count"]),
            "strict_past_pool_count": int(diagnostic["strict_past_pool_count"]),
            "low_information_rank1": bool(diagnostic["low_information_rank1"]),
            "exact_or_containment_current_echo": bool(diagnostic["exact_or_containment_current_echo"]),
            "atomic_single_seeker_turn": bool(diagnostic["atomic_single_seeker_turn"]),
        }
        labels.append(row)
        class_by_group[key["split_group_key"]][decision] += 1
        stratum = (
            "LOW_INFORMATION" if diagnostic["low_information_rank1"]
            else "CURRENT_ECHO" if diagnostic["exact_or_containment_current_echo"]
            else "ORDINARY_ATOMIC"
        )
        strata[stratum]["total"] += 1
        strata[stratum][decision.lower()] += 1

    decision_counts = Counter(row["teacher_decision"] for row in labels)
    resolved = [row for row in labels if row["binary_suitability_label"] is not None]
    logo_train_both_classes = {}
    for held_out in sorted(class_by_group):
        train_labels = {
            row["binary_suitability_label"]
            for row in resolved
            if row["split_group_key"] != held_out
        }
        logo_train_both_classes[held_out] = train_labels == {0, 1}

    checks = {
        "exact_204_reviews_frozen": len(recovered) == 204,
        "exact_five_zero_api_alias_recoveries": sum(alias_counts.values()) == 5,
        "only_frozen_aliases_used": set(alias_counts) <= {f"{k}->{v}" for k, v in ALIAS_MAP.items()},
        "all_candidates_atomic": all(row["atomic_single_seeker_turn"] for row in labels),
        "both_resolved_classes_exist": decision_counts["SUITABLE"] > 0 and decision_counts["NOT_SUITABLE"] > 0,
        "all_17_logo_training_folds_have_both_classes": len(logo_train_both_classes) == 17 and all(logo_train_both_classes.values()),
        "three_abstentions_remain_unlabeled_and_runtime_off": decision_counts["SEMANTIC_ABSTAIN"] == 3 and sum(row["binary_suitability_label"] is None for row in labels) == 3,
        "no_api_calls": True,
        "teacher_not_human_gold": True,
        "no_influenced_by_or_qa_gold_used": True,
        "no_generator_or_response_outcome_read": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    OUT.mkdir(parents=True)
    recovered_path = OUT / "frozen_teacher_reviews.jsonl"
    labels_path = OUT / "ms_teacher_labels.jsonl"
    write_jsonl(recovered_path, recovered)
    write_jsonl(labels_path, labels)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-single-teacher-label-freeze-report-v1",
        "status": "MS_SINGLE_TEACHER_LABEL_FREEZE_PASS_OOF_DESIGN_MAY_BEGIN" if not failed else "MS_SINGLE_TEACHER_LABEL_FREEZE_FAIL",
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            "cases": len(labels),
            "resolved_binary": len(resolved),
            "decisions": dict(sorted(decision_counts.items())),
            "groups": len(class_by_group),
            "alias_recoveries": dict(sorted(alias_counts.items())),
        },
        "strata": {name: dict(counts) for name, counts in sorted(strata.items())},
        "per_group_decisions": {group: dict(sorted(counts.items())) for group, counts in sorted(class_by_group.items())},
        "logo_train_both_classes": logo_train_both_classes,
        "artifacts": {
            "frozen_teacher_reviews": {"path": str(recovered_path.relative_to(ROOT)), "sha256": sha256_file(recovered_path)},
            "ms_teacher_labels": {"path": str(labels_path.relative_to(ROOT)), "sha256": sha256_file(labels_path)},
        },
        "supervision_claim": "single qualified LLM teacher distillation; not human gold",
        "abstention_runtime_policy": "OFF",
        "api_calls": 0,
        "pm_fit_count": 0,
        "next": "FREEZE_IDENTITY_FREE_LOW_CAPACITY_GROUPED_OOF_BEFORE_FIRST_FIT",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
