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
from metacom_pm.io import append_jsonl, canonical_json, sha256_text
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


def source_sha256(source: SourceCardCompileInput) -> str:
    return sha256_text(canonical_json(source.model_dump(mode="json")))


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
            return response_schema.model_validate(cached)

        reservation = self.budget.reserve(
            reservation_id=identity.cache_key,
            phase=phase,
            call_key=identity.cache_key,
            maximum_prompt_tokens=params.maximum_prompt_tokens,
            maximum_completion_tokens=params.max_tokens,
        )
        result, parsed = self.client.chat(
            messages,
            temperature=params.temperature,
            max_tokens=params.max_tokens,
            seed=None,
            response_schema=response_schema,
            retries=1,
        )
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
            raise RuntimeError(f"RS atomic-move {phase} call did not produce a parsable response")
        self.cache.store_success(identity, parsed.model_dump(mode="json"))
        return parsed

    def compile_source_card(self, source: SourceCardCompileInput) -> SourceCardCompileResult:
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
