"""Synthetic-only workflow tests; never load project outputs or model weights."""
from copy import deepcopy
from dataclasses import asdict, replace
from pathlib import Path
import json

import pytest

from metacom_pm.rl1.calibration_intake import accept_label, independent_reviewers
from metacom_pm.rl1.calibration_workflow import (
    make_freeze, require_freeze, receive_sealed, qualify, stamp, bind_measurement)
from metacom_pm.rl1 import judge_completion as scorer
from metacom_pm.rl1.natural_runner import run_episode
from metacom_pm.rl1.schema import digest, Observation
from test_rl1_environment import fixture_spec, renderer


def fixture():
    contract = json.loads((Path(__file__).parents[1] / 'docs/pm_rl1_completion_20260930_v2/execution_contract.json').read_text())
    from test_rl1_flat_judge import flat_fixture
    evidence = flat_fixture()[1]['evidence']
    pairs, jobs, refs, items, mapping, records = [], [], [], [], {}, []
    kinds = ['natural']*16 + ['control']*8 + ['natural']*8 + ['control']*8
    control_types = ['identity','subject','currentness','intent_to_result',
                     'equivalent_wording','equivalent_wording','general_support','general_support']
    for i, kind in enumerate(kinds):
        group = 'validation' if i < 24 else 'development'
        pair = dict(pair_id=f'p{i}', group=group, kind=kind, owner=f'o{i%4}',
            prefix_identity=digest(i), replies=[f'Left reply {i}.',f'Right reply {i}.'])
        if kind == 'control': pair['control_type'] = control_types[(i-16)%16]
        pairs.append(pair)
        for side in (0,1):
            job = dict(job_id=f'j{i}-{side}', group=group, prefix_identity=pair['prefix_identity'],
                reply=pair['replies'][side], evidence=evidence, recheck=False, repeat=False, seed=17, draw_id='primary')
            jobs.append(job); refs.append(dict(pair_id=pair['pair_id'], side=side, job_id=job['job_id'],group=group,kind=kind))
        item = dict(item_id=f'i{i}', A=pair['replies'][0], B=pair['replies'][1], source_key=pair['prefix_identity'])
        items.append(item); meta=dict(pair_id=pair['pair_id'], group=group, swapped=False)
        mapping[item['item_id']] = meta
        raw = dict(item_id=item['item_id'], preference='A',risk_A='none_detected',risk_B='none_detected',
            quote_A='',quote_B='',source_ids=[],reason='A fits better.',uncertainty='')
        records.append(accept_label(raw,item,meta,evidence,reviewer='Chen',
            provenance=dict(kind='saved_browser_record',observation_origin='original-Chen')))
    for job in jobs[:12]:
        jobs.append(dict(job, job_id=job['job_id']+'-repeat',primary_job_id=job['job_id'],
                         group='repeat', repeat=True, draw_id='independent-repeat-1', seed=104746))
    protocol=stamp(dict(version=scorer.VERSION,rubric_identity=scorer.RUBRIC_ID,
        packet_identity=digest('packet'),semantic_revisions_after_human_labels=0))
    runtime=stamp(dict(protocol_identity=protocol['identity']))
    form=dict(protocol='pm-rl1-p3-human-calibration-v1',packet_identity=protocol['packet_identity'],
              form_identity=digest(items),items=items)
    inputs=dict(packet=dict(packet_identity=protocol['packet_identity']),forms={'rater_1':form},
        maps={'rater_1':mapping},pairs=dict(pairs=pairs),jobs=jobs,pair_score_map=refs,
        development_intake=deepcopy(records[24:]),contract=contract,
        protocol=protocol,runtime=runtime,code={'synthetic_only':True})
    inputs['development_score_review']=stamp(dict(status='DEVELOPMENT_REVIEW_CLOSED',
        protocol_identity=protocol['identity'],runtime_identity=runtime['identity'],unresolved_measurements=[],
        job_ids=[j['job_id'] for j in jobs if j['group']=='development']))
    freeze=make_freeze(inputs,raters=['Chen'],revision_events=[],final=True)
    intake=stamp(dict(freeze_identity=freeze['identity'],phase='validation',records=records[:24]))
    scores=[]
    for j in jobs:
        side=int(j['job_id'].split('-')[1]); i=int(j['job_id'].split('-')[0][1:])
        q,m=(1,1) if 16<=i<20 and side else (4-side,0)
        scores.append(stamp(dict(job_id=j['job_id'],request_id=digest(j['job_id']),
            runtime_identity=runtime['identity'],protocol_identity=protocol['identity'],
            reply_identity=digest(j['reply']),evidence_identity=digest(evidence),
            draw_id=j['draw_id'],seed=j['seed'],attempt=0,cache_hit=False,
            measurement_status='measured_candidate',q=q,m=m,format_valid=True)))
    from metacom_pm.rl1.evidence import evidence_turns
    sid=next(iter(evidence_turns(evidence)))
    facts=[stamp(dict(pair_id=p['pair_id'],confirmation_kind='human_fact_adjudication',
        reviewer='Chen',source_confirmed=True,verbatim_confirmation='Synthetic human source confirmation.',
        replies_identity=digest(p['replies']),evidence_identity=digest(evidence),source_ids=[sid],
        good_side=0,bad_side=1,severity='severe' if p['control_type'] in ('identity','subject','currentness','intent_to_result') else 'none_detected'))
        for p in pairs if p['kind']=='control' and p['group']=='validation']
    return dict(freeze=freeze, inputs=inputs, intakes=[intake],scores=scores, confirmations=facts)


def restamp(obj):
    return stamp({k:v for k,v in obj.items() if k!='identity'})


def test_qualification_connects_frozen_24_pairs_and_twelve_draws():
    x=fixture(); r=qualify(**x)
    assert r['status']=='CALIBRATED_FOR_BOUNDED_STUDY'
    assert r['sample']['pairs']==16 and r['sample']['raters']==1
    assert r['repeat_same_utility']==12 and not r['automatic_training_authorization']


def test_no_freeze_no_decryption_and_changed_version_refused():
    x=fixture(); called=[]
    draft=make_freeze(x['inputs'],raters=['Chen'],revision_events=[])
    with pytest.raises(ValueError,match='final measurement freeze'):
        receive_sealed({},slot='rater_1',reviewer='Chen',provenance={},freeze=draft,
            inputs=x['inputs'],decrypt=lambda *a,**k:called.append(a))
    assert not called
    x['inputs']['runtime']['protocol_identity']='wrong'
    with pytest.raises(ValueError):require_freeze(x['freeze'],x['inputs'])


def test_pending_development_or_second_revision_cannot_freeze():
    x=fixture()['inputs']
    x['development_score_review']=stamp(dict(status='DEVELOPMENT_REVIEW_PENDING'))
    with pytest.raises(ValueError,match='development review'):
        make_freeze(x,raters=['Chen'],revision_events=[],final=True)
    x=fixture()['inputs']
    with pytest.raises(ValueError,match='allowance'):
        make_freeze(x,raters=['Chen'],revision_events=[dict(state='applied'),dict(state='applied')],final=True)


def test_a_derived_second_file_does_not_make_two_independent_raters():
    rows=fixture()['intakes'][0]['records']
    du=[restamp(r|dict(reviewer='Du',provenance=dict(kind='user_declared_identical_copy',
        observation_origin='original-Chen',derived_from='Chen'))) for r in rows]
    with pytest.raises(ValueError,match='derived reviewer'):
        independent_reviewers(rows+du,['Chen','Du'])


def test_sealed_receiver_opens_only_fixed_validation_and_preserves_blanks():
    x=fixture();form=x['inputs']['forms']['rater_1'];mapping=x['inputs']['maps']['rater_1']
    freeze=make_freeze(x['inputs'],raters=['Chen'],revision_events=[],final=True)
    sub=dict(protocol=form['protocol'],packet_identity=form['packet_identity'],form_identity=form['form_identity'],
        reviewer_kind='individual_human',reviewer_identity='Chen',reviewer_details='fixture',
        items=[dict(item_id=i['item_id'],wrapped_key='fake',nonce='fake',ciphertext='fake') for i in form['items']])
    raw={r['item_id']:r['raw_label'] for r in x['intakes'][0]['records']};raw['i0']['risk_A']=''
    called=[]
    def decrypt(e,**_):called.append(e['item_id']);return raw[e['item_id']]
    r=receive_sealed(sub,slot='rater_1',reviewer='Chen',provenance=dict(kind='saved_browser_record',
        observation_origin='Chen'),freeze=freeze,inputs=x['inputs'],decrypt=decrypt)
    assert len(called)==24 and 'i24' not in called
    assert r['records'][0]['risks']['A']['level'] is None


@pytest.mark.parametrize('change', ['unknown','derived','wrong_run','wrong_reply','cache_repeat','same_draw','technical'])
def test_invalid_inputs_do_not_release_measurement(change):
    x=fixture()
    if change in ('unknown','derived'):
        row=x['intakes'][0]['records'][0]
        if change=='unknown':
            row['raw_label']['preference']=''
            item=x['inputs']['forms']['rater_1']['items'][0]
            x['intakes'][0]['records'][0]=accept_label(row['raw_label'],item,row['mapping'],
                x['inputs']['jobs'][0]['evidence'],reviewer='Chen',provenance=row['provenance'])
        else:
            for row in x['intakes'][0]['records']:
                row['provenance']['kind']='user_declared_identical_copy'
            row=x['intakes'][0]['records'][0]
        x['intakes'][0]['records']=[restamp(r) for r in x['intakes'][0]['records']]
        x['intakes'][0]=restamp(x['intakes'][0])
    else:
        s=x['scores'][-1] if change in ('cache_repeat','same_draw') else x['scores'][0]
        if change=='wrong_run':s['runtime_identity']=digest('other')
        if change=='wrong_reply':s['reply_identity']=digest('other')
        if change=='cache_repeat':s['cache_hit']=True
        if change=='same_draw':s['draw_id']='primary'
        if change=='technical':s.update(measurement_status='technical_failure',q=None,m=None,format_valid=False)
        x['scores']=[restamp(v) for v in x['scores']]
    if change in ('unknown','technical'):
        r=qualify(**x)
        assert r['status'] in ('INSUFFICIENT_HUMAN_INFORMATION','MEASUREMENT_UNQUALIFIED')
    else:
        with pytest.raises(ValueError):qualify(**x)


def test_first_attempt_denominator_survives_technical_recovery():
    x=fixture(); good=x['scores'][20]
    x['scores'][20]=restamp(good|dict(q=None,m=None,format_valid=False,measurement_status='technical_failure'))
    x['scores'].append(restamp(good|dict(attempt=1,request_id=digest('recovery'))))
    r=qualify(**x)
    assert r['technical']==dict(planned=80,first_valid=79,processable_after_recovery=80)
    assert r['status']=='CALIBRATED_FOR_BOUNDED_STUDY'


def test_control_intention_or_noisy_severity_is_not_human_gold():
    x=fixture();x['confirmations']=[]
    assert qualify(**x)['status']=='INSUFFICIENT_HUMAN_INFORMATION'
    x=fixture();x['confirmations'][0]['reviewer']='AI';x['confirmations'][0]=restamp(x['confirmations'][0])
    with pytest.raises(ValueError):qualify(**x)


def test_traceable_uncertain_note_never_invents_risk_severity():
    x=fixture();r=x['intakes'][0]['records'][0];item=x['inputs']['forms']['rater_1']['items'][0]
    raw=r['raw_label']|dict(preference='',risk_A='',reason='我无法判断这种回复是否贴切')
    accepted=accept_label(raw,item,r['mapping'],x['inputs']['jobs'][0]['evidence'],reviewer='Chen',
        provenance=r['provenance'],annotations=[dict(field='reason',span='我无法判断这种回复是否贴切',
            recover_preference='uncertain',meaning='Explicit inability to choose')])
    assert accepted['preference']['canonical']=='uncertain'
    assert accepted['risks']['A']['level'] is None and accepted['raw_label']==raw
    with pytest.raises(ValueError):
        accept_label(raw,item,r['mapping'],x['inputs']['jobs'][0]['evidence'],reviewer='Chen',
            provenance=r['provenance'],annotations=[dict(field='reason',span='does not exist')])


def test_raw_score_import_checks_prompt_runtime_and_reparses_rationale():
    from test_rl1_flat_judge import flat_fixture
    value,bindings=flat_fixture();x=fixture();runtime=x['inputs']['runtime'];protocol=x['inputs']['protocol']
    job=dict(job_id='one',evidence=bindings['evidence'],reply=bindings['reply'],
             recheck=False,draw_id='primary',seed=17)
    messages,schema=scorer.messages_and_schema(job['evidence'],job['reply'])
    payload=dict(messages=messages,json_schema=schema,executor_identity=runtime['identity'],
                 draw_identity='primary',seed=17,attempt=0,
                 score_identity=scorer.score_identity(job['evidence'],job['reply'],runtime_identity=runtime['identity']))
    req=dict(payload,request_id=digest(payload))
    raw=dict(request_id=req['request_id'],runtime_identity=runtime['identity'],
             text=json.dumps(value),finish_reason='natural_stop')
    measured=scorer.parse_completion(raw['text'],**dict(bindings,runtime_identity=runtime['identity'],draw_id='primary'))
    result=bind_measurement(job,req,raw,measured,runtime=runtime,protocol=protocol,scorer=scorer)
    assert result['q']==1 and result['m']==1
    for corrupted in (dict(measured,q=4),dict(measured,judge_runtime_identity='wrong')):
        with pytest.raises(ValueError):bind_measurement(job,req,raw,corrupted,runtime=runtime,protocol=protocol,scorer=scorer)
    with pytest.raises(ValueError):
        bind_measurement(dict(job,reply='different'),req,raw,measured,runtime=runtime,protocol=protocol,scorer=scorer)


def test_candidate_is_opt_in_and_keeps_scale_parser_and_user_payload():
    from test_rl1_flat_judge import flat_fixture
    from metacom_pm.rl1 import judge_completion_candidate as proposed
    value,b=flat_fixture()
    old,old_schema=scorer.messages_and_schema(b['evidence'],b['reply'])
    new,new_schema=proposed.messages_and_schema(b['evidence'],b['reply'])
    assert old[1]==new[1] and old_schema==new_schema and old[0]!=new[0]
    a=scorer.parse_completion(json.dumps(value),**b);z=proposed.parse_completion(json.dumps(value),**b)
    assert (a['q'],a['m'],a['candidate_utility'])==(z['q'],z['m'],z['candidate_utility'])
    assert z['rubric_identity']!=a['rubric_identity'] and not z['reward_eligible']


def test_actual_cli_adapters_prepare_and_check_synthetic_batches_without_models(tmp_path):
    import argparse
    import importlib.util
    from metacom_pm.io import sha256_file
    project=Path(__file__).parents[1]
    def module(filename):
        spec=importlib.util.spec_from_file_location(filename,project/'scripts/rl1'/filename)
        mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
    w=module('107_p3_acceptance_workflow.py');backend=module('108_run_p3_acceptance_batch.py')
    x=fixture()['inputs'];p3=tmp_path/'P3';cal=p3/'calibration';candidate=p3/'candidate_v1'
    cal.mkdir(parents=True);candidate.mkdir()
    for slot in ('rater_1','rater_2'):
        w.save(cal/f'{slot}_form.json',x['forms']['rater_1'] if slot=='rater_1' else dict(form_identity=digest('second'),items=[]))
        w.save(cal/f'{slot}_map_private.json',x['maps']['rater_1'] if slot=='rater_1' else {})
    w.save(cal/'pairs_private.json',x['pairs'])
    w.save(cal/'packet_freeze.json',dict(packet_identity=x['packet']['packet_identity'],
        files={p.name:sha256_file(p) for p in cal.iterdir()}))
    protocol=restamp(x['protocol']|dict(runtime={},decode={}))
    runtime=restamp(x['runtime']|dict(protocol_identity=protocol['identity']))
    for name,value in [('protocol.json',protocol),('jobs_private.json',x['jobs']),('pair_score_map_private.json',x['pair_score_map'])]:w.save(candidate/name,value)
    w.save(candidate/'candidate_freeze.json',dict(files={p.name:sha256_file(p) for p in candidate.iterdir()},source_files={}))
    w.save(tmp_path/'runtime.json',runtime);w.save(tmp_path/'development.json',x['development_intake'])
    w.save(tmp_path/'contract.json',x['contract']);w.save(tmp_path/'summary.json',dict(physical_calls_this_invocation=0))
    context=tmp_path/'context.json'
    w.save(context,dict(p3=str(p3),protocol=str(candidate/'protocol.json'),runtime=str(tmp_path/'runtime.json'),
        development_intake=str(tmp_path/'development.json'),contract=str(tmp_path/'contract.json'),
        revision_events=[],raters=['Chen']))
    # Explicit configuration is confined to a synthetic temp directory here.
    backend.configure(context,tmp_path/'configured',False)
    context=tmp_path/'configured/context.json';draft=tmp_path/'draft.json';freeze=tmp_path/'freeze.json'
    cc=w.read(context)
    synthetic_review=restamp(x['development_score_review']|dict(protocol_identity=w.read(cc['protocol'])['identity'],runtime_identity=w.read(cc['runtime'])['identity']))
    w.save(tmp_path/'review.json',synthetic_review)
    # This is a fabricated test receipt, never usable with the real P3 packet.
    context.write_text(json.dumps(dict(cc,development_score_review=str(tmp_path/'review.json'))))
    w.main(argparse.Namespace(command='draft',context=context,out=draft))
    w.main(argparse.Namespace(command='freeze',context=context,out=freeze,reviewed_draft_identity=w.read(draft)['identity']))
    plan=tmp_path/'batch.json'
    w.main(argparse.Namespace(command='batch-plan',context=context,out=plan,freeze=freeze,phase='validation',previous_calls=0))
    backend.execute(plan,False)
    assert len(w.read(plan)['requests'])==60
    assert not (tmp_path/'configured/runs').exists()
    # A draft cannot replace the reviewed freeze even at the command layer.
    with pytest.raises(ValueError):
        w.main(argparse.Namespace(command='batch-plan',context=context,out=tmp_path/'bad.json',freeze=draft,phase='validation',previous_calls=0))


@pytest.mark.parametrize('mode',['ok','technical','uncertain','wrong_binding','unqualified'])
def test_zero_model_natural_episode_binding_masks_cost_and_pending(mode):
    x=fixture();qualification=qualify(**x)
    if mode=='unqualified':qualification=restamp(qualification|dict(status='MEASUREMENT_UNQUALIFIED'))
    spec=replace(fixture_spec(budget=2048),judge_identity=x['freeze']['runtime_identity'])
    render=renderer();seen=[];calls=[]
    def policy(obs):
        assert type(obs) is Observation
        text=json.dumps(asdict(obs));assert 'PRIVATE' not in text
        if not seen:assert 'HIDDEN' not in text
        if seen:assert 'HIDDEN_RS_0' in text and 'HIDDEN_RS_1' not in text
        seen.append(obs)
        return 1 if len(seen)==1 else 0
    def generate(req):
        calls.append(req)
        return dict(request_id=req['request_id'],runtime_identity=spec.executor_identity,
            text='ON' if req['provenance']['canonical_counts'][0] else 'OFF',finish_reason='natural_stop')
    def measure(binding,evidence,reply):
        status='technical_failure' if mode=='technical' else 'semantic_uncertainty' if mode=='uncertain' else 'measured_candidate'
        return dict(binding=binding if mode!='wrong_binding' else {},measurement_status=status,
            q=(4 if reply=='ON' else 2) if status=='measured_candidate' else None,
            m=0 if status=='measured_candidate' else None)
    kwargs=dict(policy=policy,generate=generate,measure=measure,evidence=x['inputs']['jobs'][0]['evidence'],
        freeze=x['freeze'],freeze_inputs=x['inputs'],qualification=qualification,trajectory_id='rollout-new-1')
    if mode in ('wrong_binding','unqualified'):
        with pytest.raises(ValueError):run_episode(spec,render,**kwargs)
        if mode=='unqualified':assert not calls and not seen
    else:
        result=run_episode(spec,render,**kwargs)
        assert len(calls)==2
        if mode=='ok':
            assert result['terminal_reward']==.5
            assert result['return_value']==pytest.approx(.5-.05*render.cost(spec,(1,0,0,0))/2048)
        else:
            assert result['return_value'] is None and result['terminal_reward'] is None
            assert result['phase']==('technical_failure' if mode=='technical' else 'pending_score')
