"""CPU fault injection only; fabricated mechanism examples are never research evidence."""
import copy
import dataclasses

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.compile import asof as A
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.env import research_v32 as OLD
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity
from metacom_pm.rl1v3.asof import binding as OLD_BINDING, wsa_adapter as OLD_ADAPTER
from metacom_pm.rl1v3.evaluate.terminal_registry import ReplayBinding
from metacom_pm.rl1v3.journal import runtime_binding as B, outcome_adapter as O
from metacom_pm.rl1v3.io import object_sha256
from metacom_pm.rl1v3.train.real_instances import IncompleteTable, oracle_dp


def make_registry(raw_sha='a'*64):
    entries=[]
    for n in range(4):
        turns=(K.SourceTurn(turn_index=0,role='seeker',text=f'Fixture report {n}.'),
               K.SourceTurn(turn_index=1,role='supporter',text='Fixture response.'))
        source=K.SourceSession(owner_id='fixture-owner',session_id=f's{n}',chronological_rank=n,
            date=None,turns=turns,raw_sha256=raw_sha,dataset=S.DATASET,family_id='fixture-family',
            license='test_only',provenance_version='test',source_uri='fixture://only',
            transcript_sha256=object_sha256([(t.role,t.text) for t in turns]),source_split='dev')
        entries.append(S.Entry(S._source_id(source),source,(0,1),K.TimePoint(session_rank=n),
                               K.TimePoint(session_rank=n+1),'personal_history',0))
    return S.Registry(entries,inputs={},folds={'fold_of_owner':{'fixture-owner':0},
        'historical_rl1_split':{'fixture-owner':'dev'}},excluded_families=())


class Counter:
    identity='fixture-character-count-not-native-tokenizer'
    def count(self,text):return len(text)


class SnapshotPort:
    """Test only snapshot read adapter; does not represent a Generator or retrieval experiment."""
    def __init__(self,prefix,snapshot):
        self.prefix,self.snapshot=prefix,snapshot
        self.base_tokens=100
        self.identity={k:'fixture-'+k for k in B.IDENTITY_FIELDS}
    def availability(self):return dict(RS=0,MP=0,ME=0,MS=1)
    def action_mask(self,acquired):return ('STOP',) if acquired else ('STOP','GET_MS')
    def read(self,head,*,acquired):
        v=A.read(self.snapshot,head,ordinal=len(acquired)+1,token_counter=Counter(),context_remaining=10000)
        ids=A.candidate_ids(self.snapshot,head)
        before=self.base_tokens+sum(x.tokens for x in acquired)
        return K.ReadSuccess(reading=v,record_ids=(ids[-1],),input_tokens_before=before,
            input_tokens_after=before+v.tokens,native_context_tokens=12000,output_reserve_tokens=320,elapsed_ms=0)


def world():
    r=make_registry();p=r.prefix('fixture-owner','s3',0);ledger=A.Ledger()
    for e in r.visible(p):ledger.append(A.record_from_source(e,kind='MS_RAW',writer='fixture-writer'),r)
    s=A.materialize(r,p,ledger,writer='fixture-writer');port=SnapshotPort(p,s)
    b=B.binding_for(r,p,s,port)
    return r,p,ledger,s,port,b


def test_r1_old_source_id_changes_but_new_local_binding_does_not():
    r,p,ledger,s,port,b=world();other=make_registry('b'*64)
    assert OLD_BINDING.frontier_for(r,p)!=OLD_BINDING.frontier_for(other,p)
    assert B.binding_for(other,p,s,port)==b


def test_r2_rejects_a_well_formed_but_wrong_snapshot():
    r,p,ledger,s,port,b=world()
    smaller=A.Ledger();smaller.append(ledger.rows[0],r)
    other=A.materialize(r,p,smaller,writer='fixture-writer')
    with pytest.raises(OLD.BindingMismatch,match='snapshot mismatch'):
        B.VerifiedEpisode(registry=r,prefix=p,snapshot=other,port=port,binding=b)


def test_r2_rejects_a_post_construction_port_identity_change():
    r,p,ledger,s,port,b=world();ep=B.VerifiedEpisode(registry=r,prefix=p,snapshot=s,port=port,binding=b)
    state=ep.reset();port.identity['g_id']='changed'
    with pytest.raises(OLD.BindingMismatch):ep.try_step(state,'GET_MS')


def test_r3_stop_then_get_is_after_stop():
    r,p,ledger,s,port,b=world();ep=B.VerifiedEpisode(registry=r,prefix=p,snapshot=s,port=port,binding=b)
    state=ep.reset();before=ep.composite_key(state);done,info=ep.try_step(state,'STOP')
    assert done.done and ep.composite_key(done)==before
    unchanged,error=ep.try_step(done,'GET_MS')
    assert unchanged==done and error.reason=='after_stop'


def test_real_c0_get_trace_keeps_unknown_terminal_pending():
    r,p,ledger,s,port,b=world();ep=B.VerifiedEpisode(registry=r,prefix=p,snapshot=s,port=port,binding=b)
    state,_=ep.try_step(ep.reset(),'GET_MS');ep.env.execution_trace(state).verify_key(ep.env.terminal_key(state))
    assert len(state.readings)==1 and ep.stop_value(state).status=='pending'


def test_r4_original_repaired_cache_is_idempotent_and_deeply_copied():
    r,p,ledger,s,port,b=world()
    old=OLD_BINDING.legacy_bank_v0_binding(r,p,identity=port.identity,snapshot_sha256='a'*64,
        external_snapshot='fixture',visibility_policy='fixture')
    cache=OLD.ReplayCache();value={'nested':{'v':[1]}}
    cache.put('b'*64,old,value);cache.put('b'*64,old,value)
    value['nested']['v'].append(2);got=cache.get('b'*64,old);got['nested']['v'].append(3)
    assert cache.get('b'*64,old)['nested']=={'v':[1]}
    with pytest.raises(ValueError):cache.put('b'*64,old,{'different':True})


def relation_world(approved):
    r=make_registry();p=r.prefix('fixture-owner','s3',0);ledger=A.Ledger()
    e=r.entry('fixture-owner','s0')
    old=A.record_from_source(e,kind='MP',refs=(S.span(e.source,0),),text=e.source.turns[0].text,
         writer='fixture-writer',subject='user',slot='fixture',review_status='human_approved',
         approval_ref='SYNTHETIC_TEST_ONLY_NOT_A_HUMAN_REVIEW')
    ledger.append(old,r);e=r.entry('fixture-owner','s1')
    edge=A.record_from_source(e,kind='RELATION',refs=(S.span(e.source,0),),text=e.source.turns[0].text,
        writer='fixture-writer',subject='user',slot='fixture',operation='UPDATE',target_id=old.record_id,
        valid_from=K.TimePoint(session_rank=1),valid_to=K.TimePoint(session_rank=2),
        review_status='human_approved' if approved else 'pending',
        approval_ref='SYNTHETIC_TEST_ONLY_NOT_A_HUMAN_REVIEW' if approved else None)
    ledger.append(edge,r)
    return r,p,A.materialize(r,p,ledger,writer='fixture-writer'),old,edge


@pytest.mark.parametrize('approved',[False,True])
def test_r5_old_relation_adapter_fails_but_new_exchange_keeps_all_semantics(approved):
    r,p,s,old,edge=relation_world(approved)
    with pytest.raises(KeyError):OLD_ADAPTER.to_cut(B.plain(s),r,p)
    ex=B.relation_exchange(s)
    row=next(x for x in ex['rows'] if x['kind']=='RELATION')
    assert row['head'] is None and row['record']['target_id']==old.record_id
    assert row['record']['valid_from']['session_rank']==1 and row['record']['valid_to']['session_rank']==2
    assert row['semantic_approved']==approved and ex['approval_created'] is False
    old_row=next(x for x in ex['rows'] if x['record_id']==old.record_id)
    assert old_row['disposition']==('superseded' if approved else 'supported_report')


@pytest.mark.parametrize('req,pro,status,expected',[
    (['pass'],[],'ok',('complete',1)),(['uncertain'],[],'ok',('pending',None)),
    (['fail','uncertain'],[],'ok',('complete',0)),(['pass'],['fail'],'ok',('complete',0)),
    (['pass'],[],'timeout',('technical_failure',None))])
def test_y_failure_uncertainty_and_technical_failure_are_distinct(req,pro,status,expected):
    result=O.task_success(req,pro,technical_status=status)
    assert (result['status'],result['reward'])==expected


def registered(tmp_path,qualify=False):
    r,p,ledger,s,port,b=world();ep=B.VerifiedEpisode(registry=r,prefix=p,snapshot=s,port=port,binding=b)
    key=ep.env.terminal_key(ep.reset());trace=ep.env.execution_trace(ep.reset())
    frozen=O.FrozenEvalLedger(tmp_path);spec={'requirements':[{'id':'r1','criterion':'fixture only'}],'prohibitions':[]}
    spec_sha=frozen.freeze(p.prefix_id,spec)
    qualification={'qualified':True,'protocol':O.PROTOCOL,'evidence_sha256':'c'*64,'evaluator_id':'fixture-only',
                   'evalspec_sha256':spec_sha} if qualify else None
    reg=O.TaskTerminalRegistry(identity=ep.env.identity,ledger=frozen,qualification_receipt=qualification)
    replay=ReplayBinding(p.prefix_id,port.identity,{'OFF':key.sha256},(0,));reg.bind_prefix(p,replay)
    reg.register(p.prefix_id,key,trace,'a'*64)
    return reg,p,key,spec_sha,port


def test_terminal_registry_refuses_incomplete_item_coverage_and_unknown_is_not_zero(tmp_path):
    reg,p,key,sha,port=registered(tmp_path)
    with pytest.raises(O.RegistryError,match='coverage'):
        reg.add_task_outcome(p.prefix_id,key_sha256=key.sha256,response_sha256='a'*64,evalspec_sha256=sha,
                            requirements={},prohibitions={},evidence=['fixture'])
    reg.add_task_outcome(p.prefix_id,key_sha256=key.sha256,response_sha256='a'*64,evalspec_sha256=sha,
                        requirements={'r1':'uncertain'},prohibitions={},evidence=['fixture'])
    table,report=reg.table(p.prefix_id)
    assert report['pending']==1 and not report['complete'] and table.rows=={}
    with pytest.raises(IncompleteTable):oracle_dp(reg.real_instance(p.prefix_id,lambda:port))


def test_complete_but_unqualified_endpoints_never_enter_training(tmp_path):
    reg,p,key,sha,port=registered(tmp_path)
    reg.add_task_outcome(p.prefix_id,key_sha256=key.sha256,response_sha256='a'*64,evalspec_sha256=sha,
                        requirements={'r1':'pass'},prohibitions={},evidence=['fixture'])
    table,report=reg.table(p.prefix_id)
    assert report['measured_complete'] and not report['complete'] and not table.rows
    with pytest.raises(IncompleteTable):oracle_dp(reg.real_instance(p.prefix_id,lambda:port))


def test_qualified_test_fixture_reuses_realinstance_and_oracle_only_for_engineering(tmp_path):
    reg,p,key,sha,port=registered(tmp_path,True)
    reg.add_task_outcome(p.prefix_id,key_sha256=key.sha256,response_sha256='a'*64,evalspec_sha256=sha,
                        requirements={'r1':'pass'},prohibitions={},evidence=['SYNTHETIC_UNIT_TEST_ONLY'])
    assert oracle_dp(reg.real_instance(p.prefix_id,lambda:port)).root_value==1
    with pytest.raises(O.RegistryError):reg.ledger.freeze(p.prefix_id,{'changed':True})
