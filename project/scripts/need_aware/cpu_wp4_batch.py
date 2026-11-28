#!/usr/bin/env python3
"""Native tokenizer + real samples + loss plumbing, no model/optimizer/GPU."""
import argparse,json,os
from pathlib import Path
from metacom_pm.need_aware.data.v11 import jsonl,ordered
from metacom_pm.need_aware.data.training_objective import encode_target,objective
from metacom_pm.need_aware.data.personamem import write_json,sha_file
from metacom_pm.need_aware.data.contracts import digest

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('targets','tokenizer','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();os.environ['CUDA_VISIBLE_DEVICES']='';os.environ['HF_HUB_OFFLINE']='1'
    from transformers import AutoTokenizer
    import torch
    tokenizer=AutoTokenizer.from_pretrained(a.tokenizer,local_files_only=True)
    rows=jsonl(a.targets);ix={r['variant_id']:r for r in rows}
    # Every actual target is cap-checked. First four complete matched groups
    # form the inspected batch; never pad it with made-up examples.
    batch=[];lengths=[];hashes=[];aux_tokens=0;target_tokens=0
    groups=set(ordered(sorted({r['group_id'] for r in rows}),'cpu-batch')[:4])
    for row in rows:
        encoded=encode_target(tokenizer,row);lengths.append(len(encoded['input_ids']));hashes.append(encoded['chosen_sequence_sha256'])
        aux_tokens+=len(encoded['chosen_action']['input_ids'])+len(encoded['rejected_action']['input_ids'])
        target_tokens+=sum(x!=-100 for x in encoded['labels'])
        if row['group_id'] in groups:batch.append(encoded)
    x=torch.ones(len(batch),requires_grad=True);c=torch.zeros(len(batch),requires_grad=True);r=torch.zeros(len(batch),requires_grad=True)
    mask=torch.tensor([b['pair_loss_mask'] for b in batch]);u2=objective(x,c,r,mask,method='U2');u3=objective(x,c,r,mask,method='U3');u3.backward()
    report=dict(protocol='naa-wp4-real-sample-cpu-batch-v1',source_sha256=sha_file(Path(a.targets)),
                tokenizer_path=a.tokenizer,rows_checked=len(rows),batch_rows=len(batch),batch_groups=len(groups),
                token_lengths=dict(min=min(lengths),max=max(lengths),total=sum(lengths)),cap=2048,
                chosen_sequences_sha256=digest(hashes),u2_u3_identical_chosen_sequences=True,
                sft_target_tokens=target_tokens,auxiliary_action_sequence_tokens=aux_tokens,
                processed_training_tokens_per_method=sum(lengths)+aux_tokens,
                ordinary_sft_control='Same auxiliary forward/backward graph with zero coefficient; no auxiliary gradient for U2.',
                objective_plumbing=dict(synthetic_loss_inputs=True,not_model_outputs=True,u2=float(u2.detach()),u3=float(u3.detach()),
                    chosen_gradient_negative=bool((c.grad<0).all()),rejected_gradient_positive=bool((r.grad>0).all())),
                model_loaded=False,optimizer_created=False,model_updates=0,gpu_used=False)
    write_json(Path(a.out),report);print(json.dumps(report,indent=2))
