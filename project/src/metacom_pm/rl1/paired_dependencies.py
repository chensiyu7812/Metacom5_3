"""Versioned dependency extension of the existing private paired.run loop.

Original paired.py is immutable. Replay, transport, pricing, input checks and
atomic budget are injected FROM that engine, not reimplemented here. Only the
dispatch dependency/evaluator hooks and immutable restart receipts are new.
No transport is created, credential read, or network request made on import.
"""
from pathlib import Path
import fcntl
import json
import os
import time

from .schema import digest

VERSION='paired-dependency-dispatch-v1-20261022'


def save(p, path, value):
    p.s.save(path,value)
    Path(path).chmod(0o600)
    with Path(path).open('rb') as f:os.fsync(f.fileno())


def verify_receipts(p, root, protocol, started, results):
    """Start/result binding plus sealed response/request/dependency bytes."""
    ids={s['slot_id'] for s in protocol['schedule']}
    for sid,start in started.items():
        if start['protocol_identity']!=protocol['identity']:raise ValueError('protocol changed after start')
        reqpath=root/(sid+'.request.json')
        if sid in results:
            sealpath=root/(sid+'.seal.json')
            if not sealpath.exists():raise ValueError('result not sealed; no automatic redispatch')
            sealed=p.s.read(sealpath)
            if not {sid+'.started.json',sid+'.request.json',sid+'.result.json'}<=set(sealed):
                raise ValueError('incomplete result seal')
            for name,expected in sealed.items():
                if Path(name).name!=name or p.s.sha(root/name)!=expected:raise ValueError('sealed result/request changed')
        if reqpath.exists():
            req=p.s.read(reqpath)
            if digest(dict(protocol=protocol['identity'],slot=sid,messages=req['messages'],schema=req['schema']))!=start['request_identity']:
                raise ValueError('request binding changed')
            if req['wire_body']!=p.api_body(protocol['config'],req['messages']):raise ValueError('wire payload changed')
        for name,expected in start.get('dependency_hashes',{}).items():
            if Path(name).name!=name or p.s.sha(root/name)!=expected:raise ValueError('dependency changed after dispatch')
    for path in root.glob('*.skip.json'):
        row=p.s.read(path);sid=path.name.removesuffix('.skip.json')
        if sid not in ids or sid in started or row['protocol_identity']!=protocol['identity']:
            raise ValueError('skip identity conflict')
    for path in root.glob('*.seal.json'):
        if path.name.removesuffix('.seal.json') not in results:raise ValueError('orphan seal')


def run(p, protocol, items, root, transport, budget, *, mode, runtime, auth=None,
        before_dispatch=lambda:None, global_count=lambda:285, after_result=lambda *_:None):
    """Same reserve→start→send→settle sequence; injectable dependency semantics.

    A process interruption AFTER a sealed result can resume its unstarted suffix.
    An unresolved start/reservation or STOP never retries. `after_result` is an
    offline interruption-test seam, not a provider retry callback.
    """
    if mode not in ('mock','live'):raise ValueError('unknown mode')
    if mode=='live':runtime['approve'](protocol,auth or {})
    root=Path(root);root.mkdir(parents=True,exist_ok=True,mode=0o700)
    with (root/'.study.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        started,results=p.replay(root,protocol)
        if any(s['mode']!=mode for s in started.values()):raise ValueError('mock/live mixing')
        verify_receipts(p,root,protocol,started,results)
        if len(started)>protocol['limits']['max_calls'] or global_count()+len(started)>protocol['limits']['cumulative_cap']:
            raise ValueError('historical attempt cap exceeded')
        for path in root.glob('*.skip.json'):
            sid=path.name.removesuffix('.skip.json')
            slot=next(s for s in protocol['schedule'] if s['slot_id']==sid)
            if p.s.read(path)['decision']!=runtime['dependency'](protocol,slot,results,started):
                raise ValueError('historical conditional decision changed')
        if (root/'CLOSED.json').exists() or (root/'STOP.json').exists():
            return runtime['summarize'](protocol,root,p)
        stop=runtime['stop'](protocol,started,results)
        total,trial,reserved,settled=budget._totals(budget.events())
        own={k for k,v in reserved.items() if v.get('binding',{}).get('study')==protocol['version']}
        if own-set(started):stop=stop or 'orphan reservation retained; accounting reconciliation required'
        if (set(started)-own) or any(k in results and k not in settled for k in started):
            stop=stop or 'attempt or usage liability unresolved; no retry'
        fingerprint=next((r.get('fingerprint') for r in results.values() if r.get('fingerprint')),None)
        for slot in protocol['schedule']:
            sid=slot['slot_id']
            if stop:break
            if sid in started:continue
            # All conditional slots are retained, even when the call cap is full.
            decision=runtime['dependency'](protocol,slot,results,started)
            skipfile=root/(sid+'.skip.json')
            if skipfile.exists():
                if p.s.read(skipfile)['decision']!=decision:raise ValueError('historical conditional decision changed')
                continue
            if decision['action']=='skip':
                save(p,skipfile,dict(protocol_identity=protocol['identity'],slot_id=sid,
                    decision=decision,model_attempt=False));continue
            if decision['action']!='dispatch':stop='missing required dependency';break
            if len(started)>=protocol['limits']['max_calls'] or global_count()+len(started)>=protocol['limits']['cumulative_cap']:
                stop='study or cumulative hard cap';break
            item=items[slot['item_key']]
            guard_step='identity/source/dependency'
            try:
                before_dispatch()
                dep_hashes={k+'.result.json':p.s.sha(root/(k+'.result.json')) for k in decision['dependencies']}
                for k in decision['dependencies']:
                    if p.s.read(root/(k+'.result.json'))!=results[k]:raise ValueError('dependency mutated before use')
                messages,schema=runtime['payload'](slot,item,results)
                runtime['validate_outbound'](slot,item,messages,schema,results)
                guard_step='complete native input boundary'
                screen=p.input_guard(messages);body=p.api_body(protocol['config'],messages)
                request_id=digest(dict(protocol=protocol['identity'],slot=sid,messages=messages,schema=schema))
                guard_step='atomic budget reservation'
                budget.reserve(sid,p.RESERVE,dict(study=protocol['version'],slot=slot,
                    request_identity=request_id,protocol_version=protocol['version']))
            except Exception as exc:
                # Controlled pre-dispatch checks do not touch credentials; no raw payload/error text in STOP.
                stop='pre-dispatch '+guard_step+': '+type(exc).__name__;break
            start=dict(slot=slot,protocol_identity=protocol['identity'],request_identity=request_id,
                mode=mode,started_unix=time.time(),reservation_usd=p.s.usd(p.RESERVE),dependency_hashes=dep_hashes)
            save(p,root/(sid+'.started.json'),start);started[sid]=start
            save(p,root/(sid+'.request.json'),dict(messages=messages,schema=schema,wire_body=body,input_screen=screen))
            raw=None;hard=None;financial=None;settled_ok=False;tick=time.monotonic()
            try:
                raw=transport.send(messages,schema,request=slot|dict(request_id=request_id),raw_path=root/(sid+'.sse'))
                save(p,root/(sid+'.response.json'),raw)
                if raw.get('model')!='deepseek-flash':hard='service model drift'
                if raw.get('request_identity')!=request_id:hard='transport binding mismatch'
                fp=raw.get('system_fingerprint')
                if not isinstance(fp,str) or not fp or (fingerprint and fp!=fingerprint):hard='service fingerprint missing or changed'
                fingerprint=fingerprint or fp
                # Unknown service identity may imply unknown pricing; keep its reservation.
                if not hard:
                    usage=raw.get('usage') or {}
                    output=usage.get('completion_tokens')
                    reasoning=(usage.get('completion_tokens_details') or {}).get('reasoning_tokens')
                    if reasoning is not None and (type(reasoning) is not int or type(output) is not int or not 0<=reasoning<=output):
                        raise ValueError('inconsistent reasoning usage')
                    financial=p.billed_peak_nanodollars(raw)
                    if financial is not None:
                        within=budget.settle(sid,financial,'complete usage received')
                        settled_ok=True
                        if not within:hard='actual cost exceeds reserved liability'
                ev=runtime['evaluate'](slot,item,raw)
                if financial is None:ev=ev|dict(technical_valid=False,financial_usage_unknown=True)
            except Exception as exc:
                ev=dict(technical_valid=False,model_unknown=None,value=None,q=None,m=None,U=None,
                        reward_eligible=False,error_type=type(exc).__name__,error='transport/accounting/validation exception; no retry')
            row=dict(slot_id=sid,request_identity=request_id,component=slot['component'],
                technical_valid=ev['technical_valid'] and not hard,evaluation=ev,hard_stop=hard,
                financial=dict(accounted_upper_usd=p.s.usd(financial) if settled_ok else None,
                    settlement_confirmed=settled_ok,unsettled_reservation_usd='0' if settled_ok else p.s.usd(p.RESERVE),invoice_confirmed=False),
                usage=raw.get('usage') if raw else None,elapsed_seconds=time.monotonic()-tick,
                fingerprint=raw.get('system_fingerprint') if raw else None,workflow_version=protocol['version'],
                new_step_instruction_version=protocol['version'],reward_eligible=False,
                natural_updates=0,semantic_review_status='not_adjudicated')
            save(p,root/(sid+'.result.json'),row);results[sid]=row
            names=[sid+'.started.json',sid+'.request.json',sid+'.result.json']
            names.extend(sid+'.'+s for s in ('response.json','sse') if (root/(sid+'.'+s)).exists())
            save(p,root/(sid+'.seal.json'),{name:p.s.sha(root/name) for name in names})
            stop=runtime['stop'](protocol,started,results)
            after_result(slot,row)
        if stop and not (root/'STOP.json').exists():
            save(p,root/'STOP.json',dict(reason=stop,started=len(started),automatic_retry=False,timestamp=time.time()))
        if not stop and all(s['slot_id'] in started or (root/(s['slot_id']+'.skip.json')).exists() for s in protocol['schedule']):
            save(p,root/'CLOSED.json',dict(status='AUTHORIZED_SCOPE_EXHAUSTED',protocol_identity=protocol['identity'],
                                        started=len(started),unstarted_are_explicit_conditional_skips=True))
        return runtime['summarize'](protocol,root,p)
