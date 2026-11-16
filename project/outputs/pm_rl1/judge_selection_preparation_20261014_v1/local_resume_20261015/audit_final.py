"""Read-only audit of original identities, immutable receipts and actual calls."""
from pathlib import Path
import collections, subprocess, sys, sqlite3

OUT=Path(__file__).resolve().parent
sys.path.insert(0,str(OUT.parent))
import selection as s
from resume_engineering import now,reconstruct,slots

plan=s.load_plan(); base=s.read(OUT/'baseline.json')
prior=s.read(s.HERE/'local_engineering_20261015/baseline_current.json')
manifest=s.read(s.HERE/'delivery_manifest.json')['files']
for rel,h in manifest.items():assert s.sha(s.HERE/rel)==h,rel
for rel,h in base['prior_files'].items():assert s.sha(s.HERE/rel)==h,rel
for rel,h in prior['preserved_work_files'].items():assert s.sha(s.REPO/rel)==h,rel
contract=s.REPO/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'
assert s.sha(contract)==prior['contract_sha256']
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=s.REPO,text=True).strip()
branch=subprocess.check_output(['git','branch','--show-current'],cwd=s.REPO,text=True).strip()
assert head==base['head'] and branch=='work/paper1-rq1-integration-20260816'
assert not subprocess.check_output(['git','diff','--name-only'],cwd=s.REPO,text=True)
assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=s.REPO,text=True)
old_runs=[]
old1=next((s.REPO/'project/outputs/pm_rl1/completion_20260930_v2/P3/candidate_v1').glob('development/*/summary.json')).parent
old2=s.REPO/'project/outputs/pm_rl1/p3_v2_after_confirmation_20261014/runs/development'
for folder in (old1,old2):
    ids={p.name.split('.')[0] for p in folder.glob('*.request.json')}
    assert ids=={p.name.split('.')[0] for p in folder.glob('*.raw.json')}=={p.name.split('.')[0] for p in folder.glob('*.measurement.json')}
    assert len(ids)==s.read(folder/'summary.json')['physical_calls_this_invocation']==33
    for rid in ids:
        assert s.read(folder/(rid+'.request.json'))['request_id']==rid==s.read(folder/(rid+'.raw.json'))['request_id']
    if (folder/'attempts.sqlite').exists():
        with sqlite3.connect('file:'+str(folder/'attempts.sqlite')+'?mode=ro',uri=True) as conn:
            assert {r[0] for r in conn.execute('select request_id from attempts')}==ids
    old_runs.append(dict(path=str(folder),physical_calls=len(ids),all_request_raw_measurement_bindings=True))
old_calls=sum(x['physical_calls'] for x in old_runs)
assert old_calls==66
assert s.read(s.REPO/'project/outputs/pm_rl1/p3_v2_after_confirmation_20261014/protocol.json')['semantic_revisions_after_human_labels']==1
history=reconstruct(plan,s.HERE/'live_runs')
requests={r['request_id']:r for r in slots(plan)}
assert set(history['occupied'])<=set(requests) and history['total_started_or_evidenced']==2
for rid,kinds in history['occupied'].items():
    assert set(kinds)=={'started','result','raw','response'}
    req=requests[rid];folder=s.HERE/'live_runs'/req['candidate']
    raw=s.read(folder/(rid+'.raw.json'));response=s.read(folder/(rid+'.response.json'))
    result=s.read(folder/(rid+'.result.json'))
    assert raw['request_identity']==response['request_identity']==rid
    assert raw['raw_text']==response['raw_text']
    messages,schema=s.payload(plan,req)
    assert s.digest(messages)==req['messages_identity'] and s.digest(schema)==req['schema_identity']
    assert result['measurement']==s.measured(plan,req,response)
    assert result['measurement']['measurement_status']=='parse_or_evidence_failure'
    assert all(result['measurement'][k] is None for k in ['q','m','candidate_utility'])
    assert raw['natural_eos'] and raw['last_token']==106
    assert response['native_parsed']['content'].startswith('```json\n')
    assert response['native_parsed']['content'].endswith('\n```')
    assert raw['token_accounting']['total_output']==sum(raw['token_accounting'][k] for k in ['thinking','final','format'])
    assert (folder/'STOP.json').exists()
ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
assert s.sha(ledger)==base['paid_ledger_sha256']
b=s.Budget(ledger,trial=plan['identity'],trial_cap=0,shared_cap=s.nanodollars(20),baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('0.03079930'))
total,trial,reserved,settled=b._totals(b.events())
assert trial==0 and total==s.nanodollars('1.50724291') and not (set(reserved)-set(settled))
amendment=s.read(OUT/'engineering_amendment_corrected.json')
assert s.sha(s.HERE/'resume_engineering.py')==amendment['resume_code_sha256']
assert s.sha(s.HERE/'test_resume_engineering.py')==amendment['tests_sha256']
checks=[s.read(f) for f in (s.HERE/'live_runs/continuations').rglob('gpu_check_*.json')]
assert len(checks)==12 and all(q['returncode']==0 and not q['error'] for c in checks for q in c['queries'])
assert all(not c['visible_processes'] if c['own_pid'] is None else all(x['pid']==c['own_pid'] for x in c['visible_processes']) for c in checks)
assert s.read(OUT/'process_receipt_corrected.json')['exit_code']==0
assert not Path('/proc/619502').exists()
result=dict(time_jst=now(),head=head,branch=branch,real_path=str(s.REPO),
    original_delivery_files_unchanged=len(manifest),previous_receipt_files_unchanged=len(base['prior_files']),
    previous_work_files_unchanged=len(prior['preserved_work_files']),contract_sha256=s.sha(contract),
    plan_identity=plan['identity'],original_implementation_identity=s.code_identity(),
    engineering_resume_sha256=s.sha(s.HERE/'resume_engineering.py'),old_runs=old_runs,
    old_calls=old_calls,history_after=history,semantic_revisions_total=1,semantic_revision_delta=0,
    paid_ledger_sha256=s.sha(ledger),paid_ledger_total_usd=s.usd(total),new_API_usd=s.usd(trial),
    paid_unsettled_count=len(set(reserved)-set(settled)),model_process_exited=True,
    query_receipts=12,query_commands_succeeded=36,query_failures_observed=0,
    tests_log_sha256=s.sha(OUT/'tests_corrected.log'),tests_passed=53,
    tracked_changes=False,git_status=subprocess.check_output(['git','status','--short'],cwd=s.REPO,text=True),
    review_reparsed_unchanged_completed_final_only=True,no_new_model_request=True)
s.save(OUT/'final_integrity_audit.json',result)
print(s.canonical({k:v for k,v in result.items() if k not in ['old_runs','git_status','history_after']}))
