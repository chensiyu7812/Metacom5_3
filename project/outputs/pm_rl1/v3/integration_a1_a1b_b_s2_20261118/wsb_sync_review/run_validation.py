from pathlib import Path
import glob,json,os,subprocess,sys,time
root=Path('/home/tokkio/Metacom5_3-ws-b');out=Path(__file__).resolve().parent
python='/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python'
expected='59607355b3751c87138b129a079eeb571152b7ce'
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==expected
assert not subprocess.check_output(['git','status','--porcelain=v1'],cwd=root,text=True).strip()
env=dict(os.environ,CUDA_VISIBLE_DEVICES='',HF_HUB_OFFLINE='1',TRANSFORMERS_OFFLINE='1',PYTHONDONTWRITEBYTECODE='1',PYTHONPATH='project/src:/opt/tokkio-data0/tokkio_envs/pmrl1_validation_vendor_20261103')
tests=sorted(str(p.relative_to(root)) for p in (root/'project/tests').glob('test_rl1v3_*.py'))
stages=[('v3',[python,'-m','pytest','-q','-m','not gpu',*tests,'-ra','-o','addopts=','-o','xfail_strict=true','--basetemp='+str(out/'pytest-tmp'),'--junitxml='+str(out/'v3.xml')]),
('v3_gate',[python,'project/scripts/rl1v3/verify_v3_junit.py',str(out/'v3.xml'),'--out',str(out/'v3_gate.json')]),
('schemas',[python,'project/scripts/rl1v3/c0_export_schemas.py','--check']),
('source_cross_check',[python,'project/scripts/rl1v3/B1_A1_cross_check.py','--out',str(out/'source_cross_check')]),
('needcard_preflight',[python,'project/scripts/rl1v3/B1_needcard_cpu_preflight.py','--out',str(out/'needcard_preflight')]),
('bank_replay',[python,'project/scripts/rl1v3/B5_real_replay_v2.py','--port','a','--out',str(out/'bank_replay'),'--compare','project/outputs/pm_rl1/v3/B5/real_replay_v2_aport_02d0a4b1_173bed23/replay_reports.jsonl'])]
for name,cmd in stages:
    print('STAGE '+name,flush=True);t=time.time()
    with (out/(name+'.log')).open('x') as log:
        p=subprocess.Popen(cmd,cwd=root,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
        for line in p.stdout:log.write(line);log.flush();print(line,end='',flush=True)
        code=p.wait()
    record=dict(stage=name,command=cmd,cwd=str(root),code_sha=expected,exit_code=code,seconds=time.time()-t,environment={k:env[k] for k in ('CUDA_VISIBLE_DEVICES','HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE','PYTHONPATH','PYTHONDONTWRITEBYTECODE')})
    (out/(name+'.execution.json')).write_text(json.dumps(record,indent=2)+'\n')
    if code:raise SystemExit(code)
    if name=='source_cross_check':
        r=json.loads((out/'source_cross_check/cross_check.json').read_text());assert r['zero_content_difference']
    if name=='needcard_preflight':
        r=json.loads((out/'needcard_preflight/summary.json').read_text());print('NEEDCARD_SUMMARY_KEYS',list(r),flush=True)
    if name=='bank_replay':
        r=json.loads((out/'bank_replay/summary.json').read_text());assert r['prefixes']==24 and r['passed']==24
print('ALL_SYNC_VALIDATION_STAGES_PASSED',flush=True)
