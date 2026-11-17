from datetime import datetime,timezone
from types import SimpleNamespace
import pytest
from metacom_pm.rl1v3.generator.bounded_probe import authorize,device_guard,schedule,estimate,PROTOCOL,GPU_UUID
from metacom_pm.rl1v3.io import object_sha256

def test_gpu_approval_must_be_explicit_scoped_and_unexpired():
    plan={'workloads':{'gemma':{'max_calls':154}}}
    a=dict(protocol=PROTOCOL,authorized=True,researcher_approval_reference='test-fixture-only',
           plan_sha256=object_sha256(plan),gpu_uuid=GPU_UUID,workloads=['gemma'],expires_at='2099-01-01T00:00:00Z')
    assert authorize(plan,a,'gemma')['max_calls']==154
    for change in ({'authorized':False},{'researcher_approval_reference':None},{'plan_sha256':'bad'},
                   {'gpu_uuid':'other'},{'expires_at':'2000-01-01T00:00:00Z'},{'workloads':[]}):
        with pytest.raises(ValueError):authorize(plan,a|change,'gemma')

def test_exclusive_uuid_and_free_memory_are_enforced_without_touching_gpu():
    def fake(free,apps):
        return lambda cmd,**kw:SimpleNamespace(stdout=f'{GPU_UUID}, {free}\n' if '--query-gpu=uuid,memory.free' in cmd else apps)
    assert device_guard(run=fake(40000,''))['free_mib']==40000
    for free,apps in [(30000,''),(40000,f'{GPU_UUID}, 42')]:
        with pytest.raises(RuntimeError):device_guard(run=fake(free,apps))
    assert device_guard(own_pid=42,run=fake(5000,f'{GPU_UUID}, 42'))
    with pytest.raises(RuntimeError):device_guard(own_pid=42,run=fake(2000,f'{GPU_UUID}, 42'))

def test_batch_budget_uses_padded_full_context_and_preserves_rows():
    rows=[dict(request_id=str(i),input_ids=[2]*i,max_new_tokens=4,context_limit=20) for i in (2,5,10)]
    groups=schedule(rows,[(4,3)],padded_context_cap=20)
    assert [len(g) for g in groups]==[2,1]
    assert sum(len(g) for g in groups)==3
    with pytest.raises(ValueError):schedule([rows[-1]|{'context_limit':12}],[(1,1)],padded_context_cap=20)

def test_cost_requires_matching_actual_measurements():
    assert all(x['estimated_seconds'] is None for x in estimate([],needcards=20,g_terminals=120,j1_calls=360).values())
    e=estimate([dict(workload='gemma',status='measured',seconds=10,actual_requests=2,execution_identity='fixture')],needcards=20,g_terminals=120,j1_calls=360)
    assert e['gemma']['projected_seconds_range']==[600,600]
    assert e['j1']['estimated_seconds'] is None
