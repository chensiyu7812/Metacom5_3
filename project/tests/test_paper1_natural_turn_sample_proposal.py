from collections import Counter, defaultdict
from pathlib import Path

from metacom_pm.io import read_json, read_jsonl, sha256_file


PROJECT = Path(__file__).resolve().parents[1]
DATA = PROJECT / "data/paper1_public_memory"


def test_natural_turn_sample_proposal_is_complete_zero_outcome_and_grouped():
    summary = read_json(DATA / "paper1_natural_turn_sample_proposal_summary_v1.json")
    base_path = DATA / summary["artifacts"]["base_sample"]["filename"]
    review_path = DATA / summary["artifacts"]["review_slot_plan"]["filename"]
    base = read_jsonl(base_path)
    review = read_jsonl(review_path)

    assert summary["status"] == "ZERO_OUTCOME_SAMPLE_PROPOSAL_READY_RESEARCHER_REVIEW_REQUIRED"
    assert summary["base_pairs"] == len(base) == 80
    assert summary["review_slots"] == len(review) == 96
    assert summary["reverse_duplicates"] == 16
    assert summary["reverse_fraction_of_base"] == 0.2
    assert summary["selected"]["RS_dialogues"] == 20
    assert summary["selected"]["memory_owners"] == 18
    assert summary["selected"]["memory_sessions"] == 20
    assert sha256_file(base_path) == summary["artifacts"]["base_sample"]["sha256"]
    assert sha256_file(review_path) == summary["artifacts"]["review_slot_plan"]["sha256"]
    assert summary["boundaries"]["target_supporter_responses_read_into_sample"] == 0
    assert summary["boundaries"]["gold_capability_or_effect_outcomes_read"] == 0
    assert summary["boundaries"]["formal_outcome_calls"] == 0
    assert summary["boundaries"]["paid_api_calls"] == 0
    assert summary["boundaries"]["human_or_machine_verdicts"] == 0
    assert summary["boundaries"]["not_an_empirical_pass_gate"] is True
    assert summary["boundaries"]["sample_size_is_final"] is False
    assert summary["boundaries"]["paid_machine_judging_authorized"] is False

    assert len({row["base_item_id"] for row in base}) == 80
    assert Counter(row["head"] for row in base) == {
        "RS": 20,
        "MP": 20,
        "ME": 20,
        "MS": 20,
    }
    assert all(row["target_supporter_response_included"] is False for row in base)
    assert all(row["effect_or_capability_outcome_read"] is False for row in base)
    assert all(row["paid_api_calls"] == 0 for row in base)
    assert all(row["visible_context"] and row["current_user_text"] for row in base)

    rs = [row for row in base if row["head"] == "RS"]
    assert len({row["source_group_id"] for row in rs}) == 20
    assert all(row["strict_past_candidate_counts"] is None for row in rs)

    memory = [row for row in base if row["head"] != "RS"]
    heads_by_state: dict[str, set[str]] = defaultdict(set)
    for row in memory:
        heads_by_state[row["source_state_id"]].add(row["head"])
        assert all(value > 0 for value in row["strict_past_candidate_counts"].values())
        assert row["strict_past_cutoff_rank"] >= 1
        assert not ({"topic", "psychological_condition", "physical_condition", "more_details"} & row.keys())
    assert len(heads_by_state) == 20
    assert all(heads == {"MP", "ME", "MS"} for heads in heads_by_state.values())

    slots_by_base: dict[str, list[dict]] = defaultdict(list)
    for row in review:
        slots_by_base[row["base_item_id"]].append(row)
        assert row["response_A"] is None and row["response_B"] is None
        assert row["verdict"] is None and row["rationale"] is None
    assert set(slots_by_base) == {row["base_item_id"] for row in base}
    assert Counter(len(rows) for rows in slots_by_base.values()) == {1: 64, 2: 16}
    assert all(
        sum(slot["reverse_duplicate"] for slot in slots) == (len(slots) - 1)
        for slots in slots_by_base.values()
    )
