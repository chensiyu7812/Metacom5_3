"""Official outcome and objective-efficiency adapters for Paper 1."""

from .cost import TokenPricing, build_cost_record
from .client_latency import (
    ClientLatencyObservation,
    ClientLatencySummary,
    InterleavedLatencyScheduleRow,
    build_interleaved_latency_schedule,
    summarize_client_latency,
)
from .effect_coding import (
    DgEffectSurface,
    DgObservationJudgement,
    EscEffectSurface,
    MechanicalInvalidReason,
    PairedEffectDecision,
    QaEffectSurface,
    SummaryEffectSurface,
    build_dg_effect_surface,
    code_dg_effect,
    code_esc_pairwise_effect,
    code_qa_effect,
    code_summary_effect,
)
from .official import (
    build_official_outcome,
    normalized_official_primary_quality,
    official_metric_names,
)
from .decision_correctness import (
    DecisionCorrectnessReport,
    DecisionCorrectnessRow,
    evaluate_decision_correctness,
)
from .rq1 import RQ1InputCard, RQ1RunCell, build_rq1_run_cells, load_rq1_cards

__all__ = [
    "TokenPricing",
    "ClientLatencyObservation",
    "ClientLatencySummary",
    "DgEffectSurface",
    "DgObservationJudgement",
    "DecisionCorrectnessReport",
    "DecisionCorrectnessRow",
    "EscEffectSurface",
    "MechanicalInvalidReason",
    "PairedEffectDecision",
    "QaEffectSurface",
    "SummaryEffectSurface",
    "InterleavedLatencyScheduleRow",
    "build_cost_record",
    "build_interleaved_latency_schedule",
    "build_dg_effect_surface",
    "build_official_outcome",
    "build_rq1_run_cells",
    "code_dg_effect",
    "code_esc_pairwise_effect",
    "code_qa_effect",
    "code_summary_effect",
    "evaluate_decision_correctness",
    "load_rq1_cards",
    "normalized_official_primary_quality",
    "official_metric_names",
    "summarize_client_latency",
    "RQ1InputCard",
    "RQ1RunCell",
]
