"""Offline-first Qwen semantic-memory compiler orchestration.

The runtime accepts an injected client for offline tests. Constructing a real
client or loading a secret is intentionally outside this module; callers must
pass an already configured client after an explicit live-run authorization.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, Type

from pydantic import BaseModel, Field, ValidationError

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.attempt_ledger import PersistentAttemptLedger
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import StrictContract

from .budget import PriceSnapshot, SemanticCompilerBudgetLedger
from .cache import CompilerCallIdentity, SuccessCache
from .contracts import (
    AcceptedSemanticMemoryUnit,
    CandidateSourceUse,
    ExtractorWireSessionOutput,
    ExtractorSessionOutput,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    SchemaRejectedItem,
    SessionCompileInput,
    VerifierDecision,
    VerifierWireSessionOutput,
    VerifierSessionOutput,
)
from .grounding import (
    GROUNDING_VERSION,
    prior_memory_table_sha256,
    source_sha256,
    validate_output_binding,
    validate_proposal_grounding,
)
from .input_projection import assert_compiler_input_firewall
from .prompts import (
    EXTRACTOR_PROMPT_SHA256,
    VERIFIER_PROMPT_SHA256,
    extractor_messages,
    verifier_messages,
)
from .renderer import (
    RENDERER_CODE_SHA256,
    RENDERER_SHA256,
    RENDERER_VERSION,
    render_semantic_memory,
)

COMPILER_VERSION = "paper1-qwen-semantic-memory-compiler-v6"
FROZEN_QWEN_MODEL = "qwen3-235b-a22b-instruct-2507"
VERIFIER_METHOD = "same_qwen_model_semantic_factual_verifier_not_independent"


class SemanticCompilerClient(Protocol):
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
    seed: int | None = None


class RuntimeBinding(StrictContract):
    provider: str = "Alibaba Cloud Model Studio"
    region: str = Field(min_length=1)
    endpoint: Endpoint
    extractor: CallParameters
    verifier: CallParameters
    compiler_version: str = COMPILER_VERSION

    @property
    def checked_endpoint(self) -> Endpoint:
        endpoint = self.endpoint
        if self.provider != "Alibaba Cloud Model Studio":
            raise ValueError("semantic compiler provider must remain Alibaba Cloud Model Studio")
        if self.compiler_version != COMPILER_VERSION:
            raise ValueError(f"semantic compiler version must be {COMPILER_VERSION}")
        if endpoint.model != FROZEN_QWEN_MODEL:
            raise ValueError(f"semantic compiler model must be {FROZEN_QWEN_MODEL}")
        if endpoint.transport != "openai_chat_completions":
            raise ValueError("semantic compiler requires frozen OpenAI-compatible transport")
        if endpoint.supports_strict_json_schema:
            raise ValueError("Qwen endpoint must use JSON-object mode plus local strict validation")
        if endpoint.enable_thinking is not False:
            raise ValueError("Qwen semantic compiler must explicitly disable thinking")
        return endpoint

    @property
    def identity_sha256(self) -> str:
        endpoint = self.checked_endpoint
        return sha256_text(
            canonical_json(
                {
                    "provider": self.provider,
                    "region": self.region,
                    "base_url": endpoint.base_url,
                    "model": endpoint.model,
                    "transport": endpoint.transport,
                    "supports_strict_json_schema": endpoint.supports_strict_json_schema,
                    "enable_thinking": endpoint.enable_thinking,
                    "extractor": self.extractor.model_dump(mode="json"),
                    "verifier": self.verifier.model_dump(mode="json"),
                    "compiler_version": self.compiler_version,
                    "grounding_version": GROUNDING_VERSION,
                    "extractor_prompt_sha256": EXTRACTOR_PROMPT_SHA256,
                    "verifier_prompt_sha256": VERIFIER_PROMPT_SHA256,
                    "extractor_schema_sha256": EXTRACTOR_SCHEMA_SHA256,
                    "verifier_schema_sha256": VERIFIER_SCHEMA_SHA256,
                    "renderer_version": RENDERER_VERSION,
                    "renderer_sha256": RENDERER_SHA256,
                    "renderer_code_sha256": RENDERER_CODE_SHA256,
                }
            )
        )


class SessionCompilationResult(StrictContract):
    compiler_version: str
    grounding_version: str
    owner_id: str
    session_id: str
    source_sha256: str
    prior_memory_table_sha256: str
    extractor: ExtractorSessionOutput
    verifier: VerifierSessionOutput
    schema_rejections: tuple[SchemaRejectedItem, ...] = ()
    grounding: tuple[dict[str, Any], ...]
    accepted_units: tuple[AcceptedSemanticMemoryUnit, ...]
    rejected_decisions: tuple[VerifierDecision, ...]
    extractor_cache_hit: bool
    verifier_cache_hit: bool


@dataclass(frozen=True)
class _CallArtifact:
    parsed: BaseModel
    identity: CompilerCallIdentity
    response_sha256: str
    cache_hit: bool


def _schema_sha256(schema: Type[BaseModel]) -> str:
    return sha256_text(canonical_json(schema.model_json_schema()))


EXTRACTOR_SCHEMA_SHA256 = sha256_text(
    canonical_json(
        {
            "wire_envelope": ExtractorWireSessionOutput.model_json_schema(),
            "strict_output": ExtractorSessionOutput.model_json_schema(),
            "strict_mp": ProposedMPMemoryUnit.model_json_schema(),
            "strict_ms": ProposedMSMemoryUnit.model_json_schema(),
            "strict_me": ProposedMEMemoryUnit.model_json_schema(),
        }
    )
)


def _raw_proposal_id(raw: dict[str, Any]) -> str | None:
    value = raw.get("proposal_id")
    return value if isinstance(value, str) and value else None


def _validation_violations(exc: ValidationError) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                f"{'.'.join(str(part) for part in item['loc'])}:{item['type']}"
                for item in exc.errors()
            }
        )
    )


def _schema_rejection(
    *,
    phase: str,
    item_index: int,
    raw: dict[str, Any],
    violations: tuple[str, ...],
) -> SchemaRejectedItem:
    return SchemaRejectedItem(
        phase=phase,
        item_index=item_index,
        proposal_id=_raw_proposal_id(raw),
        violations=violations,
        raw_item_sha256=sha256_text(canonical_json(raw)),
    )


def _strict_extractor_output(
    wire: ExtractorWireSessionOutput,
) -> tuple[ExtractorSessionOutput, tuple[SchemaRejectedItem, ...]]:
    lanes: tuple[tuple[str, tuple[dict[str, Any], ...], Type[BaseModel]], ...] = (
        ("mp_facts", wire.mp_facts, ProposedMPMemoryUnit),
        ("ms_memories", wire.ms_memories, ProposedMSMemoryUnit),
        ("me_experiences", wire.me_experiences, ProposedMEMemoryUnit),
    )
    all_raw = [raw for _, rows, _ in lanes for raw in rows]
    raw_ids = [_raw_proposal_id(raw) for raw in all_raw]
    duplicate_ids = {
        proposal_id
        for proposal_id, count in Counter(raw_ids).items()
        if proposal_id is not None and count > 1
    }
    parsed_by_lane: dict[str, list[BaseModel]] = {
        "mp_facts": [],
        "ms_memories": [],
        "me_experiences": [],
    }
    rejections: list[SchemaRejectedItem] = []
    item_index = 0
    for lane_name, rows, model in lanes:
        for raw in rows:
            if _raw_proposal_id(raw) in duplicate_ids:
                rejections.append(
                    _schema_rejection(
                        phase="extractor",
                        item_index=item_index,
                        raw=raw,
                        violations=("proposal_id:schema_duplicate",),
                    )
                )
                item_index += 1
                continue
            try:
                parsed_by_lane[lane_name].append(model.model_validate(raw))
            except ValidationError as exc:
                rejections.append(
                    _schema_rejection(
                        phase="extractor",
                        item_index=item_index,
                        raw=raw,
                        violations=_validation_violations(exc),
                    )
                )
            item_index += 1
    return (
        ExtractorSessionOutput(
            owner_id=wire.owner_id,
            session_id=wire.session_id,
            mp_facts=tuple(parsed_by_lane["mp_facts"]),
            ms_memories=tuple(parsed_by_lane["ms_memories"]),
            me_experiences=tuple(parsed_by_lane["me_experiences"]),
        ),
        tuple(rejections),
    )


def _strict_verifier_output(
    wire: VerifierWireSessionOutput,
    *,
    expected_proposal_ids: set[str],
) -> tuple[VerifierSessionOutput, tuple[SchemaRejectedItem, ...]]:
    raw_ids = [_raw_proposal_id(raw) for raw in wire.decisions]
    duplicate_ids = {
        proposal_id
        for proposal_id, count in Counter(raw_ids).items()
        if proposal_id is not None and count > 1
    }
    decisions: list[VerifierDecision] = []
    rejections: list[SchemaRejectedItem] = []
    covered_ids: set[str] = set()
    for index, raw in enumerate(wire.decisions):
        proposal_id = _raw_proposal_id(raw)
        if proposal_id in duplicate_ids:
            rejections.append(
                _schema_rejection(
                    phase="verifier",
                    item_index=index,
                    raw=raw,
                    violations=("proposal_id:schema_duplicate",),
                )
            )
            if proposal_id is not None:
                covered_ids.add(proposal_id)
            continue
        try:
            decision = VerifierDecision.model_validate(raw)
        except ValidationError as exc:
            rejections.append(
                _schema_rejection(
                    phase="verifier",
                    item_index=index,
                    raw=raw,
                    violations=_validation_violations(exc),
                )
            )
            if proposal_id is not None:
                covered_ids.add(proposal_id)
            continue
        covered_ids.add(decision.proposal_id)
        if decision.proposal_id not in expected_proposal_ids:
            rejections.append(
                _schema_rejection(
                    phase="verifier",
                    item_index=index,
                    raw=raw,
                    violations=("proposal_id:unknown",),
                )
            )
            continue
        decisions.append(decision)
    for offset, proposal_id in enumerate(sorted(expected_proposal_ids - covered_ids)):
        raw = {"proposal_id": proposal_id, "missing": True}
        rejections.append(
            _schema_rejection(
                phase="verifier",
                item_index=len(wire.decisions) + offset,
                raw=raw,
                violations=("proposal_id:missing_decision",),
            )
        )
    return (
        VerifierSessionOutput(
            owner_id=wire.owner_id,
            session_id=wire.session_id,
            decisions=tuple(decisions),
        ),
        tuple(rejections),
    )


VERIFIER_SCHEMA_SHA256 = sha256_text(
    canonical_json(
        {
            "wire_envelope": VerifierWireSessionOutput.model_json_schema(),
            "strict_output": VerifierSessionOutput.model_json_schema(),
            "strict_decision": VerifierDecision.model_json_schema(),
        }
    )
)


class SemanticMemoryCompiler:
    def __init__(
        self,
        *,
        binding: RuntimeBinding,
        price: PriceSnapshot,
        client: SemanticCompilerClient,
        cache_root: str | Path,
        attempt_ledger_root: str | Path,
        budget_ledger_path: str | Path,
    ) -> None:
        self.binding = binding
        self.endpoint = binding.checked_endpoint
        if price.provider != binding.provider or price.region != binding.region:
            raise ValueError("price snapshot provider/region must match runtime binding")
        self.price = price
        self.client = client
        self.cache = SuccessCache(cache_root)
        self.attempt_ledger_root = Path(attempt_ledger_root)
        self.budget = SemanticCompilerBudgetLedger(budget_ledger_path, price=price)

    @property
    def compiler_version(self) -> str:
        return self.binding.compiler_version

    @property
    def grounding_version(self) -> str:
        return GROUNDING_VERSION

    def _call(
        self,
        *,
        phase: str,
        source: SessionCompileInput,
        messages: list[dict[str, str]],
        response_schema: Type[BaseModel],
        parameters: CallParameters,
        prompt_sha256: str,
        schema_sha256_override: str | None = None,
    ) -> _CallArtifact:
        assert_compiler_input_firewall(source.model_dump(mode="json"))
        payload = chat_request_payload(
            self.endpoint,
            messages,
            temperature=parameters.temperature,
            max_tokens=parameters.max_tokens,
            seed=parameters.seed,
            response_schema=response_schema,
        )
        payload_sha = sha256_text(canonical_json(payload))
        schema_sha = schema_sha256_override or _schema_sha256(response_schema)
        identity = CompilerCallIdentity(
            phase=phase,
            compiler_version=self.binding.compiler_version,
            provider=self.binding.provider,
            region=self.binding.region,
            base_url=self.endpoint.base_url,
            model=self.endpoint.model,
            enable_thinking=False,
            response_mode="json_object_plus_local_pydantic",
            request_parameters=parameters.model_dump(mode="json"),
            prompt_sha256=prompt_sha256,
            schema_sha256=schema_sha,
            source_sha256=source_sha256(source),
            prior_memory_table_sha256=prior_memory_table_sha256(source),
            request_payload_sha256=payload_sha,
        )
        cached = self.cache.load(identity)
        if cached is not None:
            parsed = response_schema.model_validate(cached["parsed"])
            return _CallArtifact(
                parsed=parsed,
                identity=identity,
                response_sha256=str(cached["response_sha256"]),
                cache_hit=True,
            )

        call_key = identity.cache_key
        attempt_path = self.attempt_ledger_root / phase / f"{call_key}.jsonl"
        attempts = PersistentAttemptLedger(
            attempt_path,
            stage=f"paper1_semantic_memory_{phase}",
            expected_calls={call_key: 1},
            maximum_total_attempts=1,
        )
        if attempts.started_attempts:
            raise RuntimeError(
                "semantic compiler attempt already started without a success cache; "
                "fail closed for manual crash reconciliation"
            )
        reservation = self.budget.reserve(
            reservation_id=call_key,
            phase=phase,
            call_key=call_key,
            maximum_prompt_tokens=parameters.maximum_prompt_tokens,
            maximum_completion_tokens=parameters.max_tokens,
        )
        attempt = attempts.reserve(
            call_key,
            record_ids={"owner_id": source.owner_id, "session_id": source.session_id},
            prompt_sha256=prompt_sha256,
        )
        result: CallResult | None = None
        budget_settled = False
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
                raise RuntimeError("semantic compiler returned no schema-validated object")
            parsed = response_schema.model_validate(parsed)
            if result.request_hash != payload_sha:
                raise RuntimeError("client request hash differs from frozen request payload")
            if result.normalized_finish_reason != "complete":
                raise RuntimeError(
                    "semantic compiler response did not finish completely: "
                    f"{result.normalized_finish_reason}"
                )
            usage = result.usage
            maximum_cost = self.price.cost(
                prompt_tokens=parameters.maximum_prompt_tokens,
                completion_tokens=parameters.max_tokens,
            )
            actual_cost = self.price.cost(
                prompt_tokens=int(usage.get("prompt_tokens") or 0),
                completion_tokens=int(usage.get("completion_tokens") or 0),
            )
            if int(usage.get("prompt_tokens") or 0) <= 0 or actual_cost > maximum_cost:
                raise RuntimeError("provider usage is invalid or exceeds the pre-call reservation")
            if int(usage.get("prompt_tokens") or 0) > parameters.maximum_prompt_tokens:
                raise RuntimeError("provider prompt usage exceeds the frozen prompt-token bound")
            if int(usage.get("completion_tokens") or 0) > parameters.max_tokens:
                raise RuntimeError("provider completion usage exceeds the frozen output-token bound")
            response_sha = sha256_text(canonical_json(result.raw_response))
            self.cache.store_success(
                identity,
                {
                    "parsed": parsed.model_dump(mode="json"),
                    "response_sha256": response_sha,
                    "request_sha256": result.request_hash,
                    "usage": usage,
                    "latency_ms": result.latency_ms,
                    "provider_finish_reason": result.provider_finish_reason,
                    "normalized_finish_reason": result.normalized_finish_reason,
                    "structured_output_audit": result.structured_output_audit,
                },
            )
            settled_cost = self.budget.settle(reservation, usage=usage, outcome="SUCCEEDED")
            budget_settled = True
            attempts.finish(
                attempt,
                succeeded=True,
                request_hash=result.request_hash,
                usage=usage,
                error=None,
                result={"response_sha256": response_sha},
                metadata={
                    "provider": self.binding.provider,
                    "region": self.binding.region,
                    "model": self.endpoint.model,
                    "phase": phase,
                    "source_sha256": identity.source_sha256,
                    "prior_memory_table_sha256": identity.prior_memory_table_sha256,
                    "schema_sha256": identity.schema_sha256,
                    "compiler_version": identity.compiler_version,
                    "latency_ms": result.latency_ms,
                    "finish_reason": result.provider_finish_reason,
                    "retry_reason": None,
                    "estimated_cost_usd": str(settled_cost),
                    "price_snapshot_id": self.price.snapshot_id,
                },
            )
            return _CallArtifact(parsed, identity, response_sha, False)
        except Exception as exc:
            failure_result = result or getattr(exc, "call", None)
            failure_usage = (
                failure_result.usage
                if isinstance(failure_result, CallResult)
                else getattr(exc, "usage", None)
            )
            usable_failure_usage = failure_usage
            if failure_usage is not None:
                prompt_tokens = int(failure_usage.get("prompt_tokens") or 0)
                completion_tokens = int(failure_usage.get("completion_tokens") or 0)
                if (
                    prompt_tokens <= 0
                    or prompt_tokens > parameters.maximum_prompt_tokens
                    or completion_tokens < 0
                    or completion_tokens > parameters.max_tokens
                ):
                    usable_failure_usage = None
            if not budget_settled:
                self.budget.settle(
                    reservation,
                    usage=usable_failure_usage,
                    outcome=(
                        "FAILED_PROVIDER_REPORTED_USAGE"
                        if usable_failure_usage is not None
                        else "FAILED_UNKNOWN_USAGE"
                    ),
                )
            failure_request_hash = (
                failure_result.request_hash
                if isinstance(failure_result, CallResult)
                else getattr(exc, "request_hash", None) or payload_sha
            )
            failure_diagnostic: dict[str, Any] | None = None
            if isinstance(failure_result, CallResult):
                parsed_payload = getattr(exc, "parsed_payload", None)
                failure_diagnostic = {
                    "response_sha256": sha256_text(
                        canonical_json(failure_result.raw_response)
                    ),
                    "provider_text_sha256": sha256_text(failure_result.text),
                    "provider_text": failure_result.text,
                    "parsed_payload": parsed_payload,
                    "parsed_payload_sha256": (
                        sha256_text(canonical_json(parsed_payload))
                        if parsed_payload is not None
                        else None
                    ),
                    "structured_output_audit": failure_result.structured_output_audit,
                }
            if attempts.terminal_event(call_key, attempt.attempt_index) is None:
                attempts.finish(
                    attempt,
                    succeeded=False,
                    request_hash=failure_request_hash,
                    usage=failure_usage,
                    error=f"{type(exc).__name__}: {exc}",
                    result=failure_diagnostic,
                    metadata={
                        "provider": self.binding.provider,
                        "region": self.binding.region,
                        "model": self.endpoint.model,
                        "phase": phase,
                        "source_sha256": identity.source_sha256,
                        "prior_memory_table_sha256": identity.prior_memory_table_sha256,
                        "schema_sha256": identity.schema_sha256,
                        "compiler_version": identity.compiler_version,
                        "latency_ms": (
                            failure_result.latency_ms
                            if isinstance(failure_result, CallResult)
                            else None
                        ),
                        "finish_reason": (
                            failure_result.provider_finish_reason
                            if isinstance(failure_result, CallResult)
                            else None
                        ),
                        "retry_reason": getattr(exc, "last_retry_class", None),
                    },
                )
            raise

    def compile_session(self, source: SessionCompileInput) -> SessionCompilationResult:
        source_json = canonical_json(source.model_dump(mode="json"))
        extractor_call = self._call(
            phase="extractor",
            source=source,
            messages=extractor_messages(
                source_json,
                canonical_json(ExtractorSessionOutput.model_json_schema()),
            ),
            response_schema=ExtractorWireSessionOutput,
            parameters=self.binding.extractor,
            prompt_sha256=EXTRACTOR_PROMPT_SHA256,
            schema_sha256_override=EXTRACTOR_SCHEMA_SHA256,
        )
        extractor_wire = ExtractorWireSessionOutput.model_validate(extractor_call.parsed)
        if (
            extractor_wire.owner_id != source.owner_id
            or extractor_wire.session_id != source.session_id
        ):
            raise ValueError("extractor wire output owner/session binding mismatch")
        extractor, extractor_schema_rejections = _strict_extractor_output(
            extractor_wire
        )
        validate_output_binding(source, extractor)
        grounding = tuple(
            validate_proposal_grounding(source, proposal) for proposal in extractor.proposals
        )
        grounding_by_id = {result.proposal_id: result for result in grounding}
        grounded_extractor = ExtractorSessionOutput(
            owner_id=extractor.owner_id,
            session_id=extractor.session_id,
            mp_facts=tuple(
                proposal
                for proposal in extractor.mp_facts
                if grounding_by_id[proposal.proposal_id].valid
            ),
            ms_memories=tuple(
                proposal
                for proposal in extractor.ms_memories
                if grounding_by_id[proposal.proposal_id].valid
            ),
            me_experiences=tuple(
                proposal
                for proposal in extractor.me_experiences
                if grounding_by_id[proposal.proposal_id].valid
            ),
        )
        proposals_json = canonical_json(grounded_extractor.model_dump(mode="json"))
        verifier_call = self._call(
            phase="verifier",
            source=source,
            messages=verifier_messages(
                source_json,
                proposals_json,
                canonical_json(VerifierSessionOutput.model_json_schema()),
            ),
            response_schema=VerifierWireSessionOutput,
            parameters=self.binding.verifier,
            prompt_sha256=VERIFIER_PROMPT_SHA256,
            schema_sha256_override=VERIFIER_SCHEMA_SHA256,
        )
        verifier_wire = VerifierWireSessionOutput.model_validate(verifier_call.parsed)
        if (
            verifier_wire.owner_id != source.owner_id
            or verifier_wire.session_id != source.session_id
        ):
            raise ValueError("verifier wire output owner/session binding mismatch")
        verifier, verifier_schema_rejections = _strict_verifier_output(
            verifier_wire,
            expected_proposal_ids={
                proposal.proposal_id for proposal in grounded_extractor.proposals
            },
        )

        decisions_by_id = {decision.proposal_id: decision for decision in verifier.decisions}
        accepted: list[AcceptedSemanticMemoryUnit] = []
        for proposal in extractor.proposals:
            grounding_result = grounding_by_id[proposal.proposal_id]
            if not grounding_result.valid:
                continue
            decision = decisions_by_id.get(proposal.proposal_id)
            if decision is None:
                continue
            if not decision.accepted:
                continue
            turn_ids = tuple(
                dict.fromkeys(span.turn_id for span in grounding_result.grounded_spans)
            )
            rendered_content = render_semantic_memory(proposal)
            rendered_content_sha256 = sha256_text(rendered_content)
            memory_id = "smu_" + sha256_text(
                canonical_json(
                    {
                        "owner_id": source.owner_id,
                        "session_id": source.session_id,
                        "proposal": proposal.model_dump(mode="json"),
                        "compiler_version": self.binding.compiler_version,
                        "renderer_version": RENDERER_VERSION,
                        "renderer_sha256": RENDERER_SHA256,
                        "renderer_code_sha256": RENDERER_CODE_SHA256,
                        "rendered_candidate_content_sha256": rendered_content_sha256,
                    }
                )
            )[:24]
            accepted.append(
                AcceptedSemanticMemoryUnit(
                    memory_id=memory_id,
                    owner_id=source.owner_id,
                    source_session_id=source.session_id,
                    source_session_rank=source.chronological_rank,
                    source_turn_ids=turn_ids,
                    memory_class=proposal.memory_class,
                    memory_subtype=proposal.memory_subtype,
                    normalized_memory=proposal.normalized_memory,
                    supporting_spans=grounding_result.grounded_spans,
                    entities=proposal.entities,
                    timestamp=source.timestamp,
                    timestamp_status=proposal.timestamp_status,
                    candidate_source_use=(
                        CandidateSourceUse.STATE_TABLE_ONLY
                        if isinstance(proposal, ProposedMSMemoryUnit)
                        and proposal.timestamp_status.value == "uncertain"
                        else CandidateSourceUse.CANDIDATE_SOURCE
                    ),
                    linked_prior_memory_ids=proposal.linked_prior_memory_ids,
                    linked_prior_relations=proposal.linked_prior_relations,
                    profile_field_type=(
                        proposal.profile_field_type
                        if isinstance(proposal, ProposedMPMemoryUnit)
                        else None
                    ),
                    continuity_type=(
                        proposal.continuity_type
                        if isinstance(proposal, ProposedMSMemoryUnit)
                        else None
                    ),
                    historical_outcome_type=(
                        proposal.historical_outcome_type
                        if isinstance(proposal, ProposedMEMemoryUnit)
                        else None
                    ),
                    action=(
                        proposal.action
                        if isinstance(proposal, ProposedMEMemoryUnit)
                        else None
                    ),
                    observed_outcome=(
                        proposal.observed_outcome
                        if isinstance(proposal, ProposedMEMemoryUnit)
                        else None
                    ),
                    rendered_candidate_content=rendered_content,
                    rendered_candidate_content_sha256=rendered_content_sha256,
                    action_span_ids=proposal.action_span_ids,
                    observed_outcome_span_ids=proposal.observed_outcome_span_ids,
                    compiler_version=self.binding.compiler_version,
                    renderer_version=RENDERER_VERSION,
                    renderer_sha256=RENDERER_SHA256,
                    renderer_code_sha256=RENDERER_CODE_SHA256,
                    verifier_method=VERIFIER_METHOD,
                    provider=self.binding.provider,
                    region=self.binding.region,
                    model=self.endpoint.model,
                    enable_thinking=False,
                    extractor_prompt_sha256=EXTRACTOR_PROMPT_SHA256,
                    verifier_prompt_sha256=VERIFIER_PROMPT_SHA256,
                    extractor_schema_sha256=extractor_call.identity.schema_sha256,
                    verifier_schema_sha256=verifier_call.identity.schema_sha256,
                    source_sha256=extractor_call.identity.source_sha256,
                    prior_memory_table_sha256=extractor_call.identity.prior_memory_table_sha256,
                    extractor_request_sha256=extractor_call.identity.request_payload_sha256,
                    extractor_response_sha256=extractor_call.response_sha256,
                    verifier_request_sha256=verifier_call.identity.request_payload_sha256,
                    verifier_response_sha256=verifier_call.response_sha256,
                )
            )
        rejected = tuple(decision for decision in verifier.decisions if not decision.accepted)
        return SessionCompilationResult(
            compiler_version=self.binding.compiler_version,
            grounding_version=GROUNDING_VERSION,
            owner_id=source.owner_id,
            session_id=source.session_id,
            source_sha256=source_sha256(source),
            prior_memory_table_sha256=prior_memory_table_sha256(source),
            extractor=extractor,
            verifier=verifier,
            schema_rejections=(
                *extractor_schema_rejections,
                *verifier_schema_rejections,
            ),
            grounding=tuple(
                {
                    "proposal_id": item.proposal_id,
                    "schema_valid": item.schema_valid,
                    "structural_valid": item.structural_valid,
                    "valid": item.valid,
                    "violations": item.violations,
                    "grounded_spans": tuple(
                        span.model_dump(mode="json") for span in item.grounded_spans
                    ),
                }
                for item in grounding
            ),
            accepted_units=tuple(accepted),
            rejected_decisions=rejected,
            extractor_cache_hit=extractor_call.cache_hit,
            verifier_cache_hit=verifier_call.cache_hit,
        )
