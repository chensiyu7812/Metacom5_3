"""Offline-first active MP/ME compiler with mechanical MS kept separate."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Protocol, Type

from pydantic import BaseModel, Field, ValidationError

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.attempt_ledger import PersistentAttemptLedger
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.contracts import StrictContract

from .cache import CallIdentity, SuccessCache
from .contracts import (
    AcceptedAtomicMemoryUnit,
    AcceptedEventExperienceUnit,
    AcceptedProfileViewUnit,
    ExtractorSessionOutput,
    ExtractorWireSessionOutput,
    MultiViewSessionInput,
    ProposedEventExperienceUnit,
    ProposedProfileViewUnit,
    SchemaRejectedItem,
    VerificationDecision,
    VerifierSessionOutput,
    VerifierWireSessionOutput,
)
from .grounding import (
    MULTI_VIEW_GROUNDING_VERSION,
    prior_profile_sha256,
    source_sha256,
    validate_output_binding,
    validate_proposal_grounding,
)
from .input_projection import assert_input_firewall
from .prompts import (
    MULTI_VIEW_EXTRACTOR_PROMPT_SHA256,
    MULTI_VIEW_VERIFIER_PROMPT_SHA256,
    extractor_messages,
    verifier_messages,
)
from .renderer import (
    MULTI_VIEW_RENDERER_SHA256,
    MULTI_VIEW_RENDERER_VERSION,
    render_atom,
)


MULTI_VIEW_COMPILER_VERSION = "paper1-qwen-multi-view-memory-compiler-v1"
FROZEN_MULTI_VIEW_MODEL = "qwen3-235b-a22b-instruct-2507"
MULTI_VIEW_COMPILER_STAGE = "multi_view_401_compilation_and_validation"
MULTI_VIEW_COMPILER_STAGE_CAP_USD = Decimal("1.50")


class CompilerClient(Protocol):
    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float,
        max_tokens: int,
        seed: int | None,
        response_schema: Type[BaseModel] | None,
        retries: int,
    ) -> tuple[CallResult, BaseModel | None]: ...


class CallParameters(StrictContract):
    temperature: float = 0.0
    max_tokens: int = Field(gt=0)
    maximum_prompt_tokens: int = Field(gt=0)
    prompt_token_safety_margin: int = Field(ge=0)
    seed: int | None = 0


class PriceSnapshot(StrictContract):
    snapshot_id: str = Field(min_length=1)
    provider: str = Field(min_length=1)
    region: str = Field(min_length=1)
    currency: str = "USD"
    input_usd_per_million_tokens: Decimal
    output_usd_per_million_tokens: Decimal

    def cost(self, *, prompt_tokens: int, completion_tokens: int) -> Decimal:
        if prompt_tokens < 0 or completion_tokens < 0:
            raise ValueError("token counts cannot be negative")
        million = Decimal(1_000_000)
        return (
            Decimal(prompt_tokens) * self.input_usd_per_million_tokens
            + Decimal(completion_tokens) * self.output_usd_per_million_tokens
        ) / million

    @property
    def identity_sha256(self) -> str:
        return sha256_text(canonical_json(self.model_dump(mode="json")))


class RuntimeBinding(StrictContract):
    provider: str = "Alibaba Cloud Model Studio"
    region: str = "Singapore (International)"
    endpoint: Endpoint
    extractor: CallParameters
    verifier: CallParameters
    tokenizer_identity: str = Field(min_length=1)
    prior_profile_allowance_tokens: int = Field(default=1024, ge=0)
    compiler_version: str = MULTI_VIEW_COMPILER_VERSION

    @property
    def checked_endpoint(self) -> Endpoint:
        if self.provider != "Alibaba Cloud Model Studio":
            raise ValueError("active Multi-View compiler provider is frozen to Alibaba")
        if self.endpoint.model != FROZEN_MULTI_VIEW_MODEL:
            raise ValueError("active Multi-View compiler model mismatch")
        if self.endpoint.transport != "openai_chat_completions":
            raise ValueError("active Multi-View compiler requires OpenAI-compatible chat")
        if self.endpoint.supports_strict_json_schema:
            raise ValueError("active Qwen route uses JSON-object plus local strict validation")
        if self.endpoint.enable_thinking is not False:
            raise ValueError("active Multi-View compiler must disable thinking")
        return self.endpoint


class SessionCompilationResult(StrictContract):
    compiler_version: str
    grounding_version: str
    owner_id: str
    session_id: str
    source_sha256: str
    prior_profile_sha256: str
    extractor: ExtractorSessionOutput
    verifier: VerifierSessionOutput
    schema_rejections: tuple[SchemaRejectedItem, ...] = ()
    grounding: tuple[dict[str, Any], ...]
    accepted_units: tuple[AcceptedAtomicMemoryUnit, ...]
    rejected_decisions: tuple[VerificationDecision, ...]
    extractor_cache_hit: bool
    verifier_cache_hit: bool


@dataclass(frozen=True)
class _CallArtifact:
    parsed: BaseModel
    identity: CallIdentity
    response_sha256: str
    cache_hit: bool


def _schema_sha256(*models: Type[BaseModel]) -> str:
    return sha256_text(
        canonical_json({model.__name__: model.model_json_schema() for model in models})
    )


EXTRACTOR_SCHEMA_SHA256 = _schema_sha256(
    ExtractorWireSessionOutput,
    ExtractorSessionOutput,
    ProposedProfileViewUnit,
    ProposedEventExperienceUnit,
)
VERIFIER_SCHEMA_SHA256 = _schema_sha256(
    VerifierWireSessionOutput,
    VerifierSessionOutput,
    VerificationDecision,
)


def compiler_identity_sha256(binding: RuntimeBinding, price: PriceSnapshot) -> str:
    return sha256_text(
        canonical_json(
            {
                "binding": binding.model_dump(mode="json"),
                "price_sha256": price.identity_sha256,
                "grounding": MULTI_VIEW_GROUNDING_VERSION,
                "renderer": MULTI_VIEW_RENDERER_VERSION,
                "renderer_sha256": MULTI_VIEW_RENDERER_SHA256,
                "extractor_prompt_sha256": MULTI_VIEW_EXTRACTOR_PROMPT_SHA256,
                "verifier_prompt_sha256": MULTI_VIEW_VERIFIER_PROMPT_SHA256,
                "extractor_schema_sha256": EXTRACTOR_SCHEMA_SHA256,
                "verifier_schema_sha256": VERIFIER_SCHEMA_SHA256,
            }
        )
    )


def _violations(exc: ValidationError) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                f"{'.'.join(str(part) for part in error['loc'])}:{error['type']}"
                for error in exc.errors()
            }
        )
    )


def _raw_id(raw: dict[str, Any]) -> str | None:
    value = raw.get("proposal_id")
    return value if isinstance(value, str) and value else None


def _rejection(phase: str, index: int, raw: dict[str, Any], errors: tuple[str, ...]):
    return SchemaRejectedItem(
        phase=phase,
        item_index=index,
        proposal_id=_raw_id(raw),
        violations=errors,
        raw_item_sha256=sha256_text(canonical_json(raw)),
    )


def strict_extractor(
    wire: ExtractorWireSessionOutput,
) -> tuple[ExtractorSessionOutput, tuple[SchemaRejectedItem, ...]]:
    raw_rows = [*wire.mp_facts, *wire.me_events]
    duplicate_ids = {
        key for key, count in Counter(_raw_id(row) for row in raw_rows).items()
        if key is not None and count > 1
    }
    mp: list[ProposedProfileViewUnit] = []
    me: list[ProposedEventExperienceUnit] = []
    rejected: list[SchemaRejectedItem] = []
    index = 0
    for rows, model, destination in (
        (wire.mp_facts, ProposedProfileViewUnit, mp),
        (wire.me_events, ProposedEventExperienceUnit, me),
    ):
        for raw in rows:
            if _raw_id(raw) in duplicate_ids:
                rejected.append(_rejection("extractor", index, raw, ("proposal_id:duplicate",)))
            else:
                try:
                    destination.append(model.model_validate(raw))
                except ValidationError as exc:
                    rejected.append(_rejection("extractor", index, raw, _violations(exc)))
            index += 1
    return (
        ExtractorSessionOutput(
            owner_id=wire.owner_id,
            session_id=wire.session_id,
            mp_facts=tuple(mp),
            me_events=tuple(me),
        ),
        tuple(rejected),
    )


def strict_verifier(
    wire: VerifierWireSessionOutput,
    *,
    expected_ids: set[str],
) -> tuple[VerifierSessionOutput, tuple[SchemaRejectedItem, ...]]:
    duplicate_ids = {
        key for key, count in Counter(_raw_id(row) for row in wire.decisions).items()
        if key is not None and count > 1
    }
    decisions: list[VerificationDecision] = []
    rejected: list[SchemaRejectedItem] = []
    covered: set[str] = set()
    for index, raw in enumerate(wire.decisions):
        proposal_id = _raw_id(raw)
        if proposal_id is not None:
            covered.add(proposal_id)
        if proposal_id in duplicate_ids:
            rejected.append(_rejection("verifier", index, raw, ("proposal_id:duplicate",)))
            continue
        try:
            decision = VerificationDecision.model_validate(raw)
        except ValidationError as exc:
            rejected.append(_rejection("verifier", index, raw, _violations(exc)))
            continue
        if decision.proposal_id not in expected_ids:
            rejected.append(_rejection("verifier", index, raw, ("proposal_id:unknown",)))
            continue
        decisions.append(decision)
    for offset, proposal_id in enumerate(sorted(expected_ids - covered)):
        raw = {"proposal_id": proposal_id, "missing": True}
        rejected.append(
            _rejection("verifier", len(wire.decisions) + offset, raw, ("proposal_id:missing",))
        )
    return (
        VerifierSessionOutput(
            owner_id=wire.owner_id,
            session_id=wire.session_id,
            decisions=tuple(decisions),
        ),
        tuple(rejected),
    )


class MultiViewMemoryCompiler:
    def __init__(
        self,
        *,
        binding: RuntimeBinding,
        price: PriceSnapshot,
        client: CompilerClient,
        prompt_token_counter: Callable[[list[dict[str, str]]], int],
        cache_root: str | Path,
        attempt_ledger_root: str | Path,
        cumulative_budget: CumulativePaper1ApiBudgetLedger,
    ) -> None:
        self.binding = binding
        self.endpoint = binding.checked_endpoint
        if price.provider != binding.provider or price.region != binding.region:
            raise ValueError("price provider/region must match active runtime")
        if price.currency != "USD":
            raise ValueError("active compiler pricing must use USD")
        self.price = price
        self.client = client
        self.prompt_token_counter = prompt_token_counter
        self.cache = SuccessCache(cache_root)
        self.attempt_ledger_root = Path(attempt_ledger_root)
        self.cumulative_budget = cumulative_budget

    @property
    def compiler_identity_sha256(self) -> str:
        return compiler_identity_sha256(self.binding, self.price)

    def _call(
        self,
        *,
        phase: str,
        source: MultiViewSessionInput,
        messages: list[dict[str, str]],
        profile_free_messages: list[dict[str, str]],
        response_schema: Type[BaseModel],
        parameters: CallParameters,
        prompt_sha256: str,
        schema_sha256: str,
    ) -> _CallArtifact:
        assert_input_firewall(source.model_dump(mode="json"))
        estimated_prompt_tokens = int(self.prompt_token_counter(messages))
        profile_free_prompt_tokens = int(self.prompt_token_counter(profile_free_messages))
        profile_context_tokens = max(0, estimated_prompt_tokens - profile_free_prompt_tokens)
        if profile_context_tokens > self.binding.prior_profile_allowance_tokens:
            raise RuntimeError("prior current-profile context exceeds frozen token allowance")
        reserved_prompt_tokens = estimated_prompt_tokens + parameters.prompt_token_safety_margin
        if reserved_prompt_tokens > parameters.maximum_prompt_tokens:
            raise RuntimeError("local prompt estimate plus safety margin exceeds frozen bound")
        payload = chat_request_payload(
            self.endpoint,
            messages,
            temperature=parameters.temperature,
            max_tokens=parameters.max_tokens,
            seed=parameters.seed,
            response_schema=response_schema,
        )
        payload_sha = sha256_text(canonical_json(payload))
        identity = CallIdentity(
            phase=phase,
            compiler_version=self.binding.compiler_version,
            provider=self.binding.provider,
            region=self.binding.region,
            base_url=self.endpoint.base_url,
            model=self.endpoint.model,
            request_parameters={
                **parameters.model_dump(mode="json"),
                "estimated_prompt_tokens": estimated_prompt_tokens,
                "reserved_prompt_tokens": reserved_prompt_tokens,
                "tokenizer_identity": self.binding.tokenizer_identity,
                "profile_context_tokens": profile_context_tokens,
            },
            prompt_sha256=prompt_sha256,
            schema_sha256=schema_sha256,
            source_sha256=source_sha256(source),
            prior_profile_sha256=prior_profile_sha256(source),
            request_payload_sha256=payload_sha,
        )
        cached = self.cache.load(identity)
        if cached is not None:
            return _CallArtifact(
                parsed=response_schema.model_validate(cached["parsed"]),
                identity=identity,
                response_sha256=str(cached["response_sha256"]),
                cache_hit=True,
            )

        call_key = identity.cache_key
        attempts = PersistentAttemptLedger(
            self.attempt_ledger_root / phase / f"{call_key}.jsonl",
            stage=f"paper1_multi_view_{phase}",
            expected_calls={call_key: 1},
            maximum_total_attempts=1,
        )
        if attempts.started_attempts:
            raise RuntimeError("unfinished paid attempt requires manual reconciliation")
        maximum_cost = self.price.cost(
            prompt_tokens=reserved_prompt_tokens,
            completion_tokens=parameters.max_tokens,
        )
        reservation = self.cumulative_budget.reserve(
            reservation_id=call_key,
            logical_call_id=call_key,
            call_hash=call_key,
            stage=MULTI_VIEW_COMPILER_STAGE,
            provider=self.binding.provider,
            model=self.endpoint.model,
            maximum_cost_usd=maximum_cost,
            call_class="PRIMARY",
            stage_hard_cap_usd=MULTI_VIEW_COMPILER_STAGE_CAP_USD,
        )
        attempt = attempts.reserve(
            call_key,
            record_ids={"owner_id": source.owner_id, "session_id": source.session_id},
            prompt_sha256=prompt_sha256,
        )
        result: CallResult | None = None
        settled = False
        try:
            result, parsed = self.client.chat(
                messages,
                temperature=parameters.temperature,
                max_tokens=parameters.max_tokens,
                seed=parameters.seed,
                response_schema=response_schema,
                retries=1,
            )
            if parsed is None:
                raise RuntimeError("active compiler returned no parsed object")
            parsed = response_schema.model_validate(parsed)
            if result.request_hash != payload_sha:
                raise RuntimeError("client request hash differs from frozen payload")
            if result.normalized_finish_reason != "complete":
                raise RuntimeError("active compiler response did not finish completely")
            usage = result.usage
            prompt_tokens = int(usage.get("prompt_tokens") or 0)
            completion_tokens = int(usage.get("completion_tokens") or 0)
            if prompt_tokens <= 0 or prompt_tokens > reserved_prompt_tokens:
                raise RuntimeError("provider prompt usage exceeds pre-call reservation")
            if completion_tokens < 0 or completion_tokens > parameters.max_tokens:
                raise RuntimeError("provider completion usage exceeds pre-call reservation")
            actual_cost = self.price.cost(
                prompt_tokens=prompt_tokens,
                completion_tokens=completion_tokens,
            )
            response_sha = sha256_text(canonical_json(result.raw_response))
            self.cache.store_success(
                identity,
                {
                    "parsed": parsed.model_dump(mode="json"),
                    "response_sha256": response_sha,
                    "usage": usage,
                    "latency_ms": result.latency_ms,
                    "provider_finish_reason": result.provider_finish_reason,
                },
            )
            self.cumulative_budget.settle(
                reservation,
                actual_cost_usd=actual_cost,
                outcome="SUCCEEDED",
            )
            settled = True
            attempts.finish(
                attempt,
                succeeded=True,
                request_hash=result.request_hash,
                usage=usage,
                error=None,
                result={"response_sha256": response_sha},
                metadata={"cost_usd": str(actual_cost), "phase": phase},
            )
            return _CallArtifact(parsed, identity, response_sha, False)
        except Exception as exc:
            if not settled:
                self.cumulative_budget.settle(
                    reservation,
                    actual_cost_usd=None,
                    outcome="UNKNOWN",
                )
            if attempts.terminal_event(call_key, attempt.attempt_index) is None:
                attempts.finish(
                    attempt,
                    succeeded=False,
                    request_hash=getattr(result, "request_hash", payload_sha),
                    usage=getattr(result, "usage", None),
                    error=f"{type(exc).__name__}: {exc}",
                    result=None,
                    metadata={"phase": phase},
                )
            raise

    def compile_session(self, source: MultiViewSessionInput) -> SessionCompilationResult:
        source_json = canonical_json(source.model_dump(mode="json"))
        profile_free_source = source.model_copy(update={"prior_current_profile": ()})
        profile_free_source_json = canonical_json(profile_free_source.model_dump(mode="json"))
        extractor_message_rows = extractor_messages(
            source_json,
            canonical_json(ExtractorSessionOutput.model_json_schema()),
        )
        extractor_call = self._call(
            phase="extractor",
            source=source,
            messages=extractor_message_rows,
            profile_free_messages=extractor_messages(
                profile_free_source_json,
                canonical_json(ExtractorSessionOutput.model_json_schema()),
            ),
            response_schema=ExtractorWireSessionOutput,
            parameters=self.binding.extractor,
            prompt_sha256=MULTI_VIEW_EXTRACTOR_PROMPT_SHA256,
            schema_sha256=EXTRACTOR_SCHEMA_SHA256,
        )
        extractor_wire = ExtractorWireSessionOutput.model_validate(extractor_call.parsed)
        if extractor_wire.owner_id != source.owner_id or extractor_wire.session_id != source.session_id:
            raise ValueError("extractor wire owner/session mismatch")
        extractor, extractor_rejections = strict_extractor(extractor_wire)
        validate_output_binding(source, extractor)
        grounding = tuple(
            validate_proposal_grounding(source, proposal) for proposal in extractor.proposals
        )
        grounded_by_id = {row.proposal_id: row for row in grounding}
        grounded = ExtractorSessionOutput(
            owner_id=source.owner_id,
            session_id=source.session_id,
            mp_facts=tuple(
                row for row in extractor.mp_facts if grounded_by_id[row.proposal_id].valid
            ),
            me_events=tuple(
                row for row in extractor.me_events if grounded_by_id[row.proposal_id].valid
            ),
        )
        if grounded.proposals:
            grounded_json = canonical_json(grounded.model_dump(mode="json"))
            verifier_call = self._call(
                phase="verifier",
                source=source,
                messages=verifier_messages(
                    source_json,
                    grounded_json,
                    canonical_json(VerifierSessionOutput.model_json_schema()),
                ),
                profile_free_messages=verifier_messages(
                    profile_free_source_json,
                    grounded_json,
                    canonical_json(VerifierSessionOutput.model_json_schema()),
                ),
                response_schema=VerifierWireSessionOutput,
                parameters=self.binding.verifier,
                prompt_sha256=MULTI_VIEW_VERIFIER_PROMPT_SHA256,
                schema_sha256=VERIFIER_SCHEMA_SHA256,
            )
            verifier_wire = VerifierWireSessionOutput.model_validate(verifier_call.parsed)
            if verifier_wire.owner_id != source.owner_id or verifier_wire.session_id != source.session_id:
                raise ValueError("verifier wire owner/session mismatch")
            verifier, verifier_rejections = strict_verifier(
                verifier_wire,
                expected_ids={row.proposal_id for row in grounded.proposals},
            )
            verifier_cache_hit = verifier_call.cache_hit
            verifier_response_sha = verifier_call.response_sha256
        else:
            verifier = VerifierSessionOutput(
                owner_id=source.owner_id,
                session_id=source.session_id,
                decisions=(),
            )
            verifier_rejections = ()
            verifier_cache_hit = True
            verifier_response_sha = sha256_text(canonical_json(verifier.model_dump(mode="json")))

        decisions = {row.proposal_id: row for row in verifier.decisions}
        accepted: list[AcceptedAtomicMemoryUnit] = []
        for proposal in grounded.proposals:
            decision = decisions.get(proposal.proposal_id)
            if decision is None or not decision.accepted:
                continue
            spans = grounded_by_id[proposal.proposal_id].grounded_spans
            rendered = render_atom(proposal, timestamp=source.timestamp)
            memory_id = "mvu_" + sha256_text(
                canonical_json(
                    {
                        "source": source_sha256(source),
                        "proposal": proposal.model_dump(mode="json"),
                        "compiler": self.compiler_identity_sha256,
                    }
                )
            )[:24]
            common = {
                "memory_id": memory_id,
                "owner_id": source.owner_id,
                "source_session_id": source.session_id,
                "source_session_rank": source.chronological_rank,
                "timestamp": source.timestamp,
                "rendered_candidate_content": rendered,
                "supporting_spans": spans,
                "compiler_identity_sha256": self.compiler_identity_sha256,
            }
            if isinstance(proposal, ProposedProfileViewUnit):
                accepted.append(
                    AcceptedProfileViewUnit(
                        profile_field_type=proposal.profile_field_type,
                        profile_slot_key=proposal.profile_slot_key,
                        normalized_value=proposal.normalized_value,
                        **common,
                    )
                )
            else:
                accepted.append(
                    AcceptedEventExperienceUnit(
                        event_experience_type=proposal.event_experience_type,
                        temporal_status=proposal.temporal_status,
                        normalized_event=proposal.normalized_event,
                        action_text=proposal.action_text,
                        observed_outcome_text=proposal.observed_outcome_text,
                        **common,
                    )
                )
        return SessionCompilationResult(
            compiler_version=self.binding.compiler_version,
            grounding_version=MULTI_VIEW_GROUNDING_VERSION,
            owner_id=source.owner_id,
            session_id=source.session_id,
            source_sha256=source_sha256(source),
            prior_profile_sha256=prior_profile_sha256(source),
            extractor=extractor,
            verifier=verifier,
            schema_rejections=(*extractor_rejections, *verifier_rejections),
            grounding=tuple(
                {
                    "proposal_id": row.proposal_id,
                    "valid": row.valid,
                    "violations": row.violations,
                    "grounded_spans": tuple(
                        span.model_dump(mode="json") for span in row.grounded_spans
                    ),
                }
                for row in grounding
            ),
            accepted_units=tuple(accepted),
            rejected_decisions=tuple(row for row in verifier.decisions if not row.accepted),
            extractor_cache_hit=extractor_call.cache_hit,
            verifier_cache_hit=verifier_cache_hit,
        )


__all__ = [
    "CallParameters",
    "EXTRACTOR_SCHEMA_SHA256",
    "FROZEN_MULTI_VIEW_MODEL",
    "MULTI_VIEW_COMPILER_STAGE",
    "MULTI_VIEW_COMPILER_STAGE_CAP_USD",
    "MULTI_VIEW_COMPILER_VERSION",
    "MultiViewMemoryCompiler",
    "PriceSnapshot",
    "RuntimeBinding",
    "SessionCompilationResult",
    "VERIFIER_SCHEMA_SHA256",
    "compiler_identity_sha256",
    "strict_extractor",
    "strict_verifier",
]
