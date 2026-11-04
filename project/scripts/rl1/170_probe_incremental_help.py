#!/usr/bin/env python3
"""Two source-selected cases, four conditions, two frozen local Gs; no reward."""
import argparse
import importlib.util
import json
from pathlib import Path
import random
import sys

PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp,verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.schema import digest
from metacom_pm.io import sha256_file as sha
BASE=PROJECT/'outputs/pm_rl1';TRAIN=BASE/'organized_initial_training_20261103_v2'
AUDIT=BASE/'feedback_and_opportunity_20261105_v1'

def read(p):return json.loads(p.read_text())
def module(name,file):
    s=importlib.util.spec_from_file_location(name,file);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def prepare(out):
    from metacom_pm.rl1.online_materials import load_materials
    from metacom_pm.rl1.resource_organization import OrganizationSession
    from metacom_pm.rl1.resource_comparison_runner import request_for,protocol_for
    if out.exists():raise ValueError('new output required')
    opp=[x for x in read(AUDIT/'OPPORTUNITIES_PRIVATE.json') if x['new_source_hypothesis']]
    assert [x['case'] for x in opp]==['N06','N13']
    c,catalogs,renderer=load_materials(TRAIN,prefix_ids=[x['prefix_identity'] for x in opp])
    oldpath=BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json'
    old=read(oldpath);menu=read(TRAIN/'MENU_PRIVATE.json')['endpoints'];cache={}
    for e in menu:
        req=e['requests']['ON'];raw=old[req['request_id']]
        assert raw['finish_reason']=='natural_stop' and raw['source_provenance_identity']==digest(req['provenance'])
        cache[(req['executor_identity'],digest(req['messages']))]=(req,raw)
    runner=PROJECT/'src/metacom_pm/rl1/resource_comparison_runner.py';code=sha(runner)
    cards=[];inputs={};requests=[];reused={}
    for o in opp:
        cat=catalogs[o['prefix_identity']];session=OrganizationSession(cat,renderer);actions=[]
        while o['target_resource_key'] not in session.receipt()['acquired']:
            session.get('MS');actions.append(3)
        pathkeys=session.receipt()['acquired']
        arms=[('OFF',[],[0]),('FIRST_MS',[cat.rank('MS')[0]['key']],[3,0]),
              ('TARGET_ONLY',[o['target_resource_key']],None),('REAL_MS_PATH',pathkeys,actions+[0])]
        for arm,keys,program in arms:
            presented=cat.canonical(keys);usage=renderer.usage(cat,keys);assert usage['within_native_context'] and not usage['truncation']
            body=dict(prefix_identity=cat.prefix.identity,executor_identity=c['runtime']['identity'],renderer_identity=renderer.identity,
                renderer_route='pmrl1-incremental-help-v1',messages=renderer.messages(cat,keys),
                selected_keys=[x.key for x in presented],selected_resource_identities=[x.identity for x in presented],
                catalog_identity=cat.identity,usage=usage)
            row=dict(body,identity=digest(body),reusable_old_requests=[]);inputs[row['identity']]=row
            found=cache.get((c['runtime']['identity'],digest(row['messages'])));rid=None
            if found:
                req,raw=found;assert req['messages']==row['messages'] and raw['input_tokens']==usage['input_tokens']
                reused[row['identity']]=dict(source_request=req,raw=raw,source_file=str(oldpath.resolve()))
            else:
                req=request_for(row,runtime=c['runtime'],draw_identity='incremental-help:'+o['case']+':'+arm,code_identity=code)
                requests.append(req);rid=req['identity']
            cards.append(dict(case=o['case'],arm=arm,input_identity=row['identity'],request_identity=rid,
                original_reused=bool(found),actual_program=program,acquisition_order=keys,
                targeted_injection=program is None,quality=None,reward=None))
    assert len(inputs)==len(cards)==8 and len(requests)==3 and len(reused)==5
    random.Random(20261105).shuffle(requests)
    assets={str(Path(c['runtime']['model_dir'])/n):h for n,h in c['runtime']['model_files'].items()}
    assets.update({str(Path(c['runtime']['adapter']['path'])/n):h for n,h in c['runtime']['adapter']['files'].items()})
    for p in [Path(__file__),runner,PROJECT/'scripts/rl1/92_run_p2_common_pool.py',PROJECT/'src/metacom_pm/rl1/generation.py']:
        assets[str(p.resolve())]=sha(p)
    out.mkdir(mode=0o700)
    protocol=protocol_for(requests,runtime=c['runtime'],assets=assets,packages=c['runtime']['packages']|{'peft':c['runtime']['adapter']['peft_version']},
        gpu_uuid=c['gpu_uuid'],code_identity=code,source_package_identity=digest(inputs),run_directory=out/'original_G')
    auth=dict(date='2026-11-05 Asia/Tokyo',actual_user_message='好的，按计划继续推进。',
        inherited_plan='复用人评检查反馈，核对24个已暴露train情境的信息增量与GET可达性，有具体机会后做小规模机制对照。',
        implementation_scope='两情境、四条件、两冻结本地G；3原G加8替代G；无API、训练、重试或自动后续扩张。')
    save(out/'USER_AUTHORIZATION.json',auth)
    approval=dict(status='APPROVED',protocol_identity=protocol['identity'],operations=['resource_comparison_generation'],
        user_authorization_reference='2026-11-05 current conversation continuation; implementation of accepted plan',
        researcher_authorization_record=str((out/'USER_AUTHORIZATION.json').resolve()),researcher_record_sha256=sha(out/'USER_AUTHORIZATION.json'))
    study=stamp(dict(scope='TWO_CASE_INCREMENTAL_INFORMATION_MECHANISM_DIAGNOSTIC',cases=['N06','N13'],
        cards_identity=digest(cards),inputs_identity=digest(inputs),reused_identity=digest(reused),original_protocol=protocol['identity'],
        hypotheses=[dict(case=o['case'],hypothesis=o['hypothesis'],target=o['target_session']['id']) for o in opp],
        selection='Based on current missing constraints and exact legal past source, before any new output; original OFF/MS1 inspected for baseline interpretation.',
        max_new_original_G=3,max_new_alternate_G=8,old_original_inputs_reused=5,
        conclusions=['Evaluate factual use, support-action change, and judged helpfulness separately.',
          'OFF may already provide the same useful action; this falsifies claimed increment for that reply.',
          'TARGET_ONLY is not a head-selection action; REAL_MS_PATH acquires every preceding resource.',
          'Both Gs use identical system/user messages. No hypothesized benefit, reference answer or human label is injected.',
          'No source mention reward, no zero-filled failures, no new human questionnaire automatically.',
          'One greedy response per condition; no causal population or generalization claim; G timing is not deployment waiting.'],
        source_hashes={str(p.resolve()):sha(p) for p in [AUDIT/'OPPORTUNITIES_PRIVATE.json',AUDIT/'OPPORTUNITY_SOURCES.json',
            TRAIN/'PACKAGE_MANIFEST.json',TRAIN/'MENU_PRIVATE.json',oldpath]},
        API_cost_usd=0,qualified_rewards=0,training_updates=0))
    for n,v in [('STUDY.json',study),('INPUTS_PRIVATE.json',inputs),('CARDS_PRIVATE.json',cards),('REUSED_PRIVATE.json',reused),
                ('G_REQUESTS_PRIVATE.json',requests),('G_PROTOCOL.json',protocol),('APPROVAL.json',approval)]:save(out/n,v)
    print(json.dumps(dict(inputs=8,reused=5,new_original_G=3,new_alternate_G=8)),flush=True)

def prepare_alternate(out):
    from transformers import AutoTokenizer
    old=read(BASE/'alternate_executor_probe_20261104_v1/PROTOCOL.json');runtime=old['runtime'];verify_identity(runtime)
    tokenizer=AutoTokenizer.from_pretrained(runtime['model_dir'],local_files_only=True)
    assert digest(tokenizer.chat_template)==runtime['chat_template_identity']
    requests=[];inputs=read(out/'INPUTS_PRIVATE.json');study=read(out/'STUDY.json');verify_identity(study)
    assert digest(inputs)==study['inputs_identity']
    for key,item in inputs.items():
        ids=tokenizer.apply_chat_template(item['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        assert 0<len(ids)<runtime['policy']['context_limit']
        requests.append(stamp(dict(input_identity=key,messages=item['messages'],messages_identity=digest(item['messages']),
            selected_keys=item['selected_keys'],selected_resource_identities=item['selected_resource_identities'],
            runtime_identity=runtime['identity'],input_tokens=len(ids),token_ids_identity=digest(ids))))
    random.Random(20261105).shuffle(requests)
    code=[Path(__file__),PROJECT/'scripts/rl1/167_probe_alternate_executor.py',PROJECT/'src/metacom_pm/rl1/generation.py',
          PROJECT/'src/metacom_pm/rl1/local_gpu_guard.py',PROJECT/'src/metacom_pm/rl1/durable.py']
    p=stamp(dict(scope=study['scope'],runtime=runtime,gpu_uuid=old['gpu_uuid'],requests_identity=digest(requests),
        sources={str(x.resolve()):sha(x) for x in [out/'STUDY.json',out/'INPUTS_PRIVATE.json',out/'CARDS_PRIVATE.json']},
        code={str(x.resolve()):sha(x) for x in code},stage_seconds=1200,max_loads=1,max_calls=8,automatic_retries=0,
        api_cost_usd=0,new_training=False,new_rewards=False,promote=False,authorization=read(out/'USER_AUTHORIZATION.json')))
    alt=out/'alternate_G';alt.mkdir(mode=0o700)
    save(alt/'PROTOCOL.json',p);save(alt/'REQUESTS_PRIVATE.json',requests)
    print(json.dumps(dict(alternate_requests=8,unchanged_runtime=runtime['identity'])),flush=True)

def run_original(out):
    from metacom_pm.rl1.resource_comparison_runner import FixedResourceComparison
    for path,h in read(out/'STUDY.json')['source_hashes'].items():assert sha(Path(path))==h,path
    runner=FixedResourceComparison(read(out/'G_PROTOCOL.json'),read(out/'G_REQUESTS_PRIVATE.json'),out/'original_G',approval=read(out/'APPROVAL.json'))
    while True:
        r=runner.step();print(json.dumps(r),flush=True)
        if r['status']=='CLOSED_FIXED_COMPARISON':return
        if r['status']=='RECONCILIATION_REQUIRED' or r.get('finish_reason')!='natural_stop':raise RuntimeError('preserve partial; no retry')

def run_alternate(out):
    module('frozen_alternate',PROJECT/'scripts/rl1/167_probe_alternate_executor.py').run(out/'alternate_G')

def analyze(out):
    reused=read(out/'REUSED_PRIVATE.json');alt=out/'alternate_G';reqs=read(alt/'REQUESTS_PRIVATE.json');rows=[]
    for c in read(out/'CARDS_PRIVATE.json'):
        old=reused[c['input_identity']]['raw'] if c['original_reused'] else read(out/'original_G'/(c['request_identity']+'.raw.json'))
        q=next(q for q in reqs if q['input_identity']==c['input_identity']);new=read(alt/'raw'/(q['identity']+'.json'))
        for name,raw in [('original',old),('alternate',new)]:
            text=raw['text'];failure=any(marker in text for marker in ('[channel]','[end]','<think>','</think>'))
            rows.append(dict(**c,generator=name,reply=text,reply_identity=digest(text),finish_reason=raw['finish_reason'],
                format_marker_detected=failure,raw_request_identity=raw.get('request_identity',raw.get('request_id')),
                output_tokens=raw['output_tokens'],G_seconds=raw['generation_seconds'],
                source_use=None,helpfulness=None,training_reward=None))
    save(out/'RESULTS_PRIVATE.json',rows)
    save(out/'SUMMARY.json',dict(cases=2,conditions=4,rows=16,reused_original=5,new_original=3,new_alternate=8,
        natural_rows=sum(r['finish_reason']=='natural_stop' for r in rows),format_markers=sum(r['format_marker_detected'] for r in rows),
        helpfulness='unjudged',qualified_rewards=0,training_updates=0,API_cost_usd=0))
    print(json.dumps(read(out/'SUMMARY.json')),flush=True)

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','prepare_alternate','run_original','run_alternate','analyze']);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();globals()[a.mode](a.output.resolve())
