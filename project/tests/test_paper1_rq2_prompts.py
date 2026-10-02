import hashlib

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import (
    CandidateLineage,
    CandidateRecord,
    Head,
    TaskType,
    TreatmentAssignment,
)
from metacom_pm.paper1.execution.rq2_prompts import (
    GeneratorMessage,
    LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
    LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    LOCAL_GENERATOR_SERVER_PROTOCOL,
    RQ2_PROMPT_PROTOCOL,
    Rq2GeneratorRequest,
    build_dg_supporter_request,
    build_static_rq2_request,
)
from metacom_pm.paper1.execution.step2 import (
    build_typed_treatment_bundle,
    render_step2_resource_envelope,
)


def _resource(head: Head, candidate_id: str, content: str):
    candidate = CandidateRecord(
        candidate_id=candidate_id,
        head=head,
        content=content,
        token_count=len(content.split()),
        lineage=CandidateLineage(
            source="test",
            owner_id="p1",
            source_record_ids=(candidate_id,),
            strict_past=True,
            content_sha256=hashlib.sha256(content.encode()).hexdigest(),
        ),
    )
    bundle = build_typed_treatment_bundle((candidate,), target_owner_id="p1")
    return render_step2_resource_envelope(
        assignment=TreatmentAssignment.ON,
        head=head,
        bundle=bundle,
    )


def test_static_off_and_on_use_official_question_and_relevant_memory_slot():
    off = build_static_rq2_request(task_type=TaskType.QA, question="What happened?")
    assert off.protocol == RQ2_PROMPT_PROTOCOL
    assert off.provider == "local A6000 Transformers reference server"
    assert off.serving_protocol == LOCAL_GENERATOR_SERVER_PROTOCOL
    assert off.model_artifact_identity_sha256 == LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256
    assert off.chat_template_sha256 == LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256
    assert off.provider_internal_chat_template_hash_available is True
    assert off.messages[-1].content == "Question: What happened?"
    assert off.resource_heads == ()

    ms = _resource(Head.MS, "ms-1", "seeker: I changed jobs.")
    mp = _resource(Head.MP, "mp-1", "Current profile [occupation; job]: teacher")
    on = build_static_rq2_request(
        task_type=TaskType.SUMMARY,
        question="How did work change?",
        resources=(ms, mp),
    )
    assert on.resource_heads == (Head.MP, Head.MS)
    assert "Question: How did work change?\nRelevant Memory:\n" in on.messages[-1].content
    assert on.messages[-1].content.index("\"head\":\"MP\"") < on.messages[-1].content.index(
        "\"head\":\"MS\""
    )
    assert on.max_output_tokens == 256


def test_dg_places_resources_before_now_and_current_dialogue_after_now():
    me = _resource(Head.ME, "me-1", "Past event/experience: moved house")
    dialogue = (
        GeneratorMessage(role="assistant", content="Hi Alex! How are you these days?"),
        GeneratorMessage(role="user", content="Do you remember my move?"),
    )
    request = build_dg_supporter_request(
        display_name="Alex",
        current_dialogue=dialogue,
        resources=(me,),
    )
    now_index = next(
        index
        for index, message in enumerate(request.messages)
        if message.content == "The following dialogue happens now."
    )
    resource_index = next(
        index for index, message in enumerate(request.messages) if "PAPER1_RESOURCE" in message.content
    )
    assert resource_index < now_index
    assert request.messages[now_index + 1 :] == dialogue
    assert request.messages[-1].role == "user"
    assert request.max_output_tokens == 60
    assert request.hidden_seeker_simulator_fields_present is False


def test_hidden_or_malformed_dg_inputs_and_request_hash_fail_closed():
    with pytest.raises(ValueError, match="single line"):
        build_dg_supporter_request(
            display_name="Alex\nHidden topic",
            current_dialogue=(GeneratorMessage(role="user", content="hello"),),
        )
    with pytest.raises(ValueError, match="end with"):
        build_dg_supporter_request(
            display_name="Alex",
            current_dialogue=(GeneratorMessage(role="assistant", content="hello"),),
        )
    request = build_static_rq2_request(task_type=TaskType.QA, question="What happened?")
    with pytest.raises(ValidationError, match="request_messages_hash"):
        Rq2GeneratorRequest(**{**request.model_dump(), "request_messages_hash": "a" * 64})
