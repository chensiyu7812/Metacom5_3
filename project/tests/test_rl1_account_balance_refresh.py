"""Account snapshots never create research allowance or erase unknown charges."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from metacom_pm.rl1 import account_balance_refresh as implementation
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.development_dispatch import sha
from metacom_pm.rl1.schema import digest
from test_rl1_retained_liability_continuation import isolated
import test_rl1_development_feedback as fixtures


def refreshed(tmp_path, *, balance='0.00001', ceiling=100000):
    _, old, transport, claim, _ = isolated(tmp_path, ceiling=ceiling)
    path = tmp_path/'balance.json'
    path.write_text(json.dumps(dict(is_available=True, balance_infos=[dict(currency='USD', total_balance=balance)])))
    record = stamp(dict(status=implementation.STATUS, stage_identity=old.identity,
        financial_policy_identity=digest(old.policy), isolation_identity=old.isolation['identity'],
        balance_path=str(path.resolve()), available_nanodollars=implementation.available_nanodollars(json.loads(path.read_text())),
        **implementation.snapshot_fields(old.budget), new_allowance=0, settlement_changes=0,
        source_hashes={str(p.resolve()):sha(p) for p in (path,Path(implementation.__file__))}))
    new = implementation.RefreshedDevelopmentStage(old.root,old.materials,old.adapter,
        ledger=old.budget.path,policy=old.policy,engineering=True,isolation=old.isolation,refresh=record)
    return new,transport,claim


def test_refresh_continues_with_original_unknown_and_original_attempt_counts(tmp_path):
    new,transport,claim=refreshed(tmp_path)
    before=new.budget.path.read_bytes()
    with new.budget.legacy_lease(): out=fixtures.finish(new,transport)
    assert out['physical_attempts']==3 and len(transport.calls)==2 and out['unknown_liabilities']==1
    assert new.budget.path.read_bytes().startswith(before)
    assert claim['attempt_id'] not in new.budget._totals(new.budget.events())[3]
    assert new.refresh['opening_trial_nanodollars']==0


@pytest.mark.parametrize('balance,ceiling', [('0.000001999',100000),('0.00001',1999)])
def test_refresh_keeps_account_unknown_reserve_and_original_project_cap(tmp_path,balance,ceiling):
    new,transport,_=refreshed(tmp_path,balance=balance,ceiling=ceiling)
    with new.budget.legacy_lease():
        with pytest.raises(ValueError,match='balance insufficient|envelope'):new.advance(transport)
    assert len(new.budget.events())==1 and not transport.calls


def test_settled_cost_precedes_new_snapshot_but_unknown_maximum_does_not(tmp_path):
    new,transport,_=refreshed(tmp_path)
    with new.budget.legacy_lease():new.advance(transport)
    snapshot=implementation.snapshot_fields(new.budget)
    assert snapshot['trial_nanodollars']==1030
    assert snapshot['opening_trial_nanodollars']==30
    assert sum(snapshot['outstanding_nanodollars'].values())==1000


def test_cannot_hide_original_unknown_in_the_new_baseline(tmp_path):
    new,transport,_=refreshed(tmp_path)
    changed=deepcopy(new.refresh);changed.pop('identity');changed['opening_trial_nanodollars']=1000
    with pytest.raises(ValueError,match='unknown maximum'):implementation.validate_refresh(stamp(changed),new.budget)
    assert not transport.calls


@pytest.mark.parametrize('currency,value',[('EUR','1'),('USD','NaN'),('CNY','-1')])
def test_invalid_account_reply_cannot_authorize_dispatch(currency,value):
    with pytest.raises(ValueError):implementation.available_nanodollars(dict(is_available=True,balance_infos=[dict(currency=currency,total_balance=value)]))


def test_duplicate_currency_is_not_counted_twice():
    row=dict(currency='USD',total_balance='1')
    with pytest.raises(ValueError):implementation.available_nanodollars(dict(is_available=True,balance_infos=[row,row]))


def test_balance_receipt_tamper_stops_before_dispatch(tmp_path):
    new,transport,_=refreshed(tmp_path)
    Path(new.refresh['balance_path']).write_text('{}')
    with new.budget.legacy_lease():
        with pytest.raises(ValueError,match='evidence'):new.advance(transport)
    assert not transport.calls and len(new.budget.events())==1
