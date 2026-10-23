import pytest

from metacom_pm.paper1.evaluation.teacher_diagnostics import (
    clustered_agreement_interval, compare_verdicts, index_presentations, reference_comparison, reversal_consistency,
)


def row(pid, base, ref, candidate, *, reverse=False, a_arm="ON"):
    return {"presentation_id": pid, "base_pair_id": base, "task": "QA",
            "reference_verdict": ref, "candidate_verdict": candidate,
            "reverse_duplicate": reverse, "A_arm": a_arm}


def test_missing_candidate_is_not_a_matching_uncertain_verdict():
    result = compare_verdicts([row("p", "b", "uncertain", None)])
    assert result["scheduled"] == result["missing"] == 1
    assert result["observed"] == result["exact_matches"] == 0
    assert result["exact_agreement"] is None


def test_base_denominator_excludes_reversals_and_retains_uncertain_reference():
    rows = [row("a", "b", "A_better", "A_better"),
            row("r", "b", "B_better", "A_better", reverse=True, a_arm="OFF"),
            row("c", "c", "uncertain", "equivalent")]
    result = reference_comparison(list(reversed(rows)))
    assert result["base_pairs"]["observed"] == 2
    assert result["base_pairs"]["exact_agreement"] == 0.5
    assert result["all_presentations_descriptive"]["observed"] == 3
    assert result["reference_reversal"]["rate"] == 1
    assert result["candidate_reversal"]["rate"] == 0


def test_macro_recall_does_not_invent_absent_classes_or_exclude_candidate_uncertain():
    result = compare_verdicts([row("a", "a", "equivalent", "uncertain"),
                               row("b", "b", "equivalent", "equivalent")])
    assert result["recall_by_observed_reference_class"]["equivalent"] == 0.5
    assert result["macro_recall_decisive_equivalent_present_classes"] == 0.5
    assert result["macro_recall_classes_present"] == 1
    assert result["candidate_A_fraction_among_decisive"] is None


def test_duplicate_presentations_cannot_double_the_sample():
    r = row("a", "b", "equivalent", "equivalent")
    with pytest.raises(ValueError, match="duplicate"):
        index_presentations([r, r])


def test_reversal_orientation_is_validated():
    rows = [row("a", "b", "equivalent", "equivalent"),
            row("r", "b", "equivalent", "equivalent", reverse=True)]
    with pytest.raises(ValueError, match="swap"):
        reversal_consistency(rows, "candidate_verdict")


def test_noncontract_verdict_cannot_enter_counts():
    with pytest.raises(ValueError, match="vocabulary"):
        compare_verdicts([row("a", "b", "equivalent", "invalid")])


def test_cluster_bootstrap_excludes_reversals_and_reproduces_uncertainty():
    rows = [{**row("a", "a", "equivalent", "equivalent"), "cluster_id": "owner1"},
            {**row("b", "b", "A_better", "B_better"), "cluster_id": "owner2"},
            {**row("r", "a", "equivalent", "equivalent", reverse=True, a_arm="OFF"), "cluster_id": "owner1"}]
    result = clustered_agreement_interval(rows)
    assert result["clusters"] == result["observed_base_pairs"] == 2
    assert result["interval"] == [0.0, 1.0]
    assert result == clustered_agreement_interval(list(reversed(rows)))
    assert clustered_agreement_interval(rows[:1])["interval"] is None


def test_bootstrap_never_infers_an_independent_cluster_from_presentation_id():
    with pytest.raises(ValueError, match="source-bound"):
        clustered_agreement_interval([row("a", "a", "equivalent", "equivalent")])
