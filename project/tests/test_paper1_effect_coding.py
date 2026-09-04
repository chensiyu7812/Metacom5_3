from fractions import Fraction
import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.contracts import PairedOutcome, TaskType
from metacom_pm.paper1.evaluation.effect_coding import (
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


PROJECT = Path(__file__).resolve().parents[1]


def _esc(
    overall: int,
    *,
    empathy: int = 3,
    information: int = 3,
) -> EscEffectSurface:
    return EscEffectSurface(
        empathy=empathy,
        information=information,
        expression=3,
        fluency=3,
        skillful=3,
        humanoid=3,
        overall=overall,
    )


def _qa(judge: int, f1: float, bert: float) -> QaEffectSurface:
    return QaEffectSurface(llm_as_judge=judge, f1=f1, bert_score=bert)


def _summary(
    ref: int,
    generated: int,
    recalled: int,
    llm: int,
    *,
    rouge: tuple[float, float, float] = (0.5, 0.5, 0.5),
) -> SummaryEffectSurface:
    return SummaryEffectSurface(
        rouge_1=rouge[0],
        rouge_2=rouge[1],
        rouge_l=rouge[2],
        reference_events=ref,
        generated_events=generated,
        recalled_events=recalled,
        llm_score=llm,
    )


def _dg(weight_used: int, *, lt: int = 3, per: int = 3, es: int = 3) -> DgEffectSurface:
    used_count = {0: 0, 1: 1, 2: 1, 3: 2}[weight_used]
    fully_relevant_used = int(weight_used >= 2)
    return DgEffectSurface(
        scored_observation_count=2,
        used_observation_count=used_count,
        fully_relevant_total=1,
        fully_relevant_used=fully_relevant_used,
        relevance_weight_total=3,
        relevance_weight_used=weight_used,
        long_term_memory=lt,
        personalization=per,
        emotional_support=es,
    )


@pytest.mark.parametrize(
    ("outcome", "enters", "target"),
    [
        (PairedOutcome.ON_BETTER, True, 1.0),
        (PairedOutcome.OFF_BETTER, True, 0.0),
        (PairedOutcome.EQUIVALENT, True, 0.0),
        (PairedOutcome.UNCERTAIN, False, None),
    ],
)
def test_pairwise_verdict_preserves_outcome_and_training_semantics(outcome, enters, target):
    decision = code_esc_pairwise_effect(
        _esc(3),
        _esc(3),
        pairwise_verdict=outcome,
    )
    assert decision.task_type is TaskType.ESC_RESPONSE
    assert decision.outcome is outcome
    assert decision.enters_training_likelihood is enters
    assert decision.binary_target == target


def test_invalid_requires_and_preserves_a_mechanical_reason():
    with pytest.raises(ValueError):
        code_esc_pairwise_effect(
            _esc(3),
            _esc(3),
            pairwise_verdict=PairedOutcome.INVALID,
        )
    decision = code_qa_effect(
        _qa(2, 1.0, 1.0),
        _qa(0, 0.0, 0.0),
        pairwise_verdict=PairedOutcome.ON_BETTER,
        invalid_reasons=(
            MechanicalInvalidReason.WRONG_OWNER,
            MechanicalInvalidReason.IDENTITY_MISMATCH,
        ),
    )
    assert decision.outcome is PairedOutcome.INVALID
    assert decision.binary_target is None
    assert decision.reason_code == (
        "mechanically_invalid:arm_seed_prompt_candidate_identity_mismatch,wrong_owner"
    )
    with pytest.raises(ValueError, match="closed mechanical integrity enum"):
        code_qa_effect(
            _qa(2, 1.0, 1.0),
            _qa(0, 0.0, 0.0),
            pairwise_verdict=PairedOutcome.ON_BETTER,
            invalid_reasons=("semantic_nonuse",),  # type: ignore[arg-type]
        )
    with pytest.raises(ValidationError, match="non-mechanical"):
        PairedEffectDecision(
            task_type=TaskType.QA,
            outcome=PairedOutcome.INVALID,
            reason_code="mechanically_invalid:semantic_nonuse",
        )


def test_qa_semantic_judge_is_primary_and_continuous_metrics_are_explanatory():
    assert code_qa_effect(
        _qa(2, 0.2, 0.3),
        _qa(1, 0.9, 0.9),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    ).outcome is PairedOutcome.ON_BETTER
    assert code_qa_effect(
        _qa(0, 0.9, 0.9),
        _qa(1, 0.2, 0.3),
        pairwise_verdict=PairedOutcome.OFF_BETTER,
    ).outcome is PairedOutcome.OFF_BETTER
    assert code_qa_effect(
        _qa(2, 0.9, 0.9),
        _qa(1, 0.2, 0.3),
        pairwise_verdict=PairedOutcome.EQUIVALENT,
    ).outcome is PairedOutcome.EQUIVALENT


def test_qa_marks_primary_pairwise_conflict_uncertain():
    decision = code_qa_effect(
        _qa(2, 0.2, 0.9),
        _qa(1, 0.8, 0.9),
        pairwise_verdict=PairedOutcome.OFF_BETTER,
    )
    assert decision.outcome is PairedOutcome.UNCERTAIN


def test_qa_equal_judge_uses_gold_pairwise_teacher_not_metric_epsilon():
    assert code_qa_effect(
        _qa(1, 0.8, 0.9),
        _qa(1, 0.4, 0.3),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    ).outcome is PairedOutcome.ON_BETTER
    assert code_qa_effect(
        _qa(1, 0.4, 0.9),
        _qa(1, 0.8, 0.3),
        pairwise_verdict=None,
    ).outcome is PairedOutcome.UNCERTAIN
    assert code_qa_effect(
        _qa(1, 0.4, 0.3),
        _qa(1, 0.4, 0.3),
        pairwise_verdict=PairedOutcome.EQUIVALENT,
    ).outcome is PairedOutcome.EQUIVALENT


def test_esc_uses_overall_without_one_step_empathy_information_vetoes():
    assert code_esc_pairwise_effect(
        _esc(3),
        _esc(2),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    ).outcome is PairedOutcome.ON_BETTER
    restrained_but_overall_better = code_esc_pairwise_effect(
        _esc(3, empathy=2),
        _esc(2, empathy=3),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    )
    assert restrained_but_overall_better.outcome is PairedOutcome.ON_BETTER
    assert code_esc_pairwise_effect(
        _esc(3, empathy=2),
        _esc(2, empathy=3),
        pairwise_verdict=PairedOutcome.EQUIVALENT,
    ).outcome is PairedOutcome.EQUIVALENT


def test_summary_event_f1_is_exact_and_validated():
    surface = _summary(3, 2, 2, 4)
    assert surface.event_f1 == Fraction(4, 5)
    assert surface.event_precision == Fraction(1, 1)
    assert surface.event_recall == Fraction(2, 3)
    with pytest.raises(ValidationError):
        _summary(1, 2, 2, 4)


def test_summary_reference_extraction_disagreement_is_uncertain():
    decision = code_summary_effect(
        _summary(3, 2, 2, 4),
        _summary(4, 2, 2, 4),
        pairwise_verdict=PairedOutcome.EQUIVALENT,
    )
    assert decision.outcome is PairedOutcome.UNCERTAIN
    assert decision.reason_code == "summary_reference_event_extraction_disagrees"


def test_summary_event_f1_is_primary_with_semantic_guard_and_tie_evidence():
    assert code_summary_effect(
        _summary(3, 2, 2, 4),
        _summary(3, 2, 1, 4),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    ).outcome is PairedOutcome.ON_BETTER
    assert code_summary_effect(
        _summary(3, 2, 2, 2),
        _summary(3, 2, 1, 5),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    ).outcome is PairedOutcome.UNCERTAIN
    assert code_summary_effect(
        _summary(3, 2, 1, 5),
        _summary(3, 2, 1, 4),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    ).outcome is PairedOutcome.ON_BETTER
    assert code_summary_effect(
        _summary(3, 2, 1, 4),
        _summary(3, 2, 1, 4),
        pairwise_verdict=PairedOutcome.EQUIVALENT,
    ).outcome is PairedOutcome.EQUIVALENT
    assert code_summary_effect(
        _summary(3, 2, 2, 4),
        _summary(3, 2, 1, 4),
        pairwise_verdict=None,
    ).outcome is PairedOutcome.UNCERTAIN
    assert code_summary_effect(
        _summary(3, 2, 2, 4),
        _summary(3, 2, 1, 4),
        pairwise_verdict=PairedOutcome.EQUIVALENT,
    ).outcome is PairedOutcome.EQUIVALENT


def test_dg_builder_reproduces_first_five_turn_observation_aggregation():
    surface = build_dg_effect_surface(
        [
            DgObservationJudgement(observation_id="a", turn=1, relevance=3, used=True),
            DgObservationJudgement(observation_id="a", turn=2, relevance=2, used=False),
            DgObservationJudgement(observation_id="a", turn=3, relevance=1, used=False),
            DgObservationJudgement(observation_id="a", turn=4, relevance=1, used=False),
            DgObservationJudgement(observation_id="a", turn=5, relevance=1, used=False),
            DgObservationJudgement(observation_id="a", turn=6, relevance=3, used=True),
        ],
        expected_observation_ids=("a",),
        long_term_memory=4,
        personalization=3,
        emotional_support=5,
    )
    assert surface.fully_relevant_total == 1
    assert surface.observation_recall == Fraction(1, 1)
    assert surface.weighted_score == Fraction(2, 3)


def test_dg_builder_rejects_duplicate_observation_identity():
    repeated = DgObservationJudgement(observation_id="a", turn=1, relevance=3, used=True)
    with pytest.raises(ValueError):
        build_dg_effect_surface(
            [repeated, repeated],
            expected_observation_ids=("a",),
            long_term_memory=3,
            personalization=3,
            emotional_support=3,
        )


def test_dg_builder_rejects_missing_official_turn_observation_rows():
    with pytest.raises(ValueError, match="incomplete DG observation grid"):
        build_dg_effect_surface(
            [DgObservationJudgement(observation_id="a", turn=1, relevance=3, used=True)],
            expected_observation_ids=("a",),
            long_term_memory=3,
            personalization=3,
            emotional_support=3,
        )


def test_dg_surface_rejects_internally_inconsistent_aggregate():
    with pytest.raises(ValidationError, match="inconsistent"):
        DgEffectSurface(
            scored_observation_count=1,
            used_observation_count=1,
            fully_relevant_total=1,
            fully_relevant_used=1,
            relevance_weight_total=1,
            relevance_weight_used=1,
            long_term_memory=3,
            personalization=3,
            emotional_support=3,
        )
    with pytest.raises(ValidationError, match="partially-relevant"):
        DgEffectSurface(
            scored_observation_count=2,
            used_observation_count=1,
            fully_relevant_total=1,
            fully_relevant_used=0,
            relevance_weight_total=2,
            relevance_weight_used=1,
            long_term_memory=3,
            personalization=3,
            emotional_support=3,
        )


def test_dg_uses_local_utilization_with_pairwise_correctness_guard():
    assert code_dg_effect(
        _dg(2), _dg(1), pairwise_verdict=PairedOutcome.ON_BETTER
    ).outcome is PairedOutcome.ON_BETTER
    assert code_dg_effect(
        _dg(3, lt=2), _dg(2, lt=4), pairwise_verdict=PairedOutcome.OFF_BETTER
    ).outcome is PairedOutcome.UNCERTAIN
    assert code_dg_effect(
        _dg(2, lt=4, per=4, es=3),
        _dg(2, lt=3, per=3, es=3),
        pairwise_verdict=PairedOutcome.ON_BETTER,
    ).outcome is PairedOutcome.ON_BETTER
    assert code_dg_effect(
        _dg(2), _dg(2), pairwise_verdict=PairedOutcome.EQUIVALENT
    ).outcome is PairedOutcome.EQUIVALENT
    assert code_dg_effect(
        _dg(2), _dg(1), pairwise_verdict=PairedOutcome.EQUIVALENT
    ).outcome is PairedOutcome.EQUIVALENT


def test_scorer_surface_audit_is_zero_outcome_and_portable():
    path = PROJECT / "data/paper1_authority/paper1_official_scorer_surface_audit_v1.json"
    audit = json.loads(path.read_text(encoding="utf-8"))
    assert audit["outcome_calls"] == 0
    assert audit["training_calls"] == 0
    assert audit["coding_contract"]["empirical_margin_or_pass_gate"] is False
    assert audit["effect_surfaces"]["dialogue_generation"]["observation_aggregation_turns"] == [1, 2, 3, 4, 5]
    for repository in audit["official_sources"].values():
        for source in repository["files"]:
            assert not Path(source["repo_relative_path"]).is_absolute()
            assert len(source["sha256"]) == 64
    rendered = json.dumps(audit, ensure_ascii=False)
    assert "/home/tokkio" not in rendered
