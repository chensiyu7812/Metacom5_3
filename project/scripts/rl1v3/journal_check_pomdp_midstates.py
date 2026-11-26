#!/usr/bin/env python3
"""At most four preselected state payload reconstructions; CPU tokenizer only."""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import os
import sys


def main():
    p=argparse.ArgumentParser();p.add_argument('--collection',required=True)
    p.add_argument('--plan',required=True);p.add_argument('--out',required=True)
    args=p.parse_args();os.environ['CUDA_VISIBLE_DEVICES']=''
    root=Path(__file__).resolve().parents[2]
    module_path=root/'src/metacom_pm/rl1v3/journal/pomdp_decision_diagnostics.py'
    spec=importlib.util.spec_from_file_location('readonly_decisions',module_path)
    D=importlib.util.module_from_spec(spec);spec.loader.exec_module(D)
    plan=json.loads(Path(args.plan).read_text());collection=Path(args.collection)
    def rows(p):return [json.loads(s) for s in p.read_text().splitlines() if s]
    events=rows(collection/'ALL_EVENTS_PRIVATE.jsonl');endpoints=rows(collection/'ALL_48_ENDPOINTS_PRIVATE.jsonl')
    selected=D.select_midstates(plan,events)
    if len(selected)>4:raise ValueError('bounded state selection')
    base=plan['batches'][0];plan_path=Path(base['plan_path'])
    if hashlib.sha256(plan_path.read_bytes()).hexdigest()!=base['plan_file_sha256']:raise ValueError('original plan changed')
    execution=json.loads(plan_path.read_text());frozen=Path(execution['executor_root'])
    for name in ('project/src/metacom_pm/rl1v3/journal/renderer.py',
                 'project/src/metacom_pm/rl1v3/retrieve/native_tokens.py',
                 'project/src/metacom_pm/rl1v3/generator/g0e_port.py'):
        if hashlib.sha256((frozen/name).read_bytes()).hexdigest()!=execution['executor_files_sha256'][name]:
            raise ValueError('frozen implementation changed')
    sys.path.insert(0,str(frozen/'project/src'))
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    from metacom_pm.rl1v3.generator.g0e_port import PromptTokenizer
    from metacom_pm.rl1v3.journal import renderer
    source=json.loads(Path(execution['source_config_path']).read_text())
    tokenizer=PromptTokenizer(NativeTokenizer(execution['model_path'],source['asset_manifest_path']))
    renderer_sha=hashlib.sha256(Path(renderer.__file__).read_bytes()).hexdigest()
    results=[]
    for state in selected:
        if 'task_id' not in state:
            results.append(state);continue
        obs=state['observation']
        if D.digest(obs)!=state['observation_sha256']:raise ValueError('selected observation hash')
        payload=D.reconstruct_midstate_payload(obs,tokenizer=tokenizer,renderer=renderer,
            baseline_sha256=execution['baseline_sha256'],renderer_sha256=renderer_sha)
        match=D.exact_terminal_matches(task_id=state['task_id'],reconstructed_payload=payload,
                                       reconstruction_verified=True,endpoints=endpoints)
        results.append(dict(batch=state['batch'],task_id=state['task_id'],event_seq=state['event_seq'],
            state_sha256=state['state_sha256'],observation_sha256=state['observation_sha256'],
            reconstructed_payload=payload,payload_sha256=D.digest(payload),matches=match,
            native_input_tokens=len(payload['input_ids']),formal_reward=None))
    out=Path(args.out);out.mkdir(parents=True,exist_ok=False)
    (out/'MIDSTATE_EXACT_MATCH_PRIVATE.json').write_text(json.dumps(results,ensure_ascii=False,sort_keys=True,indent=2)+'\n')
    public=[dict(batch=r['batch'],status=r.get('status',r.get('matches',{}).get('status')),
        cross_arm_matches=[m['method'] for m in r.get('matches',{}).get('matches',[])],
        same_path_match=bool(r.get('matches',{}).get('same_path_matches')),formal_reward=None) for r in results]
    report=dict(protocol='pmrl1-j-selected-midstate-payload-check-v1',selected=len([r for r in results if 'payload_sha256' in r]),
        max_states=4,results=public,tokenizer_identity=tokenizer.identity,renderer_sha256=renderer_sha,
        model_loads=0,model_calls=0,gpu_calls=0,api_calls=0,training_calls=0,
        interpretation='exact G input endpoint reuse only; not randomized continuation contrast or new independent repetition',
        input_sha256={name:hashlib.sha256((collection/name).read_bytes()).hexdigest() for name in
            ['ALL_EVENTS_PRIVATE.jsonl','ALL_48_ENDPOINTS_PRIVATE.jsonl']},
        decision_plan_sha256=hashlib.sha256(Path(args.plan).read_bytes()).hexdigest())
    (out/'MIDSTATE_EXACT_MATCH_PUBLIC.json').write_text(json.dumps(report,sort_keys=True,indent=2)+'\n')
    print(json.dumps(public))


if __name__=='__main__':main()
