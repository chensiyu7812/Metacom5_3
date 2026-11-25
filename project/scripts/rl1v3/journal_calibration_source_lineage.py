#!/usr/bin/env python3
"""Finite lineage sidecar for the frozen calibration96; no reference relabeling."""
import argparse
from collections import defaultdict,Counter
import hashlib,json,re
from pathlib import Path


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def read(path):return json.loads(Path(path).read_text())
def jl(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]
def family(owner,sid):
    match=re.fullmatch(r'(?:esc|esconv_)([0-9]+)',sid)
    return 'esconv:esconv_'+str(int(match[1])).zfill(4) if match else 'evoemo_owner:'+owner


def build(items_dir,out):
    items_dir,out=Path(items_dir),Path(out);out.mkdir(parents=True,exist_ok=False)
    manifest=read(items_dir/'FREEZE_MANIFEST.json')
    for name,h in manifest['output_sha256'].items():assert sha(items_dir/name)==h
    raw_path=next(Path(p) for p in manifest['inputs_sha256'] if p.endswith('/data/external/evo_emo.json'))
    assert sha(raw_path)==manifest['inputs_sha256'][str(raw_path)]
    aligned_path=next(Path(p) for p in manifest['inputs_sha256'] if p.endswith('/gemini_qualification_v2/aligned_results.json'))
    assert sha(aligned_path)==manifest['inputs_sha256'][str(aligned_path)]
    aligned={r['presentation_id']:r for r in read(aligned_path)}
    raw=read(raw_path);owners={u['id']:u for u in raw};source_index=defaultdict(list)
    for user in raw:
        for source in user['dialog_history']:
            sequence=tuple((t['role'],t['content']) for t in source['dialogue'])
            source_index[sequence].append(dict(owner=user['id'],session_id=source['id'],family=family(user['id'],source['id'])))
    items=jl(items_dir/'ITEMS_PRIVATE.jsonl');by_group=defaultdict(list)
    for item in items:by_group[item['source_group']].append(item)
    tokens={g:set() for g in by_group};proofs=[];unknown=[]
    def add_owner(group,owner,reason,locator):
        if owner not in owners:
            unknown.append(dict(source_group=group,reason='owner_missing_from_bound_raw',owner=owner));return
        tokens[group].add('owner:'+owner)
        families=sorted({family(owner,s['id']) for s in owners[owner]['dialog_history']})
        tokens[group].update('family:'+f for f in families)
        proofs.append(dict(source_group=group,kind=reason,owner=owner,locator=locator,
            owner_history_families=families,scope='static lineage/dependence grouping, not an as-of runtime read grant'))
    for group,members in by_group.items():
        if group.startswith('memory-owner-family:'):
            for owner in group.split(':',1)[1].split('+'):add_owner(group,owner,'frozen_memory_owner_group',{'source_group':group})
        elif group.startswith('historical-DG:'):
            for item in members:
                pid=item['payload']['request']['presentation_id'];row=aligned[pid]
                assert item['payload']['task']=='DG' and str(row['cluster_id'])==group.split(':',1)[1]
                add_owner(group,str(row['cluster_id']),'historical_DG_cluster_owner_metadata',{'presentation_id':pid})
        elif group.startswith('historical-ESC:'):
            for item in members:
                pid=item['payload']['request']['presentation_id'];row=aligned[pid]
                assert item['payload']['task']=='ESC' and str(row['cluster_id'])==group.split(':',1)[1]
                f=family('',str(row['cluster_id']));assert f.startswith('esconv:')
                tokens[group].add('family:'+f);proofs.append(dict(source_group=group,kind='historical_ESC_cluster_family',family=f,presentation_id=pid))
        elif group.startswith('annomi-video:'):
            video=group.removeprefix('annomi-video:');tokens[group].add('annomi-video:'+video)
            proofs.append(dict(source_group=group,kind='frozen_AnnoMI_video_family',video=video))
        elif group.startswith('historical-evidence:'):
            # Only exact role/text matches. No fuzzy name or semantic inference.
            source=members[0]['payload']['source']
            assert all(m['payload']['source']==source for m in members)
            fragments=[(s['id'],'complete_session',tuple((t['role'],t['text']) for t in s['turns'])) for s in source['legal_past_sessions']]
            fragments.append(('current_prefix','exact_prefix',tuple((t['role'],t['text']) for t in source['current_prefix'])))
            for name,kind,sequence in fragments:
                matches=source_index.get(sequence,[]) if kind=='complete_session' else [m for full,ms in source_index.items() if len(sequence)>=3 and full[:len(sequence)]==sequence for m in ms]
                families={m['family'] for m in matches}
                if not matches or len(families)!=1:
                    unknown.append(dict(source_group=group,fragment=name,reason='unmatched_or_ambiguous_exact_source',candidate_count=len(matches)));continue
                for m in matches:
                    add_owner(group,m['owner'],'exact_'+kind+'_role_text_match',dict(fragment=name,
                        source_session=m['session_id'],source_sequence_sha256=digest(sequence),source_family=m['family']))
        else:unknown.append(dict(source_group=group,reason='unrecognized_source_namespace'))
    parent={g:g for g in by_group}
    def find(g):
        while parent[g]!=g:parent[g]=parent[parent[g]];g=parent[g]
        return g
    edges=[];groups=sorted(by_group)
    for i,left in enumerate(groups):
        for right in groups[i+1:]:
            shared=sorted(tokens[left]&tokens[right])
            if shared:
                parent[find(right)]=find(left);edges.append(dict(left=left,right=right,shared_lineage_tokens=shared))
    components=defaultdict(list)
    for g in groups:components[find(g)].append(g)
    mapped={};details=[]
    for members in sorted(components.values()):
        cid='calibration-component:'+digest(sorted(members))[:24]
        for g in members:mapped[g]=cid
        entries=[x for x in items if x['source_group'] in members]
        details.append(dict(component_id=cid,source_groups=sorted(members),items=len(entries),
            category_counts=dict(Counter(x['category'] for x in entries)),cross_construct_score=None))
    sidecar=dict(protocol='pmrl1-j-calibration96-source-lineage-v1',items=len(items),
        original_source_group_labels=len(groups),known_components=len(details),components=details,
        item_mapping=[dict(item_id=x['item_id'],category=x['category'],original_source_group=x['source_group'],component_id=mapped[x['source_group']]) for x in items],
        confirmed_edges=edges,proofs=proofs,unknown_mappings=unknown,
        limitations=['Components describe proved owner/family links, not statistically independent units.',
            'Owner-history family closure is a conservative dependence grouping, not runtime evidence or future-read permission.',
            'No approximate source match, semantic inference, relabeling, resampling, judge substitution or cross-construct score.'],
        inputs_sha256={str(items_dir/'FREEZE_MANIFEST.json'):sha(items_dir/'FREEZE_MANIFEST.json'),
            str(items_dir/'ITEMS_PRIVATE.jsonl'):sha(items_dir/'ITEMS_PRIVATE.jsonl'),str(raw_path):sha(raw_path),str(aligned_path):sha(aligned_path)},
        code_sha256=sha(__file__))
    assert len(sidecar['item_mapping'])==len({x['item_id'] for x in sidecar['item_mapping']})==96
    assert sum(x['items'] for x in details)==96 and len(mapped)==21
    with (out/'SOURCE_LINEAGE_PRIVATE.json').open('x') as f:json.dump(sidecar,f,sort_keys=True,indent=2)
    # Reconfirm original frozen bytes after building this sidecar.
    for name,h in manifest['output_sha256'].items():assert sha(items_dir/name)==h
    receipt=dict(status='CPU_LINEAGE_MAPPING_PASSED',items=96,original_labels=21,known_components=len(details),
        confirmed_group_edges=len(edges),unknown_fragments=len(unknown),original_items_references_changed=False,
        predictions_or_references_recomputed=False,cross_construct_score=None,semantic_qualification=False,
        sidecar_sha256=sha(out/'SOURCE_LINEAGE_PRIVATE.json'))
    with (out/'RECEIPT.json').open('x') as f:json.dump(receipt,f,sort_keys=True,indent=2)
    return receipt


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--items',required=True);p.add_argument('--out',required=True);a=p.parse_args()
    print(json.dumps(build(a.items,a.out),indent=2))
