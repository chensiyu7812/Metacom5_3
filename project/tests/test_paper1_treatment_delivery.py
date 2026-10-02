import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import (
    ExperimentArm,
    Head,
    TreatmentAssignment,
    TreatmentDeliveryStatus,
)
from metacom_pm.paper1.core.treatment import (
    ResourceBlock,
    RunBinding,
    inspect_treatment_delivery,
    parse_resource_blocks,
    render_resource_block,
)


def _binding(candidate_id="rs-1"):
    return RunBinding(
        target_id="card-1",
        arm=ExperimentArm.RS_FIXED_HIGH,
        seed=7,
        prompt_template_id="esc-response-v1",
        candidate_id=candidate_id,
    )


def test_exact_on_resource_is_delivered_even_when_semantically_unused():
    resource = ResourceBlock.from_content(candidate_id="rs-1", head=Head.RS, content="Reflect emotion.")
    prompt = "System\n" + render_resource_block(resource) + "\nUser"
    trace = inspect_treatment_delivery(
        assignment=TreatmentAssignment.ON,
        rendered_prompt=prompt,
        expected_binding=_binding(),
        actual_binding=_binding(),
        expected_resource=resource,
        terminal_output="I hear how difficult this is.",
        semantic_adoption_diagnostic=False,
    )
    assert trace.status is TreatmentDeliveryStatus.DELIVERED
    assert trace.mechanically_valid is True
    assert parse_resource_blocks(prompt) == (resource,)


def test_binding_mismatch_is_technical_failure():
    resource = ResourceBlock.from_content(candidate_id="rs-1", head=Head.RS, content="Reflect emotion.")
    trace = inspect_treatment_delivery(
        assignment=TreatmentAssignment.ON,
        rendered_prompt=render_resource_block(resource),
        expected_binding=_binding(),
        actual_binding=_binding(candidate_id="rs-2"),
        expected_resource=resource,
        terminal_output="response",
    )
    assert trace.status is TreatmentDeliveryStatus.TECHNICAL_FAILURE
    assert "run_binding_mismatch" in trace.mechanical_violations


def test_off_prompt_must_not_contain_a_resource():
    resource = ResourceBlock.from_content(candidate_id="rs-1", head=Head.RS, content="Reflect emotion.")
    binding = _binding(candidate_id=None)
    trace = inspect_treatment_delivery(
        assignment=TreatmentAssignment.OFF,
        rendered_prompt=render_resource_block(resource),
        expected_binding=binding,
        actual_binding=binding,
        expected_resource=None,
        terminal_output="response",
    )
    assert trace.status is TreatmentDeliveryStatus.TECHNICAL_FAILURE
    assert trace.mechanically_valid is False


def test_resource_hash_is_exact_and_fail_closed():
    with pytest.raises(ValidationError):
        ResourceBlock(
            candidate_id="rs-1",
            head=Head.RS,
            content="changed",
            resource_sha256="a" * 64,
        )
