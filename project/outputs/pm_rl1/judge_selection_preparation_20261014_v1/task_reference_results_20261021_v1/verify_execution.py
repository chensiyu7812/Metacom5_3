"""Read-only verification of input/output/ledger identity after stage close."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
P=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'project/src'))
from metacom_pm.rl1 import relation_reference as rr, task_reference as tr
spec=importlib.util.spec_from_file_location('task_entry',R/'project/scripts/rl1/116_run_task_reference.py')
entry=importlib.util.module_from_spec(spec);spec.loader.exec_module(entry)
pr,items,refs,cards,prompt,payloads,runtime_items=entry.load()
root=Path(pr['run_dir']);p=entry.engine()
assert (root/'CLOSED.json').exists() or (root/'STOP.json').exists()
starts,results=p.replay(root,pr)
assert len(starts)<=32 and tr.historical_guard(pr,P.parent)+len(starts)<=285
wire_by={};hashes={};fingerprints=set();known=0
for s in pr['schedule']:
    sid=s['slot_id']
    if sid not in starts:continue
    request=rr.read(root/(sid+'.request.json'))
    expected=payloads[s['material_id']+'__'+s['arm']]
    assert request['messages']==expected['messages'] and request['schema']==expected['schema']
    assert request['wire_body']['messages']==request['messages']
    assert request['input_screen']['client_truncation'] is False
    wire_by[s['material_id'],s['arm'],s['repetition']]=rr.digest(request['wire_body'])
    assert starts[sid]['request_identity']==rr.digest(dict(protocol=pr['identity'],slot=sid,messages=request['messages'],schema=request['schema']))
    if sid not in results:continue
    rawpath=root/(sid+'.response.json')
    if not rawpath.exists():continue
    raw=rr.read(rawpath);ev=p.evaluate(items[s['material_id']],'joint',raw,pr['identity'],sid)
    old=results[sid]['evaluation']
    for k in ('technical_valid','model_unknown','q','m','U','outer_adaptation'):
        assert ev.get(k)==old.get(k), (s['position'],k)
    hashes[sid]={'raw_response_sha256':rr.sha(rawpath),'final_sha256':hashlib.sha256(raw['choices'][0]['message']['content'].encode()).hexdigest()}
    fingerprints.add(raw.get('system_fingerprint'));known+=1
repeats=[]
for (key,arm,n),sha in wire_by.items():
    if n==2:
        assert wire_by[key,arm,1]==sha
        repeats.append(dict(material_id=key,arm=arm,identical_wire_payload=True,independent_slot_ids=True))
lines=Path(pr['financial_baseline']['ledger_path']).read_bytes().splitlines(keepends=True)
ids={s['slot_id'] for s in pr['schedule']}
cut=next((i for i,l in enumerate(lines) if json.loads(l).get('reservation_id') in ids),len(lines))
assert hashlib.sha256(b''.join(lines[:cut])).hexdigest()==pr['financial_baseline']['ledger_sha256']
events=[json.loads(l) for l in lines[cut:]]
assert all(e.get('reservation_id') in ids for e in events)
out=dict(status='VERIFIED',protocol_identity=pr['identity'],baseline=253,started=len(starts),cumulative=253+len(starts),
    immutable_files_verified=len(pr['immutable_files']),old_started_records_preserved=len(pr['historical_started_hashes']),
    old_stops_preserved=len(pr['old_stop_hashes']),reparsed_responses=known,raw_final_hashes=hashes,
    repeat_payload_identity= repeats,service_fingerprints=sorted(fingerprints),
    historical_ledger_prefix_preserved=True,new_ledger_events=len(events),
    management_requests=len(list((root/'management').glob('*.started.json'))),
    original_contract_sha256=rr.sha(R/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'),
    diagnostic_scores_reward_eligible=False,new_generations=0,natural_updates=0)
rr.save_new(P/'EXECUTION_VERIFICATION.json',out)
print(json.dumps({k:v for k,v in out.items() if k not in ('raw_final_hashes','repeat_payload_identity')},ensure_ascii=False,indent=2))
