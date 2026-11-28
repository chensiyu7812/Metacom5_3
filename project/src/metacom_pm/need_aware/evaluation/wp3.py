"""Bounded WP3 scoring: modified short protocol, same-task comparisons only."""
from .wp2 import require,unique,score_cell,counts,compare
from .short_mcq import score_short,PROTOCOL
from ..data.contracts import digest

ARMS=('B0','B1','B1s','E0','E0s','C','C+noise')


def score_requests(tasks,evaluations,requests,predictions,*,model,arm,kind='model'):
    require(arm in ARMS,'unplanned WP3 arm')
    ix=unique(requests,'logical_id'); tids={t.task_id for t in tasks}
    require(len(tids)==len(tasks) and set(evaluations)==tids,'task/evaluation population')
    selected={f'{t.task_id}|{arm}|{model}':dict(ix[f'{t.task_id}|{arm}|{model}']) for t in tasks}
    prediction_index=unique(predictions,'task_id')
    for t in tasks:
        r=selected[f'{t.task_id}|{arm}|{model}'];e=evaluations[t.task_id]
        require(r['task_id']==t.task_id and r['arm']==arm and r['model_label']==model,'request identity')
        require(r['persona_group']==t.persona_group,'wrong owner')
        require(r.get('scoring_protocol')==PROTOCOL,'protocol identity missing or changed')
        require(r.get('task_sha256')==digest(t.to_dict()),'task bytes/options/history changed')
        if r['status']=='not_evaluable':
            require(arm in ('C','C+noise') and r.get('structural_reason') in ('direct_unlocated','direct_over_cap'), 'unknown structural exception')
            if r['structural_reason']=='direct_unlocated':require(e.direct_status!='located_unique','located evidence mislabeled')
            else:
                require(e.direct_status=='located_unique' and r.get('full_direct_tokens',0)>r.get('input_cap',float('inf')),
                        'Direct over-cap requires native-token receipt')
            require(r.get('request_sha256') is None,'structural request has executable identity')
        else:
            require(r['status'] in ('ready','capacity_exceeded') and bool(r.get('request_sha256')),'invalid executable request')
            require(r.get('decode',{}).get('max_new_tokens')==64,'short protocol output cap changed')
            if arm in ('C','C+noise'):require(e.direct_status=='located_unique','missing Direct executed')
            if r['status']=='capacity_exceeded':
                require(arm not in ('C','C+noise'),'full Direct over cap must use the explicit structural exception')
                cap=r.get('capacity',{})
                require(cap.get('fits') is False and (cap.get('input_tokens',0)>cap.get('input_cap',float('inf')) or
                    cap.get('input_tokens',0)+64>cap.get('backend_cap',float('inf'))),'capacity failure needs native receipt')
                require(prediction_index[t.task_id]['status']=='capacity_exceeded','over-cap request cannot be executed')
                # Evaluation-only copy: this is a planned evaluable task with a
                # technical failure, not a structural hole. Input manifest intact.
                r['status']='ready'
    return score_cell(tasks,evaluations,selected,predictions,model=model,arm=arm,kind=kind,
                      allowed_arms=ARMS,score_function=score_short)


def paired_on_joint_eligible(left,right,policy):
    """Explicit planned intersection, retaining structural counts for each arm."""
    a,b=unique(left,'task_id'),unique(right,'task_id')
    require(set(a)==set(b),'different task sets; subset explicitly before comparison')
    joint=[t for t in sorted(a) if a[t]['eligible'] and b[t]['eligible']]
    result=compare([a[t] for t in joint],[b[t] for t in joint],policy)
    result.update(original_planned_tasks=len(a),left_structural=sum(not r['eligible'] for r in left),
                  right_structural=sum(not r['eligible'] for r in right),joint_predefined_evaluable=len(joint))
    return result


def holm_family(comparisons):
    ordered=sorted(comparisons,key=lambda r:r['mcnemar_p_two_sided'] if r['mcnemar_p_two_sided'] is not None else 1.)
    running=0.
    for i,r in enumerate(ordered):
        p=r['mcnemar_p_two_sided'];running=max(running,min(1.,(len(ordered)-i)*(p if p is not None else 1.)))
        r['mcnemar_p_holm']=running if p is not None else None
    return comparisons


def paired_frozen_subset(left,right,task_ids,policy):
    """Cross-model / bridge comparisons use preselected IDs, never correctness."""
    ids=set(task_ids);a,b=unique(left,'task_id'),unique(right,'task_id')
    require(len(ids)==len(task_ids) and ids<=set(a) and ids<=set(b),'frozen pair subset missing/duplicated')
    result=paired_on_joint_eligible([a[t] for t in sorted(ids)],[b[t] for t in sorted(ids)],policy)
    result.update(left_export_slots=len(a),right_export_slots=len(b),frozen_subset=len(ids))
    return result
