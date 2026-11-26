#!/usr/bin/env python3
"""Public-source metadata and synthetic ESCA window probe; no model calls.
Existing pinned source checkouts required. Downloaded evaluation data stays quarantined.
"""
from pathlib import Path
import json,subprocess,hashlib,ast,re,urllib.request
import argparse
p=argparse.ArgumentParser();p.add_argument('--root',required=True);a=p.parse_args()
r=Path(a.root);out={}
for d in sorted(r.iterdir()):
 if not (d/'.git').exists():continue
 paths=subprocess.check_output(['git','ls-tree','-r','--name-only','HEAD'],cwd=d,text=True).splitlines()
 out[d.name]={'commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=d,text=True).strip(),'license_paths':[x for x in paths if re.search('(^|/)(LICENSE|COPYING)',x,re.I)],'tree_files':len(paths)}
 # Existing repository dataset paths availability only, no ESConv/EvoEmo corpus body parse.
 if d.name=='ES-MemEval':
  for f in ['data/evo_emo.json','data/evo_emo_qa.json']:
   if f in paths:out[d.name][f]={'git_blob':subprocess.check_output(['git','rev-parse','HEAD:'+f],cwd=d,text=True).strip(),'bytes':int(subprocess.check_output(['git','cat-file','-s','HEAD:'+f],cwd=d,text=True)),'body_analysis':'sealed-family filter: use existing approved cache only'}
p=r/'ESCA/data/Annotation_full_file.py';tree=ast.parse(p.read_text())
fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='split_conversation')
ns={};exec(compile(ast.Module(body=[fn],type_ignores=[]),str(p),'exec'),ns)
conversation=[{'speaker':'seeker' if i%2==0 else 'supporter','text':f'UNIQUE_TURN_{i:02}'} for i in range(16)]
contexts,counts=ns['split_conversation'](conversation,'state',window_size=4,step=2)
checks=[]
for w,c in enumerate(contexts):
 seen=[int(x) for x in re.findall(r'UNIQUE_TURN_(\d+)',c)]
 for target in [x for x in seen if x%2==0]:checks.append(dict(window=w,target=target,last_visible=max(seen),future_visible=max(seen)>target,future_seekers=sum(x>target and x%2==0 for x in seen)))
out['ESCA']['synthetic_window_test']={'windows':len(contexts),'label_context_pairs':len(checks),'future_exposed':sum(x['future_visible'] for x in checks),'with_later_seeker':sum(x['future_seekers']>0 for x in checks),'details':checks,'real_sealed_dialogue_read':False}
# Schema/scale only for quarantine data. No per-row text or labels consumed by task/runtime.
data=json.loads((r/'ESCA/data/annotated_esconv_with_states.json').read_text());out['ESCA']['download_profile']={'bytes':(r/'ESCA/data/annotated_esconv_with_states.json').stat().st_size,'top_type':type(data).__name__,'records':len(data),'top_keys':sorted(data[0]) if isinstance(data,list) else sorted(data),'content_admission':'quarantine; no per-dialogue fold mapping or training admission'}
data=json.loads((r/'pgmem/prefeval/dataset/implicit_persona.json').read_text());out['pgmem']['download_profile']={'records':len(data),'top_type':type(data).__name__,'first_keys':sorted(data[0]) if isinstance(data,list) else sorted(data)[:10]}
for repo in ['xiaowu0162/longmemeval-cleaned','selfrag/selfrag_train_data']:
 meta=json.load(urllib.request.urlopen('https://huggingface.co/api/datasets/'+repo,timeout=45));key=repo.split('/')[1]
 d=r/key;d.mkdir(exist_ok=True);(d/'HUB_METADATA.json').write_text(json.dumps(meta,indent=2))
 files=[f['rfilename'] for f in meta['siblings']];out[key]={'revision':meta['sha'],'license':meta.get('cardData',{}).get('license'),'files':files}
 for name in files:
  if name=='README.md' or (key=='longmemeval-cleaned' and 'oracle' in name) or (key=='selfrag_train_data' and name.endswith('.jsonl')):
   url=f"https://huggingface.co/datasets/{repo}/resolve/{meta['sha']}/{name}"
   req=urllib.request.Request(url,headers={'Range':'bytes=0-1048575'} if key=='selfrag_train_data' and name!='README.md' else {})
   with urllib.request.urlopen(req,timeout=60) as resp:raw=resp.read(1048576 if key=='selfrag_train_data' and name!='README.md' else 30000000);status=resp.status
   dest=d/(name.replace('/','_')+('.firstMiB' if key=='selfrag_train_data' and name!='README.md' else ''));dest.write_bytes(raw)
   entry={'file':str(dest),'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'http':status}
   if key=='longmemeval-cleaned' and 'oracle' in name:
    a=json.loads(raw);entry.update(records=len(a),fields=sorted(a[0]),question_types=sorted({x['question_type'] for x in a}),usage='external eval quarantine; not training or GSWS input')
   if key=='selfrag_train_data' and name!='README.md':
    lines=raw.splitlines()[:-1];a=[json.loads(x) for x in lines];entry.update(complete_preview_rows=len(a),fields=sorted(a[0]),range_only=True)
   out[key].setdefault('downloads',[]).append(entry)
(r/'PUBLIC_DATA_AUDIT.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
