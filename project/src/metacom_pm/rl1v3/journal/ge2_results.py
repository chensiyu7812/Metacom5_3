"""Read-only GE2 real-run collection. Never a generator, policy or semantic judge.

Validate original journal chains and actual return records independently of the
job FINISHED label. Keep private responses and source receipts out of exports.
"""
from __future__ import annotations
from collections import Counter, defaultdict
import json
import math
from pathlib import Path

from ..io import file_sha256, object_sha256, write_json_once, write_jsonl_once
from .pomdp_latency import duration_ns


def read(p):
    return json.loads(Path(p).read_text())


def rows(p):
    return [json.loads(s) for s in Path(p).read_text().splitlines() if s.strip()]


def nearest(values, quantile):
    values = sorted(x for x in values if x is not None)
    return None if not values else values[max(0, math.ceil(quantile * len(values)) - 1)]


def union_ns(pairs):
    """Duration of a measured interval union, not a sum of nested categories."""
    end = None
    total = 0
    for a, b in sorted(pairs):
        if b < a:
            raise ValueError('reversed measured interval')
        total += max(0, b - max(a, end if end is not None else a))
        end = max(b, end if end is not None else b)
    return total


def journal(job):
    paths = sorted(job.glob('[0-9]*.json'))
    result = []
    previous = None
    last_stamp = None
    hashes = {}
    for index, path in enumerate(paths):
        row = read(path)
        if row['seq'] != index or row['previous_event_sha256'] != previous:
            raise ValueError('journal chain/sequence mismatch')
        if last_stamp is not None:
            duration_ns(last_stamp, row['stamp'])
        last_stamp = row['stamp']
        previous = file_sha256(path)
        hashes[str(path)] = previous
        result.append(row)
    summary_path = job / 'SUMMARY.json'
    if not summary_path.exists():
        raise ValueError('collect only a finished/stopped original attempt')
    summary = read(summary_path)
    if summary['last_journal_sha256'] != previous:
        raise ValueError('summary/journal terminal hash mismatch')
    hashes[str(summary_path)] = file_sha256(summary_path)
    return result, summary, hashes


def collect(package, root, bundle, out, batches=(1, 2, 3, 4)):
    package, root, bundle, out = map(Path, (package, root, bundle, out))
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    catalog = read(package / 'CATALOG.json')
    tasks = {r['task_id']: r for r in rows(bundle / 'TASKS.runtime.jsonl')}
    specs = {r['task_id']: r for r in rows(bundle / 'EVALSPEC.private.jsonl')}
    selection = read(package / 'batch-01' / 'PLAN.json')['selection_path']
    aliases = {r['task_id']: r['task_alias'] for r in read(selection)['tasks']}
    inputs = {str(package/'CATALOG.json'): file_sha256(package/'CATALOG.json')}
    calls, endpoints, paths_private, jobs = [], [], [], []
    for number in batches:
        entry = catalog['batches'][number-1]
        plan = read(entry['plan_path'])
        if object_sha256(plan) != entry['plan_object_sha256']:
            raise ValueError('original plan changed')
        inputs[entry['plan_path']] = file_sha256(entry['plan_path'])
        candidates = list((root / ('GE2-%d_run-v1'%number)).glob('job-*'))
        if len(candidates) != 1:
            raise ValueError('exactly one original run per job required')
        events, summary, bound = journal(candidates[0])
        inputs.update(bound)
        if summary['plan_sha256'] != entry['plan_object_sha256']:
            raise ValueError('summary wrong plan')
        start_events = {e['request']['request_id']:e for e in events if e['event']=='MODEL_REQUEST_START'}
        returns = {e['request_id']:e for e in events if e['event']=='MODEL_REQUEST_RETURNED'}
        validations = {e['request_id']:e for e in events if e['event']=='MODEL_REQUEST_VALIDATED'}
        failures = {e['request_id']:e for e in events if e['event']=='MODEL_REQUEST_FAILED'}
        by_path = defaultdict(list)
        for rid, event in start_events.items():
            request = event['request']; binding = request['binding']
            if object_sha256(request) != event['request_sha256']:
                raise ValueError('request binding mismatch')
            output = returns.get(rid, {}).get('output')
            ret = returns.get(rid)
            if output is not None:
                if object_sha256(output) != ret['output_sha256'] or output['request_sha256'] != object_sha256(request):
                    raise ValueError('returned output binding mismatch')
                if output['input_tokens'] != len(request['payload']['input_ids']):
                    raise ValueError('input token count mismatch')
                eos = request['payload']['decode']['eos_token_id']
                reason = 'eos' if output['token_ids'] and output['token_ids'][-1] in eos else 'length'
                if output['finish_reason'] != reason:
                    raise ValueError('EOS/token finish mismatch')
                if rid in validations and validations[rid]['finish_reason'] != reason:
                    raise ValueError('validation/return finish mismatch')
                worker_ns = duration_ns(output['started'], output['finished'])
                if abs(worker_ns/1e9-output['seconds']) > 1e-9:
                    raise ValueError('actual generation clock mismatch')
            else:
                reason, worker_ns = None, None
            row = dict(batch=number, task_id=binding['task_id'], task_alias=aliases[binding['task_id']],
                method=binding['method'], role=request['role'], request_id=rid,
                request_sha256=object_sha256(request), payload_sha256=object_sha256(request['payload']),
                started=event['stamp'], returned=None if ret is None else ret['stamp'],
                transport_ns=None if ret is None else duration_ns(event['stamp'],ret['stamp']),
                input_tokens=len(request['payload']['input_ids']),
                output_tokens=None if output is None else len(output['token_ids']),
                generation_ns=worker_ns, finish_reason=reason, returned_output=output is not None,
                validated=rid in validations, failed=rid in failures,
                technical_completion=output is not None and rid in validations and reason=='eos' and bool(output['text'].strip()),
                real_output=output, original_request=request, original_failure=failures.get(rid),
                formal_reward=None)
            calls.append(row); by_path[(binding['task_id'],binding['method'])].append(row)
        completed = {(e['task_id'],e['method']):e['endpoint'] for e in events if e['event']=='AGENT_PATH_COMPLETED'}
        runtime = summary.get('runtime')
        if runtime is not None and runtime['results'] != list(completed.values()):
            raise ValueError('runtime result not equal to original journal endpoint list')
        path_events = {}
        active = None
        for e in events:
            if e['event']=='AGENT_PATH_START':active=(e['task_id'],e['method']);path_events[active]=[]
            if active is not None:path_events[active].append(e)
            if e['event']=='AGENT_PATH_COMPLETED':active=None
        for slot in plan['terminal_slots']:
            key=(slot['task_id'],slot['method']);endpoint=completed.get(key)
            sequence=path_events.get(key,[]);pcalls=by_path[key]
            terminals=[c for c in pcalls if c['role']=='terminal']
            if len(terminals)>1:raise ValueError('terminal retried')
            terminal=terminals[0] if terminals else None
            controls=[c for c in pcalls if c['role']!='terminal']
            guard_ns=sum(e['elapsed_ns'] for e in sequence if e['event']=='EXPERIMENT_GUARD_RETURNED')
            tools=[e for e in sequence if e['event'] in ('TOOL_RETURNED','TOOL_REJECTED')]
            bind=next((e for e in sequence if e['event']=='TERMINAL_INPUT_BOUND'),None)
            receipt=None if bind is None else bind['source_receipt']
            if bind is not None and object_sha256(receipt)!=bind['source_receipt_sha256']:
                raise ValueError('source receipt hash')
            if endpoint is not None:
                if not terminal or endpoint['output']!=terminal['real_output']:
                    raise ValueError('completed path does not bind terminal return')
                first=terminal['real_output']['passive_output_observer']['events']['first_nonempty_decoded_text']
                first_ns=None if first is None else duration_ns(endpoint['path_started'],first)
                full_ns=duration_ns(endpoint['path_started'],endpoint['path_finished'])
                if first_ns != endpoint['agent_to_worker_first_nonempty_text_ns'] or full_ns != endpoint['agent_to_reply_ns']:
                    raise ValueError('agent first/full clock mismatch')
                pm_ns=duration_ns(endpoint['path_started'],endpoint['pm_finished'])
                if pm_ns!=endpoint['pm_elapsed_ns']:raise ValueError('PM clock mismatch')
            else:first_ns=full_ns=pm_ns=None
            technical=('unexecuted' if not sequence else 'terminal_not_started' if terminal is None else
                'terminal_call_failed' if terminal['failed'] else 'terminal_return_unvalidated' if not terminal['validated'] else
                'terminal_length' if terminal['finish_reason']=='length' else
                'terminal_empty' if not terminal['real_output']['text'].strip() else 'terminal_eos')
            spans=[] if receipt is None else receipt.get('timing_spans',[])
            categories=defaultdict(list)
            for s in spans:
                if 'started' in s:
                    duration_ns(s['started'],s['finished'])
                    categories[s['category']].append((s['started']['monotonic_ns'],s['finished']['monotonic_ns']))
            public=dict(batch=number,task_alias=aliases[key[0]],task_id=key[0],method=key[1],channel=specs[key[0]]['channel'],
                technical_status=technical,job_status=summary['status'],path_completed_event=endpoint is not None,
                terminal_eos=technical=='terminal_eos',controller_calls=len(controls),
                controller_finish_reasons=[c['finish_reason'] for c in controls],
                controller_failure=None if endpoint is None else endpoint['controller_failure'],
                fallback_executed=None if endpoint is None else endpoint['fallback_executed'],
                stop_reason=None if bind is None else bind['stop_reason'],
                acquisition_actions=[e['action']['action'] for e in tools if e['action']['action']!='STOP'],
                tool_refusals=[e.get('reason') for e in tools if e['event']=='TOOL_REJECTED'],
                input_tokens=None if terminal is None else terminal['input_tokens'],
                output_tokens=None if terminal is None else terminal['output_tokens'],
                all_call_input_tokens=sum(c['input_tokens'] for c in pcalls),
                all_returned_output_tokens=sum(c['output_tokens'] or 0 for c in pcalls),
                controller_input_tokens=sum(c['input_tokens'] for c in controls),
                controller_output_tokens=sum(c['output_tokens'] or 0 for c in controls),
                agent_complete_ns=full_ns,agent_to_G_internal_first_text_ns=first_ns,pm_ns=pm_ns,
                controller_transport_ns=sum(c['transport_ns'] or 0 for c in controls),
                controller_generation_ns=sum(c['generation_ns'] or 0 for c in controls),
                terminal_generation_ns=None if terminal is None else terminal['generation_ns'],
                experiment_guard_ns=guard_ns,tool_wall_ns=sum(e['elapsed_ns'] for e in tools),
                component_interval_unions_ns={k:union_ns(v) for k,v in categories.items()},
                component_caveat='inclusive nested components, not additive; no client/voice measurement',
                actual_payload_sha256=None if terminal is None else terminal['payload_sha256'],
                source_receipt_sha256=None if receipt is None else object_sha256(receipt),
                source_tokens=None if receipt is None else receipt.get('canonical_source_tokens'),
                client_first_text_ns=None,Tokkio_effective_voice_ns=None,quality_status='unreviewed',formal_reward=None)
            endpoints.append(public)
            paths_private.append(dict(public=public,task=tasks[key[0]],evaluation=specs[key[0]],
                original_endpoint=endpoint,terminal_request=None if terminal is None else terminal['original_request'],
                actual_output=None if terminal is None else terminal['real_output'],
                source_receipt=receipt,model_assessments=[] if bind is None else bind['model_assessments'],events=sequence))
        loads=[e for e in events if e['event']=='LOAD_OK']
        load_starts=[e for e in events if e['event']=='LOAD_START']
        jobs.append(dict(batch=number,status=summary['status'],reason=summary.get('supervisor_failure') or (runtime or {}).get('reason'),
            wall_ns=summary['wall_ns'],load_attempts=len(load_starts),loads_returned=len(loads),
            load_measurement=None if not loads else loads[0]['measurement'],
            calls_started=len(start_events),calls_returned=len(returns),calls_validated=len(validations),
            calls_failed=len(failures),terminal_slots=len(plan['terminal_slots']),
            original_model_byte_verification=any(e['event']=='MODEL_BYTES_VERIFIED' for e in events),
            plan_object_sha256=entry['plan_object_sha256'],formal_reward=None))
    write_jsonl_once(out/'CALLS_PRIVATE.jsonl',calls)
    write_jsonl_once(out/'PATHS_PRIVATE.jsonl',paths_private)
    write_jsonl_once(out/'ENDPOINTS_PUBLIC.jsonl',endpoints)
    write_json_once(out/'JOBS_PUBLIC.json',jobs)
    groups=defaultdict(list)
    for p in endpoints:groups[p['method']].append(p)
    aggregate=dict(tasks=len({p['task_id'] for p in endpoints}),terminal_slots=len(endpoints),
        technical=dict(Counter(p['technical_status'] for p in endpoints)),
        calls_started=len(calls),calls_returned=sum(c['returned_output'] for c in calls),
        calls_by_role=dict(Counter(c['role'] for c in calls)),loads=sum(j['load_attempts'] for j in jobs),
        fallback_paths=sum(bool(p['fallback_executed']) for p in endpoints),
        job_status=dict(Counter(j['status'] for j in jobs)),
        latency_unfiltered_by_quality={m:dict(paths=len(ps),full_p50_ns=nearest([p['agent_complete_ns'] for p in ps],.5),
            full_p95_ns=nearest([p['agent_complete_ns'] for p in ps],.95),
            first_p50_ns=nearest([p['agent_to_G_internal_first_text_ns'] for p in ps],.5),
            first_p95_ns=nearest([p['agent_to_G_internal_first_text_ns'] for p in ps],.95)) for m,ps in groups.items()},
        formal_reward=None,quality_not_yet_reviewed=True,latency_scope='actual local request, not client or Tokkio')
    write_json_once(out/'TECHNICAL_SUMMARY_PUBLIC.json',aggregate)
    write_json_once(out/'COLLECTION_MANIFEST_PRIVATE.json',dict(protocol='ge2-readonly-result-collection-v1',
        collector_sha256=file_sha256(__file__),input_files_sha256=inputs,
        files_sha256={p.name:file_sha256(p) for p in sorted(out.iterdir()) if p.is_file()},formal_reward=None))
    return aggregate
