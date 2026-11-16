"""Reproduce the bounded proposal using development-only local source files.

Writes a new destination; never overwrites a prior preparation or source result.
Does not access model weights, network, or sealed jobs/labels.
"""
import argparse
import copy
import csv
import json
from pathlib import Path
import subprocess
from selection import HERE, REPO, code_identity, digest, read, save, sha, API_WORST, usd, Budget, nanodollars
from metacom_pm.rl1 import judge_completion_candidate as judge

DEV = 'project/outputs/pm_rl1/p3_v2_after_confirmation_20261014/development_plan.json'
AUDIT = 'project/outputs/pm_rl1/p3_v2_development_audit_20261014/analysis/reply_comparisons_private.json'
INTAKE = 'project/outputs/pm_rl1/development_closeout_20261014_v1/acceptance_final/development_intake_private.json'
CONTRACT = 'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'
BASE = 'project/outputs/pm_rl1/route_accounting_20261014_v1/analysis_final/alternative_budget.json'


def csvwrite(path, rows):
    with path.open('x', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)


def build(out):
    out.mkdir(parents=True, exist_ok=True)
    sources = {p: sha(REPO / p) for p in (DEV, AUDIT, INTAKE, CONTRACT, BASE)}
    original = read(REPO / DEV)
    assert original['phase'] == 'development' and len(original['requests']) == 33
    old = {r['job_id']: r for r in original['requests'] if r['draw_identity'] == 'primary'}
    rows = read(REPO / AUDIT); intake = {r['pair_id']: r for r in read(REPO / INTAKE)}
    assert len(rows) == 32 and len(old) == 32 and len(intake) == 16
    assert all(r['group'] == 'development' for r in intake.values())
    configs = {
      'deepseek_flash_high': dict(backend='deepseek', model='deepseek-flash',
        published_mapping='DeepSeek-V4.1-Flash', immutable_weights=False,
        thinking='enabled', reasoning_effort='high', top_p=1, temperature=None,
        response_format='json_object', quantization='provider_unknown',
        context_tokens=1048576, max_output_tokens=393216, timeout_seconds=900,
        stream_read_timeout_seconds=30, concurrency=1, retries=0,
        response_model_allowlist=['deepseek-flash'],
        parser='existing candidate parser; final content only; no repair',
        wrapper='official Chat Completions; same two messages',
        endpoint='https://api.deepseek.com/chat/completions', readiness='approval_and_account_required'),
      'gemma4_12b_bf16': dict(backend='gemma', model='google/gemma-4-12B-it',
        revision='707f0a3b8a3c7ad586ed01e27eafbad8a27dd0f7', immutable_weights=True,
        license='Apache-2.0', dtype='bfloat16', quantization='none', enable_thinking=False,
        do_sample=False, attention='sdpa', context_tokens=262144,
        max_output_tokens='context minus actual complete input; natural EOS only',
        min_output_reserve_tokens=32768, eos_token_ids=[1,106,50],
        timeout_seconds=900, concurrency=1, retries=0,
        gpu_uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',
        packages={'transformers':'5.17.0','torch':'2.7.1+cu128','tokenizers':'0.23.2','safetensors':'0.8.0'},
        interpreter='/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python',
        wrapper='official processor.apply_chat_template(enable_thinking=False)',
        parser='official processor.parse_response -> unchanged candidate parser; no repair',
        readiness='weights absent; tokenizer length and real loading unverified')}
    gemma_off=configs['gemma4_12b_bf16']
    gemma_on=copy.deepcopy(gemma_off)
    gemma_on['enable_thinking']=True
    gemma_on['wrapper']='official processor.apply_chat_template(enable_thinking=True)'
    deep_on=configs['deepseek_flash_high']
    deep_off=copy.deepcopy(deep_on)
    deep_off.update(thinking='disabled',reasoning_effort=None,temperature=1.0,top_p=None)
    configs={'gemma4_12b_bf16':gemma_off,'gemma4_12b_bf16_thinking':gemma_on,
             'deepseek_flash_off':deep_off,'deepseek_flash_high':deep_on}
    for label,c in zip('ABCD',configs.values()):
        c['label']=label
        c['implementation_identity'] = code_identity()
        c['rubric_identity'] = judge.RUBRIC_ID
        c['identity'] = digest(c)
    items, private = {}, []
    for r in sorted(rows, key=lambda x:(x['Chen_order'],x['side'])):
        key = f"dev{r['Chen_order']:02d}{r['side']}"
        source = old[r['job_id']]
        value = json.loads(source['messages'][1]['content'])
        assert value['reply'] == r['reply']
        assert source['messages'] == judge.messages_and_schema(value['legal_evidence'],value['reply'])[0]
        human = intake[r['pair_id']]
        items[key] = dict(split='development', reply=value['reply'], evidence=value['legal_evidence'],
            origin_job_id=r['job_id'], evidence_identity=r['evidence_identity'],
            Chen_order=r['Chen_order'], side=r['side'], pair_id=r['pair_id'],
            owner=human['mapping']['owner'], prefix_index=human['mapping']['index'],
            kind=human['mapping']['kind'], synthetic=False)
        private.append(dict(item_key=key, Chen_order=r['Chen_order'], side=r['side'], pair_id=r['pair_id'],
            kind=human['mapping']['kind'], owner=human['mapping']['owner'], prefix_index=human['mapping']['index'],
            human_preference=human['preference']['value'], preference_comparable=human['preference']['comparable'],
            human_risk_level=human['risks'][r['side']]['level'], human_q=None,
            human_observations=1, Du_origin='derived from Chen; not independent',
            intake_identity=human['identity'], historical_old=r['old'], historical_v2=r['new']))
    variants = []
    designs = [
      ('variant_actor_friend','dev15A',
       'Your old college friend helped you see your thesis from a different perspective. What part of that perspective feels most helpful to hold onto?',
       ['C:T005','C:T013'], 'The benefit is attributed to the old college friend, not the historical supporter or new AI.'),
      ('variant_actor_assistant','dev15B',
       'I, this new AI assistant, helped you see your thesis from a different perspective. What part of that perspective feels most helpful to hold onto?',
       ['C:T005','C:T013'], 'The asserted benefit owner conflicts with the new-AI contract and friend attribution; severity is NOT a gold label.'),
      ('variant_format_A','dev37A',items['dev37A']['reply'].replace('. You', '.\nYou'), [],
       'Only a sentence separator changes from space to newline; no factual content changes.'),
      ('variant_format_B','dev37B',items['dev37B']['reply'].replace('. You', '.\nYou'), [],
       'Only a sentence separator changes from space to newline; no factual content changes.')]
    for key, parent, text, ids, claim in designs:
        original_item = items[parent]
        turns = {t['id']:t['text'] for t in original_item['evidence']['current_prefix']}
        quotes = {i:turns[i] for i in ids}
        if ids:
            assert "old college friend" in quotes['C:T005'] and 'different perspective' in quotes['C:T013']
        else:
            assert text.replace('\n',' ') == original_item['reply']
        items[key] = original_item | dict(reply=text, synthetic=True, parent_item_key=parent)
        variants.append(dict(item_key=key,parent=parent,reply=text,source_quotes=quotes,
            evidence_identity=original_item['evidence_identity'],verified_mechanism=claim,
            verification='literal source check plus researcher interpretation; predeclared diagnostic only',
            expected_q=None, expected_m=None, severity_status='pending; never a gold risk label',
            adds_independent_user=False, sent_to_model=False))
    phases = dict(engineering=['dev02B','dev15B','dev37A','dev37B'],
                  development=[k for k in items if not items[k]['synthetic'] and k not in
                               ['dev02B','dev15B','dev37A','dev37B']],
                  diagnostics=['dev15B','dev35B','dev37A','dev37B']+[v[0] for v in designs])
    assert list(map(len, phases.values())) == [4,28,8]
    requests = []
    for candidate, c in configs.items():
        for phase, keys in phases.items():
            for i, key in enumerate(keys):
                messages,schema = judge.messages_and_schema(items[key]['evidence'],items[key]['reply'])
                r = dict(candidate=candidate, configuration_identity=c['identity'], phase=phase,
                    ordinal=i+1, item_key=key, draw=('repeat-1' if phase=='diagnostics' and i<4 else
                    'variant-1' if items[key]['synthetic'] else 'primary'),
                    messages_identity=digest(messages), schema_identity=digest(schema),
                    paired_slot=digest([key,phase]),
                    seed=int(digest([c['backend'],key,phase])[:8],16),
                    schedule_position=i*4+['ABCD','BADC','CDAB','DCBA'][i%4].index(c['label'])+1,
                    input_utf8_bytes=sum(len(m['content'].encode()) for m in messages))
                r['request_id'] = digest(r); requests.append(r)
    p = dict(status='DRAFT_NOT_APPROVED_NOT_FINAL_FREEZE', old_started=66,
        old_applied_semantic_revisions=1, unchanged_old_call_cap=140, max_new_configurations=4,
        recommended_new_configurations=4, model_families=2,
        design_amendment='2026-10-15 user requested 2 models x native thinking on/off; no execution authorization',
        mode_pair_order=['ABCD','BADC','CDAB','DCBA'],
        selection_rules=dict(version='paired-modes-20261015',
            engineering='4/4 natural, schema/evidence/identity/usage valid; uncertain is technical success only',
            complete_comparison='40 scheduled each; missing, technical and semantic unknown separately retained; no survivor-only ranking',
            semantic_gate='review all 16 pairs and diagnostics; zero unresolved source-proven material actor/time/fact/citation/severity errors',
            stability_gate='no unexplained equivalent-text U differences or severe flips; review all repeats and variants',
            unknown_policy='unknown is not tie/zero; unresolved critical unknown blocks recommendation; no all-abstain or all-tie shortcut',
            quality_order=['complete numeric coverage','source-confirmed q/severity reasoning errors',
                           'clear-preference and tie results on common subset','repeat and equivalent stability'],
            insufficient_quality_difference='do not assert superior accuracy; if all gates met and differences insufficient, use sustainability then reproducibility',
            sustainability='project measured all-output costs and engine time for BOTH 128/384; must fit unchanged relevant budget/contract; no automatic episode choice',
            tie_break='among sustainable quality-equivalent configurations prefer fixed local revision; within model prefer lower measured total recurring cost (GPU occupied time for Gemma, peak-accounted all-output USD for API); unresolved cost uncertainty => no unique recommendation',
            winner_max=1,no_result_driven_prompt_or_mode_changes=True,
            formal_thresholds_unchanged=True,development_is_not_independent_validation=True),
        implementation_identity=code_identity(),
        source_hashes=sources, contract_measurement=read(REPO/CONTRACT)['measurement'],
        configs=configs, items=items, requests=requests, sealed_payloads_present=False,
        final_qualification=dict(selected_configurations_max=1, sealed_pairs=24,
            unique_primary_calls=47, independent_repeat_calls=12, calls=59,
            provenance='count-only from previous identity audit; no sealed payload read',
            runnable_here=False))
    p['identity']=digest(p); save(out/'plan.json',p)
    save(out/'configs.json', configs)
    save(out/'variants_private.json',variants)
    save(out/'human_and_historical_reference_private.json',private)
    save(out/'source_hashes.json',sources)
    csvwrite(out/'request_manifest.csv', requests)
    csvwrite(out/'run_order.csv',sorted(requests,key=lambda r:(list(phases).index(r['phase']),r['schedule_position'])))
    dimensions=['actor_attribution','source_support_contradiction','citation_location','risk_severity','q_quality']
    review=[]
    for r in requests:
        for dim in dimensions:
            review.append(dict(candidate=r['candidate'],request_id=r['request_id'],item_key=r['item_key'],
                dimension=dim,verdict='pending',source_ids='',exact_quote='',explanation='',
                material_error='',reviewer='',reviewed_raw_sha256=''))
    csvwrite(out/'semantic_review_template_private.csv',review)
    monetary=Budget(REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl',
        trial=p['identity'],trial_cap=nanodollars(5),shared_cap=nanodollars(20),
        baseline=nanodollars('1.50724291'),opening=nanodollars('0.03079930'))
    total,trial,reserved,settled=monetary._totals(monetary.events())
    assert total==nanodollars('1.50724291') and len(reserved)==len(settled)==1250
    b=dict(existing_calls=66, applied_revision=1, original_cap_unchanged=140,
        engineering_calls=16, development_remaining_calls=112, repeats=16, variants=16,
        new_selection_calls=160, recovery_pool=4, one_winner_future_validation=59,
        proposed_total_with_validation_and_recovery=289, proposed_increase_over140=149,
        selection_without_recovery_cumulative=226, selection_with_recovery_cumulative=230,
        api_selection_calls=80, api_upper_calls_including_all_recovery_and_validation=143,
        proposed_trial_money_cap_usd=5, money_approved=False,
        shared_followup_cap_usd=20,ledger_total_usd=usd(total),since_boundary_usd='0',
        ledger_outstanding=len(reserved)-len(settled),provider_balance=None,external_liabilities=None,
        ledger_sha256=sha(monetary.path),max_single_api_reservation_usd=usd(API_WORST),
        all_143_native_ceiling_usd=usd(API_WORST*143),
        first_eight_API_native_ceiling_usd=usd(API_WORST*8),
        cost_estimate_method='input UTF8 bytes/4..bytes/3 +256 wrapping; output ALL billed tokens incl thinking; no cache',
        local_gpu_hours_measured=None)
    save(out/'budget_ledger_snapshot.json',b)
    costs=[]
    def cost_row(candidate,stage,n,totalbytes):
        lowinp=totalbytes/4+n*256; hiinp=totalbytes/3+n*256
        for output in (2000,8000,32768,65536):
            low=(lowinp*.3+n*output*1.2)/1e6; high=(hiinp*.3+n*output*1.2)/1e6
            costs.append(dict(candidate=candidate,stage=stage,api_calls=n,billed_output_each=output,
                peak_low_usd=round(low,6),peak_high_usd=round(high,6),
                offpeak_low_usd=round(low/2,6),offpeak_high_usd=round(high/2,6),
                serial_minutes_30s=round(n*.5,1),serial_minutes_180s=round(n*3,1),
                timing='scenario only, not measured'))
    meanbytes=(1492337+2226370+645557)/92
    for candidate in ['deepseek_flash_off','deepseek_flash_high']:
        api=[r for r in requests if r['candidate']==candidate]
        for stage in phases:
            rr=[r for r in api if r['phase']==stage]
            cost_row(candidate,stage,len(rr),sum(r['input_utf8_bytes'] for r in rr))
        for name, rr in [('primary_32',[r for r in api if r['draw']=='primary']),
                         ('repeat_4',[r for r in api if r['draw']=='repeat-1']),
                         ('variant_4',[r for r in api if r['draw']=='variant-1'])]:
            cost_row(candidate,name,len(rr),sum(r['input_utf8_bytes'] for r in rr))
        cost_row(candidate,'selection_all',40,sum(r['input_utf8_bytes'] for r in api))
        # Count/size-only prior audit aggregates; no sealed payload access.
        cost_row(candidate,'future_sealed_primary',47,2226370)
        cost_row(candidate,'future_independent_repeats',12,645557)
        cost_row(candidate,'recovery_reserve',4,max(r['input_utf8_bytes'] for r in api)*4)
        for n in [2817,4353,288,96,192]:
            cost_row(candidate,'research_'+str(n),n,meanbytes*n)
    csvwrite(out/'cost_scenarios.csv',costs)
    gpu=[]
    for candidate,seconds in [('gemma4_12b_bf16',(30,180)),('gemma4_12b_bf16_thinking',(60,300))]:
        for stage,n in [('engineering',4),('selection_all',40),('future_validation',59),
                        ('research_128_core',2817),('research_384_core',4353),('optional_and_reserves',576)]:
            gpu.append(dict(candidate=candidate,stage=stage,calls=n,
                GPU_hours_low=n*seconds[0]/3600,GPU_hours_high=n*seconds[1]/3600,
                timeout_hours=n*900/3600,measured=False,
                caveat='planning sensitivity only, plus loading/prefill overrun; not a measured mode speed difference'))
    csvwrite(out/'gpu_scenarios.csv',gpu)
    approval=dict(status='PENDING_USER_CONFIRMATION',plan_identity=p['identity'],
        confirmation_reference=None,configuration_identities=[c['identity'] for c in configs.values()],
        phases=['engineering'],old_calls=66,old_semantic_revision=1,research_scope_unchanged=True,
        new_calls_limit=16,cumulative_calls_limit=140,trial_cap_usd=None,
        data_transfer_approved=False,exclusive_paid_writer_confirmed=False,
        account_read_approved=False,call_cap_amendment_reference=None,
        provider_account_reconciled=False,price_and_capabilities_rechecked=False,
        data_permission_evidence=None,service_data_conditions_acknowledged=False,
        account_available_usd=None,external_liability_usd=None,provider_metadata_receipt=None,
        local_model_path=None,local_snapshot_receipts={})
    save(out/'approval_template_PENDING.json',approval)
    save(out/'baseline.json',dict(branch=subprocess.check_output(['git','branch','--show-current'],cwd=REPO,text=True).strip(),
        head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=REPO,text=True).strip(),
        status=subprocess.check_output(['git','status','--short'],cwd=REPO,text=True),
        no_inference=True,no_download=True,no_sealed_access=True,no_source_edits=True))
    print(json.dumps(dict(out=str(out),identity=p['identity'],requests=len(requests),real_calls=0)))


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__)
    a.add_argument('--out',type=Path,required=True,help='new directory; existing files are never overwritten')
    build(a.parse_args().out)
