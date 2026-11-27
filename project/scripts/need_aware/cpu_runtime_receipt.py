#!/usr/bin/env python3
"""Run inside a mount namespace with runtime inputs only; no model results."""
import json
from pathlib import Path
import time
from metacom_pm.need_aware.data.contracts import digest,load_runtime
from metacom_pm.need_aware.data.history import HistoryResolver


def main():
    start=time.monotonic()
    # This is deliberately not an assertion about chmod: the actual host
    # paths must be absent from the worker's mount namespace.
    denied=['/opt/tokkio-data0/naa/20261127/source',
            '/opt/tokkio-data0/naa/20261127/artifacts/evaluation',
            '/opt/tokkio-data0/naa/20261127/artifacts/training','/direct']
    if any(Path(p).exists() for p in denied):
        raise RuntimeError('worker isolation failed')
    tasks=load_runtime('/runtime/tasks.mcq.jsonl')+load_runtime('/runtime/tasks.generation.jsonl')
    resolver=HistoryResolver('/runtime');out=Path('/output');trace=[]
    for task in tasks:
        records=resolver.resolve(task)
        # Actual input inspection, no retrieval algorithm or response fabricated.
        trace.append({'task_id':task.task_id,'task_mode':task.task_mode,'persona_group':task.persona_group,
                      'legal_source_ids':[r.source_id for r in records],
                      'history_messages':len(records),'history_characters':sum(len(r.original_text) for r in records),
                      'query_sha256':digest(task.user_query),'runtime_task_sha256':digest(task.to_dict()),
                      'status':'runtime_resolved','model_calls':0})
    (out/'runtime_trace.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in trace))
    report={'result_kind':'plumbing','tasks_resolved':len(trace),'mcq':sum(t.task_mode=='mcq' for t in tasks),
            'generation':sum(t.task_mode=='generation' for t in tasks),'model_calls':0,
            'namespace_denied_roots':denied,'network_namespace_isolated':True,'cpu_wall_seconds':time.monotonic()-start}
    (out/'runtime_summary.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))


if __name__=='__main__':main()
