from copy import deepcopy
from decimal import Decimal
import hashlib
import json
import socket

import pytest

from metacom_pm.rl1.development_dispatch import PaidDevelopmentStage, require_approval
from metacom_pm.rl1.schema import digest
import test_rl1_development_feedback as fixtures


@pytest.fixture(autouse=True)
def forbid_network(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *a,**k: (_ for _ in ()).throw(AssertionError('network forbidden')))


def setup(tmp_path, *, failure=None, recovery=1, capacity=100, ceiling=100000):
    policy=dict(trial='synthetic',funding_identity='shared-development-and-validation',stage_cap=ceiling,trial_cap=ceiling,shared_cap=ceiling,
        baseline=0,opening=0,external_liability=0,old_cap=ceiling,account_opening=None,opening_trial=0,
        max_attempts=6+recovery,recovery_cap=recovery,baseline_cumulative=10,cumulative_cap=capacity,
        reserve_nanodollars=1000,opening_ledger_bytes=0,opening_ledger_sha256=hashlib.sha256(b'').hexdigest(),
        historical_files={},historical_start_roots=[],historical_start_paths=[],
        legacy_lock_paths=[str(tmp_path/'legacy.lock')],request_model='deepseek-flash',
        accepted_response_models=['deepseek-flash'],input_nanodollars_per_token=1,output_nanodollars_per_token=1)
    class T(fixtures.Transport):
        def send(self, request, *, attempt_id):
            self.fail_once = failure=='format'
            raw=super().send(request,attempt_id=attempt_id)
            raw.update(attempt_id=attempt_id,model='deepseek-flash',usage=dict(prompt_tokens=10,completion_tokens=20))
            if failure=='unknown':raw.pop('usage')
            if failure=='identity':raw['attempt_id']='wrong'
            if failure=='overrun':raw['usage']['completion_tokens']=2000
            if failure=='crash':raise TimeoutError('synthetic unknown delivery')
            return raw
    s=PaidDevelopmentStage(tmp_path/'stage',fixtures.materials(),fixtures.adapter(),
        ledger=tmp_path/'ledger.jsonl',policy=policy,engineering=True)
    return s,T()


def test_complete_development_uses_real_budget_api_on_disposable_ledger(tmp_path):
    s,t=setup(tmp_path,failure='format')
    with s.budget.legacy_lease(): out=fixtures.finish(s,t)
    events=s.budget.events()
    assert len(t.calls)==5 and len(events)==10
    assert Decimal(out['accounted_usd'])==Decimal('0.00000015') and out['cumulative_attempts']==15
    assert out['physical_attempts']==5 and out['real_calls']==0 and out['qualified_receipt'] is None
    assert sum(e.get('call_class')=='TECHNICAL_RECOVERY' for e in events)==1
    before=(tmp_path/'ledger.jsonl').read_bytes()
    with s.budget.legacy_lease(): assert fixtures.finish(s,t)==out
    assert (tmp_path/'ledger.jsonl').read_bytes()==before


@pytest.mark.parametrize('failure',['unknown','crash'])
def test_unknown_usage_and_delivery_hold_full_money_and_do_not_resend(tmp_path,failure):
    s,t=setup(tmp_path,failure=failure)
    with s.budget.legacy_lease():
        with pytest.raises((ValueError,TimeoutError)):s.advance(t)
        assert s.advance(t)['status']=='RECONCILIATION_REQUIRED'
    total,_,reserved,settled=s.budget._totals(s.budget.events())
    assert total==1000 and len(reserved)==1 and not settled and len(t.calls)==1


@pytest.mark.parametrize('failure',['identity','overrun'])
def test_settled_global_risk_preserves_spend_and_stops_every_wave(tmp_path,failure):
    s,t=setup(tmp_path,failure=failure)
    with s.budget.legacy_lease():
        assert s.advance(t)['outcome']=='global_risk'
        assert s.advance(t)['status']=='RECONCILIATION_REQUIRED'
    assert len(s.budget.events())==2 and len(t.calls)==1


@pytest.mark.parametrize('constraint',['capacity','money','lease'])
def test_constraints_stop_before_transport(tmp_path,constraint):
    s,t=setup(tmp_path,capacity=10 if constraint=='capacity' else 100,ceiling=999 if constraint=='money' else 100000)
    if constraint=='lease':
        with pytest.raises(ValueError):s.advance(t)
    else:
        with s.budget.legacy_lease():
            with pytest.raises(ValueError):s.advance(t)
    assert not t.calls and not s.budget.events()


def test_orphan_reservation_and_foreign_writer_are_not_silent_reset(tmp_path,monkeypatch):
    s,t=setup(tmp_path);original=s.budget.reserve
    def broken(*args,**kwargs): original(*args,**kwargs);raise RuntimeError('after money reserve before scheduler commit')
    monkeypatch.setattr(s.budget,'reserve',broken)
    with s.budget.legacy_lease():
        with pytest.raises(RuntimeError):s.advance(t)
    monkeypatch.setattr(s.budget,'reserve',original)
    with s.budget.legacy_lease():
        with pytest.raises(ValueError,match='outstanding'):s.advance(t)
    assert len(s.budget.events())==1 and not t.calls
    event=s.budget.events()[0];event['binding']['development_stage']='foreign'
    s.budget.path.write_text(json.dumps(event)+'\n')
    with s.budget.legacy_lease():
        with pytest.raises(ValueError,match='foreign'):s.advance(t)


def test_production_approval_is_bound_to_stage_and_financial_policy(tmp_path):
    s,_=setup(tmp_path)
    with pytest.raises(ValueError):require_approval(s.identity,s.policy,None)
    record=tmp_path/'researcher.txt';record.write_text('SYNTHETIC AUTHORIZATION FIXTURE')
    a=dict(status='APPROVED',protocol_identity=s.identity,operation='bounded_development_scoring',
        financial_policy_identity=digest(s.policy),researcher_authorization_record=str(record),
        researcher_record_sha256=hashlib.sha256(record.read_bytes()).hexdigest())
    require_approval(s.identity,s.policy,a)
    with pytest.raises(ValueError):require_approval(s.identity,s.policy|dict(stage_cap=1),a)
    record.write_text('changed')
    with pytest.raises(ValueError):require_approval(s.identity,s.policy,a)


def test_following_phase_cannot_reset_shared_funding_allowance(tmp_path):
    s,t=setup(tmp_path,ceiling=2000)
    with s.budget.legacy_lease():fixtures.finish(s,t)
    data=s.budget.path.read_bytes()
    policy=deepcopy(s.policy)
    policy.update(opening_ledger_bytes=len(data),opening_ledger_sha256=hashlib.sha256(data).hexdigest(),
        reserve_nanodollars=1900,trial_cap=10000,shared_cap=10000,old_cap=10000)
    next_stage=PaidDevelopmentStage(tmp_path/'next-phase',fixtures.materials(),fixtures.adapter(),
        ledger=s.budget.path,policy=policy,engineering=True)
    with next_stage.budget.legacy_lease():
        with pytest.raises(ValueError,match='monetary envelope'):next_stage.advance(t)
    assert s.budget.path.read_bytes()==data


def test_budget_attributes_cannot_bypass_frozen_policy(tmp_path):
    s,t=setup(tmp_path);s.budget.stage_cap+=1
    with s.budget.legacy_lease():
        with pytest.raises(ValueError,match='policy changed'):s.advance(t)
    assert not t.calls and not s.budget.events()
