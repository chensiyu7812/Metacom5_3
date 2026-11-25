"""Prepare frozen M/RS real-generator inputs using pinned native tokenizer only."""
import argparse
import json
from pathlib import Path
from collections import Counter, defaultdict
from metacom_pm.rl1v3.io import object_sha256, file_sha256
from metacom_pm.rl1v3.bank.v0_port import load_bank
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
from metacom_pm.rl1v3.generator.g0e import load_binding, SYSTEM
from metacom_pm.rl1v3.render.request_packet import NOTES as OLD_NOTES
from metacom_pm.rl1v3.journal.renderer import packet
import metacom_pm.rl1v3.journal.renderer as renderer
import html


def write(path, value, lines=False):
    with path.open('x') as f:
        if lines:
            for row in value: f.write(json.dumps(row,ensure_ascii=False,sort_keys=True)+'\n')
        else: json.dump(value,f,ensure_ascii=False,sort_keys=True,indent=2);f.write('\n')


def prepare(root, memory, rs, output):
    root, output=Path(root),Path(output);output.mkdir(parents=True,exist_ok=False)
    binding=load_binding(root,backend='hf',verify_local_files=True)
    _,cfg=load_bank(root)
    tokenizer=PromptTokenizer(NativeTokenizer(cfg['tokenizer_model'],root/cfg['asset_manifest']))
    impl=file_sha256(renderer.__file__)
    records=[];failures=[];by_payload={};contrasts=[];source_hashes={}
    for domain, path in [('memory',memory),('rs',rs)]:
        path=Path(path);source_hashes[str(path)]=file_sha256(path)
        materials=[json.loads(x) for x in path.read_text().splitlines()]
        for material in materials:
            key=domain+':'+material['task_id']+':'+material['arm']
            try:
                p,views=packet(material,tokenizer,baseline_sha256=binding.sha256,implementation_sha256=impl)
            except ValueError as exc:
                if not str(exc).startswith('capacity:'):
                    raise  # implementation failures must not masquerade as scientific unreachability
                failures.append(dict(logical_id=key,domain=domain,task_id=material['task_id'],arm=material['arm'],status='unreachable',reason=str(exc)))
                continue
            # Compare exact legacy notes under the same task input. No legacy call.
            old=[dict(role='system',content=SYSTEM)]
            if views:
                blocks=['<resource head="'+v.head+'">'+html.escape(v.reading_text)+'</resource>' for v in sorted(views,key=lambda v:('RS','MP','ME','MS').index(v.head))]
                old.append(dict(role='user',content=OLD_NOTES+'<Notes>\n'+'\n'.join(blocks)+'\n</Notes>'))
            old.extend(p.payload()['messages'][-len(material.get('visible_prefix',material.get('runtime',{}))['turns']):])
            old_ids=tokenizer.encode_messages(old)
            contrasts.append(dict(logical_id=key,old_input_tokens=len(old_ids),journal_input_tokens=len(p.input_ids),
                exact_off_equal=old==p.payload()['messages'] if not views else None,
                old_payload_sha256=object_sha256(dict(messages=old,input_ids=list(old_ids),decode=binding.spec['decode'])),
                journal_payload_sha256=p.payload_sha256))
            record=dict(logical_id=key,domain=domain,task_id=material['task_id'],arm=material['arm'],
                request_id='jreq:'+p.payload_sha256,model_input=p.payload(),payload_sha256=p.payload_sha256,
                input_ids_sha256=object_sha256(list(p.input_ids)),input_tokens=len(p.input_ids),
                renderer_id=p.renderer_id,baseline_sha256=binding.sha256,source_material_sha256=object_sha256(material),
                status='frozen_candidate_awaiting_run_authorization',evaluation_status='pending',model_called=False)
            records.append(record)
            by_payload.setdefault(record['request_id'], record)
    # Each arm's first two task IDs by a fixed hash ordering. No output-based selection.
    groups=defaultdict(list)
    for r in records:groups[(r['domain'],r['arm'])].append(r)
    smoke_ids=[]
    for group,rows in sorted(groups.items()):
        for r in sorted(rows,key=lambda r:r['task_id'])[:2]:
            if r['request_id'] not in smoke_ids:smoke_ids.append(r['request_id'])
    all_unique=list(by_payload.values())
    smoke=[by_payload[k] for k in smoke_ids]
    for filename,rows in [('requests_logical.private.jsonl',records),('requests_unique.private.jsonl',all_unique),
                          ('smoke_requests.private.jsonl',smoke),('renderer_contrast.jsonl',contrasts),('unreachable.jsonl',failures)]:
        write(output/filename,rows,True)
    write(output/'G0E_BASELINE.json',dict(spec=binding.spec,identity=binding.identity,binding_sha256=binding.sha256))
    plan=dict(protocol='pmrl1-j-generation-candidate-v1',authorized=False,baseline_sha256=binding.sha256,
        renderer_id=records[0]['renderer_id'],renderer_implementation_sha256=impl,source_files_sha256=source_hashes,
        logical_requests=len(records)+len(failures),reachable_logical_requests=len(records),
        unique_calls=len(all_unique),smoke_calls=len(smoke),smoke_included_in_total=True,
        arm_counts=dict(Counter(r['domain']+':'+r['arm'] for r in records)),unreachable=len(failures),
        capacity=dict(runtime=16384,native=262144,output=320,max_input=max(r['input_tokens'] for r in records),no_truncation=True),
        reuse_rule='exact same journal renderer, G0e model/decode and payload bytes only; logical denominators retained',
        model_calls=0,model_loads=0,paid_calls=0,
        request_files={n:file_sha256(output/n) for n in ('requests_logical.private.jsonl','requests_unique.private.jsonl','smoke_requests.private.jsonl')})
    write(output/'REQUEST_MANIFEST.json',plan)
    print(json.dumps(plan,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--g-root',required=True);p.add_argument('--memory',required=True);p.add_argument('--rs',required=True);p.add_argument('--output',required=True)
    a=p.parse_args();prepare(a.g_root,a.memory,a.rs,a.output)
