"""Synthetic evidence tests: no real dialogue, answer or private review fixture."""
from copy import deepcopy
import pytest

from metacom_pm.rl1v3.journal.keycap_memory_review import (
    INCOMPLETE, check_reference, reference_mutations, source_sentence_units,
    validate_m1_manual, validate_writer_manual, writer_quote_screen)


def source():
    return dict(source=dict(owner_id='fixture-owner',session_id='fixture-session'), reported_date='2031-02-03',
        turns=[dict(turn=0,speaker='seeker',text='I might try the puzzle. I have not started.'),
               dict(turn=1,speaker='supporter',text='A small first step could help.')])


def test_exact_quotes_preserve_role_and_offsets_but_do_not_approve():
    result=writer_quote_screen('seeker: I have not started.',source())
    q=result['quotes'][0]
    assert result['mechanical_status']=='pass' and not result['semantic_approved']
    loc=q['locations'][0]
    assert source()['turns'][0]['text'][loc['start_char']:loc['end_char']]==q['text']
    assert result['reward'] is None


@pytest.mark.parametrize('text,error',[
    ('supporter: I have not started.','speaker_mismatch'),
    ('seeker: I have started.','non_exact_or_unsupported_quote'),
    ('seeker: "I have not started."','non_exact_or_unsupported_quote'),
    ('A prose summary.','unparsed_line')])
def test_bad_or_normalized_quotes_fail_strict_screen(text,error):
    assert error in writer_quote_screen(text,source())['errors']


def test_marker_and_sentence_inventory_are_separate_from_exactness():
    partial=writer_quote_screen('seeker: I might try the puzzle.',source())
    marked=writer_quote_screen('seeker: I might try the puzzle.\n'+INCOMPLETE,source())
    assert partial['mechanical_status']==marked['mechanical_status']=='pass'
    assert not partial['incomplete_marker_present'] and marked['incomplete_marker_present']
    assert len(source_sentence_units(source()))==3


def test_four_reference_variants_check_actual_fields():
    rows=reference_mutations(source(),0)
    assert [check_reference(r['answer'],source())['structural_status'] for r in rows]==['pass','fail','fail','fail']
    assert [check_reference(r['answer'],source())['errors'] for r in rows][1:]==[['speaker'],['reported_date'],['quote_offset_text_mismatch']]


@pytest.mark.parametrize('field,value',[('turn',True),('start_char',False),('end_char',999),('owner_id','other'),('event_stage','completed')])
def test_reference_rejects_invalid_types_bounds_identity_and_stage(field,value):
    answer=reference_mutations(source(),0)[0]['answer'];answer[field]=value
    assert check_reference(answer,source())['structural_status']=='fail'


def test_review_requires_all_atoms_exact_quotes_and_no_reward():
    audit=dict(task_id='task',atoms=[dict(atom_id='a',required=True)])
    joined=dict(request_id='request',request=dict(model_input=dict(messages=[dict(content='I might try the puzzle.'),dict(content='Question')])),output=dict(text='The activity is still planned.'))
    review=dict(request_id='request',task_id='task',atoms=[dict(atom_id='a',observed='complete',delivery='full',output_quotes=['still planned'],delivered_source_quotes=[dict(quote='I might try the puzzle.')])],formal_semantic_status='uncertain',reward=None)
    assert validate_m1_manual(review,joined,audit)
    for changed in [dict(atoms=[]),dict(reward=1),dict(atoms=[{**review['atoms'][0],'output_quotes':['already completed']}])]:
        with pytest.raises(ValueError):validate_m1_manual({**review,**changed},joined,audit)


def test_writer_review_cannot_drop_omitted_source_proposition():
    inventory=dict(propositions=[dict(proposition_id='p'),dict(proposition_id='q')])
    review=dict(propositions=[dict(proposition_id='p',observed='retained',output_quotes=['planned']),dict(proposition_id='q',observed='omitted',output_quotes=[])],formal_semantic_status='uncertain',reward=None)
    assert validate_writer_manual(review,inventory,'planned')
    broken=deepcopy(review);broken['propositions'].pop()
    with pytest.raises(ValueError):validate_writer_manual(broken,inventory,'planned')
