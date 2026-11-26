#!/usr/bin/env python3
"""CPU-only T03 union of its two ORIGINAL observed EXPAND candidates.

Does not change MIDSTATE4's rank-1 branch, request bytes or generation scope.
"""
import argparse
import json
from pathlib import Path
from metacom_pm.rl1v3.io import object_sha256, file_sha256, write_json_once
from metacom_pm.rl1v3.journal import pomdp_midstate_counterfactual as M
from metacom_pm.rl1v3.journal.pomdp_latency import MonotonicClock


def main():
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--out',required=True)
    a=p.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=False)
    plan=M.read(a.plan)
    assert object_sha256(plan)=='4276bf86e6e1012092018aeb6b0a8b82a9544988f74cc5c407919740b7b1e9b0'
    before={p:file_sha256(p) for p in (a.plan,plan['requests_path'],plan['states_path'],plan['review_path'])}
    factory,tasks=M.make_factory(plan,out/'ledgers')
    states=M.rows(plan['states_path']);task,state=tasks[1],states[1]
    assert task['task_id']==state['task_id']
    clock=MonotonicClock()
    ep=M.restore(factory,task,state,emit=lambda *args,**kwargs:None,clock=clock,deadline_ns=clock.now_ns()+1200*10**9)
    handles=M.ranked_handles(ep);assert len(handles)==2
    # Evaluation is loaded only after original state and rank order are bound.
    review=next(r for r in M.rows(plan['review_path']) if r['task_id']==task['task_id'])
    required=[atom for atom in review['source_binding']['atoms'] if atom['atom_id'] in review['required_fact_ids']]
    def coverage():
        refs=[]
        for item in ep.contents.values():refs.extend([item['span']] if 'span' in item else item.get('spans',[]))
        flags=[]
        for atom in required:
            supplied=any(all(any(r['session_id']==s['session_id'] and r['speaker']==s['speaker'] and s['exact_quote'] in r['exact_quote']
                for r in refs) or s['exact_quote'] in task['query'] for s in group['spans']) for group in atom['evidence_groups'])
            flags.append(dict(atom_id=atom['atom_id'],source_group_supplied=supplied))
        return flags
    initial=coverage();branches=[]
    for rank,handle in enumerate(handles,1):
        step=M.candidate_receipt(ep,handle)
        assert step['action_admissible'] and step['source_legal']
        branches.append(dict(rank=rank,transition=step,coverage=coverage()))
    ep.step({'action':'STOP'})
    private=dict(task_id=task['task_id'],original_state_sha256=state['state_sha256'],
        original_observation_sha256=state['observation_sha256'],ranked_observed_handles=handles,
        initial=initial,branches=branches,final_source_receipt=ep.receipt(),final_payload=ep.packet().payload(),
        model_calls=0,rank1_generation_plan_changed=False,formal_reward=None)
    write_json_once(out/'T03_UNION_PRIVATE.json',private)
    public=dict(protocol='ge2-original-T03-union-cpu-v1',task_alias='T03',
        original_midstate_plan_sha256=object_sha256(plan),original_midstate_requests_sha256=file_sha256(plan['requests_path']),
        candidates_observed=2,required_reference_groups=len(required),
        before_groups_supplied=sum(x['source_group_supplied'] for x in initial),
        after_rank1_groups_supplied=sum(x['source_group_supplied'] for x in branches[0]['coverage']),
        after_both_groups_supplied=sum(x['source_group_supplied'] for x in branches[1]['coverage']),
        both_actions_legal=True,both_actions_budget_reachable=True,
        final_input_tokens=len(ep.packet().input_ids),final_charged_tool_tokens=ep.charged_tokens,
        total_accesses=ep.accesses,accesses_remaining=ep.limits.accesses-ep.accesses,
        source_turns_added=[r['transition']['new_unique_source_turns'] for r in branches],
        original_span_parent_duplication_preserved=True,model_calls=0,task_success=None,
        rank1_generation_plan_changed=False,new_generation_request_added=False,
        interpretation='Exact original reference groups supplied; no claim of correct response or sequential advantage',
        input_files_unchanged=all(file_sha256(p)==sha for p,sha in before.items()),
        private_receipt_sha256=file_sha256(out/'T03_UNION_PRIVATE.json'))
    assert public['input_files_unchanged']
    write_json_once(out/'T03_UNION_PUBLIC.json',public);print(json.dumps(public,indent=2))


if __name__=='__main__':main()
