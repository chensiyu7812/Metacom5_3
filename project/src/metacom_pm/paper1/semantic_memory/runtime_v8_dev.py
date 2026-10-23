"""Verifier-only v8 DEV runtime with deterministic local acceptance.

This runtime cannot compile the 401-session catalog.  It only annotates the
frozen old-DEV proposals with typed evidence, binds that evidence to the exact
public source, and derives every verdict in local code.
"""

from __future__ import annotations

from collections import Counter
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal, Type

from pydantic import BaseModel, Field, ValidationError, model_validator

from metacom_pm.api import Endpoint
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import StrictContract

from .budget import PriceSnapshot, SemanticCompilerBudgetLedger
from .cache import SuccessCache
from .contracts import (
    ExtractorSessionOutput,
    MemoryClass,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    ProposedMSMemoryUnit,
    ProposedSemanticMemoryUnit,
    SchemaRejectedItem,
    SHA256_PATTERN,
    SessionCompileInput,
    SourceRole,
)
from .evidence_v8 import (
    DeterministicV8Decision,
    METypedEvidence,
    MPTypedEvidence,
    MSTypedEvidence,
    TypedEvidenceV8,
    V8_DETERMINISTIC_GATE_VERSION,
    V8_EVIDENCE_SCHEMA_VERSION,
    V8_VERIFIER_PROMPT_SHA256,
    V8EvidenceSessionOutput,
    V8EvidenceWireSessionOutput,
    me_gate_reasons,
    me_internal_contradictions,
    mp_gate_reasons,
    mp_internal_contradictions,
    ms_gate_reasons,
    ms_internal_contradictions,
    v8_verifier_messages,
)
from .grounding import validate_output_binding, validate_proposal_grounding
from .runtime import (
    CallParameters,
    FROZEN_QWEN_MODEL,
    SemanticCompilerClient,
    SemanticMemoryCompiler,
    _raw_proposal_id,
    _schema_rejection,
    _validation_violations,
)


COMPILER_VERSION_V8_DEV = "paper1-qwen-semantic-memory-verifier-v8-dev"
LOCAL_BINDING_VERSION_V8_DEV = (
    "paper1-semantic-memory-v8-dev-binding-v1-shared-span-compatible"
)
V8_DEV_HARD_BUDGET_USD = Decimal("0.25")
V8_DEV_SCOPE = "OLD_DEV_32_ITEMS_IN_29_SOURCE_SESSIONS_ONLY"


def _schema_sha256(value: object) -> str:
    return sha256_text(canonical_json(value))


V8_VERIFIER_SCHEMA_SHA256 = _schema_sha256(
    {
        "wire_envelope": V8EvidenceWireSessionOutput.model_json_schema(),
        "strict_output": V8EvidenceSessionOutput.model_json_schema(),
        "strict_mp": MPTypedEvidence.model_json_schema(),
        "strict_ms": MSTypedEvidence.model_json_schema(),
        "strict_me": METypedEvidence.model_json_schema(),
    }
)


class RuntimeBindingV8Dev(StrictContract):
    provider: str = "Alibaba Cloud Model Studio"
    region: str = Field(min_length=1)
    endpoint: Endpoint
    verifier: CallParameters
    compiler_version: str = COMPILER_VERSION_V8_DEV

    @property
    def checked_endpoint(self) -> Endpoint:
        endpoint = self.endpoint
        if self.provider != "Alibaba Cloud Model Studio":
            raise ValueError("v8 DEV provider must remain Alibaba Cloud Model Studio")
        if self.compiler_version != COMPILER_VERSION_V8_DEV:
            raise ValueError(f"v8 DEV compiler version must be {COMPILER_VERSION_V8_DEV}")
        if endpoint.model != FROZEN_QWEN_MODEL:
            raise ValueError(f"v8 DEV model must remain {FROZEN_QWEN_MODEL}")
        if endpoint.transport != "openai_chat_completions":
            raise ValueError("v8 DEV requires the frozen OpenAI-compatible transport")
        if endpoint.supports_strict_json_schema:
            raise ValueError("v8 DEV uses JSON-object mode plus local strict validation")
        if endpoint.enable_thinking is not False:
            raise ValueError("v8 DEV must explicitly disable thinking")
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
                    "verifier": self.verifier.model_dump(mode="json"),
                    "compiler_version": self.compiler_version,
                    "evidence_schema_version": V8_EVIDENCE_SCHEMA_VERSION,
                    "deterministic_gate_version": V8_DETERMINISTIC_GATE_VERSION,
                    "local_binding_version": LOCAL_BINDING_VERSION_V8_DEV,
                    "verifier_prompt_sha256": V8_VERIFIER_PROMPT_SHA256,
                    "verifier_schema_sha256": V8_VERIFIER_SCHEMA_SHA256,
                    "scope": V8_DEV_SCOPE,
                }
            )
        )


class V8DevBudgetLedger(SemanticCompilerBudgetLedger):
    """Dedicated crash-conservative ledger for the approved USD 0.25 DEV cap."""

    def __init__(self, path: str | Path, *, price: PriceSnapshot) -> None:
        self.path = Path(path)
        self.price = price
        self.hard_budget_usd = V8_DEV_HARD_BUDGET_USD
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._load()


class V8DevAuthorization(StrictContract):
    protocol: Literal["paper1-semantic-memory-v8-dev-live-authorization-v1"]
    status: Literal["RESEARCHER_AUTHORIZED"]
    scope: Literal[V8_DEV_SCOPE]
    authorized_model: Literal[FROZEN_QWEN_MODEL]
    maximum_source_sessions: Literal[29]
    maximum_items: Literal[32]
    maximum_provider_calls: Literal[29]
    hard_budget_usd: Decimal
    runtime_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    sanitized_runtime_sha256: str = Field(pattern=SHA256_PATTERN)
    v6_results_sha256: str = Field(pattern=SHA256_PATTERN)
    dev_plan_sha256: str = Field(pattern=SHA256_PATTERN)
    v7_report_sha256: str = Field(pattern=SHA256_PATTERN)
    price_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    all_four_outcome_locks_closed: Literal[True]
    full_401_compile_authorized: Literal[False]
    outcome_calls: Literal[0]

    @model_validator(mode="after")
    def exact_dev_cap(self) -> "V8DevAuthorization":
        if self.hard_budget_usd != V8_DEV_HARD_BUDGET_USD:
            raise ValueError("v8 DEV authorization hard cap must be exactly USD 0.25")
        return self


def _expected_by_class(
    extractor: ExtractorSessionOutput,
) -> dict[MemoryClass, set[str]]:
    return {
        MemoryClass.MP: {item.proposal_id for item in extractor.mp_facts},
        MemoryClass.MS: {item.proposal_id for item in extractor.ms_memories},
        MemoryClass.ME: {item.proposal_id for item in extractor.me_experiences},
    }


def _strict_v8_output(
    wire: V8EvidenceWireSessionOutput,
    *,
    expected_by_class: dict[MemoryClass, set[str]],
) -> tuple[V8EvidenceSessionOutput, tuple[SchemaRejectedItem, ...]]:
    lanes: tuple[
        tuple[str, MemoryClass, tuple[dict[str, Any], ...], Type[BaseModel]], ...
    ] = (
        ("mp_evidence", MemoryClass.MP, wire.mp_evidence, MPTypedEvidence),
        ("ms_evidence", MemoryClass.MS, wire.ms_evidence, MSTypedEvidence),
        ("me_evidence", MemoryClass.ME, wire.me_evidence, METypedEvidence),
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
                violations = ("proposal_id:schema_duplicate",)
            elif proposal_id not in expected_by_class[memory_class]:
                violations = ("proposal_id:unknown_or_wrong_class_lane",)
            else:
                try:
                    parsed[lane_name].append(model.model_validate(raw))
                    item_index += 1
                    continue
                except ValidationError as exc:
                    violations = _validation_violations(exc)
            rejected.append(
                _schema_rejection(
                    phase="verifier",
                    item_index=item_index,
                    raw=raw,
                    violations=violations,
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
                violations=("proposal_id:missing_evidence",),
            )
        )
    return (
        V8EvidenceSessionOutput(
            owner_id=wire.owner_id,
            session_id=wire.session_id,
            mp_evidence=tuple(parsed["mp_evidence"]),
            ms_evidence=tuple(parsed["ms_evidence"]),
            me_evidence=tuple(parsed["me_evidence"]),
        ),
        tuple(rejected),
    )


def _span_keys(spans: tuple[Any, ...]) -> set[tuple[str, str]]:
    return {(span.turn_id, span.exact_text) for span in spans}


def v8_binding_violations(
    source: SessionCompileInput,
    proposal: ProposedSemanticMemoryUnit,
    evidence: TypedEvidenceV8,
) -> tuple[str, ...]:
    """Mechanically bind evidence to class, proposal fields, and exact seeker text."""

    violations: list[str] = []
    turns = {turn.turn_id: turn for turn in source.turns}
    proposal_keys = _span_keys(proposal.supporting_spans)
    if isinstance(evidence, MPTypedEvidence):
        spans = evidence.exact_support_spans
        if not isinstance(proposal, ProposedMPMemoryUnit):
            violations.append("wrong_proposal_class")
        elif evidence.field_type is not proposal.profile_field_type:
            violations.append("mp_field_type_mismatch")
    elif isinstance(evidence, MSTypedEvidence):
        spans = evidence.exact_support_spans
        if not isinstance(proposal, ProposedMSMemoryUnit):
            violations.append("wrong_proposal_class")
        elif evidence.continuity_type is not proposal.continuity_type:
            violations.append("ms_continuity_type_mismatch")
    else:
        spans = (*evidence.action_spans, *evidence.outcome_spans)
        if not isinstance(proposal, ProposedMEMemoryUnit):
            violations.append("wrong_proposal_class")
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
            action_keys = _span_keys(evidence.action_spans)
            outcome_keys = _span_keys(evidence.outcome_spans)
            if not action_keys.issubset(expected_action):
                violations.append("me_action_span_not_bound")
            if not outcome_keys.issubset(expected_outcome):
                violations.append("me_outcome_span_not_bound")
            # Shared exact spans are legal: one utterance can contain an action
            # clause followed by an outcome clause.  Only distinct-span reverse
            # order is mechanically knowable and rejected here.
            if action_keys.isdisjoint(outcome_keys):
                positions: dict[tuple[str, str], tuple[int, int]] = {}
                for span in spans:
                    turn = turns.get(span.turn_id)
                    if turn is not None:
                        positions[(span.turn_id, span.exact_text)] = (
                            turn.turn_index,
                            turn.content.find(span.exact_text),
                        )
                action_positions = [positions.get(key, (10**9, 10**9)) for key in action_keys]
                outcome_positions = [positions.get(key, (-1, -1)) for key in outcome_keys]
                if action_positions and outcome_positions and min(outcome_positions) <= min(
                    action_positions
                ):
                    violations.append("me_outcome_not_mechanically_after_action")
    for span in spans:
        turn = turns.get(span.turn_id)
        if turn is None:
            violations.append("unknown_turn")
            continue
        if turn.role is not SourceRole.SEEKER:
            violations.append("non_seeker_span")
        if span.exact_text not in turn.content:
            violations.append("span_text_absent")
        if (span.turn_id, span.exact_text) not in proposal_keys:
            violations.append("span_not_in_grounded_proposal")
    return tuple(sorted(set(violations)))


def deterministic_v8_decision(
    source: SessionCompileInput,
    proposal: ProposedSemanticMemoryUnit,
    evidence: TypedEvidenceV8,
) -> DeterministicV8Decision:
    if isinstance(evidence, MPTypedEvidence):
        gate_reasons = mp_gate_reasons(evidence)
        contradictions = mp_internal_contradictions(evidence)
    elif isinstance(evidence, MSTypedEvidence):
        gate_reasons = ms_gate_reasons(evidence)
        contradictions = ms_internal_contradictions(evidence)
    else:
        gate_reasons = me_gate_reasons(evidence)
        contradictions = me_internal_contradictions(evidence)
    binding = v8_binding_violations(source, proposal, evidence)
    return DeterministicV8Decision(
        proposal_id=proposal.proposal_id,
        accepted=not (gate_reasons or contradictions or binding),
        gate_reasons=gate_reasons,
        binding_violations=binding,
        internal_contradictions=contradictions,
    )


class SemanticMemoryV8DevVerifier(SemanticMemoryCompiler):
    """A deliberately verifier-only runtime; there is no full compile method."""

    def __init__(
        self,
        *,
        binding: RuntimeBindingV8Dev,
        price: PriceSnapshot,
        client: SemanticCompilerClient,
        cache_root: str | Path,
        attempt_ledger_root: str | Path,
        budget_ledger_path: str | Path,
    ) -> None:
        self.binding = binding
        self.endpoint = binding.checked_endpoint
        if price.provider != binding.provider or price.region != binding.region:
            raise ValueError("price snapshot provider/region must match v8 DEV binding")
        self.price = price
        self.client = client
        self.cache = SuccessCache(cache_root)
        self.attempt_ledger_root = Path(attempt_ledger_root)
        self.budget = V8DevBudgetLedger(budget_ledger_path, price=price)

    def compile_session(self, source: SessionCompileInput):  # pragma: no cover - hard guard
        raise RuntimeError("v8 DEV runtime cannot compile the 401-session catalog")

    def verify_existing_proposals(
        self,
        *,
        source: SessionCompileInput,
        extractor: ExtractorSessionOutput,
    ) -> tuple[
        V8EvidenceSessionOutput,
        tuple[SchemaRejectedItem, ...],
        tuple[DeterministicV8Decision, ...],
    ]:
        validate_output_binding(source, extractor)
        grounded = [
            validate_proposal_grounding(source, proposal)
            for proposal in extractor.proposals
        ]
        invalid = [item.proposal_id for item in grounded if not item.valid]
        if invalid:
            raise ValueError(f"v8 DEV proposals are not structurally grounded: {invalid}")
        source_json = canonical_json(source.model_dump(mode="json"))
        proposals_json = canonical_json(extractor.model_dump(mode="json"))
        call = self._call(
            phase="verifier",
            source=source,
            messages=v8_verifier_messages(
                source_json,
                proposals_json,
                canonical_json(V8EvidenceSessionOutput.model_json_schema()),
            ),
            response_schema=V8EvidenceWireSessionOutput,
            parameters=self.binding.verifier,
            prompt_sha256=V8_VERIFIER_PROMPT_SHA256,
            schema_sha256_override=V8_VERIFIER_SCHEMA_SHA256,
        )
        wire = V8EvidenceWireSessionOutput.model_validate(call.parsed)
        if wire.owner_id != source.owner_id or wire.session_id != source.session_id:
            raise ValueError("v8 evidence owner/session binding mismatch")
        strict, rejected = _strict_v8_output(
            wire,
            expected_by_class=_expected_by_class(extractor),
        )
        proposal_by_id = {proposal.proposal_id: proposal for proposal in extractor.proposals}
        decisions = tuple(
            deterministic_v8_decision(source, proposal_by_id[item.proposal_id], item)
            for item in strict.evidence
        )
        return strict, rejected, decisions
