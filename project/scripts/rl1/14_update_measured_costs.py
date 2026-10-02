#!/usr/bin/env python3
"""Read-only measured compute and optional API quotation; sends no requests."""
import json
from pathlib import Path
import statistics
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.judge import RUBRIC
from metacom_pm.rl1.evidence import legal_evidence,prefix_from_dict
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
OUT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'
DATA=PROJECT/'outputs/pm_rl1/source_and_capacity_20260928_v1'


def main():
    import tiktoken
    enc=tiktoken.encoding_for_model('gpt-4o')
    review=json.loads((OUT/'independent_review_UNSCORED.json').read_text())
    system=(RUBRIC.split('Return ONE JSON object',1)[0].replace('ONE new emotional-support reply','each of TWO new emotional-support replies independently')+
        '\nEvaluate replies A and B separately on q/m, with source evidence for each. Then compare them using A, B, equivalent or uncertain. '
        'Equivalent can mean equally poor. Do not infer which system produced either reply. Return one JSON object with q_A,m_A,q_B,m_B,pairwise,reason,evidence,uncertainty. No arbitrary rationale length limit.')
    inputs=[];drafts=[]
    for item in review['items']:
        user=json.dumps(dict(legal_evidence=item['evidence'],replies=item['replies']),ensure_ascii=False)
        content=len(enc.encode(system))+len(enc.encode(user))
        inputs.append(content+96)
        drafts.append(dict(item_id=item['item_id'],messages=[dict(role='system',content=system),dict(role='user',content=user)],
            exact_content_tokens=content,framing_reserve=96,estimated_input_tokens=content+96))
    (OUT/'optional_model_review_pricing_drafts_private.json').write_text(json.dumps(drafts,ensure_ascii=False,indent=2)+'\n')
    users={u.owner_id:u for u in load_sanitized_runtime_users(PROJECT/'data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json')}
    formal_lengths=[]
    for raw in json.loads((DATA/'prefixes_private.json').read_text()):
        if raw['split']!='test':continue
        p=prefix_from_dict(raw);e,_=legal_evidence(p,users[p.owner_id])
        formal_lengths.append(len(enc.encode(system))+len(enc.encode(json.dumps(dict(legal_evidence=e),ensure_ascii=False)))+96+512)
    native=16384
    def price(total_input,n,output):return dict(sync_usd=(total_input*2.5+n*output*10)/1e6,
        batch_usd=(total_input*1.25+n*output*5)/1e6)
    price_rows=[dict(pilot_pairs=10,input_tokens_estimated=sum(inputs),assumed_output_tokens_per_pair=n,
        assumption_is_output_cap=False,**price(sum(inputs),10,n)) for n in (512,1024,native)]
    formal_scenarios={name:int(value) for name,value in [('median',statistics.median(formal_lengths)),
        ('p95',sorted(formal_lengths)[int(.95*len(formal_lengths))]),('max',max(formal_lengths))]}
    combined=[dict(formal_input_scenario=name,formal_pairs=24,pilot_pairs=10,assumed_output_per_pair=n,
        assumption_is_output_cap=False,**price(sum(inputs)+value*24,34,n)) for name,value in formal_scenarios.items() for n in (512,1024,native)]
    core=dict(executor_data=(96+18)*3*6,initialization=1440,rl_training=1536,
        dev_evaluation=2*3*2*18*2,formal_execution=864,formal_policy_cross=1920)
    old=json.loads((PROJECT/'outputs/pm_rl1/engineering_20260928_v1/cost_reassessment.json').read_text())
    ledger=PROJECT/'outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    assert sha256_file(ledger)==old['budget_ledger_sha256']
    result=dict(status='OFFLINE_COST_UPDATE_NO_PAID_REQUESTS',checked_date='2026-09-28',
        official_sources=dict(prices='https://developers.openai.com/api/docs/pricing',model='https://developers.openai.com/api/docs/models/gpt-4o',batch='https://developers.openai.com/api/docs/guides/batch'),
        pricing_scenario_only='gpt-4o text, standard or batch; no external reviewer model selected by this estimate',
        rates_usd_per_million=dict(standard_input=2.5,standard_output=10,batch_input=1.25,batch_output=5),native_output_limit=native,
        pilot_payload_input_tokens=dict(n=10,total=sum(inputs),min=min(inputs),median=statistics.median(inputs),max=max(inputs)),
        token_count_caveat='actual prompt text counted with o200k_base; 96-token framing reserve is an estimate, final billing requires provider usage',
        pilot_review_scenarios=price_rows,formal_input_scenarios_with_512_reply_token_allowance=formal_scenarios,
        combined_34_pair_scenarios=combined,
        external_review_caveats=['no model ranking or reliability claim follows from price','24 final replies not generated; their reply sizes are forecasts',
            'additional reverse presentations or reviewer duplicates cost extra','no provider transport/reservation has been created'],
        core_local_calls=core,core_total=sum(core.values()),previous_core_total=old['core_local_call_total'],
        additional_OFF_reserve=162*2*2,measurement_actual_J_calls=55,measurement_new_G_calls=23,measurement_existing_G_cache_hits=1,
        known_core_plus_OFF_plus_pilot_calls=sum(core.values())+648+55+23,
        not_full_project_ceiling='excludes old 6-call smoke, failed process starts, parser/rubric reruns, SFT diagnostics, LoRA/PPO compute, independent review and other optional work',
        inherited_paid_budget=old['budget'],paid_ledger_sha256=sha256_file(ledger),new_paid_api_usd=0,
        cpu_gpu_currency_cost=None,currency_reason='no hardware rental/electricity rate supplied; zero API spend is not zero local compute cost',
        downstream_calls_each_G_and_J=3096,executor_teacher_calls=1026,executor_verifier_calls=1026)
    analysis_path=OUT/'measurement_analysis.json'
    if analysis_path.exists():
        a=json.loads(analysis_path.read_text());jc=a['judge_compute'];g=a['generation']
        result['measured_compute']=dict(generator=g,judge=jc,
            pilot_inventory_process_seconds=json.loads((OUT/'retrieval_manifest.json').read_text())['elapsed_seconds'],
            full_capacity_process_seconds=json.loads((DATA/'retrieval_manifest.json').read_text())['elapsed_seconds'],
            failed_bootstrap_logged_but_duration_not_fully_persisted=True)
        result['conditional_downstream_J_only_hours']=3096*jc['engine_wall_seconds_per_completed_draw']/3600
        result['projection_caveat']='rough planning projection ONLY if future Qwen workload and concurrency match this pilot; excludes teacher/verifier, OFF, loading, failures/retries, training and independent review; current J is not yet reward-ready'
    indexed_pointer=OUT/'indexed_transport_smoke_pointer.json'
    if indexed_pointer.exists():
        ip=json.loads(indexed_pointer.read_text())
        summary_path=Path(ip['run_dir'])/'summary.json'
        assert sha256_file(summary_path)==ip['summary_sha256']
        extra=json.loads(summary_path.read_text())
        result['additional_indexed_transport_J_calls']=len(extra['rows'])
        result['total_J_calls_this_turn']=55+len(extra['rows'])
        result['indexed_transport_compute']=dict(engine_wall_seconds=extra['engine_wall_seconds'],
            load_seconds=extra['load_seconds'],note='five transport probes; not a qualified replacement throughput estimate')
        result['known_core_plus_OFF_plus_pilot_calls']+=len(extra['rows'])
    (OUT/'measured_cost_update.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ['pilot_payload_input_tokens','pilot_review_scenarios','core_total','new_paid_api_usd']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
