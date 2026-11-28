#!/usr/bin/env python3
"""One bounded retrospective WP2 audit; all products are development-only.

Full legal histories are resolved and hash-checked. Lexical search exposes
candidate alternative passages, never proves semantic absence or sufficiency.
No labels here may be consumed by a training builder.
"""
import argparse
from collections import Counter
import json
import os
from pathlib import Path
import re

from metacom_pm.need_aware.data.v11 import jsonl, verify_old
from metacom_pm.need_aware.data.contracts import load_runtime, digest
from metacom_pm.need_aware.data.history import HistoryResolver
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file


def run(old, scored, allocation, out):
    old,scored,allocation,out=map(Path,(old,scored,allocation,out))
    if out.exists():raise FileExistsError('bounded audit already materialized')
    os.umask(0o077);verify_old(old)
    a=json.loads(allocation.read_text());selected=a['review']['union']
    tasks={t.task_id:t for t in load_runtime(old/'runtime/tasks.mcq.jsonl')}
    ev={r['task_id']:r for r in jsonl(old/'evaluation/tasks.mcq.jsonl')}
    direct={r['task_id']:r for r in jsonl(old/'direct/direct.jsonl')}
    cells={(m,arm):{r['task_id']:r for r in jsonl(scored/f'scored.{m}.{arm}.private.jsonl')}
           for m in ('G0e','Qwen35') for arm in 'CD'}
    resolver=HistoryResolver(old/'runtime');cue=re.compile(a['visible_route_rule']['pattern'])
    routing={};packets=[];labels=[]
    for model in ('G0e','Qwen35'):
        result=Counter()
        for tid in sorted(tasks):
            c,d=cells[model,'C'][tid],cells[model,'D'][tid]
            if c['status']!= 'completed' or d['status']!='completed':continue
            src=resolver.resolve_direct(tasks[tid],direct[tid],'C')
            visible=bool(cue.search('\n'.join(r.original_text for r in src if r.speaker=='user')))
            truth=ev[tid]['category']['who']=='others'
            result['paired_tasks']+=1;result['C_correct']+=int(c['correct']);result['D_correct']+=int(d['correct'])
            result['posthoc_CD_upper_correct']+=int(c['correct'] or d['correct'])
            result['true_who_route_correct']+=int((d if truth else c)['correct'])
            result['visible_cue_route_correct']+=int((d if visible else c)['correct'])
            result['visible_cue_selected_D']+=visible
            result['visible_cue_disagrees_with_who']+=visible!=truth
        routing[model]=dict(result)
    stop={'about','with','that','this','have','your','their','from','some','what','when','which','would','could','should','being','into','more','than','after','during','there','them','been','they','like','user','prefers','enjoys','preference','please','forget'}
    for tid in selected:
        task=tasks[tid];e=ev[tid];records=resolver.resolve(task)
        source=resolver.resolve_direct(task,direct[tid],'C') if direct[tid]['status']=='located_unique' else []
        terms={t for t in re.findall(r'[a-z]{4,}',e['gold_preference'].lower()) if t not in stop}
        candidates=[]
        for r in records:
            hits=terms&set(re.findall(r'[a-z]{4,}',r.original_text.lower()))
            if hits:candidates.append((len(hits),r.order,r.to_dict()))
        candidates.sort(key=lambda x:(-x[0],x[1]))
        packets.append(dict(task_id=tid,task=task.to_dict(),evaluation=e,
                            full_legal_history=[r.to_dict() for r in records],
                            full_legal_history_sha256=digest([r.to_dict() for r in records]),
                            direct=[r.to_dict() for r in source],
                            alternative_candidates=[r for _,_,r in candidates[:8]],
                            lexical_search=dict(all_records_scanned=len(records),terms=sorted(terms),candidate_count=len(candidates),
                                                limitation='Retrieval candidates, not semantic absence/sufficiency proof'),
                            outcomes={m:{arm:cells[m,arm][tid] for arm in 'CD'} for m in ('G0e','Qwen35')}))
        labels.append(dict(task_id=tid,usage='development_diagnostic_only_never_training',
                           evidence_sufficiency='unknown',holder='unknown',beneficiary='unknown',
                           gold_status='not_adjudicated',semantic_error_type='unresolved',
                           source_refs=[{'source_id':r.source_id,'coordinates':r.coordinates,'sha256':r.original_text_sha256} for r in source],
                           review_status='awaiting_source_review',official_score_changed=False))
    write_jsonl(out/'PACKETS.private.jsonl',packets);write_jsonl(out/'ANNOTATION_SEED.private.jsonl',labels)
    report=dict(protocol='naa-v11-bounded-wp2-review-v1',allocation_sha256=sha_file(allocation),
                selected_who_others=len(a['review']['who_others']),selected_C_errors=40,overlap=a['review']['overlap'],
                union=len(selected),full_histories_verified=len(packets),routing=routing,
                visible_route_rule=a['visible_route_rule'],
                interpretation='All routing is retrospective development diagnosis, never a learned routing PM or confirmatory result. Semantic labels require actual source review; full lexical scan cannot prove absence.',
                packets_sha256=sha_file(out/'PACKETS.private.jsonl'),new_model_calls=0,training_use_prohibited=True)
    write_json(out/'RECEIPT.json',report);return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('old','scored','allocation','out'):p.add_argument('--'+name,required=True)
    a=p.parse_args();print(json.dumps(run(a.old,a.scored,a.allocation,a.out),indent=2))
