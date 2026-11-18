"""Writer/summary/RS mechanism regressions; synthetic labels are NOT human data."""
from dataclasses import replace
from pathlib import Path
import json

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.compile import asof as A
from metacom_pm.rl1v3.compile.resource_candidates import MethodCandidate, CaseCandidate, fair_rs_inputs
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.io import canonical_json, write_json_once

ROOT = Path(__file__).resolve().parents[2]
WRITER = 'fixture-mechanism-not-human-review'


@pytest.fixture(scope='module')
def registry():
    return S.load(ROOT/'project/outputs/pm_rl1/v3/A1_preparation/final/registry')


def entry(registry, rank):
    return next(e for e in registry.entries if e.source.owner_id=='p1' and e.source.chronological_rank==rank)


def prefix(registry,rank):
    s=entry(registry,rank).source
    i=next(i for i,t in enumerate(s.turns[:-1]) if t.role=='seeker' and s.turns[i+1].role=='supporter')
    return registry.prefix('p1',s.session_id,i)


def claim(registry,rank,**kw):
    e=entry(registry,rank)
    i=next(i for i,t in enumerate(e.source.turns) if t.role=='seeker' and t.text)
    return A.record_from_source(e,kind=kw.pop('kind','MP'),refs=(S.span(e.source,i),),
        text=kw.pop('text','synthetic mechanism statement, not an annotation of this real quote'),
        subject='user',slot=kw.pop('slot','fixture_slot'),writer=WRITER,
        review_status=kw.pop('review_status','human_approved'),
        approval_ref='SYNTHETIC_UNIT_TEST_ONLY_NOT_A_REAL_HUMAN_APPROVAL',**kw)


@pytest.mark.parametrize('stage',A.STAGES)
def test_all_seven_event_stages_remain_distinct(registry,stage):
    row=claim(registry,0,kind='ME',stage=stage,slot=None)
    ledger=A.Ledger();ledger.append(row,registry)
    snap=A.materialize(registry,prefix(registry,1),ledger,writer=WRITER)
    assert snap['ledger_prefix'][0].stage==stage
    assert snap['ledger_prefix'][0].event_time is None


def test_approved_correction_known_late_and_ready_later_never_rewrites_old_snapshot(registry):
    old=claim(registry,0)
    correction=claim(registry,4,kind='RELATION',operation='UPDATE',target_id=old.record_id,
        known_at=K.TimePoint(session_rank=5),ready_at=K.TimePoint(session_rank=7),
        event_time=K.TimePoint(session_rank=2),valid_to=K.TimePoint(session_rank=2))
    ledger=A.Ledger();ledger.append(old,registry)
    before=A.materialize(registry,prefix(registry,4),ledger,writer=WRITER)
    ledger.append(correction,registry)
    assert before==A.materialize(registry,prefix(registry,4),ledger,writer=WRITER)
    at6=A.materialize(registry,prefix(registry,6),ledger,writer=WRITER)
    assert len(at6['ledger_prefix'])==1 and not at6['invalidations']
    at7=A.materialize(registry,prefix(registry,7),ledger,writer=WRITER)
    old_view=next(v for v in at7['views'] if v['record'].record_id==old.record_id)
    assert old_view['disposition']=='superseded'
    assert at7['invalidations'][0]['invalidated_knowledge_time'].session_rank==5
    assert at7['invalidations'][0]['fact_valid_to'].session_rank==2
    assert old.valid_to is None  # append-only, never edited retrospectively


def test_approved_contradiction_keeps_both_evidence_rows_and_blocks_single_value(registry):
    old=claim(registry,0)
    edge=claim(registry,1,kind='RELATION',operation='CONTRADICTS',target_id=old.record_id)
    ledger=A.Ledger();ledger.append(old,registry);ledger.append(edge,registry)
    snap=A.materialize(registry,prefix(registry,2),ledger,writer=WRITER)
    assert len(snap['ledger_prefix'])==2
    assert next(v for v in snap['views'] if v['record']==old)['disposition']=='conflict'


def test_unusable_summary_batch_replay_parent_and_explicit_raw_fallback(registry,tmp_path):
    e=entry(registry,0);raw=A.record_from_source(e,kind='MS_RAW',writer=WRITER)
    summary=claim(registry,0,kind='MS_SUM',slot=None,raw_parent_id=raw.record_id,review_status='unusable')
    stream=A.Ledger(tmp_path/'ledger');stream.append(raw,registry);stream.append(summary,registry)
    batch=A.Ledger()
    for row in stream.rows:batch.append(row,registry)
    p=prefix(registry,1);snap=A.materialize(registry,p,stream,writer=WRITER)
    assert snap==A.materialize(registry,p,batch,writer=WRITER)
    assert snap==A.materialize(registry,p,A.Ledger(tmp_path/'ledger'),writer=WRITER)
    fallback=A.summary_or_raw(snap,summary.record_id)
    assert fallback['condition']=='SUM_TO_RAW_FALLBACK' and fallback['selected_id']==raw.record_id
    assert fallback['view_identity']!=raw.record_id
    write_json_once(tmp_path/'snapshot.json',snap)
    restored=A.load_snapshot(tmp_path/'snapshot.json',expected_sha=snap['snapshot_sha'])
    assert canonical_json(restored)==canonical_json(snap)
    assert A.summary_or_raw(restored,summary.record_id)==fallback
    with pytest.raises(ValueError):A.load_snapshot(tmp_path/'snapshot.json',expected_sha='0'*64)


def test_sum_parent_wrong_session_rejected(registry):
    raw=A.record_from_source(entry(registry,0),kind='MS_RAW',writer=WRITER)
    bad=claim(registry,1,kind='MS_SUM',slot=None,raw_parent_id=raw.record_id)
    ledger=A.Ledger();ledger.append(raw,registry)
    with pytest.raises(ValueError,match='parent mismatch'):ledger.append(bad,registry)


def test_model_extractor_is_pending(registry):
    with pytest.raises(NotImplementedError,match='pending'):
        A.PendingExtractor().extract(entry(registry,0).source,{})


def test_rs_four_inputs_share_method_prefix_and_do_not_turn_f_into_off(registry):
    p=prefix(registry,3)
    m=MethodCandidate(name='fixture',source_url='https://example.org/fixture',source_section='test',
        source_quote='fixture quote',license_scope='test_only',when_to_use='fixture use',
        when_not_to_use='fixture avoid',action_options=('fixture action',),common_misuse='fixture misuse',
        limits='not a real method',external_version='fixture-v1',available_from='2026-11-18')
    case=CaseCandidate('fixture','fixture-family','fixture external conversation','a'*64,'test_only','train')
    rows=fair_rs_inputs(p,(m,),case,external_version='fixture-v1',experiment_date='2026-11-18')
    assert [r['arm'] for r in rows]==['R0','F-resident','METHOD','METHOD+CASE']
    assert rows[0]['extra_text']=='' and rows[1]['extra_text']
    assert rows[3]['extra_text'].startswith(rows[2]['extra_text']+'\n')
    assert all(r['runtime_callable'] is False and r['outcome'] is None for r in rows)
    assert len({r['input_identity'] for r in rows})==4
    with pytest.raises(ValueError):fair_rs_inputs(p,(m,),replace(case,family_id=p.family_id),external_version='fixture-v1',experiment_date='2026-11-18')
    with pytest.raises(ValueError):fair_rs_inputs(p,(m,),case,external_version='fixture-v1',experiment_date='2026-11-17')


def test_real_five_human_labels_remain_pending():
    path=ROOT/'project/outputs/pm_rl1/v3/asof_cpu_20261118/human_review/MANIFEST.json'
    report=json.loads(path.read_text())
    assert report['human_approved_count']==0 and len(report['items'])==5
    for i in range(1,6):
        row=json.loads((path.parent/f'item_{i:02d}_FULL_RAW.json').read_text())
        assert row['review_status']=='pending_human_review'
        ref=row['focus_span'];turn=row['source']['turns'][ref['turn_index']]
        assert ref['speaker']==turn['role']=='seeker'
        assert ref['exact_quote']==turn['text']
        assert '…' not in ref['exact_quote'] and '...' not in ref['exact_quote']
