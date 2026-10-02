import json
from collections import Counter
from pathlib import Path

from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog
from metacom_pm.paper1.rs.zero_outcome_census import (
    build_rs_decision_states,
    build_rs_zero_outcome_census,
)

ROOT = Path(__file__).resolve().parents[1]


def _states():
    return build_rs_decision_states(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )


def _cards():
    return build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )


def test_rs_state_census_uses_train_dev_nonoverlap_visible_response_opportunities():
    states = _states()
    assert len(states) == 11883
    assert Counter(state.source_split for state in states) == {
        "train": 9923,
        "validation": 1960,
    }
    assert len({state.source_dialogue_id for state in states}) == 1047
    assert all(state.current_user_text for state in states)
    assert all(
        state.query_text.splitlines()[-1].partition(": ")[2]
        == state.current_user_text.splitlines()[-1]
        for state in states
    )


def test_rs_state_overlap_sensitivity_matches_authority_literal_train_dev_universe():
    states = build_rs_decision_states(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
        exclude_evoemo_overlap=False,
    )
    assert len(states) == 12656
    assert len({state.source_dialogue_id for state in states}) == 1120


def test_rs_state_prefix_stops_before_target_supporter_and_future_turns():
    states = _states()
    source = json.loads((ROOT / "data/external/ESConv.json").read_text(encoding="utf-8"))
    split_rows = [
        json.loads(line)
        for line in (ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl")
        .read_text(encoding="utf-8")
        .splitlines()
    ]
    by_id = {row["dialogue_id"]: source[row["index"]]["dialog"] for row in split_rows}
    for state in states[::997]:
        dialogue = by_id[state.source_dialogue_id]
        expected = [
            f"{turn['speaker']}: {' '.join(turn['content'].split())}"
            for turn in dialogue[: state.decision_turn_index]
            if str(turn.get("content") or "").strip()
        ]
        assert state.visible_dialogue_text.splitlines() == expected
        assert dialogue[state.decision_turn_index]["speaker"] == "supporter"


def test_rs_census_is_leave_dialogue_out_and_contains_no_raw_text():
    states = _states()
    cards = _cards()
    selected_states = states[:12]
    rows = build_rs_zero_outcome_census(
        states=selected_states,
        cards=cards,
        diagnostic_top_k=4,
    )
    cards_by_id = {card.card_id: card for card in cards}
    assert len(rows) == len(selected_states)
    for row in rows:
        assert row.candidate_count_after_leave_dialogue_out > 0
        assert len(row.diagnostic_candidate_ids) == 4
        assert all(
            cards_by_id[card_id].source_dialogue_id != row.source_dialogue_id
            for card_id in row.diagnostic_candidate_ids
        )
        fields = row.model_dump()
        assert "query_text" not in fields
        assert "current_user_text" not in fields
        assert "visible_dialogue_text" not in fields
