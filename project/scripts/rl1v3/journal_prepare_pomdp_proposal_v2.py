#!/usr/bin/env python3
"""Assemble a paired-source proposal sidecar; no execution or new source reads."""
import argparse,json
from pathlib import Path
from collections import defaultdict
from metacom_pm.rl1v3.io import file_sha256,object_sha256,write_json_once,write_jsonl_once


def run(previous,pressure,bundle,out):
    previous,pressure,bundle,out=map(Path,(previous,pressure,bundle,out))
    if out.exists():raise FileExistsError(out)
    def rows(path):return [json.loads(x) for x in path.read_text().splitlines()]
    old=json.loads((previous/'PROPOSAL_PRIVATE.json').read_text())
    tasks=old['task_ids'];envelopes={x['task_id']:x for x in rows(bundle/'TASK_ENVELOPES.private.jsonl')}
    groups=defaultdict(list)
    for task in tasks:groups[envelopes[task]['asof_runtime_sha256']].append(task)
    if len(groups)!=4 or any(len(g)!=2 for g in groups.values()):raise ValueError('four intact two-goal source pairs required')
    known=[r for r in rows(previous/'DETERMINISTIC_32_REQUESTS.private.jsonl') if r['arm']!='FixedTopK']
    broad={r['task_id']:r for r in rows(pressure/'TOP4_REQUESTS_PRIVATE.jsonl')}
    for task in tasks:
        row=dict(broad[task],arm='FixedTop4Macro')
        row['logical_id']='pmrl1-j-pomdp-memory-future-v2:'+task+':FixedTop4Macro'
        row['input_ids_sha256']=object_sha256(row['model_input']['input_ids'])
        known.append(row)
    if len(known)!=32:raise ValueError('four concrete endpoints per selected task')
    out.mkdir(parents=True)
    write_jsonl_once(out/'DETERMINISTIC_32_REQUESTS.private.jsonl',known)
    controls=rows(previous/'CONTROLLER_INITIAL_16.private.jsonl')
    write_jsonl_once(out/'CONTROLLER_INITIAL_16.private.jsonl',controls)
    batches=[]
    for i,pair in enumerate(groups.values(),1):
        requests=[r for r in known if r['task_id'] in pair]
        batches.append(dict(batch=i,task_ids=pair,terminal_logical_calls_max=12,
            oneshot_control_calls_max=2,toolagent_control_calls_max=8,physical_calls_max_before_cache=22,
            model_loads_max=1,seconds_max=1200,warmup_calls=0,retry_calls=0,
            deterministic_requests=8,deterministic_unique_payloads=len({r['payload_sha256'] for r in requests}),
            deterministic_input_tokens=sum(r['input_tokens'] for r in requests),
            output_tokens_max=6912,output_time_at_10_tokens_per_second=691.2,
            setup_allowance_seconds=100,planning_envelope_seconds=791.2,
            authorized=False,execution_ready=False))
    proposal=dict(old)
    proposal.update(protocol='pmrl1-j-pomdp-memory-future-comparison-proposal-v2',
        supersedes_proposal_sha256=file_sha256(previous/'PROPOSAL_PRIVATE.json'),
        arms=['STOP','FixedTop4Macro','LLMOneShot','LLMToolAgent','SequentialRule','SequentialNoText'],
        deterministic_unique_payloads=len({r['payload_sha256'] for r in known}),
        deterministic_input_tokens=sum(r['input_tokens'] for r in known),
        deterministic_input_tokens_max=max(r['input_tokens'] for r in known),
        suggested_jobs=4,proposed_model_loads_max=4,total_job_wall_cap_seconds=4800,
        suggested_job_scope='two fact/support goals from one source situation, each with six methods',
        token_generation_envelope_per_task_seconds=345.6,
        token_generation_envelope_per_job_seconds=691.2,setup_allowance_per_job_seconds=100,
        planning_envelope_per_job_seconds=791.2,
        timing_limit='345.6 seconds output-only per task; 691.2 seconds output-only per two-goal source-paired job; plus 100 seconds setup gives 791.2 seconds per-job planning envelope. Prefill, controller round trips and CPU retrieval remain uncertain; the 1200-second per-job hard stop is not a completion guarantee.',
        action_domain_status='not universally action-matched: FixedTop4Macro is a strong practical reference under the same token/context cap; strict sequential-mechanism comparison is LLMToolAgent versus initial-only LLMOneShot in the same primitive domain',
        macro_operator='1 retrieval + 4 full-parent reads = 5 operations; cannot relabel as one free access or fit it into the old four primitive accesses',
        common_cap='4096 delivered tokens and native context for every arm; all retrieval/read/control costs recorded',
        alternative_not_implemented='If universal action matching is required, first freeze a new common domain allowing four-hit retrieval plus five primitives for every method. No old tasks/rules/80 traces are changed here.',
        authorized=False,execution_ready=False,
        reason='dynamic runner/admission remains unimplemented, including 22-call source-paired jobs; no previous plan authorizes this proposal',
        implementation_sha256=file_sha256(__file__),pressure_sha256=file_sha256(pressure/'TOP4_PRESSURE_PUBLIC.json'),
        batches=batches,files_sha256={p.name:file_sha256(p) for p in out.iterdir()})
    write_json_once(out/'PROPOSAL_PRIVATE.json',proposal)
    public=dict(proposal);public.pop('task_ids')
    public['batches']=[{k:v for k,v in b.items() if k!='task_ids'} for b in batches]
    write_json_once(out/'PROPOSAL_PUBLIC.json',public)
    return public


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for key in ('previous','pressure','bundle','out'):parser.add_argument('--'+key,required=True)
    print(json.dumps(run(**vars(parser.parse_args())),indent=2))
