import pytest

from metacom_pm.paper1.evaluation.local_teacher import (
    binary_benefit, natural_finish_reason, parse_local_verdict, repeated_tail,
)


def test_eos_at_boundary_is_natural_and_guards_are_not():
    assert natural_finish_reason([4, 9], [9], "timeout", 2) == "stop"
    assert natural_finish_reason([4, 8], [9], None, 2) == "context_exhausted"
    assert natural_finish_reason([4], [9], "repetition_guard", 100) == "repetition_guard"
    assert natural_finish_reason([4], [9], "timeout", 100) == "timeout"


def test_long_cycles_only():
    assert repeated_tail(list(range(32)) * 4)
    assert not repeated_tail(list(range(32)) * 3)
    assert not repeated_tail(list(range(32)) * 3 + list(range(31)) + [99])


def test_final_answer_and_long_rationale():
    import json
    raw = json.dumps({"verdict": "equivalent", "rationale": "x" * 800})
    assert parse_local_verdict(raw)["verdict"] == "equivalent"
    assert parse_local_verdict("private reasoning</think>\n" + raw, thinking=True)["verdict"] == "equivalent"
    assert parse_local_verdict("```json\n" + raw + "\n```")["verdict"] == "equivalent"
    for malformed in [raw + raw, 'text ' + raw, '{"verdict":"A_better","verdict":"B_better","rationale":"x"}']:
        with pytest.raises(ValueError):
            parse_local_verdict(malformed)
    with pytest.raises(ValueError):
        parse_local_verdict(raw, thinking=True)


def test_binary_orientation_and_missingness():
    assert binary_benefit("A_better", "ON") == 1
    assert binary_benefit("B_better", "OFF") == 1
    assert binary_benefit("A_better", "OFF") == 0
    assert binary_benefit("equivalent", "ON") == 0
    assert binary_benefit("uncertain", "ON") is None
    assert binary_benefit(None, "OFF") is None
