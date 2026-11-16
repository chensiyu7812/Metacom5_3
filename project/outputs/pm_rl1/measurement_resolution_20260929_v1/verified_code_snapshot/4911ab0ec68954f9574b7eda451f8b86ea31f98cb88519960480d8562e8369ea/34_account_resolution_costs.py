#!/usr/bin/env python3
"""Local compute accounting; preserves the paid ledger and makes no API quote."""
import json
import statistics
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file

OUT=PROJECT/'outputs/pm_rl1/measurement_resolution_20260929_v1'


def read(p):return json.loads(p.read_text())


def main():
    analysis=read(OUT/'analysis_final.json')
    old=read(PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1/measured_cost_update.json')
    ledger=PROJECT/'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    assert sha256_file(ledger)==old['paid_ledger_sha256']
    phases=[]
    for name in ('v2','v4'):
        a=analysis[name]
        phases.append(dict(phase=name,device='A6000',submitted=a['calls'],returned=a['calls'],unknown=0,
            engine_seconds=a['engine_wall_seconds'],load_seconds=a['load_seconds'],output_tokens=a['output_tokens']))
    a=analysis['v3_interrupted']
    phases.append(dict(phase='v3_interrupted',device='A6000',submitted=a['generation_starts'],
        returned=a['completed_rows'],unknown=a['unknown_interrupted'],
        engine_seconds=a['approximate_engine_seconds_to_signal'],engine_seconds_approximate=True,
        engine_seconds_completed_row_lower_bound=a['engine_seconds_to_last_completed_row'],
        load_seconds=a['load_seconds'],output_tokens=None,
        output_tokens_note='4 interrupted raw tails unavailable; never report their compute as zero'))
    for name,a in analysis['independent_model_diagnostics'].items():
        phases.append(dict(phase=name,device='A4500',submitted=a['calls'],returned=a['calls'],unknown=0,
            engine_seconds=a['engine_wall_seconds'],load_seconds=a['load_seconds'],output_tokens=a['output_tokens']))
    embedding=read(OUT/'public_observation_feature_probe.json')
    totals={gpu:dict(engine_seconds=sum(p['engine_seconds'] for p in phases if p['device']==gpu),
        load_seconds=sum(p['load_seconds'] for p in phases if p['device']==gpu)) for gpu in ('A6000','A4500')}
    for t in totals.values():t['engine_hours']=t['engine_seconds']/3600
    rate=analysis['v4']['engine_wall_seconds']/analysis['v4']['calls']
    outputs=[r['output_tokens'] for r in analysis['v4']['rows']]
    result=dict(status='ACTUAL_LOCAL_COMPUTE_ACCOUNTING_NO_PAID_EXECUTION',phases=phases,device_totals=totals,
        total_judge_submissions=sum(p['submitted'] for p in phases),returned_raw_outputs=sum(p['returned'] for p in phases),
        unknown_interrupted=sum(p['unknown'] for p in phases),new_generator_calls=0,
        new_paid_api_usd=0,paid_ledger_sha256=sha256_file(ledger),paid_ledger_unchanged=True,
        inherited_budget=old['inherited_paid_budget'],local_compute_currency_cost=None,
        currency_note='No electricity/rental rate provided; zero API spending is not zero compute or research labor.',
        wall_clock_note='A4500 and A6000 overlapped. Device engine wall times must not be added as project elapsed time. Loading/hashing/CPU analysis are separate.',
        cpu_e0_training_seconds=sum(a['elapsed_seconds'] for a in analysis['e0'].values()),
        embedding_probe=dict(device='A4500',embedding_texts=embedding['embedding_texts'],
            encoder_calls=embedding['encoder_calls'],load_seconds=embedding['load_seconds'],
            encoding_seconds=embedding['encoding_seconds'],total_process_seconds=embedding['total_process_seconds'],
            generative_judge_calls=0,note='additional to the judge-only device totals above'),
        v4_token_usage=dict(input_tokens=sum(r['input_tokens'] for r in analysis['v4']['rows']),
            output_tokens=sum(outputs),mean_output_tokens=statistics.mean(outputs),
            median_output_tokens=statistics.median(outputs),max_output_tokens=max(outputs),
            note='Includes Qwen reasoning and completed portions of failed attempts; not another provider/model billing estimate'),
        historical_pilot_judge_calls=old['total_J_calls_this_turn'],
        cumulative_new_route_judge_submissions=old['total_J_calls_this_turn']+analysis['physical_judge_generation_starts'],
        remaining_scope_call_ceiling=old['core_total'],additional_OFF_call_reserve=old['additional_OFF_reserve'],
        ceiling_note='Existing 96 train / 18 dev / 48 test planning scenario; not all calls are currently justified or scheduled. SFT diagnostics/retries/independent final review are additional.',
        conditional_J_only_projection=dict(scoring_calls=old['downstream_calls_each_G_and_J'],
            seconds_per_call_from_v4_batch=rate,hours=rate*old['downstream_calls_each_G_and_J']/3600,
            assumption='Same Qwen workload/context distribution/concurrency; excludes G, teacher/verifier, OFF, model loads, failures, training and independent review.',
            executor_training_or_quality_PPO_approved_by_projection=False),
        analysis_sha256=sha256_file(OUT/'analysis_final.json'),script_sha256=sha256_file(Path(__file__)))
    (OUT/'cost_closeout.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('total_judge_submissions','returned_raw_outputs','unknown_interrupted','device_totals','cpu_e0_training_seconds','new_paid_api_usd','conditional_J_only_projection')},ensure_ascii=False))


if __name__=='__main__':main()
