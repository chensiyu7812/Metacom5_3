import json

import pytest

from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import CandidateLineage, CandidateRecord, Head, TreatmentAssignment
from metacom_pm.paper1.evaluation.pairwise_teacher import (
    RESPONSE_SCHEMA,
    TASK_RUBRICS,
    build_pairwise_teacher_prompt,
    pairwise_teacher_identity_payload,
    parse_pairwise_teacher_response,
)
from metacom_pm.paper1.execution import (
    GeneratorMessage,
    build_esc_supporter_request,
    build_typed_treatment_bundle,
    render_step2_resource_envelope,
)


def _rs_resource():
    content = "Strategy family [Question]: ask one gentle clarifying question"
    candidate = CandidateRecord(
        candidate_id="rs_test",
        head=Head.RS,
        content=content,
        token_count=8,
        lineage=CandidateLineage(
            source="test",
            owner_id="public_rs_catalog",
            source_record_ids=("rs_test",),
            strict_past=None,
            content_sha256=sha256_text(content),
        ),
    )
    bundle = build_typed_treatment_bundle((candidate,))
    return render_step2_resource_envelope(
        assignment=TreatmentAssignment.ON, head=Head.RS, bundle=bundle
    )


def test_rq1_on_off_requests_share_exact_visible_dialogue_and_decoding():
    turns = (
        GeneratorMessage(role="user", content="I feel overwhelmed."),
        GeneratorMessage(role="assistant", content="I'm here with you."),
        GeneratorMessage(role="user", content="I don't know what to do next."),
    )
    off = build_esc_supporter_request(visible_turns=turns)
    on = build_esc_supporter_request(visible_turns=turns, resource=_rs_resource())
    assert off.temperature == on.temperature == 0
    assert off.max_output_tokens == on.max_output_tokens == 256
    assert off.messages[0] == on.messages[0]
    assert off.messages[1:] == turns
    assert on.messages[2:] == turns
    assert off.resource_sha256 is None and on.resource_sha256 is not None


def test_pairwise_prompt_is_task_specific_and_blinded():
    for task in TASK_RUBRICS:
        prompt = build_pairwise_teacher_prompt(
            task=task,
            task_input="visible input",
            response_a="first anonymous response",
            response_b="second anonymous response",
            reference_material="reference" if task != "ESC" else None,
        )
        assert f"TASK: {task}" in prompt
        assert "RESPONSE A:" in prompt and "RESPONSE B:" in prompt
        assert "ON/OFF" in prompt
        assert "Response A is ON" not in prompt
        assert "Response B is ON" not in prompt


def test_pairwise_parser_is_four_class_and_fail_closed():
    parsed = parse_pairwise_teacher_response(
        json.dumps({"verdict": "equivalent", "rationale": "No material difference."})
    )
    assert parsed.verdict == "equivalent"
    for raw in (
        "equivalent",
        '{"verdict":"tie","rationale":"x"}',
        '{"verdict":"A_better","rationale":""}',
        '{"verdict":"A_better","rationale":"x","score":1}',
    ):
        with pytest.raises(ValueError):
            parse_pairwise_teacher_response(raw)


def test_teacher_identity_hashes_exact_schema_and_rubrics():
    identity = pairwise_teacher_identity_payload()
    assert identity["response_schema_sha256"] == sha256_text(canonical_json(RESPONSE_SCHEMA))
    assert identity["verdicts"] == ["A_better", "B_better", "equivalent", "uncertain"]
