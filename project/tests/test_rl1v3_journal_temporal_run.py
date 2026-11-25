import copy
import pytest
from metacom_pm.rl1v3.journal import temporal_run as R


def fixture():
    rows=[]
    for task in range(8):
        for i,arm in enumerate(sorted(R.ARMS)):
            rid=f'r{task}-{i if task%4 else min(i,1)}'
            rows.append(dict(task_id=str(task),logical_id=str(task)+':'+arm,domain='memory_temporal',arm=arm,
                             request_id=rid,model_input={'same':rid}))
    logical=rows[:12];physical=list({r['request_id']:next(x for x in logical if x['request_id']==r['request_id']) for r in logical}.values())
    plan=dict(batch_number=1,task_ids=['0','1','2','3'],logical_requests=12,max_calls=11)
    return plan,physical,logical,rows


def test_full_pairing_and_exact_reuse():
    R.validate_pairing(*fixture())


@pytest.mark.parametrize('mutation',['missing_arm','order','reuse'])
def test_scope_changes_rejected(mutation):
    p,r,l,f=copy.deepcopy(fixture())
    if mutation=='missing_arm':l.pop()
    elif mutation=='order':p['task_ids'].reverse()
    else:l[2]['model_input']={'different':1}
    with pytest.raises(ValueError):R.validate_pairing(p,r,l,f)


def test_old_approval_never_transfers():
    with pytest.raises(ValueError):R.admit(dict(protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND),
        dict(authorized=True,protocol='pmrl1-j-rs-complex-paired-run-v1',job_kind='JOURNAL_RS_COMPLEX_PAIRED'))
