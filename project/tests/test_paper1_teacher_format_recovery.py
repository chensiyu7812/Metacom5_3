import pytest

from metacom_pm.paper1.evaluation.teacher_format_recovery import recover_teacher_format, recover_reasoning_result


@pytest.mark.parametrize("typo", ["rationationale", "rationacle", "rationable"])
def test_repairs_field_spelling_without_changing_evidence_or_decision(typo):
    result = recover_teacher_format('analysis</think>\n{"verdict":"B_better","' + typo + '":"A invents dates; B says unknown."}', thinking=True)
    assert result["verdict"] == "B_better"
    assert result["rationale"] == "A invents dates; B says unknown."
    assert result["repairs"] == ["renamed_" + typo + "_to_rationale"]


def test_quotes_explicit_label_and_plain_reason_only():
    result = recover_teacher_format('{"verdict": uncertain, "rationale": Evidence cannot distinguish the responses.}')
    assert result["verdict"] == "uncertain"
    assert result["rationale"] == "Evidence cannot distinguish the responses."
    assert len(result["repairs"]) == 2


def test_trims_field_whitespace_without_changing_values():
    result = recover_teacher_format('{"verdict":"equivalent"," rationale":"Same supported facts."}')
    assert result == {"verdict": "equivalent", "rationale": "Same supported facts.",
                      "repairs": ["trimmed_JSON_key_whitespace"]}


def test_closes_object_only_when_both_values_are_complete():
    result = recover_teacher_format('{"verdict":"B_better","rationale":"B answers the question."')
    assert result["verdict"] == "B_better"
    assert result["rationale"] == "B answers the question."
    assert result["repairs"] == ["closed_single_missing_object_brace"]


@pytest.mark.parametrize("text", [
    '{"verdict":"A_better","verdict":"B_better","rationationale":"x"}',
    '{"verdict": A or B, "rationale": unknown}',
    '{"verdict": A_better, "rationale": x, "verdict": B_better}',
    '{"verdict":"A_better","rationale":"x","extra":"B_better"}',
    '{"verdict":"A_better"," verdict":"B_better","rationale":"x"}',
    '{"verdict":"B_better","rationale":"B answers the',
])
def test_ambiguous_or_extra_decisions_are_not_repaired(text):
    with pytest.raises(ValueError):
        recover_teacher_format(text)


@pytest.mark.parametrize("result,expected", [
    ("B_better is incorrect because B invents facts. A_better is incorrect because A fails the task. Therefore, the correct answer is **uncertain**.", "uncertain"),
    ("B_better is incorrect because A answers the question. A_better is correct because it matches the reference.", "A_better"),
])
def test_reads_only_explicit_native_result_endorsement(result, expected):
    parsed = recover_reasoning_result("**Reasoning:** Compare the supplied evidence.\n**Result:** " + result)
    assert parsed["verdict"] == expected
    assert parsed["rationale"].endswith(result)


@pytest.mark.parametrize("result", [
    "A_better is correct. B_better is correct.",
    "A_better is incorrect. B_better is incorrect.",
    "A_better is correct. A_better is incorrect.",
])
def test_native_result_conflicts_or_absent_selection_are_not_guessed(result):
    with pytest.raises(ValueError):
        recover_reasoning_result("**Reasoning:** Evidence.\n**Result:** " + result)


def test_native_single_terminal_period_is_format_only():
    parsed = recover_reasoning_result("**Reasoning:** Same facts.\n**Result:** equivalent.")
    assert parsed["verdict"] == "equivalent"
    assert parsed["rationale"] == "Same facts."


def test_native_period_does_not_hide_second_label():
    with pytest.raises(ValueError):
        recover_reasoning_result("**Reasoning:** Evidence.\n**Result:** A_better. B_better.")


@pytest.mark.parametrize("noun", ["answer", "result", "choice"])
def test_explicit_selection_and_not_correct_are_unambiguous(noun):
    result = "A_better is not correct. B_better is incorrect. The correct " + noun + " is **equivalent**."
    parsed = recover_reasoning_result("**Reasoning:** Both fail the task.\n**Result:** " + result)
    assert parsed["verdict"] == "equivalent"
    assert parsed["rationale"].endswith(result)
