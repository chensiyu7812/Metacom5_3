#!/usr/bin/env python3
"""Availability census only; OP/ENPMR are not admitted to NAA runtime."""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
from metacom_pm.need_aware.data.personamem import sha_file,write_json

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--upstream-root',required=True);p.add_argument('--output',required=True);a=p.parse_args();root=Path(a.upstream_root)
    commit=lambda p:subprocess.check_output(['git','-C',str(p),'rev-parse','HEAD'],text=True).strip()
    op=root/'OP-Bench';file=op/'data/locomo10_overpersonalized.json';data=json.loads(file.read_text());counts=Counter();users=0
    for pair in data:
        for person in pair.values():
            users+=1
            for k,values in person['tasks'].items():
                counts[k]+=sum(len(x['questions']) for x in values) if k=='diversity' else len(values)
    en=root/'ENPMR-Bench';ef=en/'data/pmr_bench_w_history_final.json';ed=json.loads(ef.read_text());dialogs=[d for r in ed for d in r['dialog']];mem=[m for r in ed for m in r['memory_bank']]
    report={'OP-Bench':{'revision':commit(op),'data_sha256':sha_file(file),'conversation_families':len(data),'users':users,
                'actual_queries':dict(counts),'total_queries':sum(counts.values()),'repetition_groups':sum(len(r['tasks']['diversity']) for pair in data for r in pair.values()),
                'runtime_admitted':False,'license':'no declared software license; NOTICE requests licensing/provenance resolution',
                'default_coverage':'official config defaults use_both_personas=false; 20-user denominator requires true',
                'evaluator':'src/opbench/scoring.py Scorer: API judges; diversity pairwise normalized embedding cosine; not run'},
            'ENPMR-Bench':{'revision':commit(en),'data_sha256':sha_file(ef),'personas':len(ed),'dialogues':len(dialogs),'memories':len(mem),
                'dialogue_types':dict(Counter(d['type'] for d in dialogs)),
                'dialogues_without_structured_date':sum(not any(x in d for x in ['date','timestamp','time','日期','时间']) for d in dialogs),
                'memories_with_date_field':sum(bool(m.get('date')) for m in mem),
                'license':'no LICENSE or data license declaration found','runtime_admitted':False,
                'status':'blocked: license and target-before-memory chronology unresolved',
                'evaluator':'no executable evaluation code in pinned repository (README/data/assets only)'},
            'model_calls':0,'paid_calls':0}
    write_json(a.output,report);print(json.dumps(report,indent=2))
