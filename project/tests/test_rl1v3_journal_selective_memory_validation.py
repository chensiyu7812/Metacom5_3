"""Synthetic contracts plus optional bounded private-source CPU verification."""
import copy,json,os
from pathlib import Path
import pytest
from metacom_pm.rl1v3.io import canonical_json,file_sha256,object_sha256,decode_contract
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.journal import selective_memory_validation as V
from metacom_pm.rl1v3.journal import selective_memory_validation_review as E
from metacom_pm.rl1v3.journal.selective_memory_validation_policies import simple_visible_choice
from metacom_pm.rl1v3.journal.selective_memory_validation_sources import load_development_cache


def synthetic():
    request=dict(logical_id='synthetic:1:STOP',task_id='synthetic:1',arm='STOP',request_id='synthetic:req',
        payload_sha256='synthetic:payload',model_input=dict(messages=[dict(role='user',content='[reported 2000-01-02] A &amp; B')]))
    evaluation=dict(channel='natural_support',required_fact_ids=[],fact_references=[dict(atom_id='f1')],
        prohibitions=['Respect the explicit boundary.'])
    return request,evaluation


def test_visible_baseline_never_accepts_metadata():
    assert simple_visible_choice('A current note is sufficient.')=='STOP'
    assert simple_visible_choice('Recall our previous note.')=='MS'
    with pytest.raises(TypeError):simple_visible_choice({'query':'x','gold':'y'})


def test_displayed_quote_and_report_metadata_are_diagnostics():
    assert V.quote_in_display("A & B",'A &amp; B')
    assert V.quote_in_display("Writer's note",'Writer&#x27;s note')
    request,_=synthetic()
    assert '[reported 2000-01-02]' in E.displayed_input(request)


def test_sealed_owner_rejected_before_cache_text_read(tmp_path):
    meta=tmp_path/'metadata.json';meta.write_text(json.dumps(dict(folds=dict(fold_of_owner={'sealed':6},family_groups=[]))))
    with pytest.raises(ValueError,match='sealed'):
        load_development_cache(resources_path=tmp_path/'MUST_NOT_OPEN',metadata_path=meta,
            allowed_owners=['sealed'],excluded_owners=[])


def test_family_closure_rejected_before_cache_text_read(tmp_path):
    meta=tmp_path/'metadata.json';meta.write_text(json.dumps(dict(folds=dict(fold_of_owner={'a':2,'b':2},family_groups=[['a','b']]))))
    with pytest.raises(ValueError,match='closure'):
        load_development_cache(resources_path=tmp_path/'MUST_NOT_OPEN',metadata_path=meta,
            allowed_owners=['a'],excluded_owners=[])


def test_unrun_template_cannot_report_semantic_success():
    req,ev=synthetic();row=E.template(req,ev)
    assert E.validate_review(row,req,ev)['status']=='UNRUN_TEMPLATE_VALID'
    row['support']['status']='pass'
    with pytest.raises(ValueError,match='unrun support'):E.validate_review(row,req,ev)


def test_empty_fact_list_does_not_make_support_optional():
    req,ev=synthetic();row=E.template(req,ev);row['support']['status']='not_applicable'
    with pytest.raises(ValueError,match='required support'):E.validate_review(row,req,ev)


def test_reference_scope_and_reward_cannot_silently_change():
    req,ev=synthetic();row=E.template(req,ev);row['formal_reward']=1
    with pytest.raises(ValueError,match='formal reward'):E.validate_review(row,req,ev)
    row=E.template(req,ev);row['facts'][0]['required']=True
    with pytest.raises(ValueError,match='scope'):E.validate_review(row,req,ev)


def observed_fixture():
    req,ev=synthetic();row=E.template(req,ev)
    row.update(output_sha256='synthetic:output',technical_status='eos',review_status='development_observed',
        reviewer='synthetic_development',additional_claims_review_status='development_observed',
        source_or_reference_disputes_review_status='development_observed',development_interval=[1,1])
    row['facts'][0].update(status='omitted',note='Optional background not repeated.')
    row['support'].update(status='pass',note='Observed operation in synthetic response.',output_quotes=['Acknowledged.'])
    row['prohibitions'][0].update(status='pass',note='No observed violation in this synthetic response.')
    return req,ev,row


def test_optional_fact_omission_does_not_fail_natural_support():
    req,ev,row=observed_fixture()
    result=E.validate_review(row,req,ev,output_text='Acknowledged.',output_sha256='synthetic:output')
    assert result['development_interval']==[1,1] and result['semantic_qualification'] is False


def test_unsupported_output_or_source_quote_rejected():
    req,ev,row=observed_fixture();row['support']['output_quotes']=['Not in output']
    with pytest.raises(ValueError,match='output quote'):E.validate_review(row,req,ev,output_text='Acknowledged.',output_sha256='synthetic:output')
    req,ev,row=observed_fixture();row['support']['source_quotes']=['Absent source']
    with pytest.raises(ValueError,match='supplied quote'):E.validate_review(row,req,ev,output_text='Acknowledged.',output_sha256='synthetic:output')


def test_technical_truncation_is_not_semantic_success():
    req,ev,row=observed_fixture();row['technical_status']='length'
    with pytest.raises(ValueError,match='technical failure'):E.validate_review(row,req,ev,output_text='Acknowledged.',output_sha256='synthetic:output')


def complete_joint_fixture():
    req,ev,row=observed_fixture()
    ev['channel']='joint';ev['required_fact_ids']=['f1']
    row['evalspec_sha256']=object_sha256(ev)
    row['facts'][0].update(required=True,status='supported',note='Synthetic required slot completed.',output_quotes=['A & B'])
    return req,ev,row


def test_extra_unsupported_assertion_cannot_pass_after_all_required_items_pass():
    req,ev,row=complete_joint_fixture();output='A & B. Acknowledged. The voyage is complete.'
    row['additional_claims']=[dict(id='c1',status='unsupported',output_quotes=['The voyage is complete.'],
        source_quotes=[],note='Synthetic asserted completion has no supplied evidence.')]
    with pytest.raises(ValueError,match='development interval'):
        E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')
    row['development_interval']=[0,0]
    assert E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')['development_interval']==[0,0]


@pytest.mark.parametrize('state',['uncertain','unresolved'])
def test_extra_uncertain_assertion_cannot_be_definite_completion(state):
    req,ev,row=complete_joint_fixture();output='A & B. Acknowledged. The voyage is complete.'
    row['additional_claims']=[dict(id='c1',status=state,output_quotes=['The voyage is complete.'],
        note='Synthetic completion claim remains uncertain.')]
    with pytest.raises(ValueError,match='development interval'):
        E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')
    row['development_interval']=[0,1]
    assert E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')['development_interval']==[0,1]


@pytest.mark.parametrize('field,state',[('additional_claims','pass'),('source_or_reference_disputes','ignored')])
def test_unknown_supplemental_state_cannot_silently_pass(field,state):
    req,ev,row=complete_joint_fixture()
    row[field]=[dict(id='x1',status=state,note='Synthetic unknown state.',output_quotes=['A & B'])]
    with pytest.raises(ValueError,match='state'):
        E.validate_review(row,req,ev,output_text='A & B. Acknowledged.',output_sha256='synthetic:output')


def test_unresolved_reference_dispute_cannot_be_definite_completion():
    req,ev,row=complete_joint_fixture();output='A & B. Acknowledged.'
    row['source_or_reference_disputes']=[dict(id='d1',status='unresolved',output_quotes=['A & B'],
        note='Synthetic source attribution dispute has no independent resolution.')]
    with pytest.raises(ValueError,match='development interval'):
        E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')
    row['development_interval']=[0,1]
    assert E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')['development_interval']==[0,1]


def test_resolved_dispute_must_preserve_its_entered_effect():
    req,ev,row=complete_joint_fixture();output='A & B. Acknowledged.'
    row['source_or_reference_disputes']=[dict(id='d1',status='resolved_violation',output_quotes=['A & B'],
        note='Synthetic resolution establishes a task violation.')]
    with pytest.raises(ValueError,match='development interval'):
        E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')
    row['development_interval']=[0,0]
    assert E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')['development_interval']==[0,0]
    row['source_or_reference_disputes'][0].update(status='resolved_no_violation',note='Synthetic alternate resolution has no violation.')
    row['development_interval']=[1,1]
    assert E.validate_review(row,req,ev,output_text=output,output_sha256='synthetic:output')['development_interval']==[1,1]


def test_empty_dispute_inventory_requires_explicit_review():
    req,ev,row=complete_joint_fixture();row['source_or_reference_disputes_review_status']='unreviewed'
    with pytest.raises(ValueError,match='disputes unreviewed'):
        E.validate_review(row,req,ev,output_text='A & B. Acknowledged.',output_sha256='synthetic:output')


def test_optional_fact_error_cannot_bypass_the_additional_claim_gate():
    req,ev,row=observed_fixture()
    row['facts'][0].update(status='unsupported',output_quotes=['Acknowledged.'],note='Synthetic optional assertion marked unwarranted.')
    with pytest.raises(ValueError,match='development interval'):
        E.validate_review(row,req,ev,output_text='Acknowledged.',output_sha256='synthetic:output')
    row['development_interval']=[0,0]
    assert E.validate_review(row,req,ev,output_text='Acknowledged.',output_sha256='synthetic:output')['development_interval']==[0,0]


def test_supplemental_claim_needs_a_located_assertion():
    req,ev,row=complete_joint_fixture()
    row['additional_claims']=[dict(id='c1',status='supported',note='Synthetic unlocated assertion.',output_quotes=[])]
    with pytest.raises(ValueError,match='located output quote'):
        E.validate_review(row,req,ev,output_text='A & B. Acknowledged.',output_sha256='synthetic:output')


@pytest.fixture
def actual():
    root=os.environ.get('SELECTIVE_MEMORY_VALIDATION_PRIVATE')
    if not root:pytest.skip('bounded private CPU artifacts not provided')
    p=Path(root);bundle=p/'source-bundle-v3';requests=p/'requests-top4-v1'
    receipt=json.loads((p/'SOURCE_ACCESS_RECEIPT_PRIVATE.json').read_text())
    resources=next(x for x in receipt['inputs'] if x.endswith('resources_private.jsonl'))
    metadata=next(x for x in receipt['inputs'] if x.endswith('registry.json'))
    design=json.loads((p/'DESIGN_V3_PRIVATE.json').read_text())
    registry=load_development_cache(resources_path=resources,metadata_path=metadata,
        allowed_owners=design['allowed_owners'],excluded_owners=design['excluded_J06_owners'])
    return p,bundle,requests,registry


def test_actual_original_policy_and_frozen_artifacts_unchanged(actual):
    p,b,req,r=actual;freeze=json.loads((p/'POLICY_FREEZE_PRIVATE.json').read_text())
    for key in ('C1','simple'):assert file_sha256(freeze[key]['path'])==freeze[key]['sha256']
    for folder in [b,req,p/'evaluation-preparation-v1',p/'evaluation-preparation-v2']:
        manifest=json.loads((folder/('CPU_READ_SUMMARY.json' if folder==req else 'MANIFEST.json')).read_text())
        for name,h in manifest['files_sha256'].items():assert file_sha256(folder/name)==h
    for name in ('TASKS.runtime.jsonl','TASK_ENVELOPES.private.jsonl','POLICY_CHOICES.private.jsonl'):
        assert file_sha256(p/'source-bundle-v1'/name)==file_sha256(b/name)


def test_actual_source_cache_authentication_rejects_mutated_text(actual,tmp_path):
    p,b,req,r=actual;resources=Path(next(x for x in r.inputs if x.endswith('resources_private.jsonl')))
    rows=V.jl(resources);rows[0]['source_refs'][0]['exact_quote']+=' SYNTHETIC MUTATION'
    bad=tmp_path/'bad.jsonl';bad.write_text('\n'.join(json.dumps(x) for x in rows))
    with pytest.raises((ValueError,AssertionError)):
        load_development_cache(resources_path=bad,metadata_path=next(x for x in r.inputs if x.endswith('registry.json')),
            allowed_owners=list(r.allowed),excluded_owners=[])


def test_actual_all_complete_top4_sources_are_strict_past_and_exact(actual):
    p,b,req,r=actual;envelopes={x['task_id']:x for x in V.jl(b/'TASK_ENVELOPES.private.jsonl')}
    rows=V.jl(req/'READINGS.private.jsonl');assert len(rows)==30
    for row in rows:
        e=envelopes[row['task_id']];prefix=decode_contract(K.PrefixSpec,canonical_json(e['actual_prefix']))
        assert prefix.fold!=6 and prefix.runtime_sha256==e['asof_runtime_sha256']
        if row['arm']=='STOP':assert not row['readings'];continue
        assert len(row['selected_source_session_ids'])==len(row['selected_record_ids'])==4
        assert len(row['readings'])==1 and row['readings'][0]['head']=='MS'
        for sid in row['selected_source_session_ids']:
            source=r.entry(prefix.owner_id,sid)
            assert r.reason(source.source_id,prefix) is None
            assert source.source.chronological_rank<prefix.cutoff_rank
            for turn in source.source.turns:assert turn.text in row['readings'][0]['reading_text']


def test_actual_runtime_is_eval_free_and_reuses_only_endpoints(actual):
    p,b,req,r=actual;tasks=V.jl(b/'TASKS.runtime.jsonl');rows=V.jl(req/'REQUESTS_ALL.private.jsonl')
    assert len(rows)==len({x['payload_sha256'] for x in rows})==30
    assert len(tasks)==15 and all(set(t)==V.RUNTIME_KEYS for t in tasks)
    by={(x['task_id'],x['arm']):x for x in rows}
    for task in tasks:
        for arm in ('STOP','MS'):
            row=by[(task['task_id'],arm)]
            assert row['model_input']['messages'][-1]['content']==task['query']
            assert row['input_tokens']+320<=16384
            assert row['payload_sha256']==object_sha256(row['model_input'])
            assert all(key not in row['model_input'] for key in ('fact_references','required_fact_ids','support_goal'))
    checks=V.jl(req/'READ_CHECKS.private.jsonl')
    assert all(x['after_stop_rejected'] and x['pending_reward'] for x in checks)


def test_actual_task_scope_and_unrun_review_are_explicit(actual):
    p,b,req,r=actual;evals={x['task_id']:x for x in V.jl(b/'EVALSPEC.private.jsonl')}
    rows={(x['task_id'],x['arm']):x for x in V.jl(req/'REQUESTS_ALL.private.jsonl')}
    assert sum(len(e['required_fact_ids']) for e in evals.values())==17
    assert all(not e['required_fact_ids'] for e in evals.values() if e['channel']=='natural_support')
    for row in V.jl(p/'evaluation-preparation-v2/REVIEW_TEMPLATE_PRIVATE.jsonl'):
        assert E.validate_review(row,rows[(row['task_id'],row['arm'])],evals[row['task_id']])['mechanical_only']
