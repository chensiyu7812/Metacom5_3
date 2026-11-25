"""Post-hoc observed-field accounting, never whole-reply success or RL reward."""
import argparse,json
from collections import defaultdict,Counter
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256,write_json_once


def run(source,out):
    rows=[json.loads(s) for s in Path(source).read_text().splitlines()]
    groups=defaultdict(dict)
    for row in rows:
        if row['arm'] in groups[row['task_id']]:raise ValueError('duplicate arm')
        groups[row['task_id']][row['arm']]=row
    assert len(groups)==18 and all(set(g)=={'BASE','RAW'} for g in groups.values())
    def status(r):
        d=r.get('body_diagnostic')
        return 'not_assessed' if not d or d.get('value_correct') is None else 'observed_match' if d['value_correct'] else 'observed_nonmatch'
    selected=[];paired=Counter();table=[]
    for task,g in sorted(groups.items()):
        b,r=g['BASE'],g['RAW'];paired[status(b)+' -> '+status(r)]+=1
        known=[v for v in (b,r) if status(v)=='observed_match']
        chosen=min(known,key=lambda v:v['actual_cost']['input_tokens']) if known else None
        if chosen:selected.append(chosen)
        table.append(dict(task_id=task,BASE=status(b),RAW=status(r),
            lowest_input_observed_match_arm=chosen['arm'] if chosen else None,
            formal_reward=None))
    def totals(rs):
        return dict(status_counts=dict(Counter(status(r) for r in rs)),
            input_tokens=sum(r['actual_cost']['input_tokens'] for r in rs),
            output_tokens=sum(r['actual_cost']['output_tokens'] for r in rs),
            generation_seconds=sum(r['actual_cost']['seconds'] for r in rs),
            selected_RAW=sum(r['arm']=='RAW' for r in rs))
    result=dict(protocol='structured-observed-field-posthoc-upper-bound-v1',post_hoc=True,
        original_strict_scores_unchanged=True,formal_reward=None,semantic_qualification=False,
        source_sha256=file_sha256(source),code_sha256=file_sha256(__file__),
        by_arm={arm:totals([r for r in rows if r['arm']==arm]) for arm in ('BASE','RAW')},
        privileged_lowest_input_known_match=totals(selected),paired_observed_field_changes=dict(paired),rows=table,
        limits=['Matches require an extracted field; unparsed replies are not assessed, not semantic failures.',
            'A matching value is not sufficient evidence attribution, whole-reply success, support quality, or reward.',
            'Privileged selection uses actual outputs and references; it is not an executable policy or formal PM Oracle.',
            'Block-external text remains unassessed here; original replies and strict failures remain unchanged.',
            'Do not infer a learned-policy or quality gain from token-only savings.'])
    write_json_once(Path(out),result)
    return {k:v for k,v in result.items() if k!='rows'}


if __name__=='__main__':
    p=argparse.ArgumentParser()
    for name in ('source','out'):p.add_argument('--'+name,required=True)
    print(json.dumps(run(**vars(p.parse_args())),indent=2))
