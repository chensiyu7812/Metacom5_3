from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence
import joblib
import numpy as np
from scipy import sparse
from sklearn.linear_model import LogisticRegression, Ridge
from sklearn.metrics import accuracy_score, log_loss, mean_absolute_error

from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import RuntimeState
from .features import FeatureBuilder
from .io import canonical_json, sha256_file, sha256_text, write_json
from .labels import (
    MemoryLabels,
    StrategyLabels,
    load_memory_labels,
    load_response_pairs,
    load_strategy_labels,
)
from .sweep import load_states
from .text import normalize_for_hash


@dataclass
class PMModel:
    """Multi-objective pre-evidence action scorer.

    Response quality is learned pairwise.  The remaining heads are independent
    action-level regressors.  In particular, omission is not folded into misuse:
    a generic no-memory response can be factually safe and still be an unsafe
    routing decision because it misses material user history.
    """

    feature_builder: FeatureBuilder
    response_ranker: LogisticRegression
    misuse_regressor: Ridge
    omission_regressor: Ridge
    memory_decision_regressor: Ridge
    strategy_risk_regressor: Ridge
    strategy_decision_regressor: Ridge
    feature_mode: str = "full"
    format_version: str = "5.1"
    fail_on_severe_catalog_ood: bool = True
    last_ood_report: dict[str, Any] | None = None

    def save(self, path: str | Path) -> None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)

    @staticmethod
    def load(path: str | Path) -> "PMModel":
        value = joblib.load(path)
        if not isinstance(value, PMModel):
            raise TypeError("checkpoint is not PMModel")
        required = (
            "omission_regressor", "memory_decision_regressor",
            "strategy_risk_regressor", "strategy_decision_regressor",
        )
        missing = [name for name in required if not hasattr(value, name)]
        if missing:
            raise RuntimeError(
                "legacy PM checkpoint lacks V5 safety heads: " + ", ".join(missing)
                + ". Retrain with scripts/10_train_pm.py."
            )
        if str(getattr(value, "format_version", "")) != "5.1":
            raise RuntimeError(
                "legacy PM checkpoint uses an uncalibrated response-score scale; "
                "retrain with the V5.1 pipeline before threshold transfer."
            )
        return value

    def score_actions(
        self, state: RuntimeState, action_ids: Sequence[str]
    ) -> dict[str, dict[str, float]]:
        rows = [(state, action_id) for action_id in action_ids]
        self.last_ood_report = self.feature_builder.ood_report(rows)
        severe = bool(self.last_ood_report.get("severe_scalar_ood"))
        severe_catalog = bool(self.last_ood_report.get("severe_catalog_ood"))
        if severe or (severe_catalog and self.fail_on_severe_catalog_ood):
            raise RuntimeError(
                "PM input is outside the validated pre-evidence feature domain; "
                "use a preregistered OOD baseline or retrain on a matched "
                "longitudinal development set. report=" + str(self.last_ood_report)
            )
        # Mild boundary drift may be clipped, but it is always surfaced through
        # ``last_ood_report``.  Severe drift is never silently clipped.
        x = self.feature_builder.transform(rows, clip_metadata=True)
        response_logit = np.clip(
            self.response_ranker.decision_function(x), -30.0, 30.0
        )
        # A bounded monotonic score makes the validation-selected epsilon more
        # portable when the final model is refit on all development cards.
        response = 1.0 / (1.0 + np.exp(-response_logit))
        misuse = np.clip(self.misuse_regressor.predict(x), 0.0, 1.0)
        omission = np.clip(self.omission_regressor.predict(x), 0.0, 1.0)
        memory_quality = np.clip(
            self.memory_decision_regressor.predict(x), 0.0, 1.0
        )
        strategy_risk = np.clip(
            self.strategy_risk_regressor.predict(x), 0.0, 1.0
        )
        strategy_quality = np.clip(
            self.strategy_decision_regressor.predict(x), 0.0, 1.0
        )
        return {
            action_id: {
                "response_score": float(response[i]),
                "misuse_risk": float(misuse[i]),
                "memory_omission_risk": float(omission[i]),
                "strategy_decision_risk": float(strategy_risk[i]),
                "memory_decision_quality": float(memory_quality[i]),
                "strategy_decision_quality": float(strategy_quality[i]),
            }
            for i, action_id in enumerate(action_ids)
        }


def _pair_training_data(
    pairs: list[dict[str, Any]],
    states: dict[str, RuntimeState],
    builder: FeatureBuilder,
    allowed_cards: set[str],
):
    usable = [
        row for row in pairs
        if row["card_id"] in allowed_cards and row["preference"] != "tie"
    ]
    by_card = Counter(row["card_id"] for row in usable)
    rows_a = [(states[row["card_id"]], row["action_a"]) for row in usable]
    rows_b = [(states[row["card_id"]], row["action_b"]) for row in usable]
    xa = builder.transform(rows_a)
    xb = builder.transform(rows_b)
    diff = xa - xb
    labels = np.asarray([1 if row["preference"] == "A" else 0 for row in usable])
    weights = np.asarray([
        1.0 / (2.0 * by_card[row["card_id"]]) for row in usable
    ])
    # Mirror every sample to remove residual A/B orientation dependence.
    x = sparse.vstack([diff, -diff], format="csr")
    y = np.concatenate([labels, 1 - labels])
    w = np.concatenate([weights, weights])
    return x, y, w, usable


def _action_regression_data(
    states: dict[str, RuntimeState],
    labels: dict[tuple[str, str], float],
    builder: FeatureBuilder,
    allowed_cards: set[str],
):
    rows = [
        (card_id, action_id, value)
        for (card_id, action_id), value in labels.items()
        if card_id in allowed_cards
        and card_id in states
        and action_id in states[card_id].allowed_actions
    ]
    if not rows:
        raise ValueError("no action-level labels for requested cards")
    by_card = Counter(card_id for card_id, _, _ in rows)
    x = builder.transform([
        (states[card_id], action_id) for card_id, action_id, _ in rows
    ])
    y = np.asarray([value for _, _, value in rows], dtype=float)
    w = np.asarray([1.0 / by_card[card_id] for card_id, _, _ in rows], dtype=float)
    return x, y, w, rows


def _fit_ridge(
    states: dict[str, RuntimeState],
    labels: dict[tuple[str, str], float],
    builder: FeatureBuilder,
    card_ids: set[str],
    alpha: float,
) -> tuple[Ridge, int]:
    x, y, w, rows = _action_regression_data(states, labels, builder, card_ids)
    model = Ridge(alpha=alpha, solver="lsqr")
    model.fit(x, y, sample_weight=w)
    return model, len(rows)


def _validation_mae(
    model: Ridge,
    labels: dict[tuple[str, str], float],
    states: dict[str, RuntimeState],
    builder: FeatureBuilder,
    card_ids: set[str],
) -> float | None:
    rows = [
        key for key in labels
        if key[0] in card_ids
        and key[0] in states
        and key[1] in states[key[0]].allowed_actions
    ]
    if not rows:
        return None
    x = builder.transform([(states[c], a) for c, a in rows])
    pred = np.clip(model.predict(x), 0.0, 1.0)
    return float(mean_absolute_error([labels[key] for key in rows], pred))


def train_pm(
    runtime_path: str | Path,
    response_path: str | Path,
    m0_path: str | Path,
    m2_path: str | Path,
    strategy_use_path: str | Path,
    strategy_omission_path: str | Path,
    train_card_ids: set[str],
    validation_card_ids: set[str],
    out_checkpoint_path: str | Path,
    out_report_path: str | Path,
    *,
    m2b_path: str | Path | None = None,
    feature_mode: str = "full",
    require_m2b: bool = True,
    c: float = 1.0,
    ridge_alpha: float = 5.0,
    seed: int = 17,
    judging_attestation_path: str | Path | None = None,
    m2b_attestation_path: str | Path | None = None,
    out_attestation_path: str | Path | None = None,
    strict_split: bool = False,
) -> dict[str, Any]:
    runtime_path = Path(runtime_path).resolve()
    response_path = Path(response_path).resolve()
    m0_path = Path(m0_path).resolve()
    m2_path = Path(m2_path).resolve()
    m2b_path = Path(m2b_path).resolve() if m2b_path is not None else None
    if require_m2b and m2b_path is None:
        raise RuntimeError(
            "M2b selected-set omission labels are required for V3.3 training. "
            "Pass --m2b-path, or explicitly use --allow-no-m2b for non-reportable debugging."
        )
    strategy_use_path = Path(strategy_use_path).resolve()
    strategy_omission_path = Path(strategy_omission_path).resolve()
    out_checkpoint_path = Path(out_checkpoint_path).resolve()
    out_report_path = Path(out_report_path).resolve()
    judging_attestation_path = Path(
        judging_attestation_path or response_path.parent / "artifact_attestation.json"
    ).resolve()
    judging_verification = require_artifact_attestation(
        judging_attestation_path,
        required_stage="full_judging",
        required_output_paths={
            "response_pairs": response_path,
            "memory_omission": m0_path,
            "memory_use": m2_path,
            "strategy_use": strategy_use_path,
            "strategy_omission": strategy_omission_path,
        },
    )
    m2b_verification = None
    if m2b_path is not None:
        m2b_attestation_path = Path(
            m2b_attestation_path or m2b_path.parent / "artifact_attestation.json"
        ).resolve()
        m2b_verification = require_artifact_attestation(
            m2b_attestation_path,
            required_stage="m2b_selected_set_omission",
            required_output_paths={"memory_selected_set_omission": m2b_path},
        )
    states = load_states(runtime_path)
    unknown_train = set(train_card_ids) - set(states)
    unknown_validation = set(validation_card_ids) - set(states)
    if unknown_train or unknown_validation:
        raise ValueError(
            f"unknown split cards: train={sorted(unknown_train)[:5]}, "
            f"validation={sorted(unknown_validation)[:5]}"
        )
    if not train_card_ids:
        raise ValueError("training split is empty")
    overlap_cards = set(train_card_ids) & set(validation_card_ids)
    if overlap_cards:
        raise ValueError(f"train/validation card overlap: {sorted(overlap_cards)[:5]}")
    train_state_ids = {states[x].state_id for x in train_card_ids}
    validation_state_ids = {states[x].state_id for x in validation_card_ids}
    state_overlap = train_state_ids & validation_state_ids
    if state_overlap:
        raise ValueError(
            "counterfactual inventory siblings cross train/validation: "
            + str(sorted(state_overlap)[:5])
        )
    train_texts = {normalize_for_hash(states[x].current_user_text) for x in train_card_ids}
    validation_texts = {
        normalize_for_hash(states[x].current_user_text) for x in validation_card_ids
    }
    train_users = {states[x].user_id for x in train_card_ids}
    validation_users = {states[x].user_id for x in validation_card_ids}
    train_families = {states[x].semantic_family for x in train_card_ids}
    validation_families = {states[x].semantic_family for x in validation_card_ids}
    split_diagnostics = {
        "card_overlap": 0,
        "state_id_overlap": 0,
        "normalized_current_text_overlap": len(train_texts & validation_texts),
        "user_overlap": len(train_users & validation_users),
        "semantic_family_overlap": len(train_families & validation_families),
    }
    if strict_split and validation_card_ids and any(
        split_diagnostics[key] for key in (
            "normalized_current_text_overlap", "user_overlap",
            "semantic_family_overlap",
        )
    ):
        raise RuntimeError(
            "strict joint holdout violated: " + str(split_diagnostics)
        )
    pairs = load_response_pairs(response_path)
    memory: MemoryLabels = load_memory_labels(m0_path, m2_path, m2b_path)
    strategy: StrategyLabels = load_strategy_labels(
        strategy_use_path, strategy_omission_path
    )
    expected_action_keys = {
        (card_id, action_id)
        for card_id in (set(train_card_ids) | set(validation_card_ids))
        for action_id in states[card_id].allowed_actions
    }
    if m2b_path is not None:
        expected_m2b_keys = {
            key for key in expected_action_keys
            if not key[1].startswith("M0+")
        }
        missing_m2b = expected_m2b_keys - set(memory.m2b_omission_keys)
        extra_m2b = set(memory.m2b_omission_keys) - expected_m2b_keys
        if missing_m2b or extra_m2b:
            raise RuntimeError(
                "M2b selected-set omission supervision is incomplete or stale: "
                f"missing={sorted(missing_m2b)[:10]}, extra={sorted(extra_m2b)[:10]}"
            )
    label_maps = {
        "misuse": memory.misuse_risk,
        "memory_omission": memory.omission_risk,
        "memory_decision": memory.decision_quality,
        "strategy_risk": strategy.risk,
        "strategy_decision": strategy.decision_quality,
    }
    missing_labels = {
        name: sorted(expected_action_keys - set(values))[:10]
        for name, values in label_maps.items()
        if expected_action_keys - set(values)
    }
    if missing_labels:
        raise RuntimeError(
            "full action-level supervision is incomplete: " + str(missing_labels)
        )

    builder = FeatureBuilder(mode=feature_mode).fit(
        [states[card_id] for card_id in sorted(train_card_ids)]
    )
    x_pair, y_pair, w_pair, train_pairs = _pair_training_data(
        pairs, states, builder, train_card_ids
    )
    if not len(y_pair) or len(set(y_pair.tolist())) < 2:
        raise ValueError("pairwise training data has fewer than two classes")
    ranker = LogisticRegression(
        C=c,
        solver="liblinear",
        max_iter=3000,
        random_state=seed,
    )
    ranker.fit(x_pair, y_pair, sample_weight=w_pair)

    misuse, n_misuse = _fit_ridge(
        states, memory.misuse_risk, builder, train_card_ids, ridge_alpha
    )
    omission, n_omission = _fit_ridge(
        states, memory.omission_risk, builder, train_card_ids, ridge_alpha
    )
    memory_decision, n_memory_decision = _fit_ridge(
        states, memory.decision_quality, builder, train_card_ids, ridge_alpha
    )
    strategy_risk, n_strategy_risk = _fit_ridge(
        states, strategy.risk, builder, train_card_ids, ridge_alpha
    )
    strategy_decision, n_strategy_decision = _fit_ridge(
        states, strategy.decision_quality, builder, train_card_ids, ridge_alpha
    )

    model = PMModel(
        feature_builder=builder,
        response_ranker=ranker,
        misuse_regressor=misuse,
        omission_regressor=omission,
        memory_decision_regressor=memory_decision,
        strategy_risk_regressor=strategy_risk,
        strategy_decision_regressor=strategy_decision,
        feature_mode=feature_mode,
    )
    model.save(out_checkpoint_path)

    # Held-out pair evaluation.
    val_pairs = [
        row for row in pairs
        if row["card_id"] in validation_card_ids and row["preference"] != "tie"
    ]
    if val_pairs:
        xa = builder.transform([
            (states[row["card_id"]], row["action_a"]) for row in val_pairs
        ])
        xb = builder.transform([
            (states[row["card_id"]], row["action_b"]) for row in val_pairs
        ])
        prob = ranker.predict_proba(xa - xb)[:, 1]
        y = np.asarray([1 if row["preference"] == "A" else 0 for row in val_pairs])
        pair_accuracy = float(accuracy_score(y, prob >= 0.5))
        pair_log_loss = float(log_loss(y, prob, labels=[0, 1]))
    else:
        pair_accuracy = pair_log_loss = None

    report = {
        "model_format_version": model.format_version,
        "feature_mode": feature_mode,
        "catalog_fingerprint_exposed": feature_mode in {"full", "catalog_only"},
        "raw_catalog_fingerprint_exposed": feature_mode in {"full", "catalog_only"},
        "response_score_transform": "sigmoid(pairwise_logit)",
        "seed": seed,
        "n_train_cards": len(train_card_ids),
        "n_validation_cards": len(validation_card_ids),
        "n_train_non_tie_pairs": len(train_pairs),
        "effective_train_states": len(train_state_ids),
        "effective_validation_states": len(validation_state_ids),
        "split_diagnostics": split_diagnostics,
        "strict_split": strict_split,
        "judging_attestation_sha256": judging_verification["attestation_sha256"],
        "m2b_attestation_sha256": (
            m2b_verification["attestation_sha256"] if m2b_verification else None
        ),
        "n_action_labels": {
            "misuse": n_misuse,
            "memory_omission": n_omission,
            "memory_decision": n_memory_decision,
            "strategy_risk": n_strategy_risk,
            "strategy_decision": n_strategy_decision,
            "m2b_selected_set_omission": len(memory.m2b_omission_keys),
        },
        "validation_pair_accuracy": pair_accuracy,
        "validation_pair_log_loss": pair_log_loss,
        "validation_mae": {
            "misuse": _validation_mae(
                misuse, memory.misuse_risk, states, builder, validation_card_ids
            ),
            "memory_omission": _validation_mae(
                omission, memory.omission_risk, states, builder,
                validation_card_ids,
            ),
            "memory_decision": _validation_mae(
                memory_decision, memory.decision_quality, states, builder,
                validation_card_ids,
            ),
            "strategy_risk": _validation_mae(
                strategy_risk, strategy.risk, states, builder,
                validation_card_ids,
            ),
            "strategy_decision": _validation_mae(
                strategy_decision, strategy.decision_quality, states, builder,
                validation_card_ids,
            ),
        },
        "text_dimension": builder.text_dim,
        "checkpoint": str(out_checkpoint_path),
    }
    write_json(out_report_path, report)
    out_attestation_path = Path(
        out_attestation_path
        or out_checkpoint_path.with_suffix(out_checkpoint_path.suffix + ".attestation.json")
    ).resolve()
    create_artifact_attestation(
        out_attestation_path,
        stage="pm_training",
        inputs={
            "runtime": runtime_path,
            "response_pairs": response_path,
            "memory_omission": m0_path,
            "memory_use": m2_path,
            **({"memory_selected_set_omission": m2b_path} if m2b_path is not None else {}),
            "strategy_use": strategy_use_path,
            "strategy_omission": strategy_omission_path,
            "full_judging_attestation": judging_attestation_path,
            **({"m2b_attestation": Path(m2b_attestation_path)} if m2b_verification else {}),
        },
        outputs={
            "checkpoint": (out_checkpoint_path, False),
            "training_report": (out_report_path, False),
        },
        parameters={
            "feature_mode": feature_mode,
            "c": c,
            "ridge_alpha": ridge_alpha,
            "seed": seed,
            "strict_split": strict_split,
            "m2b_enabled": m2b_path is not None,
            "require_m2b": bool(require_m2b),
            "train_card_ids_sha256": sha256_text(canonical_json(sorted(train_card_ids))),
            "validation_card_ids_sha256": sha256_text(canonical_json(sorted(validation_card_ids))),
        },
        expected={
            "train_cards": len(train_card_ids),
            "validation_cards": len(validation_card_ids),
            "train_states": len(train_state_ids),
            "validation_states": len(validation_state_ids),
        },
    )
    report["training_attestation"] = str(out_attestation_path)
    return report
