#!/usr/bin/env python3
"""One fixed local CPU capability diagnostic; no Judge/reward qualification."""
import argparse,hashlib,json,os,time
from collections import Counter
from pathlib import Path


def readlines(path):return [json.loads(s) for s in Path(path).read_text().splitlines() if s.strip()]
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(frozen, snapshot, output):
    if os.environ.get('CUDA_VISIBLE_DEVICES')!='' or os.environ.get('HF_HUB_OFFLINE')!='1':
        raise ValueError('CPU offline execution only')
    frozen=Path(frozen);out=Path(output);out.mkdir(parents=True,exist_ok=False)
    assert Path(snapshot).name=='6c749ce3425cd33b46d187e45b92bbf96ee12ec7'
    inputs=readlines(frozen/'CLAIM_INPUTS.private.jsonl');assert len(inputs)==32
    binding={name:sha(frozen/name) for name in ('CLAIM_PROTOCOL.json','CLAIM_INPUTS.private.jsonl','CLAIM_REFERENCES.private.jsonl')}
    (out/'PRE_PREDICTION_BINDING.json').write_text(json.dumps(binding,indent=2)+'\n')
    import torch
    from metacom_pm.rl1v3.journal.event_understanding import LocalNLIAssistance,inspect
    torch.set_num_threads(4);torch.set_num_interop_threads(1)
    start=time.monotonic_ns();model=LocalNLIAssistance(snapshot);load_ns=time.monotonic_ns()-start
    predictions=[]
    with (out/'PREDICTIONS_BEFORE_REFERENCE_JOIN.private.jsonl').open('x') as f:
        for item in inputs:
            result=inspect(item['evidence'],item['proposition'],model=model)
            row=dict(item_id=item['item_id'],result=result)
            f.write(json.dumps(row,ensure_ascii=False)+'\n');f.flush();predictions.append(row)
    # Join only after writing all model predictions. Assistant references remain development evidence.
    refs={r['item_id']:r for r in readlines(frozen/'CLAIM_REFERENCES.private.jsonl')}
    joined=[];by_ref=Counter();confusion=Counter();by_group={}
    for r in predictions:
        ref=refs[r['item_id']];p=r['result']['entailment_assistance'];truth=ref['reference'];pred=p['verdict']
        by_ref[truth]+=1;confusion[(truth,pred)]+=1
        group=by_group.setdefault(ref['source_group'],Counter());group[(truth,pred)]+=1
        joined.append(dict(item_id=r['item_id'],**{k:v for k,v in ref.items() if k!='item_id'},prediction=pred,status=p['status']))
    def matrix(c):return [{'reference':a,'prediction':b,'count':v} for (a,b),v in sorted(c.items())]
    report=dict(protocol='event-skill-candidate32-cpu-v1',model_revision=Path(snapshot).name,
        model_loads=1,device='cpu',cpu_forward_items=sum(r['result']['entailment_assistance']['status']=='CPU_scored' for r in predictions),
        calls=32,load_ns=load_ns,skill_total_ns=sum(r['result']['elapsed_ns'] for r in predictions),
        nli_inference_and_tokenization_ns=sum(r['result']['entailment_assistance']['elapsed_ns'] for r in predictions),
        capacity_not_scored=sum(r['result']['entailment_assistance']['status']=='capacity_not_scored' for r in predictions),
        references=dict(by_ref),confusion=matrix(confusion),
        false_pass=sum(v for (a,b),v in confusion.items() if a!='supported' and b=='supported'),
        false_pass_denominator=sum(v for a,v in by_ref.items() if a!='supported'),
        false_fail=confusion[('supported','contradicted')],false_fail_denominator=by_ref['supported'],
        supported_abstentions=confusion[('supported','unknown')],
        unknown_outputs=sum(v for (a,b),v in confusion.items() if b=='unknown'),
        rejected_unknown_reference=sum(v for (a,b),v in confusion.items() if a=='unknown' and b!='unknown'),
        group_results=[dict(source_alias='source-'+str(i+1),matrix=matrix(c)) for i,(g,c) in enumerate(sorted(by_group.items()))],
        uncertainty='8 source prefixes, 6 owner/source groups; constructed correlated contrasts, assistant references, no independent qualification',
        natural_quality_reward=None,factuality_detector=False,training_steps=0,thresholds_retuned=False)
    (out/'RESULTS_PRIVATE.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in joined))
    (out/'RESULTS_PUBLIC.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('frozen','snapshot','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();run(a.frozen,a.snapshot,a.output)
