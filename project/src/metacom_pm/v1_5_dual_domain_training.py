from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from .contracts import MemorySource
from .io import canonical_json, sha256_text
from .pm_v2_contracts import ActionLabel, PMV2Split, PMV2State


DUAL_DOMAIN_TRAINING_PROTOCOL = "pm-v1.5-dual-domain-training-input-v1"
LONGITUDINAL_DOMAIN = "longitudinal_synthetic"
ESCONV_AUXILIARY_DOMAIN = "esconv_auxiliary"
ESCONV_AUXILIARY_FAMILY = "esconv_auxiliary_strategy_routing"
ESCONV_AUXILIARY_ACTIONS = frozenset({"M0+R0", "M0+RS"})


def training_domain_for_state(state: PMV2State) -> str:
    if state.semantic_family == ESCONV_AUXILIARY_FAMILY:
        if state.provenance.get("adapted_from_runtime_state") is not True:
            raise ValueError(
                f"ESConv auxiliary state {state.state_id} lacks runtime provenance"
            )
        return ESCONV_AUXILIARY_DOMAIN
    return LONGITUDINAL_DOMAIN


def _state_universe_sha256(states: Sequence[PMV2State]) -> str:
    return sha256_text(canonical_json(sorted(state.state_id for state in states)))


def _label_universe_sha256(labels: Sequence[ActionLabel]) -> str:
    return sha256_text(
        canonical_json(
            sorted((label.state_id, label.action_id) for label in labels)
        )
    )


def _validate_unique_states(
    states: Sequence[PMV2State], *, domain: str
) -> dict[str, PMV2State]:
    by_id = {state.state_id: state for state in states}
    if not states or len(by_id) != len(states):
        raise ValueError(f"{domain} states must be unique and non-empty")
    card_ids = [state.card_id for state in states]
    if len(card_ids) != len(set(card_ids)):
        raise ValueError(f"{domain} card ids must be unique")
    return by_id


def _validate_split_group_isolation(
    states: Sequence[PMV2State], *, domain: str
) -> dict[str, Any]:
    splits_by_user: dict[str, set[str]] = {}
    for state in states:
        splits_by_user.setdefault(state.user_id, set()).add(state.split.value)
    leaked = sorted(
        user_id for user_id, splits in splits_by_user.items() if len(splits) != 1
    )
    if leaked:
        raise ValueError(f"{domain} users/dialogues cross splits: {leaked[:10]}")
    training_splits = (
        PMV2Split.TRAIN,
        PMV2Split.CALIBRATION,
        PMV2Split.INTERNAL_TEST,
    )
    unexpected = sorted(
        state.state_id for state in states if state.split not in training_splits
    )
    if unexpected:
        raise ValueError(f"{domain} contains non-training splits: {unexpected[:10]}")
    return {
        "state_counts": {
            split.value: sum(state.split is split for state in states)
            for split in training_splits
        },
        "group_counts": {
            split.value: len(
                {state.user_id for state in states if state.split is split}
            )
            for split in training_splits
        },
    }


def _validate_exact_labels(
    states: Sequence[PMV2State],
    labels: Sequence[ActionLabel],
    *,
    domain: str,
) -> None:
    state_map = {state.state_id: state for state in states}
    keys = [(label.state_id, label.action_id) for label in labels]
    if len(keys) != len(set(keys)):
        raise ValueError(f"{domain} labels contain duplicate state/action rows")
    expected = {
        (state.state_id, action_id)
        for state in states
        if state.split is not PMV2Split.INTERNAL_TEST
        for action_id in state.allowed_actions
    }
    if set(keys) != expected:
        raise ValueError(
            f"{domain} train/calibration labels are not the exact legal matrix; "
            f"missing={sorted(expected - set(keys))[:10]}, "
            f"extra={sorted(set(keys) - expected)[:10]}"
        )
    for label in labels:
        state = state_map[label.state_id]
        if label.user_id != state.user_id or label.card_id != state.card_id:
            raise ValueError(f"{domain} label identity mismatch for {label.state_id}")


@dataclass(frozen=True)
class DualDomainTrainingInputs:
    longitudinal_states: tuple[PMV2State, ...]
    auxiliary_states: tuple[PMV2State, ...]
    longitudinal_train_calibration_labels: tuple[ActionLabel, ...]
    auxiliary_train_calibration_labels: tuple[ActionLabel, ...]
    report: dict[str, Any]

    @property
    def combined_states(self) -> list[PMV2State]:
        return [*self.longitudinal_states, *self.auxiliary_states]

    @property
    def combined_train_calibration_labels(self) -> list[ActionLabel]:
        return [
            *self.longitudinal_train_calibration_labels,
            *self.auxiliary_train_calibration_labels,
        ]

    def states_for_split(self, split: PMV2Split) -> list[PMV2State]:
        return [state for state in self.combined_states if state.split is split]

    def labels_for_split(self, split: PMV2Split) -> list[ActionLabel]:
        state_ids = {state.state_id for state in self.states_for_split(split)}
        return [
            label
            for label in self.combined_train_calibration_labels
            if label.state_id in state_ids
        ]


def validate_dual_domain_training_inputs(
    *,
    longitudinal_states: Sequence[PMV2State],
    auxiliary_states: Sequence[PMV2State],
    longitudinal_train_calibration_labels: Sequence[ActionLabel],
    auxiliary_train_calibration_labels: Sequence[ActionLabel],
    pm_config: Mapping[str, Any],
) -> DualDomainTrainingInputs:
    """Validate the two training domains without opening either internal label file."""

    long_states = tuple(longitudinal_states)
    aux_states = tuple(auxiliary_states)
    long_labels = tuple(longitudinal_train_calibration_labels)
    aux_labels = tuple(auxiliary_train_calibration_labels)
    long_map = _validate_unique_states(long_states, domain=LONGITUDINAL_DOMAIN)
    aux_map = _validate_unique_states(aux_states, domain=ESCONV_AUXILIARY_DOMAIN)
    overlap = sorted(set(long_map) & set(aux_map))
    if overlap:
        raise ValueError(f"dual-domain state ids overlap: {overlap[:10]}")
    card_overlap = sorted(
        {state.card_id for state in long_states}
        & {state.card_id for state in aux_states}
    )
    if card_overlap:
        raise ValueError(f"dual-domain card ids overlap: {card_overlap[:10]}")
    user_overlap = sorted(
        {state.user_id for state in long_states}
        & {state.user_id for state in aux_states}
    )
    if user_overlap:
        raise ValueError(f"dual-domain user/dialogue ids overlap: {user_overlap[:10]}")

    long_counts = _validate_split_group_isolation(
        long_states, domain=LONGITUDINAL_DOMAIN
    )
    aux_counts = _validate_split_group_isolation(
        aux_states, domain=ESCONV_AUXILIARY_DOMAIN
    )
    data_cfg = dict(pm_config.get("data_generation") or {})
    expected_long_groups = {
        "train": int(data_cfg.get("train_users") or 0),
        "calibration": int(data_cfg.get("calibration_users") or 0),
        "internal_test": int(data_cfg.get("internal_test_users") or 0),
    }
    cases_per_user = int(data_cfg.get("cases_per_user") or 0)
    expected_long_states = {
        split: groups * cases_per_user
        for split, groups in expected_long_groups.items()
    }
    aux_cfg = dict(pm_config.get("esconv_auxiliary_training") or {})
    if aux_cfg.get("protocol") != (
        "pm-v1.5-esconv-auxiliary-bank-disjoint-seed-training-support-v1"
    ):
        raise ValueError("ESConv auxiliary training contract is missing or stale")
    expected_aux_groups = {
        str(key): int(value)
        for key, value in (aux_cfg.get("split_dialogue_counts") or {}).items()
    }
    expected_aux_states = {
        str(key): int(value)
        for key, value in (aux_cfg.get("expected_state_counts") or {}).items()
    }
    if long_counts["group_counts"] != expected_long_groups:
        raise ValueError("longitudinal group counts differ from the frozen contract")
    if long_counts["state_counts"] != expected_long_states:
        raise ValueError("longitudinal state counts differ from the frozen contract")
    if aux_counts["group_counts"] != expected_aux_groups:
        raise ValueError("ESConv auxiliary dialogue counts differ from the frozen contract")
    if aux_counts["state_counts"] != expected_aux_states:
        raise ValueError("ESConv auxiliary state counts differ from the frozen contract")
    if sum(expected_aux_states.values()) != int(aux_cfg.get("expected_total_states") or 0):
        raise ValueError("ESConv auxiliary expected total is internally inconsistent")

    for state in aux_states:
        if training_domain_for_state(state) != ESCONV_AUXILIARY_DOMAIN:
            raise ValueError(f"invalid ESConv auxiliary state {state.state_id}")
        if set(state.allowed_actions) != ESCONV_AUXILIARY_ACTIONS:
            raise ValueError(
                f"ESConv auxiliary state {state.state_id} has non-canonical actions"
            )
        for source in MemorySource:
            summary = state.inventory[source]
            if summary.available or summary.count != 0 or summary.estimated_tokens != 0:
                raise ValueError(
                    f"ESConv auxiliary state {state.state_id} exposes {source.value}"
                )
    if any(
        training_domain_for_state(state) != LONGITUDINAL_DOMAIN
        for state in long_states
    ):
        raise ValueError("longitudinal input contains ESConv auxiliary states")
    _validate_exact_labels(long_states, long_labels, domain=LONGITUDINAL_DOMAIN)
    _validate_exact_labels(aux_states, aux_labels, domain=ESCONV_AUXILIARY_DOMAIN)
    aux_state_map = {state.state_id: state for state in aux_states}
    for label in aux_labels:
        split = str(label.provenance.get("esconv_auxiliary_split") or "")
        if split != aux_state_map[label.state_id].split.value:
            raise ValueError(
                f"ESConv auxiliary label split provenance mismatch for {label.state_id}"
            )

    report = {
        "protocol": DUAL_DOMAIN_TRAINING_PROTOCOL,
        "status": "PASS",
        "internal_labels_opened": False,
        "domains": {
            LONGITUDINAL_DOMAIN: {
                **long_counts,
                "state_universe_sha256": _state_universe_sha256(long_states),
                "train_calibration_label_universe_sha256": _label_universe_sha256(
                    long_labels
                ),
            },
            ESCONV_AUXILIARY_DOMAIN: {
                **aux_counts,
                "state_universe_sha256": _state_universe_sha256(aux_states),
                "train_calibration_label_universe_sha256": _label_universe_sha256(
                    aux_labels
                ),
                "legal_actions": sorted(ESCONV_AUXILIARY_ACTIONS),
            },
        },
        "top_level_domain_weight": {
            LONGITUDINAL_DOMAIN: 0.5,
            ESCONV_AUXILIARY_DOMAIN: 0.5,
        },
        "state_id_overlap_count": 0,
        "card_id_overlap_count": 0,
        "user_or_dialogue_id_overlap_count": 0,
    }
    return DualDomainTrainingInputs(
        longitudinal_states=long_states,
        auxiliary_states=aux_states,
        longitudinal_train_calibration_labels=long_labels,
        auxiliary_train_calibration_labels=aux_labels,
        report=report,
    )
