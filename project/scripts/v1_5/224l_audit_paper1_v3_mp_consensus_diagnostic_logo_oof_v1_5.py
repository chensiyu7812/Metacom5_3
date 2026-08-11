#!/usr/bin/env python3
"""Audit what the frozen MP diagnostic OOF actually learned; never tune it."""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
from typing import Any

from sklearn.metrics import brier_score_loss, roc_auc_score


ROOT = Path(__file__).resolve().parents[2]
OOF = ROOT / "outputs/pm_v1_5_paper1_v3_mp_consensus_diagnostic_logo_oof_20260811/report.json"
PREDICTIONS = ROOT / "outputs/pm_v1_5_paper1_v3_mp_consensus_diagnostic_logo_oof_20260811/oof_predictions.jsonl"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811/private_case_key.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_mp_consensus_diagnostic_logo_oof_audit_20260811/report.json"


def read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def concordance_within_field(
    data: list[dict[str, Any]], probability_key: str
) -> dict[str, Any]:
    concordant = tied = pairs = 0
    for positive in data:
        if positive["label"] != 1:
            continue
        for negative in data:
            if negative["label"] != 0 or negative["profile_field"] != positive["profile_field"]:
                continue
            pairs += 1
            if positive[probability_key] > negative[probability_key]:
                concordant += 1
            elif positive[probability_key] == negative[probability_key]:
                tied += 1
    return {
        "eligible_positive_negative_pairs": pairs,
        "concordant": concordant,
        "tied": tied,
        "pair_concordance": (concordant + 0.5 * tied) / pairs,
    }


def main() -> None:
    report = read(OOF)
    if report["status"] != "MP_CONSENSUS_DIAGNOSTIC_OOF_COMPLETE_NO_FORMAL_PROMOTION":
        raise RuntimeError("unexpected diagnostic status")
    predictions = rows(PREDICTIONS)
    private = {
        row["case_key"]: row
        for row in rows(PRIVATE)
        if row["component"] == "MP"
    }
    data = []
    for row in predictions:
        data.append(
            {
                **row,
                "profile_field": private[row["case_key"]]["proxy_flags"]["profile_field"],
            }
        )
    if len(data) != 136:
        raise RuntimeError("diagnostic denominator drifted")

    by_field: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in data:
        by_field[row["profile_field"]].append(row)
    field_rows = []
    for field, items in sorted(by_field.items()):
        y = [row["label"] for row in items]
        primary = [row["primary_probability"] for row in items]
        transparent = [row["field_only_probability"] for row in items]
        detail: dict[str, Any] = {
            "profile_field": field,
            "rows": len(items),
            "on": sum(y),
            "off": len(y) - sum(y),
            "primary_brier": brier_score_loss(y, primary),
            "field_only_brier": brier_score_loss(y, transparent),
        }
        if len(set(y)) == 2:
            detail["primary_auc_within_field"] = roc_auc_score(y, primary)
            detail["field_only_auc_within_field"] = roc_auc_score(y, transparent)
        field_rows.append(detail)

    groups = sorted({row["split_group_key"] for row in data})
    mixed_groups = sum(
        len({row["label"] for row in data if row["split_group_key"] == group}) == 2
        for group in groups
    )
    primary = report["primary_metrics"]
    transparent = report["field_only_metrics"]
    audit = {
        "protocol": "pm-v1.5-paper1-v3-mp-consensus-diagnostic-logo-oof-audit-v1",
        "status": "MP_DIAGNOSTIC_POOLED_SIGNAL_FIELD_PRIOR_DOMINATED_NO_FORMAL_PROMOTION",
        "answer": {
            "pooled_cross_user_signal_present": True,
            "evidence_of_state_conditional_signal_beyond_profile_field": False,
            "formal_mp_label_route_passed": False,
            "formal_mp_fit_or_checkpoint_authorized": False,
        },
        "pooled_metrics": {
            "primary": primary,
            "profile_field_only": transparent,
            "primary_minus_field_only": {
                "roc_auc": primary["roc_auc"] - transparent["roc_auc"],
                "balanced_accuracy_at_0_5": primary["balanced_accuracy_at_0_5"]
                - transparent["balanced_accuracy_at_0_5"],
                "brier_gain_where_positive_is_better": transparent["brier"]
                - primary["brier"],
                "log_loss_gain_where_positive_is_better": transparent["log_loss"]
                - primary["log_loss"],
            },
        },
        "conditional_diagnostics": {
            "primary_within_profile_field": concordance_within_field(
                data, "primary_probability"
            ),
            "field_only_within_profile_field": concordance_within_field(
                data, "field_only_probability"
            ),
            "mixed_label_groups": mixed_groups,
            "all_groups": len(groups),
            "by_profile_field": field_rows,
        },
        "interpretation": [
            "The pooled MP result is directionally above chance, so the exact-consensus subset is not random.",
            "The profile-field-only comparator has better balanced accuracy, Brier score, and log loss; the full feature set improves pooled AUC by only about 0.005.",
            "Within the same profile field, the primary model's positive-negative pair concordance is below 0.5. The observed pooled discrimination therefore does not establish state-specific profile suitability.",
            "The 136-row consensus subset is selected by reviewer agreement and cannot repair the failed 204-case measurement route.",
        ],
        "root_cause": {
            "label_side": "reviewers agree strongly on profile-field priors but not reliably on the bounded material-use decision for a concrete state",
            "feature_side": "the frozen features mainly describe field type, lexical scope, retrieval position, and redundancy; they do not encode a reliable state-to-profile material response change",
            "not_the_cause": [
                "the four heads being trained separately",
                "the 16-action requested space",
                "a global one-memory cap",
                "threshold tuning, because none occurred",
            ],
        },
        "routing": {
            "MP": "SURFACE_PASS__LABEL_FAIL__DIAGNOSTIC_FIELD_PRIOR_SIGNAL_ONLY__PAUSE_FORMAL_FIT",
            "RS": "OOF_PASS__UNCHANGED",
            "MS": "SURFACE_PASS__V3_LABEL_UNPROVEN__NEXT_SOURCE_AWARE_ATOMIC_LABEL_ROUTE_AUDIT",
            "ME": "LIMITED_SURFACE__LABEL_FAIL__CONTINGENCY_ONLY",
            "joint_execution": "V3_EXECUTOR_DESIGN_PRESERVED__NOT_EVALUATED_BY_THIS_DIAGNOSTIC",
        },
        "next": [
            "freeze this MP diagnostic without feature or threshold repair",
            "use EvoEmo influenced_by only to stratify a source-aware atomic MS annotation audit; never inherit a session label onto a turn",
            "use ES-MemEval QA evidence only to diagnose retrieval/semantic representation, never as response-PM suitability gold",
            "only after a prospective exact-turn MS label route passes, train MS separately and then evaluate RS+MS through the shared 16-action V3 executor",
            "return to MP later with an outcome-blind state-to-profile material-use representation rather than profile-field priors",
        ],
        "api_calls": 0,
        "generator_calls": 0,
        "baseline_calls": 0,
        "external_calls": 0,
        "threshold_or_feature_changes_after_result": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=False)
    OUT.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(audit, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
