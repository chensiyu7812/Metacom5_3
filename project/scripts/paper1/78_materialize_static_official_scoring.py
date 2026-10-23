#!/usr/bin/env python3
"""Bind completed natural-end generations to exact official scoring payloads.

Offline only. Produces actual payload/token estimates and per-call native-
maximum reservations; it never sends an API request or fills missing outputs.
"""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_file, sha256_text, write_json, write_jsonl
from metacom_pm.paper1.evaluation.static_official_templates import render_templates


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--package',type=Path,default=PROJECT/'outputs/paper1_calibration/static_sample_20260917_v1')
    parser.add_argument('--responses',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    summary=read_json(args.package/'preparation_summary.json')
    for name,digest in summary['package_artifacts'].items():
        if sha256_file(args.package/name)!=digest:raise RuntimeError('package file changed: '+name)
    config=read_json(args.package/'scorer_config.json')
    templates=read_json(args.package/'official_scorer_templates.json')
    references={r['target_id']:r for r in iter_jsonl(args.package/'evaluator_inputs.jsonl')}
    requests=list(iter_jsonl(args.package/'generator_requests.jsonl'))
    by_id={r['request_id']:r for r in requests}
    actual=list(args.responses.glob('*.json'))
    if any(f.stem not in by_id for f in actual):raise RuntimeError('unknown response identity')
    import tiktoken
    encoder=tiktoken.encoding_for_model(config['model'])
    payloads,excluded=[],[]
    for r in requests:
        path=args.responses/(r['request_id']+'.json')
        if not path.exists():
            excluded.append({'request_id':r['request_id'],'reason':'not_generated'})
            continue
        saved=read_json(path)
        if saved['request_sha256']!=r['request_sha256']:raise RuntimeError('generation request identity mismatch')
        if saved.get('natural_end') is not True or saved.get('finish_reason')!='stop':
            excluded.append({'request_id':r['request_id'],'reason':'not_naturally_complete'})
            continue
        reference=references[r['target_id']]
        messages=render_templates(templates[r['task']],question=reference['question'],gold=reference['gold'],prediction=saved['raw_output'])
        estimated_input=32+sum(32+len(encoder.encode(m['content'])) for m in messages)
        if estimated_input + config['provider_max_output_tokens'] > config['context_tokens']:
            excluded.append({'request_id':r['request_id'],'reason':'complete_input_does_not_leave_native_output_space'})
            continue
        body={'model':config['model'],'messages':messages}
        payloads.append({'logical_call_id':'amount_score_'+r['request_id'],'request_id':r['request_id'],
                         'target_id':r['target_id'],'task':r['task'],'body':body,
                         'call_hash':sha256_text(canonical_json(body)),
                         'prediction_sha256':sha256_text(saved['raw_output']),
                         'generator_result_sha256':sha256_file(path),
                         'estimated_input_tokens_with_framing_reserve':estimated_input,
                         'maximum_output_tokens_for_reservation_only':config['provider_max_output_tokens'],
                         'reservation_usd':round((estimated_input*2.5+config['provider_max_output_tokens']*10)/1e6,8)})
    args.out.mkdir(parents=True,exist_ok=True)
    write_jsonl(args.out/'requests.jsonl',payloads)
    write_json(args.out/'manifest.json',{'status':'OFFLINE_PREPARED_NOT_EXECUTED','scheduled_generations':len(requests),
        'naturally_complete_scorer_payloads':len(payloads),'excluded':excluded,'paid_calls':0,
        'stage_cap_usd':summary['proposed_stage_hard_cap_including_retries_usd'],
        'full_batch_simultaneous_worst_case_usd':sum(r['reservation_usd'] for r in payloads),
        'sequential_reservation_required':True,'temperature_and_max_completion_tokens_omitted_as_upstream':True,
        'no_API_execution_authorized_by_this_script':True,'request_file_sha256':sha256_file(args.out/'requests.jsonl')})
    print(json.dumps({'prepared':len(payloads),'excluded':len(excluded),'paid_calls':0}))


if __name__=='__main__':main()
