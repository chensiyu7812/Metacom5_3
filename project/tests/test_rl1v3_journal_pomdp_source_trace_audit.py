"""Delivery/provenance is neither inferred semantics nor resolved uncertainty."""
import json,os
from pathlib import Path
import pytest
from metacom_pm.rl1v3.journal import pomdp_source_trace_audit as A
from metacom_pm.rl1v3.io import file_sha256


def span(turn,text):
    return dict(owner_id='synthetic-owner',session_id='synthetic-session',turn_index=turn,start_char=0,
        end_char=len(text),raw_turn_sha256='synthetic-hash-'+str(turn),exact_quote=text)


def test_context_group_needs_the_user_reply_and_antecedent():
    a,b=span(0,'Synthetic question about an activity.'),span(1,'Synthetic reported response.')
    atoms=[dict(atom_id='a',kind='reported_fact',evidence_groups=[dict(spans=[a,b])])]
    assert not A.delivered_groups(atoms,{A.span_key(a)},'')[0]['source_group_present']
    assert A.delivered_groups(atoms,{A.span_key(a),A.span_key(b)},'')[0]['source_group_present']


def test_matching_all_unknown_boundary_quotes_does_not_resolve_it():
    s=span(0,'Synthetic reported plan.')
    atoms=[dict(atom_id='u',kind='unresolved_boundary',evidence_groups=[dict(spans=[s])])]
    row=A.delivered_groups(atoms,{A.span_key(s)},'')[0]
    assert row['source_group_present'] and row['semantic_boundary_resolved'] is None


def test_metadata_is_observed_but_is_not_a_source_body_clue():
    row=A.query_provenance('goal Reported example','goal','example','Reported example')
    assert row['added_body_terms']==['example'] and row['added_metadata_only_terms']==['reported']


def test_unread_gold_word_is_rejected_by_independent_query_audit():
    with pytest.raises(ValueError,match='unobserved'):
        A.query_provenance('goal hiddenanswer','goal','visible body','Reported visible body')


def test_current_exact_quote_counts_without_a_retrieval_action():
    s=span(0,'Synthetic complete note.')
    atoms=[dict(atom_id='a',kind='reported_fact',evidence_groups=[dict(spans=[s])])]
    assert A.delivered_groups(atoms,set(),'Use this: Synthetic complete note.')[0]['source_group_present']


@pytest.fixture
def actual():
    root=os.environ.get('POMDP_SOURCE_CASES_PRIVATE')
    if not root:pytest.skip('actual post-trace private artifacts not supplied')
    p=Path(root)/'trace-audit-v1';m=json.loads((p/'MANIFEST.json').read_text())
    for name,h in m['files_sha256'].items():assert file_sha256(p/name)==h
    return p,A.rows(p/'DELIVERY_AND_QUERY_PRIVATE.jsonl'),json.loads((p/'SUMMARY_PUBLIC.json').read_text())


def test_actual_all80_paths_preserve_query_source_and_unknown_status(actual):
    p,rows,s=actual
    assert len(rows)==80 and len({r['task_id'] for r in rows})==16
    assert all(r['query_integrity_passed'] and r['whole_legal_pool_preserved'] for r in rows)
    assert all(r['model_calls']==0 and r['formal_reward'] is None and r['task_success'] is None for r in rows)
    for row in rows:
        for atom in row['final_source_delivery']:
            if atom['kind']=='unresolved_boundary':assert atom['semantic_boundary_resolved'] is None
    assert s['unique_legal_source_sessions']==54


def test_actual_full_parent_adds_source_context_without_claiming_adaptive_value(actual):
    p,rows,s=actual
    assert sum(r['EXPAND_reported_groups'] for r in rows)>0
    assert s['policies']['SequentialRule']['additional_SEARCH_reported_groups']==0
    assert s['policies']['FixedTopK']['fact_required_supplied']==s['policies']['SequentialNoText']['fact_required_supplied']
    assert s['supply_is_not_task_success'] and s['static_rule_does_not_test_full_POMDP_optimality']


def test_actual_current_sufficient_pair_remains_no_read_control(actual):
    p,rows,s=actual
    control=[r for r in rows if r['case_id']=='P08']
    assert len(control)==10 and all(r['diagnostic_reported_supplied']==1 for r in control)
    stop=[r for r in control if r['policy']=='STOP']
    assert len(stop)==2 and all(r['charged_delivery_tokens']==0 for r in stop)
    assert all(r['canonical_input_tokens']>next(t['canonical_input_tokens'] for t in stop if t['goal_kind']==r['goal_kind']) for r in control if r['policy']!='STOP')


def test_static_pressure_keeps_operation_domain_difference_explicit(actual):
    p,rows,s=actual
    report=json.loads((p.parent/'top4-audit-v1/COMPARISON_PUBLIC.json').read_text())
    top=report['comparison']['FixedTop4WholeStress']
    assert top['fact_required_supplied']==14 and top['fact_required_slots']==16
    assert top['primitive_operations_per_goal']==5 and top['original_primitive_cap']==4
    assert not top['action_matched'] and report['no_action_matched_effect_claim']
    assert report['original_paths_preserved']==80 and report['new_G_calls']==0


def test_static_macro_does_not_resolve_reference_unknowns(actual):
    p,rows,s=actual
    for row in A.rows(p.parent/'top4-audit-v1/TOP4_SOURCE_DELIVERY_PRIVATE.jsonl'):
        assert row['formal_reward'] is None and row['task_success'] is None
        for atom in row['source_delivery']:
            if atom['kind']=='unresolved_boundary':assert atom['semantic_boundary_resolved'] is None
