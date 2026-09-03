from decimal import Decimal

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.multi_view_memory.contracts import (
    EventExperienceType,
    EventTemporalStatus,
    ExtractorSessionOutput,
    MultiViewSessionInput,
    ProfileFieldType,
    ProposedEventExperienceUnit,
    ProposedProfileViewUnit,
    ProposedSourceSpan,
    SourceTurn,
    VerificationDecision,
    VerificationReason,
    VerifierSessionOutput,
)
from metacom_pm.paper1.multi_view_memory.runtime import (
    CallParameters,
    MultiViewMemoryCompiler,
    PriceSnapshot,
    RuntimeBinding,
)


def _endpoint():
    return Endpoint(
        base_url="https://example.invalid/compatible-mode/v1",
        model="qwen3-235b-a22b-instruct-2507",
        api_key_env="NEVER_READ_OFFLINE",
        transport="openai_chat_completions",
        supports_strict_json_schema=False,
        enable_thinking=False,
    )


def _binding():
    params = CallParameters(
        max_tokens=1024,
        maximum_prompt_tokens=8192,
        prompt_token_safety_margin=256,
    )
    return RuntimeBinding(
        endpoint=_endpoint(),
        extractor=params,
        verifier=params,
        tokenizer_identity="offline-four-char-estimator",
    )


def _price():
    return PriceSnapshot(
        snapshot_id="official-test-price",
        provider="Alibaba Cloud Model Studio",
        region="Singapore (International)",
        input_usd_per_million_tokens=Decimal("0.23"),
        output_usd_per_million_tokens=Decimal("0.92"),
    )


def _source():
    text = "I moved to Tokyo last month, and walking there has helped me feel calmer."
    return MultiViewSessionInput(
        owner_id="u1",
        session_id="session-1",
        timestamp="2025-02-01",
        chronological_rank=1,
        turns=(
            SourceTurn(
                turn_id="session-1:0",
                turn_index=0,
                role="seeker",
                content=text,
            ),
        ),
    )


class FakeClient:
    def __init__(self, endpoint, outputs):
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
                usage={"prompt_tokens": 300, "completion_tokens": 100, "total_tokens": 400},
                latency_ms=1.0,
                request_hash=sha256_text(canonical_json(payload)),
                provider_finish_reason="stop",
                normalized_finish_reason="complete",
            ),
            parsed,
        )


def _compiler(tmp_path, client):
    return MultiViewMemoryCompiler(
        binding=_binding(),
        price=_price(),
        client=client,
        prompt_token_counter=lambda messages: max(1, len(canonical_json(messages)) // 4),
        cache_root=tmp_path / "cache",
        attempt_ledger_root=tmp_path / "attempts",
        cumulative_budget=CumulativePaper1ApiBudgetLedger(tmp_path / "api-budget.jsonl"),
    )


def _outputs():
    text = _source().turns[0].content
    profile = ProposedProfileViewUnit(
        proposal_id="mp1",
        profile_field_type=ProfileFieldType.LOCATION,
        profile_slot_key="residence.current_city",
        normalized_value="Tokyo",
        supporting_spans=(
            ProposedSourceSpan(span_id="s1", turn_id="session-1:0", exact_text=text),
        ),
    )
    event = ProposedEventExperienceUnit(
        proposal_id="me1",
        event_experience_type=EventExperienceType.LIFE_EVENT,
        temporal_status=EventTemporalStatus.OCCURRED,
        normalized_event="Moved to Tokyo last month",
        supporting_spans=(
            ProposedSourceSpan(span_id="s2", turn_id="session-1:0", exact_text=text),
        ),
    )
    extractor = ExtractorSessionOutput(
        owner_id="u1",
        session_id="session-1",
        mp_facts=(profile,),
        me_events=(event,),
    )
    verifier = VerifierSessionOutput(
        owner_id="u1",
        session_id="session-1",
        decisions=tuple(
            VerificationDecision(
                proposal_id=proposal_id,
                accepted=True,
                reason=VerificationReason.ACCEPTED,
                factual_rationale="Directly supported by seeker text.",
            )
            for proposal_id in ("mp1", "me1")
        ),
    )
    return extractor, verifier


def test_active_runtime_accepts_grounded_verified_mp_and_broad_me_and_caches(tmp_path):
    extractor, verifier = _outputs()
    client = FakeClient(_endpoint(), [extractor, verifier])
    first = _compiler(tmp_path, client).compile_session(_source())
    assert len(first.accepted_units) == 2
    assert {unit.head.value for unit in first.accepted_units} == {"MP", "ME"}
    assert first.accepted_units[0].supporting_spans[0].exact_text_sha256
    assert client.calls == 2

    cached_client = FakeClient(_endpoint(), [])
    second = _compiler(tmp_path, cached_client).compile_session(_source())
    assert second.accepted_units == first.accepted_units
    assert second.extractor_cache_hit and second.verifier_cache_hit
    assert cached_client.calls == 0


def test_grounding_failure_cannot_be_overridden_by_verifier(tmp_path):
    extractor, _ = _outputs()
    bad = extractor.mp_facts[0].model_copy(
        update={
            "supporting_spans": (
                ProposedSourceSpan(
                    span_id="s1",
                    turn_id="session-1:0",
                    exact_text="I live in Kyoto",
                ),
            )
        }
    )
    bad_extractor = extractor.model_copy(update={"mp_facts": (bad,), "me_events": ()})
    client = FakeClient(_endpoint(), [bad_extractor])
    result = _compiler(tmp_path, client).compile_session(_source())
    assert result.accepted_units == ()
    assert result.grounding[0]["valid"] is False
    assert client.calls == 1


def test_empty_extraction_skips_paid_verifier_call(tmp_path):
    empty = ExtractorSessionOutput(owner_id="u1", session_id="session-1")
    client = FakeClient(_endpoint(), [empty])
    result = _compiler(tmp_path, client).compile_session(_source())
    assert result.verifier.decisions == ()
    assert result.verifier_cache_hit is True
    assert client.calls == 1


def test_schema_invalid_item_is_rejected_without_losing_valid_item(tmp_path):
    extractor, verifier = _outputs()
    valid = extractor.mp_facts[0].model_dump(mode="json")
    invalid = {**valid, "proposal_id": "bad", "profile_field_type": "invented"}
    from metacom_pm.paper1.multi_view_memory.contracts import ExtractorWireSessionOutput

    wire = ExtractorWireSessionOutput(
        owner_id="u1",
        session_id="session-1",
        mp_facts=(valid, invalid),
    )
    one_verdict = verifier.model_copy(update={"decisions": (verifier.decisions[0],)})
    result = _compiler(tmp_path, FakeClient(_endpoint(), [wire, one_verdict])).compile_session(
        _source()
    )
    assert len(result.accepted_units) == 1
    assert len(result.schema_rejections) == 1
    assert result.schema_rejections[0].proposal_id == "bad"
