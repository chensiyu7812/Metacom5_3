"""Deterministic blind packet construction for Paper 1 P2A.

Sampling strata are outcome-blind diagnostics used only to obtain semantic
range.  They are written to a physically private key and never become labels,
reviewer-visible fields, PM features, or downstream targets.
"""

from __future__ import annotations

from collections import defaultdict
import hashlib
import json
from typing import Any, Mapping, Sequence

from .contracts import StrategyCard


PACKET_PROTOCOL = "pm-v1.5-paper1-p2a-suitability-qualification-packet-v1"


def _opaque(prefix: str, *parts: Any) -> str:
    payload = json.dumps(
        [str(part) for part in parts],
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return f"{prefix}_{hashlib.sha256(payload.encode('utf-8')).hexdigest()[:24]}"


def _stable(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _pair_by_group(
    rows: Sequence[Mapping[str, Any]],
    *,
    component: str,
    group_limit: int,
    used_state_ids: set[str],
) -> list[tuple[Mapping[str, Any], str]]:
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in rows:
        if row["component"] == component and row["candidate_present"]:
            grouped[str(row["split_group_key"])].append(row)
    eligible_groups = [
        group for group, values in grouped.items() if len(values) >= 2
    ]
    eligible_groups.sort(key=_stable)
    selected: list[tuple[Mapping[str, Any], str]] = []
    selected_groups = 0
    for group in eligible_groups:
        available = [
            row for row in grouped[group] if str(row["state_id"]) not in used_state_ids
        ]
        if len(available) < 2:
            continue
        high = max(
            available,
            key=lambda row: (
                float(row["selection_score"]),
                float(row["top1_top2_margin"] or 0.0),
                _stable(str(row["state_id"])),
            ),
        )
        remaining = [row for row in available if row["state_id"] != high["state_id"]]
        low = min(
            remaining,
            key=lambda row: (
                float(row["selection_score"]),
                float(row["top1_top2_margin"] or 0.0),
                _stable(str(row["state_id"])),
            ),
        )
        selected.extend([(high, "diagnostic_high_like"), (low, "diagnostic_low_like")])
        used_state_ids.update({str(high["state_id"]), str(low["state_id"])})
        selected_groups += 1
        if selected_groups == group_limit:
            break
    if selected_groups != group_limit:
        raise ValueError(
            f"{component} only supplied {selected_groups}/{group_limit} two-row groups"
        )
    return selected


def _rs_by_mode(
    rows: Sequence[Mapping[str, Any]],
    *,
    mode: str,
    count: int,
    used_group_ids: set[str],
) -> list[tuple[Mapping[str, Any], str]]:
    available = [
        row
        for row in rows
        if row["component"] == "RS"
        and row["candidate_present"]
        and row["dataset"] == "ESConv"
        and row["retrieval_observations"].get("selection_mode") == mode
        and str(row["split_group_key"]) not in used_group_ids
    ]
    by_move: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    for row in available:
        by_move[str(row["retrieval_observations"]["move_id"])].append(row)
    for move_rows in by_move.values():
        move_rows.sort(key=lambda row: _stable(str(row["state_id"])))
    selected: list[Mapping[str, Any]] = []
    # Stable round-robin prevents AM01/AM14's much larger natural pools from
    # consuming the packet.  This is coverage sampling, never a target label.
    move_ids = sorted(by_move)
    offsets = {move: 0 for move in move_ids}
    while len(selected) < count:
        added = False
        for move in move_ids:
            values = by_move[move]
            while offsets[move] < len(values):
                candidate = values[offsets[move]]
                offsets[move] += 1
                group = str(candidate["split_group_key"])
                if group in used_group_ids:
                    continue
                selected.append(candidate)
                used_group_ids.add(group)
                added = True
                break
            if len(selected) == count:
                break
        if not added:
            break
    if len(selected) != count:
        raise ValueError(f"RS {mode} supplied {len(selected)}/{count} unique groups")
    return [(row, f"diagnostic_{mode}") for row in selected]


def select_qualification_rows(
    rows: Sequence[Mapping[str, Any]],
) -> list[tuple[Mapping[str, Any], str]]:
    """Select exactly 132 actual-Rank-1 present rows without outcomes."""

    used_states: set[str] = set()
    # Sparse ME chooses first, then MP/MS avoid its exact states.
    selected = _pair_by_group(
        rows,
        component="ME",
        group_limit=14,
        used_state_ids=used_states,
    )
    selected += _pair_by_group(
        rows,
        component="MP",
        group_limit=17,
        used_state_ids=used_states,
    )
    selected += _pair_by_group(
        rows,
        component="MS",
        group_limit=17,
        used_state_ids=used_states,
    )
    used_rs_groups: set[str] = set()
    selected += _rs_by_mode(
        rows,
        mode="transparent_priority",
        count=18,
        used_group_ids=used_rs_groups,
    )
    selected += _rs_by_mode(
        rows,
        mode="lexical_fallback",
        count=18,
        used_group_ids=used_rs_groups,
    )
    state_ids = [str(row["state_id"]) for row, _ in selected]
    if len(selected) != 132 or len(state_ids) != len(set(state_ids)):
        raise ValueError("qualification selection must be 132 unique states")
    return selected


def _visible_spans(state: Mapping[str, Any]) -> list[dict[str, Any]]:
    dialogue = (
        state["visible_dialogue"]
        if state["dataset"] == "ESConv"
        else state["visible_current_session_dialogue"]
    )
    return [
        {
            "span_id": f"V{index:03d}",
            "speaker": str(turn["speaker"]),
            "content": str(turn["content"]),
        }
        for index, turn in enumerate(dialogue, start=1)
    ]


def _candidate_spans(
    rank1: Mapping[str, Any],
    *,
    candidates: Mapping[str, Mapping[str, Any]],
    cards: Mapping[str, StrategyCard],
) -> list[dict[str, Any]]:
    candidate_id = str(rank1["actual_rank1_id"])
    if rank1["component"] == "RS":
        card = cards[candidate_id]
        return [
            {"span_id": "C001", "kind": "guidance", "content": card.guidance_text}
        ]
    candidate = candidates[candidate_id]
    spans = [
        {
            "span_id": "C001",
            "kind": "literal_candidate",
            "content": str(candidate["literal_text"]),
        }
    ]
    if rank1["component"] == "ME":
        spans.extend(
            [
                {
                    "span_id": "C002",
                    "kind": "past_action",
                    "content": str(candidate["action_span"]),
                },
                {
                    "span_id": "C003",
                    "kind": "observed_result",
                    "content": str(candidate["result_span"]),
                },
            ]
        )
    return spans


def build_blind_packets(
    *,
    selected: Sequence[tuple[Mapping[str, Any], str]],
    states: Mapping[str, Mapping[str, Any]],
    candidates: Mapping[str, Mapping[str, Any]],
    cards: Mapping[str, StrategyCard],
    component_minima: Mapping[str, Any],
    axes: Mapping[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    common: list[tuple[str, dict[str, Any], Mapping[str, Any], str]] = []
    private: list[dict[str, Any]] = []
    for rank1, stratum in selected:
        state = states[str(rank1["state_id"])]
        case_key = _opaque("case", rank1["state_id"], rank1["component"])
        surface = {
            "protocol": PACKET_PROTOCOL,
            "component": str(rank1["component"]),
            "visible_spans": _visible_spans(state),
            "candidate_spans": _candidate_spans(
                rank1, candidates=candidates, cards=cards
            ),
            "component_minimum": component_minima[str(rank1["component"])],
            "axes": axes,
            "response_contract": {
                "axis_values": ["YES", "NO", "UNKNOWN"],
                "evidence_submission": "pre_numbered_span_ids_only",
                "derived_suitability": "machine_projection_only",
            },
        }
        common.append((case_key, surface, rank1, stratum))
        private.append(
            {
                "case_key": case_key,
                "state_id": str(rank1["state_id"]),
                "component": str(rank1["component"]),
                "split_group_key": str(rank1["split_group_key"]),
                "actual_rank1_id": str(rank1["actual_rank1_id"]),
                "diagnostic_stratum": stratum,
                "selection_score": rank1["selection_score"],
                "top1_top2_margin": rank1["top1_top2_margin"],
            }
        )

    packets: list[list[dict[str, Any]]] = []
    for reviewer in ("A", "B"):
        ordered = sorted(
            common,
            key=lambda row: _stable(f"reviewer-{reviewer}::{row[0]}"),
        )
        packets.append(
            [
                {
                    **surface,
                    "review_item_id": _opaque(
                        "review", reviewer, case_key
                    ),
                    "review_position": position,
                }
                for position, (case_key, surface, _rank1, _stratum) in enumerate(
                    ordered, start=1
                )
            ]
        )
        item_id_by_case = {
            case_key: _opaque("review", reviewer, case_key)
            for case_key, _surface, _rank1, _stratum in common
        }
        for row in private:
            row[f"reviewer_{reviewer.lower()}_item_id"] = item_id_by_case[
                row["case_key"]
            ]
    return packets[0], packets[1], private
