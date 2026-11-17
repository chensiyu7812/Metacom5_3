"""CPU-only integration receipts; invokes unchanged repository tests/B runners.

Each phase writes a fresh directory and stops on a nonzero exit. Call verify
only after all phases finish; the B runners' zero exit alone is insufficient.
"""
import argparse,subprocess,os,json,time,hashlib,sys,xml.etree.ElementTree as ET
from pathlib import Path
from collections import Counter
P=argparse.ArgumentParser();P.add_argument('--repo',type=Path,required=True);P.add_argument('--out',type=Path,required=True);P.add_argument('--expected-head',required=True);P.add_argument('--phase',choices=['v3','cpu','guards','real','verify'],required=True);args=P.parse_args()
root=args.repo.resolve();project=root/'project';out=args.out.resolve();head=args.expected_head
python='/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python'
def git(*cmd):return subprocess.check_output(['git',*cmd],cwd=root,text=True).strip()
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def put(p,x):
 p.parent.mkdir(parents=True,exist_ok=True)
 with p.open('x') as f:json.dump(x,f,ensure_ascii=False,indent=2);f.write('\n')
def read(p):return json.loads(Path(p).read_text())
def lines(p):return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]
assert git('rev-parse','HEAD')==head
assert git('branch','--show-current')=='pmrl1-v3/integration'
env=dict(os.environ,PYTHONPATH=str(project/'src')+':/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103',CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',TMPDIR=str(out/'tmp'),MPLCONFIGDIR=str(out/'mpl'),XDG_CACHE_HOME=str(out/'cache'))
for key in ('TMPDIR','MPLCONFIGDIR','XDG_CACHE_HOME'):Path(env[key]).mkdir(parents=True,exist_ok=True)
phase=out/('guards_retry' if args.phase=='guards' else args.phase)
if args.phase!='verify':phase.mkdir(parents=True,exist_ok=False)
commands=[]
def run(label,argv):
 assert git('rev-parse','HEAD')==head
 start=time.time();log=phase/(label+'.log')
 with log.open('xb') as f:r=subprocess.run([python,*map(str,argv)],cwd=project,env=env,stdout=f,stderr=subprocess.STDOUT)
 receipt=dict(label=label,command=[python,*map(str,argv)],cwd=str(project),head=head,exit_code=r.returncode,seconds=time.time()-start,log=log.name,log_sha256=sha(log))
 commands.append(receipt);put(phase/(label+'.receipt.json'),receipt)
 print(label,'exit',r.returncode,flush=True)
 if r.returncode:raise SystemExit(r.returncode)
def pytest_files(pattern):return sorted(str(p.relative_to(project)) for p in (project/'tests').glob(pattern))
base=['-m','pytest','-q','-m','not gpu','-ra','-o','addopts=']
if args.phase=='v3':
 run('pytest',base+pytest_files('test_rl1v3_*.py')+['-o','xfail_strict=true','--junitxml='+str(phase/'pytest.xml'),'--basetemp='+str(out/'tmp/v3')])
 run('strict_gate',['scripts/rl1v3/verify_v3_junit.py',phase/'pytest.xml','--out',phase/'gate.json'])
elif args.phase=='cpu':
 run('pytest',base+sum((pytest_files(p) for p in ('test_paper1_*.py','test_rl1_*.py','test_rl1v3_*.py')),[])+['--junitxml='+str(phase/'pytest.xml'),'--basetemp='+str(out/'tmp/cpu')])
elif args.phase=='guards':
 run('gpu_isolation',base+['tests/test_paper1_authority.py::test_ci_never_runs_local_gpu_tests_on_github_cpu_runner','--junitxml='+str(phase/'gpu.xml'),'--basetemp='+str(out/'tmp/guards')])
 run('schemas',['scripts/rl1v3/c0_export_schemas.py','--check','--out',project/'schemas/rl1v3'])
 run('integration_base',['scripts/paper1/00_validate_integration_base.py'])
elif args.phase=='real':
 run('B5',['scripts/rl1v3/B5_real_replay_v2.py','--port','a','--out',phase/'B5','--compare',project/'outputs/pm_rl1/v3/B5/real_replay_v2_aport_02d0a4b1_173bed23/replay_reports.jsonl'])
 run('B1_cross_check',['scripts/rl1v3/B1_A1_cross_check.py','--out',phase/'B1_cross_check'])
 run('B1_preflight',['scripts/rl1v3/B1_needcard_cpu_preflight.py','--out',phase/'B1_preflight'])
else:
 result=dict(head=head,model_calls=0,gpu_used=False,paid_calls=0)
 for phase_name in ('v3','cpu','guards_retry','real'):
  meta=read(out/phase_name/'EXECUTION.json');assert meta['head']==head
  assert all(x['exit_code']==0 for x in meta['commands'])
 guards=list(ET.parse(out/'guards_retry/gpu.xml').getroot().iter('testcase'))
 assert len(guards)==1 and all(guards[0].find(k) is None for k in ('skipped','failure','error'))
 assert (out/'guards_retry/schemas.log').read_text().strip()=='32 schemas checked'
 assert read(out/'guards_retry/integration_base.log')['status']=='PASS'
 gate=read(out/'v3/gate.json');assert gate['passed']==466 and all(gate[x]==0 for x in ('errors','failures','skipped','xfailed'));result['v3']=gate
 for name in ('cpu','v3'):
  cases=list(ET.parse(out/name/'pytest.xml').getroot().iter('testcase'))
  assert not any(c.find('error') is not None or c.find('failure') is not None for c in cases)
  skips=[dict(test=c.attrib.get('classname','')+'::'+c.attrib['name'],reason=c.find('skipped').get('message'),detail=c.find('skipped').text) for c in cases if c.find('skipped') is not None]
  assert all('rl1v3' not in r['test'] for r in skips)
  result[name+'_counts']=dict(tests=len(cases),passed=len(cases)-len(skips),skipped=skips)
 b5=read(out/'real/B5/summary.json');rs=lines(out/'real/B5/replay_reports.jsonl')
 assert b5['a_integrated'] and b5['status']=='formal_on_integration' and b5['code_head']==head
 assert b5['prefixes']==b5['passed']==24 and b5['reachable_distribution']=={'16':21,'8':3}
 assert sum(r['n_reachable'] for r in rs)==360 and sum(r['n_orders'] for r in rs)==1413
 assert b5['capacity_stress']['passed']==b5['capacity_stress']['rejected_read_tested']==24
 assert not b5['failure_kinds'] and b5['terminal_outcomes'].startswith('all pending')
 assert all(r['passed'] and r['replay_identical'] and not r['failures'] for r in rs)
 previous=lines(project/'outputs/pm_rl1/v3/B5/real_replay_v2_aport_02d0a4b1_173bed23/replay_reports.jsonl')
 assert rs==previous,'deterministic B5 prefix reports changed'
 cross=read(out/'real/B1_cross_check/cross_check.json');assert cross['code_head']==head
 assert cross['personal_sessions']==401 and cross['prefixes']==4119 and cross['zero_content_difference']
 assert cross['content_mismatches']==cross['prefix_mismatches']==0 and not cross['coverage_mismatches']
 old=read(project/'outputs/pm_rl1/v3/B1/A1_cross_check_c6ad9b15/cross_check.json')
 strip=lambda x:{k:v for k,v in x.items() if k not in ('wall_seconds','code_head')}
 assert strip(cross)==strip(old)
 need=read(out/'real/B1_preflight/summary.json');assert need['pilots']==need['statuses']['ready']==20 and need['truncated']==need['writer_calls']==0 and need['legality_all_true']
 old=read(project/'outputs/pm_rl1/v3/B1/needcard_cpu_preflight_v2_a1b_catalog/summary.json');assert strip(need)==strip(old)
 assert lines(out/'real/B1_preflight/pilot_inputs.jsonl')==lines(project/'outputs/pm_rl1/v3/B1/needcard_cpu_preflight_v2_a1b_catalog/pilot_inputs.jsonl')
 result.update(B5=dict(passed=24,reachable=360,orders=1413,distribution=b5['reachable_distribution'],terminal_outcomes=b5['terminal_outcomes'],deterministic_reports_equal=True),cross_check=cross,needcard_preflight=need)
 freeze=read(project/'outputs/pm_rl1/v3/integration_c0_freeze_20261117/C0_FREEZE_MANIFEST.json')
 for f in freeze['shared_files']:assert sha(root/f['path'])==f['sha256']
 result['shared_identity']=freeze['shared_identity_sha256']
 assert not git('diff','HEAD','--','project/src','project/tests','project/configs','project/schemas','project/outputs','project/docs')
 put(out/'VALIDATION_RESULTS.json',result);print('ALL_INTEGRATION_LOCAL_CHECKS_PASSED',flush=True)
if args.phase!='verify':
 assert git('rev-parse','HEAD')==head
 put(phase/'EXECUTION.json',dict(head=head,phase=args.phase,commands=commands,env={k:env[k] for k in ('PYTHONPATH','CUDA_VISIBLE_DEVICES','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','TMPDIR','MPLCONFIGDIR','XDG_CACHE_HOME')},runner_sha256=sha(Path(__file__))))
