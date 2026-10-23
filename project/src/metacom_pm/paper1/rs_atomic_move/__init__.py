"""Standalone RS atomic-move compiler: ESConv supporter turns -> structured,
fold-safe atomic support-move cards.

Independent of ``paper1.semantic_memory`` (MP/MS/ME). Live calls are
separately authorization- and budget-gated; nothing here is authorized to
call a paid API on its own.
"""

from .authorization import (
    FULL_CATALOG_SIZE,
    FULL_SCOPE,
    SMOKE_MAXIMUM_CARDS,
    SMOKE_SCOPE,
    LiveCompilerAuthorization,
    load_live_authorization,
)
from .batch import run_source_card_prefix
from .catalog import (
    AtomicMoveRetrievalDocument,
    build_atomic_move_retrieval_document,
    load_atomic_move_retrieval_documents,
)
from .contracts import (
    CONTRACTS_CODE_SHA256,
    RS_ATOMIC_MOVE_SCHEMA_VERSION,
    AcceptedAtomicMoveUnit,
    AtomicMoveFamily,
    ExtractorProposalBatch,
    ProposedAtomicMoveUnit,
    ProposedSpanQuote,
    SourceCardCompileInput,
    SupportingSpan,
    VerifierDecidableRejectionReason,
    VerifierDecision,
    VerifierDecisionBatch,
    VerifierRejectionReason,
    fold_exclusion_dialogue_ids,
)
from .grounding import (
    GROUNDING_VERSION,
    GroundingResult,
    check_action_description_not_leaking,
    locate_spans,
    run_deterministic_grounding,
)
from .renderer import (
    RENDERER_CODE_SHA256,
    RENDERER_SHA256,
    RENDERER_VERSION,
    UnscrubbedActionDescriptionError,
    render_atomic_move,
)
from .runtime import (
    MAX_CONSECUTIVE_CALL_FAILURES,
    CallParameters,
    RsAtomicMoveCallFailed,
    RsAtomicMoveCircuitBreakerTripped,
    RsAtomicMoveCompiler,
    RuntimeBinding,
    SourceCardCompileResult,
)
from .source_adapter import SOURCE_ADAPTER_CODE_SHA256, build_source_card_compile_input, load_esconv_data
from .zero_outcome_census import (
    RS_ATOMIC_MOVE_CENSUS_ROW_PROTOCOL,
    BgeAuditIndex,
    RSAtomicMoveCensusRow,
    build_rs_atomic_move_zero_outcome_census,
)

__all__ = [
    "FULL_CATALOG_SIZE",
    "FULL_SCOPE",
    "SMOKE_MAXIMUM_CARDS",
    "SMOKE_SCOPE",
    "LiveCompilerAuthorization",
    "load_live_authorization",
    "CONTRACTS_CODE_SHA256",
    "RS_ATOMIC_MOVE_SCHEMA_VERSION",
    "AcceptedAtomicMoveUnit",
    "AtomicMoveFamily",
    "ExtractorProposalBatch",
    "ProposedAtomicMoveUnit",
    "ProposedSpanQuote",
    "SourceCardCompileInput",
    "SupportingSpan",
    "VerifierDecidableRejectionReason",
    "VerifierDecision",
    "VerifierDecisionBatch",
    "VerifierRejectionReason",
    "fold_exclusion_dialogue_ids",
    "GROUNDING_VERSION",
    "GroundingResult",
    "check_action_description_not_leaking",
    "locate_spans",
    "run_deterministic_grounding",
    "RENDERER_CODE_SHA256",
    "RENDERER_SHA256",
    "RENDERER_VERSION",
    "UnscrubbedActionDescriptionError",
    "render_atomic_move",
    "CallParameters",
    "RsAtomicMoveCompiler",
    "RuntimeBinding",
    "SourceCardCompileResult",
    "RsAtomicMoveCallFailed",
    "RsAtomicMoveCircuitBreakerTripped",
    "MAX_CONSECUTIVE_CALL_FAILURES",
    "SOURCE_ADAPTER_CODE_SHA256",
    "build_source_card_compile_input",
    "load_esconv_data",
    "run_source_card_prefix",
    "AtomicMoveRetrievalDocument",
    "build_atomic_move_retrieval_document",
    "load_atomic_move_retrieval_documents",
    "RS_ATOMIC_MOVE_CENSUS_ROW_PROTOCOL",
    "BgeAuditIndex",
    "RSAtomicMoveCensusRow",
    "build_rs_atomic_move_zero_outcome_census",
]
