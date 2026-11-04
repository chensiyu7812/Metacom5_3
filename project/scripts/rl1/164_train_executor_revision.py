#!/usr/bin/env python3
"""Fixed weak-SFT continuation; separate fresh-load behavioral comparison.

This cannot admit quality rewards or select a production executor. Training
targets remain AI weak examples. Each real model load is recorded before entry.
"""
import argparse
from copy import deepcopy
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import random
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp,verify_identity
from metacom_pm.rl1.durable import save_json_once as save_once
from metacom_pm.rl1.executor_encoding import encode_response,collate_responses,response_nll_sum
from metacom_pm.rl1.executor_engineering import accumulation_groups
from metacom_pm.rl1.executor_revision import validate_dataset
from metacom_pm.rl1.executor_use_probe import FIELDS,request_for
from metacom_pm.rl1.generation import LocalNaturalGenerator
from metacom_pm.rl1.local_backend import check_static,load_generator
from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
from metacom_pm.rl1.resource_comparison_runner import FixedResourceComparison,protocol_for
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import file_sha,save_json


def read(path):return json.loads(path.read_text())


def package(root):
    p=read(root/'PROTOCOL.json');verify_identity(p);check_static(p)
    for name,h in p['sources'].items():assert file_sha(Path(name))==h,name
    inputs=read(root/'INPUTS_PRIVATE.json');rows=read(root/'TRAINING_PRIVATE.json')
    for name,key in [('TRAINING_PRIVATE.json','training_identity'),('INPUTS_PRIVATE.json','inputs_identity'),
                     ('EVAL_CARDS_PRIVATE.json','evaluation_identity'),('BASELINE_JOBS_PRIVATE.json','baseline_jobs_identity'),
                     ('REUSED_BASELINES_PRIVATE.json','reused_identity')]:
        assert digest(read(root/name))==p[key],name
    validate_dataset(rows,inputs)
    review=read(root/'WEAK_SOURCE_REVIEW_PRIVATE.json');verify_identity(review)
    assert review['training_identity']==p['training_identity'] and review['protocol_identity']==p['identity']
    assert review['admitted_for']=='bounded_weak_SFT_only' and review['qualified_reward'] is False
    assert {x['row_id'] for x in review['rows']}=={x['id'] for x in rows}
    assert all(x['visible_source_checked'] and x['current_need_checked'] for x in review['rows'])
    assert p['epochs']==3 and p['accumulation']==4 and p['lr']==1e-4 and p['seed']==17
    assert p['fixed_final_epoch']==3 and not p['checkpoint_search'] and p['max_optimizer_updates']==15
    assert all(os.environ.get(k)=='1' for k in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE'))
    return p,inputs,rows


def encode(g,rows,inputs):
    return [(r,encode_response(g.tokenizer,inputs[r['input_identity']]['messages'],r['response'],
        context_limit=g.model.config.max_position_embeddings,eos_token_ids=[128001,128008,128009])) for r in rows]


def batch(g,e):
    import torch
    return {k:torch.tensor(v,dtype=torch.long,device='cuda:0') for k,v in
            collate_responses([e],pad_token_id=g.tokenizer.eos_token_id).items()}


def evaluate(g,encoded):
    import torch
    g.model.eval();per=[];total=0.;count=0
    with torch.inference_mode():
        for r,e in encoded:
            b=batch(g,e);labels=b.pop('labels');logits=g.model(**b,use_cache=False).logits
            loss,n=response_nll_sum(logits,labels);value=float(loss)
            assert n==e.target_tokens and torch.isfinite(loss)
            per.append(dict(row_id=r['id'],sum_nll=value,target_tokens=n,nll=value/n));total+=value;count+=n
            del logits,loss,b
    return dict(nll=total/count,sum_nll=total,target_tokens=count,rows=per,interpretation='weak target fit only, not quality')


def contrast_rows(rows):
    pairs=[]
    for case in ('N21','N23'):
        group={r['condition']:r for r in rows if r['case']==case}
        for condition in ('OFF','MEMORY','OTHER'):
            r=deepcopy(group[condition]);target=group['OFF' if condition=='MEMORY' else 'MEMORY']
            r.update(response=target['response'],response_identity=target['response_identity'],
                     id=case+':'+condition+':cross_target')
            pairs.append(r)
    return pairs


def frozen_hash(model):
    import torch
    h=hashlib.sha256()
    for name,p in model.named_parameters():
        if 'lora_' not in name:
            h.update(name.encode());h.update(p.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes())
    return h.hexdigest()


def train(root):
    import torch
    start=time.monotonic();p,inputs,rows=package(root);run=root/'training';run.mkdir(exist_ok=True)
    if (run/'load.started.json').exists():raise RuntimeError('one training load already entered; no silent restart')
    guard=LocalGPUCheck(p['gpu_uuid'],p['runtime'],run/'gpu_checks',latest_snapshot=True);guard.check()
    save_once(run/'load.started.json',dict(protocol_identity=p['identity'],pid=os.getpid()))
    g=load_generator(p['runtime']);assert digest(dict(g.manifest,identity=g.identity))==digest(p['runtime'])
    save_once(run/'load.done.json',dict(runtime_identity=g.identity,seconds=time.monotonic()-start))
    # Obtain every missing original baseline before changing a single parameter.
    for job in read(root/'BASELINE_JOBS_PRIVATE.json'):
        guard.check(own_pid=os.getpid());key=job['request']['request_id'];path=root/'baseline_G'
        save_once(path/(key+'.started.json'),job)
        raw=LocalNaturalGenerator.generate(g,job['request']);save_once(path/(key+'.raw.json'),raw)
        item=inputs[job['input_identity']]
        assert raw['runtime_identity']==g.identity and raw['request_id']==key
        assert raw['input_tokens']==item['usage']['input_tokens'] and raw['api_cost_usd']==0
        if raw['finish_reason']!='natural_stop':raise RuntimeError('incomplete baseline; preserve raw, no retry')
        print(json.dumps(dict(stage='baseline_G',input=job['input_identity'],replay=job.get('replay',False))),flush=True)
    random.seed(p['seed']);torch.manual_seed(p['seed']);torch.cuda.manual_seed_all(p['seed'])
    torch.backends.cuda.matmul.allow_tf32=False
    model=g.model
    for name,param in model.named_parameters():param.requires_grad_('lora_' in name)
    trainable=[(n,v) for n,v in model.named_parameters() if v.requires_grad]
    assert sum(v.numel() for _,v in trainable)==3407872
    initial={n:v.detach().cpu().clone() for n,v in trainable};before=frozen_hash(model)
    encoded=encode(g,rows,inputs);contrasts=encode(g,contrast_rows(rows),inputs)
    save_once(run/'ENCODING.json',[dict(row_id=r['id'],**asdict(e)) for r,e in encoded])
    baseline=evaluate(g,encoded);save_once(run/'baseline_fit.json',baseline)
    save_once(run/'baseline_contrast.json',evaluate(g,contrasts))
    print(json.dumps(dict(stage='baseline_fit',nll=baseline['nll'])),flush=True)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.enable_input_require_grads();model.config.use_cache=False
    optimizer=torch.optim.AdamW([v for _,v in trainable],lr=p['lr'],betas=(.9,.999),eps=1e-8,weight_decay=0.)
    steps=[];epochs=[];step=0;torch.cuda.reset_peak_memory_stats(0)
    for epoch in range(1,4):
        order=list(encoded);random.Random(p['seed']+epoch).shuffle(order);model.train();epoch_start=time.monotonic()
        for group,denominator in accumulation_groups(order,p['accumulation']):
            guard.check(own_pid=os.getpid());optimizer.zero_grad(set_to_none=True);group_sum=0.
            for r,e in group:
                b=batch(g,e);labels=b.pop('labels');logits=model(**b,use_cache=False).logits
                loss,n=response_nll_sum(logits,labels);assert n==e.target_tokens
                if not torch.isfinite(loss):raise RuntimeError('nonfinite training loss')
                group_sum+=float(loss.detach());(loss/denominator).backward();del logits,loss,b
            norm=torch.nn.utils.clip_grad_norm_([v for _,v in trainable],1.,error_if_nonfinite=True)
            optimizer.step();step+=1
            record=dict(step=step,epoch=epoch,examples=len(group),target_tokens=denominator,
                        nll=group_sum/denominator,gradient_norm=float(norm))
            steps.append(record);save_json(run/'steps.json',steps);print(json.dumps(record),flush=True)
        measured=evaluate(g,encoded);contrast=evaluate(g,contrasts);checkpoint=run/f'epoch_{epoch}'
        model.save_pretrained(checkpoint,safe_serialization=True,selected_adapters=[p['runtime']['adapter']['name']],save_embedding_layers=False)
        configs=list(checkpoint.rglob('adapter_config.json'));assert len(configs)==1;adapter=configs[0].parent
        torch.save(dict(optimizer=optimizer.state_dict(),torch_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state_all(),
            python_rng=random.getstate(),epoch=epoch,step=step,training_identity=p['training_identity']),checkpoint/'training_state.pt')
        rec=dict(epoch=epoch,step=step,fit=measured,contrast=contrast,adapter=str(adapter.resolve()),
                 adapter_files={name:file_sha(adapter/name) for name in ('adapter_config.json','adapter_model.safetensors')},
                 optimizer_state_sha256=file_sha(checkpoint/'training_state.pt'),seconds=time.monotonic()-epoch_start)
        epochs.append(rec);save_json(run/'epochs.json',epochs)
        print(json.dumps(dict(stage='epoch',epoch=epoch,nll=measured['nll'])),flush=True)
    after=frozen_hash(model);changes={n:float((v.detach().float().cpu()-initial[n].float()).abs().max()) for n,v in trainable}
    assert before==after and any(v>0 for v in changes.values()) and step==p['max_optimizer_updates']
    save_once(run/'FINAL.json',dict(status='TRAINED_WEAK_CANDIDATE_ONLY',steps=step,epochs=3,fixed_final=epochs[-1],
        protocol_identity=p['identity'],base_hash_before=before,base_hash_after=after,parameter_changes=changes,
        trainable_parameters=sum(v.numel() for _,v in trainable),trainable_tensors=len(trainable),
        baseline_fit_nll=baseline['nll'],final_fit_nll=epochs[-1]['fit']['nll'],api_cost_usd=0,
        seconds=time.monotonic()-start,peak_allocated_bytes=torch.cuda.max_memory_allocated(0),
        production_promoted=False,qualified_reward=False))
    package(root)


def compare(root):
    p,inputs,rows=package(root);final=read(root/'training/FINAL.json')['fixed_final'];runtime=deepcopy(p['runtime'])
    adapter=Path(final['adapter'])
    for name,h in final['adapter_files'].items():assert file_sha(adapter/name)==h
    runtime['adapter'].update(path=str(adapter),files=final['adapter_files'])
    runtime['identity']=digest({k:v for k,v in runtime.items() if k!='identity'});verify_identity(runtime)
    cards=read(root/'EVAL_CARDS_PRIVATE.json');keys=list(dict.fromkeys(c['input_identity'] for c in cards))
    code=PROJECT/'src/metacom_pm/rl1/resource_comparison_runner.py';code_id=file_sha(code)
    requests=[];mapping={};candidate_inputs={}
    for key in keys:
        item=deepcopy(inputs[key]);item['executor_identity']=runtime['identity'];item['identity']=digest({k:item[k] for k in FIELDS})
        req=request_for(item,runtime=runtime,draw_identity='revision-candidate:'+key,code_identity=code_id)
        requests.append(req);mapping[key]=req['identity'];candidate_inputs[key]=item
    assets=deepcopy(p['assets']);assets.update({str(adapter/name):h for name,h in final['adapter_files'].items()})
    protocol=protocol_for(requests,runtime=runtime,assets=assets,packages=p['packages'],gpu_uuid=p['gpu_uuid'],
        code_identity=code_id,source_package_identity=p['identity'],run_directory=root/'candidate_G')
    save_once(root/'CANDIDATE_PROTOCOL.json',protocol);save_once(root/'CANDIDATE_REQUESTS_PRIVATE.json',requests)
    save_once(root/'CANDIDATE_MAPPING.json',mapping);save_once(root/'CANDIDATE_INPUTS_PRIVATE.json',candidate_inputs)
    approval=dict(status='APPROVED',protocol_identity=protocol['identity'],operations=['resource_comparison_generation'],
        user_authorization_reference=p['authorization'],researcher_authorization_record=str((root/'PROTOCOL.json').resolve()),
        researcher_record_sha256=file_sha(root/'PROTOCOL.json'))
    save_once(root/'CANDIDATE_APPROVAL.json',approval)
    runner=FixedResourceComparison(protocol,requests,root/'candidate_G',approval=approval)
    result=runner.step();print(json.dumps(result),flush=True)
    if runner.generator is None:raise RuntimeError('fresh candidate load unavailable; no reset/reload')
    measured=evaluate(runner.generator,encode(runner.generator,rows,inputs));expected=final['fit']
    assert [r['row_id'] for r in measured['rows']]==[r['row_id'] for r in expected['rows']]
    delta=abs(measured['nll']-expected['nll']);per_delta=max(abs(a['nll']-b['nll']) for a,b in zip(measured['rows'],expected['rows']))
    passed=max(delta,per_delta)<=1e-4
    save_once(root/'RELOAD.json',dict(passed=passed,fresh_process=True,fit=measured,absolute_nll_delta=delta,
        max_row_nll_delta=per_delta,tolerance=1e-4,runtime_identity=runtime['identity']))
    if not passed:raise RuntimeError('fresh reload NLL mismatch')
    while result['status']=='GENERATION_RECORDED':
        result=runner.step();print(json.dumps(result),flush=True)
    if result['status']!='CLOSED_FIXED_COMPARISON':raise RuntimeError('candidate comparison incomplete')
    assert result['completed']==p['max_candidate_G_calls'] and result['natural_stops']==result['completed']
    package(root)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=['train','compare']);parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();globals()[args.action](args.root.resolve())
