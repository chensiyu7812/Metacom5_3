#!/usr/bin/env python3
from pathlib import Path
import json,hashlib
P=Path(__file__).resolve().parent
read=lambda n:json.loads((P/n).read_text())
canon=lambda x:json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()
sha=lambda b:hashlib.sha256(b).hexdigest()
ss=read('SELECTED_COMPLETE_SESSIONS_PRIVATE.json');mm=read('SAMPLE_MANIFEST.json');rr=read('SEMANTIC_OBSERVATIONS_PRIVATE.json');cc=read('SEMANTIC_REVIEW_COVERAGE.json')
byid={s['sample_id']:s for s in ss}
assert len(byid)==len(ss)==len(mm)==len(cc)==24
assert len({s['source']['owner_id'] for s in ss})==15
for s in ss:
 assert s['split'] in ('train','dev')
 assert sha(canon(s['source']))==s['normalized_source_sha256']
 assert s['review_status']=='complete_session_read_single_assistant_first_pass'
 assert all(s['source']['session_rank']<p['cutoff_rank'] and s['source']['reported_at']<=p['timestamp'] for p in s['legal_prefix_bindings'])
for r in rr:
 s=byid[r['sample_id']];assert r['source_sha256']==s['normalized_source_sha256']
 assert r['owner_id']==s['source']['owner_id'] and r['session_id']==s['source']['session_id']
 assert r['formal_training_label'] is False and r['causal_effect_established'] is False
 for e in r['evidence']:
  t=s['source']['turns'][e['turn_index']];assert e['speaker']==t['role'] and e['quote']==t['text'][e['start_char']:e['end_char']]
result=dict(status='PASS_OFFLINE_SOURCE_AND_QUOTE_INVARIANTS',selected_sessions=24,owners=15,observations=len(rr),checks=['isolated train/dev source hashes','same-owner strict-past ranks and as-of dates','unique source sessions','complete normalized source content hashes','all quote role/turn/offset checks','semantic review status explicit; no formal training labels'],not_checked=['independent human agreement','complete raw mixed-corpus re-extraction','compiler recall across all MP/ME','current target-time validity','G benefit or reward qualification'])
(P/'VALIDATION.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
manifest={p.name:sha(p.read_bytes()) for p in sorted(P.iterdir()) if p.is_file() and p.name!='OUTPUT_HASHES.json'}
(P/'OUTPUT_HASHES.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(result,ensure_ascii=False,indent=2))
