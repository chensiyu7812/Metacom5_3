"""Researcher-authorized verifier-only v9 DEV runtime with a USD 0.25 cap."""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from pydantic import Field, model_validator

from metacom_pm.api import Endpoint
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import StrictContract

from .budget import PriceSnapshot, SemanticCompilerBudgetLedger
from .cache import SuccessCache
from .contracts import ExtractorSessionOutput, SHA256_PATTERN, SchemaRejectedItem, SessionCompileInput
from .evidence_v9 import (
    DeterministicV9Decision,
    METypedEvidenceV9,
    MPTypedEvidenceV9,
    MSTypedEvidenceV9,
    V9_DETERMINISTIC_GATE_VERSION,
    V9_EVIDENCE_SCHEMA_VERSION,
    V9_VERIFIER_PROMPT_SHA256,
    V9EvidenceSessionOutput,
    V9EvidenceWireSessionOutput,
    v9_verifier_messages,
)
from .grounding import validate_output_binding, validate_proposal_grounding
from .runtime import CallParameters, FROZEN_QWEN_MODEL, SemanticCompilerClient, SemanticMemoryCompiler
from .runtime_v9_dev import (
    LOCAL_BINDING_VERSION_V9_DEV,
    deterministic_v9_decision,
    strict_v9_output,
)


COMPILER_VERSION_V9_LIVE = "paper1-qwen-semantic-memory-verifier-v9-dev-live"
V9_DEV_HARD_BUDGET_USD = Decimal("0.25")
V9_DEV_SCOPE = "OLD_DEV_32_ITEMS_IN_29_SOURCE_SESSIONS_ONLY"


def _schema_sha256(value: object) -> str:
    return sha256_text(canonical_json(value))


V9_VERIFIER_SCHEMA_SHA256 = _schema_sha256(
    {
        "wire_envelope": V9EvidenceWireSessionOutput.model_json_schema(),
        "strict_output": V9EvidenceSessionOutput.model_json_schema(),
        "strict_mp": MPTypedEvidenceV9.model_json_schema(),
        "strict_ms": MSTypedEvidenceV9.model_json_schema(),
        "strict_me": METypedEvidenceV9.model_json_schema(),
    }
)


class RuntimeBindingV9Dev(StrictContract):
    provider: str = "Alibaba Cloud Model Studio"
    region: str = Field(min_length=1)
    endpoint: Endpoint
    verifier: CallParameters
    compiler_version: str = COMPILER_VERSION_V9_LIVE

    @property
    def checked_endpoint(self) -> Endpoint:
        endpoint = self.endpoint
        if self.provider != "Alibaba Cloud Model Studio":
            raise ValueError("v9 DEV provider must remain Alibaba Cloud Model Studio")
        if self.compiler_version != COMPILER_VERSION_V9_LIVE:
            raise ValueError(f"v9 DEV compiler version must be {COMPILER_VERSION_V9_LIVE}")
        if endpoint.model != FROZEN_QWEN_MODEL:
            raise ValueError(f"v9 DEV model must remain {FROZEN_QWEN_MODEL}")
        if endpoint.transport != "openai_chat_completions":
            raise ValueError("v9 DEV requires the frozen OpenAI-compatible transport")
        if endpoint.supports_strict_json_schema:
            raise ValueError("v9 DEV uses JSON-object mode plus local strict validation")
        if endpoint.enable_thinking is not False:
            raise ValueError("v9 DEV must explicitly disable thinking")
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
                    "evidence_schema_version": V9_EVIDENCE_SCHEMA_VERSION,
                    "deterministic_gate_version": V9_DETERMINISTIC_GATE_VERSION,
                    "local_binding_version": LOCAL_BINDING_VERSION_V9_DEV,
                    "verifier_prompt_sha256": V9_VERIFIER_PROMPT_SHA256,
                    "verifier_schema_sha256": V9_VERIFIER_SCHEMA_SHA256,
                    "scope": V9_DEV_SCOPE,
                }
            )
        )


class V9DevBudgetLedger(SemanticCompilerBudgetLedger):
    def __init__(self, path: str | Path, *, price: PriceSnapshot) -> None:
        self.path = Path(path)
        self.price = price
        self.hard_budget_usd = V9_DEV_HARD_BUDGET_USD
        self._events: dict[str, list[dict[str, Any]]] = {}
        self._load()


class V9DevAuthorization(StrictContract):
    protocol: Literal["paper1-semantic-memory-v9-dev-live-authorization-v1"]
    status: Literal["RESEARCHER_AUTHORIZED"]
    approval_date: Literal["2026-09-02"]
    scope: Literal[V9_DEV_SCOPE]
    authorized_model: Literal[FROZEN_QWEN_MODEL]
    maximum_source_sessions: Literal[29]
    maximum_items: Literal[32]
    maximum_provider_calls: Literal[29]
    hard_budget_usd: Decimal
    runtime_binding_sha256: str = Field(pattern=SHA256_PATTERN)
    runner_sha256: str = Field(pattern=SHA256_PATTERN)
    live_runtime_module_sha256: str = Field(pattern=SHA256_PATTERN)
    offline_gate_module_sha256: str = Field(pattern=SHA256_PATTERN)
    frozen_package_sha256: str = Field(pattern=SHA256_PATTERN)
    package_report_sha256: str = Field(pattern=SHA256_PATTERN)
    price_snapshot_sha256: str = Field(pattern=SHA256_PATTERN)
    all_four_outcome_locks_closed: Literal[True]
    full_401_compile_authorized: Literal[False]
    stop_after_dev_for_researcher_review: Literal[True]
    outcome_calls: Literal[0]

    @model_validator(mode="after")
    def exact_dev_cap(self) -> "V9DevAuthorization":
        if self.hard_budget_usd != V9_DEV_HARD_BUDGET_USD:
            raise ValueError("v9 DEV authorization hard cap must be exactly USD 0.25")
        return self


class SemanticMemoryV9DevVerifier(SemanticMemoryCompiler):
    def __init__(
        self, *, binding: RuntimeBindingV9Dev, price: PriceSnapshot,
        client: SemanticCompilerClient, cache_root: str | Path,
        attempt_ledger_root: str | Path, budget_ledger_path: str | Path,
    ) -> None:
        self.binding = binding
        self.endpoint = binding.checked_endpoint
        if price.provider != binding.provider or price.region != binding.region:
            raise ValueError("price snapshot provider/region must match v9 DEV binding")
        self.price = price
        self.client = client
        self.cache = SuccessCache(cache_root)
        self.attempt_ledger_root = Path(attempt_ledger_root)
        self.budget = V9DevBudgetLedger(budget_ledger_path, price=price)

    def compile_session(self, source: SessionCompileInput):  # pragma: no cover
        raise RuntimeError("v9 DEV runtime cannot compile the 401-session catalog")

    def verify_existing_proposals(
        self, *, source: SessionCompileInput, extractor: ExtractorSessionOutput,
    ) -> tuple[V9EvidenceSessionOutput, tuple[SchemaRejectedItem, ...], tuple[DeterministicV9Decision, ...]]:
        validate_output_binding(source, extractor)
        invalid = [
            item.proposal_id
            for item in (validate_proposal_grounding(source, proposal) for proposal in extractor.proposals)
            if not item.valid
        ]
        if invalid:
            raise ValueError(f"v9 DEV proposals are not structurally grounded: {invalid}")
        call = self._call(
            phase="verifier",
            source=source,
            messages=v9_verifier_messages(
                canonical_json(source.model_dump(mode="json")),
                canonical_json(extractor.model_dump(mode="json")),
                canonical_json(V9EvidenceSessionOutput.model_json_schema()),
            ),
            response_schema=V9EvidenceWireSessionOutput,
            parameters=self.binding.verifier,
            prompt_sha256=V9_VERIFIER_PROMPT_SHA256,
            schema_sha256_override=V9_VERIFIER_SCHEMA_SHA256,
        )
        wire = V9EvidenceWireSessionOutput.model_validate(call.parsed)
        if wire.owner_id != source.owner_id or wire.session_id != source.session_id:
            raise ValueError("v9 evidence owner/session binding mismatch")
        strict, rejected = strict_v9_output(wire, extractor=extractor)
        proposal_by_id = {item.proposal_id: item for item in extractor.proposals}
        decisions = tuple(
            deterministic_v9_decision(source, proposal_by_id[item.proposal_id], item)
            for item in strict.evidence
        )
        return strict, rejected, decisions
