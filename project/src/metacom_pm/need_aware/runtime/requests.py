"""Logical requests, exact-request identity and de-duplication for NAA batch runs.

request_sha256 covers only what the generator actually receives (generator binding,
messages, native input ids, decode). Two logical slots with the same request_sha256
are ONE physical call: the second is an exact reuse, never an independent observation.
"""
from __future__ import annotations

from ..data.contracts import digest

REQUEST_VERSION = 'naa-request-v1'


def physical_identity(g_id, messages, input_ids, decode):
    return 'naareq:' + digest(dict(version=REQUEST_VERSION, g_id=g_id, messages=messages,
                                   input_ids=input_ids, decode=decode))


def logical_id(task_id, arm, model_label):
    return f'{task_id}|{arm}|{model_label}'


def make(task, arm, spec, messages, input_ids, decode, trace, capacity, versions):
    return dict(logical_id=logical_id(task.task_id, arm, spec.label), task_id=task.task_id,
                task_mode=task.task_mode, persona_group=task.persona_group, arm=arm, model_label=spec.label,
                model_id=spec.model_id, g_id=spec.g_id, decode=decode, messages=messages,
                input_ids=input_ids, input_ids_sha256=digest(input_ids), capacity=capacity,
                trace=trace, versions=versions, status='ready' if capacity['fits'] else 'capacity_exceeded',
                request_sha256=physical_identity(spec.g_id, messages, input_ids, decode))


def not_evaluable(task, arm, spec, reason, versions):
    return dict(logical_id=logical_id(task.task_id, arm, spec.label), task_id=task.task_id,
                task_mode=task.task_mode, persona_group=task.persona_group, arm=arm, model_label=spec.label,
                model_id=spec.model_id, g_id=spec.g_id, status='not_evaluable', reason=reason,
                versions=versions, request_sha256=None)


def deduplicate(rows):
    """Mark exact repeats; the first occurrence in manifest order owns the physical call."""
    owner = {}
    for row in rows:
        sha = row.get('request_sha256')
        if row['status'] != 'ready' or sha is None:
            continue
        if sha in owner:
            row['duplicate_of'] = owner[sha]
        else:
            owner[sha] = row['logical_id']
    return dict(physical_unique=len(owner), logical_ready=sum(r['status'] == 'ready' for r in rows),
                exact_duplicates=sum('duplicate_of' in r for r in rows))
