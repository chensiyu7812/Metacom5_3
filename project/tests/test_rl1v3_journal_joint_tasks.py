"""Real source/AsOf and runtime/evaluator separation; no generated outcomes."""
import copy
import json
import os
from pathlib import Path

import pytest

from metacom_pm.rl1v3.io import file_sha256, object_sha256
from metacom_pm.rl1v3.journal import joint_tasks as J
from metacom_pm.rl1v3.sources import source_registry as S

ROOT=os.environ.get('JOURNAL_JOINT_BUNDLE')


def test_multiple_or_approved_procedure_candidates_are_rejected():
    for changes in [dict(number_of_new_procedures=2),dict(professional_approval=True),dict(case_examples=[{'fixture':True}])]:
        design=dict(number_of_new_procedures=1,professional_approval=False,case_examples=[]);design.update(changes)
        with pytest.raises(ValueError,match='one unapproved'):J.procedure(design,'unused')


@pytest.fixture
def bundle():
    if not ROOT:pytest.skip('actual private joint source bundle not supplied')
    p=Path(ROOT);manifest=json.loads((p/'MANIFEST.json').read_text())
    for name,h in manifest['files_sha256'].items():assert file_sha256(p/name)==h
    read=lambda name:[json.loads(x) for x in (p/name).read_text().splitlines()]
    registry_path=Path(next(k for k in manifest['inputs_sha256'] if k.endswith('/registry.json'))).parent
    return p,read,S.load(registry_path),manifest


def test_actual24_balanced_with_six_dependent_sources(bundle):
    p,read,registry,m=bundle;tasks=read('TASKS.runtime.jsonl');strata=read('DEMAND_STRATA.private.jsonl');envelopes=read('TASK_ENVELOPES.private.jsonl')
    assert len(tasks)==len({t['task_id'] for t in tasks})==24
    assert J.Counter(s['stratum'] for s in strata)=={s:6 for s in J.STRATA}
    assert len({s['owner_family'] for s in strata})==6
    assert len({e['asof_runtime_sha256'] for e in envelopes})==6
    assert all(s['source_split']=='train' and s['expected_need_is_not_forced_call_label'] for s in strata)


def test_original_prefix_identity_and_all_source_evidence_are_real_strict_past(bundle):
    p,read,registry,m=bundle;bindings=json.loads((p/'SOURCE_BINDINGS.private.json').read_text())
    for b in bindings:
        e=registry.entry(b['owner_id'],b['source_session_id'])
        prefix=registry.prefix(b['owner_id'],b['asof_prefix']['session_id'],b['asof_prefix']['cut_turn'])
        assert J.canonical(prefix)==b['asof_prefix'] and prefix.runtime_sha256==b['asof_runtime_sha256']
        assert registry.reason(e.source_id,prefix) is None and e.source.chronological_rank<prefix.cutoff_rank
        t=e.source.turns[b['source_turn_index']]
        assert t.role=='seeker' and t.text==b['exact_quote']
        assert e.original_turn_indices[b['source_turn_index']]==b['original_turn_index']
        assert e.ready_at.session_rank<=prefix.cutoff_rank
        assert registry.reason(registry.entry(prefix.owner_id,prefix.session_id).source_id,prefix)=='future_source'


def test_constructed_visible_view_is_separate_and_does_not_leak_private_evaluation(bundle):
    p,read,registry,m=bundle;tasks={r['task_id']:r for r in read('TASKS.runtime.jsonl')};evs=read('EVALSPEC.private.jsonl')
    for e in read('TASK_ENVELOPES.private.jsonl'):
        t=tasks[e['task_id']]
        assert set(t)==J.RUNTIME_KEYS and t['query']==t['turns'][-1]['text']
        assert e['visible_task_sha256']==object_sha256(t) and e['visible_task']==t
        assert 'needs_stratum_private' not in json.dumps(e) and 'personal_fact_references' not in json.dumps(e)
        assert e['actual_prefix']['turns']!=t['turns']
    for ev in evs:
        t=tasks[ev['task_id']];quote=ev['source_binding']['exact_quote']
        assert (quote in t['query'])==ev['fact_available_in_current_view']
        assert ev['formal_reward'] is None and ev['assistant_authored_not_independent_human_reference']
        assert ev['evaluation_rules']['support'].endswith('No criterion requires a particular head, call, or selected method.')


def test_one_real_source_bound_procedure_available_even_when_not_applicable(bundle):
    p,read,registry,m=bundle;rows=read('RS_PROCEDURE.private.jsonl')
    assert len(rows)==1;row=rows[0]
    assert row['legally_available_independent_of_applicability'] is True
    assert row['professional_approval'] is False and not row['case_examples']
    assert len(row['procedure'])==5 and len(row['source_refs'])==9
    assert {r['section'] for r in row['source_refs']}=={'ch6.s2.1'}
    for path,h in m['source_documents_sha256'].items():assert file_sha256(path)==h
    assert all(step in row['reading_text'] for step in row['procedure']+row['stop_conditions'])


def test_outcomes_unread_and_original_splits_not_reassigned(bundle):
    p,read,registry,m=bundle;s=json.loads((p/'SUMMARY_PUBLIC.json').read_text())
    assert m['generated_output_files_read']==s['current_TS_outcomes_read']==s['new_model_calls']==0
    assert s['tasks']==24 and s['max_logical_generations']==96
    for e in read('TASK_ENVELOPES.private.jsonl'):
        assert registry.folds['historical_rl1_split'][e['owner_id']]=='train'
        assert e['actual_prefix']['fold']==registry.folds['fold_of_owner'][e['owner_id']]
