"""Deterministic treatment delivery; never a semantic-use filter.

The resource block is part of the experimental treatment.  This module only
answers whether the assigned bytes and run binding reached the prompt.  It
does not judge whether the Generator noticed, used, or benefited from them.
"""

from __future__ import annotations

import hashlib
import json
import re

from pydantic import Field, model_validator

from ..contracts import (
    ExperimentArm,
    Head,
    StrictContract,
    TreatmentAssignment,
    TreatmentDeliveryStatus,
    TreatmentDeliveryTrace,
)

_OPEN = "<PAPER1_RESOURCE>"
_CLOSE = "</PAPER1_RESOURCE>"
_BLOCK_RE = re.compile(
    rf"{re.escape(_OPEN)}\n(?P<header>[^\n]+)\n(?P<content>.*?)(?:\n){re.escape(_CLOSE)}",
    re.DOTALL,
)


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class ResourceBlock(StrictContract):
    candidate_id: str = Field(min_length=1)
    head: Head
    content: str = Field(min_length=1)
    resource_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def hash_matches_content(self) -> "ResourceBlock":
        if sha256_text(self.content) != self.resource_sha256:
            raise ValueError("resource_sha256 does not match the exact UTF-8 content")
        if _OPEN in self.content or _CLOSE in self.content:
            raise ValueError("resource content collides with the frozen block delimiter")
        return self

    @classmethod
    def from_content(cls, *, candidate_id: str, head: Head, content: str) -> "ResourceBlock":
        return cls(
            candidate_id=candidate_id,
            head=head,
            content=content,
            resource_sha256=sha256_text(content),
        )


class RunBinding(StrictContract):
    target_id: str = Field(min_length=1)
    arm: ExperimentArm
    seed: int = Field(ge=0)
    prompt_template_id: str = Field(min_length=1)
    candidate_id: str | None = None


def render_resource_block(block: ResourceBlock) -> str:
    header = json.dumps(
        {
            "candidate_id": block.candidate_id,
            "head": block.head.value,
            "resource_sha256": block.resource_sha256,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    return f"{_OPEN}\n{header}\n{block.content}\n{_CLOSE}"


def parse_resource_blocks(prompt: str) -> tuple[ResourceBlock, ...]:
    blocks: list[ResourceBlock] = []
    for match in _BLOCK_RE.finditer(prompt):
        try:
            header = json.loads(match.group("header"))
            blocks.append(
                ResourceBlock(
                    candidate_id=header["candidate_id"],
                    head=header["head"],
                    content=match.group("content"),
                    resource_sha256=header["resource_sha256"],
                )
            )
        except (KeyError, TypeError, ValueError):
            # A malformed resource block is not silently reinterpreted.
            continue
    return tuple(blocks)


def inspect_treatment_delivery(
    *,
    assignment: TreatmentAssignment,
    rendered_prompt: str,
    expected_binding: RunBinding,
    actual_binding: RunBinding,
    expected_resource: ResourceBlock | None,
    terminal_output: str | None,
    scorer_parseable: bool | None = None,
    semantic_adoption_diagnostic: bool | None = None,
) -> TreatmentDeliveryTrace:
    """Return a mechanical delivery trace without conditioning on semantic use."""

    violations: list[str] = []
    parsed = parse_resource_blocks(rendered_prompt)

    if expected_binding != actual_binding:
        violations.append("run_binding_mismatch")
    if terminal_output is None or not terminal_output.strip():
        violations.append("terminal_empty_output")
    if scorer_parseable is False:
        violations.append("official_scorer_unparseable")

    if assignment is TreatmentAssignment.OFF:
        if expected_resource is not None:
            violations.append("off_assignment_has_expected_resource")
        if parsed:
            violations.append("off_prompt_contains_resource")
        if violations:
            return TreatmentDeliveryTrace(
                assignment=assignment,
                status=TreatmentDeliveryStatus.TECHNICAL_FAILURE,
                mechanical_violations=tuple(violations),
                semantic_adoption_diagnostic=semantic_adoption_diagnostic,
            )
        return TreatmentDeliveryTrace(
            assignment=assignment,
            status=TreatmentDeliveryStatus.NOT_ASSIGNED,
            semantic_adoption_diagnostic=semantic_adoption_diagnostic,
        )

    if expected_resource is None:
        violations.append("on_assignment_missing_expected_resource")
    if len(parsed) != 1:
        violations.append("on_prompt_resource_count_mismatch")

    delivered = parsed[0] if len(parsed) == 1 else None
    if expected_resource is not None and delivered is not None and delivered != expected_resource:
        violations.append("delivered_resource_identity_mismatch")

    if violations:
        return TreatmentDeliveryTrace(
            assignment=assignment,
            status=TreatmentDeliveryStatus.TECHNICAL_FAILURE,
            expected_resource_sha256=(
                expected_resource.resource_sha256 if expected_resource is not None else None
            ),
            delivered_resource_sha256=(delivered.resource_sha256 if delivered is not None else None),
            mechanical_violations=tuple(violations),
            semantic_adoption_diagnostic=semantic_adoption_diagnostic,
        )

    assert expected_resource is not None and delivered is not None
    return TreatmentDeliveryTrace(
        assignment=assignment,
        status=TreatmentDeliveryStatus.DELIVERED,
        expected_resource_sha256=expected_resource.resource_sha256,
        delivered_resource_sha256=delivered.resource_sha256,
        semantic_adoption_diagnostic=semantic_adoption_diagnostic,
    )
