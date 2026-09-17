"""Historical v7/v8/v9 semantic-memory compiler contracts and runtime.

This package preserves engineering provenance for the superseded ontology in
which MS meant atomic continuity and ME meant only action/outcome. New Paper-1
artifacts must use :mod:`metacom_pm.paper1.multi_view_memory`.
"""

HISTORICAL_ONLY = True

from .contracts import (
    AcceptedSemanticMemoryUnit,
    ExtractorSessionOutput,
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    MSContinuityType,
    MemoryClass,
    MemorySubtype,
    SessionCompileInput,
    TemporalStatus,
    VerifierDecision,
    VerifierSessionOutput,
)

__all__ = [
    "AcceptedSemanticMemoryUnit",
    "ExtractorSessionOutput",
    "MEHistoricalOutcomeType",
    "MPProfileFieldType",
    "MSContinuityType",
    "MemoryClass",
    "MemorySubtype",
    "SessionCompileInput",
    "TemporalStatus",
    "VerifierDecision",
    "VerifierSessionOutput",
]
