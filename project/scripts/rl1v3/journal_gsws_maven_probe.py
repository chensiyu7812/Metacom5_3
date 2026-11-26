#!/usr/bin/env python3
"""Public official file download and event-label profile; no training or text export."""
from pathlib import Path
import requests,html,re,json,hashlib,collections
import argparse
p=argparse.ArgumentParser();p.add_argument('--output-dir',required=True);a=p.parse_args()
r=Path(a.output_dir);r.mkdir(parents=True,exist_ok=True)
s=requests.Session();url='https://drive.google.com/uc?export=download&id=1NUOXtSgU6wJfeA4SIxsRboMYRpVT8OPN'
x=s.get(url,stream=True,timeout=60)
if 'text/html' in x.headers.get('content-type',''):
 txt=x.text
 form=re.search(r'<form[^>]+action="([^"]+)"[^>]*>(.*?)</form>',txt,re.S)
 if not form:raise RuntimeError('public Drive download form unavailable')
 params={a:b for a,b in re.findall(r'name="([^"]+)"[^>]*value="([^"]*)"',form.group(2))}
 x=s.get(html.unescape(form.group(1)),params=params,stream=True,timeout=60)
x.raise_for_status();assert 'text/html' not in x.headers.get('content-type','')
p=r/'train.download.jsonl'
with p.open('xb') as f:
 for block in x.iter_content(1024*1024):f.write(block)
labels=collections.Counter();docs=events=mentions=0;keys=None
for line in p.open():
 d=json.loads(line);docs+=1;keys=sorted(d) if keys is None else keys
 for e in d.get('events',[]):
  events+=1
  for m in e.get('mention',e.get('mentions',[])):
   mentions+=1;labels[m.get('factuality','MISSING')]+=1
report=dict(bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest(),documents=docs,events=events,mentions=mentions,labels=dict(labels),fields=keys,license='not established by official repository or Drive metadata',source_id='1NUOXtSgU6wJfeA4SIxsRboMYRpVT8OPN',training_started=False)
(r/'DOWNLOAD_PROFILE.json').write_text(json.dumps(report,indent=2));print(json.dumps(report))
