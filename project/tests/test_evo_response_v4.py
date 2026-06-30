from metacom_pm.evo_response_v4 import (
    DEFAULT_RESPONSE_V4_CONDITIONS,
    EvoResponseV4CandidateScore,
    EvoResponseV4Judgment,
    _candidate_id_validator,
    balanced_candidate_order,
)


def test_balanced_candidate_order_cycles_each_condition_through_each_position():
    conditions = DEFAULT_RESPONSE_V4_CONDITIONS
    for variant in (0, 1):
        positions = [set() for _ in conditions]
        for unit_ordinal in range(len(conditions)):
            order = balanced_candidate_order(
                conditions,
                unit_ordinal=unit_ordinal,
                order_variant=variant,
            )
            for index, condition in enumerate(order):
                positions[index].add(condition)
        assert all(position == set(conditions) for position in positions)


def test_candidate_id_validator_rejects_missing_candidate():
    parsed = EvoResponseV4Judgment(
        candidates=[
            EvoResponseV4CandidateScore(
                candidate_id="C1",
                emotional_support=3,
                personalization=3,
                memory_appropriateness=3,
                factual_grounding=3,
                temporal_consistency=3,
                non_intrusiveness=3,
                overall=3,
                reason="ok",
            )
        ]
    )
    validator = _candidate_id_validator({"C1", "C2"})
    try:
        validator(parsed)
    except ValueError as exc:
        assert "candidate ID mismatch" in str(exc)
    else:
        raise AssertionError("validator accepted a missing candidate")
