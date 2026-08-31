"""Typed, deterministic Step2 resource delivery without a utility filter.

Step1 selects an eligible treatment bundle.  Step2 receives that exact bundle
as one hash-bound resource block and remains responsible only for generation.
It may use the resource naturally, but it may not silently rerank, delete or
replace selected candidates.  Generator non-use or misuse remains a valid
realized treatment effect rather than a row-filtering rule.
"""

from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import Field, model_validator

from ..contracts import CandidateRecord, Head, StrictContract, TreatmentAssignment
from ..core.treatment import ResourceBlock, render_resource_block

STEP2_RESOURCE_PROTOCOL = "pm-paper1-typed-step2-resource-envelope-v1"

_TEMPLATE_IDS: dict[Head, str] = {
    Head.RS: "paper1-step2-rs-atomic-move-bundle-v1",
    Head.MP: "paper1-step2-profile-memory-bundle-v1",
    Head.MS: "paper1-step2-continuity-memory-bundle-v1",
    Head.ME: "paper1-step2-experience-memory-bundle-v1",
}

_GUIDANCE: dict[Head, str] = {
    Head.RS: (
        "The following items are response-planning atomic moves, not facts about the "
        "current user. Express the assigned moves naturally in the response when composing it."
    ),
    Head.MP: (
        "The following items are strictly-past profile facts about this user. Use them only "
        "as factual context and do not invent preferences, instructions, or current status."
    ),
    Head.MS: (
        "The following items describe strictly-past event, state, or continuity facts. Treat "
        "them as past context, not as guaranteed facts about the user's current state."
    ),
    Head.ME: (
        "The following items describe a strictly-past action and a user-observed outcome. "
        "They are tentative analogical context, not a guarantee of present effectiveness."
    ),
}


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class TypedTreatmentBundle(StrictContract):
    bundle_id: str = Field(pattern=r"^paper1_bundle_[0-9a-f]{24}$")
    head: Head
    candidates: tuple[CandidateRecord, ...] = Field(min_length=1)
    target_owner_id: str | None = Field(
        default=None, description="Audit/ownership validation only; never model-visible"
    )
    candidate_ids: tuple[str, ...]
    candidate_content_sha256s: tuple[str, ...]
    total_candidate_tokens: int = Field(ge=1)
    preserves_retrieval_order: Literal[True] = True
    candidate_level_utility_filter: Literal[False] = False
    candidate_level_reranking: Literal[False] = False

    @model_validator(mode="after")
    def validate_exact_bundle(self) -> "TypedTreatmentBundle":
        if any(candidate.head is not self.head for candidate in self.candidates):
            raise ValueError("a treatment bundle cannot mix Paper-1 heads")
        ids = tuple(candidate.candidate_id for candidate in self.candidates)
        if len(set(ids)) != len(ids):
            raise ValueError("a treatment bundle cannot repeat candidate identities")
        hashes = tuple(candidate.lineage.content_sha256 for candidate in self.candidates)
        if any(
            _sha256_text(candidate.content) != digest
            for candidate, digest in zip(self.candidates, hashes, strict=True)
        ):
            raise ValueError("candidate lineage hash does not match exact candidate content")
        if self.candidate_ids != ids or self.candidate_content_sha256s != hashes:
            raise ValueError("bundle identity fields do not match candidates in retrieval order")
        if self.total_candidate_tokens != sum(
            candidate.token_count for candidate in self.candidates
        ):
            raise ValueError("total_candidate_tokens does not match the exact bundle")
        if self.head in {Head.MP, Head.MS, Head.ME}:
            if not self.target_owner_id:
                raise ValueError("memory bundles require a target owner for mechanical validation")
            if any(
                candidate.lineage.owner_id != self.target_owner_id
                for candidate in self.candidates
            ):
                raise ValueError("memory bundle contains a wrong-owner candidate")
        elif self.target_owner_id is not None:
            raise ValueError("RS bundle cannot carry a memory-owner identity")

        identity = {
            "protocol": STEP2_RESOURCE_PROTOCOL,
            "head": self.head.value,
            "candidate_ids": ids,
            "candidate_content_sha256s": hashes,
        }
        digest = _sha256_text(
            json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
        )
        if self.bundle_id != f"paper1_bundle_{digest[:24]}":
            raise ValueError("bundle_id does not match exact ordered candidate identity")
        return self


class Step2ResourceEnvelope(StrictContract):
    protocol: str = STEP2_RESOURCE_PROTOCOL
    assignment: TreatmentAssignment
    head: Head
    prompt_template_id: str
    bundle: TypedTreatmentBundle | None = None
    resource_block: ResourceBlock | None = None
    candidate_level_utility_filter: Literal[False] = False
    candidate_level_reranking: Literal[False] = False
    semantic_adoption_required_for_validity: Literal[False] = False

    @model_validator(mode="after")
    def assignment_matches_delivery(self) -> "Step2ResourceEnvelope":
        if self.protocol != STEP2_RESOURCE_PROTOCOL:
            raise ValueError("Step2 resource protocol identity mismatch")
        if self.prompt_template_id != _TEMPLATE_IDS[self.head]:
            raise ValueError("prompt template does not match typed resource head")
        if self.assignment is TreatmentAssignment.OFF:
            if self.bundle is not None or self.resource_block is not None:
                raise ValueError("OFF Step2 envelope cannot contain a resource")
            return self
        if self.bundle is None or self.resource_block is None:
            raise ValueError("ON Step2 envelope requires an exact bundle and resource block")
        if self.bundle.head is not self.head or self.resource_block.head is not self.head:
            raise ValueError("Step2 envelope head does not match its resource")
        if self.resource_block.candidate_id != self.bundle.bundle_id:
            raise ValueError("resource block must bind the whole ordered bundle")
        if self.resource_block.content != _render_bundle_content(self.bundle):
            raise ValueError("resource block bytes do not match the deterministic bundle renderer")
        return self

    @property
    def rendered_resource_block(self) -> str:
        if self.resource_block is None:
            return ""
        return render_resource_block(self.resource_block)


def build_typed_treatment_bundle(
    candidates: tuple[CandidateRecord, ...],
    *,
    target_owner_id: str | None = None,
) -> TypedTreatmentBundle:
    if not candidates:
        raise ValueError("an ON treatment bundle requires at least one candidate")
    head = candidates[0].head
    ids = tuple(candidate.candidate_id for candidate in candidates)
    hashes = tuple(candidate.lineage.content_sha256 for candidate in candidates)
    identity = {
        "protocol": STEP2_RESOURCE_PROTOCOL,
        "head": head.value,
        "candidate_ids": ids,
        "candidate_content_sha256s": hashes,
    }
    digest = _sha256_text(
        json.dumps(identity, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    )
    return TypedTreatmentBundle(
        bundle_id=f"paper1_bundle_{digest[:24]}",
        head=head,
        candidates=candidates,
        target_owner_id=target_owner_id,
        candidate_ids=ids,
        candidate_content_sha256s=hashes,
        total_candidate_tokens=sum(candidate.token_count for candidate in candidates),
    )


def _render_bundle_content(bundle: TypedTreatmentBundle) -> str:
    lines = [
        f"Typed Paper-1 resource bundle ({bundle.head.value})",
        _GUIDANCE[bundle.head],
        "Selected candidates, in frozen retrieval order:",
    ]
    for index, candidate in enumerate(bundle.candidates, start=1):
        lines.extend((f"[{index}]", candidate.content))
    return "\n".join(lines)


def render_step2_resource_envelope(
    *,
    assignment: TreatmentAssignment,
    head: Head,
    bundle: TypedTreatmentBundle | None = None,
) -> Step2ResourceEnvelope:
    if assignment is TreatmentAssignment.OFF:
        if bundle is not None:
            raise ValueError("OFF assignment cannot receive a treatment bundle")
        return Step2ResourceEnvelope(
            assignment=assignment,
            head=head,
            prompt_template_id=_TEMPLATE_IDS[head],
        )
    if bundle is None:
        raise ValueError("ON assignment requires a treatment bundle")
    if bundle.head is not head:
        raise ValueError("requested head does not match treatment bundle")
    content = _render_bundle_content(bundle)
    return Step2ResourceEnvelope(
        assignment=assignment,
        head=head,
        prompt_template_id=_TEMPLATE_IDS[head],
        bundle=bundle,
        resource_block=ResourceBlock.from_content(
            candidate_id=bundle.bundle_id,
            head=head,
            content=content,
        ),
    )
