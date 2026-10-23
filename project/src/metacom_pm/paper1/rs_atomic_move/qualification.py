"""Outcome-free contracts for RS semantics and treatment-uptake qualification."""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import Field, model_validator

from metacom_pm.io import sha256_text
from metacom_pm.paper1.contracts import StrictContract

SHA256_PATTERN = r"^[0-9a-f]{64}$"
UPTAKE_PROTOCOL = "pm-paper1-rs-treatment-uptake-qualification-v1"
STEP2_PROTOCOL = "pm-paper1-rs-single-exact-move-step2-v1"


class UptakeArm(StrEnum):
    OFF = "OFF"
    ON = "ON"


class QualificationState(StrictContract):
    qualification_state_id: str = Field(min_length=1)
    source_dataset: Literal["ESConv"] = "ESConv"
    source_split: Literal["train", "validation"]
    source_dialogue_id: str = Field(min_length=1)
    visible_state: str = Field(min_length=1)
    query_text: str = Field(min_length=1)
    future_esc_role_card_overlap: Literal[False] = False


class AssignedExactTreatment(StrictContract):
    treatment_id: str = Field(pattern=r"^rs_treatment_[0-9a-f]{24}$")
    rendered_card_text: str = Field(min_length=1)
    rendered_card_text_sha256: str = Field(pattern=SHA256_PATTERN)
    source_card_ids: tuple[str, ...] = Field(min_length=1)
    source_dialogue_ids: tuple[str, ...] = Field(min_length=1)
    atomic_move_families: tuple[str, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def verify_treatment_hash(self) -> "AssignedExactTreatment":
        if sha256_text(self.rendered_card_text) != self.rendered_card_text_sha256:
            raise ValueError("exact treatment text/hash mismatch")
        return self


class UptakeAssignment(StrictContract):
    protocol: str = UPTAKE_PROTOCOL
    assignment_id: str = Field(min_length=1)
    state: QualificationState
    arm: UptakeArm
    treatment: AssignedExactTreatment | None = None

    @model_validator(mode="after")
    def arm_matches_treatment(self) -> "UptakeAssignment":
        if self.arm is UptakeArm.OFF and self.treatment is not None:
            raise ValueError("OFF must contain no RS treatment")
        if self.arm is UptakeArm.ON and self.treatment is None:
            raise ValueError("ON must contain exactly one assigned RS treatment")
        return self


class UptakeRuntimeManifest(StrictContract):
    protocol: str = UPTAKE_PROTOCOL
    generator_provider: str = Field(min_length=1)
    generator_model: str = Field(min_length=1)
    base_prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    step2_protocol: Literal[STEP2_PROTOCOL] = STEP2_PROTOCOL
    step2_code_sha256: str = Field(pattern=SHA256_PATTERN)
    decoding_parameters_sha256: str = Field(pattern=SHA256_PATTERN)
    seed_schedule_id: str = Field(min_length=1)
    utility_filter_present: Literal[False] = False


class IntendedMoveReflection(StrEnum):
    CLEAR = "clear"
    PARTIAL = "partial"
    ABSENT = "absent"
    UNREVIEWED = "unreviewed"


class UptakeExecutionRecord(StrictContract):
    protocol: str = UPTAKE_PROTOCOL
    assignment: UptakeAssignment
    runtime_manifest_sha256: str = Field(pattern=SHA256_PATTERN)
    exact_prompt: str = Field(min_length=1)
    prompt_sha256: str = Field(pattern=SHA256_PATTERN)
    response: str = Field(min_length=1)
    response_sha256: str = Field(pattern=SHA256_PATTERN)
    treatment_delivery_trace: tuple[str, ...]
    intended_move_reflection: IntendedMoveReflection = IntendedMoveReflection.UNREVIEWED
    additional_unassigned_moves: tuple[str, ...] = ()
    mechanical_failure: bool
    mechanical_failure_reasons: tuple[str, ...] = ()
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    latency_ms: int = Field(ge=0)
    outcome_metric_fields_present: Literal[False] = False

    @model_validator(mode="after")
    def hashes_and_failure_match(self) -> "UptakeExecutionRecord":
        if sha256_text(self.exact_prompt) != self.prompt_sha256:
            raise ValueError("prompt hash mismatch")
        if sha256_text(self.response) != self.response_sha256:
            raise ValueError("response hash mismatch")
        if self.mechanical_failure != bool(self.mechanical_failure_reasons):
            raise ValueError("mechanical failure boolean/reasons mismatch")
        return self


class BlindAdherenceReview(StrictContract):
    protocol: str = UPTAKE_PROTOCOL
    blind_item_id: str = Field(min_length=1)
    reviewer_id: str = Field(min_length=1)
    assigned_arm_hidden: Literal[True] = True
    intended_move_reflection: IntendedMoveReflection
    additional_move_count: int = Field(ge=0)
    exact_treatment_was_copied_verbatim: bool
    boundary_compatible: bool
    mechanical_execution_valid: bool
    rationale: str = Field(min_length=1)
    evaluates_response_quality_or_utility: Literal[False] = False


def render_step2_prompt(*, base_prompt: str, assignment: UptakeAssignment) -> str:
    """Mechanically render OFF or one exact move; never score/filter utility."""

    if assignment.arm is UptakeArm.OFF:
        resource_block = "[RS_RESOURCE]\nOFF\n[/RS_RESOURCE]"
    else:
        assert assignment.treatment is not None
        resource_block = (
            "[RS_RESOURCE]\n"
            f"treatment_id={assignment.treatment.treatment_id}\n"
            f"exact_atomic_move={assignment.treatment.rendered_card_text}\n"
            "Use this as optional response-planning guidance. Do not quote its metadata.\n"
            "[/RS_RESOURCE]"
        )
    return (
        f"{base_prompt.rstrip()}\n\n"
        f"[VISIBLE_DIALOGUE_STATE]\n{assignment.state.visible_state}\n[/VISIBLE_DIALOGUE_STATE]\n\n"
        f"{resource_block}"
    )
