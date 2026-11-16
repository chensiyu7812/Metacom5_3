"""Read-only, whitelist-first extraction of existing development outputs.

No model/account/credential imports. Re-running verifies identical derived files.
Human labels are copied unchanged; analyst judgments are authored separately.
"""
from pathlib import Path
import hashlib
import json
import shutil

ROOT = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
BASE = ROOT / 'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1'
OUT = Path(__file__).resolve().parents[1]
POOL = ROOT / 'project/outputs/pm_rl1/completion_20260930_v2/P2/common_pool'

def load(p):
    return json.loads(p.read_text())

def digest(x):
    return hashlib.sha256(json.dumps(x, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()

def file_sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()

def save(rel, x):
    p = OUT / rel
    data = (json.dumps(x, ensure_ascii=False, indent=2) + '\n').encode()
    if p.exists():
        assert p.read_bytes() == data, f'Never overwrite changed artifact: {p}'
    else:
        p.write_bytes(data)

def copy_once(src, dst):
    if dst.exists():
        assert src.read_bytes() == dst.read_bytes()
    else:
        shutil.copyfile(src, dst)

def main():
    protocol = load(OUT / 'selection_protocol.json')
    indices = protocol['content_allowlist_prefix_indices']
    plans = [tuple(p) for p in protocol['plans']]
    bindings = load(BASE / 'reference_preparation_20261016_v1/coordinator/item_bindings.json')
    packet = load(BASE / 'reference_preparation_20261016_v1/materials/packet.json')
    assert set(indices) == {b['prefix_index'] for b in bindings}
    contexts = {b['prefix_index']: b['context_id'] for b in bindings}
    provenance = {}
    def track(p):
        provenance[str(p)] = file_sha(p)
    track(OUT / 'selection_protocol.json')
    for p in [BASE / 'reference_preparation_20261016_v1/coordinator/item_bindings.json',
              BASE / 'reference_preparation_20261016_v1/materials/packet.json']:
        track(p)
    run = Path(load(POOL / 'primary_generation_pointer.json')['run_dir'])
    track(POOL / 'primary_generation_pointer.json')
    track(run / 'jobs_private.json')
    # The job manifest is indexed programmatically. No non-whitelisted content
    # is printed or copied, and only selected raw outputs are opened.
    jobs = { (j['slot']['index'], tuple(j['slot']['counts'])): j
             for j in load(run / 'jobs_private.json')
             if j['slot']['index'] in indices and tuple(j['slot']['counts']) in plans }
    unavailable = { (s['index'], tuple(s['counts'])): s
                    for s in load(POOL / 'slots_private.json')['unavailable']
                    if s['index'] in indices and tuple(s['counts']) in plans }
    track(POOL / 'slots_private.json')
    records = []
    for index in indices:
        ctx = contexts[index]
        current = packet['contexts'][ctx]['current_prefix']
        for counts in plans:
            key = index, counts
            row_id = ctx + '_' + ''.join(map(str, counts))
            if key not in jobs:
                assert key in unavailable, f'Unknown missing slot: {key}'
                records.append(dict(row_id=row_id, context_id=ctx, prefix_index=index,
                    counts=list(counts), status='unavailable', unavailable=unavailable[key]))
                continue
            j = jobs[key]
            slot, request = j['slot'], j['request']
            assert slot['split'] == 'dev'
            assert slot['messages'] == request['messages']
            assert digest(request['messages']) == slot['messages_identity']
            assert digest({k:v for k,v in request.items() if k!='request_id'}) == request['request_id']
            assert request['provenance']['prefix_identity'] == slot['prefix_identity']
            assert request['provenance']['canonical_counts'] == list(counts)
            assert request['messages'][-1]['content'] == current[-1]['text']
            system = request['messages'][0]['content']
            history = json.loads(system.split('<quoted_conversation_context>\n',1)[1].split('\n</quoted_conversation_context>',1)[0])
            assert history == [dict(speaker=t['role'],text=t['text']) for t in current[:-1]]
            resources = json.loads(system.split('<resources>\n',1)[1].split('\n</resources>',1)[0]) if '<resources>' in system else []
            assert len(resources) == sum(counts)
            reqfile = run / (request['request_id']+'.request.json')
            rawfile = run / (request['request_id']+'.raw.json')
            assert load(reqfile) == request
            raw = load(rawfile)
            assert raw['request_id'] == request['request_id']
            assert raw['runtime_identity'] == request['executor_identity']
            assert raw['finish_reason'] == 'natural_stop' and raw['text'].strip()
            assert raw['source_provenance_identity'] == digest(request['provenance'])
            track(reqfile); track(rawfile)
            records.append(dict(row_id=row_id, context_id=ctx, prefix_index=index,
                owner=slot['owner'], split=slot['split'], prefix_identity=slot['prefix_identity'],
                counts=list(counts), status='completed_existing', slot_id=slot['slot_id'],
                request_id=request['request_id'], request_path=str(reqfile), raw_path=str(rawfile),
                request_file_sha256=file_sha(reqfile), raw_file_sha256=file_sha(rawfile),
                reply_identity=digest(raw['text']), reply_text_sha256=hashlib.sha256(raw['text'].encode()).hexdigest(),
                reply=raw['text'], resources=resources, candidate_ids=slot['candidate_ids'],
                resource_tokens=slot['resource_tokens'], input_tokens=raw['input_tokens'],
                output_tokens=raw['output_tokens'], generation_seconds=raw['generation_seconds'],
                peak_allocated_bytes=raw['peak_allocated_bytes'], executor_identity=raw['runtime_identity'],
                renderer_identity=request['renderer_identity'], draw_identity=request['draw_identity']))
    save('materials/selected_existing_records.json',records)
    humanpath = Path('/home/tokkio/PMRL1_researcher_2026-10-19T05-14-10-023Z_5da6d7b6-9aa8-43e5-855a-2eee6e486376.json')
    human = load(humanpath)
    track(humanpath)
    answer_by_id = {r['item_id']:r for r in human['state']['items']}
    packet_by_id = {r['item_id']:r for r in packet['items']}
    annotated = []
    for b in bindings:
        h = answer_by_id[b['item_id']]
        p = packet_by_id[b['item_id']]
        assert h['reply_identity'] == b['reply_identity'] == p['reply_identity'] == digest(p['reply'])
        assert h['evidence_identity'] == b['evidence_identity'] == p['evidence_identity']
        annotated.append(dict(binding=b,original_human_answer=h,english_reply=p['reply'],
            matches_selected_pool=[r['row_id'] for r in records if r.get('reply_identity')==b['reply_identity']
                and r['prefix_index']==b['prefix_index']]))
    save('materials/original_annotation_bindings.json',annotated)
    sourcebase=BASE/'paired_diagnostic_20261019_v1/execution_20261019/sources'
    for ctx in protocol['context_ids']:
        p=sourcebase/(ctx+'_complete.txt');track(p)
        copy_once(p, OUT/'materials'/p.name)
    save('materials/contexts.json',packet['contexts'])
    save('provenance/source_hashes.json',provenance)
    valid=[r for r in records if r['status']=='completed_existing']
    metrics=dict(planned=len(records),existing_completed=len(valid),unavailable=len(records)-len(valid),
        contexts=len(contexts),owners=len({r['owner'] for r in valid}),new_generations=0,new_scores=0,
        new_human_judgments=0,formal_eligibility_labels=0,
        selected_files_mechanically_bound=True,
        exact_same_as_OFF=sum(r['reply']==next(x['reply'] for x in valid if x['context_id']==r['context_id'] and sum(x['counts'])==0)
            for r in valid if sum(r['counts'])>0),
        original_human_items=8,independent_human_raters=1,
        annotation_matches_selected_pool=sum(bool(x['matches_selected_pool']) for x in annotated))
    save('data_quality_receipt.json',metrics)
    print(json.dumps(metrics,ensure_ascii=False))

if __name__=='__main__':
    main()
