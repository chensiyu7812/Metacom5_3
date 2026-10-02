#!/usr/bin/env python3
"""No training/generation: audit masks, token losses and shared-prefix EOS logits.

Development diagnosis on already observed responses. Does not select a new
checkpoint or establish why an independent training run would behave similarly.
"""
from dataclasses import asdict
import json
from pathlib import Path
import sys
import time
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.executor_encoding import encode_response
from metacom_pm.rl1.schema import digest
ENG=PROJECT/'outputs/pm_rl1/executor_engineering_20260929_v1'
OUT=PROJECT/'outputs/pm_rl1/executor_coverage_20260929_v1'

def save(name,obj):
    with (OUT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def main():
    import torch
    import torch.nn.functional as F
    from transformers import AutoTokenizer,AutoModelForCausalLM,AutoConfig,GenerationConfig
    from peft import PeftModel
    from contextlib import nullcontext
    start=time.monotonic()
    if torch.cuda.device_count()!=1 or 'A6000' not in torch.cuda.get_device_name(0) or torch.cuda.mem_get_info(0)[0]<40*1024**3:
        raise RuntimeError('bind free A6000; no fallback')
    tr=Path(json.loads((ENG/'training_pointer.json').read_text())['run_dir'])
    runtime=json.loads((tr/'runtime.json').read_text());sel=json.loads((tr/'selection.json').read_text())
    base=Path(runtime['base_model']);checkpoint=Path(sel['checkpoint'])
    for name,h in runtime['base_files'].items():assert sha256_file(base/name)==h
    for name,h in sel['adapter_files'].items():assert sha256_file(checkpoint/name)==h
    data=json.loads((ENG/'accepted_dataset_private.json').read_text())['rows']
    tk=AutoTokenizer.from_pretrained(base,local_files_only=True)
    limit=AutoConfig.from_pretrained(base,local_files_only=True).max_position_embeddings
    eos=GenerationConfig.from_pretrained(base,local_files_only=True).eos_token_id
    encoded=[(r,encode_response(tk,r['messages'],r['response'],context_limit=limit,eos_token_ids=eos)) for r in data]
    audits=[]
    for r,e in encoded:
        prompt=list(tk.apply_chat_template(r['messages'],tokenize=True,add_generation_prompt=True))
        targets=e.labels[e.prompt_tokens:]
        assert list(e.input_ids[:e.prompt_tokens])==prompt and all(t==-100 for t in e.labels[:e.prompt_tokens])
        assert targets[-1] in eos and not set(targets[:-1]).intersection(tk.all_special_ids)
        assert tk.decode(list(targets[:-1]),skip_special_tokens=False).strip()==r['response'].strip()
        audits.append(dict(request_id=r['request_id'],split=r['split'],prompt_tokens=e.prompt_tokens,
            body_tokens=e.target_tokens-1,terminal_tokens=1,terminal_token_id=targets[-1],
            footer_removed=e.trailing_template_tokens_removed,encoding_identity=digest(asdict(e))))
    save('encoding_reaudit.json',dict(rows=audits,prompt_targets=0,interior_control_tokens=0,reply_text_roundtrip=True))
    dg=Path(json.loads((ENG/'diagnostic_pointer.json').read_text())['run_dir'])
    ds=json.loads((dg/'summary.json').read_text())['rows']
    contexts=[]
    for row in ds:
        req=json.loads((dg/(row['request_id']+'.request.json')).read_text())
        raw=json.loads((dg/(row['request_id']+'.raw.json')).read_text())
        prompt=list(tk.apply_chat_template(req['messages'],tokenize=True,add_generation_prompt=True))
        assert raw['finish_reason']=='natural_stop' and raw['output_token_ids'][-1] in eos
        contexts.append((row,prompt+raw['output_token_ids'][:-1],raw['output_token_ids'][-1]))
    protocol=dict(purpose='POST_HOC_DIAGNOSTIC_ONLY',checkpoint=str(checkpoint),
        dataset_sha256=sha256_file(ENG/'accepted_dataset_private.json'),
        selection_sha256=sha256_file(tr/'selection.json'),diagnostic_sha256=sha256_file(dg/'summary.json'),
        script_sha256=sha256_file(Path(__file__)),shared_stop_contexts=len(contexts),
        weak_reference_dev_count=sum(r['split']=='dev' for r,e in encoded),training_updates=0,new_generations=0,paid_calls=0)
    save('stopping_probe_protocol.json',protocol)
    torch.manual_seed(0);torch.backends.cuda.matmul.allow_tf32=False
    model=AutoModelForCausalLM.from_pretrained(base,local_files_only=True,torch_dtype=torch.bfloat16,attn_implementation='sdpa').to('cuda:0')
    model=PeftModel.from_pretrained(model,checkpoint,is_trainable=False).eval()
    losses=[];stops=[]
    for arm in ('base','lora'):
        with (model.disable_adapter() if arm=='base' else nullcontext()),torch.inference_mode():
            for r,e in encoded:
                if r['split']!='dev':continue
                ids=torch.tensor([e.input_ids],dtype=torch.long,device='cuda:0')
                logits=model(ids,attention_mask=torch.ones_like(ids),use_cache=False).logits
                # Only the response and true EOT; compare independent decomposition
                # with the selected checkpoint's persisted token-weighted dev NLL.
                predicted=logits[0,e.prompt_tokens-1:-1].float()
                targets=ids[0,e.prompt_tokens:]
                loss=F.cross_entropy(predicted,targets,reduction='none')
                losses.append(dict(arm=arm,request_id=r['request_id'],body_sum=float(loss[:-1].sum()),
                    body_tokens=len(targets)-1,eot_nll=float(loss[-1]),all_sum=float(loss.sum()),all_tokens=len(targets)))
                del ids,logits,predicted,loss
            for row,context,terminal in contexts:
                ids=torch.tensor([context],dtype=torch.long,device='cuda:0')
                logits=model(ids,attention_mask=torch.ones_like(ids),use_cache=False).logits[0,-1].float()
                probs=F.softmax(logits,dim=-1);top=int(logits.argmax())
                stops.append(dict(scored_model=arm,generated_by=row['arm'],index=row['index'],condition=row['condition'],
                    original_request_id=row['request_id'],context_identity=digest(context),context_tokens=len(context),
                    observed_reply_tokens=row['output_tokens'],eos_probability=float(probs[eos].sum()),
                    eot_probability=float(probs[terminal]),terminal_rank=1+int((logits>logits[terminal]).sum()),
                    next_argmax_id=top,next_argmax_text=tk.decode([top],skip_special_tokens=False)))
                del ids,logits,probs
        print(json.dumps(dict(stage='scored',arm=arm)),flush=True)
    aggregates={}
    for arm in ('base','lora'):
        rows=[r for r in losses if r['arm']==arm]
        aggregates[arm]=dict(all_nll=sum(r['all_sum'] for r in rows)/sum(r['all_tokens'] for r in rows),
            body_nll=sum(r['body_sum'] for r in rows)/sum(r['body_tokens'] for r in rows),
            eot_nll=sum(r['eot_nll'] for r in rows)/len(rows),
            all_tokens=sum(r['all_tokens'] for r in rows),eot_tokens=len(rows))
    assert abs(aggregates['lora']['all_nll']-sel['dev']['nll'])<1e-5
    save('stopping_probe_results.json',dict(protocol_identity=digest(protocol),aggregates=aggregates,
        weak_reference_rows=losses,shared_stop_context_rows=stops,total_seconds=time.monotonic()-start,
        training_updates=0,new_generations=0,paid_api_usd=0,
        limitations='Shared-prefix logits establish local stop preference, not sole causal attribution to EOT loss or proof of support-quality change.'))
    print(json.dumps(aggregates),flush=True)
if __name__=='__main__':main()
