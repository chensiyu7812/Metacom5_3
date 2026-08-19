"""Offline-first RS atomic-move compiler orchestration.

Mirrors ``semantic_memory/runtime.py``'s shape (injectable client for offline
tests; no secret loading or real client construction happens in this
module) but is simpler: one proposal type instead of three lanes, and no
cross-session prior-memory table (RS source turns are single-dialogue).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol, Type

from pydantic import BaseModel

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.io import append_jsonl, canonical_json, sha256_file, sha256_text
from metacom_pm.paper1.contracts import StrictContract
from pydantic import Field

from .budget import PriceSnapshot, RsAtomicMoveBudgetLedger
from .cache import CompilerCallIdentity, SuccessCache
from .contracts import (
    CONTRACTS_CODE_SHA256,
    RS_ATOMIC_MOVE_SCHEMA_VERSION,
    AcceptedAtomicMoveUnit,
    ExtractorProposalBatch,
    ProposedAtomicMoveUnit,
    SourceCardCompileInput,
    VerifierDecisionBatch,
)
from .grounding import GROUNDING_VERSION, GroundingResult, run_deterministic_grounding
from .prompts import (
    EXTRACTOR_PROMPT_SHA256,
    VERIFIER_PROMPT_SHA256,
    extractor_messages,
    verifier_messages,
)
from .renderer import RENDERER_CODE_SHA256, RENDERER_SHA256, RENDERER_VERSION, render_atomic_move
from .source_adapter import SOURCE_ADAPTER_CODE_SHA256

COMPILER_VERSION = "paper1-rs-atomic-move-compiler-v2"
FROZEN_QWEN_MODEL = "qwen3-235b-a22b-instruct-2507"
VERIFIER_METHOD = "same_qwen_model_semantic_factual_verifier_not_independent"
# Bound into run_manifest so a change to this module's own call-handling
# logic (e.g. the 2026-08-19 circuit-breaker/exception-narrowing fix) is
# reflected in run_identity_sha256, not just prompt/schema/renderer content.
RUNTIME_CODE_SHA256 = sha256_file(Path(__file__))
MAX_CONSECUTIVE_CALL_FAILURES = 5


class RsAtomicMoveClient(Protocol):
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
            raise ValueError("RS atomic-move compiler provider must remain Alibaba Cloud Model Studio")
        if self.compiler_version != COMPILER_VERSION:
            raise ValueError(f"RS atomic-move compiler version must be {COMPILER_VERSION}")
        if endpoint.model != FROZEN_QWEN_MODEL:
            raise ValueError(f"RS atomic-move compiler model must be {FROZEN_QWEN_MODEL}")
        if endpoint.transport != "openai_chat_completions":
            raise ValueError("RS atomic-move compiler requires frozen OpenAI-compatible transport")
        if endpoint.supports_strict_json_schema:
            raise ValueError("Qwen endpoint must use JSON-object mode plus local strict validation")
        if endpoint.enable_thinking is not False:
            raise ValueError("Qwen RS atomic-move compiler must explicitly disable thinking")
        return endpoint

    @property
    def identity_sha256(self) -> str:
        endpoint = self.checked_endpoint
        return sha256_text(
            canonical_json(
                {
                    "compiler_version": self.compiler_version,
                    "provider": self.provider,
                    "region": self.region,
                    "base_url": endpoint.base_url,
                    "model": endpoint.model,
                    "transport": endpoint.transport,
                    "supports_strict_json_schema": endpoint.supports_strict_json_schema,
                    "enable_thinking": endpoint.enable_thinking,
                }
            )
        )


@dataclass(frozen=True)
class SourceCardCompileResult:
    accepted_units: tuple[AcceptedAtomicMoveUnit, ...] = ()
    schema_invalid_proposals: int = 0
    structurally_invalid_proposals: int = 0
    grounding_rejections: tuple[GroundingResult, ...] = field(default_factory=tuple)
    verifier_rejections: int = 0
    extractor_proposal_count: int = 0
    duplicate_semantic_content_count: int = 0
    # A call that raised after exhausting its own internal retries (provider
    # error, or a response that never became parsable/schema-valid) --
    # distinct from schema_invalid_proposals/verifier_rejections, which both
    # require a response that WAS parsed. 0 accepted units either way
    # (fail-closed): an extractor call failure means no proposals exist to
    # ground at all; a verifier call failure means grounded proposals exist
    # but no decision was ever obtained for them, so none can be accepted.
    call_failure_phase: str | None = None


def source_sha256(source: SourceCardCompileInput) -> str:
    return sha256_text(canonical_json(source.model_dump(mode="json")))


class RsAtomicMoveCallFailed(RuntimeError):
    """A phase's provider call could not produce a usable response even
    after the client's own internal retries. The pre-call budget
    reservation for this exact call identity has already been settled
    (crash-conservatively, at the reserved maximum) before this is raised --
    callers must not attempt to reserve/settle again for the same identity,
    and per RsAtomicMoveBudgetLedger's fail-closed reservation-uniqueness
    rule, retrying the identical call content would raise on re-reservation
    regardless. The caller's only safe response is to record this source
    card's compile as a structural, zero-accepted-unit failure for this run
    and move on to the next card."""

    def __init__(self, phase: str, *, cause: BaseException) -> None:
        super().__init__(f"RS atomic-move {phase} call failed: {cause}")
        self.phase = phase


class RsAtomicMoveCircuitBreakerTripped(RuntimeError):
    """Raised instead of RsAtomicMoveCallFailed once too many call failures
    happen in a row without an intervening success. A single isolated
    per-card failure (a rare malformed provider response) is expected and
    safe to skip past; MAX_CONSECUTIVE_CALL_FAILURES failures in a row with
    no success between them is evidence of a systemic problem (an expired
    API key, a provider outage, a client-side bug) that would otherwise be
    silently misrecorded as thousands of individual "this card has no
    candidates" rows while burning through the entire budget. This is
    deliberately NOT caught by compile_source_card -- it must propagate and
    stop the run."""


class RsAtomicMoveCompiler:
    def __init__(
        self,
        *,
        binding: RuntimeBinding,
        price: PriceSnapshot,
        client: RsAtomicMoveClient,
        cache_root,
        attempt_ledger_root,
        budget_ledger_path,
        hard_budget_usd,
    ) -> None:
        self.binding = binding
        self.endpoint = binding.checked_endpoint
        if price.provider != binding.provider or price.region != binding.region:
            raise ValueError("price snapshot provider/region must match runtime binding")
        self.price = price
        self.client = client
        self.cache = SuccessCache(cache_root)
        # TODO(rs_atomic_move batch layer): upgrade to
        # metacom_pm.attempt_ledger.PersistentAttemptLedger once the batch
        # orchestrator (mirrors semantic_memory/batch.py) knows the full
        # expected_calls/maximum_total_attempts plan across all source cards
        # up front, as that ledger's constructor requires. This lightweight
        # append-only log covers single-card offline use in the meantime and
        # is not itself a budget or resume authority -- RsAtomicMoveBudgetLedger
        # and SuccessCache remain the fail-closed sources of truth for spend
        # and resume-without-repayment respectively.
        self.attempt_ledger_path = Path(attempt_ledger_root) / "attempts.jsonl"
        self.budget = RsAtomicMoveBudgetLedger(
            budget_ledger_path, price=price, hard_budget_usd=hard_budget_usd
        )
        # Consecutive call-failure circuit breaker (see
        # RsAtomicMoveCircuitBreakerTripped) -- reset to 0 on every success,
        # never persisted across process restarts (a resumed run starts
        # this back at 0, which is correct: the prior process's failures are
        # already durably recorded per-row in session_results.jsonl and
        # conservatively charged in the budget ledger; this counter's only
        # job is bounding damage *within* one process's run).
        self._consecutive_call_failures = 0

    @property
    def run_manifest(self) -> dict[str, object]:
        """Everything that changes what a compiled result *means*, as a
        plain, auditable dict -- not just its hash. A batch resume must bind
        every stored row to ``run_identity_sha256`` (below) so a prompt/
        schema/renderer/grounding/parameter edit cannot silently keep stale
        results (see batch.py's resume check); this dict is what a human
        reviewer reads to know what that opaque hash actually represents."""

        return {
            "runtime_binding": self.binding.identity_sha256,
            "extractor_call_parameters": self.binding.extractor.model_dump(mode="json"),
            "verifier_call_parameters": self.binding.verifier.model_dump(mode="json"),
            "extractor_prompt_sha256": EXTRACTOR_PROMPT_SHA256,
            "verifier_prompt_sha256": VERIFIER_PROMPT_SHA256,
            "extractor_schema_sha256": sha256_text(
                canonical_json(ExtractorProposalBatch.model_json_schema())
            ),
            "verifier_schema_sha256": sha256_text(
                canonical_json(VerifierDecisionBatch.model_json_schema())
            ),
            "contracts_schema_version": RS_ATOMIC_MOVE_SCHEMA_VERSION,
            "contracts_code_sha256": CONTRACTS_CODE_SHA256,
            "grounding_version": GROUNDING_VERSION,
            "source_adapter_code_sha256": SOURCE_ADAPTER_CODE_SHA256,
            "renderer_spec_sha256": RENDERER_SHA256,
            "renderer_code_sha256": RENDERER_CODE_SHA256,
            "price_snapshot": self.price.identity_sha256,
            "runtime_code_sha256": RUNTIME_CODE_SHA256,
        }

    @property
    def run_identity_sha256(self) -> str:
        return sha256_text(canonical_json(self.run_manifest))

    def _call(
        self,
        *,
        phase: str,
        source: SourceCardCompileInput,
        messages: list[dict[str, str]],
        response_schema: Type[BaseModel],
        prompt_sha256: str,
        params: CallParameters,
    ) -> BaseModel:
        payload = chat_request_payload(
            self.endpoint,
            messages,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            seed=None,
            response_schema=response_schema,
        )
        request_payload_sha256 = sha256_text(canonical_json(payload))
        schema_sha256 = sha256_text(canonical_json(response_schema.model_json_schema()))
        identity = CompilerCallIdentity(
            phase=phase,
            compiler_version=self.binding.compiler_version,
            provider=self.binding.provider,
            region=self.binding.region,
            base_url=self.endpoint.base_url,
            model=self.endpoint.model,
            enable_thinking=False,
            response_mode="json_object_plus_local_pydantic",
            request_parameters={
                "temperature": params.temperature,
                "max_tokens": params.max_tokens,
                "seed": None,
            },
            prompt_sha256=prompt_sha256,
            schema_sha256=schema_sha256,
            source_card_id=source.source_card_id,
            source_sha256=source_sha256(source),
            request_payload_sha256=request_payload_sha256,
        )
        cached = self.cache.load(identity)
        if cached is not None:
            self._consecutive_call_failures = 0
            return response_schema.model_validate(cached)

        try:
            reservation = self.budget.reserve(
                reservation_id=identity.cache_key,
                phase=phase,
                call_key=identity.cache_key,
                maximum_prompt_tokens=params.maximum_prompt_tokens,
                maximum_completion_tokens=params.max_tokens,
            )
        except RuntimeError as exc:
            if "budget reservation ID already exists" not in str(exc):
                # A genuinely different failure (e.g. hard budget would be
                # exceeded) must propagate and stop the run -- only a
                # dangling reservation from an earlier interrupted attempt
                # at this exact call is recovered here.
                raise
            # This exact call identity was already reserved by an earlier
            # process run that was interrupted before it could settle (a
            # hard process kill, not the try/except below, which always
            # settles before raising) -- reservation_id is a pure function
            # of call content, so this identity can never be reserved again.
            # The money is already conservatively counted in
            # accounted_cost_usd via that dangling RESERVED row; no new
            # settlement is needed, just recovery so this run can move past
            # the card instead of crashing on it forever.
            self._raise_call_failed(phase, cause=exc)
        try:
            result, parsed = self.client.chat(
                messages,
                temperature=params.temperature,
                max_tokens=params.max_tokens,
                seed=None,
                response_schema=response_schema,
                retries=1,
            )
        except Exception as exc:
            # The client already retried internally and still could not
            # produce a usable response (e.g. a provider response that
            # never became schema-valid JSON). Settle this reservation now,
            # crash-conservatively at the reserved maximum (usage=None), so
            # it is never left permanently dangling -- reservation_id is a
            # pure function of call content, so a bare retry of the same
            # card/phase would otherwise collide with this same identity
            # forever. The caller records this source card as a structural
            # failure and moves on; this exact call is never retried.
            #
            # This except is deliberately broad (bare Exception, not a
            # whitelist of known-transient types): a whitelist can only ever
            # be as complete as what has been seen before, and the failure
            # mode this guards against (a systemic problem -- an expired API
            # key, a provider outage, a bug in this client) is exactly the
            # kind that would raise something not yet on any whitelist.
            # Broad catching is safe here specifically because of
            # _raise_call_failed's circuit breaker below: an isolated
            # per-card issue stays isolated (skip and continue), but N
            # consecutive failures with no success between them -- which is
            # what a systemic problem looks like -- stops the whole run
            # instead of silently burning the rest of the budget recording
            # thousands of cards as "no candidates".
            self.budget.settle(reservation, usage=None, outcome="FAILED_CALL")
            append_jsonl(
                self.attempt_ledger_path,
                {
                    "protocol": "paper1-rs-atomic-move-attempt-log-v1",
                    "phase": phase,
                    "source_card_id": source.source_card_id,
                    "cache_key": identity.cache_key,
                    "outcome": "FAILED_CALL",
                    "error": str(exc),
                },
            )
            self._raise_call_failed(phase, cause=exc)
        append_jsonl(
            self.attempt_ledger_path,
            {
                "protocol": "paper1-rs-atomic-move-attempt-log-v1",
                "phase": phase,
                "source_card_id": source.source_card_id,
                "cache_key": identity.cache_key,
                "request_hash": result.request_hash,
                "finish_reason": result.normalized_finish_reason,
                "usage": result.usage,
                "latency_ms": result.latency_ms,
            },
        )
        outcome = "SUCCEEDED" if parsed is not None else "FAILED_PARSE"
        self.budget.settle(reservation, usage=result.usage, outcome=outcome)
        if parsed is None:
            self._raise_call_failed(
                phase, cause=RuntimeError(f"RS atomic-move {phase} call did not produce a parsable response")
            )
        self._consecutive_call_failures = 0
        self.cache.store_success(identity, parsed.model_dump(mode="json"))
        return parsed

    def _raise_call_failed(self, phase: str, *, cause: BaseException) -> None:
        """Increment the consecutive-failure circuit breaker and raise
        either the recoverable per-card RsAtomicMoveCallFailed (caught by
        compile_source_card) or, once MAX_CONSECUTIVE_CALL_FAILURES is
        reached with no success in between, the fatal
        RsAtomicMoveCircuitBreakerTripped (never caught, stops the run)."""

        self._consecutive_call_failures += 1
        if self._consecutive_call_failures >= MAX_CONSECUTIVE_CALL_FAILURES:
            raise RsAtomicMoveCircuitBreakerTripped(
                f"{self._consecutive_call_failures} consecutive RS atomic-move call "
                f"failures with no success in between (most recent phase={phase}); "
                "treating as a systemic failure, not isolated per-card noise. "
                f"Last cause: {cause}"
            ) from cause
        raise RsAtomicMoveCallFailed(phase, cause=cause) from cause

    def compile_source_card(self, source: SourceCardCompileInput) -> SourceCardCompileResult:
        try:
            extractor_batch = self._call(
                phase="extractor",
                source=source,
                messages=extractor_messages(
                    canonical_json(source.model_dump(mode="json")),
                    canonical_json(ExtractorProposalBatch.model_json_schema()),
                ),
                response_schema=ExtractorProposalBatch,
                prompt_sha256=EXTRACTOR_PROMPT_SHA256,
                params=self.binding.extractor,
            )
        except RsAtomicMoveCallFailed:
            return SourceCardCompileResult(call_failure_phase="extractor")
        assert isinstance(extractor_batch, ExtractorProposalBatch)

        grounded: list[ProposedAtomicMoveUnit] = []
        located_spans_by_id: dict[str, tuple] = {}
        grounding_rejections: list[GroundingResult] = []
        for proposal in extractor_batch.proposals:
            grounding_result = run_deterministic_grounding(
                proposal,
                target_dialogue_id=source.target_dialogue_id,
                target_turn_index=source.target_turn_index,
                target_turn_text=source.target_turn.text,
            )
            if grounding_result.passed:
                grounded.append(proposal)
                located_spans_by_id[proposal.proposal_id] = grounding_result.located_spans
            else:
                grounding_rejections.append(grounding_result)

        if not grounded:
            return SourceCardCompileResult(
                extractor_proposal_count=len(extractor_batch.proposals),
                structurally_invalid_proposals=len(grounding_rejections),
                grounding_rejections=tuple(grounding_rejections),
            )

        try:
            verifier_batch = self._call(
                phase="verifier",
                source=source,
                messages=verifier_messages(
                    canonical_json(source.model_dump(mode="json")),
                    canonical_json([p.model_dump(mode="json") for p in grounded]),
                    canonical_json(VerifierDecisionBatch.model_json_schema()),
                ),
                response_schema=VerifierDecisionBatch,
                prompt_sha256=VERIFIER_PROMPT_SHA256,
                params=self.binding.verifier,
            )
        except RsAtomicMoveCallFailed:
            # Grounded proposals exist but no decision was ever obtained for
            # them -- fail closed: none are accepted, and this card's
            # verifier phase is never retried (see RsAtomicMoveCallFailed).
            return SourceCardCompileResult(
                extractor_proposal_count=len(extractor_batch.proposals),
                structurally_invalid_proposals=len(grounding_rejections),
                grounding_rejections=tuple(grounding_rejections),
                call_failure_phase="verifier",
            )
        assert isinstance(verifier_batch, VerifierDecisionBatch)

        # Fail closed on anything other than an exact 1:1 correspondence
        # between the grounded proposal IDs sent to the verifier and the
        # decision IDs it returns. VerifierDecisionBatch already forbids
        # duplicate decision IDs at the schema level; this checks the
        # remaining failure modes: a decision for a proposal_id that was
        # never sent, and a grounded proposal with no decision at all.
        grounded_ids = {p.proposal_id for p in grounded}
        decided_ids = {d.proposal_id for d in verifier_batch.decisions}
        extra_ids = decided_ids - grounded_ids
        if extra_ids:
            raise RuntimeError(
                f"verifier decided proposal_id(s) that were never sent: {sorted(extra_ids)}"
            )
        missing_ids = grounded_ids - decided_ids
        if missing_ids:
            raise RuntimeError(
                f"verifier did not decide grounded proposal_id(s): {sorted(missing_ids)}"
            )

        decisions_by_id = {d.proposal_id: d for d in verifier_batch.decisions}
        accepted: list[AcceptedAtomicMoveUnit] = []
        seen_card_ids: set[str] = set()
        verifier_reject_count = 0
        duplicate_semantic_content_count = 0
        for proposal in grounded:
            decision = decisions_by_id[proposal.proposal_id]
            if not decision.accept:
                verifier_reject_count += 1
                continue
            located_spans = located_spans_by_id[proposal.proposal_id]
            rendered = render_atomic_move(proposal)
            card_identity = sha256_text(
                canonical_json(
                    {
                        "source_card_id": source.source_card_id,
                        "compiler_version": self.binding.compiler_version,
                        "atomic_move_family": proposal.atomic_move_family.value,
                        "action_description": proposal.action_description,
                        "supporting_spans": [
                            s.model_dump(mode="json") for s in located_spans
                        ],
                    }
                )
            )
            card_id = "rs_atomic_" + card_identity[:24]
            if card_id in seen_card_ids:
                # Two distinct proposal_ids produced identical semantic
                # content (same family/action_description/spans) for this
                # source card -- content-addressing means they collide by
                # design. Keep the first, drop the duplicate, and count it
                # rather than silently emitting two accepted units sharing
                # one card_id (which would violate accepted-set uniqueness).
                duplicate_semantic_content_count += 1
                continue
            seen_card_ids.add(card_id)
            accepted.append(
                AcceptedAtomicMoveUnit(
                    card_id=card_id,
                    # The proposal is mechanically anchored to target_dialogue_id
                    # (locate_spans only ever searches the target turn's own
                    # text, so a non-target grounding is structurally
                    # impossible, not just checked-and-rejected) PLUS every
                    # other dialogue whose supporter turn produced
                    # the same normalized, case-folded
                    # (retrieval_text, response) duplicate key --
                    # StrategySourceCard.source_dialogue_ids, threaded through
                    # source_adapter.py as equivalent_dialogue_ids, so
                    # leave-current-dialogue-out fold exclusion catches a card
                    # for every dialogue it is verbatim equivalent to, not
                    # just the one arbitrarily kept as representative. Never
                    # derived from the proposal itself.
                    source_dialogue_ids=tuple(
                        sorted((source.target_dialogue_id, *source.equivalent_dialogue_ids))
                    ),
                    # Locally derived from the compile input's own target
                    # identity, never from a Qwen-declared field -- Qwen no
                    # longer even carries a source_turn_index in its schema.
                    source_turn_index=source.target_turn_index,
                    atomic_move_family=proposal.atomic_move_family,
                    action_description=proposal.action_description,
                    supporting_spans=located_spans,
                    rendered_card_text=rendered,
                    rendered_card_text_sha256=sha256_text(rendered),
                    renderer_version=RENDERER_VERSION,
                    compiler_version=self.binding.compiler_version,
                    extractor_prompt_sha256=EXTRACTOR_PROMPT_SHA256,
                    extractor_response_sha256=sha256_text(
                        canonical_json(proposal.model_dump(mode="json"))
                    ),
                    verifier_prompt_sha256=VERIFIER_PROMPT_SHA256,
                    verifier_response_sha256=sha256_text(
                        canonical_json(decision.model_dump(mode="json"))
                    ),
                )
            )

        return SourceCardCompileResult(
            accepted_units=tuple(accepted),
            structurally_invalid_proposals=len(grounding_rejections),
            grounding_rejections=tuple(grounding_rejections),
            verifier_rejections=verifier_reject_count,
            extractor_proposal_count=len(extractor_batch.proposals),
            duplicate_semantic_content_count=duplicate_semantic_content_count,
        )
