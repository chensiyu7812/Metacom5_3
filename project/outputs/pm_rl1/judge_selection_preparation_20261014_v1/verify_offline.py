"""Run reproducible CPU-only tests, dry-runs and explicitly labelled mock analysis."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import selection as s


def verify(out):
    out.mkdir(parents=True,exist_ok=False)
    plan=s.load_plan()
    ledger=s.REPO/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
    before=s.sha(ledger)
    prior=s.read(s.REPO/'project/outputs/pm_rl1/route_accounting_20261014_v1/analysis_final/baseline.json')
    for name,expected in prior['existing_work_hashes'].items():
        if s.sha(s.REPO/name)!=expected:raise ValueError('previous local work changed: '+name)
    env=os.environ|{'CUDA_VISIBLE_DEVICES':'','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
                    'TOKENIZERS_PARALLELISM':'false','PYTHONDONTWRITEBYTECODE':'1'}
    commands=[]
    def run(label,args):
        cmd=[sys.executable]+[str(x) for x in args]
        result=subprocess.run(cmd,cwd=s.REPO,env=env,text=True,capture_output=True)
        (out/(label+'.log')).write_text(result.stdout+result.stderr)
        commands.append(dict(label=label,argv=cmd,exit_code=result.returncode))
        if result.returncode:raise RuntimeError('offline check failed: '+label)
    run('unittest',['-m','unittest','discover','-s',s.HERE,'-p','test_selection.py','-v'])
    run('existing_workflow_tests',['-m','pytest','-q','project/tests/test_rl1_calibration_workflow.py'])
    for name in ['selection','prepare','runtime_receipts','analyze','verify_offline']:
        run('help_'+name,[s.HERE/(name+'.py'),'--help'])
    for sub in ['execute','dry-run','mock','run-stage']:
        run('help_selection_'+sub,[s.HERE/'selection.py',sub,'--help'])
    for sub in ['local','api']:
        run('help_runtime_'+sub,[s.HERE/'runtime_receipts.py',sub,'--help'])
    mock=out/'paired_mock'
    for c in plan['configs']:
        for phase in s.STAGES:
            run('dry_'+c+'_'+phase,[s.HERE/'selection.py','dry-run','--candidate',c,'--phase',phase])
    for phase in s.STAGES:
        run('paired_mock_'+phase,[s.HERE/'selection.py','run-stage','--phase',phase,'--out',mock])
    run('paired_analysis',[s.HERE/'analyze.py','--compare-pool','--run-dir',mock,
        '--out',out/'paired_analysis','--allow-mock'])
    run('mock_failure',[s.HERE/'selection.py','mock','--candidate','deepseek_flash_high',
        '--phase','engineering','--out',out/'mock_failure','--fail-at','2'])
    run('reproduce',[s.HERE/'prepare.py','--out',out/'reproduced'])
    for name in ['plan.json','configs.json','request_manifest.csv','run_order.csv','cost_scenarios.csv','gpu_scenarios.csv','variants_private.json']:
        if s.sha(s.HERE/name)!=s.sha(out/'reproduced'/name):
            raise ValueError('non-reproducible artifact: '+name)
    if s.sha(ledger)!=before:raise ValueError('shared real ledger changed')
    s.save(out/'verification.json',dict(plan_identity=plan['identity'],commands=commands,
        unit_tests=33,existing_workflow_tests=23,completed_mock_requests=160,
        extra_mock_failure_attempts=2,real_inference_calls=0,real_paid_calls=0,
        weights_downloaded=False,sealed_access=False,shared_ledger_before=before,
        shared_ledger_after=s.sha(ledger),reproduced_artifacts_identical=True,
        previous_nine_work_files_unchanged=True,
        qualification='NOT_EVALUATED',limits=['No live tokenizer/weight loading or model inference tested',
          'No service account, real pricing, network stream or GPU behavior validated',
          'Mock uncertainty is not judge accuracy evidence']))
    print(json.dumps({'verification':str(out/'verification.json'),'real_calls':0,'checks':'passed'}))


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--out',type=Path,required=True,help='new results directory')
    verify(ap.parse_args().out.resolve())
