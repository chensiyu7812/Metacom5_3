"""A source decisions -> B reply trainer. No target is used to render/retrieve evidence."""
from .contracts import digest
from ..agent import behavior as B
from ..memory import reader as R

VERSION='naa-official-reply-joint-v1'


def delivered(task, supply, store):
    if supply['task_sha256'] != digest(task.to_dict()) or store.owner_id != task.persona_group:
        raise ValueError('foreign supply/task/owner')
    ids=supply['trace']['delivered_ids'];by=store.by_id()
    if len(ids)!=len(set(ids)):
        raise ValueError('duplicate evidence id')
    units=[by[i] for i in ids]
    expected={x['source_id']:x['original_text_sha256'] for x in supply['evidence_records']}
    if {u.unit_id:u.original_text_sha256 for u in units}!=expected:
        raise ValueError('evidence bytes differ from frozen delivery')
    return R.Packed(units=tuple(units),priority_ids=tuple(ids),skipped_over_budget=(),
                    tokens=supply['trace']['evidence_tokens'])


def row(candidate, task, supply, store):
    """One checked relative negative at most; unreviewed alternatives remain masked."""
    if candidate['split'] not in ('fit','tune') or not candidate['sft_eligible']:
        raise ValueError('only eligible fit/tune enters the trainer')
    if task.task_mode!='generation' or task.options:
        raise ValueError('reply input must be gold-free generation task')
    if candidate['owner']!=task.persona_group or candidate['task_id']!=task.task_id:
        raise ValueError('candidate source mismatch')
    if digest(candidate['positive'])!=candidate['source_reply_sha256']:
        raise ValueError('official positive changed')
    if digest(candidate['negatives'])!=candidate['source_negative_sha256']:
        raise ValueError('official negatives changed')
    packed=delivered(task,supply,store)
    messages,trace=B.build('U0',task,store,packed,recall_suffix=False)
    indices=candidate['pair_negative_indices'][:1]
    return dict(example_id=task.task_id,group_id=task.task_id,owner_id=task.persona_group,
        history_family=task.source_family,split=candidate['split'],messages=messages,
        chosen=candidate['positive'],rejected=[candidate['negatives'][i] for i in indices],
        provenance=dict(schema=VERSION,plumbing=False,source_row=candidate['source_row'],
            revision=task.dataset_revision,history_sha256=task.history_sha256,
            source_reply_sha256=candidate['source_reply_sha256'],runtime_sha256=candidate['runtime_sha256'],
            original_request_sha256=digest(task.user_query),delivered_ids=trace['delivered_ids'],
            delivered_text_sha256=supply['trace']['delivered_text_sha256'],
            positive_status=candidate['positive_status'],negative_indices=indices,
            negative_relation='reviewed dataset-relative preference; not absolute harm/falsehood',
            renderer=B.BEHAVIOR_VERSION,recall_suffix=False,class_weight=1.0))
