import hashlib
import json
from pathlib import Path

from metacom_pm.paper1.rs.strategy_bank import (
    build_strategy_source_catalog,
    rank_strategy_cards,
)
from metacom_pm.paper1.rs import strategy_bank

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
