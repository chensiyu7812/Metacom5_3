#!/usr/bin/env python3
"""Audit existing timing coverage; never infer deployment latency from tokens."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

PROJECT=Path(__file__).resolve().parents[2]
BASE=PROJECT/'outputs/pm_rl1'


def main(output):
    if output.exists():raise ValueError('New output directory required')
    sources={}
    def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
    def read(p):
        p=Path(p).resolve();sources[str(p)]=sha(p)
        return json.loads(p.read_text())
    def verify(folder,manifest='OUTPUT_MANIFEST.json'):
        for name,h in read(folder/manifest).items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha(folder/name)==h
    train=BASE/'organized_initial_training_20261103_v2'
    feedback=BASE/'actual_training_feedback_20261103_v1'
    findings=BASE/'decision_findings_20261104_v1'
    verify(train,'PACKAGE_MANIFEST.json');verify(feedback);verify(findings)
    lineage=read(feedback/'SOURCES_PRIVATE.json')
    response_path=BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json'
    assert sha(response_path)==lineage['response_export_sha256']
    assert sha(train/'PACKAGE_MANIFEST.json')==lineage['package_manifest_sha256']
    raw=read(response_path)
    for p,h in lineage['raw_and_seal_hashes'].items():assert sha(p)==h
    menu={e['identity']:e for e in read(train/'MENU_PRIVATE.json')['endpoints']}
    question=read(findings/'PRIORITY_QUESTION_PRIVATE.json')
    case=[]
    for c in question['cards']:
        request=menu[c['endpoint_identity']]['requests']['ON']
        row=raw[request['request_id']]
        assert row['request_id']==request['request_id'] and row['text']==c['reply']
        case.append(dict(alias=c['alias'],endpoint_identity=c['endpoint_identity'],
            request_id=request['request_id'],resource_tokens=c['resource_tokens'],
            generation_seconds=row['generation_seconds'],input_tokens=row['input_tokens'],
            output_tokens=row['output_tokens'],historical_reuse='reuse_proof_identity' in row,
            client_E2E_TTFT_seconds=None,client_E2E_completion_seconds=None,
            paired_latency_effect=None,
            interpretation='Component timing from different runs; not a matched deployment comparison.'))
    groups={}
    for label,flag in [('historical_OFF_reuse',True),('new_generation',False)]:
        values=[r['generation_seconds'] for r in raw.values() if ('reuse_proof_identity' in r)==flag]
        assert values and all(isinstance(v,(int,float)) and math.isfinite(v) and v>=0 for v in values)
        groups[label]=dict(calls=len(values),min_seconds=min(values),median_seconds=statistics.median(values),
            max_seconds=max(values),scope='archived G component durations, not client latency')
    timing_keys=sorted({k for r in raw.values() for k in r if any(s in k.lower() for s in ('seconds','latency','first_token','client_send'))})
    assert timing_keys==['generation_seconds']
    assert len(raw)==431 and groups['new_generation']['calls']==407 and groups['historical_OFF_reuse']['calls']==24
    cfg=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for p,h in cfg['policy']['historical_files'].items():assert sha(p)==h
    sources[str(Path(cfg['ledger']).resolve())]=sha(cfg['ledger'])
    last=read(PROJECT/'docs/reviews/20261104/pm_rl1_contextual_value/CHECKS.json')
    assert sha(cfg['ledger'])==last['ledger_sha256']
    sources[str(Path(__file__).resolve())]=sha(__file__)
    sources[str((PROJECT/'src/metacom_pm/rl1/generation.py').resolve())]=sha(PROJECT/'src/metacom_pm/rl1/generation.py')
    assert all(sha(p)==h for p,h in sources.items())
    summary=dict(generation_records=len(raw),G_component_timed_records=len(raw),
        deployment_client_TTFT_records=0,deployment_client_completion_records=0,
        complete_PM_acquisition_G_client_traces=0,fields_found=timing_keys,
        G_timing_scope='Timer starts after chat tokenization/device transfer and ends after generation, synchronization and decoding.',
        missing=['client send/receive/display events','initial PM encoding and planning','sequential retrieval and encoding',
            'queue/network time','first visible content event','matched interleaved repetitions'],
        group_diagnostics=groups,token_to_latency_conversion_performed=False,
        previous_token_break_even_is_not_deployment_value=True,
        deployment_latency_claim_supported=False,new_model_calls=0,new_provider_calls=0,
        new_cost_usd=0,natural_training_updates=0,
        frozen_historical_files_verified=len(cfg['policy']['historical_files']),
        raw_and_seal_files_verified=len(lineage['raw_and_seal_hashes']))
    output.mkdir(parents=True,mode=0o700)
    def save(name,value):
        p=output/name;p.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
    save('SUMMARY.json',summary);save('C02_COMPONENT_TIMINGS_PRIVATE.json',case)
    save('SOURCE_HASHES_PRIVATE.json',sources)
    save('OUTPUT_MANIFEST.json',{p.name:sha(p) for p in output.iterdir()})
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    main(p.parse_args().output)
