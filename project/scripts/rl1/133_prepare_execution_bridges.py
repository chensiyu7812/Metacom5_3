#!/usr/bin/env python3
"""Freeze two finite execution packages from isolated, already opened inputs.

Only existing files and the local tokenizer are used. No provider management,
GPU query, model load, inference, independent labels or training occurs here.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import verify_identity
from metacom_pm.rl1.development_feedback import DevelopmentAdapter, save_once, freeze_inputs
from metacom_pm.rl1.development_dispatch import PaidDevelopmentStage
from metacom_pm.rl1.resource_comparison_runner import request_for, protocol_for
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1 import diagnostic_support as money


def run(args):
    started=time.monotonic(); out=args.output.resolve()
    if out.exists(): raise ValueError('use a new package directory; never overwrite an old stage')
    out.mkdir(parents=True,mode=0o700)
    used={}
    def read(p, expected=None, text=False):
        p=Path(p).resolve(); h=sha(p)
        if expected is not None and h!=expected: raise ValueError('source hash mismatch: '+str(p))
        used[str(p)]=h
        return p.read_text() if text else json.loads(p.read_text())
    views=args.views.resolve(); vm=read(views/'OUTPUT_MANIFEST.json')
    def view(name):return read(views/name,vm[name])
    audit=args.audit.resolve(); am=read(audit/'OUTPUT_MANIFEST.json')
    def old_audit(name):return read(audit/name,am[name])
    old_allow=old_audit('INPUT_HASHES_PRIVATE.json')
    def old(name):return read(PROJECT/name,old_allow[name])
    protected=view('PROTECTED_HASHES.json')
    for path,h in protected.items():
        if sha(Path(path))!=h:raise ValueError('protected historical input changed')
    inputs=view('GENERATION_INPUTS_PRIVATE.json')
    freeze=read(PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2/executor_freeze.json',
        '7f552e714c595428f8268505762cf7cf8313e021fa971ac7ab9ec035ce234457')
    runtime=freeze['primary_runtime'];verify_identity(runtime)
    originals=old_audit('RESPONSE_LEDGER_PRIVATE.json')
    by_request={r['request_id']:r for r in originals}
    reuse=[]
    for row in inputs:
        if not row['reusable_old_requests']:continue
        if row['selected_keys'] or row['renderer_route']!='unchanged_original_OFF':raise ValueError('only unchanged OFF may reuse')
        # The old audit binds these raw/request files, not only their summaries.
        rid=sorted(row['reusable_old_requests'])[0];record=by_request[rid]
        request=old(record['request_path']);raw=old(record['raw_path'])
        if (record['split']!='dev' or request['request_id']!=rid or raw['request_id']!=rid
            or raw['runtime_identity']!=runtime['identity'] or raw['finish_reason']!='natural_stop'
            or request['messages']!=row['messages'] or request['renderer_identity']!=row['renderer_identity']
            or request['provenance']['prefix_identity']!=row['prefix_identity']
            or request['provenance']['canonical_counts']!=[0,0,0,0]
            or request['draw_identity']!=freeze['terminal_draw_identity']):raise ValueError('OFF reuse binding failed')
        reuse.append(dict(prepared_input_identity=row['identity'],original_request_id=rid,
            request_path=record['request_path'],raw_path=record['raw_path'],raw_sha256=old_allow[record['raw_path']],
            reply=raw['text'],score=None,independent_sample=False))
    code_names=['src/metacom_pm/rl1/'+x+'.py' for x in (
        'resource_comparison_runner','development_feedback','development_dispatch','development_preflight','durable',
        'local_backend','local_gpu_guard','generation','bound_generation','schema','calibration_workflow',
        'diagnostic_engine','diagnostic_support','recovery_schedule','strict_audit_delivery','feedback_score_audit')]
    code_names+=['scripts/rl1/'+x+'.py' for x in ('92_run_p2_common_pool','133_prepare_execution_bridges',
        '134_run_resource_comparison','135_run_development_stage')]
    code={str((PROJECT/n).resolve()):sha(PROJECT/n) for n in code_names}
    code_identity=digest(code)
    requests=[request_for(r,runtime=runtime,draw_identity=freeze['terminal_draw_identity'],code_identity=code_identity)
              for r in inputs if not r['reusable_old_requests']]
    if len(inputs)!=49 or len(reuse)!=6 or len(requests)!=43:raise ValueError('fixed input scope changed')
    from transformers import AutoTokenizer
    tokenizer=AutoTokenizer.from_pretrained(runtime['model_dir'],local_files_only=True)
    for r in requests:
        n=len(tokenizer.apply_chat_template(r['messages'],tokenize=True,add_generation_prompt=True))
        if n!=r['expected_input_tokens'] or n>=runtime['policy']['context_limit']:
            raise ValueError('token count/native context mismatch')
    assets={str((Path(runtime['model_dir'])/n).resolve()):h for n,h in runtime['model_files'].items()}
    assets.update({str((Path(runtime['adapter']['path'])/n).resolve()):h for n,h in runtime['adapter']['files'].items()})
    assets.update(code)
    if sha(PROJECT/'src/metacom_pm/rl1/generation.py')!=runtime['code_sha256'] or sha(PROJECT/'src/metacom_pm/rl1/bound_generation.py')!=runtime['binding_code_sha256']:
        raise ValueError('original decoding or binding code changed')
    reference=read(PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1/four_head_diagnostic_preparation_20261020_v1/protocol.json',
        '78185012ad3b307cf781757ed2fc7f5572c0ea08e58ae6a8971cd4a9b53e21ee')
    gp=protocol_for(requests,runtime=runtime,assets=assets,
        packages=runtime['packages']|{'peft':runtime['adapter']['peft_version']},
        gpu_uuid=reference['approval_scope']['gpu_uuid'],code_identity=code_identity,
        source_package_identity=digest(vm),run_directory=out/'live_G')
    save_once(out/'G_PROTOCOL.json',gp);save_once(out/'G_REQUESTS_PRIVATE.json',requests)
    save_once(out/'REUSED_OFF_PRIVATE.json',reuse)
    save_once(out/'G_APPROVAL_PENDING.json',dict(status='PENDING_RESEARCHER_DECISION',protocol_identity=gp['identity'],
        operations=['resource_comparison_generation'],user_authorization_reference=None,
        researcher_authorization_record=None,researcher_record_sha256=None,
        G_loads=1,G_calls_upper=43,BGE_loads=0,BGE_calls=0,API_cost_usd='0',automatic_retry=False))

    # Original J1 definitions, current score-aware S/A/R interfaces, no test data.
    vinputs=view('INPUT_HASHES_PRIVATE.json')
    base=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1'
    def prior(p,text=False):return read(p,vinputs[str(p.resolve())],text=text)
    materials=prior(PROJECT/'outputs/pm_rl1/completion_preparation_20261022/stage_materials_private.json')
    prompt=prior(base/'feedback_source_evidence_preparation_20261022_v2/JOINT_PROMPT_EN.txt',text=True)
    config=prior(base/'feedback_source_evidence_preparation_20261022_v2/protocol.json')['config']
    strict=read(base/'score_audit_strict_preparation_20261022_v1/protocol.json')
    adapter=DevelopmentAdapter(prompt=prompt,config=config)
    primary=[adapter.prepare({k:m[k] for k in ('reply','evidence')},'S') for m in materials]
    frozen_primary=view('J1_PRIMARY_REQUESTS_PRIVATE.json')
    if [dict(material=m['key'],purpose=m['purpose'],request=r) for m,r in zip(materials,primary)]!=frozen_primary:
        raise ValueError('prepared primary request identity or exact wire changed')
    ledger=Path(strict['financial_baseline']['ledger_path']).resolve();data=ledger.read_bytes()
    history=dict(strict['immutable_files'])|strict['historical_started_hashes']|strict['old_stop_hashes']
    history.pop(str(ledger),None)
    for p in Path(strict['run_dir']).glob('*'):
        if p.is_file() and p.suffix in ('.json','.sse'):history[str(p.resolve())]=sha(p)
    claude=PROJECT/'outputs/pm_rl1/claude_pilot_20261022_v1'
    for p in claude.rglob('*.json'):history[str(p.resolve())]=sha(p)
    counter=dict(prior_cumulative=strict['baseline_cumulative'],
        final_old_judge_starts=len(list(Path(strict['run_dir']).glob('*.started.json'))),
        claude_configuration_starts=len(list((claude/'live').glob('*.started.json'))))
    if counter!=dict(prior_cumulative=304,final_old_judge_starts=3,claude_configuration_starts=1):
        raise ValueError('historical cumulative identity needs reconciliation')
    save_once(out/'COUNTER_BASELINE.json',dict(**counter,cumulative=sum(counter.values()),
        interpretation='attempts including failures, not independent valid judgments'))
    lineage=[]
    migrated_tests={str((PROJECT/'tests'/n).resolve()) for n in (
        'test_rl1_feedback_workflow.py','test_rl1_feedback_source_evidence.py',
        'test_rl1_score_audit_validation.py','test_rl1_strict_audit_delivery.py')}
    for p,h in list(history.items()):
        actual=sha(Path(p))
        if actual!=h:
            if p not in migrated_tests:raise ValueError('historical protocol/start/STOP changed: '+p)
            # These public-engine test migrations postdate the old sealed run.
            # Preserve old expected hashes as history, bind current tests for
            # this NEW stage; never report the old protocol as unchanged code.
            lineage.append(dict(path=p,old_expected_sha256=h,current_sha256=actual,
                reason='public-engine test migration after the historical run; new-stage-only binding'))
            history[p]=actual
    save_once(out/'HISTORICAL_CODE_DELTAS.json',lineage)
    roots=[str(base.resolve()),str(claude.resolve())]
    starts=sorted(str(p.resolve()) for root in roots for p in Path(root).rglob('*.started.json') if 'management' not in p.parts)
    locks=sorted(str(p.resolve()) for p in base.rglob('*.lock') if not any('mock' in s or 'verification' in s for s in p.parts))
    # Same $6 funding identity must be reused by a later selected-validation
    # phase; it is NOT a fresh $6 for each directory. Neither phase is approved.
    funding=digest(dict(proposal='J1-complete-selection-20261022',materials=digest(materials),
        original_budget_usd='6',baseline_cumulative=308))
    policy=dict(trial=strict['financial_baseline']['financial_trial_identity'],funding_identity=funding,
        stage_cap=money.nanodollars('6'),trial_cap=money.nanodollars('7.9058232'),shared_cap=money.nanodollars('20'),
        baseline=money.nanodollars('1.50724291'),opening=money.nanodollars('0.03079930'),external_liability=0,
        old_cap=money.nanodollars('50'),account_opening=None,opening_trial=money.nanodollars('1.9058232'),
        max_attempts=82,recovery_cap=16,baseline_cumulative=308,cumulative_cap=567,
        reserve_nanodollars=money.API_WORST,opening_ledger_bytes=len(data),opening_ledger_sha256=hashlib.sha256(data).hexdigest(),
        historical_files=history|code|{k:v for k,v in used.items() if k!=str(ledger)},
        historical_start_roots=roots,historical_start_paths=starts,legacy_lock_paths=locks,
        ledger_path=str(ledger),run_directory=str(out/'live_J'),
        request_model='deepseek-flash',accepted_response_models=['deepseek-flash'],
        input_nanodollars_per_token=300,output_nanodollars_per_token=1200,
        public_price_table_identity=strict['public_price_table_identity'],
        published_model_names=['DeepSeek-V4.1-Flash','DeepSeek-V4.1-Flash-1017'])
    stage=PaidDevelopmentStage(out/'live_J',materials,adapter,ledger=ledger,policy=policy)
    stage.budget._history()
    total,trial,reserved,settled=stage.budget._totals(stage.budget.events())
    if trial!=policy['opening_trial'] or set(reserved)-set(settled):raise ValueError('financial opening differs or unknown liability remains')
    save_once(out/'J_CONFIG_PRIVATE.json',dict(inputs=freeze_inputs(materials,prompt,config),policy=policy,
        protocol_identity=stage.identity,ledger=str(ledger)))
    save_once(out/'J_APPROVAL_PENDING.json',dict(status='PENDING_RESEARCHER_DECISION',protocol_identity=stage.identity,
        operation='bounded_development_scoring',financial_policy_identity=digest(policy),
        researcher_authorization_record=None,researcher_record_sha256=None,physical_attempts_upper=82,
        funding_identity=funding,funding_usd='6',selected_validation_included_in_funding=True,
        selected_validation_authorized=False,management_requests_upper=2,
        old_service_cap_usd='3.65',proposed_service_cap_usd='7.9058232',old_capacity=374,proposed_capacity=567))
    save_once(out/'SOURCE_HASHES_PRIVATE.json',used)
    save_once(out/'CODE_HASHES.json',code)
    save_once(out/'PROTECTED_HASHES.json',protected)
    summary=dict(status='PREPARED_NOT_EXECUTED',G_protocol=gp['identity'],J_protocol=stage.identity,
        new_G_inputs=len(requests),reused_OFF=len(reuse),input_tokens=sum(r['expected_input_tokens'] for r in requests),
        J_primary=len(primary),J_max_attempts=82,J_funding_usd='6',J_funding_shared_with_selected_validation=True,
        ledger_trial_accounted_usd=money.usd(trial),shared_remaining_usd=money.usd(policy['shared_cap']-(total-policy['baseline'])),
        historical_attempts=308,real_BC_checkpoints=0,natural_updates=0,
        network_requests=0,model_loads=0,model_inference=0,API_cost_usd='0',seconds=time.monotonic()-started,
        remaining=['explicit live scopes','independent development references','selected-validation exposure and qualification',
                   'expanded common learning domain and fair baselines'])
    save_once(out/'READY.json',summary)
    save_once(out/'PACKAGE_MANIFEST.json',{str(p.relative_to(out)):sha(p) for p in out.rglob('*') if p.is_file()})
    print(json.dumps(summary,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output',required=True,type=Path)
    p.add_argument('--views',type=Path,default=PROJECT/'outputs/pm_rl1/evidence_views_20261030_v3')
    p.add_argument('--audit',type=Path,default=PROJECT/'outputs/pm_rl1/reorganization_20261029_v4')
    a=p.parse_args()
    try:run(a)
    except Exception as e:
        if a.output.exists() and not (a.output/'FAILURE.json').exists():
            save_once(a.output/'FAILURE.json',dict(error_type=type(e).__name__,message=str(e),real_calls=0))
        raise
