from decimal import Decimal

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
from metacom_pm.paper1.semantic_memory.precision_qualification import (
    CurrentValidityEvidence,
    DurabilityEvidence,
    ExperienceLinkage,
    MEPrecisionDecision,
    MEPrecisionReason,
    MPPrecisionDecision,
    MPPrecisionReason,
    PrecisionVerifierSessionOutput,
)
from metacom_pm.paper1.semantic_memory.runtime import CallParameters
from metacom_pm.paper1.semantic_memory.runtime_v7 import (
    COMPILER_VERSION_V7,
    RuntimeBindingV7,
    SemanticMemoryCompilerV7,
    precision_binding_violations,
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
    return RuntimeBindingV7(
        region="Singapore (International)",
        endpoint=_endpoint(),
        extractor=CallParameters(max_tokens=100, maximum_prompt_tokens=200),
        verifier=CallParameters(max_tokens=200, maximum_prompt_tokens=300),
    )


def _price():
    return PriceSnapshot(
        snapshot_id="test-v7-price",
        provider="Alibaba Cloud Model Studio",
        region="Singapore (International)",
        currency="USD",
        input_usd_per_million_tokens=Decimal("0.01"),
        output_usd_per_million_tokens=Decimal("0.01"),
    )


class FakeClient:
    def __init__(self, outputs):
        self.endpoint = _endpoint()
        self.outputs = list(outputs)
        self.calls = 0

    def chat(self, messages, *, temperature, max_tokens, seed, response_schema, retries):
        assert retries == 1
        supplied = self.outputs.pop(0)
        parsed = response_schema.model_validate(supplied.model_dump(mode="json"))
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
                raw_response={"call": self.calls, "parsed": parsed.model_dump(mode="json")},
                usage={"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15},
                latency_ms=1.0,
                request_hash=sha256_text(canonical_json(payload)),
                provider_finish_reason="stop",
                normalized_finish_reason="complete",
                structured_output_audit={"initially_valid_json": True},
            ),
            parsed,
        )


def _case(field_type=MPProfileFieldType.LOCATION):
    text = "I live in Kyoto."
    span = SupportingSpan(span_id="s1", turn_id="s:turn:1", exact_text=text)
    source = SessionCompileInput(
        owner_id="u",
        session_id="s",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(
            SessionTurnInput(
                turn_id="s:turn:1",
                turn_index=1,
                role="seeker",
                content=text,
            ),
        ),
    )
    proposal = ProposedMPMemoryUnit(
        proposal_id="p",
        profile_field_type=field_type,
        factual_claim="The owner lives in Kyoto.",
        supporting_spans=(span,),
        entities=("Kyoto",),
        linked_prior_relations=(),
    )
    extractor = ExtractorSessionOutput(
        owner_id="u",
        session_id="s",
        mp_facts=(proposal,),
    )
    return source, extractor, span


def _compiler(tmp_path, outputs):
    return SemanticMemoryCompilerV7(
        binding=_binding(),
        price=_price(),
        client=FakeClient(outputs),
        cache_root=tmp_path / "cache",
        attempt_ledger_root=tmp_path / "attempts",
        budget_ledger_path=tmp_path / "budget.jsonl",
    )


def test_v7_live_path_binds_precision_prompt_schema_gate_and_accepts(tmp_path):
    source, extractor, span = _case()
    decision = MPPrecisionDecision(
        proposal_id="p",
        exact_support_span=(span,),
        field_type=MPProfileFieldType.LOCATION,
        owner_subject_direct=True,
        directly_entailed_by_current_span=True,
        durability_evidence=DurabilityEvidence.DIRECT_ENDURING,
        current_validity_evidence=CurrentValidityEvidence.DIRECT_CURRENT,
        episodic_or_transient=False,
        future_plan=False,
        requires_prior_inference=False,
        accepted=True,
        reason=MPPrecisionReason.ACCEPTED,
    )
    verifier = PrecisionVerifierSessionOutput(
        owner_id="u", session_id="s", mp_decisions=(decision,)
    )
    result = _compiler(tmp_path, [extractor, verifier]).compile_session(source)
    assert result.compiler_version == COMPILER_VERSION_V7
    assert result.precision_verifier == verifier
    assert result.precision_binding == (
        {"proposal_id": "p", "valid": True, "violations": ()},
    )
    assert len(result.accepted_units) == 1
    assert result.accepted_units[0].compiler_version == COMPILER_VERSION_V7
    assert result.accepted_units[0].verifier_method.startswith("same_qwen_model_v7")


def test_v7_local_binding_rejects_verifier_field_type_drift(tmp_path):
    source, extractor, span = _case()
    decision = MPPrecisionDecision(
        proposal_id="p",
        exact_support_span=(span,),
        field_type=MPProfileFieldType.EDUCATION,
        owner_subject_direct=True,
        directly_entailed_by_current_span=True,
        durability_evidence=DurabilityEvidence.DIRECT_ENDURING,
        current_validity_evidence=CurrentValidityEvidence.DIRECT_CURRENT,
        episodic_or_transient=False,
        future_plan=False,
        requires_prior_inference=False,
        accepted=True,
        reason=MPPrecisionReason.ACCEPTED,
    )
    verifier = PrecisionVerifierSessionOutput(
        owner_id="u", session_id="s", mp_decisions=(decision,)
    )
    result = _compiler(tmp_path, [extractor, verifier]).compile_session(source)
    assert result.accepted_units == ()
    assert result.precision_binding[0]["violations"] == (
        "precision_mp_field_type_mismatch",
    )


def test_v7_identity_changes_when_verifier_call_parameters_change():
    first = _binding()
    second = first.model_copy(
        update={"verifier": CallParameters(max_tokens=999, maximum_prompt_tokens=300)}
    )
    assert first.identity_sha256 != second.identity_sha256


def _me_decision(proposal_id, *, action_span, outcome_span):
    return MEPrecisionDecision(
        proposal_id=proposal_id,
        action_span=(action_span,),
        action_is_owner=True,
        action_is_agentive=True,
        action_is_completed=True,
        outcome_span=(outcome_span,),
        outcome_is_user_observed=True,
        action_before_outcome=True,
        same_predicate=False,
        future_or_hypothetical=False,
        purpose_or_prediction_as_outcome=False,
        experience_linkage=ExperienceLinkage.SAME_EXPERIENCE,
        accepted=True,
        reason=MEPrecisionReason.ACCEPTED,
    )


def test_v7_binding_allows_one_exact_span_to_evidence_ordered_me_propositions():
    text = "I tried breathing exercises, and they helped me feel calmer."
    span = SupportingSpan(span_id="both", turn_id="s:turn:1", exact_text=text)
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
    proposal = ProposedMEMemoryUnit(
        proposal_id="me",
        historical_outcome_type=MEHistoricalOutcomeType.POSITIVE,
        action="The owner tried breathing exercises.",
        observed_outcome="The owner felt calmer.",
        supporting_spans=(span,),
        action_span_ids=("both",),
        observed_outcome_span_ids=("both",),
        entities=(),
        linked_prior_relations=(),
    )
    decision = _me_decision("me", action_span=span, outcome_span=span)
    assert precision_binding_violations(source, proposal, decision) == ()


def test_v7_binding_still_rejects_distinct_outcome_span_before_action_span():
    outcome_span = SupportingSpan(
        span_id="outcome", turn_id="s:turn:1", exact_text="I felt calmer."
    )
    action_span = SupportingSpan(
        span_id="action", turn_id="s:turn:2", exact_text="I tried breathing exercises."
    )
    source = SessionCompileInput(
        owner_id="u",
        session_id="s",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(
            SessionTurnInput(
                turn_id="s:turn:1", turn_index=1, role="seeker", content="I felt calmer."
            ),
            SessionTurnInput(
                turn_id="s:turn:2",
                turn_index=2,
                role="seeker",
                content="I tried breathing exercises.",
            ),
        ),
    )
    proposal = ProposedMEMemoryUnit(
        proposal_id="me",
        historical_outcome_type=MEHistoricalOutcomeType.POSITIVE,
        action="The owner tried breathing exercises.",
        observed_outcome="The owner felt calmer.",
        supporting_spans=(outcome_span, action_span),
        action_span_ids=("action",),
        observed_outcome_span_ids=("outcome",),
        entities=(),
        linked_prior_relations=(),
    )
    decision = _me_decision(
        "me", action_span=action_span, outcome_span=outcome_span
    )
    assert precision_binding_violations(source, proposal, decision) == (
        "precision_me_outcome_not_mechanically_after_action",
    )
