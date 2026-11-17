"""CPU-only G0e binding and real request construction; never loads weights."""
import argparse
from dataclasses import replace
import itertools
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.generator.g0e import (Binding, CONFIG, DECODE, PROTOCOL, STEP2, SYSTEM)
from metacom_pm.rl1v3.generator.preflight import environment_snapshot
from metacom_pm.rl1v3.io import canonical_json, file_sha256, object_sha256, write_json_once, write_jsonl_once


def build_config(root):
    """Reuse fixed A0 weight attestation; no model bytes are re-scanned."""
    att='project/outputs/pm_rl1/v3/A0/repair_1/ENV_REPORT.json'
    old=json.loads((root/att).read_text()); model=old['models']['g0_candidate']
    path=Path(model['path'])
    revision=(path/'.cache/huggingface/download/model.safetensors.metadata').read_text().splitlines()[0]
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    native=NativeTokenizer(path,root/'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json')
    envs={name:environment_snapshot(Path(python)) for name,python in (
        ('hf','/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python'),
        ('vllm','/opt/tokkio-data0/tokkio_envs/paper1-qwen35-vllm-py312/bin/python'))}
    runtimes={}
    for name,env in envs.items():
        runtimes[name]=dict(backend=name,python=env['python'],packages={k:env['packages'][k]
            for k in ('torch','transformers','tokenizers','safetensors','vllm')},
            dtype='bfloat16',attention='sdpa' if name=='hf' else 'backend-default-versioned',
            model_class='AutoModelForMultimodalLM' if name=='hf' else 'LLM',
            max_model_len=16384,max_batch_size=1,fixed_batch_size=1,max_batch_context_tokens=32768,
            padding_side='left',gpu_uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',
            deterministic_algorithms=True,allow_tf32=False,cublas_workspace_config=':4096:8',
            cross_backend_bitwise_determinism_claim=False)
    common=dict(protocol=PROTOCOL,scope='engineering_only',system_prompt=SYSTEM,step2_id=STEP2,
        decode=DECODE,tokenizer_identity=native.identity,
        renderer_implementation_sha256=file_sha256(root/'project/src/metacom_pm/rl1v3/render/request_packet.py'),
        model=dict(model_id='Gemma-4-12B-it-707f0a3',revision=revision,
            architecture=model['architectures'][0],native_context_tokens=model['context_limit'],
            files=model['files'],attestation_path=att,attestation_sha256=file_sha256(root/att),
            weight_hash_status='reused_A0_byte_attestation; fresh hash required before GPU load'),
        output_policy=dict(protocol='pmrl1v3-g0e-output-cache-1',timeout_seconds=300,
            empty='technical_failure_pending',length='technical_truncation_pending',
            timeout='technical_timeout_pending',oom='abort_own_job_pending',
            automatic_retry=False,cache='write_once_full_TerminalKey_request_and_runtime',
            output_parser='nonthinking_plain_response_v1',A7_research_G0=False))
    return dict(common=common,runtimes=runtimes,model_path=str(path),
        execution=dict(gpu_authorized=False,model_calls=0,preferred_probe='vllm',
            cpu_example_binding='hf_from_existing_pinned_runtime',
            fallback='named_HF_binding_only; no automatic different model'),environments=envs)


def run_examples(root,out):
    from metacom_pm.rl1v3.generator.g0e_port import make_port_factory
    factory=make_port_factory(root=root)
    coverage=[json.loads(x) for x in (root/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl').read_text().splitlines()]
    row=next(r for r in coverage if r['fold']<=5 and all(factory.for_prefix(factory.prefix(r)).availability().values()))
    prefix=factory.prefix(row); port=factory.for_prefix(prefix)
    hashes={}; keys={}; rows=[]; checks=[]
    for n in range(5):
        for subset in itertools.combinations(K.HEAD_ORDER,n):
            for order in itertools.permutations(subset):
                acquired=(); results=[]
                for h in order:
                    res=port.read(h,acquired=acquired)
                    assert isinstance(res,K.ReadSuccess),res
                    assert not port.verify_records(res.record_ids)
                    results.append(res); acquired+=(res.reading,)
                packet=port.request_packet(acquired)
                mask='+'.join(subset) or 'OFF'
                if mask in hashes:
                    assert hashes[mask]==packet.request_sha256 and keys[mask]==packet.key.sha256
                else:
                    hashes[mask]=packet.request_sha256; keys[mask]=packet.key.sha256
                    if subset in ((),('ME',),('RS',),K.HEAD_ORDER):
                        rows.append(dict(case=mask,prefix_id=prefix.prefix_id,**packet.private_envelope()))
                assert packet.token_ledger['input_tokens']==len(packet.input_ids)
                assert packet.token_ledger['total_context_bound']<=port.effective_context_tokens
                replay=port.replay(packet.key)
                assert isinstance(replay,K.ExecutionTrace);replay.verify_key(packet.key)
                checks.append(dict(subset=mask,order=order,request_sha256=packet.request_sha256,
                                   key_sha256=packet.key.sha256,trace_sha256=packet.trace.sha256,
                                   token_ledger=packet.token_ledger))
    assert len(hashes)==len(set(hashes.values()))==16 and len(checks)==65 and len(rows)==4
    write_jsonl_once(out/'REQUEST_EXAMPLES.jsonl',rows)
    write_jsonl_once(out/'ORDER_REPLAY.jsonl',checks)
    write_json_once(out/'REQUEST_ACCEPTANCE.json',dict(prefix_id=prefix.prefix_id,fold=row['fold'],
        subsets=16,orders=65,request_identity_count=len(set(hashes.values())),
        source_version=factory.registry.version,bank_version=factory.bank.version,index_version=factory.bank.index_version,
        bank_records=len(factory.bank.records),binding=factory.binding.spec,
        identity=factory.binding.identity,weights_loaded=False,model_calls=0,gpu_used=False,
        evaluation_status='pending',evidence_tier='engineering_only',cases=[r['case'] for r in rows]))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--write-binding',action='store_true',help='create a new CPU binding; refuses an existing path')
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.write_binding: write_json_once(ROOT/CONFIG,build_config(ROOT))
    a.out.mkdir(parents=True,exist_ok=True)
    run_examples(ROOT,a.out)
    print('G0e CPU examples: 4 cases, 16 subset identities, 65 read orders; zero model calls')


if __name__=='__main__':main()
