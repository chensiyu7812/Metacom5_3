#!/usr/bin/env python3
"""Populate the original eight frozen sheets; preserve selection and blind key.

No model/Judge call, semantic labels, new sampling, or message sending.
"""
from pathlib import Path
import argparse,json,shutil
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once

p=argparse.ArgumentParser()
p.add_argument('--frozen',required=True)
p.add_argument('--collection',required=True)
p.add_argument('--out',required=True)
a=p.parse_args();frozen=Path(a.frozen);collection=Path(a.collection);out=Path(a.out)
out.mkdir(parents=True,exist_ok=False,mode=0o700)
read=lambda p:json.loads(p.read_text())
rows=lambda p:[json.loads(s) for s in p.read_text().splitlines() if s.strip()]
manifest=read(frozen/'MANIFEST_PUBLIC.json')
for name,h in manifest['files_sha256'].items():
    if file_sha256(frozen/name)!=h:raise ValueError('original frozen blind packet changed')
key={r['case_id']:r for r in read(frozen/'BLIND_KEY_PRIVATE.json')['selection']}
actual={(r['public']['task_id'],r['public']['method']):r for r in rows(collection/'PATHS_PRIVATE.jsonl')}
templates=rows(frozen/'BLIND_REVIEW_TEMPLATES_PRIVATE.jsonl');outputs=[];bound=[]
for row in templates:
    k=key[row['case_id']];path=actual.get((k['task_id'],k['arm']))
    if path is None:raise ValueError('original selected task missing from completed collection; no replacement')
    output=path['actual_output'];row=dict(row)
    row['technical_status']=('not_run' if output is None else 'eos' if path['public']['technical_status']=='terminal_eos' else path['public']['technical_status'])
    row['actual_output_sha256']=None if output is None else object_sha256(output)
    row['output_text']=None if output is None else output['text']
    outputs.append(dict(case_id=row['case_id'],actual_output=output,source_packet_sha256=row['source_packet_sha256']))
    bound.append(row)
write_jsonl_once(out/'BLIND_REVIEW_PENDING_PRIVATE.jsonl',bound)
write_jsonl_once(out/'ACTUAL_OUTPUTS_PRIVATE.jsonl',outputs)
for path in frozen.glob('SOURCE_PACKET_*.private.json'):
    shutil.copy2(path,out/path.name)
write_json_once(out/'BINDING_PUBLIC.json',dict(protocol='ge2-original-blind-eight-actual-binding-v1',
    frozen_manifest_sha256=file_sha256(frozen/'MANIFEST_PUBLIC.json'),
    selection_key_sha256=file_sha256(frozen/'BLIND_KEY_PRIVATE.json'),
    collection_manifest_sha256=file_sha256(collection/'COLLECTION_MANIFEST_PRIVATE.json'),
    selected_outputs=len(bound),returned_outputs=sum(r['actual_output'] is not None for r in outputs),
    independent_human_reviews=0,assistant_reviews=0,old_five_human_items='pending_unchanged',
    labels_or_delivery_sidecars_exported=False,new_sampling=False,formal_reward=None))
write_json_once(out/'MANIFEST_PRIVATE.json',dict(files_sha256={p.name:file_sha256(p) for p in out.iterdir() if p.is_file()},
    script_sha256=file_sha256(__file__),formal_reward=None))
print(json.dumps(dict(outputs=len(bound),new_labels=0,key_copied=False)))
