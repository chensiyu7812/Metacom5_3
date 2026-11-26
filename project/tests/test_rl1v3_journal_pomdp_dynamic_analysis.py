"""Missing counterfactuals and shared uncertainty must not become task labels."""
import os
from pathlib import Path
import pytest
from metacom_pm.rl1v3.journal.pomdp_dynamic_analysis import paired, group_summary, quantile, analyze


def row(value, seconds=2, payload='a', text='a', method='STOP'):
    return dict(task='T01', method=method, completion_interval=value,
        completion_status='not_evaluated' if value is None else 'uncertain' if value==[0,1] else 'complete' if value==[1,1] else 'incomplete',
        technical_status='unexecuted' if seconds is None else 'returned_eos',
        payload_sha256=payload, text_sha256=text,
        agent_wall_ns=None if seconds is None else seconds * 10**9,
        pm_ns=None, guard_ns=None, controller_generation_ns=None)


def test_missing_terminal_has_no_semantic_difference_or_fake_zero_latency():
    result=paired(row(None,None,None,None),row([0,0]))
    assert result['stratum']=='missing_terminal_or_review'
    assert result['completion_difference_interval'] is None
    assert result['agent_wall_difference_ns'] is None


def test_shared_same_output_ambiguity_cancels_but_actual_times_do_not():
    result=paired(row([0,1],3),row([0,1],2))
    assert result['completion_difference_interval']==[0,0]
    assert result['agent_wall_difference_ns']==10**9


def test_inconsistent_identical_evidence_review_rejected():
    with pytest.raises(ValueError,match='inconsistent'):
        paired(row([1,1]),row([0,1]))


def test_independent_uncertain_evidence_is_not_forced_failure():
    result=paired(row([0,1],payload='other'),row([1,1]))
    assert result['completion_difference_interval']==[-1,0]
    assert result['stratum']=='semantic_uncertainty'


def test_failure_is_not_excluded_from_denominator_or_time_imputed():
    result=group_summary([row([1,1]),row(None,None,None,None)])
    assert result['slots']==2 and result['evaluated']==1 and result['missing_quality']==1
    assert result['completion_interval_observed']==[1,1]
    assert result['agent_wall_observations']==1


def test_small_sample_p95_is_max_and_empty_is_missing():
    assert quantile([1,2,3,4,5,6],.95)==6
    assert quantile([], .95) is None


def test_entirely_unexecuted_group_has_missing_quality_and_time():
    result=group_summary([row(None,None,None,None)])
    assert result['completion_interval_observed'] is None
    assert result['pm_ns_sum_observed'] is None
    assert result['agent_wall_sum_ns'] is None


def test_actual_48_slot_join_keeps_incomplete_pairs_out_of_common_denominator(tmp_path):
    location=os.environ.get('POMDP_DYNAMIC_RESULTS_PRIVATE')
    if not location:
        pytest.skip('requires private actual outputs and frozen development review; no model access')
    root=Path(location)
    result=analyze(root/'collection-final-v1',root/'quality/review-v1/REVIEWS_PRIVATE.jsonl',tmp_path/'joined')
    assert result['common_six_arm_tasks']==['T01','T02','T03','T04','T07','T08']
    assert result['incomplete_counterfactual_tasks']==['T05','T06']
    assert sum(x['evaluated'] for x in result['per_method_all_observed'].values())==38
    assert all(x['evaluated']==6 for x in result['per_method_common_six_arm_tasks'].values())
