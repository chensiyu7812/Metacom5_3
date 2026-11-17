"""Reuse fixed requests and build bounded CPU-only GPU proposal. No weights loaded."""
import argparse
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from metacom_pm.rl1v3.generator.g0e_port import make_port_factory,PromptTokenizer
from metacom_pm.rl1v3.generator.bounded_probe import PROTOCOL,GPU_UUID,schedule,estimate


def prepare(out,examples):
    import yaml
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    from metacom_pm.rl1v3.needs import protocol_v2 as W
    from metacom_pm.rl1v3.needs.sources import a1_context
    from metacom_pm.rl1v3.bank import rs_v0_catalog as AC
    f=make_port_factory(root=ROOT);cfg=json.loads((ROOT/'project/configs/rl1v3/G0e.json').read_text())
    base=ROOT/'project/outputs/pm_rl1/v3'
    old=base/'A0/repair_1/OFF_REQUESTS.jsonl';off=[json.loads(x) for x in old.read_text().splitlines()]
    probe=json.loads((base/'A0/repair_1/TOKENIZER_PROBE.json').read_text())
    prior_tokens={r['request_sha256']:r for r in probe['rows']}
    gemma=[];checks=[]
    for r in off:
        req=r['request'];assert object_sha256(req)==r['request_sha256']
        ids=f.tokenizer.encode_messages(req['messages'])
        assert len(ids)+320<=f.binding.spec['runtime']['max_model_len']
        assert len(ids)==prior_tokens[r['request_sha256']]['input_tokens']
        assert object_sha256(ids)==prior_tokens[r['request_sha256']]['input_ids_sha256']
        gemma.append(dict(request_id=r['request_sha256'],messages=req['messages'],input_ids=ids,
            max_new_tokens=320,context_limit=16384,condition='OFF_reused',decode=f.binding.spec['decode']))
        checks.append(dict(request_sha256=r['request_sha256'],input_tokens=len(ids),token_ids_sha256=object_sha256(ids)))
    # Existing 100 payloads, no resampling, no reply/evaluation fields.
    assert len(gemma)==100
    for r in [json.loads(x) for x in examples.read_text().splitlines()]:
        p=r['model_input'];gemma.append(dict(request_id=r['request_sha256'],messages=p['messages'],input_ids=p['input_ids'],
            max_new_tokens=320,context_limit=16384,condition=r['case'],decode=p['decode']))
    wc=yaml.safe_load((ROOT/'project/configs/rl1v3/B1_needcard_v2.yaml').read_text())
    native=NativeTokenizer(wc['writer_model']['path'],ROOT/'project'/wc['asset_manifest']);tok=PromptTokenizer(native)
    catalog=AC.load(ROOT/wc['rs_catalog_path'],root=ROOT,bank=f.bank)
    census={r['prefix_id']:r for r in (json.loads(x) for x in (ROOT/'project'/wc['census']).read_text().splitlines())}
    pilots=[json.loads(x) for x in (base/'B1/needcard_cpu_preflight_v2_a1b_catalog/pilot_inputs.jsonl').read_text().splitlines()]
    ordered=sorted(pilots,key=lambda r:(r['input_tokens'],r['prefix_id']))
    chosen=[ordered[i] for i in (0,len(ordered)//2,len(ordered)-1)];qwen=[]
    qpath=Path(wc['writer_model']['path'])
    qmodel=json.loads((qpath/'config.json').read_text())
    qtok=json.loads((qpath/'tokenizer_config.json').read_text())
    qc=dict(eos_token_id=qmodel['text_config']['eos_token_id'],
            pad_token_id=native.tokenizer.convert_tokens_to_ids(qtok['pad_token']))
    assert isinstance(qc['pad_token_id'],int)
    for r in chosen:
        ctx=a1_context(f.registry,census[r['prefix_id']])
        pack=W.build_pack(ctx,catalog,registry=f.registry,count_prompt=lambda m:len(tok.encode_messages(m)),
            native_context_tokens=tok.native_context_tokens,operational_max_input_tokens=wc['operational_max_input_tokens'],tokenizer_identity=tok.identity)
        assert pack['pack_sha256']==r['pack_sha256'] and pack['input_tokens']==r['input_tokens'] and pack['status']=='ready'
        msgs=W.messages(pack);ids=tok.encode_messages(msgs)
        qwen.append(dict(request_id=pack['pack_sha256'],messages=msgs,input_ids=ids,max_new_tokens=800,
            context_limit=32768,condition='real_needcard_input_timing_only',decode=dict(do_sample=False,num_beams=1,
                seed=0,max_new_tokens=800,enable_thinking=False,eos_token_id=qc['eos_token_id'],pad_token_id=qc['pad_token_id'])))
    env=cfg['environments'];vr=Path('/opt/tokkio-data0/tokkio_envs/paper1-qwen35-vllm-py312/lib/python3.12/site-packages/vllm/model_executor/models/registry.py')
    hf=Path('/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/lib/python3.12/site-packages/transformers/models/gemma4_unified/modeling_gemma4_unified.py')
    reg=vr.read_text();arch=cfg['common']['model']['architecture']
    compat=dict(inspection='static installed files only; no GPU/model import',architecture=arch,
        vllm_registry_sha256=file_sha256(vr),vllm_exact_architecture_registered=arch in reg,
        qwen_architecture_registered='Qwen3_5ForConditionalGeneration' in reg,
        hf_implementation_present=hf.exists(),hf_implementation_sha256=file_sha256(hf),
        vllm_status='blocked_static_architecture' if arch not in reg else 'runtime_unmeasured',
        hf_status='runtime_unmeasured',no_architecture_alias_or_model_substitution=True)
    write_jsonl_once(out/'gemma_requests.jsonl',gemma);write_jsonl_once(out/'needcard_requests.jsonl',qwen)
    write_json_once(out/'OFF_REUSE_CHECK.json',dict(requests=100,original_file_sha256=file_sha256(old),
        old_tokenizer_probe_sha256=file_sha256(base/'A0/repair_1/TOKENIZER_PROBE.json'),tokenizer_identity=f.tokenizer.identity,
        rows=checks,input_tokens_min=min(r['input_tokens'] for r in checks),input_tokens_max=max(r['input_tokens'] for r in checks),
        original_payloads_unchanged=True,weight_loads=0))
    oldenv=json.loads((base/'A0/repair_1/ENV_REPORT.json').read_text())
    workloads={}
    for name,rows,batches,warmup,model in [('gemma',gemma,[(1,104),(4,16),(8,16),(16,16)],2,'g0_candidate'),
                                          ('needcard',qwen,[(1,3),(2,3)],1,'qwen_judge_candidate')]:
        groups=schedule(rows,batches,padded_context_cap=32768)
        m=oldenv['models'][model]
        workloads[name]=dict(requests_file=name+'_requests.jsonl',requests_sha256=file_sha256(out/(name+'_requests.jsonl')),
            model_path=m['path'],model_files=m['files'],architecture=m['architectures'][0],
            execution_identity='A0-probe:'+object_sha256(dict(model_files=m['files'],
                runtime=dict(cfg['runtimes']['hf'],fixed_batch_size=None,max_batch_size=16 if name=='gemma' else 2,
                    max_model_len=16384 if name=='gemma' else 32768),batch_schedule=batches,
                runner_sha256=file_sha256(ROOT/'project/scripts/rl1v3/a0_bounded_run.py'),decode=rows[0]['decode'])),
            g0e_reference_identity=f.binding.g_id if name=='gemma' else None,
            backend='hf',runtime_packages=cfg['runtimes']['hf']['packages'],
            max_model_loads=1,max_calls=sum(len(g) for g in groups)+warmup,warmup_calls=warmup,
            batches=[dict(request_ids=[r['request_id'] for r in g],batch=len(g),input_lengths=[len(r['input_ids']) for r in g]) for g in groups],
            padded_context_cap=32768,request_timeout_seconds=300,stage_timeout_seconds=7200 if name=='gemma' else 3600,
            native_context_tokens=262144,runtime_context_tokens=16384 if name=='gemma' else 32768,
            model_load_seconds=None,prefill_seconds=None,decode_seconds=None,ttft_seconds=None,peak_vram_mib=None,
            notes='timing outputs are not approved NeedCards, judge labels or B6e terminals')
    plan=dict(protocol=PROTOCOL,gpu_uuid=GPU_UUID,gpu_authorized=False,workloads=workloads,compatibility=compat,
        code_sha256={p:file_sha256(ROOT/p) for p in ('project/scripts/rl1v3/a0_bounded_run.py',
            'project/src/metacom_pm/rl1v3/generator/bounded_probe.py')},
        qwen_generation_config='absent; EOS from model text_config, PAD from pinned tokenizer vocabulary; explicit greedy config',
        backend_order='vLLM static admission first; named HF fallback only; no automatic alternate model',
        safety=dict(exclusive_process=True,minimum_free_before_load_mib=30720,minimum_free_during_run_mib=2048,
            lock='/opt/tokkio-data0/tokkio_projects/pmrl1-a6000-exclusive.lock',automatic_retry=False,
            on_failure='stop own job, preserve partials, release lock; do not kill another job or switch GPU'),
        source_version=f.registry.version,bank_version=f.bank.version,index_version=f.bank.index_version,
        fixed_pilot_budget=dict(needcards=20,g0_terminals=120,j1_max=360),
        b_v2_budget_discrepancy=dict(existing= [128,384],requested=[120,360],resolution='B owner must freeze the new manifest; no B sampler changed'),
        j1=dict(status='blocked_missing_actual_Checklist_and_G0_response_packs',requests_prepared=0,
            qwen_needcard_timing_is_not_j1_timing=True),
        scale_requests={str(n):dict(needcards=n,g0_terminals=n*16,j1_max=n*16*3,
            interpretation='finite-domain upper bound; unavailable heads reduce realized count') for n in (288,482,748)},
        measurements=[],costs=estimate([],needcards=20,g_terminals=120,j1_calls=360))
    write_json_once(out/'GPU_PLAN.json',plan)
    write_json_once(out/'APPROVAL_TEMPLATE_NOT_AUTHORIZED.json',dict(protocol=PROTOCOL,authorized=False,
        researcher_approval_reference=None,plan_sha256=object_sha256(plan),gpu_uuid=GPU_UUID,workloads=['gemma','needcard'],expires_at=None))
    print(json.dumps(dict(plan_sha256=object_sha256(plan),max_calls={k:v['max_calls'] for k,v in workloads.items()},compatibility=compat)))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);p.add_argument('--examples',type=Path,required=True)
    a=p.parse_args();prepare(a.out,a.examples)
