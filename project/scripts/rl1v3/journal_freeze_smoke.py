"""Freeze a private executable smoke package; never authorizes or runs it."""
import argparse
import json
from pathlib import Path
import shutil
from metacom_pm.rl1v3.io import file_sha256,object_sha256
from metacom_pm.rl1v3.journal.run import PROTOCOL,check


def freeze(stack, requests, a0_plan, output, repo, evidence):
    stack,requests,output,repo=map(Path,(stack,requests,output,repo))
    output.mkdir(parents=True,exist_ok=False)
    executor=output/'executor'
    shutil.copytree(stack/'project/src',executor/'project/src',ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    (executor/'project/scripts/rl1v3').mkdir(parents=True)
    shutil.copy2(repo/'project/scripts/rl1v3/journal_smoke_run.py',executor/'project/scripts/rl1v3/journal_smoke_run.py')
    manifest=json.loads((requests/'REQUEST_MANIFEST.json').read_text())
    impl=executor/'project/src/metacom_pm/rl1v3/journal/renderer.py'
    assert file_sha256(impl)==manifest['renderer_implementation_sha256']
    request_path=output/'SMOKE_REQUESTS.private.jsonl'
    shutil.copy2(requests/'smoke_requests.private.jsonl',request_path)
    baseline_path=output/'G0E_BASELINE.json';shutil.copy2(requests/'G0E_BASELINE.json',baseline_path)
    a0=json.loads(Path(a0_plan).read_text())
    # Resolve against the caller's exact original #23 checkout, never guess another version.
    checkpoint=Path('/opt/tokkio-data0/tokkio_runs/wsb_v321a/wt23')/a0['checkpoint_path']
    assert file_sha256(checkpoint)==a0['files_sha256'][a0['checkpoint_path']]
    checkpoint_path=output/'CHECKPOINT_CPU.json';shutil.copy2(checkpoint,checkpoint_path)
    rows=[json.loads(x) for x in request_path.read_text().splitlines()]
    baseline=json.loads(baseline_path.read_text())
    hashes={str(p.resolve()):file_sha256(p) for p in [request_path,baseline_path,checkpoint_path,requests/'REQUEST_MANIFEST.json',*map(Path,evidence)]}
    executor_hashes={str(p.relative_to(executor)):file_sha256(p) for p in sorted(executor.rglob('*')) if p.is_file()}
    plan=dict(protocol=PROTOCOL,job_kind='JOURNAL_SMOKE',authorized=False,research_qualified=False,
        executor_root=str(executor.resolve()),requests_path=str(request_path.resolve()),requests_sha256=file_sha256(request_path),
        ordered_request_ids=[r['request_id'] for r in rows],baseline_path=str(baseline_path.resolve()),
        baseline_sha256=object_sha256(baseline),checkpoint_path=str(checkpoint_path.resolve()),
        model_path=a0['model_path'],python=a0['python'],max_calls=20,max_model_loads=1,warmup_calls=0,
        automatic_retry=False,global_seconds=1200,load_seconds=600,request_seconds=300,
        renderer_id=manifest['renderer_id'],renderer_implementation_sha256=manifest['renderer_implementation_sha256'],
        files_sha256=hashes,executor_files_sha256=executor_hashes,
        parent_logical_requests=264,parent_unique_calls=258,smoke_included_in_total=True,
        remainder_authorized=False,paid_api_allowed=False,
        stop_rules=['device/disk/hash mismatch: no load','OOM/worker error/timeout: stop own job',
                    'third length termination: stop','no output-based reselection or retry'],
        timing_basis='1200s conservative hard pilot cap, not throughput prediction; A0 blocked before loading')
    plan_path=output/'SMOKE_PLAN.json';plan_path.write_text(json.dumps(plan,indent=2)+'\n')
    auth=dict(protocol=PROTOCOL,job_kind='JOURNAL_SMOKE',authorized=False,plan_sha256=object_sha256(plan),
        max_calls=20,max_model_loads=1,researcher=None,decision_evidence=None)
    (output/'AUTHORIZATION_PENDING.json').write_text(json.dumps(auth,indent=2)+'\n')
    verified,_,_=check(plan_path)
    receipt=dict(status='CPU_CHECK_PASSED',plan_sha256=object_sha256(verified),request_sha256=file_sha256(request_path),
        requests=20,executor_files=len(executor_hashes),model_loads=0,device_access=False,authorized=False)
    (output/'CPU_CHECK.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(receipt,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--stack',required=True);p.add_argument('--requests',required=True);p.add_argument('--a0-plan',required=True);p.add_argument('--output',required=True);p.add_argument('--repo',required=True);p.add_argument('--evidence',action='append',default=[])
    a=p.parse_args();freeze(a.stack,a.requests,a.a0_plan,a.output,a.repo,a.evidence)
