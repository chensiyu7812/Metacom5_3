"""Scientific decision checks: missing/uncertain is not zero, retrieval != RL."""
import importlib.util
from pathlib import Path

spec=importlib.util.spec_from_file_location('qa_gain_assessment',Path(__file__).parents[1]/'scripts/rl1/177_assess_qa_resource_gain.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
P=dict(resource_gate=dict(C_accuracy_min=.8,C_minus_OFF_min=.3,C_minus_D_min=.2,positive_C_minus_OFF_owner_means_min=4),
    deployable_retrieval_screen=dict(R2_minus_OFF_min=.2,retain_C_minus_OFF_gain_fraction_min=2/3))


def records(r2_correct=8):
    return [dict(case=str(i),owner=str(i//2),arm=arm,valid=True,
        verdict='correct' if arm=='C' or (arm=='R2' and i<r2_correct) else 'abstained')
        for i in range(10) for arm in ['OFF','C','D','R1','R2']]


def test_positive_screen_does_not_claim_rl_or_deployed_latency():
    r=module.summarize(records(),list(map(str,range(10))),P)
    assert r['resource_gate_passed'] and r['short_retrieval_screen_passed']
    assert not r['RL_ready'] and not r['reward_qualified'] and r['deployment_latency_passed'] is None


def test_fixed_retrieval_gap_does_not_erase_resource_value():
    r=module.summarize(records(5),list(map(str,range(10))),P)
    assert r['resource_gate_passed'] and not r['short_retrieval_screen_passed']
    assert r['status']=='RESOURCE_PRESENT_RETRIEVAL_GAP_NO_RL'


def test_missing_off_is_not_an_observed_incorrect_answer():
    rows=records()
    for row in rows:
        if row['arm']=='OFF':row.update(valid=False,verdict='pending')
    r=module.summarize(rows,list(map(str,range(10))),P)
    assert r['full_answer_accuracy_bounds']['OFF']==dict(lower=0,upper=1)
    assert not r['resource_gate_passed'] and r['status']=='PENDING_TECHNICAL_COVERAGE'


def test_uncertain_off_prevents_falsely_large_increment():
    rows=records()
    for row in rows:
        if row['arm']=='OFF' and int(row['case'])<8:row['verdict']='uncertain'
    r=module.summarize(rows,list(map(str,range(10))),P)
    assert r['paired_mean_difference_bounds']['C/OFF']['lower']<.3
    assert not r['resource_gate_passed'] and r['status']=='PENDING_PRIMARY_SOURCE_REVIEW'
