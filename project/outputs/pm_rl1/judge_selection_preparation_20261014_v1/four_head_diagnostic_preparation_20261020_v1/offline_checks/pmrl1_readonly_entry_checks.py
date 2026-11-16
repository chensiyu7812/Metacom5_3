import hashlib,json,os,runpy,sys,socket
from pathlib import Path
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3');P=R/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/four_head_diagnostic_preparation_20261020_v1'
sys.path.insert(0,str(R/'project/src'))
script=R/'project/scripts/rl1/112_run_four_head_diagnostic.py'
import importlib.util
spec=importlib.util.spec_from_file_location('offline_diagnostic_entry',script);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
p=m.check();ledger=Path(p['financial_baseline']['ledger_path']);before=ledger.read_bytes()
counts={'network':0,'credential':0,'gpu':0}
def net(*a,**k):counts['network']+=1;raise AssertionError('network forbidden')
socket.socket.connect=net
op=Path.open
def readguard(self,*a,**k):
 if str(self)=='/home/tokkio/metacom5_3.env':counts['credential']+=1;raise AssertionError('credential forbidden')
 return op(self,*a,**k)
Path.open=readguard
import torch
def gpu(*a,**k):counts['gpu']+=1;raise AssertionError('GPU forbidden')
torch.cuda._lazy_init=gpu
p=m.check()
a=json.loads((P/'APPROVAL_REQUIRED.json').read_text());errors=[]
for label,fn in [('advance',lambda:m.advance(p,a)),('paid_worker',lambda:m.paid_worker(p,a,None))]:
 try:fn()
 except ValueError as e:errors.append({'entry':label,'rejected':True,'reason':str(e)})
 else:raise AssertionError('pending approval was accepted')
r=m.report(p)
assert r['actual_new_judge_attempts']==0 and r['actual_new_generation_attempts']==0
assert not Path(p['run_dir']).exists()
assert ledger.read_bytes()==before and not any(counts.values())
(P/'report_before_execution.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n')
receipt=dict(protocol_identity=p['identity'],offline_check_passed=True,guard_rejections=errors,
 dependency_touches=counts,run_dir_created=False,ledger_sha256=hashlib.sha256(before).hexdigest(),
 raw_actual_count=225,new_real_requests=0,new_natural_updates=0)
(P/'entry_checks.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(receipt))
