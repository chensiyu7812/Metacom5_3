#!/usr/bin/env python3
"""One bounded free local relative-feedback attempt; reuse real G and human data."""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.durable import save_json_once
from metacom_pm.rl1.relative_diagnostic import VERSION,messages,parse,agreement
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import file_sha,save_json

BASE=PROJECT/'outputs/pm_rl1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b')
HUMAN_IDS=['3f4214fc5795bbdc0377','a526ebd76cfb2345fbb6','P07','P01','P05','P08',
    'pmrl1-c02-history-benefit-20261104-v1','f1db75e1b87d6db7e53e']
PROGRAMS=[[0],[1,0],[2,0],[3,0],[4,0],[3,4,0],[4,3,0]]


def read(p):return json.loads(Path(p).read_text())


def prepare(out):
    if out.exists():raise ValueError('new directory required')
    registry=read(BASE/'contextual_value_reference_20261104_v1/ANSWER_REGISTRY_PRIVATE.json')
    cases=read(BASE/'decision_branches_20261104_v1/CASES_PRIVATE.json')
    menu=read(BASE/'organized_initial_training_20261103_v2/MENU_PRIVATE.json')
    replies=read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    pairs=[];expectations={};selected=[]
    for rid in HUMAN_IDS:
        h=next(r for r in registry if r['record_id']==rid);left,right=h['reply_identities']
        pair=stamp(dict(group='reference',key=rid,evidence=h['evidence'],left=left,right=right,
            replies=h['replies'],human_asset=h['asset_id']))
        if h['direction']=='preferred_reply':expect='A_better' if h['preferred_reply_identity']==left else 'B_better'
        elif h['direction']=='tie':expect='near_equal'
        elif h['direction']=='uncertain':expect='unscored_reference'
        else:expect='not_material'
        expectations[pair['identity']]=expect;pairs.append(pair)
    for case in cases:
        es=[e for e in menu['endpoints'] if e['prefix_identity']==case['prefix_identity']]
        off=next(e for e in es if e['actions']==[0]);b=replies[off['requests']['ON']['request_id']]['text']
        for e in es:
            if e['actions'] not in PROGRAMS:continue
            selected.append(e)
            if e['actions']==[0]:continue
            a=replies[e['requests']['ON']['request_id']]['text'];left,right=digest(a),digest(b)
            pairs.append(stamp(dict(group='train_diagnostic',key=e['identity'],case=case['case_id'],
                endpoint_identity=e['identity'],OFF_endpoint_identity=off['identity'],
                evidence=case['evidence'],left=left,right=right,replies={left:a,right:b})))
    requests=[]
    for pair in pairs:
        if pair['left']==pair['right']:continue
        for reverse in (False,True):
            l,r=(pair['right'],pair['left']) if reverse else (pair['left'],pair['right'])
            requests.append(stamp(dict(pair_identity=pair['identity'],group=pair['group'],reverse=reverse,
                messages=messages(pair['evidence'],pair['replies'][l],pair['replies'][r]))))
    model_manifest=read(PROJECT/'outputs/paper1_pairwise_teacher/local_comparison_20260917_v2/qwen35_9b/manifest.json')
    sources=[Path(__file__),PROJECT/'src/metacom_pm/rl1/relative_diagnostic.py',
        BASE/'contextual_value_reference_20261104_v1/ANSWER_REGISTRY_PRIVATE.json',
        BASE/'decision_branches_20261104_v1/CASES_PRIVATE.json',
        BASE/'organized_initial_training_20261103_v2/MENU_PRIVATE.json',
        BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json']
    protocol=stamp(dict(version=VERSION,scope='REAL_DATA_RELATIVE_FEEDBACK_DIAGNOSTIC',
        sources={str(p.resolve()):file_sha(p) for p in sources},model=str(MODEL),model_files=model_manifest['model_files'],
        pairs_identity=digest(pairs),requests_identity=digest(requests),endpoint_identity=digest(selected),
        expectations_identity=digest(expectations),max_calls=len(requests),max_model_loads=1,
        stage_timeout_seconds=2700,request_timeout_seconds=180,thinking=True,temperature=.6,top_p=.95,top_k=20,
        repetition_penalty=1.,seed=20261104,natural_EOS=True,task_output_token_cap=None,
        reference_rule=dict(factual_preferences='3/3 both orders',ties='at least 2/3 both orders',
            near_equal='no stable material preference',overall_order_consistency='at least 6/7 scored references',
            purpose='limited exposed development screen, not population qualification'),
        train_scope='four preselected public-metadata cases; available fixed seven programs; no test',
        api_cost_usd=0,permission='Current researcher request: 好的，试试看，看看能不能解决现在的问题。'))
    out.mkdir(parents=True,mode=0o700)
    for name,value in [('PROTOCOL.json',protocol),('PAIRS_PRIVATE.json',pairs),('REQUESTS_PRIVATE.json',requests),
                       ('EXPECTATIONS_PRIVATE.json',expectations),('ENDPOINTS_PRIVATE.json',selected)]:save_json(out/name,value)
    print(json.dumps(dict(status='PREPARED',pairs=len(pairs),endpoints=len(selected),requests=len(requests),API_cost_usd=0)))


def analyze(out):
    pairs=read(out/'PAIRS_PRIVATE.json');requests=read(out/'REQUESTS_PRIVATE.json');expected=read(out/'EXPECTATIONS_PRIVATE.json')
    results={}
    for pair in pairs:
        if pair['left']==pair['right']:
            results[pair['identity']]=dict(status='identical_reply',gain=0.,source='exact text and complete evidence equality');continue
        parsed=[]
        for reverse in (False,True):
            req=next(r for r in requests if r['pair_identity']==pair['identity'] and r['reverse']==reverse)
            p=out/'responses'/(req['identity']+'.json');parsed.append(read(p).get('parsed') if p.exists() else None)
        results[pair['identity']]=agreement(pair,*parsed)
    counts=Counter();checks=[]
    for pair in [p for p in pairs if p['group']=='reference']:
        got=results[pair['identity']];want=expected[pair['identity']];verdict=got.get('verdict')
        counts['consistent']+=got['status'] in ('agreed','uncertain') and want!='unscored_reference'
        if want in ('A_better','B_better'):counts['factual_correct']+=verdict==want
        elif want=='near_equal':counts['ties_correct']+=verdict==want
        elif want=='not_material':counts['near_not_material']+=verdict=='near_equal' or got['status']=='uncertain'
        checks.append(dict(key=pair['key'],expected=want,result=got))
    passed=counts['factual_correct']==3 and counts['ties_correct']>=2 and counts['near_not_material']==1 and counts['consistent']>=6
    summary=dict(status='REFERENCE_SCREEN_PASSED' if passed else 'REFERENCE_SCREEN_NOT_PASSED',
        counts=dict(counts),checks=checks,train_statuses=dict(Counter(results[p['identity']]['status'] for p in pairs if p['group']=='train_diagnostic')),
        calls_completed=len(list((out/'responses').glob('*.json'))),api_cost_usd=0,natural_policy_updates=0)
    # Repeated closeout is idempotent. A later stage gets a new immutable
    # analysis file; the earlier reference-screen snapshot is retained.
    for name,value in [('ANALYSIS.json',summary),('PAIR_RESULTS_PRIVATE.json',results)]:
        target=out/name
        if target.exists():
            if read(target)==value:continue  # Preserve older JSON formatting too.
            target=out/(target.stem+f'_{summary["calls_completed"]:04d}'+target.suffix)
            if target.exists() and read(target)==value:continue
        save_json_once(target,value)
    return summary


def run(out):
    from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
    p=read(out/'PROTOCOL.json');requests=read(out/'REQUESTS_PRIVATE.json');pairs=read(out/'PAIRS_PRIVATE.json')
    assert p['requests_identity']==digest(requests) and p['pairs_identity']==digest(pairs)
    assert p['expectations_identity']==digest(read(out/'EXPECTATIONS_PRIVATE.json'))
    for path,h in p['sources'].items():assert file_sha(path)==h
    for name,h in p['model_files'].items():assert file_sha(MODEL/name)==h
    if (out/'LOAD_STARTED.json').exists():raise ValueError('bounded attempt already entered')
    c=read(BASE/'organized_initial_training_20261103_v2/CONFIG.json')
    guard=LocalGPUCheck(c['gpu_uuid'],c['runtime'],out/'gpu_checks',latest_snapshot=True);guard.check()
    save_json(out/'LOAD_STARTED.json',dict(protocol=p['identity'],unix_seconds=time.time()))
    import torch
    from transformers import AutoTokenizer,AutoModelForImageTextToText,StoppingCriteria,StoppingCriteriaList
    torch.set_num_threads(1);tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    model=AutoModelForImageTextToText.from_pretrained(MODEL,local_files_only=True,
        dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda:0').eval()
    context=read(MODEL/'config.json')['text_config']['max_position_embeddings']
    eos=model.generation_config.eos_token_id or tokenizer.eos_token_id;eos=[eos] if isinstance(eos,int) else eos
    (out/'responses').mkdir(mode=0o700);start=time.monotonic();phase='reference'
    save_json(out/'RUNTIME.json',dict(model_class=type(model).__name__,eos=eos,context=context,gpu=torch.cuda.get_device_name(0)))
    for req in requests:
        if req['group']!=phase:
            check=analyze(out);print(json.dumps(check),flush=True)
            if check['status']!='REFERENCE_SCREEN_PASSED':break
            phase=req['group']
        if time.monotonic()-start>p['stage_timeout_seconds']:break
        guard.check(own_pid=os.getpid())
        inputs=tokenizer.apply_chat_template(req['messages'],tokenize=True,add_generation_prompt=True,
            enable_thinking=True,return_tensors='pt',return_dict=True)
        inputs={k:v.to('cuda:0') for k,v in inputs.items()};n=inputs['input_ids'].shape[-1]
        if n>=context:raise ValueError('full evidence exceeds native context')
        torch.manual_seed(p['seed']);began=time.monotonic()
        class Watchdog(StoppingCriteria):
            reason=None
            def __call__(self,input_ids,scores,**kwargs):
                tail=input_ids[0,n:].tolist()
                if tail and tail[-1] in eos:return False
                if time.monotonic()-began>p['request_timeout_seconds']:self.reason='technical_timeout'
                if len(tail)>=128 and all(tail[-32:]==tail[-32*(i+1):-32*i] for i in range(1,4)):self.reason='repetition_guard'
                return self.reason is not None
        watchdog=Watchdog();save_json(out/(req['identity']+'.started.json'),dict(request=req['identity'],input_tokens=n))
        with torch.inference_mode():
            generated=model.generate(**inputs,max_new_tokens=context-n,do_sample=True,temperature=p['temperature'],
                top_p=p['top_p'],top_k=p['top_k'],repetition_penalty=p['repetition_penalty'],eos_token_id=eos,
                pad_token_id=tokenizer.pad_token_id or eos[0],forced_eos_token_id=None,
                stopping_criteria=StoppingCriteriaList([watchdog]))
        tokens=generated[0,n:].tolist();raw=tokenizer.decode(tokens,skip_special_tokens=True)
        finish='natural_stop' if tokens and tokens[-1] in eos else watchdog.reason or 'context_exhaustion'
        record=dict(request_identity=req['identity'],raw=raw,output_token_ids=tokens,finish_reason=finish,
            input_tokens=n,output_tokens=len(tokens),seconds=time.monotonic()-began,parsed=None)
        if finish=='natural_stop':
            pair=next(x for x in pairs if x['identity']==req['pair_identity'])
            try:record['parsed']=parse(raw,pair['evidence'])
            except (ValueError,TypeError) as exc:record['parse_error']=str(exc)
        save_json(out/'responses'/(req['identity']+'.json'),record)
        print(json.dumps(dict(group=req['group'],pair=req['pair_identity'][:10],reverse=req['reverse'],
            verdict=record['parsed']['verdict'] if record['parsed'] else None,finish=finish,seconds=record['seconds'])),flush=True)
        del generated,inputs
    summary=analyze(out);print(json.dumps(summary),flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('mode',choices=['prepare','run','analyze']);parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args();result=globals()[a.mode](a.output)
    if result is not None:print(json.dumps(result,ensure_ascii=False,indent=2))
