"""Source-case separation and exact evidence checks; no model outputs."""
import copy,json,os
from pathlib import Path
import pytest
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import file_sha256,object_sha256,canonical_json,decode_contract
from metacom_pm.rl1v3.journal import pomdp_source_cases as P


def source_selection():
    kinds=['distributed_facts','real_update','plan_execution_unknown','current_sufficient']
    cases=[dict(case_id='synthetic-'+str(i),primary_type=k) for i,k in enumerate(kinds)]
    sel=dict(retrieval_results_seen=False,new_G_outputs_seen=False,authorized_G_calls=0,
        strata={c['primary_type']:[c['case_id']] for c in cases},selected_case_ids=[c['case_id'] for c in cases])
    return sel,cases


def test_selection_is_source_only_and_has_distinct_required_strata():
    sel,cases=source_selection();assert P.source_only_selection(sel,cases)==set(sel['selected_case_ids'])
    for flag in ['retrieval_results_seen','new_G_outputs_seen']:
        bad=copy.deepcopy(sel);bad[flag]=True
        with pytest.raises(ValueError,match='pre-outcome'):P.source_only_selection(bad,cases)


def test_outcome_chosen_or_reclassified_case_is_rejected():
    sel,cases=source_selection();bad=copy.deepcopy(sel);bad['selected_case_ids'][0]='synthetic-foreign'
    with pytest.raises(ValueError,match='selection changed'):P.source_only_selection(bad,cases)
    bad=copy.deepcopy(cases);bad[0]['primary_type']='different'
    with pytest.raises(ValueError,match='stratum mismatch'):P.source_only_selection(sel,bad)


def test_current_prefix_evidence_must_be_delivered_in_current_query():
    group=dict(source_status='current_prefix',spans=[dict(exact_quote='Synthetic current report.')])
    P.verify_current_delivery([group],'Please use this: Synthetic current report.')
    with pytest.raises(ValueError,match='not actually'):P.verify_current_delivery([group],'An unrelated visible goal.')


@pytest.fixture
def actual():
    root=os.environ.get('POMDP_SOURCE_CASES_PRIVATE')
    if not root:pytest.skip('bounded private source bundle not supplied')
    p=Path(root);b=p/'bundle-v1';manifest=json.loads((b/'MANIFEST.json').read_text())
    for name,h in manifest['files_sha256'].items():assert file_sha256(b/name)==h
    design=json.loads((p/'SOURCE_DESIGN_V2_PRIVATE.json').read_text())
    resources=next(k for k in design['source_inputs_sha256'] if k.endswith('resources_private.jsonl'))
    metadata=next(k for k in design['source_inputs_sha256'] if k.endswith('registry.json'))
    registry=P.load_bounded_registry(resources,metadata,design)
    read=lambda name:[json.loads(line) for line in (b/name).read_text().splitlines()]
    return p,b,read,registry,design


def test_actual_source_recipe_is_finite_and_old_splits_preserved(actual):
    p,b,read,registry,design=actual;strata=read('STRATA.private.jsonl')
    assert len(strata)==16 and len({x['case_id'] for x in strata})==8
    assert P.Counter(x['goal_kind'] for x in strata)=={'fact':8,'natural_support':8}
    assert len({x['family_component'] for x in strata})==3
    assert all(x['original_fold']!=6 and x['original_split']==registry.folds['historical_rl1_split'][x['owner_id']] for x in strata)
    assert len(registry.entries)==91


def test_actual_full_legal_pools_have_no_targeted_source_removal(actual):
    p,b,read,registry,design=actual;envelopes={x['task_id']:x for x in read('TASK_ENVELOPES.private.jsonl')}
    for pool in read('FULL_LEGAL_POOLS.private.jsonl'):
        env=envelopes[pool['task_id']];prefix=decode_contract(K.PrefixSpec,canonical_json(env['actual_prefix']))
        assert prefix.runtime_sha256==env['asof_runtime_sha256']
        legal=sorted((e for e in registry.entries if e.source.owner_id==prefix.owner_id and registry.reason(e.source_id,prefix) is None),key=lambda e:e.source.chronological_rank)
        assert [e.source_id for e in legal]==pool['source_ids'] and len(legal)==pool['legal_count']
        assert pool['no_manual_source_removal']
        assert all(e.source.chronological_rank<prefix.cutoff_rank for e in legal)


def test_actual_spans_owner_role_date_and_current_delivery(actual):
    p,b,read,registry,design=actual;tasks={x['task_id']:x for x in read('TASKS.runtime.jsonl')}
    for ev in read('EVALSPEC.private.jsonl'):
        binding=ev['source_binding'];prefix=decode_contract(K.PrefixSpec,canonical_json(binding['actual_prefix']))
        for atom in binding['atoms']:
            for group in atom['evidence_groups']:
                entry=registry.entry(group['owner_id'],group['session_id'])
                assert group['owner_id']==prefix.owner_id and group['source_id']==entry.source_id
                assert group['reported_at']['date']==entry.source.date
                for raw in group['spans']:
                    span=decode_contract(K.SourceSpan,canonical_json(raw));span.verify(entry.source)
                    assert entry.source.turns[span.turn_index].role==span.speaker
                if group['source_status']=='current_prefix':
                    assert all(s['turn_index']<=prefix.cut_turn and s['exact_quote'] in tasks[ev['task_id']]['query'] for s in group['spans'])
                else:assert registry.reason(entry.source_id,prefix) is None


def test_actual_runtime_excludes_reference_and_clue_hypotheses(actual):
    p,b,read,registry,design=actual
    for task in read('TASKS.runtime.jsonl'):
        assert set(task)==P.RUNTIME_KEYS
        assert task['query']=='\n'.join(x['text'] for x in task['turns'])
    for env in read('TASK_ENVELOPES.private.jsonl'):
        assert object_sha256(env['visible_task'])==env['visible_task_sha256']
        assert not {'atoms','source_binding','source_clue_hypothesis','required_fact_ids'} & set(env)
    for ev in read('EVALSPEC.private.jsonl'):
        assert ev['formal_reward'] is None
        if ev['goal_kind']=='natural_support':assert not ev['required_fact_ids']
        unresolved={a['atom_id'] for a in ev['source_binding']['atoms'] if a['kind']=='unresolved_boundary'}
        assert not unresolved & set(ev['required_fact_ids'])


def test_actual_future_subset_is_prefixed_source_strata_not_first_cases(actual):
    p,b,read,registry,design=actual;sel=json.loads((p/'G_SELECTION_SOURCE_ONLY_PRIVATE.json').read_text())
    selected=P.source_only_selection(sel,design['cases'])
    assert selected=={'P02','P05','P06','P08'}
    future=json.loads((b/'FUTURE_G_SELECTION_PRIVATE.json').read_text())
    assert len(future['selected_task_ids'])==8 and future['authorized'] is False
    assert not future['retrieval_results_seen'] and not future['new_G_outputs_seen']
    strata={x['task_id']:x for x in read('STRATA.private.jsonl')}
    assert {strata[t]['case_id'] for t in future['selected_task_ids']}==selected
    assert P.Counter(strata[t]['goal_kind'] for t in future['selected_task_ids'])=={'fact':4,'natural_support':4}
