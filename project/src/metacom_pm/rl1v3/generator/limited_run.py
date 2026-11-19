"""Single-job CPU admission and durable supervisor. Model imports live only in worker.
No authorization is created by this module, a plan, or a CPU test.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import math
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from ..io import file_sha256, object_sha256, parse_json, canonical_json
from ..compile.ms_pp1 import check_bundle

PROTOCOL="pmrl1-limited-run-1"
G0E_HEAD="73fdb12f29b6970a268eeda704d73e1bd35b1c3e"
GPU="GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4"
DATA=Path("/opt/tokkio-data0")
class AdmissionError(ValueError): pass
def require(ok, why):
    if not ok: raise AdmissionError(why)
def utc(): return datetime.now(timezone.utc).isoformat()
def write_once(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    raw=(canonical_json(obj)+"\n").encode()
    fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    try:
        with os.fdopen(fd,"wb") as f: f.write(raw);f.flush();os.fsync(f.fileno())
        d=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(d)
        finally: os.close(d)
    except BaseException:
        # A partial record is retained as an unresolved attempt; never erase it.
        raise
    return hashlib.sha256(raw).hexdigest()

class Journal:
    def __init__(self, path):
        self.path=Path(path);self.path.mkdir(parents=True,exist_ok=False)
        self.seq=0;self.prev=None
    def add(self,event,**fields):
        row=dict(seq=self.seq,event=event,utc=utc(),previous_event_sha256=self.prev,**fields)
        self.prev=write_once(self.path/("%03d-%s.json"%(self.seq,event)),row);self.seq+=1
        return self.prev

def read_plan(root,path,executor_binding=None):
    root=Path(root);path=Path(path);plan=parse_json(path.read_text())
    require(plan["protocol"]==PROTOCOL and plan["job_kind"] in {"A0_MIN","PP1"},"unknown job")
    require(plan["authorized"] is False and plan["research_qualified"] is False,"proposal state changed")
    require({plan["requests_path"],plan["baseline_path"],plan["checkpoint_path"]} <= set(plan["files_sha256"]),"unbound plan input")
    require(plan["model_path"]=="/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3","model path")
    require(plan["python"]=="/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python","Python executable")
    for rel,sha in plan["files_sha256"].items():
        p=(root/rel).resolve();require(p.is_relative_to(root.resolve()),"source path escapes root")
        require(file_sha256(p)==sha,"bound file changed: "+rel)
    for rel,sha in plan["executor_files_sha256"].items():
        if executor_binding is None:
            require(file_sha256(root/rel)==sha,"executor source changed: "+rel)
        blob=subprocess.check_output(["git","show",plan["executor_source_head"]+":"+rel],cwd=root)
        require(hashlib.sha256(blob).hexdigest()==sha,"executor commit/file mismatch")
    if executor_binding is not None:
        check_executor_binding(root,plan,executor_binding)
    rows=[parse_json(x) for x in (root/plan["requests_path"]).read_text().splitlines()]
    require([x["request_id"] for x in rows]==plan["ordered_request_ids"],"order/request set changed")
    require(len(rows)==plan["max_calls"]==(16 if plan["job_kind"]=="PP1" else 4),"wrong budget")
    require(len(set(plan["ordered_request_ids"]))==len(rows),"duplicate call IDs")
    baseline=json.loads((root/plan["baseline_path"]).read_text())
    require(plan["baseline_sha256"]==object_sha256(baseline),"baseline hash")
    for row in rows:
        payload=row["model_input"]
        require(set(payload)=={"messages","input_ids","decode"},"payload whitelist")
        require(object_sha256(payload)==row["payload_sha256"],"payload identity")
        require(payload["decode"]==baseline["spec"]["decode"],"decode differs")
        require(payload["messages"][0]=={"role":"system","content":baseline["spec"]["system_prompt"]},"system differs")
        require(len(payload["input_ids"])+320<=16384,"capacity")
        require(object_sha256(payload["input_ids"])==row["input_ids_sha256"],"input IDs hash")
    if plan["job_kind"]=="A0_MIN":
        require(all(rows[i]["model_input"]==rows[i+1]["model_input"] for i in (0,2)),"A0 repeat pairs")
        require(rows[0]["payload_sha256"]!=rows[2]["payload_sha256"],"A0 distinct lengths")
    if plan["job_kind"]=="PP1":
        require(plan["requests_sha256"]=="9af4a17328c3bf730899d3724452a06a7929e63962b7c2ef09319a168722226c","PP1 fixed file")
        check_bundle((root/plan["requests_path"]).parent,root)
    require(file_sha256(root/plan["requests_path"])==plan["requests_sha256"],"request bytes")
    require(plan["max_model_loads"]==1 and plan["warmup_calls"]==0 and plan["automatic_retry"] is False,"extra calls/retries")
    require(plan["global_seconds"]==1200 and plan["load_seconds"]==600 and plan["request_seconds"]==300,"deadline changed")
    return plan,rows,baseline

def check_executor_binding(root,plan,binding):
    require(binding.get("protocol")=="pmrl1-executor-repair-binding-1","executor binding protocol")
    require(binding.get("authorized") is False and binding.get("research_qualified") is False,"binding is not authorization")
    require(binding.get("original_plan_sha256")==object_sha256(plan),"binding original plan SHA")
    require(binding.get("original_executor_source_head")==plan["executor_source_head"],"binding original executor")
    paths=set(plan["executor_files_sha256"]) | {"project/src/metacom_pm/rl1v3/generator/limited_worker_guard.py"}
    require(set(binding.get("executor_files_sha256",{}))==paths,"executor binding file set")
    for rel,sha in binding["executor_files_sha256"].items():
        require(file_sha256(Path(root)/rel)==sha,"executor source changed: "+rel)
        blob=subprocess.check_output(["git","show",binding["executor_source_head"]+":"+rel],cwd=root)
        require(hashlib.sha256(blob).hexdigest()==sha,"repair executor commit/file mismatch")

def authorize(root,plan,auth,executor_binding=None):
    require(auth.get("authorized") is True,"no explicit authorization")
    require(auth.get("job_kind")==plan["job_kind"],"A0/PP1 authorization cannot transfer")
    require(auth.get("plan_sha256")==object_sha256(plan),"authorization plan SHA")
    require(auth.get("executor_binding_sha256")==
            (object_sha256(executor_binding) if executor_binding is not None else None),
            "authorization executor binding SHA")
    require(auth.get("max_calls")==plan["max_calls"],"authorization call budget")
    require(bool(auth.get("researcher")) and bool(auth.get("decision_evidence")),"researcher signature/evidence missing")
    head=subprocess.check_output(["git","rev-parse","HEAD"],cwd=root,text=True).strip()
    require(auth.get("executor_checkout_head")==head,"approval must pin actual checkout HEAD")
    require(not subprocess.check_output(["git","status","--porcelain","--untracked-files=no"],cwd=root,text=True),"dirty tracked checkout")
    decision=auth.get("g0e_identity_decision",{})
    require(decision.get("source_head")==G0E_HEAD and decision.get("signed_by") and decision.get("evidence"),"G0e identity not fixed")
    route=decision.get("route")
    if route=="integrated":
        integrated=decision.get("integration_head","")
        require(subprocess.run(["git","merge-base","--is-ancestor",G0E_HEAD,integrated],cwd=root,capture_output=True).returncode==0,"G0e not in signed integration")
        require(decision.get("integration_owner_acceptance"),"integration owner acceptance missing")
    else: require(route=="researcher_written_limited","unknown G0e identity path")
    require(auth.get("executor_review_evidence"),"final executor acceptance missing")
    if plan["job_kind"]=="PP1":
        require(auth.get("B_request_receipt")=="https://github.com/chensiyu7812/Metacom5_3/pull/19#issuecomment-6985130856","B fixed input receipt")
        require(auth.get("approved_PP1_protocol_sha256")==plan["PP1_protocol_sha256"],"PP1 protocol not approved")
        for key in ("screening_frozen_sha256","QH_frozen_sha256","raters_and_tool_ready_evidence"):
            require(auth.get(key),"PP1 prerequisite: "+key)
        a0=auth.get("A0_receipt",{});p=Path(a0.get("path","/nonexistent"))
        require(p.is_file() and file_sha256(p)==a0.get("file_sha256"),"A0 measured receipt missing")
        d=json.loads(p.read_text())
        require(d.get("job_kind")=="A0_MIN" and d.get("status")=="FINISHED" and d.get("backend")=="hf_real","not a real successful A0")
        require(d.get("baseline_sha256")==plan["baseline_sha256"] and d.get("physical_calls")==4 and d.get("deterministic_pairs_equal") is True,"A0 scope/determinism mismatch")
    return auth

def capacity(paths):
    out={}
    for label,path in paths.items():
        p=Path(path).resolve()
        while not p.exists():p=p.parent
        s=os.statvfs(p);out[label]={"path":str(p),"available_bytes":s.f_bavail*s.f_frsize,"free_inodes":s.f_favail}
    return out

def storage_guard(run_root):
    p=Path(run_root).resolve()
    require(p.is_relative_to(DATA) and p!=DATA,"run root must be inside data volume")
    snap=capacity({"root":"/","data":p})
    require(snap["root"]["available_bytes"]>=1024**3,"root reserve below 1 GiB; owner must resolve, no automatic cleanup")
    require(snap["data"]["available_bytes"]>=4*1024**3 and snap["data"]["free_inodes"]>=1000,"data capacity")
    for name in ("TMPDIR","TMP","TEMP","HF_HOME","HF_HUB_CACHE","TRANSFORMERS_CACHE","XDG_CACHE_HOME","TORCH_HOME","TORCHINDUCTOR_CACHE_DIR","TRITON_CACHE_DIR","CUDA_CACHE_PATH","PYTHONPYCACHEPREFIX"):
        value=os.environ.get(name,"")
        require(value and Path(value).resolve().is_relative_to(p),"redirect "+name+" to run data root")
    require(os.environ.get("PYTHONDONTWRITEBYTECODE")=="1","bytecode disabled")
    return snap

def device_guard(own_pid=None,initial=False):
    r=subprocess.run(["nvidia-smi","--id="+GPU,"--query-gpu=uuid,memory.free","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=10,check=True)
    fields=[x.strip() for x in r.stdout.strip().split(",")]
    require(len(fields)==2 and fields[0]==GPU,"GPU identity")
    free=int(fields[1]);require(free>=(40960 if initial else 4096),"GPU free memory floor")
    r=subprocess.run(["nvidia-smi","--query-compute-apps=gpu_uuid,pid","--format=csv,noheader,nounits"],capture_output=True,text=True,timeout=10,check=True)
    other=[]
    for line in r.stdout.splitlines():
        pair=[x.strip() for x in line.split(",")]
        require(len(pair)==2,"unparseable GPU process census")
        if pair[0]==GPU and int(pair[1])!=own_pid:other.append(int(pair[1]))
    require(not other,"GPU occupied by another process; stop own job only")
    return {"gpu_uuid":GPU,"free_mib":free,"other_pids":other}

def validate_result(row,result):
    require(set(result)>={"token_ids","text","finish_reason","seconds","input_tokens"},"worker result fields")
    ids=result["token_ids"];d=row["model_input"]["decode"]
    require(isinstance(ids,list) and ids and all(type(x)is int and x>=0 for x in ids),"empty/invalid output IDs")
    require(len(ids)<=d["max_new_tokens"] and result["input_tokens"]==len(row["model_input"]["input_ids"]),"output cap/input count")
    require(isinstance(result["text"],str) and result["text"].strip(),"empty output")
    require(type(result["seconds"]) in (int,float) and math.isfinite(result["seconds"]) and result["seconds"]>=0,"invalid timing")
    eos=d["eos_token_id"];eos=[eos] if isinstance(eos,int) else eos
    require(not any(x in eos for x in ids[:-1]),"tokens after first EOS")
    reason="eos" if ids[-1] in eos else "length" if len(ids)==d["max_new_tokens"] else "invalid"
    require(reason==result["finish_reason"] and reason!="invalid","finish reason does not match tokens")
    return reason

def drive(plan,rows,baseline,journal,backend,guard=lambda:None,clock=time.monotonic,started=None):
    started=clock() if started is None else started
    results=[];truncated=[];pending=[r["request_id"] for r in rows];lengths=0;physical=0;status="STOPPED";reason=None
    def remaining(limit):
        left=min(limit,plan["global_seconds"]-(clock()-started))
        require(left>0,"global deadline");return left
    try:
        journal.add("LOAD_START",max_loads=1)
        loaded=backend.load(remaining(plan["load_seconds"]))
        journal.add("LOAD_OK",measurement=loaded)
        for row in rows:
            guard();deadline=remaining(plan["request_seconds"])
            journal.add("REQUEST_START",request_id=row["request_id"],payload_sha256=row["payload_sha256"],physical_ordinal=physical+1)
            physical+=1
            result=backend.generate(row["model_input"],deadline)
            # Save the original returned evidence even if validation fails.
            journal.add("REQUEST_RETURNED",request_id=row["request_id"],output=result)
            finish=validate_result(row,result);results.append(result);pending.pop(0)
            journal.add("REQUEST_VALIDATED",request_id=row["request_id"],finish_reason=finish)
            lengths+=finish=="length"
            if finish=="length":truncated.append(row["request_id"])
            require(clock()-started<plan["global_seconds"],"global deadline")
            if plan["job_kind"]=="A0_MIN":
                require(finish=="eos","A0 truncation: diagnostic incomplete, no extra call")
                if len(results)%2==0:
                    require(results[-1]["token_ids"]==results[-2]["token_ids"],"A0 repeated tokens differ")
            elif lengths>=3:
                raise AdmissionError("third length stop")
        status="FINISHED"
    except BaseException as exc:
        reason=type(exc).__name__+": "+str(exc)
        journal.add("STOP",reason=reason,pending=pending,no_retry=True)
    finally:
        try: backend.close()
        except Exception as exc:
            status="STOPPED";reason=(reason or "")+"; worker close: "+str(exc)
            journal.add("STOP",reason=reason,pending=pending,no_retry=True)
    summary={"job_kind":plan["job_kind"],"status":status,"reason":reason,"backend":backend.kind,
             "plan_sha256":object_sha256(plan),"baseline_sha256":plan["baseline_sha256"],
             "physical_calls":physical,"validated_calls":len(results),"pending":[r["request_id"] for r in rows if r["request_id"] in pending+truncated],
             "unattempted_or_failed_pending":pending,"truncated_pending":truncated,"length_count":lengths,
             "wall_seconds":clock()-started,"deterministic_pairs_equal":plan["job_kind"]=="A0_MIN" and status=="FINISHED",
             "research_qualified":False,"last_journal_sha256":journal.prev}
    write_once(journal.path/"SUMMARY.json",summary)
    return summary

class SubprocessHF:
    kind="hf_real"
    def __init__(self,root,plan,baseline,out,deadline):
        self.root,self.plan,self.baseline,self.out,self.deadline=Path(root),plan,baseline,Path(out),deadline
        self.p=None;self.error=None;self.buffer=b""
        self.global_timer=threading.Timer(max(0,deadline-time.monotonic()),self._kill_own_worker)
        self.global_timer.daemon=True;self.global_timer.start()
    def _kill_own_worker(self):
        if self.p is not None and self.p.poll() is None:
            try:os.killpg(self.p.pid,signal.SIGKILL)
            except ProcessLookupError:pass
    def _exchange(self,command,seconds):
        limit=min(self.deadline,time.monotonic()+seconds)
        def expire():
            if self.p.poll() is None:
                try: os.killpg(self.p.pid,signal.SIGKILL)
                except ProcessLookupError: pass
        timer=threading.Timer(max(0,limit-time.monotonic()),expire)
        timer.daemon=True;timer.start()
        sel=selectors.DefaultSelector()
        try:
            self.p.stdin.write((json.dumps(command)+"\n").encode());self.p.stdin.flush()
            sel.register(self.p.stdout,selectors.EVENT_READ)
            while True:
                require(time.monotonic()<limit,"worker hard deadline")
                device_guard(self.p.pid)
                if b"\n" in self.buffer:
                    line,self.buffer=self.buffer.split(b"\n",1);response=json.loads(line)
                    require(response.get("ok") is True,"worker error: "+str(response.get("error")))
                    return response["result"]
                ready=sel.select(min(1,max(0,limit-time.monotonic())))
                if ready:
                    data=os.read(self.p.stdout.fileno(),65536)
                    require(bool(data),"worker exited without complete response")
                    self.buffer+=data;require(len(self.buffer)<16*1024*1024,"worker response overflow")
        finally:sel.close();timer.cancel()
    def load(self,seconds):
        require(time.monotonic()<self.deadline,"global deadline before load")
        device_guard(initial=True)
        self.error=(self.out/"worker.stderr.log").open("xb")
        env=dict(os.environ,PYTHONPATH=str(self.root/"project/src"),CUDA_VISIBLE_DEVICES=GPU,
                 CUBLAS_WORKSPACE_CONFIG=":4096:8",HF_HUB_OFFLINE="1",TRANSFORMERS_OFFLINE="1",PYTHONNOUSERSITE="1",
                 PMRL1_LIMITED_SUPERVISOR_PID=str(os.getpid()),PMRL1_LIMITED_DEADLINE=str(self.deadline))
        self.p=subprocess.Popen([sys.executable,"-m","metacom_pm.rl1v3.generator.limited_worker_guard",
            self.plan["python"],"-m","metacom_pm.rl1v3.generator.limited_hf_worker"],
            cwd=self.out,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=self.error,env=env,start_new_session=True)
        report=json.loads((self.root/self.plan["checkpoint_path"]).read_text())
        return self._exchange({"operation":"load","model_path":self.plan["model_path"],
            "spec":self.baseline["spec"],"checkpoint":report},seconds)
    def generate(self,payload,seconds):
        return self._exchange({"operation":"generate","payload":payload},seconds)
    def close(self):
        self.global_timer.cancel()
        if self.p is not None:
            # Process group contains only the worker started by this supervisor.
            if self.p.poll() is None:
                try:os.killpg(self.p.pid,signal.SIGTERM)
                except ProcessLookupError:pass
                try:self.p.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    try:os.killpg(self.p.pid,signal.SIGKILL)
                    except ProcessLookupError:pass
                    self.p.wait(timeout=5)
            self.p.stdin.close();self.p.stdout.close()
        if self.error:self.error.close()

def claim_request_set(plan,auth):
    # A different approval or repaired executor cannot resurrect an attempted
    # request set. Conservative whole-set reservation: pending stays pending.
    identity={k:plan[k] for k in ("job_kind","requests_sha256","ordered_request_ids","baseline_sha256")}
    key=object_sha256(identity)
    directory=DATA/"tokkio_projects/pmrl1-validation/limited-g0e-claims"
    for old in directory.glob("*.json"):
        record=parse_json(old.read_text())  # malformed/partial claim also fails closed
        if record.get("plan_sha256")==object_sha256(plan) or record.get("request_set_sha256")==key:
            raise FileExistsError("request set already claimed; unresolved starts cannot retry")
    return write_once(directory/(key+".json"),dict(approval_sha256=object_sha256(auth),
        plan_sha256=object_sha256(plan),request_set_sha256=key,utc=utc(),no_retry=True))

def run(root,plan_path,approval_path,run_root,executor_binding_path=None):
    root=Path(root).resolve()
    binding=parse_json(Path(executor_binding_path).read_text()) if executor_binding_path is not None else None
    plan,rows,baseline=read_plan(root,plan_path,binding) if binding is not None else read_plan(root,plan_path)
    auth=authorize(root,plan,parse_json(Path(approval_path).read_text()),binding) # before device/model access
    run_root=Path(run_root).resolve();storage=storage_guard(run_root)
    run_root.mkdir(parents=True,exist_ok=True)
    # Shared lock at a fixed location, not a caller-chosen directory.
    lock_path=DATA/"tokkio_projects/pmrl1-validation/limited-g0e-exclusive.lock"
    with lock_path.open("a") as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        initial=device_guard(initial=True)
        claim_request_set(plan,auth)
        journal=Journal(run_root/("job-"+object_sha256(auth)))
        started=time.monotonic()
        journal.add("RUN_START",approval=auth,plan_sha256=object_sha256(plan),storage=storage,gpu=initial,
                    executor_binding_sha256=object_sha256(binding) if binding is not None else None)
        # Fresh byte verification, bounded in chunks; never allocate tensor objects.
        try:
            for name,expected in baseline["spec"]["model"]["files"].items():
                p=Path(plan["model_path"])/name;h=hashlib.sha256()
                require(p.stat().st_size==expected["bytes"],"model size: "+name)
                with p.open("rb") as f:
                    for block in iter(lambda:f.read(8*1024*1024),b""):
                        require(time.monotonic()-started<plan["global_seconds"],"hash/global deadline")
                        h.update(block)
                require(h.hexdigest()==expected["sha256"],"model hash: "+name)
            report=json.loads((root/plan["checkpoint_path"]).read_text())
            for path,sha in report["software_files"].items():require(file_sha256(path)==sha,"HF software changed")
            journal.add("MODEL_BYTES_VERIFIED",files=baseline["spec"]["model"]["files"])
        except Exception as exc:
            journal.add("STOP",reason=str(exc),pending=plan["ordered_request_ids"],no_retry=True)
            raise
        backend=SubprocessHF(root,plan,baseline,journal.path,started+plan["global_seconds"])
        return drive(plan,rows,baseline,journal,backend,lambda:(storage_guard(run_root),device_guard(backend.p.pid if backend.p else None)),started=started)

