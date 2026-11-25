"""Exact pairing and authorization boundaries; no device, claims or model calls."""
import copy
import pytest
from metacom_pm.rl1v3.journal.run import BATCH_PROTOCOL, PROTOCOL, admit, check_pairing
from metacom_pm.rl1v3.io import object_sha256


def fixture():
    rows=[];logical=[]
    for arm,rid in [('DP','off'),('OFF','off'),('RET','ret'),('matched-other','other')]:
        row=dict(domain='memory',task_id='t',arm=arm,logical_id='memory:t:'+arm,
            request_id=rid,payload_sha256=rid,model_input={'source':rid})
        logical.append(row)
        if rid not in {r['request_id'] for r in rows}:rows.append(row)
    plan=dict(protocol=BATCH_PROTOCOL,job_kind='JOURNAL_PAIRED_BATCH',max_calls=3,
        logical_requests=4,paired_tasks=[dict(domain='memory',task_id='t')])
    return plan,rows,logical


def test_abs_keeps_four_logical_arms_and_exactly_three_unique_calls():
    plan,rows,logical=fixture()
    check_pairing(plan,rows,logical,[])


@pytest.mark.parametrize('mutation,reason',[
    ('duplicate_physical','physical cardinality'),('missing_arm','incomplete task'),
    ('prior_request','already executed'),('different_reuse_payload','identical payload'),
    ('extra_call','unpaired physical'),('duplicate_logical','logical identity'),
])
def test_pairing_rejects_retries_missing_arms_and_nonidentical_reuse(mutation,reason):
    plan,rows,logical=fixture();rows=copy.deepcopy(rows);logical=copy.deepcopy(logical);prior=[]
    if mutation=='duplicate_physical':rows.append(rows[0]);plan['max_calls']=4
    elif mutation=='missing_arm':logical.pop();rows.pop();plan.update(max_calls=2,logical_requests=3)
    elif mutation=='prior_request':prior=[rows[0]]
    elif mutation=='different_reuse_payload':logical[1]['model_input']={'source':'changed'}
    elif mutation=='extra_call':rows.append(dict(rows[-1],request_id='extra'));plan['max_calls']=4
    elif mutation=='duplicate_logical':logical[1]['logical_id']=logical[0]['logical_id']
    with pytest.raises(ValueError,match=reason):check_pairing(plan,rows,logical,prior)


def test_old_smoke_approval_cannot_authorize_new_batch_even_with_rebound_plan_hash():
    plan,_,_=fixture()
    auth=dict(authorized=True,protocol=PROTOCOL,job_kind='JOURNAL_SMOKE',
        max_calls=3,max_model_loads=1,plan_sha256=object_sha256(plan),researcher='fixture',decision_evidence='fixture')
    with pytest.raises(ValueError,match='do not transfer'):admit(plan,auth)


def test_new_batch_approval_cannot_authorize_old_smoke_and_pending_is_not_permission():
    old=dict(protocol=PROTOCOL,job_kind='JOURNAL_SMOKE',max_calls=20)
    auth=dict(authorized=True,protocol=BATCH_PROTOCOL,job_kind='JOURNAL_PAIRED_BATCH',
        max_calls=20,max_model_loads=1,plan_sha256=object_sha256(old),researcher='fixture',decision_evidence='fixture')
    with pytest.raises(ValueError,match='do not transfer'):admit(old,auth)
    auth['authorized']=False
    with pytest.raises(ValueError,match='explicit journal approval'):admit(old,auth)
