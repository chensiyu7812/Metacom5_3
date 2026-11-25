"""Synthetic closeout fixtures; no real source, QA answer or output included."""
import json
from copy import deepcopy

import pytest

from metacom_pm.rl1v3.journal.closeout_memory import (
    check_update, combined_representation_aggregate, navigation_digest,
    paired_representation_changes, parse_update, per_task_representation_table, validate_update_review)


def fixture():
    inventory=dict(sessions=[dict(session_id='fixture',reported_date='2032-04-05',turns=[
        dict(turn=2,speaker='seeker',text='I might start a small puzzle.'),
        dict(turn=3,speaker='supporter',text='Taking a break is one option.')])])
    value=dict(records=[dict(kind='ME',source_session='fixture',turn=2,speaker='seeker',
        exact_quote='I might start a small puzzle.',reported_date='2032-04-05',
        slot_or_event='puzzle',stage='intended',relation='append')],coverage='partial')
    return inventory,value


def test_exact_source_check_does_not_establish_stage_truth():
    inv,value=fixture();value['records'][0]['stage']='completed'
    check=check_update(json.dumps(value),inv)
    assert check['primary_mechanical_status']=='pass'
    assert check['records'][0]['stage_enum_is_not_stage_semantics']
    assert not check['semantic_approved'] and check['reward'] is None


@pytest.mark.parametrize('field,new,error',[
    ('source_session','absent','source_session_not_supplied'),
    ('turn',True,'source_turn_not_supplied'),
    ('speaker','supporter','speaker'),
    ('reported_date','2032-04-06','reported_date'),
    ('exact_quote','I started a small puzzle.','non_exact_quote_at_specified_turn'),
    ('exact_quote','','non_exact_quote_at_specified_turn'),
    ('stage','finished','ME_stage_enum'),
    ('relation','replace','relation_enum')])
def test_update_metadata_and_contract_errors(field,new,error):
    inv,value=fixture();value['records'][0][field]=new
    check=check_update(json.dumps(value),inv)
    assert check['primary_mechanical_status']=='fail'
    assert error in check['records'][0]['errors']


def test_cpu_prior_missing_supporter_turn_is_not_supplied():
    inv,value=fixture();inv['sessions'][0]['turns']=inv['sessions'][0]['turns'][:1]
    value['records'][0].update(turn=3,speaker='supporter',exact_quote='Taking a break is one option.')
    assert 'source_turn_not_supplied' in check_update(json.dumps(value),inv)['records'][0]['errors']


def test_fence_sensitivity_preserves_primary_parse_failure():
    inv,value=fixture();check=check_update('```json\n'+json.dumps(value)+'\n```',inv)
    assert check['schema_and_source_status']=='pass'
    assert check['primary_mechanical_status']=='fail'
    assert check['parse']['sensitivity']=='outer_fence_only'


def test_no_duplicate_keys_or_json_with_commentary_repair():
    assert parse_update('{"records":[],"records":[]}')['strict_parse_status']=='fail'
    assert parse_update('Here it is: {"records":[]}')['value'] is None


def test_record_count_and_coverage_contract():
    inv,value=fixture();value['records']*=2;value['coverage']='complete'
    check=check_update(json.dumps(value),inv)
    assert set(check['errors'])=={'more_than_one_per_kind','coverage_not_partial'}


def test_manual_review_field_binding_and_no_reward():
    inv,value=fixture();checked=check_update(json.dumps(value),inv)
    review=dict(records=[dict(record_index=0,output_field_evidence=[dict(field='stage',value='intended')])],formal_semantic_status='uncertain',reward=None)
    assert validate_update_review(review,checked,json.dumps(value))
    wrong=deepcopy(review);wrong['records'][0]['output_field_evidence'][0]['value']='completed'
    with pytest.raises(ValueError):validate_update_review(wrong,checked,json.dumps(value))


def test_combined_counts_exclude_unknown_gold_from_eligible_denominator():
    audits={'t':dict(atoms=[dict(atom_id='a',required=True,status_end_history='supported'),dict(atom_id='b',required=True,status_end_history='unknown')])}
    rows=[]
    for arm in ('RAW','SPAN','TYPED_OR_SUM'):
        rows.append(dict(task_id='t',arm=arm,atoms=[dict(atom_id='a',observed='complete',delivery='full'),dict(atom_id='b',observed='uncertain',delivery='uncertain')],technical=dict(input_tokens=10,output_tokens=3,seconds=1)))
    agg=combined_representation_aggregate(rows,audits)['by_arm']['RAW']
    assert agg['original_required_atom_presentations']==2 and agg['supported_or_calendar_atom_presentations']==1
    assert agg['unresolved_gold_observations']=={'uncertain':1}
    assert all(not x['repaired_atom_ids'] and not x['newly_incomplete_atom_ids'] for x in paired_representation_changes(rows,audits))


def test_navigation_wrapper_preserves_original_and_is_not_semantic_promotion():
    original='seeker: I might start a small puzzle.'
    one=navigation_digest(original,raw_pointer='fixture-record')
    two=navigation_digest(one['text'],raw_pointer='fixture-record')
    assert one['text'].startswith(original) and one['incomplete_marker_added']
    assert not two['incomplete_marker_added'] and two['text']==one['text']
    assert not one['semantic_approved'] and not one['semantic_content_improved']
    with pytest.raises(ValueError):navigation_digest(original,raw_pointer='')


def test_unknown_only_task_never_passes_by_empty_conjunction():
    audits={'unknown-only':dict(atoms=[dict(atom_id='a',required=True,status_end_history='unknown')])}
    rows=[dict(task_id='unknown-only',arm='RAW',atoms=[dict(atom_id='a',delivery='uncertain',observed='uncertain')],technical=dict(input_tokens=2,output_tokens=1,seconds=.1))]
    assert combined_representation_aggregate(rows,audits)['by_arm']['RAW']['complete_on_supported_atoms_tasks']==0
    table=per_task_representation_table(rows,audits)[0]
    assert table['supported_or_calendar_atoms']==0 and table['unresolved_reference_atoms']==1
    assert not table['arms']['RAW']['complete_on_supported_atoms']
    assert set(table)=={'task_id','original_required_atoms','supported_or_calendar_atoms','unresolved_reference_atoms','unresolved_reference_statuses','arms','formal_semantic_status','reward'}
