from copy import deepcopy
import json
from types import SimpleNamespace

import pytest

from metacom_pm.rl1.resource_comparison_runner import (request_for, visible_request, protocol_for, FixedResourceComparison)
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.schema import digest


def setup(tmp_path, *, finish='natural_stop', scope='engineering'):
    runtime=stamp(dict(model='SYNTHETIC',policy=dict(context_limit=100000)))
    rows=[]
    for i in range(2):
        row=dict(prefix_identity='prefix'+str(i),executor_identity=runtime['identity'],renderer_identity='renderer',
            renderer_route='new_organization_renderer',messages=[dict(role='user',content='synthetic request '+str(i))],
            selected_keys=[f'address-{j}' for j in range(6)],selected_resource_identities=[f'resource-{j}' for j in range(6)],
            catalog_identity='catalog',usage=dict(input_tokens=17))
        row.update(identity=digest(row),reusable_old_requests=[]);rows.append(row)
    requests=[request_for(r,runtime=runtime,draw_identity='draw',code_identity='source-code') for r in rows]
    p=protocol_for(requests,runtime=runtime,assets={},packages={},gpu_uuid='fixture',code_identity='source-code',
                   source_package_identity='prepared',engineering=scope=='engineering',run_directory=tmp_path/'run')
    calls=[]
    def factory(r):calls.append('load');return SimpleNamespace(identity=r['identity'],manifest={k:v for k,v in r.items() if k!='identity'})
    def invoke(g,request):
        calls.append(deepcopy(request))
        if finish=='crash':raise KeyboardInterrupt('synthetic interrupted model')
        return dict(request_id=request['request_id'],runtime_identity=g.identity,text='synthetic reply',
                    finish_reason=finish,input_tokens=17,api_cost_usd=0)
    guard=SimpleNamespace(check=lambda **kw:None)
    kwargs=dict(factory=factory,guard=guard,invoke=invoke) if scope=='engineering' else {}
    runner=FixedResourceComparison(p,requests,tmp_path/'run',**kwargs)
    return runner,calls,rows,requests,kwargs


def test_explicit_six_resource_addresses_project_only_messages_and_run_once(tmp_path):
    r,c,_,requests,_=setup(tmp_path)
    assert r.step()['status']=='GENERATION_RECORDED';assert r.step()['status']=='GENERATION_RECORDED'
    out=r.step();assert out['completed']==2 and out['natural_stops']==2
    assert c.count('load')==1 and len(c)==3
    assert set(c[1])=={'request_id','messages','executor_identity','draw_identity','renderer_identity'}
    assert 'address-' not in str(c[1]) and r.step()==out
    assert len(requests[0]['provenance']['selected_keys'])==6


def test_unauthorized_cannot_load_or_create_run_directory(tmp_path):
    r,c,*_=setup(tmp_path,scope='production')
    with pytest.raises(ValueError,match='not authorized'):r.step()
    assert not c and not r.root.exists()


def test_crash_is_not_resent_and_known_non_natural_finishes_remain_failures(tmp_path):
    r,c,*_=setup(tmp_path/'crash',finish='crash')
    with pytest.raises(KeyboardInterrupt):r.step()
    assert r.step()['status']=='RECONCILIATION_REQUIRED' and len(c)==2
    r,c,*_=setup(tmp_path/'timeout',finish='technical_timeout')
    r.step();r.step();out=r.step()
    assert out['natural_stops']==0 and out['non_natural']==2 and out['quality_effect']=='not_evaluated'


def test_raw_result_recovery_avoids_reload_but_remaining_calls_need_unused_load_scope(tmp_path,monkeypatch):
    import metacom_pm.rl1.resource_comparison_runner as m
    r,c,_,requests,kwargs=setup(tmp_path);original=m.save_once
    def stop_at_seal(path,value):
        if path.name.endswith('.sealed.json'):raise KeyboardInterrupt()
        original(path,value)
    with monkeypatch.context() as patch:
        patch.setattr(m,'save_once',stop_at_seal)
        with pytest.raises(KeyboardInterrupt):r.step()
    resumed=FixedResourceComparison(r.protocol,requests,r.root,**kwargs)
    assert resumed.step()['recovered_without_model_call'] and len(c)==2
    with pytest.raises(ValueError,match='no implicit reload'):resumed.step()
    assert len(c)==2


def test_changed_source_token_counts_and_duplicate_inputs_rejected(tmp_path):
    r,c,rows,requests,kwargs=setup(tmp_path)
    changed=deepcopy(rows[0]);changed['selected_keys'][0]='other'
    with pytest.raises(ValueError):request_for(changed,runtime=r.protocol['runtime'],draw_identity='draw',code_identity='source-code')
    with pytest.raises(ValueError):protocol_for([requests[0],requests[0]],runtime=r.protocol['runtime'],assets={},packages={},
        gpu_uuid='fixture',code_identity='source-code',source_package_identity='x',engineering=True)
    invoke=kwargs['invoke']
    def wrong(*args):return invoke(*args)|dict(input_tokens=16)
    r.invoke=wrong
    with pytest.raises(ValueError,match='input-token'):r.step()
    assert len(c)==2


def test_tampered_seal_and_completed_replay_checked_without_model(tmp_path):
    r,c,_,requests,kwargs=setup(tmp_path)
    r.step();r.step();r.step();n=len(c)
    resumed=FixedResourceComparison(r.protocol,requests,r.root,**kwargs)
    assert resumed.step()['completed']==2 and len(c)==n
    p=next(r.root.glob('*.raw.json'));v=json.loads(p.read_text());v['text']='changed';p.write_text(json.dumps(v))
    with pytest.raises(ValueError,match='sealed'):resumed.step()
