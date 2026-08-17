from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path

import pytest

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.config import endpoint_from_config
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.semantic_memory.authorization import LiveCompilerAuthorization
from metacom_pm.paper1.semantic_memory.budget import PriceSnapshot
from metacom_pm.paper1.semantic_memory.contracts import (
    ExtractorSessionOutput,
    ExtractorWireSessionOutput,
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    MSContinuityType,
    PriorMemoryRelationType,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    SessionCompileInput,
    SessionTurnInput,
    SupportingSpan,
    VerifierDecision,
    VerifierRejectionReason,
    VerifierSessionOutput,
    VerifierWireSessionOutput,
)
from metacom_pm.paper1.semantic_memory.runtime import (
    CallParameters,
    RuntimeBinding,
    SemanticMemoryCompiler,
)
from metacom_pm.paper1.semantic_memory.prompts import (
    EXTRACTOR_SYSTEM_PROMPT,
    extractor_messages,
    verifier_messages,
)


def _endpoint() -> Endpoint:
    return Endpoint(
        base_url="https://example.invalid/compatible-mode/v1",
        model="qwen3-235b-a22b-instruct-2507",
        api_key_env="NEVER_READ_IN_OFFLINE_TEST",
        transport="openai_chat_completions",
        supports_strict_json_schema=False,
        enable_thinking=False,
    )


def _binding() -> RuntimeBinding:
    return RuntimeBinding(
        region="test-region",
        endpoint=_endpoint(),
        extractor=CallParameters(max_tokens=100, maximum_prompt_tokens=200),
        verifier=CallParameters(max_tokens=100, maximum_prompt_tokens=300),
    )


def _price() -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id="test-price",
        provider="Alibaba Cloud Model Studio",
        region="test-region",
        currency="USD",
        input_usd_per_million_tokens=Decimal("0.01"),
        output_usd_per_million_tokens=Decimal("0.01"),
    )


class FakeClient:
    def __init__(self, endpoint: Endpoint, outputs: list[object]) -> None:
        self.endpoint = endpoint
        self.outputs = list(outputs)
        self.calls = 0

    def chat(
        self,
        messages,
        *,
        temperature,
        max_tokens,
        seed,
        response_schema,
        retries,
    ):
        assert retries == 1
        supplied = self.outputs.pop(0)
        assert hasattr(supplied, "model_dump")
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


def _compiler(tmp_path, client: FakeClient) -> SemanticMemoryCompiler:
    return SemanticMemoryCompiler(
        binding=_binding(),
        price=_price(),
        client=client,
        cache_root=tmp_path / "cache",
        attempt_ledger_root=tmp_path / "attempts",
        budget_ledger_path=tmp_path / "budget.jsonl",
    )


def _accepted_case():
    text = "I moved to Kyoto."
    source = SessionCompileInput(
        owner_id="u1",
        session_id="esc1",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(
            SessionTurnInput(
                turn_id="esc1:turn:1", turn_index=1, role="seeker", content=text
            ),
        ),
    )
    proposal = ProposedMPMemoryUnit(
        proposal_id="p1",
        profile_field_type=MPProfileFieldType.LOCATION,
        factual_claim="The seeker moved to Kyoto.",
        supporting_spans=(
            SupportingSpan(
                span_id="s1", turn_id="esc1:turn:1", exact_text=text
            ),
        ),
        entities=("Kyoto",),
        linked_prior_relations=(),
    )
    extractor = ExtractorSessionOutput(
        owner_id="u1", session_id="esc1", mp_facts=(proposal,)
    )
    verifier = VerifierSessionOutput(
        owner_id="u1",
        session_id="esc1",
        decisions=(
            VerifierDecision(
                proposal_id="p1",
                accepted=True,
                reason=VerifierRejectionReason.ACCEPTED,
                factual_rationale="The seeker explicitly states the fact.",
            ),
        ),
    )
    return source, extractor, verifier


def test_acceptance_requires_schema_grounding_and_verifier_and_resumes_from_cache(tmp_path) -> None:
    source, extractor, verifier = _accepted_case()
    first_client = FakeClient(_endpoint(), [extractor, verifier])
    first = _compiler(tmp_path, first_client).compile_session(source)
    assert len(first.accepted_units) == 1
    unit = first.accepted_units[0]
    assert unit.source_turn_ids == ("esc1:turn:1",)
    assert unit.normalized_memory == "The seeker moved to Kyoto."
    assert unit.rendered_candidate_content.startswith("Profile fact [location]:")
    assert unit.profile_field_type is MPProfileFieldType.LOCATION
    assert unit.verifier_method.endswith("not_independent")
    assert first_client.calls == 2

    second_client = FakeClient(_endpoint(), [])
    second = _compiler(tmp_path, second_client).compile_session(source)
    assert second.extractor_cache_hit and second.verifier_cache_hit
    assert second.accepted_units == first.accepted_units
    assert second_client.calls == 0


def test_structural_grounding_failure_cannot_be_overridden_by_verifier(tmp_path) -> None:
    source, extractor, verifier = _accepted_case()
    bad_proposal = extractor.proposals[0].model_copy(
        update={
            "supporting_spans": (
                SupportingSpan(
                    span_id="s1",
                    turn_id="esc1:turn:1",
                    exact_text="moved to Osaka",
                ),
            )
        }
    )
    bad_extractor = extractor.model_copy(update={"mp_facts": (bad_proposal,)})
    empty_verifier = VerifierSessionOutput(
        owner_id=source.owner_id,
        session_id=source.session_id,
        decisions=(),
    )
    result = _compiler(
        tmp_path,
        FakeClient(_endpoint(), [bad_extractor, empty_verifier]),
    ).compile_session(source)
    assert result.accepted_units == ()
    assert result.grounding[0]["valid"] is False


def test_one_invalid_enum_is_rejected_without_losing_valid_proposals(tmp_path) -> None:
    source, extractor, verifier = _accepted_case()
    valid_raw = extractor.proposals[0].model_dump(mode="json")
    invalid_raw = dict(valid_raw)
    invalid_raw.update(
        {
            "proposal_id": "bad-enum",
            "profile_field_type": "invented_profile_field",
        }
    )
    wire_extractor = ExtractorWireSessionOutput(
        owner_id=source.owner_id,
        session_id=source.session_id,
        mp_facts=(valid_raw, invalid_raw),
    )
    wire_verifier = VerifierWireSessionOutput(
        owner_id=source.owner_id,
        session_id=source.session_id,
        decisions=tuple(
            decision.model_dump(mode="json") for decision in verifier.decisions
        ),
    )
    result = _compiler(
        tmp_path,
        FakeClient(_endpoint(), [wire_extractor, wire_verifier]),
    ).compile_session(source)
    assert [unit.memory_subtype.value for unit in result.accepted_units] == [
        "mp_location"
    ]
    assert len(result.schema_rejections) == 1
    assert result.schema_rejections[0].proposal_id == "bad-enum"
    assert result.schema_rejections[0].violations == ("profile_field_type:enum",)


def test_invalid_verifier_decision_cannot_accept_a_proposal(tmp_path) -> None:
    source, extractor, verifier = _accepted_case()
    invalid_decision = verifier.decisions[0].model_dump(mode="json")
    invalid_decision["reason"] = "invented_acceptance_reason"
    wire_verifier = VerifierWireSessionOutput(
        owner_id=source.owner_id,
        session_id=source.session_id,
        decisions=(invalid_decision,),
    )
    result = _compiler(
        tmp_path,
        FakeClient(_endpoint(), [extractor, wire_verifier]),
    ).compile_session(source)
    assert result.accepted_units == ()
    assert len(result.schema_rejections) == 1
    assert result.schema_rejections[0].phase == "verifier"


def test_me_regression_fixtures_are_rejected_by_semantic_verifier(tmp_path) -> None:
    fixture_path = Path(__file__).parent / "fixtures/paper1_semantic_memory/me_regressions_v1.json"
    cases = json.loads(fixture_path.read_text(encoding="utf-8"))
    for case in cases:
        text = case["text"]
        source = SessionCompileInput(
            owner_id=case["owner_id"],
            session_id=case["session_id"],
            timestamp="2024-01-01",
            chronological_rank=0,
            turns=(
                SessionTurnInput(
                    turn_id=case["turn_id"],
                    turn_index=case["turn_index"],
                    role="seeker",
                    content=text,
                ),
            ),
        )
        span = SupportingSpan(
            span_id="s1",
            turn_id=case["turn_id"],
            exact_text=text,
        )
        proposal = ProposedMEMemoryUnit(
            proposal_id="p1",
            historical_outcome_type=MEHistoricalOutcomeType.OTHER_OBSERVED,
            action="Incorrect proposed owner action.",
            observed_outcome="Incorrect proposed observed outcome.",
            supporting_spans=(span,),
            entities=(),
            linked_prior_relations=(),
            action_span_ids=("s1",),
            observed_outcome_span_ids=("s1",),
        )
        extractor = ExtractorSessionOutput(
            owner_id=case["owner_id"],
            session_id=case["session_id"],
            me_experiences=(proposal,),
        )
        verifier = VerifierSessionOutput(
            owner_id=case["owner_id"],
            session_id=case["session_id"],
            decisions=(
                VerifierDecision(
                    proposal_id="p1",
                    accepted=False,
                    reason=case["expected_rejection"],
                    factual_rationale="Regression category must be rejected.",
                ),
            ),
        )
        case_root = tmp_path / case["case_id"]
        result = _compiler(case_root, FakeClient(_endpoint(), [extractor, verifier])).compile_session(source)
        assert result.accepted_units == ()
        assert result.rejected_decisions[0].reason.value == case["expected_rejection"]


def test_config_binds_enable_thinking_false() -> None:
    endpoint = endpoint_from_config(
        {
            "endpoints": {
                "semantic_compiler": {
                    "base_url": "https://example.invalid/v1",
                    "model": "qwen3-235b-a22b-instruct-2507",
                    "api_key_env": "QWEN_API_KEY",
                    "enable_thinking": False,
                }
            }
        },
        "semantic_compiler",
    )
    assert endpoint.enable_thinking is False


def test_json_object_prompts_contain_the_exact_local_output_schema() -> None:
    extractor_schema = canonical_json(ExtractorSessionOutput.model_json_schema())
    verifier_schema = canonical_json(VerifierSessionOutput.model_json_schema())
    assert extractor_schema in extractor_messages("{}", extractor_schema)[1]["content"]
    assert verifier_schema in verifier_messages("{}", "{}", verifier_schema)[1]["content"]


def test_minimal_provider_ontology_is_bound_by_schema_and_task_first_prompt() -> None:
    schema = canonical_json(ExtractorSessionOutput.model_json_schema())
    for value in (
        *MPProfileFieldType,
        *MSContinuityType,
        *MEHistoricalOutcomeType,
        *PriorMemoryRelationType,
    ):
        assert value.value in schema
    assert "Scan the session independently for all three arrays" in EXTRACTOR_SYSTEM_PROMPT
    assert "memory_subtype" not in EXTRACTOR_SYSTEM_PROMPT
    assert "ON/OFF" in EXTRACTOR_SYSTEM_PROMPT


def test_live_authorization_fails_closed_while_outcome_lock_stays_closed() -> None:
    with pytest.raises(Exception, match="not authorized"):
        LiveCompilerAuthorization(
            semantic_compiler_calls_authorized=False,
            scope="PUBLIC_EVOEMO_SEMANTIC_COMPILER_SMOKE_ONLY",
            maximum_sessions=20,
            model="qwen3-235b-a22b-instruct-2507",
            sanitized_runtime_sha256="0" * 64,
            runtime_binding_sha256="1" * 64,
            price_snapshot_id="test-price",
            price_snapshot_sha256="2" * 64,
            hard_budget_usd=Decimal("2.00"),
            outcome_calls=0,
            outcome_lock="LOCKED_PRE_ZERO_OUTCOME_FREEZE",
        )


def test_live_authorization_separates_smoke_from_full_resume_scope() -> None:
    common = {
        "semantic_compiler_calls_authorized": True,
        "model": "qwen3-235b-a22b-instruct-2507",
        "sanitized_runtime_sha256": "0" * 64,
        "runtime_binding_sha256": "1" * 64,
        "price_snapshot_id": "test-price",
        "price_snapshot_sha256": "2" * 64,
        "hard_budget_usd": Decimal("2.00"),
        "outcome_calls": 0,
        "outcome_lock": "LOCKED_PRE_ZERO_OUTCOME_FREEZE",
    }
    with pytest.raises(Exception, match="cannot exceed 20"):
        LiveCompilerAuthorization(
            **common,
            scope="PUBLIC_EVOEMO_SEMANTIC_COMPILER_SMOKE_ONLY",
            maximum_sessions=21,
        )
    with pytest.raises(Exception, match="all 401"):
        LiveCompilerAuthorization(
            **common,
            scope="PUBLIC_EVOEMO_SEMANTIC_COMPILER_FULL_401_RESUME",
            maximum_sessions=400,
        )
    full = LiveCompilerAuthorization(
        **common,
        scope="PUBLIC_EVOEMO_SEMANTIC_COMPILER_FULL_401_RESUME",
        maximum_sessions=401,
    )
    assert full.maximum_sessions == 401
