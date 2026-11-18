#!/usr/bin/env python3
"""Prepare exactly 16 existing MS/OFF inputs and eight pending DP slots on CPU."""
from __future__ import annotations
import argparse
import importlib.util
import importlib.metadata
import json
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.compile import ms_pp1 as M
from metacom_pm.rl1v3.bank.v0_port import load_bank
from metacom_pm.rl1v3.retrieve.v0 import search
from metacom_pm.rl1v3.io import object_sha256, file_sha256, sha256_bytes, write_json_once, write_jsonl_once

A18='0a91ff3329dc0d091fbb9e234035638efb45146c'
B17='3dafb2aa6e861846aa77a96d99a02c66e4fade7d'
A12='8ba20d21da4bdcbb552946241563bd41dbe46c6c'
A13='ea2f5bde04caba4590b26c80a572d66caa4a2d08'
V3='project/outputs/pm_rl1/v3/'
QUAL=V3+'qualification_e1_20261118/cpu_v3/'


def build(out):
    if out.exists(): raise FileExistsError('new CPU export directory required')
    inputs=[]
    def pin(commit,path,lines=False):
        data=subprocess.check_output(['git','-C',str(ROOT),'show',commit+':'+path])
        inputs.append(dict(commit=commit,path=path,sha256=sha256_bytes(data)))
        return [json.loads(x) for x in data.splitlines()] if lines else json.loads(data)
    def local(path):
        data=(ROOT/path).read_bytes()
        expected=subprocess.check_output(['git','-C',str(ROOT),'show',A18+':'+path])
        if data!=expected: raise ValueError('A18 evidence changed: '+path)
        inputs.append(dict(commit=A18,path=path,sha256=sha256_bytes(data)))
        return json.loads(data)
    binds=pin(A18,QUAL+'BINDINGS.jsonl',True)
    jobs=pin(A13,V3+'resource_architecture_review_20261118/cpu/PROPOSED_JOBS.json')['jobs']
    jobs={r['existing_request_id']:r for r in jobs}
    elig=pin(B17,V3+'V32_WSB_P0P2/p2/ELIGIBILITY_54.json')
    elig={r['existing_request_id']:r for r in elig['rows'] if r.get('joint_eligibility')=='ELIGIBLE' and r.get('subset') in ('OFF','MS')}
    if len(elig)!=16: raise ValueError('B eligible 16 changed')
    requests=pin(A12,V3+'G0e_binding_20261118/CPU_REQUESTS_ONLY.jsonl',True)
    requests={r['request_id']:r for r in requests if r['request_id'] in elig}
    keys=pin(A12,V3+'G0e_binding_20261118/KEY_BINDINGS.jsonl',True)
    keys={r['request_sha256']:r for r in keys if r['request_sha256'] in elig}
    protocol=pin(B17,V3+'V32_WSB_RQ1Q/protocol/PROTOCOL_CANDIDATE.json')
    gc=pin(A12,'project/configs/rl1v3/G0e.json')
    baseline=local(QUAL+'GENERATOR_BASELINE.json')
    spec=baseline['spec']; identity=dict(baseline['identity'])
    identity.pop('decode')
    identity['renderer_id']=next(iter(keys.values()))['new_key']['renderer_id']
    baseline=dict(spec=spec,identity=identity,source_commit=A12,
        renderer_policy='preserve original G0e Notes renderer and all 16 payload bytes; PR18 direct renderer remains separate',
        same_renderer_for_future_DP=True,model_loaded=False)
    modspec=importlib.util.spec_from_file_location('e1_tokenizer_only',ROOT/'project/scripts/rl1v3/prepare_e1_qualification.py')
    mod=importlib.util.module_from_spec(modspec);modspec.loader.exec_module(mod)
    counter=mod.NativeCounter(Path(gc['model_path']),gc)
    bank,_=load_bank(ROOT); registry=bank.registry
    sources=[]; pools=[]; audits=[]; newbindings=[]; rows=[]; pending=[]
    # Original B order, interleave OFF then RET-MS. Never reorder by outcomes.
    for b in binds:
        p=registry.prefix(b['owner_id'],b['session_id'],b['cut_turn'])
        prefix=local(QUAL+b['prefix_path']); snap=local(QUAL+b['snapshot_past'])
        if snap!=local(QUAL+b['snapshot_future']): raise ValueError('dual horizon')
        if p.runtime_sha256!=b['prefix_context_sha256']:raise ValueError('prefix binding')
        nb={k:b[k] for k in ('owner_id','prefix_id','session_id','cut_turn','cutoff_rank','timestamp',
             'prefix_context_sha256','snapshot_sha','source_frontier_sha256')}
        nb.update(prefix_file=QUAL+b['prefix_path'],snapshot_past_file=QUAL+b['snapshot_past'],snapshot_future_file=QUAL+b['snapshot_future'])
        newbindings.append(nb)
        armrows={r['subset']:r for r in requests.values() if r['prefix_id']==b['prefix_id']}
        if set(armrows)!= {'OFF','MS'}:raise ValueError('fixed pair missing')
        ranked=search(bank,'MS',p)
        rid=keys[armrows['MS']['request_id']]['new_key']['acquired'][0][0]
        if ranked.ranked[0].record_id!=rid:raise ValueError('original lexical-v0 winner changed')
        bankrecord=bank.by_id[rid]; source=registry.entry(p.owner_id,bankrecord.source_refs[0].session_id).source
        raw=next(v['record'] for v in snap['views'] if v['record']['kind']=='MS_RAW' and v['record']['session_id']==source.session_id)
        if raw['text']!='\n'.join(t.role+': '+t.text for t in source.turns):raise ValueError('source text')
        reading=keys[armrows['MS']['request_id']]['new_trace']['readings'][0]
        sourcebinding=dict(owner_id=p.owner_id,prefix_id=p.prefix_id,snapshot_sha=snap['snapshot_sha'],
            source_frontier_sha256=snap['source_frontier_sha256'],asof_record_id=raw['record_id'],
            bank_record_id=rid,source_session_id=source.session_id,source_rank=source.chronological_rank,
            family_id=source.family_id,ancestor_family_ids=list(source.ancestor_family_ids),
            known_at=raw['known_at'],ready_at=raw['ready_at'],reported_at=raw['reported_at'],
            source_refs=raw['source_refs'],reading_text=reading['reading_text'],
            reading_sha256=object_sha256(reading),selection='legacy lexical-v0 Top-1; not Direct Provision',
            query_identity=ranked.query_identity,rank=1,score=ranked.ranked[0].score,
            legal_candidates=len(ranked.ranked),license=source.license,
            semantic_review='quoted RAW; applicability/continuity human review pending',
            current_request_suitability=None,generator_correct_use=None)
        sources.append(sourcebinding)
        raws=sorted([v['record'] for v in snap['views'] if v['record']['kind']=='MS_RAW'],key=lambda r:r['reported_at']['session_rank'])
        pool=dict(owner_id=p.owner_id,prefix_id=p.prefix_id,prefix=prefix,
            snapshot_sha=snap['snapshot_sha'],instructions='Read this current prefix and the chronological lawful RAW only. No replies, scores, or arm selections are provided. Freeze the independent QH background first. Select a complete RAW if suitable; otherwise record unavailable without replacing the prefix.',
            candidates=[{k:r[k] for k in ('record_id','owner_id','session_id','family_id','reported_at','known_at','ready_at','text','source_refs')} for r in raws],
            reviewer=None,review_status='pending_human_review')
        pools.append(pool);pending.append(M.dp_slot(nb,identity,object_sha256(pool)))
        # Auditing sample is fixed first / RET / latest / current; not a DP selection.
        sample={r['record_id']:r for r in (raws[0],raw,raws[-1])}
        audits.append(dict(owner_id=p.owner_id,prefix_id=p.prefix_id,
            sample_rule='first historical, existing RET, latest historical (deduplicate), current lawful prefix',
            historical=[dict(session_id=r['session_id'],rank=r['reported_at']['session_rank'],family_id=r['family_id'],
                record_id=r['record_id'],text=r['text'],source_refs=r['source_refs']) for r in sorted(sample.values(),key=lambda r:r['reported_at']['session_rank'])],
            current_prefix=prefix,mechanical_owner_time='pass',semantic_consistency='pending_human_review',
            identity_basis='dataset owner grouping, not proof these are one natural human',
            B_independent_review='pending'))
        for arm in ('OFF','MS'):
            old=armrows[arm];key=keys[old['request_id']];trace=key['new_trace']
            expected=M.audit_projection(prefix,trace['readings'][0] if arm=='MS' else None,spec['system_prompt'])
            if old['messages']!=expected:raise ValueError('whitelist projection')
            ids=counter.ids(old['messages'])
            if ids!=old['input_ids']:raise ValueError('native input IDs differ')
            payload=dict(messages=old['messages'],input_ids=ids,decode=old['decode'])
            row=dict(protocol=M.PROTOCOL,condition='RET-MS' if arm=='MS' else 'OFF',
                owner_id=p.owner_id,prefix_id=p.prefix_id,prefix_context_sha256=p.runtime_sha256,
                snapshot_sha=b['snapshot_sha'],source_frontier_sha256=b['source_frontier_sha256'],
                legacy_request_id=old['request_id'],terminal_key_sha256=old['terminal_key_sha256'],
                payload_sha256=object_sha256(payload),input_ids_sha256=object_sha256(ids),
                source_binding_sha256=object_sha256(sourcebinding),**identity)
            row.update(request_id='PP1-admission:'+object_sha256(M.admission_identity(row)),
                model_input=payload,input_tokens=len(ids),order=len(rows)+1,
                plan_job_id=jobs[old['request_id']]['plan_job_id'],old_joint_eligibility=elig[old['request_id']]['joint_eligibility'],
                token_provenance='fresh native CPU tokenization; exact equality to preserved old input checked',
                execution_authorized=False,research_qualified=False,result=None,reward=None)
            rows.append(row)
    write_json_once(out/'BASELINE.json',baseline)
    write_json_once(out/'PINNED_A_BINDINGS.json',dict(a_head=A18,rows=newbindings))
    write_json_once(out/'LEGACY_INPUTS_16.json',dict(source_commit=A12,requests=list(requests.values()),bindings=list(keys.values())))
    write_json_once(out/'MS_SOURCE_BINDINGS.json',dict(rows=sources))
    write_json_once(out/'DP_REVIEW_POOLS.json',dict(status='unranked_source_package_not_QH_background',rows=pools))
    write_json_once(out/'DP_PENDING.json',dict(rows=pending))
    write_json_once(out/'OWNER_AUDIT_SAMPLES.json',dict(rows=audits))
    write_jsonl_once(out/'REQUESTS_16.jsonl',rows)
    write_json_once(out/'B_PROTOCOL_CANDIDATE.json',protocol)
    # Conservative storage estimate: all layers cache all tokens, no sliding eviction or K/V sharing assumed.
    modelcfg=json.loads((Path(gc['model_path'])/'config.json').read_text());tc=modelcfg['text_config']
    maxseq=max(r['input_tokens'] for r in rows)+320
    kv_elements_per_token=2*sum((tc['num_global_key_value_heads']*tc['global_head_dim'] if t=='full_attention'
        else tc['num_key_value_heads']*tc['head_dim']) for t in tc['layer_types'])
    weight_bytes=gc['common']['model']['files']['model.safetensors']['bytes']
    plan=dict(protocol=M.PROTOCOL,status='PREPARED_NOT_AUTHORIZED',authorized=False,
        purpose='B PP1 procedure pilot only; not an MS effect test or formal G0 promotion',
        A_head=A18,B_head=B17,B_protocol_sha256=object_sha256(protocol),
        ordered_request_ids=[r['request_id'] for r in rows],requests_file='REQUESTS_16.jsonl',
        requests_file_sha256=file_sha256(out/'REQUESTS_16.jsonl'),baseline_sha256=object_sha256(baseline),
        max_generator_calls=16,warmup_generator_calls=0,max_model_loads=1,max_judge_calls=0,
        automatic_retry=False,dp_calls=0,paid_api_calls=0,
        runtime=dict(spec['runtime'],model_path=gc['model_path'],max_new_tokens=320,request_timeout_seconds=300,
            load_timeout_seconds=600,total_wall_limit_seconds=1200,minimum_initial_free_mib=40960,
            minimum_running_free_mib=4096,exclusive_gpu=True,no_device_fallback=True,
            load='AutoModelForMultimodalLM.from_pretrained(local_files_only=True, trust_remote_code=False, ignore_mismatched_sizes=False, output_loading_info=True, dtype=bfloat16, attn_implementation=sdpa); validate shapes/aliases/loading_info; then cuda:0 and eval',
            weight_verification='fresh SHA256 of every pinned file only after GPU authorization and before load',
            load_attestation='A12 checkpoint guard and admission evidence must be refreshed on authorized integration HEAD'),
        memory_estimate=dict(measured=False,checkpoint_bytes=weight_bytes,checkpoint_gib=weight_bytes/2**30,
            max_input_plus_output_tokens=maxseq,kv_upper_bytes=kv_elements_per_token*2*maxseq,
            kv_formula='batch=1 * (prompt+320) * 2(K,V) * BF16 2 bytes * sum(layer kv_heads * head_dim); no eviction/sharing discount',
            estimated_peak_gib_range=[26,36],range_basis='checkpoint storage + conservative KV + 3-12 GiB unmeasured activation/loading/allocator allowance; not a hardware measurement',
            admission_floor_gib=40,headroom_guard_gib=4),
        time_estimate=dict(measured=False,B_draft_load_minutes=[3,5],B_draft_generation_minutes=5,
            planning_total_minutes=[8,20],hard_total_minutes=20,
            caution='B draft estimate is unmeasured; 16*300s + load exceeds 20min. Global deadline takes precedence; pending suffix is retained without automatic resume.',
            prerequisite='authorized A0 measured load/throughput receipt; this PP1 does not add A0/warmup calls'),
        stop_conditions=['load failure or OOM','identity/token/source/frontier mismatch','any unexpected visible field',
            'third length-truncated reply (>2/16); retain all three without regeneration','request timeout or empty output',
            'total 1200s deadline','device contention or free memory guard','request outside manifest, duplicate start, unresolved prior attempt',
            'missing authorization, B receipt, integration acceptance, screening/QH/procedure approval'],
        result_policy='new PP1 write-once log namespace; never read old reward/result caches; do not filter or regenerate based on content; merge into analysis only under B approved pre-registered rule',
        requirements=dict(B_review='pending',integration_owner_acceptance='pending',researcher_PP1_approval='pending',
            A0_measurement='pending',screening_8='pending',QH_background_8='pending',two_reviewers='pending',
            DP_selection='not required for OFF/RET PP1; required before a DP comparison',MP_ME_RS_SUM='not prerequisites'))
    write_json_once(out/'PP1_PLAN.json',plan)
    write_json_once(out/'PREPARE_SUMMARY.json',dict(requests=16,prefixes=8,dp_pending=8,
        input_tokens_range=[min(r['input_tokens'] for r in rows),max(r['input_tokens'] for r in rows)],
        all_capacity_fit=all(r['input_tokens']+320<=16384 for r in rows),historical_sessions=sum(len(p['candidates']) for p in pools),
        legacy_payloads_preserved=16,tokenizer_runtime={n:importlib.metadata.version(n) for n in ('transformers','tokenizers')},
        plan_sha256=object_sha256(plan),model_calls=0,GPU_used=False,original_five_human_labels='pending_human_review unchanged'))
    write_json_once(out/'INPUT_PINS.json',dict(inputs=inputs,code_sha256={str(p.relative_to(ROOT)):file_sha256(p) for p in
        [Path(__file__),Path(M.__file__),ROOT/'project/scripts/rl1v3/prepare_e1_qualification.py']}))
    write_json_once(out/'MANIFEST.json',dict(files={str(p.relative_to(out)):file_sha256(p) for p in sorted(out.rglob('*')) if p.is_file()}))
    print(json.dumps(M.check_bundle(out,ROOT),ensure_ascii=False))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--out',type=Path,required=True)
    build(ap.parse_args().out)
