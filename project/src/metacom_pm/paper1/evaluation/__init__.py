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
from .formal_schedule import (
    CANONICAL_DG_ARMS,
    FORMAL_MISTRAL_SCHEDULE_PROTOCOL,
    build_arm_balanced_schedule,
)
from .rq1 import RQ1InputCard, RQ1RunCell, build_rq1_run_cells, load_rq1_cards
from .pairwise_teacher import (
    PAIRWISE_TEACHER_PROTOCOL,
    ParsedTeacherVerdict,
    build_pairwise_teacher_prompt,
    pairwise_teacher_identity_payload,
    parse_pairwise_teacher_response,
)

__all__ = [
    "TokenPricing",
    "ClientLatencyObservation",
    "ClientLatencySummary",
    "CANONICAL_DG_ARMS",
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
    "FORMAL_MISTRAL_SCHEDULE_PROTOCOL",
    "build_arm_balanced_schedule",
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
    "PAIRWISE_TEACHER_PROTOCOL",
    "ParsedTeacherVerdict",
    "build_pairwise_teacher_prompt",
    "pairwise_teacher_identity_payload",
    "parse_pairwise_teacher_response",
]
