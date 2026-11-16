"""Engineering-only continuation of the existing AB stage, never a new experiment.

Original selection/adapters/plan/request identities remain immutable. This module
adds auditable GPU diagnostics and continuation orchestration; no score changes.
"""
import argparse
import csv
import datetime
import fcntl
import hashlib
import importlib.metadata as md
import io
import os
from pathlib import Path
import subprocess
import sys
import time
import xml.etree.ElementTree as ET
import selection as s

UUID = 'GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4'
CANDIDATES = s.CANDIDATES[:2]

def now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=9))).isoformat()

def parse_gpu(gpu, compute, xml, expected_uuid=UUID, own_pid=None):
    reasons=[];selected=None;visible=[];visibility='unknown'
    try:
        rows=list(csv.reader(io.StringIO(gpu)))
        matches=[r for r in rows if r and r[0].strip()==expected_uuid]
        if len(matches)!=1:raise ValueError('designated UUID missing or duplicated')
        r=[x.strip() for x in matches[0]]
        if len(r)!=4:raise ValueError('GPU CSV field count')
        selected=dict(uuid=r[0],name=r[1],free_mib=int(r[2]),utilization_percent=int(r[3]))
        if selected['free_mib']<0 or not 0<=selected['utilization_percent']<=100:raise ValueError('GPU value range')
        if 'A6000' not in r[1]:reasons.append('designated_uuid_product_mismatch')
    except (ValueError,TypeError) as exc:reasons.append('gpu_query_parse_error: '+str(exc))
    try:
        doc=ET.fromstring(xml)
        matches=[g for g in doc.findall('gpu') if g.findtext('uuid')==expected_uuid]
        if len(matches)!=1:raise ValueError('XML designated UUID missing or duplicated')
        g=matches[0];processes=g.find('processes')
        if processes is None or (processes.text or '').strip() not in ('','None'):
            raise ValueError('XML processes unavailable')
        for p in processes.findall('process_info'):
            pid=int(p.findtext('pid'));name=p.findtext('process_name');kind=p.findtext('type')
            if pid<=0 or not name or name in ('N/A','[Not Found]') or not kind:
                raise ValueError('process metadata unavailable')
            visible.append(dict(pid=pid,name=name,type=kind,source='nvidia-smi XML'))
        csv_pids=[]
        for row in csv.reader(io.StringIO(compute)):
            if not row:continue
            if len(row)!=4:raise ValueError('compute CSV field count')
            if row[0].strip()!=expected_uuid:raise ValueError('compute query UUID mismatch')
            pid=int(row[1].strip());name=row[2].strip()
            if pid<=0 or not name or name in ('N/A','[Not Found]'):raise ValueError('compute process metadata unavailable')
            csv_pids.append(pid)
            if not any(p['pid']==pid for p in visible):
                visible.append(dict(pid=pid,name=name,type='C',source='nvidia-smi compute CSV'))
        visibility='queries_succeeded_visible_processes' if visible else 'queries_succeeded_no_processes_listed'
        if any(p['pid']!=own_pid for p in visible):reasons.append('other_visible_gpu_process')
    except (ValueError,TypeError,ET.ParseError) as exc:reasons.append('process_visibility_unknown: '+str(exc))
    if selected is not None and own_pid is None:
        if selected['free_mib']<45000:reasons.append('free_memory_below_45000_MiB')
        if selected['utilization_percent']!=0:reasons.append('utilization_not_zero')
    return dict(selected_gpu=selected,visible_processes=visible,process_visibility=visibility,
        visibility_limit='Successful empty process lists describe what these NVIDIA queries expose; they do not prove absence of hidden, transient or future jobs.',
        rejection_reasons=reasons,eligible=not reasons,
        guard='original free>=45000MiB and util==0 plus visible-process check' if own_pid is None else 'resident model: original other-process exclusion; no idle threshold applied to our own loaded model')

class GPUChecks:
    def __init__(self,out):self.out=Path(out);self.index=0
    def check(self,*,deadline=None,own_pid=None):
        self.index+=1;start=time.monotonic();commands=[]
        args=[['nvidia-smi','-i',UUID,'--query-gpu=uuid,name,memory.free,utilization.gpu','--format=csv,noheader,nounits'],
              ['nvidia-smi','-i',UUID,'--query-compute-apps=gpu_uuid,pid,process_name,used_gpu_memory','--format=csv,noheader,nounits'],
              ['nvidia-smi','-i',UUID,'-q','-x']]
        for cmd in args:
            remaining=20 if deadline is None else min(20,deadline-time.monotonic())
            q=dict(argv=cmd,start_jst=now(),returncode=None,stdout='',stderr='',error=None)
            t=time.monotonic()
            if remaining<=0:q['error']='five_minute_check_deadline'
            else:
                try:
                    p=subprocess.run(cmd,capture_output=True,text=True,timeout=remaining)
                    q.update(returncode=p.returncode,stdout=p.stdout,stderr=p.stderr)
                except subprocess.TimeoutExpired as exc:
                    q.update(error='query_timeout',stdout=(exc.stdout or b'').decode(errors='replace') if isinstance(exc.stdout,bytes) else exc.stdout or '',stderr=(exc.stderr or b'').decode(errors='replace') if isinstance(exc.stderr,bytes) else exc.stderr or '')
                except OSError as exc:q['error']=type(exc).__name__+': '+str(exc)
            q.update(end_jst=now(),elapsed_seconds=time.monotonic()-t);commands.append(q)
        result=parse_gpu(*(q['stdout'] for q in commands),own_pid=own_pid)
        for i,q in enumerate(commands):
            if q['returncode']!=0 or q['error']:
                result['rejection_reasons'].append(f'query_{i}_failed: rc={q["returncode"]} error={q["error"]}')
        context={}
        try:
            context['uid_map']=Path('/proc/self/uid_map').read_text()
            context['proc_mounts']=[x for x in Path('/proc/mounts').read_text().splitlines() if x.split()[1]=='/proc']
            context['self_pid_namespace']=os.readlink('/proc/self/ns/pid')
            context['init_pid_namespace']=os.readlink('/proc/1/ns/pid')
            if any('hidepid=1' in x or 'hidepid=2' in x for x in context['proc_mounts']):
                result['rejection_reasons'].append('process_visibility_restricted_hidepid')
            if context['self_pid_namespace']!=context['init_pid_namespace']:
                result['rejection_reasons'].append('process_visibility_namespace_mismatch')
        except OSError as exc:
            context['error']=type(exc).__name__;result['rejection_reasons'].append('process_visibility_context_unreadable')
        result.update(eligible=not result['rejection_reasons'],check_index=self.index,start_jst=commands[0]['start_jst'],end_jst=now(),elapsed_seconds=time.monotonic()-start,queries=commands,process_visibility_context=context,own_pid=own_pid)
        s.save(self.out/f'gpu_check_{self.index:04d}.json',result)
        print(s.canonical({'gpu_check':self.index,'gpu':result['selected_gpu'],'visibility':result['process_visibility'],'visible_processes':result['visible_processes'],'eligible':result['eligible'],'reasons':result['rejection_reasons']}),flush=True)
        return result
    def wait_idle(self,seconds=300):
        if not 0<seconds<=300:raise ValueError('read-only wait must be at most 300 seconds')
        start=time.monotonic();deadline=start+seconds;checks=[]
        while time.monotonic()<deadline:
            r=self.check(deadline=deadline);checks.append(r['check_index'])
            if r['eligible']:
                answer=dict(eligible=True,check_indices=checks,elapsed_seconds=time.monotonic()-start,max_seconds=seconds)
                break
            remaining=deadline-time.monotonic()
            if remaining>0:time.sleep(min(10,remaining))
        else:answer=dict(eligible=False,check_indices=checks,elapsed_seconds=time.monotonic()-start,max_seconds=seconds)
        s.save(self.out/'idle_wait_result.json',answer);return answer

def validate_artifacts(plan,approval):
    """Same local artifact/package guard as selection.live_preflight, separated from live GPU sampling.

    Hash shared files once, then validate both exact existing per-mode receipts.
    No downloads, retokenization, imports of model code, or GPU activity.
    """
    path=Path(approval['local_model_path']);official=s.read(s.HERE/'gemma_public_file_metadata.json')
    required={x['rfilename'] for x in official['files']};hashes={}
    for name in required:
        f=(path/name).resolve()
        if not f.is_relative_to(path.resolve()):raise ValueError('model path escapes root')
        hashes[name]=s.sha(f)
    for candidate in CANDIDATES:
        c=s.verify_approval(plan,candidate,'engineering',approval)
        if c['gpu_uuid']!=UUID:raise ValueError('GPU UUID binding drift')
        r=s.read(approval['local_snapshot_receipts'][c['identity']])
        if r['revision']!=c['revision'] or r['configuration_identity']!=c['identity']:raise ValueError('readiness identity mismatch')
        if r['files']!=hashes or set(r['files'])!=required:raise ValueError('weight receipt mismatch')
        if r['all_full_inputs_fit'] is not True or r['output_reserve_tokens']<32768:raise ValueError('complete input reserve not verified')
        expected={x['request_id'] for x in plan['requests'] if x['candidate']==candidate}
        if set(r['request_input_tokens'])!=expected or not all(type(n)==int and n>0 and n+32768<=262144 for n in r['request_input_tokens'].values()):raise ValueError('input length receipt mismatch')
        for package,version in c['packages'].items():
            if md.version(package)!=version:raise ValueError('package drift: '+package)
    for item in official['files']:
        if (path/item['rfilename']).stat().st_size!=item['size']:raise ValueError('official size mismatch')
        if 'lfs' in item and hashes[item['rfilename']]!=item['lfs']['sha256']:raise ValueError('official weight/tokenizer mismatch')
        if 'lfs' not in item:
            data=(path/item['rfilename']).read_bytes()
            if hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()!=item['blobId']:raise ValueError('official metadata git hash mismatch')
    return dict(all_shared_files_verified=True,files=hashes,complete_inputs_and_reserves_verified=True,packages_verified=True,download=False)

def slots(plan):
    return sorted([r for r in plan['requests'] if r['candidate'] in CANDIDATES and r['phase']=='engineering'],key=lambda r:r['schedule_position'])

def reconstruct(plan,root,mode='live'):
    """Every durable start/result/raw counts; no cache or directory can reset allowance."""
    root=Path(root);requests={r['request_id']:r for r in plan['requests']};occupied={};blocked={};issues=[]
    for suffix in ['started','result','raw','response']:
        for path in root.rglob('*.'+suffix+'.json'):
            rid=path.name.split('.')[0]
            if rid not in requests:raise ValueError('unknown attempt artifact: '+str(path))
            req=requests[rid]
            if path.parent!=root/req['candidate']:raise ValueError('attempt outside canonical candidate directory')
            if suffix in ('started','result'):
                row=s.read(path)
                if row.get('request')!=req or row.get('mode')!=mode:raise ValueError('attempt identity/mode mismatch')
                if suffix=='result' and row['measurement']['measurement_status'] not in s.VALID:
                    blocked[req['candidate']]='prior failed model request; no retry'
            occupied.setdefault(rid,[]).append(suffix)
    for rid,kinds in occupied.items():
        candidate=requests[rid]['candidate']
        if 'started' not in kinds:issues.append('orphan attempt evidence: '+rid);blocked[candidate]='orphan result/raw; count retained, do not repeat'
        if 'result' not in kinds:blocked[candidate]='prior started request without completed result; no retry'
    for c in CANDIDATES:
        if (root/c/'STOP.json').exists():blocked[c]='original durable STOP retained'
    local_counts={c:sum(requests[r]['candidate']==c for r in occupied) for c in CANDIDATES}
    if len(occupied)>8 or any(n>4 for n in local_counts.values()):raise ValueError('existing starts exceed authorized envelope')
    return dict(occupied=occupied,blocked=blocked,issues=issues,total_started_or_evidenced=len(occupied),old_calls=66,cumulative_calls=66+len(occupied),per_configuration=local_counts)

def continue_stage(plan,root,out,approval,parent,*,mode,wait_fn,transport_factory,static_check):
    """Call under the same pool lock as the old runner. One phase, no retries."""
    root=Path(root);out=Path(out);parent=Path(parent)
    old=s.read(parent)
    if old['plan_identity']!=plan['identity'] or old['phase']!='engineering' or old['mode']!=mode:raise ValueError('wrong parent stage')
    reqs=slots(plan);before=reconstruct(plan,root,mode)
    for c in CANDIDATES:s.verify_approval(plan,c,'engineering',approval)
    if approval['new_calls_limit']!=8 or approval['cumulative_calls_limit']!=74 or set(approval['configuration_identities'])!={plan['configs'][c]['identity'] for c in CANDIDATES}:raise ValueError('must preserve AB eight-attempt scope')
    if len(reqs)!=8:raise ValueError('original eight slots changed')
    for a in old['attempts']:
        if a.get('started') and a['request_id'] not in before['occupied']:raise ValueError('parent claims missing start; cannot reset count')
    if not set(old.get('history_after',{}).get('occupied',{})).issubset(before['occupied']):
        raise ValueError('parent continuation lost attempt evidence; cannot reset count')
    s.save(out/'continuation_schedule.json',dict(plan_identity=plan['identity'],parent_stage=str(parent),parent_sha256=s.sha(parent),request_ids=[r['request_id'] for r in reqs],history_before=before,mode=mode,phase='engineering',new_experiment=False))
    blocked=dict(before['blocked']);pending=[r for r in reqs if r['request_id'] not in before['occupied'] and r['candidate'] not in blocked]
    if pending:
        try:
            static_check()
            ready=wait_fn()
            if not ready['eligible']:
                blocked.update({r['candidate']:'GPU readiness window ended without satisfying unchanged guard' for r in pending})
        except Exception as exc:
            error=dict(time_jst=now(),error_type=type(exc).__name__,error=str(exc),started=False)
            s.save(out/'preflight_error.json',error)
            blocked.update({r['candidate']:'pre-dispatch readiness failure: '+error['error'] for r in pending})
    attempts=[];transport=None;loads=[];resident_start=None
    try:
        for req in reqs:
            rid=req['request_id'];candidate=req['candidate'];c=plan['configs'][candidate]
            current=reconstruct(plan,root,mode)
            blocked.update(current['blocked'])
            if rid in current['occupied']:
                attempts.append(dict(request_id=rid,candidate=candidate,started_this_continuation=False,previously_evidenced=True,reason='existing start/result retained; skip'))
                continue
            if candidate in blocked:
                attempts.append(dict(request_id=rid,candidate=candidate,started_this_continuation=False,previously_evidenced=False,reason=blocked[candidate]));continue
            if current['total_started_or_evidenced']>=8 or current['per_configuration'][candidate]>=4:raise ValueError('original call cap reached')
            try:
                if transport is None:
                    resident_start=time.monotonic()
                    transport=transport_factory(c)
                    loads.append(dict(load_seconds=getattr(transport,'load_seconds',0),shared=True))
                transport.config=c
                transport.gpu_condition()
                r=s.execute(plan,candidate,'engineering',root/candidate,mode=mode,approval=approval,request_ids=[rid],transport=transport,readiness_checked=True,pool_root=root)
                attempts.append(dict(request_id=rid,candidate=candidate,started_this_continuation=bool(r['started']),stopped=r['stopped']))
                if r['stopped']:blocked[candidate]='technical failure; no model request retry'
            except Exception as exc:
                # Local-only path has no credential-bearing network exceptions.
                started=(root/candidate/(rid+'.started.json')).exists()
                detail=dict(request_id=rid,candidate=candidate,error_type=type(exc).__name__,error=str(exc),started=started,time_jst=now())
                s.save(out/(rid+'.dispatch_error.json'),detail)
                attempts.append(dict(request_id=rid,candidate=candidate,started_this_continuation=started,reason=detail['error']))
                blocked[candidate]=detail['error']
                if transport is None:
                    # One shared model load failure is not retried under the other mode.
                    blocked.update({x:'shared model load failed before dispatch; not retried' for x in CANDIDATES})
    finally:
        after=reconstruct(plan,root,mode)
        summary=dict(plan_identity=plan['identity'],parent_stage=str(parent),parent_sha256=s.sha(parent),mode=mode,phase='engineering',attempts=attempts,blocked_configurations=blocked,history_before=before,history_after=after,started_this_continuation=after['total_started_or_evidenced']-before['total_started_or_evidenced'],loads=loads,shared_GPU_residence_seconds=time.monotonic()-resident_start if resident_start is not None else None,next_phase_started=False,qualification='NOT_EVALUATED',new_experiment=False)
        s.save(out/'continuation_result.json',summary)
    return summary

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--amendment',type=Path,required=True)
    ap.add_argument('--execute-live',action='store_true',required=True)
    args=ap.parse_args();plan=s.load_plan();a=s.read(args.amendment)
    if a['status']!='APPROVED' or a['plan_identity']!=plan['identity'] or a['resume_code_sha256']!=s.sha(__file__):raise ValueError('engineering amendment binding mismatch')
    if a['semantic_revision_delta']!=0 or a['maximum_idle_wait_seconds']!=300:raise ValueError('scope drift')
    root=s.HERE/'live_runs';parent=root/'engineering.AB.stage_result.json'
    if s.sha(parent)!=a['parent_stage_sha256']:raise ValueError('parent receipt changed')
    approval=s.read(a['original_approval_path'])
    if s.sha(a['original_approval_path'])!=a['original_approval_sha256']:raise ValueError('approval changed')
    for path,expected in a['local_snapshot_receipt_sha256'].items():
        if s.sha(path)!=expected:raise ValueError('original readiness receipt changed')
    out=root/'continuations'/a['continuation_id']
    with (root/'.pool.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        out.mkdir(parents=True,exist_ok=False)
        s.save(out/'engineering_amendment.json',a);checks=GPUChecks(out)
        def static():
            t=time.monotonic();r=validate_artifacts(plan,approval);r['seconds']=time.monotonic()-t;s.save(out/'artifact_preflight.json',r)
        def factory(c):
            from adapters import GemmaTransport
            class ObservedGemma(GemmaTransport):
                def gpu_condition(self):
                    receipt=checks.check(own_pid=os.getpid())
                    if not receipt['eligible']:raise ValueError('resident GPU/process query blocked: '+str(receipt['rejection_reasons']))
                    return receipt['queries'][0]['stdout']
            return ObservedGemma(c,approval['local_model_path'])
        result=continue_stage(plan,root,out,approval,parent,mode='live',wait_fn=lambda:checks.wait_idle(300),transport_factory=factory,static_check=static)
        print(s.canonical({k:result[k] for k in ['started_this_continuation','blocked_configurations','history_after','shared_GPU_residence_seconds']}),flush=True)

if __name__=='__main__':main()
