from decimal import Decimal

import pytest
from pydantic import ValidationError

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.multi_view_memory.contracts import (
    CompactExtractorWireSessionOutput,
    CompactVerifierWireSessionOutput,
    EventExperienceType,
    EventTemporalStatus,
    ExtractorSessionOutput,
    MultiViewSessionInput,
    PriorCurrentProfileSlot,
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
from metacom_pm.paper1.multi_view_memory.prompts import extractor_messages, verifier_messages
from metacom_pm.paper1.multi_view_memory.input_projection import prompt_source_projection


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
        if isinstance(supplied, Exception):
            raise supplied
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
    extractor = CompactExtractorWireSessionOutput(
        o="u1",
        s="session-1",
        p=(
            {
                "i": profile.proposal_id,
                "t": profile.profile_field_type.value,
                "k": profile.profile_slot_key,
                "v": profile.normalized_value,
                "s": ({"i": "session-1:0"},),
            },
        ),
        e=(
            {
                "i": event.proposal_id,
                "t": event.event_experience_type.value,
                "z": event.temporal_status.value,
                "n": event.normalized_event,
                "s": ({"i": "session-1:0"},),
                "a": None,
                "o": None,
            },
        ),
    )
    verifier = CompactVerifierWireSessionOutput(
        o="u1",
        s="session-1",
        d=tuple({"i": proposal_id, "r": "accepted"} for proposal_id in ("mp1", "me1")),
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


def test_unknown_turn_reference_is_rejected_before_verifier(tmp_path):
    extractor, _ = _outputs()
    bad = {**extractor.p[0], "s": ({"i": "unknown-turn"},)}
    bad_extractor = extractor.model_copy(update={"p": (bad,), "e": ()})
    client = FakeClient(_endpoint(), [bad_extractor])
    result = _compiler(tmp_path, client).compile_session(_source())
    assert result.accepted_units == ()
    assert len(result.schema_rejections) == 1
    assert "supporting_spans.0.exact_text:string_type" in result.schema_rejections[
        0
    ].violations
    assert client.calls == 1


def test_empty_extraction_skips_paid_verifier_call(tmp_path):
    empty = CompactExtractorWireSessionOutput(o="u1", s="session-1")
    client = FakeClient(_endpoint(), [empty])
    result = _compiler(tmp_path, client).compile_session(_source())
    assert result.verifier.decisions == ()
    assert result.verifier_cache_hit is True
    assert client.calls == 1


def test_schema_invalid_item_is_rejected_without_losing_valid_item(tmp_path):
    extractor, verifier = _outputs()
    valid = extractor.p[0]
    invalid = {**valid, "i": "bad", "t": "invented"}
    wire = CompactExtractorWireSessionOutput(
        o="u1",
        s="session-1",
        p=(valid, invalid),
    )
    one_verdict = verifier.model_copy(update={"d": (verifier.d[0],)})
    result = _compiler(tmp_path, FakeClient(_endpoint(), [wire, one_verdict])).compile_session(
        _source()
    )
    assert len(result.accepted_units) == 1
    assert len(result.schema_rejections) == 1
    assert result.schema_rejections[0].proposal_id == "bad"


def test_compact_transport_accepts_provider_uppercase_keys_without_changing_values():
    wire = CompactExtractorWireSessionOutput.model_validate(
        {
            "V": "paper1-multi-view-memory-schema-v1",
            "O": "u1",
            "S": "session-1",
            "P": [
                {
                    "I": "mp1",
                    "T": "location",
                    "K": "residence.current_city",
                    "V": "Tokyo",
                    "S": [{"I": "session-1:0"}],
                }
            ],
            "E": [],
        }
    )
    expanded = wire.expand(_source())
    assert expanded.owner_id == "u1"
    assert expanded.mp_facts[0]["normalized_value"] == "Tokyo"
    assert expanded.mp_facts[0]["supporting_spans"][0]["exact_text"] == _source().turns[0].content


def test_compact_transport_rejects_case_collisions():
    with pytest.raises(ValidationError, match="conflicting compact transport key"):
        CompactExtractorWireSessionOutput.model_validate(
            {"o": "u1", "O": "other", "s": "session-1"}
        )


def test_json_object_provider_prompts_explicitly_name_json():
    assert "json" in canonical_json(extractor_messages("{}", "{}")).casefold()
    assert "json" in canonical_json(verifier_messages("{}", "{}", "{}")).casefold()


def test_prompt_source_projection_keeps_current_value_but_removes_audit_lineage():
    source = _source().model_copy(
        update={
            "chronological_rank": 2,
            "prior_current_profile": (
                PriorCurrentProfileSlot(
                    memory_id="audit-only-memory-id",
                    profile_field_type=ProfileFieldType.LOCATION,
                    profile_slot_key="residence.current_city",
                    normalized_value="Tokyo",
                    source_session_rank=1,
                ),
            ),
        }
    )
    projected = prompt_source_projection(source)
    assert projected["prior_current_profile"] == [
        {"t": "location", "k": "residence.current_city", "v": "Tokyo"}
    ]
    assert "audit-only-memory-id" not in canonical_json(projected)


def test_failed_physical_attempt_can_resume_once_with_separate_budget_reservation(tmp_path):
    extractor, verifier = _outputs()
    with pytest.raises(TimeoutError):
        _compiler(tmp_path, FakeClient(_endpoint(), [TimeoutError("network timeout")])).compile_session(
            _source()
        )

    resumed = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier])).compile_session(
        _source()
    )
    assert len(resumed.accepted_units) == 2
    budget_rows = [
        __import__("json").loads(line)
        for line in (tmp_path / "api-budget.jsonl").read_text(encoding="utf-8").splitlines()
    ]
    reservations = [row for row in budget_rows if row["event"] == "RESERVED"]
    assert [row["call_class"] for row in reservations[:2]] == [
        "PRIMARY",
        "PRIMARY_RETRY",
    ]
    assert reservations[0]["reservation_id"] != reservations[1]["reservation_id"]
