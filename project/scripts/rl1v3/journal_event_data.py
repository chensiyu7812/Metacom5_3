#!/usr/bin/env python3
"""Prepare private MAVEN-FACT supervision and inspect original coordinates.

No model calls/training. Official train only; gold arguments/relations/supporting
words stay in targets, not in source-only inference input. Never redistributes RAW.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import time


def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(8*1024*1024),b''):h.update(b)
    return h.hexdigest()


def prepare(source, output):
    start=time.monotonic_ns();out=Path(output);out.mkdir(parents=True,exist_ok=False)
    labels=Counter();checks=Counter();relations=Counter();splits=Counter();missing=Counter();roles=Counter()
    document_ids=set();mention_ids=set();diagnostic=[];selected=Counter();problems=[]
    with (out/'INPUTS.private.jsonl').open('x') as inputs,(out/'TARGETS.private.jsonl').open('x') as targets:
        for line in Path(source).open():
            d=json.loads(line);did=d['id'];checks['documents']+=1
            checks['duplicate_document_ids']+=did in document_ids;document_ids.add(did)
            split='internal_dev' if int(hashlib.sha256(('gsws-event-data-v1|'+did).encode()).hexdigest()[:8],16)%10==0 else 'train_candidate'
            splits[split+'_documents']+=1;checks['documents_with_arguments']+=d['has_arguments']
            ids={e['id'] for e in d['events']}|{t['id'] for t in d['TIMEX']}
            for e in d['events']:
                checks['event_clusters']+=1
                for arg in e.get('arguments',[]):
                    roles[arg['type']]+=1
                    for a in arg['mentions']:
                        lo,hi=a['offset'];checks['argument_mentions']+=1
                        checks['argument_char_exact']+=d['document'][lo:hi]==a['mention']
                for m in e['mention']:
                    sid=m['sent_id'];lo,hi=m['offset'];mid=m['id'];label=m['factuality']
                    labels[label]+=1;checks['mentions']+=1;splits[split+'_mentions']+=1
                    checks['duplicate_mention_ids']+=mid in mention_ids;mention_ids.add(mid)
                    trigger_exact=' '.join(d['tokens'][sid][lo:hi])==m['trigger_word']
                    checks['trigger_token_exact']+=trigger_exact
                    ev=m['evidence_word'];offs=m['evidence_offset']
                    if ev is None:missing[label]+=1;ev_ok=offs is None
                    else:
                        checks['mentions_with_supporting_words']+=1
                        valid_offsets=isinstance(offs,list) and all(isinstance(x,list) and len(x)==2
                            and type(x[0]) is int and 0<=x[0]<len(d['tokens'])
                            and type(x[1]) is int and 0<=x[1]<len(d['tokens'][x[0]]) for x in offs)
                        ev_ok=valid_offsets and len(ev)==len(offs) and all(d['tokens'][s][i]==w for (s,i),w in zip(offs,ev))
                        checks['supporting_offset_out_of_bounds']+=not valid_offsets
                        checks['supporting_words_exact']+=ev_ok
                        checks['cross_sentence_evidence_mentions']+=any(s!=sid for s,i in (offs or []))
                    if not(trigger_exact and ev_ok):problems.append(dict(document_id=did,mention_id=mid,trigger_exact=trigger_exact,evidence_exact=ev_ok))
                    # Whole source document, no gold relations/arguments/factuality.
                    # Annotated trigger localization is explicit, not a learned detector result.
                    row=dict(item_id=mid,document_id=did,split=split,
                        input=dict(document=d['document'],sentences=d['sentences'],tokens=d['tokens'],
                            target_trigger=dict(sent_id=sid,offset=[lo,hi],text=m['trigger_word']),
                            localization='official annotated trigger; conditional EFD, not end-to-end extraction'),
                        provenance=dict(dataset='MAVEN-FACT',official_split='train',coordinate_contract='sentence-token half-open; arguments document-char half-open'))
                    target=dict(item_id=mid,factuality=label,supporting_words=ev,supporting_offsets=offs,
                        event_cluster_id=e['id'],arguments=e.get('arguments'),
                        temporal_relations={k:[pair for pair in pairs if e['id'] in pair] for k,pairs in d['temporal_relations'].items()},
                        has_arguments=d['has_arguments'],action_stage_label=None,current_user_identity_label=None,
                        source='official supervision, not a runtime observation',coordinate_eligible=trigger_exact and ev_ok)
                    inputs.write(json.dumps(row,ensure_ascii=False)+'\n');targets.write(json.dumps(target,ensure_ascii=False)+'\n')
                    if split=='internal_dev' and selected[label]<10 and trigger_exact and ev_ok:
                        selected[label]+=1;diagnostic.append(dict(item_id=mid,document_id=did,label=label))
            for t in d['TIMEX']:
                lo,hi=t['offset'];checks['timex_mentions']+=1
                checks['timex_token_exact']+=' '.join(d['tokens'][t['sent_id']][lo:hi])==t['mention']
            for typ,edges in d['temporal_relations'].items():
                relations[typ]+=len(edges)
                for edge in edges:
                    checks['temporal_edges']+=1;checks['temporal_endpoints_resolved']+=all(x in ids for x in edge)
            for typ,edges in d['causal_relation'].items():relations['causal_'+typ]+=len(edges)
            relations['subevent']+=len(d['subevent_relations'])
    n=sum(labels.values());major=labels['CT+'];major_f1=2*major/(n+major)
    report=dict(protocol='gsws-event-training-entry-v1',source_sha256=sha(source),source_bytes=Path(source).stat().st_size,
        official_split='train',grain='event mention; split and uncertainty grouping by document',counts=dict(checks),
        labels=dict(labels),null_supporting_words_by_label=dict(missing),relations=dict(relations),argument_role_counts=dict(roles),
        split_counts=dict(splits),diagnostic_counts=dict(selected),coordinate_problem_count=len(problems),
        majority_baseline=dict(accuracy=major/n,macro_f1=major_f1/5,balanced_accuracy=.2,minority_recall=0),
        generated_model_outputs=0,training_steps=0,qualified_semantic_labels=False,
        intended_use='local research entry; document EFD does not supervise companion goals/action completion',
        elapsed_ns=time.monotonic_ns()-start)
    for name,value in [('PROFILE_PUBLIC.json',report),('COORDINATE_PROBLEMS.private.json',problems),('DIAGNOSTIC50.private.json',diagnostic)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    (out/'FILES_PRIVATE.json').write_text(json.dumps({p.name:sha(p) for p in out.iterdir() if p.is_file()},indent=2)+'\n')
    print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();prepare(a.source,a.output)
