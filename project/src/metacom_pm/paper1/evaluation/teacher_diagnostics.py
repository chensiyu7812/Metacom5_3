"""Offline reference comparisons. These diagnostics do not create PM labels."""

from __future__ import annotations

from collections import Counter, defaultdict
from typing import Any

from metacom_pm.paper1.evaluation.pairwise_teacher import VERDICTS


def index_presentations(rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    indexed = {}
    for row in rows:
        pid = row["presentation_id"]
        if not isinstance(pid, str) or not pid or pid in indexed:
            raise ValueError("missing or duplicate presentation identity")
        indexed[pid] = row
    return indexed


def compare_verdicts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """Compare raw four-class verdicts; null candidate results are missing, not uncertain."""
    index_presentations(rows)
    classes = sorted(VERDICTS)
    confusion = {a: {b: 0 for b in classes} for a in classes}
    observed = []
    for row in rows:
        ref, candidate = row["reference_verdict"], row["candidate_verdict"]
        if ref not in VERDICTS or (candidate is not None and candidate not in VERDICTS):
            raise ValueError("verdict outside frozen four-class vocabulary")
        if candidate is not None:
            confusion[ref][candidate] += 1
            observed.append(row)
    recalls = {
        label: confusion[label][label] / sum(confusion[label].values())
        if sum(confusion[label].values()) else None
        for label in classes
    }
    material = [recalls[c] for c in ("A_better", "B_better", "equivalent") if recalls[c] is not None]
    matched = sum(r["reference_verdict"] == r["candidate_verdict"] for r in observed)
    candidate_counts = Counter(r["candidate_verdict"] for r in observed)
    decisive = candidate_counts["A_better"] + candidate_counts["B_better"]
    return {
        "scheduled": len(rows), "observed": len(observed), "missing": len(rows) - len(observed),
        "exact_matches": matched, "exact_agreement": matched / len(observed) if observed else None,
        "reference_counts_all": dict(Counter(r["reference_verdict"] for r in rows)),
        "candidate_counts_observed": dict(candidate_counts),
        "confusion_reference_rows_candidate_columns": confusion,
        "recall_by_observed_reference_class": recalls,
        "macro_recall_decisive_equivalent_present_classes": sum(material) / len(material) if material else None,
        "macro_recall_classes_present": len(material),
        "candidate_A_fraction_among_decisive": candidate_counts["A_better"] / decisive if decisive else None,
        "position_fraction_interpretation": "descriptive, not by itself evidence of bias",
        "is_accuracy_against_independent_gold": False,
    }


def reversal_consistency(rows: list[dict[str, Any]], verdict_field: str) -> dict[str, Any]:
    index_presentations(rows)
    groups = defaultdict(list)
    for row in rows:
        if row["A_arm"] not in {"ON", "OFF"}:
            raise ValueError("unknown response orientation")
        if row[verdict_field] is not None and row[verdict_field] not in VERDICTS:
            raise ValueError("invalid reversal verdict")
        groups[row["base_pair_id"]].append(row)
    compared, consistent, missing = 0, 0, 0
    for items in groups.values():
        if len(items) == 1:
            if items[0]["reverse_duplicate"]:
                raise ValueError("reversed presentation without its base")
            continue
        if len(items) != 2 or sum(i["reverse_duplicate"] for i in items) != 1:
            raise ValueError("invalid base/reversal multiplicity")
        if items[0]["A_arm"] == items[1]["A_arm"]:
            raise ValueError("reversal must swap response orientation")
        if any(i[verdict_field] is None for i in items):
            missing += 1
            continue
        normalized = []
        for item in items:
            v = item[verdict_field]
            if v in {"A_better", "B_better"}:
                v = item["A_arm"] if v == "A_better" else ("OFF" if item["A_arm"] == "ON" else "ON")
            normalized.append(v)
        compared += 1
        consistent += normalized[0] == normalized[1]
    return {"paired_bases": compared, "consistent": consistent, "missing_pairs": missing,
            "rate": consistent / compared if compared else None}


def reference_comparison(rows: list[dict[str, Any]]) -> dict[str, Any]:
    base = [r for r in rows if not r["reverse_duplicate"]]
    return {
        "base_pairs": compare_verdicts(base),
        "all_presentations_descriptive": compare_verdicts(rows),
        "by_task_base_pairs": {
            task: compare_verdicts([r for r in base if r["task"] == task])
            for task in sorted({r["task"] for r in rows})
        },
        "reference_reversal": reversal_consistency(rows, "reference_verdict"),
        "candidate_reversal": reversal_consistency(rows, "candidate_verdict"),
        "reversals_are_independent_effect_samples": False,
        "empirical_pass_gate": None,
    }


def clustered_agreement_interval(
    rows: list[dict[str, Any]], *, replicates: int = 2000, seed: int = 20260917
) -> dict[str, Any]:
    """Percentile cluster bootstrap of exact agreement on non-reversed bases.

    Memory clusters are owners, ESC clusters are source dialogues. The caller
    binds those IDs from the outcome-blind preflight, never from judge verdicts.
    """
    import numpy as np

    index_presentations(rows)
    if type(replicates) is not int or replicates < 1:
        raise ValueError("positive bootstrap replication count required")
    usable = [r for r in rows if not r["reverse_duplicate"] and r["candidate_verdict"] is not None]
    groups = defaultdict(list)
    for row in usable:
        if not isinstance(row.get("cluster_id"), str) or not row["cluster_id"]:
            raise ValueError("source-bound cluster identity required")
        if row["reference_verdict"] not in VERDICTS or row["candidate_verdict"] not in VERDICTS:
            raise ValueError("invalid bootstrap verdict")
        groups[row["cluster_id"]].append(row)
    result = {"method": "cluster_resampling_percentile_95_percent", "seed": seed,
              "replicates": replicates, "clusters": len(groups), "observed_base_pairs": len(usable),
              "unit": "memory_owner_or_ESC_source_dialogue", "interval": None,
              "macro_recall_interval": None, "macro_recall_valid_replicates": 0,
              "reference_is_joint_not_independent_gold": True}
    if len(groups) < 2:
        result["reason"] = "fewer_than_two_observed_clusters"
        return result
    totals = np.array([len(g) for _, g in sorted(groups.items())])
    matches = np.array([sum(r["reference_verdict"] == r["candidate_verdict"] for r in g)
                        for _, g in sorted(groups.items())])
    sampled = np.random.default_rng(seed).integers(0, len(groups), size=(replicates, len(groups)))
    agreement = matches[sampled].sum(axis=1) / totals[sampled].sum(axis=1)
    result["interval"] = [float(v) for v in np.quantile(agreement, [0.025, 0.975])]
    labels = [label for label in ("A_better", "B_better", "equivalent")
              if any(r["reference_verdict"] == label for r in usable)]
    result["macro_recall_supported_classes"] = labels
    if labels:
        class_counts = np.array([[sum(r["reference_verdict"] == label for r in g) for label in labels]
                                 for _, g in sorted(groups.items())])
        class_matches = np.array([[sum(r["reference_verdict"] == label and r["candidate_verdict"] == label
                                      for r in g) for label in labels] for _, g in sorted(groups.items())])
        denominators = class_counts[sampled].sum(axis=1)
        numerators = class_matches[sampled].sum(axis=1)
        valid = (denominators > 0).all(axis=1)
        result["macro_recall_valid_replicates"] = int(valid.sum())
        if valid.any():
            macro = (numerators[valid] / denominators[valid]).mean(axis=1)
            result["macro_recall_interval"] = [float(v) for v in np.quantile(macro, [0.025, 0.975])]
        result["macro_recall_missing_class_policy"] = "replicates missing an originally supported class are undefined; report valid count"
    return result
