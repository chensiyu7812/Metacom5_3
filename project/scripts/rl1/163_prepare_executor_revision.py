#!/usr/bin/env python3
"""Freeze a matched weak-SFT pilot and fixed before/after evaluation inputs."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.executor_revision import validate_dataset
from metacom_pm.rl1.online_materials import load_materials,read
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import file_sha,save_json

BASE=PROJECT/'outputs/pm_rl1'
PRIOR=BASE/'resource_value_probe_20261104_v1'
EDIT=BASE/'executor_use_probe_20261104_v1'
INITIAL=BASE/'organized_initial_training_20261103_v2'


def main(out):
    if out.exists():raise ValueError('new trial directory required')
    for root in (PRIOR,EDIT):
        for name,h in read(root/'OUTPUT_MANIFEST.json').items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            assert file_sha(root/name)==h
    config,catalogs,renderer=load_materials(INITIAL)
    inventory={x['case']:x for x in read(PRIOR/'INVENTORY_PRIVATE.json')}
    old_items=read(PRIOR/'INPUTS_PRIVATE.json');old_cards=read(PRIOR/'CARDS_PRIVATE.json')
    old_results=read(PRIOR/'RESULTS_PRIVATE.json')
    drafts=read(EDIT/'REVISION_CANDIDATES_PRIVATE.json')['candidates']
    inputs={};training=[];eval_cards=[];projections=[]
    def add_input(case,keys):
        cat=catalogs[inventory[case]['prefix_identity']]
        keys=[x.key for x in cat.canonical(keys)]
        body=dict(prefix_identity=cat.prefix.identity,executor_identity=config['runtime']['identity'],
            renderer_identity=renderer.identity,renderer_route='pmrl1-matched-executor-revision-v1',
            messages=renderer.messages(cat,keys),selected_keys=keys,
            selected_resource_identities=[cat.item(k).identity for k in keys],catalog_identity=cat.identity,
            usage=renderer.usage(cat,keys))
        assert body['usage']['within_native_context'] and not body['usage']['truncation']
        item=dict(body,identity=digest(body),reusable_old_requests=[]);inputs[item['identity']]=item
        return item['identity']
    def old_keys(case,arm):
        card=next(x for x in old_cards if x['case']==case and x['arm']==arm)
        return old_items[card['input_identity']]['selected_keys']
    def original_reply(case):
        return next(x['reply'] for x in old_results if x['case']==case and x['arm']=='A_OFF')
    def draft(case,condition):
        return next(x for x in drafts if x['case']==case and x['condition']==condition)
    def map_draft(x):
        cat=catalogs[x['prefix_identity']]
        records=json.loads(x['messages'][0]['content'].split('<resources>\n',1)[1].split('\n</resources>',1)[0])
        keys=[]
        for r in records:
            found=[v for v in cat._items.values() if v.head==r['head'] and v.reported_at==r['source_time']
                   and json.loads(v.content)==json.loads(r['content'])]
            assert len(found)==1,'ambiguous old/new resource projection'
            keys.append(found[0].key)
        projected=add_input(x['case'],keys)
        projections.append(dict(case=x['case'],condition=x['condition'],old_slot=x['original_slot_id'],
            original_messages_identity=x['messages_identity'],new_input_identity=projected,
            full_resource_content_and_time_preserved=True,new_wrapper='current organized address renderer'))
        return keys
    def add_train(case,condition,keys,response,*,origin,claims=(),role=None):
        key=add_input(case,keys)
        row=dict(case=case,condition=condition,role=role or condition,input_identity=key,
            prefix_identity=inventory[case]['prefix_identity'],owner=inventory[case]['owner'],split='train',
            response=response,response_identity=digest(response),historical_claims=list(claims),
            weak_supervision=True,reward=None,origin=origin,
            quality_gain_assumed=False,same_target_does_not_mean_equal_quality=True)
        row['id']=digest(row);training.append(row)
        eval_cards.append(dict(case=case,condition='fit_'+condition,input_identity=key,used_for_updates=True))
    for case,condition in [('N04','single'),('N18','single')]:
        x=draft(case,condition);keys=map_draft(x)
        add_train(case,'OFF',[],x['proposed_response'],origin='current-only portion of reviewed weak edit')
        add_train(case,'EDIT',keys,x['proposed_response'],origin=x['proposed_response_identity'])
        add_train(case,'OTHER',old_keys(case,'D_other_topic_full_MS'),x['proposed_response'],
                  origin='same acceptable current-focused weak target',role='other_topic_control')
    x=draft('N21','four');keys=map_draft(x);generic=x['proposed_response']
    add_train('N21','OFF',[],generic,origin='current-focused weak edit')
    add_train('N21','RS4',keys,generic,origin=x['proposed_response_identity'])
    add_train('N21','OTHER',old_keys('N21','D_other_topic_full_MS'),generic,
              origin='current-focused weak target, not a neutrality label',role='other_topic_control')
    for case,condition in [('N21','single'),('N23','same_two')]:
        x=draft(case,condition);keys=map_draft(x)
        claims=[dict(source_quote=a['turn']['text'],source_turn=a['turn']['id'],
                     modality='past_report_not_current_success') for a in x['source_anchors']]
        add_train(case,'MEMORY',keys,x['proposed_response'],origin=x['proposed_response_identity'],claims=claims)
        if case=='N23':
            add_train(case,'OFF',[],original_reply(case),origin='previous actual OFF reply as weak target')
            add_train(case,'OTHER',old_keys(case,'D_other_topic_full_MS'),original_reply(case),
                      origin='acceptable current-focused weak target',role='other_topic_control')
    for case in ('N02','N03'):
        add_train(case,'OFF',[],original_reply(case),origin='retained acceptable current-focused reply')
        add_train(case,'CONTROL',old_keys(case,'B_retrieved_MS1'),original_reply(case),
                  origin='preserve optional ignoring; no zero-benefit label')
    stats=validate_dataset(training,inputs)
    assert stats['rows']==17 and stats['contexts']==6 and stats['historical_target_rows']==2
    fit_cases={r['case'] for r in training}
    # Predeclared diagnostic panel: retain original eight, add four train contexts by hash.
    panel=[x['case'] for x in inventory.values() if x['pilot']]
    extras=sorted([c for c in inventory if c not in panel],key=lambda c:digest(['revision-extra-v1',inventory[c]['prefix_identity']]))[:4]
    for case in panel+extras:
        if case in panel:
            keys=old_keys(case,'B_retrieved_MS1' if case=='N03' else 'C_target_full_MS')
        else:
            cat=catalogs[inventory[case]['prefix_identity']];keys=[cat.rank('MS')[0]['key']]
        for cond,ks in [('OFF',[]),('ON',keys)]:
            eval_cards.append(dict(case=case,condition='panel_'+cond,input_identity=add_input(case,ks),used_for_updates=case in fit_cases))
    eval_keys=list(dict.fromkeys(x['input_identity'] for x in eval_cards))
    assert len(eval_keys)==32
    # Cache priority is fixed before new outputs: original organized pool, then prior fixed probe.
    cache={};conflicts=[]
    def cache_add(messages,raw,provenance):
        assert raw['runtime_identity']==config['runtime']['identity'] and raw['finish_reason']=='natural_stop'
        key=digest(messages)
        if key in cache and cache[key]['raw']['text']!=raw['text']:conflicts.append(dict(key=key,kept=cache[key]['provenance'],other=provenance))
        cache.setdefault(key,dict(messages=messages,raw=raw,provenance=provenance))
    raw_path=BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json';raws=read(raw_path)
    for e in read(INITIAL/'MENU_PRIVATE.json')['endpoints']:
        req=e['requests']['ON'];cache_add(req['messages'],raws[req['request_id']],dict(path=str(raw_path),request_id=req['request_id']))
    reused=read(PRIOR/'REUSED_PRIVATE.json')
    for c in old_cards:
        raw=reused[c['input_identity']]['raw'] if c['reused'] else read(PRIOR/'live_G'/(c['request_identity']+'.raw.json'))
        cache_add(old_items[c['input_identity']]['messages'],raw,dict(probe=str(PRIOR),case=c['case'],arm=c['arm']))
    old_baselines={};baseline_jobs=[]
    def job_for(key,draw):
        item=inputs[key];body=dict(messages=item['messages'],executor_identity=config['runtime']['identity'],
            draw_identity=draw,renderer_identity=item['renderer_identity'])
        return dict(input_identity=key,request=dict(body,request_id=digest(body)))
    for key in eval_keys:
        item=inputs[key];hit=cache.get(digest(item['messages']))
        if hit:
            assert hit['messages']==item['messages'] and hit['raw']['input_tokens']==item['usage']['input_tokens']
            old_baselines[key]=hit
        else:baseline_jobs.append(job_for(key,'revision-baseline:'+key))
    repeats=[]
    for case,cond in [('N02','panel_OFF'),('N19','panel_ON')]:
        key=next(c['input_identity'] for c in eval_cards if c['case']==case and c['condition']==cond)
        assert key in old_baselines
        job=job_for(key,'revision-replay:'+key);job['replay']=True;repeats.append(job)
    baseline_jobs+=repeats
    prior_protocol=read(EDIT/'G_PROTOCOL.json');assets=deepcopy(prior_protocol['assets'])
    code_paths=[Path(__file__),PROJECT/'scripts/rl1/164_train_executor_revision.py',
                PROJECT/'src/metacom_pm/rl1/executor_revision.py',PROJECT/'src/metacom_pm/rl1/executor_encoding.py',
                PROJECT/'src/metacom_pm/rl1/executor_engineering.py']
    assets.update({str(p.resolve()):file_sha(p) for p in code_paths})
    sources={str(p.resolve()):file_sha(p) for p in [PRIOR/'OUTPUT_MANIFEST.json',EDIT/'OUTPUT_MANIFEST.json',
        EDIT/'REVISION_CANDIDATES_PRIVATE.json',INITIAL/'PACKAGE_MANIFEST.json',INITIAL/'INPUT_HASHES_PRIVATE.json',raw_path,
        PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2/dataset_freeze.json']}
    protocol=stamp(dict(scope='BOUNDED_WEAK_EXECUTOR_REVISION_NOT_PM_REWARD',runtime=config['runtime'],assets=assets,
        packages=prior_protocol['packages'],gpu_uuid=config['gpu_uuid'],sources=sources,
        training_identity=digest(training),inputs_identity=digest(inputs),evaluation_identity=digest(eval_cards),
        baseline_jobs_identity=digest(baseline_jobs),reused_identity=digest(old_baselines),
        seed=17,epochs=3,accumulation=4,microbatch=1,lr=1e-4,gradient_clip=1.,optimizer='AdamW betas .9/.999 eps1e-8 weight_decay0',
        initial_adapter='existing P2 epoch_3; continue only its q/v LoRA parameters',
        fixed_final_epoch=3,checkpoint_search=False,max_training_loads=1,max_candidate_loads=1,
        max_baseline_G_calls=len(baseline_jobs),max_candidate_G_calls=len(eval_keys),max_optimizer_updates=15,
        native_context_only=True,API_calls=0,qualified_reward=False,training_claim='Source-conditioned weak-target fit and observed behavior only.',
        source_scope='Existing isolated 24 train prefixes; no dev/test expansion.',
        evaluation_scope='12 exposed train contexts: 6 receive this update, 6 do not; not an independent held-out test.',
        changed_from_old_P2='Independent continuation trial: 17 matched weak targets, accumulation4, fixed final epoch, no old checkpoint replacement.',
        run_directory=str(out.resolve()),authorization='2026-11-04 researcher: 继续推进; carry out the planned limited matched supervision experiment.'))
    out.mkdir(parents=True,mode=0o700)
    for name,obj in [('TRAINING_PRIVATE.json',training),('INPUTS_PRIVATE.json',inputs),('EVAL_CARDS_PRIVATE.json',eval_cards),
        ('REUSED_BASELINES_PRIVATE.json',old_baselines),('BASELINE_JOBS_PRIVATE.json',baseline_jobs),('PROJECTIONS_PRIVATE.json',projections),
        ('PROTOCOL.json',protocol),('SUMMARY_PREPARE.json',dict(**stats,evaluation_inputs=len(eval_keys),evaluation_contexts=12,
            fit_cases=sorted(fit_cases),update_excluded_cases=sorted(set(panel+extras)-fit_cases),
            reused_baselines=len(old_baselines),new_baseline_calls=len(baseline_jobs),candidate_calls=len(eval_keys),cache_conflicts=conflicts,
            target_author='AI weak revisions with source review, no independent helpfulness labels'))]:save_json(out/name,obj)
    print(json.dumps(read(out/'SUMMARY_PREPARE.json'),ensure_ascii=False),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True)
    main(parser.parse_args().output)
