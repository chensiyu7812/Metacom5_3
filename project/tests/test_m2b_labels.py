from metacom_pm.io import write_jsonl
from metacom_pm.labels import load_memory_labels
from metacom_pm.contracts import MemorySelectedSetOmissionJudgment
from metacom_pm.m2b import _semantic_validate_m2b


def test_m2b_selected_set_omission_updates_non_m0_omission(tmp_path):
    m0 = tmp_path / "m0.jsonl"
    m2 = tmp_path / "m2.jsonl"
    m2b = tmp_path / "m2b.jsonl"
    write_jsonl(m0, [
        {
            "card_id": "card_1",
            "action_id": "M0+R0",
            "omission_appropriateness": 2,
            "missed_memory_opportunity_severity": 0,
            "unsupported_personal_claim": 0,
            "reason": "ok",
        }
    ])
    write_jsonl(m2, [
        {
            "card_id": "card_1",
            "action_id": "ME+R0",
            "source_assessments": [
                {
                    "source": "ME",
                    "utilization": 1,
                    "unused_retrieval": 0,
                    "unnecessary_exposure": 0,
                    "stale_or_conflicting_use": 0,
                    "unsupported_personal_claim": 0,
                }
            ],
            "overall_source_set_appropriateness": 2,
            "reason": "ok",
        }
    ])
    without_m2b = load_memory_labels(m0, m2)
    assert without_m2b.omission_risk[("card_1", "ME+R0")] == 0.0

    write_jsonl(m2b, [
        {
            "card_id": "card_1",
            "action_id": "ME+R0",
            "selected_set_sufficiency": 0,
            "selected_set_omission_severity": 2,
            "missed_useful_sources": ["MS"],
            "reason": "MS was needed to cover the broader pattern.",
        }
    ])
    with_m2b = load_memory_labels(m0, m2, m2b)
    assert with_m2b.omission_risk[("card_1", "ME+R0")] == 1.0
    assert with_m2b.decision_quality[("card_1", "ME+R0")] == 0.0
    assert ("card_1", "ME+R0") in with_m2b.m2b_omission_keys


def test_m2b_validator_rejects_selected_source_as_missed(tiny_state):
    from metacom_pm.contracts import ActionOutcome, CostRecord, MemoryItem, MemorySource

    outcome = ActionOutcome(
        card_id=tiny_state.card_id,
        state_id=tiny_state.state_id,
        user_id=tiny_state.user_id,
        action_id="ME+R0",
        response="I remember the work change.",
        selected_memory_ids=["mem_aaaaaaaaaaaa0001"],
        selected_strategy_ids=[],
        memory_view=[
            MemoryItem(
                memory_id="mem_aaaaaaaaaaaa0001",
                source=MemorySource.ME,
                created_session=1,
                text="The user changed teams.",
            )
        ],
        strategy_view=[],
        cost=CostRecord(
            pm_input_tokens_est=5,
            retrieval_calls=1,
            reranker_calls=0,
            memory_tokens=10,
            strategy_tokens=0,
            base_prompt_tokens=85,
            total_input_tokens=100,
            output_tokens=20,
            latency_ms=1.0,
        ),
        model_name="mock",
        prompt_hash="hash",
        request_hash="request",
        provenance={},
    )
    bad = MemorySelectedSetOmissionJudgment(
        selected_set_sufficiency=0,
        selected_set_omission_severity=2,
        missed_useful_sources=["ME"],
        reason="badly claims selected source was missed",
    )
    try:
        _semantic_validate_m2b(bad, tiny_state, outcome)
    except ValueError as exc:
        assert "selected sources" in str(exc)
    else:
        raise AssertionError("validator accepted selected source as missed")
