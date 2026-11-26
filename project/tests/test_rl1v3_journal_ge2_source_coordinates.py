from copy import deepcopy
import pytest
from metacom_pm.rl1v3.journal import ge2_source_coordinate_audit as A


def fixture():
    text='Synthetic café 🧪 report.'
    def turn(i,role):return dict(turn_index=i,speaker=role,exact_quote=text,start_char=0,end_char=len(text),raw_turn_sha256=A.text_sha(text))
    record=dict(record_id='synthetic:r1',owner_id='synthetic-owner',parent_session_id='synthetic-session',
                source_refs=[turn(0,'supporter'),turn(1,'seeker'),turn(2,'seeker')])
    ref=dict(record_id=record['record_id'],owner_id=record['owner_id'],session_id=record['parent_session_id'],
             turn_index=1,speaker='seeker',start_char=0,end_char=len(text),exact_quote=text,current_visible=False)
    atom=dict(id='synthetic:a',requirement_role='explicit_answer',sufficient_groups=[[ref]])
    task=dict(task_id='synthetic-task',turns=[dict(role='seeker',text='Synthetic visible question?')])
    return record,ref,atom,task


def test_wrong_speaker_same_words_are_not_historical_supply():
    record,ref,atom,task=fixture()
    strict=A.strict_supply([atom],[record],{'synthetic:r1':[[0,0]]},task)
    legacy=A.legacy_supply([atom],[dict(record_id='synthetic:r1',text=ref['exact_quote'])],'')
    assert legacy['covered_slots']==1 and strict['covered_slots']==0


def test_other_original_turn_same_speaker_same_words_cannot_replace_named_turn():
    record,ref,atom,task=fixture()
    assert A.strict_supply([atom],[record],{'synthetic:r1':[[2,2]]},task)['covered_slots']==0
    assert A.strict_supply([atom],[record],{'synthetic:r1':[[1,1]]},task)['covered_slots']==1


def test_wrong_record_id_with_same_text_is_absent():
    record,ref,atom,task=fixture();ref['record_id']='synthetic:other'
    assert A.reference_location(ref,{'synthetic:r1':record})['status']=='record_absent'


def test_reference_speaker_not_only_supplied_turn_is_checked():
    record,ref,atom,task=fixture();ref['speaker']='supporter'
    assert A.reference_location(ref,{'synthetic:r1':record})['status']=='speaker_mismatch'


def test_unicode_offsets_are_characters_not_utf8_byte_offsets():
    record,ref,atom,task=fixture();start=ref['exact_quote'].index('🧪');ref.update(start_char=start,end_char=start+1,exact_quote='🧪')
    assert A.reference_location(ref,{'synthetic:r1':record})['valid'] is True
    ref['end_char']=start+len('🧪'.encode())
    assert A.reference_location(ref,{'synthetic:r1':record})['valid'] is False


def test_boolean_indices_and_invalid_intervals_are_rejected():
    record,ref,atom,task=fixture();ref['turn_index']=True
    assert A.reference_location(ref,{'synthetic:r1':record})['valid'] is False
    with pytest.raises(ValueError,match='interval'):
        A.strict_supply([atom],[record],{'synthetic:r1':[[False,1]]},task)


def test_group_requires_context_and_answer_at_their_original_turns():
    record,ref,atom,task=fixture();context=deepcopy(ref);context.update(turn_index=0,speaker='supporter')
    atom['sufficient_groups']=[[context,ref]]
    assert A.strict_supply([atom],[record],{'synthetic:r1':[[1,1]]},task)['covered_slots']==0
    assert A.strict_supply([atom],[record],{'synthetic:r1':[[0,1]]},task)['covered_slots']==1


def test_absence_reference_keeps_unknown_in_all_conditions():
    record,ref,atom,task=fixture();atom['sufficient_groups']=[]
    got=A.strict_supply([atom],[record],{'synthetic:r1':[[0,2]]},task)
    assert got['unknown_slots']==1 and got['covered_slots']==0 and got['task_success'] is None


def test_current_matching_words_without_semantic_review_remain_unknown():
    record,ref,atom,task=fixture();ref['current_visible']=True;task['turns'][0]['text']=ref['exact_quote']
    got=A.strict_supply([atom],[record],{},task)
    assert got['unknown_slots']==1 and got['covered_slots']==0


def current_review(task,ref,classification,status):
    return dict(task_sha256=A.object_sha(task),reviewer_identity='synthetic assistant',reference_occurrences=[dict(
        reference_sha256=A.object_sha(ref),occurrence=A.occurrences(ref,task)[0],classification=classification,
        admissible_for_original_task=status,rationale='Synthetic entered judgement only.')])


def test_current_question_with_literal_reference_is_not_an_asserted_fact():
    record,ref,atom,task=fixture();ref['current_visible']=True;task['turns'][0]['text']='Did you say '+ref['exact_quote']+'?'
    review=current_review(task,ref,'question','no')
    assert A.strict_supply([atom],[record],{},task,review)['covered_slots']==0


def test_bounded_quote_can_answer_quoted_content_without_becoming_history_delivery():
    record,ref,atom,task=fixture();ref['current_visible']=True;task['turns'][0]['text']='The note says “'+ref['exact_quote']+'”.'
    review=current_review(task,ref,'quoted_note','yes_bounded');got=A.strict_supply([atom],[record],{},task,review)
    assert got['covered_slots']==1 and got['historical_required_covered']==0
    assert got['current_task_scope_required_covered']==1 and got['task_success'] is None


def test_current_wrong_speaker_is_not_accepted_even_with_entered_positive_judgement():
    record,ref,atom,task=fixture();ref['current_visible']=True;task['turns'][0].update(role='supporter',text=ref['exact_quote'])
    review=current_review(task,ref,'user_self_report','yes_bounded')
    assert A.strict_supply([atom],[record],{},task,review)['covered_slots']==0


def test_review_hash_drift_is_rejected_and_direct_does_not_expand_ranges():
    record,ref,atom,task=fixture();ref['current_visible']=True;task['turns'][0]['text']=ref['exact_quote']
    review=current_review(task,ref,'user_self_report','yes_bounded');review['task_sha256']='changed'
    with pytest.raises(ValueError,match='identity'):A.strict_supply([atom],[record],{},task,review)
    assert A.direct_intervals(dict(source_units=[dict(record_id='synthetic:r1',start_turn=1,end_turn=1)]))=={'synthetic:r1':[[1,1]]}
