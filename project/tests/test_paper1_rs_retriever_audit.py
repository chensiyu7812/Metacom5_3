import hashlib
import json
from pathlib import Path

import pytest

from metacom_pm.paper1.rs.retriever_audit import build_retriever_comparison_rows
from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog
from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _surface():
    cards = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    states = build_rs_decision_states(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )[:2]
    eligible = [
        card
        for card in cards
        if card.source_dialogue_id != states[0].source_dialogue_id
    ][:3]
    eligible_second = [
        card
        for card in cards
        if card.source_dialogue_id != states[1].source_dialogue_id
    ][:3]
    by_state = {
        states[0].state_id: tuple(
            (card.card_id, 1.0 - index / 10) for index, card in enumerate(eligible)
        ),
        states[1].state_id: tuple(
            (card.card_id, 1.0 - index / 10)
            for index, card in enumerate(eligible_second)
        ),
    }
    rankings = {
        "lexical_jaccard": by_state,
        "bge_small": by_state,
        "bge_m3": by_state,
    }
    return states, cards, rankings


def test_retriever_comparison_is_text_free_complete_and_fold_exclusive():
    states, cards, rankings = _surface()
    rows = build_retriever_comparison_rows(
        states=states,
        cards=cards,
        rankings_by_method=rankings,
    )
    assert len(rows) == 2
    assert [ranking.method for ranking in rows[0].rankings] == [
        "lexical_jaccard",
        "bge_small",
        "bge_m3",
    ]
    dumped = rows[0].model_dump(mode="json")
    assert "query_text" not in dumped
    assert "visible_dialogue_text" not in dumped
    assert "target_supporter_response" not in dumped


def test_retriever_comparison_rejects_leave_dialogue_out_violation():
    states, cards, rankings = _surface()
    leaking = next(
        card for card in cards if card.source_dialogue_id == states[0].source_dialogue_id
    )
    rankings["bge_m3"] = dict(rankings["bge_m3"])
    rankings["bge_m3"][states[0].state_id] = (
        (leaking.card_id, 1.0),
        *rankings["bge_m3"][states[0].state_id][1:],
    )
    with pytest.raises(ValueError, match="leave-current-dialogue-out"):
        build_retriever_comparison_rows(
            states=states,
            cards=cards,
            rankings_by_method=rankings,
        )


def test_retriever_comparison_rejects_missing_state_surface():
    states, cards, rankings = _surface()
    rankings["bge_small"] = {
        states[0].state_id: rankings["bge_small"][states[0].state_id]
    }
    with pytest.raises(ValueError, match="state identities do not match"):
        build_retriever_comparison_rows(
            states=states,
            cards=cards,
            rankings_by_method=rankings,
        )


def test_committed_retriever_surface_is_complete_text_free_and_not_a_winner():
    summary_path = (
        ROOT / "data/paper1_public_rs/esconv_rs_retriever_comparison_summary_v1.json"
    )
    surface_path = (
        ROOT / "data/paper1_public_rs/esconv_rs_retriever_comparison_surface_v1.jsonl"
    )
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    assert summary["status"] == (
        "ZERO_OUTCOME_DECISION_SURFACE_NO_WINNER_NOT_RETRIEVER_FREEZE"
    )
    assert summary["scientific_scope"]["winner_selected"] is False
    assert summary["scientific_scope"]["formal_outcome_calls"] == 0
    assert summary["universe"]["source_card_count"] == 12169
    assert summary["universe"]["decision_state_count"] == 11883
    assert summary["provenance"]["surface_sha256"] == _sha256(surface_path)

    forbidden = {
        "query_text",
        "visible_dialogue_text",
        "current_user_text",
        "target_supporter_response",
        "situation",
        "outcome",
    }
    card_dialogues = {
        row["card_id"]: row["source_dialogue_id"]
        for row in (
            json.loads(line)
            for line in (
                ROOT
                / "data/paper1_public_rs/esconv_strategy_source_identity_dialogue_only_v2.jsonl"
            )
            .read_text(encoding="utf-8")
            .splitlines()
        )
    }
    count = 0
    for line in surface_path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        count += 1
        assert not forbidden & set(row)
        assert [ranking["method"] for ranking in row["rankings"]] == [
            "lexical_jaccard",
            "bge_small",
            "bge_m3",
        ]
        assert all(len(ranking["candidate_ids"]) == 4 for ranking in row["rankings"])
        assert all(
            card_dialogues[card_id] != row["source_dialogue_id"]
            for ranking in row["rankings"]
            for card_id in ranking["candidate_ids"]
        )
    assert count == 11883
