from copy import deepcopy
import pytest
from metacom_pm.rl1v3.journal import ge2_evaluation as E


def material(channel='fact'):
    task={'turns':[{'role':'seeker','text':'Synthetic hobby question'}]}
    ev={'channel':channel,'required_atoms':[] if channel=='natural_support' else [dict(id='a',reference='synthetic',evidence_groups=[{'id':'g1'}])],
        'constraints':[{'id':'c1','text':'Synthetic visible constraint'}]}
    row=E.review_template(case_id='b1',task=task,evaluation=ev,channel=channel,source_packet_sha256='source')
    return task,ev,row


def observed(channel='fact'):
    task,ev,row=material(channel);output=dict(text='A synthetic substantive answer.',finish_reason='eos',token_ids=[17,1])
    row.update(actual_output_sha256=E.sha(output),output_text=output['text'],technical_status='eos',
        constraints_reviewed=True,additional_claims_reviewed=True,reference_disputes_reviewed=True,development_interval=[1,1])
    row['reviewer'].update(identity='synthetic reviewer',kind='assistant_development')
    span={'start':0,'end':len(output['text']),'text':output['text']}
    for atom in row['facts']:atom.update(status='supported',answers_requested_proposition=True,output_spans=[span],source_evidence_ids=['g1'],rationale='Synthetic entered observation, not automated truth.')
    row['constraints'][0].update(status='pass',output_spans=[span],rationale='Synthetic constraint observation.')
    if channel!='fact':
        row['requested_support'].update(status='pass',output_spans=[span],rationale='Synthetic support observation.')
        row['natural_quality'].update(status='pass',rationale='Synthetic bounded quality observation.')
    return task,ev,row,output


def validate(task,ev,row,out=None):
    return E.validate_review(row,task=task,evaluation=ev,source_packet_sha256='source',actual_output=out)


def test_unrun_stays_unreviewed_not_vacuous_natural_pass():
    task,ev,row=material('natural_support');assert validate(task,ev,row)['status']=='UNRUN_TEMPLATE_VALID'
    row['natural_quality']['status']='pass'
    with pytest.raises(ValueError,match='unrun quality'):validate(task,ev,row)


def test_supported_citation_without_answer_is_not_success_record():
    task,ev,row,out=observed();row['facts'][0]['answers_requested_proposition']=False
    with pytest.raises(ValueError,match='not a substantive answer'):validate(task,ev,row,out)


def test_literal_and_source_id_cannot_qualify_reward():
    task,ev,row,out=observed();result=validate(task,ev,row,out)
    assert result['formal_reward'] is None and not result['semantic_qualification']
    row['formal_reward']=1
    with pytest.raises(ValueError,match='qualification'):validate(task,ev,row,out)


def test_exact_full_output_and_raw_offsets_not_trimmed():
    task,ev,row,out=observed();row['facts'][0]['output_spans'][0]['start']=1
    with pytest.raises(ValueError,match='span mismatch'):validate(task,ev,row,out)


def test_natural_empty_atoms_does_not_eliminate_support_quality_review():
    task,ev,row,out=observed('natural_support');row['requested_support']['status']='unreviewed'
    with pytest.raises(ValueError,match='support judgement'):validate(task,ev,row,out)


def test_visible_constraint_cannot_be_dropped():
    task,ev,row,out=observed();row['constraints']=[]
    with pytest.raises(ValueError,match='constraint inventory'):validate(task,ev,row,out)


def test_unsupported_extra_claim_prevents_otherwise_complete_pass():
    task,ev,row,out=observed();row['additional_claims']=[dict(id='extra',status='fail',output_spans=row['facts'][0]['output_spans'],rationale='Synthetic known extra assertion.')]
    with pytest.raises(ValueError,match='interval'):validate(task,ev,row,out)
    row['development_interval']=[0,0];assert validate(task,ev,row,out)['development_interval']==[0,0]


def test_uncertain_reference_never_becomes_zero_or_pass():
    task,ev,row,out=observed();row['reference_disputes']=[dict(id='d',status='uncertain',output_spans=[],rationale='Source scope unresolved.')]
    with pytest.raises(ValueError,match='interval'):validate(task,ev,row,out)
    row['development_interval']=[0,1];assert validate(task,ev,row,out)['development_interval']==[0,1]


def test_independent_human_label_requires_actual_provenance():
    task,ev,row,out=observed();row['reviewer']['kind']='human_independent'
    with pytest.raises(ValueError,match='independence'):validate(task,ev,row,out)


def test_non_eos_and_missing_never_semantic_failure():
    task,ev,row,out=observed();out['finish_reason']='length';row['actual_output_sha256']=E.sha(out)
    with pytest.raises(ValueError,match='non-EOS'):validate(task,ev,row,out)
    row['technical_status']='length';row['development_interval']=None
    assert validate(task,ev,row,out)['development_interval'] is None


def test_fixed_eight_selection_ignores_task_outcomes_and_direct():
    order=['n','f','j','f2'];channels={'n':'natural_support','f':'fact','j':'joint','f2':'fact'}
    got=E.select_blind(order,channels)
    assert len(got)==8 and got[0]==('f','STOP') and got[4]==('n','STOP')
    assert all(arm!='DirectEvidence' for _,arm in got)


def test_natural_cannot_inherit_constructed_required_memory():
    task,ev,row=material();ev['required_atoms'][0]['requirement_role']='explicit_answer'
    with pytest.raises(ValueError,match='mandatory recall'):E.normalized_atoms(ev,'natural_support')


def test_source_group_lists_and_bounded_absence_are_distinct():
    task,ev,row,out=observed();a=ev['required_atoms'][0];a.pop('evidence_groups');a['sufficient_groups']=[];a['reference_status']='absence_supported'
    row['evaluation_sha256']=E.sha(ev);row['facts'][0]['source_evidence_ids']=[]
    with pytest.raises(ValueError,match='substantive answer'):validate(task,ev,row,out)
    row['facts'][0]['bounded_unknown']=True
    assert validate(task,ev,row,out)['semantic_qualification'] is False


def test_calendar_assumption_remains_unknown_until_explicit_development_acceptance():
    task,ev,row,out=observed();ev['required_atoms'][0]['reference_status']='calendar_derived';row['evaluation_sha256']=E.sha(ev)
    row['facts'][0]['reference_assumption_disposition']='unresolved';row['development_interval']=[0,1]
    assert validate(task,ev,row,out)['development_interval']==[0,1]
    row['facts'][0]['reference_assumption_disposition']='accepted_development_assumption';row['development_interval']=[1,1]
    assert validate(task,ev,row,out)['formal_reward'] is None


def test_channel_cannot_be_changed_to_skip_natural_review():
    task,ev,row,out=observed('natural_support');row['channel']='fact'
    row['requested_support']['status']='not_applicable';row['natural_quality']['status']='not_applicable'
    with pytest.raises(ValueError,match='channel changed'):validate(task,ev,row,out)


def test_source_natural_alias_keeps_original_hash_and_review_scope():
    task,ev,row,out=observed('natural_support');ev['channel']='natural';row['evaluation_sha256']=E.sha(ev)
    assert validate(task,ev,row,out)['formal_reward'] is None


def test_fact_scope_cannot_smuggle_natural_quality_claim():
    task,ev,row,out=observed();row['natural_quality']['standardized_score']=1
    with pytest.raises(ValueError,match='unmeasured'):validate(task,ev,row,out)


def test_no_output_cannot_be_marked_eos():
    task,ev,row=material();row['technical_status']='eos'
    with pytest.raises(ValueError,match='missing output'):validate(task,ev,row)
