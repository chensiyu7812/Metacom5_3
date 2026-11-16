from pathlib import Path
import sys,subprocess
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent))
import selection as s
import continue_v1 as c
import outer_format_v1 as interface
from resume_engineering import now,slots

plan=s.load_plan();p=s.read(HERE/'protocol.json');assert p==c.protocol(plan)
baseline=s.read(HERE/'baseline.json');root=s.HERE/'live_runs';history=c.reconstruct(plan,p,root)
for rel,h in baseline['preserved_files'].items():assert s.sha(s.HERE/rel)==h,rel
for name,old in plan['configs'].items():
    new=p['configs'][name];assert old['identity']!=new['identity']
    for k,v in old.items():
        if k!='identity':assert new[k]==v
    assert new['output_interface']==p['interface']
oldmap={r['request_id']:r for r in slots(plan)}
assert set(history['slot_owners'])<=set(oldmap) and history['started_or_evidenced']<=8
assert history['per_configuration'][s.CANDIDATES[2]]==history['per_configuration'][s.CANDIDATES[3]]==0
bindings=[]
for req in p['requests']:
    orig=oldmap[req['original_slot_request_id']];folder=root/c.SUBDIR/req['candidate'];rid=req['request_id']
    result=folder/(rid+'.result.json')
    if not result.exists():continue
    row=s.read(result);assert row['original_request']==orig and row['request']==req
    messages,schema=s.payload(plan,orig)
    assert s.digest(messages)==req['messages_identity'] and s.digest(schema)==req['schema_identity']
    response=folder/(rid+'.response.json')
    if response.exists():
        raw=s.read(response);assert raw['request_identity']==rid
        assert interface.evaluate(plan,orig,raw,req['configuration_identity'],rid)==row['evaluation']
        assert raw['native_thinking']==p['configs'][req['candidate']]['enable_thinking']
        saved=s.read(folder/(rid+'.raw.json'));assert saved['raw_text']==raw['raw_text']
        label=p['configs'][req['candidate']]['label'];readiness=s.read(s.HERE/'local_engineering_20261015'/('gemma_'+label+'_readiness.json'))
        assert raw['input_tokens']==readiness['request_input_tokens'][orig['request_id']]
        tokens=raw['token_accounting'];assert tokens['total_output']==sum(tokens[k] for k in ['thinking','final','format'])
        review=root/c.SUBDIR/'stage'/(rid+'.review.json')
        if row['evaluation']['measurement']['measurement_status'] in s.VALID:
            assert review.exists();c.review_valid(s.read(review),plan,orig,rid,response)
        bindings.append(dict(original_slot=orig['request_id'],request_id=rid,result_sha256=s.sha(result),response_sha256=s.sha(response),
            final_sha256=interface.text_hash(raw['native_parsed']['content']),natural_eos=raw['natural_eos'],input_tokens=raw['input_tokens']))
for orig in slots(plan)[:2]:
    old=root/orig['candidate']/orig['request_id'];m=s.read(old.with_suffix('.result.json'))['measurement']
    assert all(m[k] is None for k in ('q','m','candidate_utility')) and m['measurement_status']=='parse_or_evidence_failure'
    d=s.read(HERE/'derived'/(orig['request_id']+'.derived.json'))
    assert d['evaluation']==interface.evaluate(plan,orig,s.read(old.with_suffix('.response.json')),d['new_configuration_identity'],d['derived_id'])
    assert d['new_physical_calls']==d['new_independent_samples']==0
    for f,h in d['original_hashes'].items():assert s.sha(f)==h
    assert not (root/c.SUBDIR/orig['candidate']/next(x['request_id'] for x in p['requests'] if x['original_slot_request_id']==orig['request_id'])).with_suffix('.started.json').exists()
ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl';assert s.sha(ledger)==baseline['paid_ledger_sha256']
b=s.Budget(ledger,trial=plan['identity'],trial_cap=0,shared_cap=s.nanodollars(20),baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('0.03079930'))
total,trial,reserved,settled=b._totals(b.events());assert total==s.nanodollars('1.50724291') and trial==0 and not (set(reserved)-set(settled))
head=subprocess.check_output(['git','rev-parse','HEAD'],cwd=s.REPO,text=True).strip();assert head==baseline['head']
branch=subprocess.check_output(['git','branch','--show-current'],cwd=s.REPO,text=True).strip();assert branch==baseline['branch']
assert not subprocess.check_output(['git','diff','--name-only'],cwd=s.REPO,text=True)
assert not subprocess.check_output(['git','diff','--cached','--name-only'],cwd=s.REPO,text=True)
process=s.read(HERE/'own_process.json');assert not Path('/proc/'+str(process['pid'])).exists()
receipt=s.read(HERE/'process_receipt.json');assert receipt['exit_code']==0
queries=[s.read(f) for f in (root/c.SUBDIR/'stage').glob('gpu_check_*.json')]
audit=dict(time_jst=now(),head=head,branch=branch,protocol_identity=p['identity'],interface_identity=p['interface']['identity'],
    old_files_hash_verified=len(baseline['preserved_files']),new_live_bindings=bindings,history=history,
    previous_strict_failures_and_nulls_unchanged=True,derived_not_new_calls=True,new_dev02B_starts=0,
    full_input_tokens_match=True,original_generation_settings_identical=True,all_four_use_same_interface=True,
    paid_ledger_sha256=s.sha(ledger),paid_total_usd=s.usd(total),new_API_usd=s.usd(trial),unsettled=0,
    semantic_revision_delta=0,total_semantic_revisions=1,tests_passed=76,tests_log_sha256=s.sha(HERE/'tests_v1_corrected.log'),
    GPU_queries=len(queries),GPU_query_commands=len(queries)*3,query_command_failures=sum(q['returncode']!=0 or bool(q['error']) for r in queries for q in r['queries']),
    own_model_process_exited=True,process_receipt=receipt,
    git_status=subprocess.check_output(['git','status','--short'],cwd=s.REPO,text=True),new_stage_or_paid_call=False)
s.save(HERE/'final_integrity_audit.json',audit)
print(s.canonical({k:v for k,v in audit.items() if k not in ['new_live_bindings','git_status','history']}))
