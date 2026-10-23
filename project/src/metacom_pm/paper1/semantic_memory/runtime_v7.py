"""Live v7 precision runtime for the frozen Paper-1 Qwen semantic compiler.

The v6 result carrier and artifact loader remain available for provenance.  This
module changes neither model nor ontology: it binds the approved v7 prompts,
class-specific verifier schemas, and deterministic precision gates to a new
content-addressed runtime identity.
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any, Type

from pydantic import BaseModel, Field, ValidationError

from metacom_pm.api import Endpoint
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import StrictContract

from .budget import PriceSnapshot
from .contracts import (
    AcceptedSemanticMemoryUnit,
    CandidateSourceUse,
    ExtractorSessionOutput,
    ExtractorWireSessionOutput,
    MemoryClass,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    ProposedSemanticMemoryUnit,
    SchemaRejectedItem,
    SessionCompileInput,
    SourceRole,
    VerifierDecision,
    VerifierRejectionReason,
    VerifierSessionOutput,
)
from .grounding import (
    prior_memory_table_sha256,
    source_sha256,
    validate_output_binding,
    validate_proposal_grounding,
)
from .precision_qualification import (
    MEPrecisionDecision,
    MPPrecisionDecision,
    MSSemanticAuditDecision,
    PRECISION_EXTRACTOR_PROMPT_SHA256,
    PRECISION_GROUNDING_VERSION,
    PRECISION_VERIFIER_PROMPT_SHA256,
    PrecisionDecision,
    PrecisionVerifierSessionOutput,
    PrecisionVerifierWireSessionOutput,
    precision_extractor_messages,
    precision_verifier_messages,
)
from .renderer import (
    RENDERER_CODE_SHA256,
    RENDERER_SHA256,
    RENDERER_VERSION,
    render_semantic_memory,
)
from .runtime import (
    CallParameters,
    FROZEN_QWEN_MODEL,
    SemanticCompilerClient,
    SemanticMemoryCompiler,
    SessionCompilationResult,
    _raw_proposal_id,
    _schema_rejection,
    _strict_extractor_output,
    _validation_violations,
)

COMPILER_VERSION_V7 = "paper1-qwen-semantic-memory-compiler-v7"
VERIFIER_METHOD_V7 = "same_qwen_model_v7_precision_verifier_not_independent"
LOCAL_PRECISION_BINDING_VERSION_V7 = (
    "paper1-semantic-memory-v7-local-binding-v2-shared-span-ordering-fix"
)


def _schema_sha256(value: object) -> str:
    return sha256_text(canonical_json(value))


EXTRACTOR_SCHEMA_SHA256_V7 = _schema_sha256(
    {
        "wire_envelope": ExtractorWireSessionOutput.model_json_schema(),
        "strict_output": ExtractorSessionOutput.model_json_schema(),
        "strict_mp": ProposedMPMemoryUnit.model_json_schema(),
        "strict_ms": ProposedMSMemoryUnit.model_json_schema(),
        "strict_me": ProposedMEMemoryUnit.model_json_schema(),
        "precision_schema_version": "paper1-semantic-memory-precision-schema-v7",
    }
)
VERIFIER_SCHEMA_SHA256_V7 = _schema_sha256(
    {
        "wire_envelope": PrecisionVerifierWireSessionOutput.model_json_schema(),
        "strict_output": PrecisionVerifierSessionOutput.model_json_schema(),
        "strict_mp": MPPrecisionDecision.model_json_schema(),
        "strict_ms": MSSemanticAuditDecision.model_json_schema(),
        "strict_me": MEPrecisionDecision.model_json_schema(),
    }
)


class RuntimeBindingV7(StrictContract):
    provider: str = "Alibaba Cloud Model Studio"
    region: str = Field(min_length=1)
    endpoint: Endpoint
    extractor: CallParameters
    verifier: CallParameters
    compiler_version: str = COMPILER_VERSION_V7

    @property
    def checked_endpoint(self) -> Endpoint:
        endpoint = self.endpoint
        if self.provider != "Alibaba Cloud Model Studio":
            raise ValueError("semantic compiler provider must remain Alibaba Cloud Model Studio")
        if self.compiler_version != COMPILER_VERSION_V7:
            raise ValueError(f"v7 compiler version must be {COMPILER_VERSION_V7}")
        if endpoint.model != FROZEN_QWEN_MODEL:
            raise ValueError(f"semantic compiler model must be {FROZEN_QWEN_MODEL}")
        if endpoint.transport != "openai_chat_completions":
            raise ValueError("semantic compiler requires frozen OpenAI-compatible transport")
        if endpoint.supports_strict_json_schema:
            raise ValueError("Qwen must use JSON-object mode plus local strict validation")
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
                    "grounding_version": PRECISION_GROUNDING_VERSION,
                    "local_precision_binding_version": LOCAL_PRECISION_BINDING_VERSION_V7,
                    "extractor_prompt_sha256": PRECISION_EXTRACTOR_PROMPT_SHA256,
                    "verifier_prompt_sha256": PRECISION_VERIFIER_PROMPT_SHA256,
                    "extractor_schema_sha256": EXTRACTOR_SCHEMA_SHA256_V7,
                    "verifier_schema_sha256": VERIFIER_SCHEMA_SHA256_V7,
                    "renderer_version": RENDERER_VERSION,
                    "renderer_sha256": RENDERER_SHA256,
                    "renderer_code_sha256": RENDERER_CODE_SHA256,
                }
            )
        )


def _strict_precision_output(
    wire: PrecisionVerifierWireSessionOutput,
    *,
    expected_by_class: dict[MemoryClass, set[str]],
) -> tuple[PrecisionVerifierSessionOutput, tuple[SchemaRejectedItem, ...]]:
    lanes: tuple[
        tuple[str, MemoryClass, tuple[dict[str, Any], ...], Type[BaseModel]], ...
    ] = (
        ("mp_decisions", MemoryClass.MP, wire.mp_decisions, MPPrecisionDecision),
        ("ms_decisions", MemoryClass.MS, wire.ms_decisions, MSSemanticAuditDecision),
        ("me_decisions", MemoryClass.ME, wire.me_decisions, MEPrecisionDecision),
    )
    all_raw = [raw for _, _, rows, _ in lanes for raw in rows]
    raw_ids = [_raw_proposal_id(raw) for raw in all_raw]
    duplicate_ids = {
        proposal_id
        for proposal_id, count in Counter(raw_ids).items()
        if proposal_id is not None and count > 1
    }
    parsed: dict[str, list[BaseModel]] = {name: [] for name, _, _, _ in lanes}
    rejected: list[SchemaRejectedItem] = []
    covered: set[str] = set()
    item_index = 0
    for lane_name, memory_class, rows, model in lanes:
        for raw in rows:
            proposal_id = _raw_proposal_id(raw)
            if proposal_id is not None:
                covered.add(proposal_id)
            if proposal_id in duplicate_ids:
                rejected.append(
                    _schema_rejection(
                        phase="verifier",
                        item_index=item_index,
                        raw=raw,
                        violations=("proposal_id:schema_duplicate",),
                    )
                )
            elif proposal_id not in expected_by_class[memory_class]:
                rejected.append(
                    _schema_rejection(
                        phase="verifier",
                        item_index=item_index,
                        raw=raw,
                        violations=("proposal_id:unknown_or_wrong_class_lane",),
                    )
                )
            else:
                try:
                    parsed[lane_name].append(model.model_validate(raw))
                except ValidationError as exc:
                    rejected.append(
                        _schema_rejection(
                            phase="verifier",
                            item_index=item_index,
                            raw=raw,
                            violations=_validation_violations(exc),
                        )
                    )
            item_index += 1
    expected_all = set().union(*expected_by_class.values())
    for offset, proposal_id in enumerate(sorted(expected_all - covered)):
        rejected.append(
            _schema_rejection(
                phase="verifier",
                item_index=item_index + offset,
                raw={"proposal_id": proposal_id, "missing": True},
                violations=("proposal_id:missing_decision",),
            )
        )
    return (
        PrecisionVerifierSessionOutput(
            owner_id=wire.owner_id,
            session_id=wire.session_id,
            mp_decisions=tuple(parsed["mp_decisions"]),
            ms_decisions=tuple(parsed["ms_decisions"]),
            me_decisions=tuple(parsed["me_decisions"]),
        ),
        tuple(rejected),
    )


def precision_binding_violations(
    source: SessionCompileInput,
    proposal: ProposedSemanticMemoryUnit,
    decision: PrecisionDecision,
) -> tuple[str, ...]:
    """Bind semantic evidence back to the exact grounded proposal and source."""

    violations: list[str] = []
    turns = {turn.turn_id: turn for turn in source.turns}
    proposal_spans = {(span.turn_id, span.exact_text) for span in proposal.supporting_spans}
    if isinstance(decision, MPPrecisionDecision):
        spans = decision.exact_support_span
        if not isinstance(proposal, ProposedMPMemoryUnit):
            violations.append("precision_wrong_proposal_class")
        elif decision.field_type is not proposal.profile_field_type:
            violations.append("precision_mp_field_type_mismatch")
    elif isinstance(decision, MSSemanticAuditDecision):
        spans = decision.exact_support_span
        if not isinstance(proposal, ProposedMSMemoryUnit):
            violations.append("precision_wrong_proposal_class")
        elif decision.continuity_type is not proposal.continuity_type:
            violations.append("precision_ms_continuity_type_mismatch")
    else:
        spans = (*decision.action_span, *decision.outcome_span)
        if not isinstance(proposal, ProposedMEMemoryUnit):
            violations.append("precision_wrong_proposal_class")
        else:
            span_by_id = {span.span_id: span for span in proposal.supporting_spans}
            expected_action = {
                (span_by_id[span_id].turn_id, span_by_id[span_id].exact_text)
                for span_id in proposal.action_span_ids
                if span_id in span_by_id
            }
            expected_outcome = {
                (span_by_id[span_id].turn_id, span_by_id[span_id].exact_text)
                for span_id in proposal.observed_outcome_span_ids
                if span_id in span_by_id
            }
            if not {(span.turn_id, span.exact_text) for span in decision.action_span}.issubset(
                expected_action
            ):
                violations.append("precision_me_action_span_not_bound")
            if not {(span.turn_id, span.exact_text) for span in decision.outcome_span}.issubset(
                expected_outcome
            ):
                violations.append("precision_me_outcome_span_not_bound")
            positions: dict[tuple[str, str], tuple[int, int]] = {}
            for span in spans:
                turn = turns.get(span.turn_id)
                if turn is not None:
                    positions[(span.turn_id, span.exact_text)] = (
                        turn.turn_index,
                        turn.content.find(span.exact_text),
                    )
            action_positions = [
                positions.get((span.turn_id, span.exact_text), (10**9, 10**9))
                for span in decision.action_span
            ]
            outcome_positions = [
                positions.get((span.turn_id, span.exact_text), (-1, -1))
                for span in decision.outcome_span
            ]
            # A single exact source span may contain two ordered propositions
            # (completed action, then user-observed outcome).  Character/turn
            # order is only mechanically decidable when the verifier selected
            # distinct spans.  Shared-span semantic ordering remains governed
            # by the frozen ME precision fields/gate and must not be overruled
            # by an artificial ``same start position`` failure here.
            action_span_keys = {
                (span.turn_id, span.exact_text) for span in decision.action_span
            }
            outcome_span_keys = {
                (span.turn_id, span.exact_text) for span in decision.outcome_span
            }
            if (
                action_positions
                and outcome_positions
                and action_span_keys.isdisjoint(outcome_span_keys)
                and min(outcome_positions) <= min(action_positions)
            ):
                violations.append("precision_me_outcome_not_mechanically_after_action")
    for span in spans:
        turn = turns.get(span.turn_id)
        if turn is None:
            violations.append("precision_unknown_turn")
            continue
        if turn.role is not SourceRole.SEEKER:
            violations.append("precision_non_seeker_span")
        if turn.content.find(span.exact_text) < 0:
            violations.append("precision_span_text_absent")
        if (span.turn_id, span.exact_text) not in proposal_spans:
            violations.append("precision_span_not_in_grounded_proposal")
    return tuple(sorted(set(violations)))


def _legacy_decision(decision: PrecisionDecision) -> VerifierDecision:
    accepted = (
        decision.accepted
        if isinstance(decision, (MPPrecisionDecision, MEPrecisionDecision))
        else decision.accepted_for_candidate_source
    )
    return VerifierDecision(
        proposal_id=decision.proposal_id,
        accepted=accepted,
        reason=(
            VerifierRejectionReason.ACCEPTED
            if accepted
            else VerifierRejectionReason.OTHER_FACTUAL_MISMATCH
        ),
        factual_rationale=(
            "v7 class-specific precision gates passed"
            if accepted
            else "v7 class-specific precision gates rejected proposal"
        ),
    )


class SemanticMemoryCompilerV7(SemanticMemoryCompiler):
    def __init__(
        self,
        *,
        binding: RuntimeBindingV7,
        price: PriceSnapshot,
        client: SemanticCompilerClient,
        cache_root: str | Path,
        attempt_ledger_root: str | Path,
        budget_ledger_path: str | Path,
    ) -> None:
        super().__init__(
            binding=binding,  # type: ignore[arg-type]
            price=price,
            client=client,
            cache_root=cache_root,
            attempt_ledger_root=attempt_ledger_root,
            budget_ledger_path=budget_ledger_path,
        )

    @property
    def grounding_version(self) -> str:
        return PRECISION_GROUNDING_VERSION

    def _run_precision_verifier(
        self,
        *,
        source: SessionCompileInput,
        extractor: ExtractorSessionOutput,
    ) -> tuple[
        PrecisionVerifierSessionOutput,
        tuple[SchemaRejectedItem, ...],
        Any,
    ]:
        source_json = canonical_json(source.model_dump(mode="json"))
        proposals_json = canonical_json(extractor.model_dump(mode="json"))
        call = self._call(
            phase="verifier",
            source=source,
            messages=precision_verifier_messages(
                source_json,
                proposals_json,
                canonical_json(PrecisionVerifierSessionOutput.model_json_schema()),
            ),
            response_schema=PrecisionVerifierWireSessionOutput,
            parameters=self.binding.verifier,
            prompt_sha256=PRECISION_VERIFIER_PROMPT_SHA256,
            schema_sha256_override=VERIFIER_SCHEMA_SHA256_V7,
        )
        wire = PrecisionVerifierWireSessionOutput.model_validate(call.parsed)
        if wire.owner_id != source.owner_id or wire.session_id != source.session_id:
            raise ValueError("v7 verifier wire owner/session binding mismatch")
        expected_by_class = {
            MemoryClass.MP: {proposal.proposal_id for proposal in extractor.mp_facts},
            MemoryClass.MS: {proposal.proposal_id for proposal in extractor.ms_memories},
            MemoryClass.ME: {proposal.proposal_id for proposal in extractor.me_experiences},
        }
        strict, rejected = _strict_precision_output(
            wire,
            expected_by_class=expected_by_class,
        )
        return strict, rejected, call

    def verify_existing_proposals(
        self,
        *,
        source: SessionCompileInput,
        extractor: ExtractorSessionOutput,
    ) -> tuple[PrecisionVerifierSessionOutput, tuple[SchemaRejectedItem, ...]]:
        """Verifier-only DEV regression; it never creates candidate-source rows."""

        validate_output_binding(source, extractor)
        grounded = [validate_proposal_grounding(source, proposal) for proposal in extractor.proposals]
        invalid = [item.proposal_id for item in grounded if not item.valid]
        if invalid:
            raise ValueError(f"DEV proposals are not structurally grounded: {invalid}")
        verifier, rejected, _ = self._run_precision_verifier(source=source, extractor=extractor)
        return verifier, rejected

    def compile_session(self, source: SessionCompileInput) -> SessionCompilationResult:
        source_json = canonical_json(source.model_dump(mode="json"))
        extractor_call = self._call(
            phase="extractor",
            source=source,
            messages=precision_extractor_messages(
                source_json,
                canonical_json(ExtractorSessionOutput.model_json_schema()),
            ),
            response_schema=ExtractorWireSessionOutput,
            parameters=self.binding.extractor,
            prompt_sha256=PRECISION_EXTRACTOR_PROMPT_SHA256,
            schema_sha256_override=EXTRACTOR_SCHEMA_SHA256_V7,
        )
        extractor_wire = ExtractorWireSessionOutput.model_validate(extractor_call.parsed)
        if extractor_wire.owner_id != source.owner_id or extractor_wire.session_id != source.session_id:
            raise ValueError("v7 extractor wire owner/session binding mismatch")
        extractor, extractor_schema_rejections = _strict_extractor_output(extractor_wire)
        validate_output_binding(source, extractor)
        grounding = tuple(
            validate_proposal_grounding(source, proposal) for proposal in extractor.proposals
        )
        grounding_by_id = {item.proposal_id: item for item in grounding}
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
        precision, verifier_schema_rejections, verifier_call = self._run_precision_verifier(
            source=source,
            extractor=grounded_extractor,
        )
        proposal_by_id = {proposal.proposal_id: proposal for proposal in extractor.proposals}
        precision_by_id = {decision.proposal_id: decision for decision in precision.decisions}
        legacy_decisions: list[VerifierDecision] = []
        accepted: list[AcceptedSemanticMemoryUnit] = []
        precision_binding: list[dict[str, Any]] = []
        for proposal in extractor.proposals:
            grounding_result = grounding_by_id[proposal.proposal_id]
            decision = precision_by_id.get(proposal.proposal_id)
            violations = (
                precision_binding_violations(source, proposal, decision)
                if decision is not None
                else ("precision_missing_or_schema_invalid_decision",)
            )
            decision_accepted = False
            if decision is not None:
                legacy = _legacy_decision(decision)
                decision_accepted = legacy.accepted and not violations
                if legacy.accepted and violations:
                    legacy = VerifierDecision(
                        proposal_id=proposal.proposal_id,
                        accepted=False,
                        reason=VerifierRejectionReason.OTHER_FACTUAL_MISMATCH,
                        factual_rationale="deterministic v7 precision binding failed",
                    )
                legacy_decisions.append(legacy)
            precision_binding.append(
                {
                    "proposal_id": proposal.proposal_id,
                    "valid": not violations,
                    "violations": violations,
                }
            )
            if not grounding_result.valid or not decision_accepted:
                continue
            rendered_content = render_semantic_memory(proposal)
            rendered_sha = sha256_text(rendered_content)
            memory_id = "smu_" + sha256_text(
                canonical_json(
                    {
                        "owner_id": source.owner_id,
                        "session_id": source.session_id,
                        "proposal": proposal.model_dump(mode="json"),
                        "compiler_version": self.compiler_version,
                        "renderer_version": RENDERER_VERSION,
                        "renderer_sha256": RENDERER_SHA256,
                        "renderer_code_sha256": RENDERER_CODE_SHA256,
                        "rendered_candidate_content_sha256": rendered_sha,
                    }
                )
            )[:24]
            turn_ids = tuple(
                dict.fromkeys(span.turn_id for span in grounding_result.grounded_spans)
            )
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
                    action=proposal.action if isinstance(proposal, ProposedMEMemoryUnit) else None,
                    observed_outcome=(
                        proposal.observed_outcome
                        if isinstance(proposal, ProposedMEMemoryUnit)
                        else None
                    ),
                    rendered_candidate_content=rendered_content,
                    rendered_candidate_content_sha256=rendered_sha,
                    action_span_ids=proposal.action_span_ids,
                    observed_outcome_span_ids=proposal.observed_outcome_span_ids,
                    compiler_version=self.compiler_version,
                    renderer_version=RENDERER_VERSION,
                    renderer_sha256=RENDERER_SHA256,
                    renderer_code_sha256=RENDERER_CODE_SHA256,
                    verifier_method=VERIFIER_METHOD_V7,
                    provider=self.binding.provider,
                    region=self.binding.region,
                    model=self.endpoint.model,
                    enable_thinking=False,
                    extractor_prompt_sha256=PRECISION_EXTRACTOR_PROMPT_SHA256,
                    verifier_prompt_sha256=PRECISION_VERIFIER_PROMPT_SHA256,
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
        legacy_verifier = VerifierSessionOutput(
            owner_id=source.owner_id,
            session_id=source.session_id,
            decisions=tuple(legacy_decisions),
        )
        return SessionCompilationResult(
            compiler_version=self.compiler_version,
            grounding_version=self.grounding_version,
            owner_id=source.owner_id,
            session_id=source.session_id,
            source_sha256=source_sha256(source),
            prior_memory_table_sha256=prior_memory_table_sha256(source),
            extractor=extractor,
            verifier=legacy_verifier,
            precision_verifier=precision,
            schema_rejections=(*extractor_schema_rejections, *verifier_schema_rejections),
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
            precision_binding=tuple(precision_binding),
            accepted_units=tuple(accepted),
            rejected_decisions=tuple(
                decision for decision in legacy_decisions if not decision.accepted
            ),
            extractor_cache_hit=extractor_call.cache_hit,
            verifier_cache_hit=verifier_call.cache_hit,
        )
