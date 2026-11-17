"""Real-bank admission/reading/replay. Tiny tokenizer is test-only, never measurement."""
from pathlib import Path
from collections import Counter
from dataclasses import replace
import json
import itertools
import pytest
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import canonical_json,object_sha256
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.bank import bank_v0 as B
from metacom_pm.rl1v3.retrieve import Reader,search
from metacom_pm.rl1v3.render.v0 import messages
ROOT=Path(__file__).resolve().parents[2]

class FixtureTokenizer:
    identity='unit_test_only_unicode_codepoints'
    native_context_tokens=100000
    def count(self,text):return len(text)
    def prompt_tokens(self,prefix,readings):return len(canonical_json(messages(prefix,readings)))

@pytest.fixture(scope='module')
def bank():return B.build(ROOT,S.build(ROOT))

@pytest.fixture
def reader(bank):
    source=max((e.source for e in bank.registry.entries if e.source.owner_id=='p2'),key=lambda s:s.chronological_rank)
    cut=next(i for i,t in enumerate(source.turns[:-1]) if t.role=='seeker' and source.turns[i+1].role=='supporter')
    return Reader(bank,bank.registry.prefix('p2',source.session_id,cut),FixtureTokenizer(),g_id='test_g',decode_id='greedy-test')


def test_real_counts_and_no_auto_validation(bank):
    assert Counter(r.head for r in bank.records)=={'MP':387,'ME':1525,'MS':401,'RS':875}
    assert len([r for r in bank.ledger if r['old_head']=='MP'])==713
    assert len([r for r in bank.ledger if r['old_head']=='ME'])==1523
    assert Counter(r.review_status for r in bank.records)=={'unverified':3185,'development_reviewed':3}
    assert all(not r.positive_eligible and r.evidence_status=='exact_span_verified' for r in bank.records)
    assert all(not r.related_claim_ids and not r.relation_index_version for r in bank.records)


def test_all_325_old_mp_exclusions_reconciled(bank):
    missing=[r for r in bank.ledger if r['old_head']=='MP' and not r['old_pool_member']]
    assert len(missing)==325
    assert all(r['replacement_ids'] for r in missing)
    assert Counter(r['status'] for r in missing)=={'quarantine':324,'repaired':1}
    assert all(not r['new_record_ids'] for r in missing if r['status']=='quarantine')
    assert all(bank.by_id[i].head=='ME' for r in missing for i in r['new_record_ids'])


def test_three_repairs_use_exact_evidence_and_new_identities(bank):
    repairs=[r for r in bank.ledger if r['status']=='repaired']
    assert len(repairs)==3
    stages={r['old_id']:bank.by_id[r['new_record_ids'][0]].stage for r in repairs}
    assert stages['mp::mvu_2a73b2853cdd499d576e2ab5']=='attempted'
    assert stages['mp::mvu_785a6f6f9e719c52ef13fc57']=='attempted'
    assert stages['me::mvu_c8da36ab41b1d4da5464dd8d']=='unknown'
    for row in repairs:
        rec=bank.by_id[row['new_record_ids'][0]]
        assert rec.head=='ME' and rec.event_time is None and rec.valid_from is None
        assert rec.review_status=='development_reviewed'
        assert not json.loads(rec.body)['repair_candidate']['causal_effect_established']
        assert all(ref.exact_quote in rec.reading_text for ref in rec.source_refs)


def test_rs_lineage_not_independent_strategy_count(bank):
    strategy=[r for r in bank.ledger if r['old_head']=='RS_strategy']
    treatments=[r for r in bank.ledger if r['old_head']=='RS_treatment']
    assert len(strategy)==11590 and len(treatments)==13172
    assert sum(r['binding']=='exact' for r in strategy)==6410
    assert sum(r['binding'].startswith('legacy_whitespace') for r in strategy)==5180
    assert len({i for row in strategy for i in row['new_record_ids']})==823
    assert len({i for row in strategy+treatments for i in row['new_record_ids']})==875
    assert all(not r['source_verified'] and r['lineage_verified'] for r in treatments)
    assert all(r['source_card_ids'] and r['atomic_card_ids'] for r in treatments)
    drafts=[r for r in bank.ledger if r['old_head'] in ('RS_case','RS_method')]
    assert len(drafts)==15 and all(not r['new_record_ids'] for r in drafts)
    assert Counter(r['status'] for r in drafts)=={'quarantine':9,'repair':6}


def test_raw_and_case_are_whole_original_dialogues(bank):
    for r in bank.records:
        if r.head not in ('MS','RS'):continue
        s=bank.registry.by_id[bank.source_ids[r.record_id][0]].source
        assert r.reading_text.endswith('\n'.join(f'{t.role}: {t.text}' for t in s.turns))
        assert r.view in ('raw','case')
        assert all(ref.raw_turn_sha256==s.turns[ref.turn_index].raw_turn_sha256 for ref in r.source_refs)


def test_filter_before_rank_uses_only_visible_query(reader):
    for h in K.HEAD_ORDER:
        result=search(reader.bank,h,reader.prefix)
        assert result.ranked
        for candidate in result.ranked:
            r=reader.bank.by_id[candidate.record_id]
            assert reader.bank.reason(r,reader.prefix) is None
            if h!='RS':assert r.owner_id==reader.prefix.owner_id and r.source_rank<reader.prefix.cutoff_rank
            else:assert not ({r.family_id}&(reader.bank.registry.excluded_families|set(reader.prefix.ancestor_family_ids)))
    assert search(reader.bank,'ME',reader.prefix)==search(reader.bank,'ME',replace(reader.prefix,stratum='none'))


def test_deterministic_read_and_counter_accounting(reader):
    a=reader.read('ME');b=reader.read('ME')
    assert isinstance(a,K.ReadSuccess) and a.reading.tokens==reader.tokenizer.count(a.reading.reading_text)
    assert replace(a,elapsed_ms=0)==replace(b,elapsed_ms=0)
    assert a.record_ids and a.input_tokens_after+a.output_reserve_tokens<=a.native_context_tokens
    assert 'record_id' not in json.loads(canonical_json(a.reading))


def test_read_failures_do_not_consume_ordinal(reader):
    for result in [reader.read('EXPAND_MS(1)'),reader.read('MP',bank_version='wrong'),reader.read('ME',index_version='wrong')]:
        assert isinstance(result,K.ReadFailure)
    assert reader.read('MS').reading.ordinal==1
    first=reader.read('ME')
    assert reader.read('ME',acquired=(first.reading,)).reason=='invalid_action'
    assert reader.read('MS',acquired=(first.reading,)).reading.ordinal==2


def test_whole_unit_capacity_rejection_never_truncates(reader):
    reader.tokenizer.native_context_tokens=reader.base_tokens+reader.output_reserve_tokens+1
    res=reader.read('MS')
    assert isinstance(res,K.ReadFailure) and res.reason=='capacity'
    assert res.input_tokens_unchanged==reader.base_tokens and not hasattr(res,'reading')
    assert reader.action_mask()==('STOP',)


def test_empty_and_no_legal_candidates(bank):
    prefix=bank.registry.prefix('p1','esc1024',0)
    reader=Reader(bank,prefix,FixtureTokenizer(),g_id='test',decode_id='test')
    assert reader.read('MS').reason=='unavailable'
    empty=B.Bank([],bank.registry,{},[])
    r=Reader(empty,prefix,FixtureTokenizer(),g_id='test',decode_id='test')
    assert r.read('MP').reason=='empty'


@pytest.mark.parametrize('field',['bank_version','index_version','renderer_id','g_id','decode_id','step2_id'])
def test_replay_rejects_every_identity_change(reader,field):
    success=reader.read('ME');key=reader.terminal_key([success])
    assert isinstance(reader.replay(key),K.ExecutionTrace)
    assert reader.replay(replace(key,**{field:'different-version'})).reason=='integrity'


def test_cross_owner_and_record_group_replay_rejected(reader):
    res=reader.read('ME');key=reader.terminal_key([res])
    assert reader.replay(replace(key,owner_id='p999')).reason=='owner'
    assert reader.replay(replace(key,acquired=(('not-the-selected-record',),))).reason=='integrity'


def test_all_16_real_subsets_preserve_get_order(reader):
    keys={}
    for size in range(5):
        for heads in itertools.combinations(K.HEAD_ORDER,size):
            for order in (heads,tuple(reversed(heads))):
                results=[]
                for head in order:
                    result=reader.read(head,acquired=tuple(r.reading for r in results))
                    assert isinstance(result,K.ReadSuccess);results.append(result)
                key=reader.terminal_key(results)
                trace=K.ExecutionTrace(domain_id='finite_head_v1',ordered_path=tuple('GET_'+h for h in order)+('STOP',),
                    acquired=tuple(r.record_ids for r in results),readings=tuple(r.reading for r in results))
                trace.verify_key(key)
                if heads in keys:assert keys[heads]==key
                keys[heads]=key
                assert isinstance(reader.replay(key),K.ExecutionTrace)
    assert len({k.sha256 for k in keys.values()})==16


def test_actual_b5_can_use_real_read_without_business_changes(reader):
    from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv,TerminalIdentity,TerminalTable,ReadRejected
    from metacom_pm.rl1v3.env.finite_head import PendingTerminal
    state_box={}
    def read(head):
        s=state_box['state']
        return reader.read(head,acquired=env.readings(s))
    env=C0FiniteHeadEnv(prefix=reader.prefix,history_sessions=reader.prefix.cutoff_rank,
        availability=reader.availability(),read=read,identity=TerminalIdentity(**reader.identity),
        table=TerminalTable({},table_id='unrun_generation'),prefix_tokens=reader.base_tokens)
    state_box['state']=env.reset()
    for head in K.HEAD_ORDER:
        state_box['state']=env.step(state_box['state'],'GET_'+head)[0]
    state=state_box['state'];trace=env.execution_trace(state);key=env.terminal_key(state)
    trace.verify_key(key);assert isinstance(reader.replay(key),K.ExecutionTrace)
    with pytest.raises(PendingTerminal):env.step(state,'STOP')  # no fabricated terminal reward
    assert len(env.observe(state).acquired)==4


def test_bank_load_detects_corruption_and_wrong_version(bank,tmp_path):
    B.save(bank,tmp_path);assert B.load(tmp_path,bank.registry,expected_version=bank.version).version==bank.version
    with pytest.raises(ValueError):B.load(tmp_path,bank.registry,expected_version='wrong')
    p=tmp_path/'index.json';obj=json.loads(p.read_text());obj['algorithm']='invented_graph';p.write_text(json.dumps(obj))
    with pytest.raises(ValueError):B.load(tmp_path,bank.registry)


def test_unverified_relation_cannot_enter_runtime(bank):
    changed=replace(bank.records[0],related_claim_ids=('invented-edge',))
    records=(changed,*bank.records[1:]);version=B._identity(records,bank.registry,bank.inputs)
    with pytest.raises(ValueError,match='graph propagation'):
        B.Bank([replace(r,bank_version=version) for r in records],bank.registry,bank.inputs,bank.ledger)
