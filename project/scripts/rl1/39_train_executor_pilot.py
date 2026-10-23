#!/usr/bin/env python3
"""Actual response-only LoRA updates, epoch dev selection, and fresh-process reload."""
import argparse
from dataclasses import asdict
import importlib.metadata
import json
import os
from pathlib import Path
import random
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.executor_encoding import encode_response,collate_responses,response_nll_sum
from metacom_pm.rl1.executor_pilot import accumulation_groups,admitted_rows

OUT=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v1'
MODEL=Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77')

def save(path,obj):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');temp.replace(path)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--reload',action='store_true');args=ap.parse_args()
    import torch
    from transformers import AutoConfig,AutoTokenizer,AutoModelForCausalLM,GenerationConfig
    from peft import LoraConfig,get_peft_model,PeftModel,get_peft_model_state_dict
    start=time.monotonic()
    if torch.cuda.device_count()!=1 or 'A6000' not in torch.cuda.get_device_name(0): raise RuntimeError('bind A6000')
    if torch.cuda.mem_get_info(0)[0]<40*1024**3: raise RuntimeError('A6000 busy; no fallback')
    contract=json.loads((OUT/'condition_contract_private.json').read_text()); hp=contract['training']
    # Rebuild from raw output and every review, not from an unchecked hand-edited dataset.
    author=Path(json.loads((OUT/'author_pointer.json').read_text())['run_dir'])
    jobs=json.loads((author/'jobs.json').read_text())
    requests={j['request_id']:json.loads((author/(j['request_id']+'.request.json')).read_text()) for j in jobs}
    raws={j['request_id']:json.loads((author/(j['request_id']+'.raw.json')).read_text()) for j in jobs}
    review_file=OUT/'admission_reviews_private.json'; review_doc=json.loads(review_file.read_text())
    if review_doc['contract_sha256']!=sha256_file(OUT/'condition_contract_private.json'): raise ValueError('review contract changed')
    if review_doc['reviewer']!=contract['admission']['reviewer']: raise ValueError('review identity mismatch')
    rows=admitted_rows(contract,jobs,requests,raws,{r['request_identity']:r for r in review_doc['rows']})
    if len(review_doc['rows'])!=len(jobs): raise ValueError('duplicate or missing reviews')
    dataset=dict(status='AI_ASSISTED_WEAK_SUPERVISION_NOT_HUMAN_GOLD',rows=rows,
        contract_sha256=sha256_file(OUT/'condition_contract_private.json'),reviews_sha256=sha256_file(review_file),
        author_runtime_sha256=sha256_file(author/'runtime.json'),dataset_identity=digest(rows))
    dataset_path=OUT/'accepted_dataset_private.json'
    if dataset_path.exists():
        if json.loads(dataset_path.read_text())!=dataset: raise ValueError('frozen dataset changed')
    else: save(dataset_path,dataset)
    tokenizer=AutoTokenizer.from_pretrained(MODEL,local_files_only=True)
    config=AutoConfig.from_pretrained(MODEL,local_files_only=True); gc=GenerationConfig.from_pretrained(MODEL,local_files_only=True)
    eos=gc.eos_token_id if isinstance(gc.eos_token_id,list) else [gc.eos_token_id]
    encoded=[(r,encode_response(tokenizer,r['messages'],r['response'],context_limit=config.max_position_embeddings,eos_token_ids=eos)) for r in rows]
    train=[x for x in encoded if x[0]['split']=='train'];dev=[x for x in encoded if x[0]['split']=='dev']
    runtime=dict(protocol='pm-rl1-r05-response-only-lora-v1',base_model=str(MODEL),
        base_files={p.name:sha256_file(p) for p in sorted(MODEL.iterdir()) if p.is_file() and p.suffix in ('.json','.safetensors','.jinja')},
        packages={p:importlib.metadata.version(p) for p in ('torch','transformers','tokenizers','peft','accelerate')},
        gpu=torch.cuda.get_device_name(0),cuda_visible_devices=os.environ.get('CUDA_VISIBLE_DEVICES'),
        cuda_version=torch.version.cuda,dtype='bfloat16',attention='sdpa',hyperparameters=hp,
        dataset_sha256=sha256_file(dataset_path),contract_sha256=sha256_file(OUT/'condition_contract_private.json'),
        chat_template_identity=digest(tokenizer.chat_template),train_examples=len(train),dev_examples=len(dev),
        train_target_tokens=sum(e.target_tokens for _,e in train),dev_target_tokens=sum(e.target_tokens for _,e in dev),
        max_sequence_tokens=max(len(e.input_ids) for _,e in encoded),
        runner_sha256=sha256_file(Path(__file__)),
        encoding_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/executor_encoding.py'),
        admission_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/executor_pilot.py'))
    identity=digest(runtime); run=OUT/'training'/identity
    if args.reload:
        selected=json.loads((run/'selection.json').read_text())
        checkpoint=Path(selected['checkpoint'])
        for name,expected in selected['adapter_files'].items():
            if sha256_file(checkpoint/name)!=expected: raise ValueError('adapter changed')
    elif (run/'runtime.json').exists(): raise RuntimeError('training run already exists; no silent restart')
    else:
        save(run/'runtime.json',dict(**runtime,identity=identity))
        save(OUT/'training_pointer.json',dict(run_dir=str(run),runtime_identity=identity))
        save(run/'encoding_audit.json',[dict(request_id=r['request_id'],split=r['split'],prompt_tokens=e.prompt_tokens,
            target_tokens=e.target_tokens,trailing_template_tokens_removed=e.trailing_template_tokens_removed,
            encoding_identity=digest(asdict(e))) for r,e in encoded])
    random.seed(17);torch.manual_seed(17);torch.cuda.manual_seed_all(17)
    torch.backends.cuda.matmul.allow_tf32=False
    load=time.monotonic()
    base=AutoModelForCausalLM.from_pretrained(MODEL,local_files_only=True,torch_dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda:0')
    base.config.use_cache=False
    if args.reload: model=PeftModel.from_pretrained(base,checkpoint,is_trainable=False)
    else: model=get_peft_model(base,LoraConfig(r=8,lora_alpha=16,target_modules=['q_proj','v_proj'],lora_dropout=0.,bias='none',task_type='CAUSAL_LM'))
    load_seconds=time.monotonic()-load
    def tensor_batch(e):
        return {k:torch.tensor(v,dtype=torch.long,device='cuda:0') for k,v in collate_responses([e],pad_token_id=tokenizer.eos_token_id).items()}
    def evaluate():
        model.eval();total=0.;count=0;per=[]
        with torch.inference_mode():
            for r,e in dev:
                b=tensor_batch(e);labels=b.pop('labels');logits=model(**b,use_cache=False).logits
                nll,n=response_nll_sum(logits,labels);value=float(nll);total+=value;count+=n
                per.append(dict(request_id=r['request_id'],sum_nll=value,target_tokens=n,nll=value/n))
                del logits,nll,b
        return dict(nll=total/count,sum_nll=total,target_tokens=count,rows=per)
    if args.reload:
        measured=evaluate();expected=selected['dev'];delta=abs(measured['nll']-expected['nll'])
        per_delta=max(abs(a['nll']-b['nll']) for a,b in zip(measured['rows'],expected['rows']))
        ok=delta<=hp['reload_nll_absolute_tolerance'] and per_delta<=hp['reload_nll_absolute_tolerance']
        save(run/'reload.json',dict(fresh_process=True,passed=ok,checkpoint=str(checkpoint),dev=measured,
            absolute_nll_delta=delta,max_example_nll_delta=per_delta,load_seconds=load_seconds,
            total_seconds=time.monotonic()-start,training_updates=0,api_cost_usd=0))
        print(json.dumps(dict(stage='reload',passed=ok,nll=measured['nll'],delta=delta)),flush=True)
        if not ok: raise RuntimeError('reload mismatch')
        return
    # Full tensor hashes before/after prove frozen base rather than sampling a few values.
    import hashlib
    def frozen_hash():
        h=hashlib.sha256()
        for name,p in model.named_parameters():
            if not p.requires_grad:
                h.update(name.encode());h.update(p.detach().contiguous().view(torch.uint8).cpu().numpy().tobytes())
        return h.hexdigest()
    trainable=[(n,p) for n,p in model.named_parameters() if p.requires_grad]
    if not trainable or any('lora_' not in n for n,p in trainable): raise RuntimeError('unexpected trainable base weights')
    initial={n:p.detach().cpu().clone() for n,p in trainable};before=frozen_hash()
    baseline=evaluate();save(run/'baseline_dev.json',baseline)
    print(json.dumps(dict(stage='baseline',nll=baseline['nll'],train=len(train),dev=len(dev))),flush=True)
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    model.enable_input_require_grads()
    optimizer=torch.optim.AdamW([p for n,p in trainable],lr=hp['lr'],betas=(.9,.999),eps=1e-8,weight_decay=0.)
    epochs=[];steps=[];step=0;train_start=time.monotonic()
    torch.cuda.reset_peak_memory_stats(0)
    for epoch in range(1,4):
        order=list(train);random.Random(17+epoch).shuffle(order);model.train();epoch_start=time.monotonic()
        for group,denominator in accumulation_groups(order,16):
            optimizer.zero_grad(set_to_none=True);group_sum=0.
            for r,e in group:
                b=tensor_batch(e);labels=b.pop('labels');logits=model(**b,use_cache=False).logits
                nll,n=response_nll_sum(logits,labels)
                if not torch.isfinite(nll): raise RuntimeError('nonfinite training loss')
                group_sum+=float(nll.detach());(nll/denominator).backward();del logits,nll,b
            norm=torch.nn.utils.clip_grad_norm_([p for n,p in trainable],1.,error_if_nonfinite=True)
            optimizer.step();step+=1
            row=dict(step=step,epoch=epoch,examples=len(group),target_tokens=denominator,nll=group_sum/denominator,gradient_norm=float(norm))
            steps.append(row);save(run/'steps.json',steps);print(json.dumps(row),flush=True)
        measured=evaluate();checkpoint=run/f'epoch_{epoch}';model.save_pretrained(checkpoint,safe_serialization=True)
        torch.save(dict(optimizer=optimizer.state_dict(),torch_rng=torch.get_rng_state(),cuda_rng=torch.cuda.get_rng_state_all(),
            python_rng=random.getstate(),epoch=epoch,step=step,dataset_identity=dataset['dataset_identity']),checkpoint/'training_state.pt')
        rec=dict(epoch=epoch,step=step,dev=measured,checkpoint=str(checkpoint),seconds=time.monotonic()-epoch_start,
            adapter_files={p.name:sha256_file(p) for p in sorted(checkpoint.iterdir()) if p.name in ('adapter_config.json','adapter_model.safetensors')},
            optimizer_state_sha256=sha256_file(checkpoint/'training_state.pt'))
        epochs.append(rec);save(run/'epochs.json',epochs);print(json.dumps(dict(stage='epoch',epoch=epoch,dev_nll=measured['nll'])),flush=True)
    after=frozen_hash();changes={n:float((p.detach().float().cpu()-initial[n].float()).abs().max()) for n,p in trainable}
    if before!=after or not any(x>0 for x in changes.values()) or step==0: raise RuntimeError('base freeze or parameter update check failed')
    selected=min(epochs,key=lambda e:(e['dev']['nll'],e['epoch']));save(run/'selection.json',selected)
    save(run/'summary.json',dict(status='X_L_PILOT_TRAINED_RELOAD_PENDING',steps=step,epochs=3,
        trainable_parameters=sum(p.numel() for n,p in trainable),trainable_tensors=len(trainable),all_trainable_are_lora=True,
        frozen_base_hash_before=before,frozen_base_hash_after=after,parameter_max_abs_changes=changes,
        baseline_dev_nll=baseline['nll'],selected_dev_nll=selected['dev']['nll'],selected_epoch=selected['epoch'],
        load_seconds=load_seconds,train_and_epoch_dev_seconds=time.monotonic()-train_start,
        total_seconds=time.monotonic()-start,peak_allocated_bytes=torch.cuda.max_memory_allocated(0),api_cost_usd=0,
        claim='optimization/reload pilot only; dev likelihood of AI weak targets is not support effectiveness'))

if __name__=='__main__':main()
