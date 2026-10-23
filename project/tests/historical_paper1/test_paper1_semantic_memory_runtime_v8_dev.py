from decimal import Decimal

import pytest
from pydantic import ValidationError

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.semantic_memory.budget import PriceSnapshot
from metacom_pm.paper1.semantic_memory.contracts import (
    ExtractorSessionOutput,
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    SessionCompileInput,
    SessionTurnInput,
    SupportingSpan,
)
from metacom_pm.paper1.semantic_memory.evidence_v8 import (
    ActionOutcomeOrder,
    EvidenceTemporalStatus,
    ExperienceLinkageV8,
    METypedEvidence,
    MPTypedEvidence,
    PersistenceObservation,
    V8EvidenceWireSessionOutput,
)
from metacom_pm.paper1.semantic_memory.precision_qualification import (
    CurrentValidityEvidence,
)
from metacom_pm.paper1.semantic_memory.runtime import CallParameters
from metacom_pm.paper1.semantic_memory.runtime_v8_dev import (
    COMPILER_VERSION_V8_DEV,
    RuntimeBindingV8Dev,
    SemanticMemoryV8DevVerifier,
    V8_DEV_HARD_BUDGET_USD,
    deterministic_v8_decision,
    v8_binding_violations,
)


def _endpoint():
    return Endpoint(
        base_url="https://example.invalid/compatible-mode/v1",
        model="qwen3-235b-a22b-instruct-2507",
        api_key_env="NEVER_READ_IN_TEST",
        transport="openai_chat_completions",
        supports_strict_json_schema=False,
        enable_thinking=False,
    )


def _binding():
    return RuntimeBindingV8Dev(
        region="Singapore (International)",
        endpoint=_endpoint(),
        verifier=CallParameters(max_tokens=200, maximum_prompt_tokens=300),
    )


def _price():
    return PriceSnapshot(
        snapshot_id="test-v8-price",
        provider="Alibaba Cloud Model Studio",
        region="Singapore (International)",
        currency="USD",
        input_usd_per_million_tokens=Decimal("0.01"),
        output_usd_per_million_tokens=Decimal("0.01"),
    )


class FakeClient:
    def __init__(self, output):
        self.endpoint = _endpoint()
        self.output = output
        self.calls = 0

    def chat(self, messages, *, temperature, max_tokens, seed, response_schema, retries):
        assert retries == 1
        parsed = response_schema.model_validate(self.output)
        payload = chat_request_payload(
            self.endpoint,
            messages,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            response_schema=response_schema,
        )
        self.calls += 1
        return (
            CallResult(
                text=canonical_json(parsed.model_dump(mode="json")),
                raw_response={"parsed": parsed.model_dump(mode="json")},
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                latency_ms=1.0,
                request_hash=sha256_text(canonical_json(payload)),
                provider_finish_reason="stop",
                normalized_finish_reason="complete",
                structured_output_audit={"initially_valid_json": True},
            ),
            parsed,
        )


def _mp_case():
    text = "I live in Kyoto."
    span = SupportingSpan(span_id="s1", turn_id="s:turn:1", exact_text=text)
    source = SessionCompileInput(
        owner_id="u",
        session_id="s",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(
            SessionTurnInput(
                turn_id="s:turn:1", turn_index=1, role="seeker", content=text
            ),
        ),
    )
    proposal = ProposedMPMemoryUnit(
        proposal_id="p",
        profile_field_type=MPProfileFieldType.LOCATION,
        factual_claim="The owner lives in Kyoto.",
        supporting_spans=(span,),
        entities=("Kyoto",),
        linked_prior_relations=(),
    )
    extractor = ExtractorSessionOutput(
        owner_id="u", session_id="s", mp_facts=(proposal,)
    )
    return source, extractor, proposal, span


def _mp_evidence(span, **updates):
    values = {
        "proposal_id": "p",
        "exact_support_spans": (span,),
        "field_type": MPProfileFieldType.LOCATION,
        "owner_subject_direct": True,
        "exact_entailment": True,
        "temporal_status": EvidenceTemporalStatus.CURRENT,
        "persistence": PersistenceObservation.DURABLE,
        "requires_prior_memory_inference": False,
        "current_validity_evidence": CurrentValidityEvidence.DIRECT_CURRENT,
    }
    values.update(updates)
    return MPTypedEvidence(**values)


def test_v8_provider_schema_forbids_verdict_and_reason():
    source = {
        "schema_version": "paper1-semantic-memory-typed-evidence-v8",
        "owner_id": "u",
        "session_id": "s",
        "mp_evidence": [
            {
                **_mp_evidence(
                    SupportingSpan(span_id="s", turn_id="t", exact_text="x")
                ).model_dump(mode="json"),
                "accepted": True,
                "reason": "accepted",
            }
        ],
    }
    wire = V8EvidenceWireSessionOutput.model_validate(source)
    with pytest.raises(ValidationError):
        MPTypedEvidence.model_validate(wire.mp_evidence[0])


def test_v8_deterministic_mp_acceptance_ignores_any_model_verdict():
    source, _, proposal, span = _mp_case()
    accepted = deterministic_v8_decision(source, proposal, _mp_evidence(span))
    assert accepted.accepted
    rejected = deterministic_v8_decision(
        source,
        proposal,
        _mp_evidence(
            span,
            temporal_status=EvidenceTemporalStatus.PLAN,
            persistence=PersistenceObservation.UNKNOWN,
            current_validity_evidence=CurrentValidityEvidence.NONE,
        ),
    )
    assert not rejected.accepted
    assert set(rejected.gate_reasons) >= {
        "temporal_plan",
        "persistence_unknown",
        "current_validity_not_established",
    }


def _me_case(*, shared_span: bool):
    if shared_span:
        text = "I tried breathing exercises, and they helped me feel calmer."
        action_span = outcome_span = SupportingSpan(
            span_id="both", turn_id="s:turn:1", exact_text=text
        )
        turns = (
            SessionTurnInput(
                turn_id="s:turn:1", turn_index=1, role="seeker", content=text
            ),
        )
    else:
        outcome_span = SupportingSpan(
            span_id="outcome", turn_id="s:turn:1", exact_text="I felt calmer."
        )
        action_span = SupportingSpan(
            span_id="action",
            turn_id="s:turn:2",
            exact_text="I tried breathing exercises.",
        )
        turns = (
            SessionTurnInput(
                turn_id="s:turn:1", turn_index=1, role="seeker", content="I felt calmer."
            ),
            SessionTurnInput(
                turn_id="s:turn:2",
                turn_index=2,
                role="seeker",
                content="I tried breathing exercises.",
            ),
        )
    source = SessionCompileInput(
        owner_id="u",
        session_id="s",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=turns,
    )
    proposal = ProposedMEMemoryUnit(
        proposal_id="me",
        historical_outcome_type=MEHistoricalOutcomeType.POSITIVE,
        action="The owner tried breathing exercises.",
        observed_outcome="The owner felt calmer.",
        supporting_spans=tuple(dict.fromkeys((action_span, outcome_span))),
        action_span_ids=(action_span.span_id,),
        observed_outcome_span_ids=(outcome_span.span_id,),
        entities=(),
        linked_prior_relations=(),
    )
    evidence = METypedEvidence(
        proposal_id="me",
        action_spans=(action_span,),
        owner_action=True,
        action_agentive=True,
        action_completed=True,
        outcome_spans=(outcome_span,),
        outcome_user_observed=True,
        temporal_order=ActionOutcomeOrder.ACTION_BEFORE_OUTCOME,
        same_predicate=False,
        future_or_hypothetical=False,
        purpose_or_prediction=False,
        same_experience_linkage=ExperienceLinkageV8.SAME_EXPERIENCE,
    )
    return source, proposal, evidence


def test_v8_shared_span_ordering_bug_remains_fixed():
    source, proposal, evidence = _me_case(shared_span=True)
    assert v8_binding_violations(source, proposal, evidence) == ()
    assert deterministic_v8_decision(source, proposal, evidence).accepted


def test_v8_distinct_reverse_spans_remain_mechanically_rejected():
    source, proposal, evidence = _me_case(shared_span=False)
    decision = deterministic_v8_decision(source, proposal, evidence)
    assert not decision.accepted
    assert decision.binding_violations == (
        "me_outcome_not_mechanically_after_action",
    )


def test_v8_dev_runtime_is_verifier_only_and_uses_quarter_dollar_ledger(tmp_path):
    source, extractor, _, span = _mp_case()
    output = {
        "schema_version": "paper1-semantic-memory-typed-evidence-v8",
        "owner_id": "u",
        "session_id": "s",
        "mp_evidence": [_mp_evidence(span).model_dump(mode="json")],
        "ms_evidence": [],
        "me_evidence": [],
    }
    runtime = SemanticMemoryV8DevVerifier(
        binding=_binding(),
        price=_price(),
        client=FakeClient(output),
        cache_root=tmp_path / "cache",
        attempt_ledger_root=tmp_path / "attempts",
        budget_ledger_path=tmp_path / "budget.jsonl",
    )
    evidence, rejected, decisions = runtime.verify_existing_proposals(
        source=source, extractor=extractor
    )
    assert evidence.mp_evidence[0].proposal_id == "p"
    assert rejected == ()
    assert decisions[0].accepted
    assert runtime.binding.compiler_version == COMPILER_VERSION_V8_DEV
    assert runtime.budget.hard_budget_usd == V8_DEV_HARD_BUDGET_USD
    with pytest.raises(RuntimeError, match="cannot compile"):
        runtime.compile_session(source)

