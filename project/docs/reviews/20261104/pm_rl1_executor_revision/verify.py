"""Independent artifact reconciliation; no model load or paid calls."""
import hashlib
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[4]
BASE=PROJECT/'outputs/pm_rl1';ROOT=BASE/'executor_revision_20261104_v2';FAILED=BASE/'executor_revision_20261104_v1'


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def stamped(x):assert x['identity']==digest({k:v for k,v in x.items() if k!='identity'})


def main():
    for folder in [ROOT,FAILED,BASE/'resource_value_probe_20261104_v1',BASE/'executor_use_probe_20261104_v1']:
        for name,h in read(folder/'OUTPUT_MANIFEST.json').items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha(folder/name)==h,name
    p=read(ROOT/'PROTOCOL.json');stamped(p)
    for name,h in p['sources'].items():assert sha(Path(name))==h,name
    for name,h in p['assets'].items():
        if name.endswith('.py'):assert sha(Path(name))==h,name
    for name,h in p['runtime']['adapter']['files'].items():assert sha(Path(p['runtime']['adapter']['path'])/name)==h
    rows=read(ROOT/'TRAINING_PRIVATE.json');inputs=read(ROOT/'INPUTS_PRIVATE.json');cards=read(ROOT/'EVAL_CARDS_PRIVATE.json')
    assert digest(rows)==p['training_identity'] and digest(inputs)==p['inputs_identity'] and digest(cards)==p['evaluation_identity']
    inv={x['case']:x for x in read(BASE/'resource_value_probe_20261104_v1/INVENTORY_PRIVATE.json')}
    assert len(rows)==17 and len({r['case'] for r in rows})==6 and sum(bool(r['historical_claims']) for r in rows)==2
    for row in rows:
        assert row['split']=='train' and row['weak_supervision'] and row['reward'] is None
        assert row['prefix_identity']==inv[row['case']]['prefix_identity'] and row['owner']==inv[row['case']]['owner']
        assert row['response_identity']==digest(row['response']) and row['id']==digest({k:v for k,v in row.items() if k!='id'})
        item=inputs[row['input_identity']]
        assert row['prefix_identity']==item['prefix_identity'] and not item['usage']['truncation']
        system=item['messages'][0]['content']
        records=json.loads(system.split('<resources>\n')[1].split('\n</resources>')[0]) if item['selected_keys'] else []
        assert [r['address'] for r in records]==item['selected_keys']
        for claim in row['historical_claims']:
            assert claim['modality']=='past_report_not_current_success'
            assert any('seeker: '+claim['source_quote'] in json.loads(r['content']).get('full_source_conversation','') for r in records)
    review=read(ROOT/'WEAK_SOURCE_REVIEW_PRIVATE.json');stamped(review)
    assert review['training_identity']==p['training_identity'] and review['admitted_for']=='bounded_weak_SFT_only'
    assert not review['qualified_reward'] and len(review['rows'])==17
    encoded=read(ROOT/'training/ENCODING.json');assert len(encoded)==17
    for row,e in zip(rows,encoded):
        assert row['id']==e['row_id'] and e['response_identity']==row['response_identity']
        assert e['messages_identity']==digest(inputs[row['input_identity']]['messages'])
        assert e['labels'][:e['prompt_tokens']]==[-100]*e['prompt_tokens']
        assert e['labels'][e['prompt_tokens']:]==e['input_ids'][e['prompt_tokens']:]
        assert len(e['input_ids'])==e['prompt_tokens']+e['target_tokens']<=131072
        assert e['input_ids'][-1] in p['runtime']['policy']['eos_token_ids']
    assert read(FAILED/'training/baseline_fit.json')==read(ROOT/'training/baseline_fit.json')
    assert read(FAILED/'FAILURE.json')['usable_checkpoints']==0
    steps=read(ROOT/'training/steps.json');epochs=read(ROOT/'training/epochs.json');final=read(ROOT/'training/FINAL.json')
    assert len(steps)==final['steps']==p['max_optimizer_updates']==15 and len(epochs)==3
    assert sum(s['examples'] for s in steps)==51 and [s['step'] for s in steps]==list(range(1,16))
    for epoch in range(1,4):assert sorted(s['examples'] for s in steps if s['epoch']==epoch)==[1,4,4,4,4]
    assert final['base_hash_before']==final['base_hash_after'] and any(v>0 for v in final['parameter_changes'].values())
    assert final['trainable_parameters']==3407872 and final['fixed_final']==epochs[-1]
    assert all('lora_' in n for n in final['parameter_changes'])
    assert not final['production_promoted'] and not final['qualified_reward']
    for epoch in epochs:
        adapter=Path(epoch['adapter'])
        for name,h in epoch['adapter_files'].items():assert sha(adapter/name)==h
        assert sha(adapter.parent/'training_state.pt')==epoch['optimizer_state_sha256']
    reload=read(ROOT/'RELOAD.json');expected=epochs[-1]['fit'];measured=reload['fit']
    delta=abs(expected['nll']-measured['nll']);per=max(abs(a['nll']-b['nll']) for a,b in zip(expected['rows'],measured['rows']))
    assert max(delta,per)<=1e-4 and reload['passed'] and reload['fresh_process']
    assert read(ROOT/'BASELINE_JOBS_PRIVATE.json')==[] and p['max_baseline_G_calls']==0
    assert len(read(ROOT/'REUSED_BASELINES_PRIVATE.json'))==32
    fp=read(FAILED/'PROTOCOL.json')
    jobs=read(FAILED/'BASELINE_JOBS_PRIVATE.json');baselines=read(FAILED/'REUSED_BASELINES_PRIVATE.json')
    assert digest(jobs)==fp['baseline_jobs_identity'] and digest(baselines)==fp['reused_identity']
    assert digest(read(ROOT/'REUSED_BASELINES_PRIVATE.json'))==p['reused_identity']
    assert len(jobs)==5 and len(baselines)==29 and sum(j.get('replay',False) for j in jobs)==2
    baseline_raws={k:v['raw'] for k,v in baselines.items()};replays=[]
    for job in jobs:
        key=job['input_identity'];request=job['request'];rid=request['request_id']
        assert request['messages']==inputs[key]['messages']
        assert rid==digest({k:v for k,v in request.items() if k!='request_id'})
        assert read(FAILED/'baseline_G'/(rid+'.started.json'))==job
        raw=read(FAILED/'baseline_G'/(rid+'.raw.json'))
        assert raw['request_id']==rid and raw['runtime_identity']==p['runtime']['identity']
        assert raw['input_tokens']==inputs[key]['usage']['input_tokens'] and raw['finish_reason']=='natural_stop'
        assert raw['output_token_ids'][-1] in p['runtime']['policy']['eos_token_ids'] and raw['api_cost_usd']==0
        if job.get('replay'):
            old=baseline_raws[key];replays.append(dict(text_equal=raw['text']==old['text'],tokens_equal=raw['output_token_ids']==old['output_token_ids']))
        else:baseline_raws[key]=raw
    cp=read(ROOT/'CANDIDATE_PROTOCOL.json');stamped(cp);assert cp==read(ROOT/'candidate_G/PROTOCOL.json')
    cr=cp['runtime'];old={k:v for k,v in p['runtime'].items() if k not in ('adapter','identity')}
    assert {k:v for k,v in cr.items() if k not in ('adapter','identity')}==old
    assert cr['adapter']['files']==epochs[-1]['adapter_files'] and cr['adapter']['path']==epochs[-1]['adapter']
    assert read(ROOT/'candidate_G/load.observed.json')['runtime']==cr
    requests=read(ROOT/'CANDIDATE_REQUESTS_PRIVATE.json');mapping=read(ROOT/'CANDIDATE_MAPPING.json')
    cinputs=read(ROOT/'CANDIDATE_INPUTS_PRIVATE.json');results=read(ROOT/'RESULTS_PRIVATE.json')
    assert len(requests)==len(mapping)==len(results)==32 and cp['max_G_loads']==1 and cp['max_G_calls']==32
    assert [r['identity'] for r in requests]==cp['request_ids']
    for key,rid in mapping.items():
        req=next(r for r in requests if r['identity']==rid);stamped(req);olditem=inputs[key];item=cinputs[key]
        assert req['messages']==item['messages']==olditem['messages']
        assert req['provenance']['selected_keys']==item['selected_keys']==olditem['selected_keys']
        assert item['selected_resource_identities']==olditem['selected_resource_identities'] and item['usage']==olditem['usage']
        assert read(ROOT/'candidate_G'/(rid+'.started.json'))['request']==req
        raw=read(ROOT/'candidate_G'/(rid+'.raw.json'));seal=read(ROOT/'candidate_G'/(rid+'.sealed.json'));stamped(seal)
        assert seal['raw_identity']==digest(raw) and seal['protocol_identity']==cp['identity'] and seal['reward'] is None
        visible=dict(messages=req['messages'],executor_identity=cr['identity'],draw_identity=req['draw_identity'],renderer_identity=req['renderer_identity'])
        assert raw['request_id']==digest(visible) and raw['runtime_identity']==cr['identity']
        assert raw['input_tokens']==olditem['usage']['input_tokens'] and raw['finish_reason']=='natural_stop' and raw['api_cost_usd']==0
        assert raw['output_token_ids'][-1] in cr['policy']['eos_token_ids'] and len(raw['output_token_ids'])==raw['output_tokens']
        row=next(r for r in results if r['input_identity']==key)
        assert row['before']==baseline_raws[key]['text'] and row['after']==raw['text'] and row['quality'] is row['reward'] is None
    assert len(list((FAILED/'baseline_G').glob('*.raw.json')))==5 and len(list((ROOT/'candidate_G').glob('*.raw.json')))==32
    review=read(ROOT/'CONTENT_REVIEW_PRIVATE.json');stamped(review)
    assert len(review['rows'])==32 and not review['qualified_reward']
    for rec in review['rows']:
        row=next(r for r in results if r['input_identity']==rec['input_identity'])
        assert rec['after_identity']==digest(row['after']) and rec['before_identity']==digest(row['before'])
        assert rec['quality'] is rec['reward'] is rec['human_quality_label'] is None
        for a in rec['anchors']:assert row['after'][a['start']:a['end']]==a['quote']
    closed=read(ROOT/'candidate_G/CLOSED.json');stamped(closed);assert closed['completed']==closed['natural_stops']==32
    freeze=read(BASE/'completion_20260930_v2/P2/dataset_freeze.json')
    for name,h in freeze['files'].items():assert sha(PROJECT/name)==h,name
    cfg=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for name,h in cfg['policy']['historical_files'].items():assert sha(Path(name))==h,name
    ledger=sha(Path(cfg['ledger']));assert ledger=='e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    checks=dict(status='VERIFIED',training_rows=17,training_contexts=6,epochs=3,optimizer_updates=15,
        training_exposures=51,failed_process_updates_without_checkpoint=2,training_loads_including_failed=2,candidate_loads=1,trainable_lora_parameters=3407872,frozen_base_unchanged=True,
        baseline_fit_nll=final['baseline_fit_nll'],final_fit_nll=final['final_fit_nll'],fresh_reload_nll_delta=delta,max_row_reload_delta=per,
        fixed_final_epoch=3,new_original_baseline_calls=5,candidate_calls=32,total_new_G_calls=37,
        natural_stops=37,preexisting_reused_baselines=29,reused_original_model_inputs_after_repair=32,evaluation_inputs=32,update_excluded_inputs=12,
        original_replays=replays,old_P2_frozen_files=len(freeze['files']),old_history_files=len(cfg['policy']['historical_files']),
        ledger_sha256=ledger,new_human_questions=0,new_quality_rewards=0,new_PM_PPO_updates=0,
        old_cost_control_PM_PPO_updates=24,API_cost_usd=0,new_client_latency_measurements=0,production_promoted=False,
        primary_target_fact_use_observed=sum(x['fact_used_in_candidate'] for x in review['primary_history_targets']),
        primary_targets=2,content_review_is_independent_human_rating=False)
    (Path(__file__).parent/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
