#!/usr/bin/env python3
"""Select causal training-family source prefixes before any skill prediction.

Keep fold 6 sealed. Parse only eligible metadata-selected lines; exclude all
GSWS owner/family components and ESConv/EvoEmo overlap. No goal/gold labels used.
"""
import argparse,hashlib,json,re
from pathlib import Path


def prepare(registry, metadata, gsws_resources, output):
    out=Path(output);out.mkdir(parents=True,exist_ok=False)
    meta=json.loads(Path(metadata).read_text())
    gsws=[json.loads(s) for s in Path(gsws_resources).read_text().splitlines() if s.strip()]
    blocked={r['family_id'] for r in gsws}|{f for r in gsws for f in r.get('ancestor_family_ids',[])}
    train_owners={'p5','p6'}  # historical train, outside GSWS and sealed original fold 6
    for owner in train_owners:
        assert meta['folds']['historical_rl1_split'][owner]=='train'
        assert meta['folds']['fold_of_owner'][owner]!=6
    candidates=[]
    for raw in Path(registry).open():
        # Metadata occurs before the body in this pinned canonical file.
        fold=re.search(r'"fold":(\d+)',raw)
        owner=re.search(r'"owner_id":"([^"]+)"',raw)
        dataset=re.search(r'"dataset":"([^"]+)"',raw)
        split=re.search(r'"source_split":"([^"]+)"',raw)
        if (fold and int(fold[1])==6) or not split or split[1]!='train':continue
        if dataset[1]=='es_memeval_evoemo_public_v1' and owner[1] not in train_owners:continue
        if dataset[1] not in ('ESConv','es_memeval_evoemo_public_v1'):continue
        row=json.loads(raw);s=row['source']
        if s['family_id'] in blocked or set(s['ancestor_family_ids']) & blocked:continue
        if dataset[1]=='ESConv' and (s['excluded_for_overlap'] or s['family_id'] in meta['excluded_families']):continue
        turns=s['turns'];idx=None
        for i,t in enumerate(turns[:12]):
            if t['role']=='seeker' and len(t['text'])>=40 and re.search(r'\b(?:plan|planned|want|wanted|tried|trying|started|not|never|might|could|decided|offered)\b',t['text'],re.I):
                idx=i;break
        if idx is None or idx+1>=len(turns) or turns[idx+1]['role']!='supporter':continue
        family=s['family_id'];key=hashlib.sha256(('event-skill-dialogue-v1|'+family+'|'+s['session_id']).encode()).hexdigest()
        candidates.append(dict(key=key,source_id=row.get('source_id'),owner_id=s['owner_id'],family_id=family,
            dataset=s['dataset'],source_split=s['source_split'],fold=row['fold'],session_id=s['session_id'],
            cutoff_turn=idx,report_time=s['date'],source_transcript_sha256=s['transcript_sha256'],
            prefix=[dict(evidence_id=f'C{j}',speaker=t['role'],text=t['text'],reported_at=s['date'],origin='current_visible') for j,t in enumerate(turns[:idx+1])],
            future_turns_read_into_input=False,exposure='historical public research train; newly selected development capability material'))
    selected=[];seen=set();counts={}
    # 4 ESConv families; 2 source sessions per each of 2 permitted EvoEmo owners.
    for row in sorted(candidates,key=lambda r:r['key']):
        group='ESConv' if row['dataset']=='ESConv' else row['owner_id'];cap=4 if group=='ESConv' else 2
        if counts.get(group,0)>=cap or row['family_id'] in seen:continue
        counts[group]=counts.get(group,0)+1;seen.add(row['family_id']);selected.append(row)
    for n,row in enumerate(selected,1):row['alias']=f'E{n:02}'
    (out/'PREFIXES.private.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in selected))
    report=dict(protocol='gsws-event-dialogue-training-prefix-v1',selection='family hash order; first cue-bearing seeker before supporter within first12 turns; fixed before predictions',
        selected=len(selected),groups=counts,causal_prefixes=True,fold6_included=False,gsws_family_overlap=0,
        labels='not generated; semantic review pending; runtime input is source only',actual_model_calls=0,
        aliases=[dict(alias=r['alias'],dataset=r['dataset'],fold=r['fold'],prefix_turns=len(r['prefix'])) for r in selected])
    (out/'SELECTION_PUBLIC.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('registry','metadata','gsws-resources','output'):p.add_argument('--'+name,required=True)
    a=p.parse_args();prepare(a.registry,a.metadata,a.gsws_resources,a.output)
