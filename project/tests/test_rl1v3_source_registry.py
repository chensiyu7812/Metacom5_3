"""Real-data A1 acceptance, independent of B business code and model runtimes."""
from pathlib import Path
import dataclasses
import json
import pytest
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import canonical_json

ROOT=Path(__file__).resolve().parents[2]

@pytest.fixture(scope='module')
def registry():return S.build(ROOT)


def test_real_source_counts_and_families(registry):
    assert len(registry.entries)==1276
    assert sum(e.source.dataset==S.DATASET for e in registry.entries)==401
    assert sum(e.source.dataset=='ESConv' for e in registry.entries)==875
    assert len(registry.rejected)==425 and len(registry.excluded_families)==84
    a=registry.entry('p13','esc1198');b=registry.entry('p18','esc1198')
    assert a.source_id!=b.source_id and a.source.transcript_sha256==b.source.transcript_sha256
    assert a.source.family_id==b.source.family_id=='esconv:esconv_1198'
    assert a.fold==b.fold==2


def test_every_b0_prefix_identity_and_visible_history(registry):
    rows=[json.loads(l) for l in (ROOT/'project/outputs/pm_rl1/v3/B0/prefix_census.jsonl').read_text().splitlines()]
    assert len(rows)==4119
    for row in rows:
        p=registry.prefix(row['owner_id'],row['session_id'],row['cut_turn'])
        assert p.prefix_id==row['prefix_id']
        visible=registry.visible(p)
        assert len(visible)==p.cutoff_rank
        assert all(e.source.owner_id==p.owner_id and e.source.chronological_rank<p.cutoff_rank for e in visible)


def test_original_turns_and_indices_are_lossless(registry):
    runtime=json.loads((ROOT/'project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json').read_text())
    for user in runtime['users']:
        for old in user['sessions']:
            entry=registry.entry(user['owner_id'],old['session_id'])
            assert [(t.role,t.text) for t in entry.source.turns]==[(t['role'],t['content']) for t in old['turns']]
            assert entry.original_turn_indices==tuple(t['idx'] for t in old['turns'])
            for i,t in enumerate(entry.source.turns):
                if t.text:S.span(entry.source,i).verify(entry.source)


def test_runtime_has_no_privileged_fields(registry):
    payload=json.loads(canonical_json(registry.entries))
    forbidden={'question_groups','summaries','subsequent_topics','basic_info','survey_score','annotation','situation'}
    def walk(value):
        if isinstance(value,dict):
            assert not (set(value)&forbidden)
            for child in value.values():walk(child)
        elif isinstance(value,list):
            for child in value:walk(child)
    walk(payload)


@pytest.mark.parametrize('bad', ['owner','time','family','fold','future_text'])
def test_context_tampering_rejected(registry,bad):
    p=registry.prefix('p1','p1_conv_1',0)
    changes={'owner':dict(owner_id='p2'),'time':dict(timestamp='2099-01-01'),
        'family':dict(ancestor_family_ids=(p.family_id,'foreign:family')),'fold':dict(fold=3),
        'future_text':dict(turns=(K.SourceTurn(turn_index=0,role='seeker',text='not the source'),))}[bad]
    kwargs=json.loads(canonical_json(p));kwargs.pop('prefix_id');kwargs.pop('schema_version')
    kwargs['turns']=p.turns;kwargs['ancestor_family_ids']=p.ancestor_family_ids;kwargs.update(changes)
    with pytest.raises((ValueError,KeyError)):registry.context(K.PrefixSpec.create(**kwargs))


def test_owner_future_and_family_fail_closed(registry):
    p=registry.prefix('p1','p1_conv_1',0)
    assert registry.reason(registry.entry('p2','p2_conv_1').source_id,p)=='owner'
    assert registry.reason(registry.entry('p1','p1_conv_1').source_id,p)=='future_source'
    assert registry.reason(registry.entry('p1','esc1024').source_id,p,rs=True)=='non_train_source'
    assert all(not ({e.source.family_id}&registry.excluded_families) for e in registry.visible(p,rs=True))


def test_source_dates_are_not_event_or_writer_timestamps(registry):
    e=registry.entry('p1','esc1024')
    assert e.reported_at==K.TimePoint(date='2024-06-30',session_rank=0)
    assert e.ready_at==K.TimePoint(session_rank=1)
    assert all(e.reported_at is None and e.ready_at is None for e in registry.entries if e.source.dataset=='ESConv')


def test_invalidation_is_versioned_not_retroactive(registry):
    e=registry.entry('p1','esc1024');evidence=(S.span(registry.entry('p1','p1_conv_1').source,0),)
    changed=registry.invalidate(e.source_id,known_at=K.TimePoint(session_rank=5),evidence=evidence)
    before=registry.prefix('p1','p1_conv_1',0)
    later=next(e.source for e in registry.entries if e.source.owner_id=='p1' and e.source.chronological_rank==5)
    cut=next(i for i,t in enumerate(later.turns[:-1]) if t.role=='seeker' and later.turns[i+1].role=='supporter')
    after=registry.prefix('p1',later.session_id,cut)
    assert changed.version!=registry.version
    assert changed.reason(e.source_id,before) is None
    assert changed.reason(e.source_id,after)=='invalidated'
    assert registry.reason(e.source_id,after) is None
    assert changed.invalidate(e.source_id,known_at=K.TimePoint(session_rank=5),evidence=evidence) is changed


def test_invalid_invalidation_has_no_effect(registry):
    e=registry.entry('p1','esc1024')
    with pytest.raises(ValueError):registry.invalidate(e.source_id,known_at=K.TimePoint(session_rank=5),evidence=())
    with pytest.raises(ValueError):registry.invalidate(e.source_id,known_at=K.TimePoint(session_rank=5),
         evidence=(S.span(registry.entry('p2','p2_conv_1').source,0),))


def test_registry_rebuild_and_no_overwrite(registry,tmp_path):
    assert S.build(ROOT).version==registry.version
    S.save(registry,tmp_path);restored=S.load(tmp_path)
    assert canonical_json(restored.entries)==canonical_json(registry.entries)
    S.save(registry,tmp_path)
    (tmp_path/'sources.jsonl').write_text('corrupt\n')
    with pytest.raises(ValueError):S.load(tmp_path)
    with pytest.raises(FileExistsError):S.save(registry,tmp_path)


def test_unpinned_input_cannot_be_consumed():
    with pytest.raises(ValueError):S.PinnedInputs(ROOT).path('project/pyproject.toml')


def test_snapshot_operations_do_not_mutate_raw(registry):
    assert {r['operation'] for r in S.changes(None,registry)}=={'ADD'}
    assert {r['operation'] for r in S.changes(registry,registry)}=={'NOOP'}
    e=registry.entries[0]
    from dataclasses import replace
    new_source=replace(e.source,license='test_explicit_revised_terms')
    updated=replace(e,source=new_source,source_id=S._source_id(new_source))
    other=S.Registry((updated,*registry.entries[1:]),inputs=registry.inputs,folds=registry.folds,
                     excluded_families=registry.excluded_families,rejected=registry.rejected)
    changes=[r for r in S.changes(registry,other) if r['operation']!='NOOP']
    assert len(changes)==1 and changes[0]['operation']=='UPDATE'
    assert registry.entries[0].source.license!=other.entries[0].source.license
