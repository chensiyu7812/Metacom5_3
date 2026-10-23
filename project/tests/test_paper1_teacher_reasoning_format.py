import pytest

from metacom_pm.paper1.evaluation.teacher_reasoning_format import (
    JSON_INSTRUCTION, REASONING_INSTRUCTION, parse_reasoning_result, reasoning_first_prompt,
)


def test_changes_only_format_instruction():
    evidence = "\nTASK INPUT: untouched evidence\nRESPONSE A: yes\nRESPONSE B: no"
    assert reasoning_first_prompt(JSON_INSTRUCTION + evidence) == REASONING_INSTRUCTION + evidence


@pytest.mark.parametrize("verdict", ["A_better", "B_better", "equivalent", "uncertain"])
def test_accepts_each_class_after_complete_reasoning(verdict):
    raw = f"**Reasoning:** Both are supported.\n**Result:** {verdict}"
    assert parse_reasoning_result(raw)["verdict"] == verdict


@pytest.mark.parametrize("raw", [
    "**Reasoning:** Evidence.\n**Result:** A_better\n**Result:** B_better",
    "**Reasoning:** Evidence.\n**Result:** A_better or B_better",
    "**Reasoning:** \n**Result:** equivalent",
    "**Reasoning:** Evidence.\n**Result:**",
])
def test_rejects_ambiguous_or_incomplete_results(raw):
    with pytest.raises(ValueError):
        parse_reasoning_result(raw)
