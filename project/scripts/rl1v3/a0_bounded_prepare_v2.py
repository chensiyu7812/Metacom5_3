"""Bounded-plan supplement: preserve old100 OFF, add multi-prefix resource costs.

No model invocation. New approval must bind this supplement; old plan unchanged.
"""
import argparse
import copy
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.generator.bounded_probe import schedule,PROTOCOL,GPU_UUID,estimate
from metacom_pm.rl1v3.generator.g0e_port import make_port_factory
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once,write_bytes_once


def prepare(joint,preflight,out):
    base=ROOT/'project/outputs/pm_rl1/v3/A0_bounded_cpu_20261118'
    old=json.loads((base/'GPU_PLAN.json').read_text());plan=copy.deepcopy(old)
    plan['amendment_protocol']='pmrl1v3-a0-bounded-supplement-2'
    plan['parent_plan_sha256']=object_sha256(old)
    oldrows=[json.loads(x) for x in (base/'gemma_requests.jsonl').read_text().splitlines()]
    off=[r for r in oldrows if r['condition']=='OFF_reused'];assert len(off)==100
    factory=make_port_factory(root=ROOT)
    offchecks=[]
    for r in off:
        ids=factory.tokenizer.encode_messages(r['messages']);assert list(ids)==r['input_ids']
        offchecks.append(dict(request_id=r['request_id'],token_ids_sha256=object_sha256(ids),input_tokens=len(ids)))
    allrows=[json.loads(x) for x in (joint/'CPU_REQUESTS_ONLY.jsonl').read_text().splitlines()]
    summary=json.loads((joint/'SUMMARY.json').read_text());assert len(allrows)==summary['terminals']==120
    chosen=[]
    for pid in sorted({r['prefix_id'] for r in allrows}):
        rows=[r for r in allrows if r['prefix_id']==pid]
        for condition in ('ME','MS','RS','ALL'):
            if condition=='ALL':
                r=max(rows,key=lambda x:len(x['subset'].split('+')))
                label='ALL' if r['subset']=='RS+MP+ME+MS' else 'ALL_AVAILABLE_MP_UNAVAILABLE'
            else:r=next(x for x in rows if x['subset']==condition);label=condition
            ids=factory.tokenizer.encode_messages(r['messages']);assert list(ids)==r['input_ids']
            chosen.append(dict(request_id=r['request_id'],messages=r['messages'],input_ids=r['input_ids'],
                max_new_tokens=320,context_limit=16384,condition=label,decode=r['decode'],
                prefix_id=pid,subset=r['subset'],owner_id=r['owner_id']))
    assert len(chosen)==32
    gemma=[*off,*chosen];assert len({r['request_id'] for r in gemma})==132
    write_jsonl_once(out/'gemma_requests.jsonl',gemma)
    write_bytes_once(out/'needcard_requests.jsonl',(base/'needcard_requests.jsonl').read_bytes())
    write_bytes_once(out/'CHECKPOINT_PREFLIGHT.json',preflight.read_bytes())
    plan['checkpoint_preflight_file']='CHECKPOINT_PREFLIGHT.json'
    plan['checkpoint_preflight_sha256']=file_sha256(out/'CHECKPOINT_PREFLIGHT.json')
    paths=['project/scripts/rl1v3/a0_bounded_run_v2.py',
        'project/src/metacom_pm/rl1v3/generator/checkpoint_guard.py',
        'project/src/metacom_pm/rl1v3/generator/bounded_probe.py','project/src/metacom_pm/rl1v3/io.py']
    plan['code_sha256']={p:file_sha256(ROOT/p) for p in paths}
    plan['schedule_amendment']=dict(old_primary=104,new_primary=132,
        previous_short_repeat_calls=48,new_short_repeat_calls=20,warmup_calls=2,
        reason='replace four single-prefix examples with 32 multi-prefix ME/MS/RS/ALL conditions; same 154 maximum calls',
        batch1_primary_calls=132,batch4_short_calls=4,batch16_short_calls=16,
        B6e_real_terminal_generation_authorized=False)
    groups=schedule(gemma,[(1,132),(4,4),(16,16)],padded_context_cap=32768)
    g=plan['workloads']['gemma'];g['batches']=[dict(request_ids=[r['request_id'] for r in group],batch=len(group),
        input_lengths=[len(r['input_ids']) for r in group]) for group in groups]
    g['max_calls']=sum(len(group) for group in groups)+g['warmup_calls'];assert g['max_calls']==154
    for name,cfg in plan['workloads'].items():
        cfg['requests_sha256']=file_sha256(out/cfg['requests_file'])
        cfg['execution_identity']='A0-probe-v2:'+object_sha256(dict(model_files=cfg['model_files'],
            packages=cfg['runtime_packages'],runner=plan['code_sha256'],batches=cfg['batches'],
            requests_sha256=cfg['requests_sha256'],checkpoint_preflight_sha256=plan['checkpoint_preflight_sha256'],
            timeouts=[cfg['request_timeout_seconds'],cfg['stage_timeout_seconds']]))
    plan['b_v2_budget_discrepancy']['resolution']='B S3 v3 frozen at 120/360; matched CPU joint binding'
    plan['b6e_joint_binding']=dict(summary_sha256=file_sha256(joint/'SUMMARY.json'),
        requests_sha256=file_sha256(joint/'CPU_REQUESTS_ONLY.jsonl'),selection_sha256=summary['selection_sha256'],
        identity=summary['identity'])
    plan['gpu_authorized']=False;plan['measurements']=[]
    plan['j1']['requests_prepared']=0
    write_json_once(out/'GPU_PLAN.json',plan)
    write_json_once(out/'APPROVAL_TEMPLATE_NOT_AUTHORIZED.json',dict(protocol=PROTOCOL,authorized=False,
        researcher_approval_reference=None,plan_sha256=object_sha256(plan),gpu_uuid=GPU_UUID,workloads=['gemma','needcard'],expires_at=None))
    write_json_once(out/'OFF_REUSE_CHECK.json',dict(rows=offchecks,requests=100,original_payloads_unchanged=True,
        source_gemma_sha256=file_sha256(base/'gemma_requests.jsonl'),original_off_evidence_sha256=file_sha256(base/'OFF_REUSE_CHECK.json'),
        input_ids_retokenized_on_cpu=True,weight_loads=0))
    profiles={}
    for c in sorted({r['condition'] for r in chosen}):
        a=[r for r in chosen if r['condition']==c];sizes=sorted(len(r['input_ids']) for r in a)
        profiles[c]=dict(requests=len(a),owners=sorted({r['owner_id'] for r in a}),
            min_input_tokens=sizes[0],median_input_tokens=sizes[len(sizes)//2],max_input_tokens=sizes[-1],
            complete_input_lengths=sizes,output_reserve=320,
            requests_index=[dict(request_id=r['request_id'],prefix_id=r['prefix_id'],subset=r['subset']) for r in a])
    write_json_once(out/'LENGTH_PROFILES.json',dict(profiles=profiles,prefixes=8,
        full_cpu_subset_inventory=120,gpu_primary_resource_requests=32,no_truncation=True,
        operational_context=16384,native_context=262144))
    write_json_once(out/'COST_STATUS.json',dict(gpu_measured=False,actual_calls=0,
        pilot=estimate([],needcards=20,g_terminals=120,j1_calls=360),
        tiers={label:estimate([],needcards=n,g_terminals=n*16,j1_calls=n*16*3)
            for label,n in [('S=288',288),('M=482',482),('L-realized=748',748)]},
        interpretation='request ceilings, not realized reachable terminal counts; unavailable heads reduce counts',
        invalid_old_L_960_used=False,j1_measurement_separate=True,
        missing=['actual load seconds and peak VRAM','batch1 length-stratified Gemma rates','separate real J1 packs/rates'],
        feasibility='pending authorization and hardware measurements'))
    print(json.dumps(dict(plan_sha256=object_sha256(plan),max_calls={k:v['max_calls'] for k,v in plan['workloads'].items()},profiles={k:{x:v[x] for x in ('requests','min_input_tokens','max_input_tokens')} for k,v in profiles.items()})))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--joint',type=Path,required=True)
    p.add_argument('--preflight',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();prepare(a.joint,a.preflight,a.out)
