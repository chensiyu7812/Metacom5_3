"""Disposable ledgers only: never erase, charge zero, or resend an unknown call."""
from copy import deepcopy
import json
from pathlib import Path
import sqlite3

import pytest

from metacom_pm.rl1 import retained_liability_continuation as implementation
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.schema import digest
from test_rl1_development_dispatch import setup
import test_rl1_development_feedback as fixtures


def isolated(tmp_path, *, ceiling=100000, capacity=100):
    old, crash = setup(tmp_path, failure='crash', ceiling=ceiling, capacity=capacity)
    with old.budget.legacy_lease():
        with pytest.raises(TimeoutError): old.advance(crash)
    with sqlite3.connect(old.root/'S/attempts.sqlite') as db:
        claim=json.loads(db.execute('SELECT claim FROM attempts').fetchone()[0])
    wire=old.root/'wire';wire.mkdir()
    sse=wire/(claim['attempt_id']+'.sse')
    sse.write_text('data: '+json.dumps(dict(choices=[dict(delta=dict(reasoning_content='SYNTHETIC partial'),finish_reason=None)],usage=None))+'\n\n')
    hashes={str(p.resolve()):implementation.sha(p) for p in (sse,Path(implementation.__file__))}
    proof=stamp(dict(status=implementation.STATUS, stage_identity=old.identity,
        financial_policy_identity=digest(old.policy),run_directory=str(old.root.resolve()),
        component='S',attempt_id=claim['attempt_id'],claim_identity=digest(claim),logical_slot=claim['slot_id'],
        source_hashes=hashes,new_allowance=0,retry_isolated_request=False))
    new=implementation.RetainedDevelopmentStage(old.root,old.materials,old.adapter,
        ledger=old.budget.path,policy=old.policy,engineering=True,isolation=proof)
    _,normal=setup(tmp_path/'other_fixture')
    return old,new,normal,claim,sse


def test_continue_only_independent_slots_with_full_liability_and_failure_denominator(tmp_path):
    old,new,transport,claim,_=isolated(tmp_path)
    initial=old.budget.path.read_bytes()
    with new.budget.legacy_lease(): out=fixtures.finish(new,transport)
    assert len(transport.calls)==2 and out['physical_attempts']==3
    assert out['unknown_liabilities']==1 and out['unknown_attempt_retried'] is False
    assert out['waves'][0]['states'][claim['slot_id']]=='UNKNOWN_ISOLATED_FULL_LIABILITY_RETAINED'
    total,_,reserved,settled=new.budget._totals(new.budget.events())
    assert total==1060 and len(reserved)==3 and len(settled)==2
    assert claim['attempt_id'] not in settled and new.budget.path.read_bytes().startswith(initial)
    with sqlite3.connect(new.root/'S/attempts.sqlite') as db:
        assert db.execute('SELECT result FROM attempts WHERE id=?',(claim['attempt_id'],)).fetchone()==(None,)
    requests={key:new.adapter.prepare(item,'S') for key,item in new.items.items()}
    sched=new._wave('S',requests,new.recovery_cap)
    report=sched.report()
    assert report['first_attempts']==2 and report['first_technical_valid']==1
    assert all(r['S_candidate'] is None and r['A_resolution'] is None for r in out['materials'] if r['logical_identity']==claim['slot_id'])
    # Historical code still refuses the unaltered unresolved row.
    with old.budget.legacy_lease(): assert old.advance(transport)['status']=='RECONCILIATION_REQUIRED'


@pytest.mark.parametrize('constraint',['money','attempts'])
def test_no_reset_of_original_money_or_physical_attempt_cap(tmp_path,constraint):
    _,new,transport,_,_=isolated(tmp_path,ceiling=1999 if constraint=='money' else 100000,
                                capacity=11 if constraint=='attempts' else 100)
    with new.budget.legacy_lease():
        with pytest.raises(ValueError,match='envelope|capacity'): new.advance(transport)
    assert not transport.calls and len(new.budget.events())==1


def test_a_second_unknown_stops_instead_of_becoming_automatically_isolated(tmp_path):
    _,new,_,claim,_=isolated(tmp_path)
    _,crash=setup(tmp_path/'second_failure',failure='crash')
    with new.budget.legacy_lease():
        with pytest.raises(TimeoutError):new.advance(crash)
        assert new.advance(crash)['status']=='RECONCILIATION_REQUIRED'
    assert len(crash.calls)==1 and len(new.budget.events())==2
    assert new.budget._totals(new.budget.events())[0]==2000


def test_isolated_input_cannot_be_retried_under_a_new_attempt_id(tmp_path):
    _,new,_,claim,_=isolated(tmp_path)
    binding=dict(development_stage=new.identity,study=new.policy['funding_identity'],
                 logical_slot=claim['slot_id'],ordinal=1)
    with new.budget.legacy_lease():
        with pytest.raises(ValueError,match='cannot be resent'):new.budget.reserve('new-id',1000,binding)
    assert len(new.budget.events())==1


@pytest.mark.parametrize('tamper',['stream','policy','code_binding'])
def test_proof_tamper_fails_before_more_spending(tmp_path,tamper):
    _,new,transport,_,sse=isolated(tmp_path)
    if tamper=='stream':sse.write_text(sse.read_text()+'data: [DONE]\n\n')
    elif tamper=='policy':new.policy['stage_cap']+=1
    else:
        proof=deepcopy(new.isolation);proof['source_hashes'].pop(str(Path(implementation.__file__).resolve()))
        new.isolation=stamp({k:v for k,v in proof.items() if k!='identity'})
    with new.budget.legacy_lease():
        with pytest.raises(ValueError):new.advance(transport)
    assert not transport.calls and len(new.budget.events())==1
