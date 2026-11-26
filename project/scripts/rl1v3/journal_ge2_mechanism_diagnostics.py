#!/usr/bin/env python3
"""Read-only diagnostics of actual GE2 actions, observations and stop causes.

No policy labels, semantic judge, counterfactual generation or model loading.
Use the original hash-verified collection, not CPU fixture endpoints.
"""
from collections import Counter
from pathlib import Path
import argparse
import json

from metacom_pm.rl1v3.io import file_sha256, write_json_once
from journal_audit_ge2_actual_supply import rows, source_handle


def main():
    parser = argparse.ArgumentParser()
    for key in ('collection', 'bundle', 'out'):
        parser.add_argument('--' + key, required=True)
    args = parser.parse_args()
    collection, bundle, out = map(Path, (args.collection, args.bundle, args.out))
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    paths = rows(collection / 'PATHS_PRIVATE.jsonl')
    calls = rows(collection / 'CALLS_PRIVATE.jsonl')
    jobs = json.loads((collection / 'JOBS_PUBLIC.json').read_text())
    pools = {p['task_id']: p['records'] for p in rows(bundle / 'LEGAL_POOLS_PRIVATE.jsonl')}
    searches = 0
    role_sets = Counter()
    statuses = Counter()
    rejections = []
    first_read = []
    for path in paths:
        public = path['public']
        records = {source_handle(r): r for r in pools[public['task_id']]}
        events = path['events']
        accepted = [e for e in events if e['event'] == 'CONTROLLER_ACCEPTED']
        statuses.update(e['output']['evidence_state']['status'] for e in accepted)
        search_events = [e for e in events if e['event'] == 'TOOL_RETURNED'
                         and e['action']['action'] == 'SEARCH']
        searches += len(search_events)
        for event in search_events:
            observation = event['observation']
            hits = {h['handle']: h for h in observation['hits']}
            for handle in observation['last_hits']:
                hit = hits[handle]
                refs = records[hit['source_handle']]['source_refs']
                roles = {r['speaker'] for r in refs
                         if hit['start_turn'] <= r['turn_index'] <= hit['end_turn']}
                if not roles:
                    raise ValueError('actual hit has no original turn')
                role_sets[','.join(sorted(roles))] += 1
        rejections.extend(dict(task_alias=public['task_alias'], method=public['method'],
                               action=e['action']['action'], reason=e.get('reason'))
                          for e in events if e['event'] == 'TOOL_REJECTED')
        if public['method'] == 'LLMToolAgent' and search_events:
            first = search_events[0]
            requests = [e for e in events if e['event'] == 'MODEL_REQUEST_START'
                        and e['role'] != 'terminal']
            last_observation = json.loads(requests[-1]['request']['payload']['messages'][1]['content'])
            later = [e for e in events if e['event'] == 'TOOL_RETURNED'
                     and e['seq'] > first['seq'] and e['action']['action'] != 'STOP']
            first_read.append(dict(
                task_alias=public['task_alias'],
                first_search_equals_last_control_reading=(
                    first['observation']['readings'] == last_observation['readings']),
                later_resource_acquisitions=len(later),
                interpretation='Actual evidence path only; no counterfactual quality or static-window latency.',
                correct_action_label=None))
    summary = dict(
        complete_original_calls=sum(c['technical_completion'] for c in calls),
        terminal_eos=sum(c['finish_reason'] == 'eos' and c['role'] == 'terminal' for c in calls),
        control_eos=sum(c['finish_reason'] == 'eos' and c['role'] != 'terminal' for c in calls),
        technical_length=sum(c['finish_reason'] == 'length' for c in calls),
        fallback=sum(bool(p['public']['fallback_executed']) for p in paths),
        unexecuted=sum(p['public']['technical_status'] == 'unexecuted' for p in paths),
        actual_search_calls=searches, search_source_windows=sum(role_sets.values()),
        window_role_sets=dict(role_sets), query_or_tool_refusals=rejections,
        stop_reasons=dict(Counter(p['public']['stop_reason'] for p in paths)),
        controller_self_status=dict(statuses),
        ToolAgent_first_read_diagnostics=first_read,
        job_wall_seconds_total=sum(j['wall_ns'] for j in jobs) / 1e9,
        formal_reward=None, new_model_calls=0)
    write_json_once(out / 'MECHANISM_DIAGNOSTICS_PUBLIC.json', summary)
    write_json_once(out / 'MANIFEST_PRIVATE.json', dict(
        script_sha256=file_sha256(__file__),
        collection_manifest_sha256=file_sha256(collection / 'COLLECTION_MANIFEST_PRIVATE.json'),
        bundle_manifest_sha256=file_sha256(bundle / 'MANIFEST_PRIVATE.json'),
        files_sha256={'MECHANISM_DIAGNOSTICS_PUBLIC.json': file_sha256(out / 'MECHANISM_DIAGNOSTICS_PUBLIC.json')},
        formal_reward=None))
    print(json.dumps(summary, indent=2))


if __name__ == '__main__':
    main()
