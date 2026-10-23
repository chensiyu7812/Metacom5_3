#!/usr/bin/env python3
"""Count full requests for every locked calibration job without scoring them."""
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.judge_completion import messages_and_schema

ROOT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P3'


def main():
    source=ROOT/'candidate_v1/jobs_private.json'
    jobs=json.loads(source.read_text())
    protocol=json.loads((ROOT/'candidate_v1/protocol.json').read_text())
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(protocol['model'],local_files_only=True)
    rows=[]
    for job in jobs:
        messages,_=messages_and_schema(job['evidence'],job['reply'],recheck=job['recheck'])
        ids=tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,
            return_dict=False,enable_thinking=protocol['decode']['thinking'])
        assert len(ids)<protocol['runtime']['native_context']
        rows.append(dict(job_id=job['job_id'],group=job['group'],input_tokens=len(ids)))
    profile=dict(status='FULL_LOCKED_REQUESTS_FIT_WITHOUT_TRUNCATION',rows=rows,
        groups=dict(Counter(r['group'] for r in rows)),
        min_input_tokens=min(r['input_tokens'] for r in rows),
        median_input_tokens=statistics.median(r['input_tokens'] for r in rows),
        max_input_tokens=max(r['input_tokens'] for r in rows),
        model_context=protocol['runtime']['native_context'],task_output_cap=None,
        model_calls=0,human_labels_read=0,
        source_files={str(p.relative_to(PROJECT)):sha256_file(p) for p in [source,Path(__file__),
            ROOT/'candidate_v1/protocol.json',PROJECT/'src/metacom_pm/rl1/judge_completion.py']})
    target=ROOT/'verification/full_request_context.json'
    with target.open('x') as f:f.write(json.dumps(profile,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in profile.items() if k not in ('rows','source_files')},ensure_ascii=False))


if __name__=='__main__':main()
