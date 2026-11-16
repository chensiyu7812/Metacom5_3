#!/usr/bin/env python3
"""Offline audit-only sampler. Reads only frozen isolated train/dev source evidence."""
from pathlib import Path
import json, hashlib
from collections import defaultdict, Counter
ROOT=Path(__file__).resolve().parents[4]
OUT=Path(__file__).resolve().parent
BASE=ROOT/'outputs/pm_rl1/completion_20260930_v2/P3/common_evidence'
SEED='pmrl1-memory-preparation-20261115-v1'
def sha_bytes(b):return hashlib.sha256(b).hexdigest()
def canonical(x):return json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
def save(name,x): (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
freeze=json.loads((BASE/'input_freeze.json').read_text())
inputs={}
for name in ('evidence_pool_private.json','source_map_private.json'):
 path=BASE/name; actual=sha_bytes(path.read_bytes());assert actual==freeze['files'][name];inputs[str(path.relative_to(ROOT))]=actual
inputs[str((BASE/'input_freeze.json').relative_to(ROOT))]=sha_bytes((BASE/'input_freeze.json').read_bytes())
pool=json.loads((BASE/'evidence_pool_private.json').read_text());maps=json.loads((BASE/'source_map_private.json').read_text())
assert len(pool)==len(maps)==42 and all(m['split'] in ('train','dev') for m in maps)
bykey={}; owners={}
for m in maps:
 p=m['prefix'];owner=m['owner'];assert owner==p['owner_id'];owners[owner]=m['split']
 e=pool[m['prefix_identity']]; mapping={x['blind_id']:x for x in m['source_map']}
 for s in e['legal_past_sessions']:
  sm=mapping[s['id']];assert sm['rank']<p['cutoff_rank'] and s['date']<=p['timestamp']
  turns=[dict(turn_index=i,role=t['role'],text=t['text']) for i,t in enumerate(s['turns'])]
  assert [t['id'] for t in s['turns']]==[s['id']+':T'+str(i).zfill(3) for i in range(len(turns))]
  key=owner+'/'+sm['session']; normalized=dict(owner_id=owner,session_id=sm['session'],session_rank=sm['rank'],reported_at=s['date'],turns=turns)
  h=sha_bytes(canonical(normalized)); proof=dict(prefix_identity=m['prefix_identity'],cutoff_rank=p['cutoff_rank'],timestamp=p['timestamp'])
  if key in bykey:assert bykey[key]['normalized_source_sha256']==h;bykey[key]['legal_prefix_bindings'].append(proof)
  else:bykey[key]=dict(key=key,split=m['split'],normalized_source_sha256=h,selection_hash=sha_bytes((SEED+'|session|'+key).encode()),source=normalized,legal_prefix_bindings=[proof])
# Round-robin over all owners sorted by predeclared hash; then per-owner sessions by hash.
owner_order=sorted(owners,key=lambda o:sha_bytes((SEED+'|owner|'+o).encode()))
byowner={o:sorted([s for s in bykey.values() if s['source']['owner_id']==o],key=lambda s:s['selection_hash']) for o in owner_order}
selected=[]
for r in range(max(map(len,byowner.values()))):
 for owner in owner_order:
  if len(byowner[owner])>r:selected.append(byowner[owner][r])
  if len(selected)==24:break
 if len(selected)==24:break
assert len(selected)==24 and len(set(x['key'] for x in selected))==24
rows=[]
for i,x in enumerate(selected,1):
 x['sample_id']='M'+str(i).zfill(2);x['review_status']='pending';
 rows.append({k:v for k,v in x.items() if k!='source'}|dict(owner_id=x['source']['owner_id'],session_id=x['source']['session_id'],reported_at=x['source']['reported_at'],session_rank=x['source']['session_rank'],turns=len(x['source']['turns']),words=sum(len(t['text'].split()) for t in x['source']['turns']),completeness='complete_session_as_exported_by_frozen_legal_evidence; not independently reread from mixed raw corpus'))
save('INPUT_HASHES.json',inputs);save('SELECTION_PROTOCOL.json',dict(seed=SEED,scope='train/dev isolated existing evidence only; excludes all test and raw mixed corpus',sampling='round-robin owners in sha256(seed|owner|owner) order, sessions in sha256(seed|session|owner/session) order; stop at 24; no semantic preselection',population_sessions=len(bykey),owners=owners,owner_order=owner_order,selected_by_owner=dict(Counter(r['owner_id'] for r in rows)),selected_by_split=dict(Counter(r['split'] for r in rows)),semantic_review_is_separate=True,model_calls=0,paid_calls=0))
save('SAMPLE_MANIFEST.json',rows);save('SELECTED_COMPLETE_SESSIONS_PRIVATE.json',selected)
with (OUT/'REVIEW_PACK_PRIVATE.txt').open('w') as f:
 for x in selected:
  f.write('\n===== '+x['sample_id']+' '+x['key']+' '+x['source']['reported_at']+' =====\n')
  for t in x['source']['turns']:f.write(str(t['turn_index'])+' '+t['role']+': '+t['text']+'\n')
print(json.dumps(dict(population=len(bykey),selected=len(rows),owners=len(owners),total_words=sum(r['words'] for r in rows),inputs=inputs,first6=[(r['sample_id'],r['owner_id'],r['session_id'],r['words']) for r in rows[:6]]),ensure_ascii=False,indent=2))
