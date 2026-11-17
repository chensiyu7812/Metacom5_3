"""CPU plan validation, exclusive-device guard, and measurement-based estimates.

Importing this module never imports torch/vLLM or opens model weights.
"""
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import subprocess
from ..io import object_sha256, file_sha256

PROTOCOL='pmrl1v3-a0-bounded-probe-1'
GPU_UUID='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4'

def authorize(plan, approval, workload, *, now=None):
    now=now or datetime.now(timezone.utc)
    if approval.get('authorized') is not True or not approval.get('researcher_approval_reference'):
        raise ValueError('separate researcher GPU authorization is required')
    if approval.get('protocol')!=PROTOCOL or approval.get('plan_sha256')!=object_sha256(plan):
        raise ValueError('approval does not bind this plan')
    expiry=datetime.fromisoformat(approval['expires_at'].replace('Z','+00:00'))
    if expiry.tzinfo is None or expiry<=now:raise ValueError('approval expired or lacks timezone')
    if workload not in approval.get('workloads',[]):raise ValueError('workload not authorized')
    if approval.get('gpu_uuid')!=GPU_UUID:raise ValueError('wrong approved GPU')
    return plan['workloads'][workload]

def device_guard(*, own_pid=None, run=subprocess.run):
    def query(args):
        r=run(['nvidia-smi',*args],capture_output=True,text=True,check=True,timeout=15)
        return r.stdout.strip().splitlines()
    rows=query(['--query-gpu=uuid,memory.free','--format=csv,noheader,nounits'])
    found=[int(r.split(',')[1]) for r in rows if r.split(',')[0].strip()==GPU_UUID]
    if len(found)!=1:raise RuntimeError('exclusive A6000 UUID missing')
    apps=query(['--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'])
    other=[r for r in apps if r.split(',')[0].strip()==GPU_UUID and int(r.split(',')[1])!=own_pid]
    if other:raise RuntimeError('another compute process owns A6000; do not preempt or switch device')
    floor=30720 if own_pid is None else 2048
    if found[0]<floor:raise RuntimeError('A6000 free-memory guard failed')
    return dict(gpu_uuid=GPU_UUID,free_mib=found[0],other_compute_processes=0)

def schedule(rows, batches, *, padded_context_cap):
    """Stable input-length ordering; count real rows, no padding/truncating input."""
    result=[]
    for b,limit in batches:
        chosen=sorted(rows,key=lambda r:(len(r['input_ids']),r['request_id']))[:limit]
        group=[]
        for row in chosen:
            if len(row['input_ids'])+row['max_new_tokens']>row['context_limit']:
                raise ValueError('request exceeds complete input+output budget')
            if group and (len(group)==b or (len(group)+1)*max(len(x['input_ids'])+x['max_new_tokens'] for x in [*group,row])>padded_context_cap):
                result.append(group);group=[]
            if len(row['input_ids'])+row['max_new_tokens']>padded_context_cap:raise ValueError('single request exceeds batch budget')
            group.append(row)
        if group:result.append(group)
    return result

def estimate(metrics, *, needcards, g_terminals, j1_calls):
    """Only measured matching workloads; no substitute for unavailable J1 packs."""
    counts={'needcard':needcards,'gemma':g_terminals,'j1':j1_calls};result={}
    for name,n in counts.items():
        m=[x for x in metrics if x.get('workload')==name and x.get('status')=='measured'
           and x.get('actual_requests',0)>0 and x.get('execution_identity')]
        if not m:
            result[name]=dict(requests=n,estimated_seconds=None,reason='no matching actual GPU measurement');continue
        rates=[x['seconds']/x['actual_requests'] for x in m]
        if any(not math.isfinite(x) or x<=0 for x in rates):raise ValueError('invalid measured time')
        result[name]=dict(requests=n,estimated_seconds=None,
            measured_seconds_per_request_range=[min(rates),max(rates)],
            projected_seconds_range=[n*min(rates),n*max(rates)],
            limitation='length/batch-specific extrapolation; excludes model loading, retries and queueing')
    return result
