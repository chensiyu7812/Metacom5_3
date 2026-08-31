import hashlib

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import (
    CandidateLineage,
    CandidateRecord,
    Head,
    TreatmentAssignment,
)
from metacom_pm.paper1.core.treatment import parse_resource_blocks
from metacom_pm.paper1.execution.step2 import (
    STEP2_RESOURCE_PROTOCOL,
    TypedTreatmentBundle,
    build_typed_treatment_bundle,
    render_step2_resource_envelope,
)


def _candidate(
    candidate_id: str,
    head: Head,
    content: str,
    *,
    owner_id: str = "p1",
) -> CandidateRecord:
    return CandidateRecord(
        candidate_id=candidate_id,
        head=head,
        content=content,
        token_count=len(content.split()),
        lineage=CandidateLineage(
            source="test-public-source",
            owner_id=owner_id,
            source_record_ids=(f"source-{candidate_id}",),
            strict_past=True if head is not Head.RS else None,
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
        ),
    )


def test_multi_candidate_bundle_is_one_exact_resource_block_in_retrieval_order():
    first = _candidate("rs-1", Head.RS, "Acknowledge the user's uncertainty.")
    second = _candidate("rs-2", Head.RS, "Ask one open question about the concern.")
    bundle = build_typed_treatment_bundle((first, second))
    envelope = render_step2_resource_envelope(
        assignment=TreatmentAssignment.ON,
        head=Head.RS,
        bundle=bundle,
    )
    blocks = parse_resource_blocks(envelope.rendered_resource_block)
    assert len(blocks) == 1
    assert blocks[0] == envelope.resource_block
    assert blocks[0].content.index(first.content) < blocks[0].content.index(second.content)
    assert envelope.candidate_level_utility_filter is False
    assert envelope.semantic_adoption_required_for_validity is False


def test_off_envelope_contains_no_resource():
    envelope = render_step2_resource_envelope(
        assignment=TreatmentAssignment.OFF,
        head=Head.MP,
    )
    assert envelope.bundle is None
    assert envelope.resource_block is None
    assert envelope.rendered_resource_block == ""


def test_memory_bundle_rejects_wrong_owner():
    candidate = _candidate("mp-1", Head.MP, "Profile fact [occupation]: teacher", owner_id="p2")
    with pytest.raises(ValidationError, match="wrong-owner"):
        build_typed_treatment_bundle((candidate,), target_owner_id="p1")


def test_bundle_rejects_mixed_heads_and_duplicate_ids():
    rs = _candidate("same", Head.RS, "Reflect the emotion.")
    mp = _candidate("mp", Head.MP, "Profile fact [occupation]: teacher")
    with pytest.raises(ValidationError, match="mix"):
        build_typed_treatment_bundle((rs, mp))

    duplicate = _candidate("same", Head.RS, "Ask a gentle question.")
    with pytest.raises(ValidationError, match="repeat"):
        build_typed_treatment_bundle((rs, duplicate))


def test_bundle_rejects_false_content_hash():
    candidate = _candidate("rs-1", Head.RS, "Reflect the emotion.")
    bad = candidate.model_copy(
        update={"lineage": candidate.lineage.model_copy(update={"content_sha256": "a" * 64})}
    )
    with pytest.raises(ValidationError, match="hash"):
        build_typed_treatment_bundle((bad,))


def test_typed_guidance_preserves_head_semantics_without_secondary_filter():
    mp = _candidate("mp-1", Head.MP, "Profile fact [occupation]: teacher")
    mp_bundle = build_typed_treatment_bundle((mp,), target_owner_id="p1")
    mp_text = render_step2_resource_envelope(
        assignment=TreatmentAssignment.ON,
        head=Head.MP,
        bundle=mp_bundle,
    ).resource_block.content
    assert "invent preferences" in mp_text
    assert "utility filter" not in mp_text.lower()

    me = _candidate(
        "me-1",
        Head.ME,
        "Past action: took a walk User-observed outcome [helpful]: felt calmer",
    )
    me_bundle = build_typed_treatment_bundle((me,), target_owner_id="p1")
    me_text = render_step2_resource_envelope(
        assignment=TreatmentAssignment.ON,
        head=Head.ME,
        bundle=me_bundle,
    ).resource_block.content
    assert "tentative analogical context" in me_text
    assert "not a guarantee" in me_text


def test_bundle_identity_is_order_sensitive_and_deterministic():
    a = _candidate("rs-a", Head.RS, "Reflect emotion.")
    b = _candidate("rs-b", Head.RS, "Ask a question.")
    first = build_typed_treatment_bundle((a, b))
    repeated = build_typed_treatment_bundle((a, b))
    reversed_bundle = build_typed_treatment_bundle((b, a))
    assert first == repeated
    assert first.bundle_id != reversed_bundle.bundle_id


def test_envelope_schema_is_fail_closed():
    candidate = _candidate("rs-1", Head.RS, "Reflect emotion.")
    bundle = build_typed_treatment_bundle((candidate,))
    with pytest.raises(ValidationError):
        TypedTreatmentBundle(**{**bundle.model_dump(), "runtime_helpfulness": 1.0})
    with pytest.raises(ValueError, match="OFF"):
        render_step2_resource_envelope(
            assignment=TreatmentAssignment.OFF,
            head=Head.RS,
            bundle=bundle,
        )
    assert STEP2_RESOURCE_PROTOCOL == "pm-paper1-typed-step2-resource-envelope-v1"
