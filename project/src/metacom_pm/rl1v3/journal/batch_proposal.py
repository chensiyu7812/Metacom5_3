"""One outcome-blind continuation proposal; no scheduling or model invocation."""
import copy
import json
from collections import defaultdict
from pathlib import Path
import shutil

from ..io import file_sha256, object_sha256, write_json_once, write_jsonl_once
from .run import BATCH_PROTOCOL, PAIRED_ARMS, check, check_pairing


def jl(path):
    return [json.loads(x) for x in Path(path).read_text().splitlines()]


def prepare(*, requests, smoke, measurements, a0_measurements, repo, out):
    requests,smoke,measurements,a0_measurements,repo,out=map(Path,
        (requests,smoke,measurements,a0_measurements,repo,out))
    out.mkdir(parents=True,exist_ok=False)
    original_plan,done,_=check(smoke/'SMOKE_PLAN.json')
    manifest=json.loads((requests/'REQUEST_MANIFEST.json').read_text())
    for name,sha in manifest['request_files'].items():
        assert file_sha256(requests/name)==sha, 'frozen input changed'
    logical=jl(requests/'requests_logical.private.jsonl')
    unique={r['request_id']:r for r in jl(requests/'requests_unique.private.jsonl')}
    completed={(r['domain'],r['task_id']) for r in done}
    completed_ids={r['request_id'] for r in done}
    groups=defaultdict(list)
    for r in logical:groups[(r['domain'],r['task_id'])].append(r)
    for (domain,_),rows in groups.items():
        assert len(rows)==len(PAIRED_ARMS[domain]) and {r['arm'] for r in rows}==PAIRED_ARMS[domain]
    queues={d:sorted(k for k in groups if k[0]==d and k not in completed) for d in PAIRED_ARMS}
    task_batches=[]
    # Preserve the original per-domain task_id order, never response quality.
    while len(queues['memory'])>=2 and len(queues['rs'])>=2:
        task_batches.append(queues['memory'][:2]+queues['rs'][:2])
        queues['memory']=queues['memory'][2:];queues['rs']=queues['rs'][2:]
    for domain in ('memory','rs'):
        capacity=20//len(PAIRED_ARMS[domain])
        while queues[domain]:
            task_batches.append(queues[domain][:capacity]);queues[domain]=queues[domain][capacity:]
    allocations=[];scheduled=set(completed_ids);first_rows=None;first_logical=None
    for number,keys in enumerate(task_batches,1):
        members=sorted((r for k in keys for r in groups[k]),key=lambda r:(r['domain'],r['task_id'],r['arm']))
        ids=list(dict.fromkeys(r['request_id'] for r in members))
        assert not set(ids)&scheduled, 'cross-batch reuse needs explicit prior-result mapping'
        rows=[dict(unique[key],authorized=False) for key in ids]
        paired=[dict(domain=d,task_id=t) for d,t in sorted(keys)]
        proposal=dict(max_calls=len(rows),logical_requests=len(members),paired_tasks=paired)
        check_pairing(proposal,rows,members,done)
        reused=defaultdict(list)
        for r in members:reused[r['request_id']].append(r['logical_id'])
        allocations.append(dict(batch_number=number,paired_tasks=paired,logical_requests=len(members),
            unique_physical_calls=len(rows),exact_payload_reuse=len(members)-len(rows),
            ordered_request_ids=ids,logical_ids=[r['logical_id'] for r in members],
            reuse_groups=[dict(request_id=k,logical_ids=v) for k,v in reused.items() if len(v)>1],
            input_tokens=sum(len(r['model_input']['input_ids']) for r in rows),authorized=False,
            old_smoke_cardinality_compatible=len(rows)==20,
            status='allocation_only_separate_freeze_and_authorization_required'))
        if number==1:first_rows=rows;first_logical=[dict(r,authorized=False) for r in members]
        scheduled.update(ids)
    assert len(logical)==264 and len(unique)==258 and len(done)==20
    assert len(allocations)==13 and sum(a['logical_requests'] for a in allocations)==244
    assert sum(a['unique_physical_calls'] for a in allocations)==238
    assert sum(a['exact_payload_reuse'] for a in allocations)==6
    assert scheduled==set(unique), 'allocation changed the frozen denominator'
    write_json_once(out/'REMAINING_BATCH_ALLOCATION.json',dict(
        protocol='pmrl1-j-frozen-paired-allocation-v1',authorized=False,
        selection='per-domain frozen task_id lexical order; first two remaining Memory and first two remaining RS; no output access',
        completed_tasks=[dict(domain=d,task_id=t) for d,t in sorted(completed)],
        remaining_logical=244,remaining_unique=238,exact_payload_reuses=6,batches=allocations))
    write_jsonl_once(out/'REQUESTS.private.jsonl',first_rows)
    write_jsonl_once(out/'LOGICAL_REQUESTS.private.jsonl',first_logical)
    # Timing measurements are consumed only after all task selection is fixed.
    measured=json.loads(measurements.read_text());a0=json.loads(a0_measurements.read_text())
    assert measured['physical_calls']==20 and measured['returned']==20
    assert {(p['domain'],p['task_id']) for p in measured['pairs']}==completed
    for name,sha in measured['source_files_sha256'].items():assert file_sha256(name)==sha
    n=len(first_rows);inputs=[len(r['model_input']['input_ids']) for r in first_rows]
    overhead=measured['total_wall_seconds']-measured['total_generation_seconds']
    multiplier=max(1,n*320/measured['total_output_tokens'],sum(inputs)/measured['total_input_tokens'])
    smoke_proxy=2*(overhead+measured['total_generation_seconds']*multiplier)
    a0rate=min(c['tokens_per_second'] for c in a0['calls'][1:])
    a0overhead=a0['total_wall_seconds']-sum(c['seconds'] for c in a0['calls'])
    a0_proxy=1.25*(a0overhead+n*320/a0rate+10*n)
    feasibility=dict(protocol='pmrl1-j-next-batch-timing-v1',authorized=False,
        measured_20=dict(wall_seconds=measured['total_wall_seconds'],load_seconds=measured['model_load']['seconds'],
            input_tokens=measured['total_input_tokens'],output_tokens=measured['total_output_tokens'],
            generation_seconds=measured['total_generation_seconds']),
        next=dict(logical=len(first_logical),physical=n,input_tokens_total=sum(inputs),
            input_tokens_min=min(inputs),input_tokens_max=max(inputs),output_tokens_cap=n*320),
        assumptions=['20-smoke proxy scales generation by the larger input or full-output-cap token ratio, then doubles total time.',
            'A0 proxy uses slowest post-first-call token rate, 10 s extra prefill per request, and 25% margin.',
            'Both are scenario estimates, not fitted throughput predictions or guarantees; prefill/output interactions and GPU contention may differ.'],
        smoke_proxy_seconds=smoke_proxy,a0_proxy_seconds=a0_proxy,
        conservative_scenario_seconds=max(smoke_proxy,a0_proxy),hard_seconds=1200,
        load_seconds=600,request_seconds=300,automatic_retry=False,
        stop_rules_unchanged=original_plan['stop_rules'],
        source_measurements_sha256=file_sha256(measurements),a0_measurements_sha256=file_sha256(a0_measurements))
    write_json_once(out/'FEASIBILITY.json',feasibility)
    executor=out/'executor';shutil.copytree(original_plan['executor_root'],executor)
    admission='project/src/metacom_pm/rl1v3/journal/run.py'
    shutil.copy2(repo/admission,executor/admission)
    executor_hashes={name:file_sha256(executor/name) for name in original_plan['executor_files_sha256']}
    changes=[name for name,sha in executor_hashes.items() if sha!=original_plan['executor_files_sha256'][name]]
    assert changes==[admission], 'only admission may differ from original frozen executor'
    plan=copy.deepcopy(original_plan)
    plan.update(protocol=BATCH_PROTOCOL,job_kind='JOURNAL_PAIRED_BATCH',authorized=False,
        executor_root=str(executor.resolve()),executor_files_sha256=executor_hashes,
        requests_path=str((out/'REQUESTS.private.jsonl').resolve()),
        requests_sha256=file_sha256(out/'REQUESTS.private.jsonl'),
        ordered_request_ids=[r['request_id'] for r in first_rows],
        max_calls=n,logical_requests=len(first_logical),paired_tasks=allocations[0]['paired_tasks'],
        logical_requests_path=str((out/'LOGICAL_REQUESTS.private.jsonl').resolve()),
        prior_requests_path=str((smoke/'SMOKE_REQUESTS.private.jsonl').resolve()),
        continuation_of_plan_sha256=object_sha256(original_plan),batch_number=1,
        remainder_authorized=False,timing_basis='FEASIBILITY.json uses actual A0 and 20-smoke; 1200 s remains a hard cap, no completion guarantee.')
    bound=[out/'REQUESTS.private.jsonl',out/'LOGICAL_REQUESTS.private.jsonl',
        out/'REMAINING_BATCH_ALLOCATION.json',out/'FEASIBILITY.json',smoke/'SMOKE_PLAN.json',
        requests/'requests_logical.private.jsonl',requests/'requests_unique.private.jsonl',measurements,a0_measurements]
    plan['files_sha256'].update({str(p.resolve()):file_sha256(p) for p in bound})
    write_json_once(out/'BATCH_PLAN.json',plan)
    verified,rows,_=check(out/'BATCH_PLAN.json')
    write_json_once(out/'AUTHORIZATION_PENDING.json',dict(protocol=BATCH_PROTOCOL,
        job_kind='JOURNAL_PAIRED_BATCH',authorized=False,plan_sha256=object_sha256(plan),
        max_calls=n,max_model_loads=1,researcher=None,decision_evidence=None))
    report=dict(status='CPU_CHECK_PASSED',authorized=False,plan_sha256=object_sha256(verified),
        plan_file_sha256=file_sha256(out/'BATCH_PLAN.json'),requests_sha256=plan['requests_sha256'],
        logical_requests=len(first_logical),unique_calls=len(rows),reuse=len(first_logical)-len(rows),
        changed_executor_files=changes,old_executor_unchanged=True,model_loads=0,device_access=False,
        next_input_tokens=dict(total=sum(inputs),minimum=min(inputs),maximum=max(inputs)),
        remaining_logical=244,remaining_unique=238,allocation_batches=len(allocations),
        hard_seconds=1200,conservative_scenario_seconds=max(smoke_proxy,a0_proxy))
    # Recheck the old plan after copying: no mutation of its executor or evidence.
    check(smoke/'SMOKE_PLAN.json')
    write_json_once(out/'CPU_CHECK.json',report)
    writer=out.parent/'representations/writer8-v1/WRITER8_REQUEST.json'
    if writer.exists():
        write_json_once(out/'WRITER8_TIMING_UPDATE.json',dict(
            frozen_writer_request_sha256=file_sha256(writer),authorized=False,
            superseded_note='A0 throughput unavailable',actual_measurements_available=True,
            A0_wall_seconds=a0['total_wall_seconds'],smoke20_wall_seconds=measured['total_wall_seconds'],
            hard_seconds=1200,calls=8,executor_admission='still requires a separate Writer binding; not executable by this paired-batch admission',
            scope='Timing note only; original frozen Writer v1 is unchanged.'))
    return report
