"""Integrity boundaries using fictional mechanical fixtures, no study content."""
from copy import deepcopy
import hashlib
import pytest
from metacom_pm.rl1v3.journal.memory_outcome_review import exact_supplied_sessions, validate_review


def fixture():
    source = dict(id="session", timestamp="2020-01-02", dialogue=[dict(role="seeker", idx=1, content="Example record.")])
    raw = [dict(id="owner", dialog_history=[source])]
    resource = '<resource>Completed historical session; reported 2020-01-02:\nSOURCE_EXACT example\nseeker: Example record.</resource>'
    response = "Example reply."
    blind = [dict(case_id="case", task_id="task", response=response, response_sha256=hashlib.sha256(response.encode()).hexdigest(),
                  visible_question="Example question?", supplied_resources=[resource])]
    audit = [dict(task_id="task", owner_id="owner", question="Example question?", gold="Example reference.", explicit_time=dict(upper="2020-01-01"),
                  atoms=[dict(atom_id="task:a1", sufficient_source_groups=[["session:1"]], source_evidence=[])])]
    manual = dict(cases={"case":dict(formal_status="uncertain", reward=None,
                  atoms=[dict(atom_id="task:a1", observed="complete", output_quotes=[response])],
                  claims=[dict(output_quote=response, source_refs=["session:1"])])})
    return blind, audit, manual, raw


def test_delivered_future_is_separate_from_answer_completion():
    result = validate_review(*fixture())[0]
    assert result["completed_necessary_atoms"] == 1
    assert result["legal_supported_completed_atoms"] == 0
    assert result["strict_future_sessions"] == ["session"]
    assert result["reward"] is None


@pytest.mark.parametrize("failure", ["fabricated_quote", "missing_source", "reward", "arm", "missing_atom", "wrong_hash"])
def test_review_integrity_rejects_invalid_claims(failure):
    blind, audit, manual, raw = deepcopy(fixture())
    decision = manual["cases"]["case"]
    if failure == "fabricated_quote": decision["claims"][0]["output_quote"] = "Unsaid text."
    if failure == "missing_source": decision["claims"][0]["source_refs"] = ["missing:1"]
    if failure == "reward": decision["reward"] = 1
    if failure == "arm": decision["arm"] = "exposed"
    if failure == "missing_atom": decision["atoms"] = []
    if failure == "wrong_hash": blind[0]["response_sha256"] = "changed"
    with pytest.raises((ValueError, KeyError)):
        validate_review(blind, audit, manual, raw)


def test_exact_source_body_must_match():
    blind, _, _, raw = fixture()
    sources = {("owner", "session"): raw[0]["dialog_history"][0]}
    resources = [blind[0]["supplied_resources"][0].replace("Example record.", "Changed record.")]
    with pytest.raises(ValueError):
        exact_supplied_sessions(resources, sources)
