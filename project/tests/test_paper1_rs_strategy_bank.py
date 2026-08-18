import hashlib
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.rs.strategy_bank import (
    StrategySourceCard,
    build_strategy_source_catalog,
    rank_strategy_cards,
)
from metacom_pm.paper1.rs import strategy_bank

HEX64 = "a" * 64


def _card_fields(**overrides):
    fields = dict(
        card_id="rs_src_" + "0" * 24,
        source_dialogue_id="esconv_0002",
        source_dialogue_ids=("esconv_0002",),
        source_turn_index=3,
        strategy_label="Question",
        retrieval_text="seeker: I feel awful.",
        guidance_text="Use the strategy.",
        example_response="How are you feeling?",
        retrieval_text_sha256=HEX64,
        example_response_sha256=HEX64,
    )
    fields.update(overrides)
    return fields

ROOT = Path(__file__).resolve().parents[1]


def test_public_strategy_source_catalog_is_train_only_and_overlap_excluded():
    cards = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    assert cards
    assert all(card.source_split == "train" for card in cards)

    excluded = set()
    train_sources = set()
    for line in (ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl").read_text().splitlines():
        import json

        row = json.loads(line)
        if row["split"] == "train":
            train_sources.add(row["dialogue_id"])
            if row["excluded_for_evoemo_overlap"]:
                excluded.add(row["dialogue_id"])
    source_ids = {card.source_dialogue_id for card in cards}
    assert source_ids <= train_sources
    assert source_ids.isdisjoint(excluded)


def test_card_rejects_source_dialogue_ids_missing_self():
    with pytest.raises(ValidationError, match="must include source_dialogue_id"):
        StrategySourceCard(**_card_fields(source_dialogue_ids=("esconv_0099",)))


def test_card_rejects_duplicate_source_dialogue_ids():
    with pytest.raises(ValidationError, match="must not contain duplicates"):
        StrategySourceCard(
            **_card_fields(source_dialogue_ids=("esconv_0002", "esconv_0002"))
        )


def test_card_rejects_unsorted_source_dialogue_ids():
    with pytest.raises(ValidationError, match="must be sorted"):
        StrategySourceCard(
            **_card_fields(source_dialogue_ids=("esconv_0009", "esconv_0002"))
        )


def test_card_accepts_sorted_unique_multi_dialogue_lineage():
    card = StrategySourceCard(
        **_card_fields(source_dialogue_ids=("esconv_0002", "esconv_0009"))
    )
    assert card.source_dialogue_ids == ("esconv_0002", "esconv_0009")


def test_source_dialogue_ids_always_includes_the_representative_dialogue():
    cards = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    for card in cards:
        assert card.source_dialogue_id in card.source_dialogue_ids
        assert tuple(sorted(set(card.source_dialogue_ids))) == card.source_dialogue_ids


def test_source_dialogue_ids_records_the_full_234_card_dedup_equivalence_lineage():
    # Real, exact regression: commit 993f6a9 (dialogue_only_v2_identities)
    # collapsed 12403 raw candidates into 12169 cards by making retrieval_text
    # context-only. Those 234 collapsed candidates must not just vanish --
    # every dialogue_id that shares a representative card's exact
    # (retrieval_text, response) content must appear in source_dialogue_ids,
    # so leave-current-dialogue-out fold exclusion catches them too.
    cards = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    assert len(cards) == 12169
    multi_dialogue_cards = [card for card in cards if len(card.source_dialogue_ids) > 1]
    assert len(multi_dialogue_cards) == 82
    assert sum(len(card.source_dialogue_ids) - 1 for card in multi_dialogue_cards) == 234


def test_duplicate_content_from_a_different_dialogue_is_folded_into_one_cards_lineage(
    tmp_path, monkeypatch
):
    esconv = json.loads((ROOT / "data/external/ESConv.json").read_text())
    # esconv_0002/0003/0004 (list indices 2/3/4) are all real train,
    # non-EvoEmo-overlap dialogues -- replace only their content with a
    # byte-identical, no-preceding-context supporter turn so their
    # retrieval_text falls back to the response itself for all three,
    # a minimal controlled duplicate-content fixture.
    duplicate_turn = {
        "speaker": "supporter",
        "content": "I'm really glad you reached out today.",
        "annotation": {"strategy": "Affirmation and Reassurance"},
    }
    fixture = list(esconv)
    for index in (2, 3, 4):
        fixture[index] = {"dialog": [dict(duplicate_turn)]}
    fixture_path = tmp_path / "esconv_fixture.json"
    fixture_path.write_text(json.dumps(fixture), encoding="utf-8")

    monkeypatch.setattr(
        strategy_bank, "EXPECTED_ESCONV_SHA256", hashlib.sha256(fixture_path.read_bytes()).hexdigest()
    )
    cards = build_strategy_source_catalog(
        esconv_path=fixture_path,
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    matching = [c for c in cards if c.example_response == duplicate_turn["content"]]
    assert len(matching) == 1
    card = matching[0]
    assert card.source_dialogue_ids == ("esconv_0002", "esconv_0003", "esconv_0004")
    assert card.source_dialogue_id == "esconv_0002"


def test_overlap_policy_can_be_audited_without_silently_changing_the_default():
    conservative = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    authority_literal = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
        exclude_evoemo_overlap=False,
    )
    assert len(conservative) == 12169
    assert len(authority_literal) == 12906
    assert {
        (card.retrieval_text.casefold(), card.example_response.casefold())
        for card in conservative
    } <= {
        (card.retrieval_text.casefold(), card.example_response.casefold())
        for card in authority_literal
    }


def test_retrieval_is_deterministic_and_fold_exclusive():
    cards = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    first_source = cards[0].source_dialogue_id
    kwargs = {
        "cards": cards,
        "query_text": "I feel anxious and overwhelmed about my job.",
        "excluded_dialogue_ids": {first_source},
        "top_k": 4,
    }
    left = rank_strategy_cards(**kwargs)
    right = rank_strategy_cards(**kwargs)
    assert left == right
    assert len(left) == 4
    assert all(row.card.source_dialogue_id != first_source for row in left)
    assert [row.rank for row in left] == [1, 2, 3, 4]


def test_retrieval_excludes_every_dialogue_in_a_cards_equivalence_lineage():
    cards = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    multi = next(card for card in cards if len(card.source_dialogue_ids) > 1)
    non_representative = next(
        dialogue_id
        for dialogue_id in multi.source_dialogue_ids
        if dialogue_id != multi.source_dialogue_id
    )
    result = rank_strategy_cards(
        cards=(multi,),
        query_text=multi.retrieval_text,
        excluded_dialogue_ids={non_representative},
        top_k=1,
    )
    assert result == ()


def test_strategy_source_contract_contains_no_outcome_fields():
    cards = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    fields = set(cards[0].model_dump())
    assert fields.isdisjoint({"survey_score", "feedback", "gold", "quality", "risk", "pass"})


def test_catalog_is_invariant_to_situation_and_outcome_fields(tmp_path, monkeypatch):
    source = json.loads((ROOT / "data/external/ESConv.json").read_text(encoding="utf-8"))
    original = build_strategy_source_catalog(
        esconv_path=ROOT / "data/external/ESConv.json",
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    for row in source:
        row["situation"] = "PRIVILEGED SITUATION MUST NOT CHANGE THE CATALOG"
        row["survey_score"] = {"forbidden": "changed"}
        row["seeker_question1"] = "changed"
        row["seeker_question2"] = "changed"
        row["supporter_question1"] = "changed"
        row["supporter_question2"] = "changed"
        for turn in row["dialog"]:
            if turn["speaker"] == "seeker":
                turn["annotation"] = {"feedback": "changed"}
    changed_path = tmp_path / "ESConv.changed.json"
    changed_path.write_text(json.dumps(source, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(
        strategy_bank,
        "EXPECTED_ESCONV_SHA256",
        hashlib.sha256(changed_path.read_bytes()).hexdigest(),
    )
    changed = build_strategy_source_catalog(
        esconv_path=changed_path,
        split_manifest_path=ROOT / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    assert changed == original
