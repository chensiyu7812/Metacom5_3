#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
P=Path(__file__).resolve().parent;ROOT=P.parents[3];BASE=ROOT/'outputs/pm_rl1/resource_organization_20261029_v1'
read=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
manifest=read(BASE/'OUTPUT_MANIFEST.json');catalog_manifest=read(BASE/'CATALOG_MANIFEST.json')
assert sha(BASE/'CATALOG_MANIFEST.json')==manifest['CATALOG_MANIFEST.json']
inputs={str((BASE/'CATALOG_MANIFEST.json').relative_to(ROOT)):sha(BASE/'CATALOG_MANIFEST.json')};hits={}
targets={'mp::mvu_2a73b2853cdd499d576e2ab5':dict(sample_id='M17',turn=11,note='原文明确 I have hung up 且对方生气；past_report 改写为 avoids hanging up，无法忠实表达已尝试和不良结果。是当前 MP 陈述层的语义偏移；完整 evidence 仍含原文，不等于 G 必然看不到。'), 'mp::mvu_785a6f6f9e719c52ef13fc57':dict(sample_id='M04',turn=11,note='原文 joined workshop that helped, but imposter syndrome creeps in；MP past_report 仅保留 enrolled ... address writer block，结果与残留困难未结构化。引用仍保留，不能宣称原文或交付证据完全丢失。'), 'me::mvu_c8da36ab41b1d4da5464dd8d':dict(sample_id='M04',turn=13,note='ME evidence 自述 It helps ... online community supportive；action_stage unknown 且 observed_outcome null，past_report 仅 receives emotional support。是结果未进结构字段，缺少特定行动归因，应保留主观感受而不强编为单项干预效果。')}
for row in catalog_manifest:
 if row['owner'] not in ('p8','p2'):continue
 assert row['split'] in ('train','dev')
 rel='catalogs_private/'+row['prefix_identity']+'.json';path=BASE/rel;assert sha(path)==manifest[rel];inputs[str(path.relative_to(ROOT))]=sha(path)
 a=read(path)
 for x in a['memory']:
  if x['key'] not in targets:continue
  if x['key'] not in hits:hits[x['key']]=dict(**targets[x['key']],item=x,body=json.loads(x['content']),prefix_bindings=[])
  hits[x['key']]['prefix_bindings'].append(dict(prefix_identity=row['prefix_identity'],source_path=str(path.relative_to(ROOT)),source_sha256=sha(path)))
assert set(hits)==set(targets)
ss={s['sample_id']:s for s in read(P/'SELECTED_COMPLETE_SESSIONS_PRIVATE.json')}
for x in hits.values():
 s=ss[x['sample_id']];t=s['source']['turns'][x['turn']]
 assert any(e['quote']==t['text'] and e['speaker']==t['role'] for e in x['body']['evidence'])
 x['source_quote_binding']=dict(ordinal_turn=x['turn'],text=t['text'],normalized_session_sha256=s['normalized_source_sha256'],binding='exact role and quote; historical raw turn_index differs by one from exported ordinal; not silently equated')
 x['scope']='frozen target-time resource catalog; not all historical compiler outputs; not typed-view G receipt'
(P/'CURRENT_VIEW_COMPARISONS_PRIVATE.json').write_text(json.dumps(list(hits.values()),ensure_ascii=False,indent=2)+'\n')
(P/'COMPARISON_INPUT_HASHES.json').write_text(json.dumps(inputs,ensure_ascii=False,indent=2)+'\n')
print('3 exact source-to-current-catalog comparisons; frozen input hashes verified; all source quotes matched')
