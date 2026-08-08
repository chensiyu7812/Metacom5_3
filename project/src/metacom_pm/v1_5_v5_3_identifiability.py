"""Outcome-blind feature-support and effective-sample audit for V5.3.

This audit refuses to turn rows or template variants into independent power.
It reports user, family, and counterfactual-group support; one-hot design rank;
constant/missing features; and a conservative feature-dimension budget.  Class
balance and empirical power remain pending until paired effects exist.
"""

from __future__ import annotations

from collections import Counter, defaultdict
import math
from typing import Any, Iterable, Mapping

import numpy as np


COMPONENTS = ("MP", "MS", "ME", "RS")


def _feature_items(row: Mapping[str, Any]) -> dict[str, Any]:
    return dict(row["model_input"]["contribution_slots"])


def _encode(rows: list[Mapping[str, Any]]) -> tuple[np.ndarray, list[str]]:
    raw = [_feature_items(row) for row in rows]
    keys = sorted({key for item in raw for key in item})
    columns: list[list[float]] = []
    names: list[str] = []
    for key in keys:
        values = [item.get(key) for item in raw]
        observed = [value for value in values if value is not None]
        if not observed:
            continue
        if all(isinstance(value, (bool, int, float)) and not isinstance(value, str) for value in observed):
            columns.append([float("nan") if value is None else float(value) for value in values])
            names.append(key)
            continue
        categories = sorted({str(value) for value in observed})
        for category in categories:
            columns.append([1.0 if str(value) == category else 0.0 for value in values])
            names.append(f"{key}={category}")
    if not columns:
        return np.empty((len(rows), 0)), []
    matrix = np.asarray(columns, dtype=float).T
    for index in range(matrix.shape[1]):
        column = matrix[:, index]
        missing = np.isnan(column)
        if missing.any():
            observed = column[~missing]
            fill = float(np.median(observed)) if observed.size else 0.0
            column[missing] = fill
    return matrix, names


def audit_identifiability(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    materialized = [dict(row) for row in rows]
    by_component: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in materialized:
        component = str(row["model_input"]["component"])
        if component not in COMPONENTS:
            raise ValueError(f"unexpected component {component!r}")
        by_component[component].append(row)

    reports: dict[str, Any] = {}
    for component in COMPONENTS:
        subset = by_component.get(component, [])
        users = {str(row["state"]["catalog_user_id"]) for row in subset}
        groups = {str(row["state"]["counterfactual_group_id"]) for row in subset}
        families = {str(row["state"]["semantic_family"]) for row in subset}
        conditions = Counter(str(row["state"]["state_condition"]) for row in subset)
        matrix, names = _encode(subset)
        constant = []
        variable = []
        if matrix.size:
            for index, name in enumerate(names):
                (constant if np.unique(matrix[:, index]).size <= 1 else variable).append(name)
        variable_matrix = (
            matrix[:, [names.index(name) for name in variable]]
            if variable
            else np.empty((len(subset), 0))
        )
        rank = int(np.linalg.matrix_rank(variable_matrix)) if variable_matrix.size else 0
        unique_vectors = (
            len({tuple(row) for row in np.round(variable_matrix, 8)})
            if variable_matrix.size
            else 0
        )
        group_cap = max(1, len(groups) // 5) if groups else 0
        user_cap = max(1, len(users) // 5) if users else 0
        conservative_cap = min(group_cap, user_cap) if group_cap and user_cap else 0
        per_user = Counter(str(row["state"]["catalog_user_id"]) for row in subset)
        per_group = Counter(str(row["state"]["counterfactual_group_id"]) for row in subset)
        reports[component] = {
            "rows": len(subset),
            "unique_users": len(users),
            "unique_counterfactual_groups": len(groups),
            "unique_semantic_families": len(families),
            "state_condition_counts_audit_only_not_gold": dict(sorted(conditions.items())),
            "encoded_feature_columns": len(names),
            "variable_feature_columns": len(variable),
            "constant_feature_columns": constant,
            "design_matrix_rank": rank,
            "unique_runtime_feature_vectors": unique_vectors,
            "maximum_rows_per_user": max(per_user.values(), default=0),
            "maximum_rows_per_counterfactual_group": max(per_group.values(), default=0),
            "five_independent_units_per_parameter_caps": {
                "counterfactual_group_cap": group_cap,
                "user_cluster_cap": user_cap,
                "conservative_predeclared_feature_cap": conservative_cap,
            },
            "candidate_present_rate": (
                sum(bool(_feature_items(row).get("candidate_present")) for row in subset)
                / len(subset)
                if subset
                else None
            ),
            "formal_label_class_support": "PENDING_PAIRED_EFFECT_LABELS",
            "formal_power": "PENDING_PAIRED_EFFECT_LABELS_AND_FINAL_USER_SPLIT",
        }

    all_users = {str(row["state"]["catalog_user_id"]) for row in materialized}
    all_groups = {str(row["state"]["counterfactual_group_id"]) for row in materialized}
    return {
        "protocol": "pm-v1.5-v5.3-feature-identifiability-audit-v1",
        "status": "DESIGN_SUPPORT_AUDITED_FORMAL_POWER_PENDING_EFFECT_LABELS",
        "rows": len(materialized),
        "unique_users": len(all_users),
        "unique_counterfactual_groups": len(all_groups),
        "per_component": reports,
        "sample_size_rule": {
            "formal_catalog_80_users_is": "planned_balanced_design_target_not_a_scientific_truth",
            "use_all_qualified_unique_groups_within_frozen_splits": True,
            "duplicate_templates_to_n": False,
            "freeze_final_effect_n_after": [
                "formal_blueprint_integrity_audit",
                "runtime_feature_rank_and_support_audit",
                "paired_label_shape_pilot_without_method_changes",
            ],
            "sealed_16_users_role": (
                "honest held-out estimate and collapse check; a wide interval is reported "
                "rather than converted into automatic PM failure"
            ),
            "reference_plus_minus_0_05_margin_is_binary_learning_gate": False,
        },
        "learning_evidence_tiers": {
            "SUPPORTED": "reference point estimate and interval both pass",
            "DIRECTIONALLY_USABLE": (
                "selection is nontrivial and beats matched/trivial controls with practically "
                "acceptable point estimates, while intervals remain wide"
            ),
            "NOT_SUPPORTED": "constant collapse, no matched-control gain, or materially bad point estimate",
        },
        "generated_response_or_quality_risk_outcome_read": False,
        "api_calls": 0,
    }
