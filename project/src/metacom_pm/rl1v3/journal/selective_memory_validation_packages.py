"""Freeze exactly two unapproved selective Memory jobs from real prepared inputs."""
import ast,json,shutil
from pathlib import Path
from ..io import file_sha256,object_sha256,write_json_once,write_jsonl_once
from . import selective_memory_validation_run as R
from . import joint_run


def prepare(*,base_plan,bundle,requests,read_checks,measurements,repo,out,evaluation_preparation=None):
    base_plan,bundle,requests,read_checks,measurements,repo,out=map(Path,
        (base_plan,bundle,requests,read_checks,measurements,repo,out))
    base,_,_=joint_run.check(base_plan)
    tasks=R.jl(bundle/'TASKS.runtime.jsonl');all_rows=R.jl(requests)
    task_ids=[r['task_id'] for r in tasks]
    if len(tasks)!=15 or len(set(task_ids))!=15:raise ValueError('exact frozen 15 task scope')
    if len(all_rows)!=30 or len({r['request_id'] for r in all_rows})!=30:raise ValueError('exact 30 distinct payloads')
    if list(dict.fromkeys(r['task_id'] for r in all_rows))!=task_ids:raise ValueError('task/runtime order mismatch')
    out.mkdir(parents=True,exist_ok=False);executor=out/'executor'
    shutil.copytree(base['executor_root'],executor,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    new_names=('project/src/metacom_pm/rl1v3/journal/selective_memory_validation_run.py',
        'project/scripts/rl1v3/journal_selective_memory_validation_run.py')
    for name in new_names:shutil.copy2(repo/name,executor/name)
    inventory=dict(base['executor_files_sha256'],**{name:file_sha256(executor/name) for name in new_names})
    # Byte-identical old worker/guards/driver are all retained in the inventory.
    for name,sha in base['executor_files_sha256'].items():
        if file_sha256(executor/name)!=sha:raise ValueError('old frozen executor copy differs')
    original_tree=ast.parse(Path(joint_run.__file__).read_text());new_tree=ast.parse(Path(R.__file__).read_text())
    find=lambda t:next(x for x in t.body if isinstance(x,ast.FunctionDef) and x.name=='run')
    if ast.dump(find(original_tree))!=ast.dump(find(new_tree)):raise ValueError('bounded run implementation differs')
    frozen=out/'REQUESTS_ALL.private.jsonl';shutil.copy2(requests,frozen)
    bound={str(p):file_sha256(p) for p in sorted(bundle.rglob('*')) if p.is_file()}
    # Bind the actual readings, complete legal pools, immutable ledgers and CPU receipt.
    bound.update({str(p):file_sha256(p) for p in sorted(requests.parent.rglob('*')) if p.is_file()})
    for name in ('TOP4_SELECTION_FREEZE_PRIVATE.json','POLICY_FREEZE_PRIVATE.json','SOURCE_ACCESS_RECEIPT_PRIVATE.json'):
        p=bundle.parent/name
        if not p.is_file():raise ValueError('missing fixed retrieval/policy/source receipt: '+name)
        bound[str(p)]=file_sha256(p)
    for name in ('EVALUATION_REPAIR_PROOF_PRIVATE.json','archive-review-v1/MANIFEST.json'):
        p=bundle.parent/name
        if p.is_file():bound[str(p)]=file_sha256(p)
    for p in sorted((repo/'project/src/metacom_pm/rl1v3/journal').glob('selective_memory_validation*.py')):
        bound[str(p)]=file_sha256(p)
    if evaluation_preparation is not None:
        directory=Path(evaluation_preparation)
        files=[p for p in sorted(directory.rglob('*')) if p.is_file()]
        if not files:raise ValueError('evaluation preparation directory is empty')
        bound.update({str(p):file_sha256(p) for p in files})
    for path in (requests,read_checks,measurements,base_plan,Path(base['baseline_path']),Path(base['checkpoint_path']),frozen):
        bound[str(path)]=file_sha256(path)
    observed=json.loads(measurements.read_text())
    measured_rate=observed['total_output_tokens']/observed['total_generation_seconds']
    if observed['physical_calls']!=20:raise ValueError('expected original 20-call throughput reference')
    measured_requests=[Path(p) for p in observed['source_files_sha256'] if p.endswith('SMOKE_REQUESTS.private.jsonl')]
    if len(measured_requests)!=1:raise ValueError('missing measured request context range')
    reference=measured_requests[0]
    if file_sha256(reference)!=observed['source_files_sha256'][str(reference)]:raise ValueError('measured request identity')
    measured_max=max(len(r['model_input']['input_ids']) for r in R.jl(reference))
    bound[str(reference)]=file_sha256(reference)
    catalog=[]
    for n,selected in ((1,task_ids[:8]),(2,task_ids[8:])):
        batch=out/f'batch-{n:02d}';batch.mkdir();rows=[r for r in all_rows if r['task_id'] in selected]
        logical=batch/'LOGICAL.private.jsonl';physical=batch/'REQUESTS.private.jsonl'
        write_jsonl_once(logical,rows);write_jsonl_once(physical,rows)
        projected=len(rows)*320/10+100
        feasibility=dict(calls=len(rows),input_tokens=sum(r['input_tokens'] for r in rows),
            min_input_tokens=min(r['input_tokens'] for r in rows),max_input_tokens=max(r['input_tokens'] for r in rows),
            output_token_cap=len(rows)*320,observed20_tokens_per_second=measured_rate,
            planning_tokens_per_second=10,setup_hash_load_seconds=100,projected_seconds=projected,
            global_hard_seconds=1200,completion_guaranteed=False,unconstrained_original_G=True,
            measured20_max_input_tokens=measured_max,
            input_context_exceeds_throughput_reference=max(r['input_tokens'] for r in rows)>measured_max,
            measured_reference_sha256=file_sha256(measurements))
        fp=batch/'FEASIBILITY.json';write_json_once(fp,feasibility)
        plan=dict(protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,authorized=False,remaining_batches_authorized=False,
            automatic_retry=False,max_model_loads=1,warmup_calls=0,global_seconds=1200,load_seconds=600,request_seconds=300,
            python=base['python'],model_path=base['model_path'],baseline_path=base['baseline_path'],baseline_sha256=base['baseline_sha256'],
            checkpoint_path=base['checkpoint_path'],executor_root=str(executor),executor_files_sha256=inventory,
            batch_number=n,task_ids=selected,logical_requests=len(rows),max_calls=len(rows),
            requests_path=str(physical),requests_sha256=file_sha256(physical),logical_requests_path=str(logical),
            frozen_requests_path=str(frozen),ordered_request_ids=[r['request_id'] for r in rows],
            task_manifest_path=str(bundle/'TASKS.runtime.jsonl'),task_manifest_sha256=file_sha256(bundle/'TASKS.runtime.jsonl'),
            review_path=str(bundle/'EVALSPEC.private.jsonl'),review_sha256=file_sha256(bundle/'EVALSPEC.private.jsonl'),
            read_checks_path=str(read_checks),renderer_id=base['renderer_id'],paid_api_allowed=False,research_qualified=False,
            stop_rules=base['stop_rules'],files_sha256=dict(bound,**{str(p):file_sha256(p) for p in (logical,physical,fp)}))
        plan_path=batch/'PLAN.json';write_json_once(plan_path,plan);R.check(plan_path)
        write_json_once(batch/'APPROVAL_TEMPLATE.json',dict(protocol=R.RUN_PROTOCOL,job_kind=R.JOB_KIND,
            authorized=False,plan_sha256=object_sha256(plan),max_calls=len(rows),max_model_loads=1,researcher='',decision_evidence=''))
        catalog.append(dict(batch=n,task_ids=selected,logical=len(rows),physical=len(rows),authorized=False,
            plan_path=str(plan_path),plan_sha256=object_sha256(plan),plan_file_sha256=file_sha256(plan_path),
            requests_sha256=file_sha256(physical),input_tokens=feasibility['input_tokens'],
            min_input_tokens=feasibility['min_input_tokens'],max_input_tokens=feasibility['max_input_tokens'],
            projected_seconds=projected,hard_seconds=1200))
    result=dict(protocol='selective-memory-validation-catalog-v1',calls=30,tasks=15,batches=catalog,
        authorized=False,model_loads_requested=2,gpu_calls_executed=0,old_bounded_run_ast_identical=True,
        executor_inventory_object_sha256=object_sha256(inventory),frozen_requests_sha256=file_sha256(frozen))
    write_json_once(out/'CATALOG.json',result);return result
