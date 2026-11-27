#!/usr/bin/env python3
"""Evaluation-side known-answer/invalid-output checks on frozen REAL tasks.

Generated strings below are scorer fixtures, never model predictions.
"""
import argparse
from pathlib import Path
import json
from metacom_pm.need_aware.data.contracts import load_runtime
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl
from metacom_pm.need_aware.evaluation.score import load_eval,score_predictions

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--artifacts',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.artifacts);out=Path(a.output);tasks=load_runtime(root/'runtime/tasks.mcq.jsonl');ev=load_eval(root/'evaluation/tasks.mcq.jsonl')
    summaries={}
    for label in ['known_answer','invalid_output']:
        preds=[{'task_id':t.task_id,'output':f'Final Answer: {ev[t.task_id].gold_choice_id}' if label=='known_answer' else 'unparseable output',
                'result_kind':'plumbing','status':'completed','generator':'scorer fixture; no model'} for t in tasks]
        records,summary=score_predictions(tasks,ev,preds,'plumbing')
        write_jsonl(out/f'{label}.predictions.jsonl',preds);write_jsonl(out/f'{label}.scored.jsonl',records);write_json(out/f'{label}.summary.json',summary)
        summaries[label]={k:v for k,v in summary.items() if k!='by_category'}
    write_json(out/'receipt.json',{'model_calls':0,'result_kind':'plumbing','checks':summaries});print(json.dumps(summaries,indent=2))
