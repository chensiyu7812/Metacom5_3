from pathlib import Path

from metacom_pm.paper1.rs.strategy_bank import (
    build_strategy_source_catalog,
    rank_strategy_cards,
)

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
