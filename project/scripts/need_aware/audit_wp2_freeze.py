#!/usr/bin/env python3
"""Review old/new execution requests without reading model outputs or using a GPU."""
import argparse
from collections import Counter
import json
from pathlib import Path

from metacom_pm.need_aware.data.contracts import digest, load_runtime
from metacom_pm.need_aware.evaluation.score import load_eval
from metacom_pm.need_aware.evaluation.wp2 import require, unique, validate_population, validate_requests
from metacom_pm.need_aware.evaluation.evidence_audit import audit_evidence
from evaluate_wp2 import read, jsonl, bound, sha


def audit(a):
    policy = read(a.policy)
    root = Path(a.artifacts)
    bound(root/'FREEZE.json', policy['dataset_freeze_sha256'])
    for p, h in read(root/'FREEZE.json')['artifacts'].items():
        bound(root/p, h)
    tasks = load_runtime(root/'runtime/tasks.mcq.jsonl')
    ev = load_eval(root/'evaluation/tasks.mcq.jsonl')
    validate_population(tasks, ev, policy)
    manifests, indices = [], []
    for location in (a.old, a.new):
        md = Path(location)
        m = read(md/'MANIFEST.json')
        bound(md/m['requests_file'], m['requests_sha256'])
        require(m['runtime_tasks_sha256'] == policy['runtime_tasks_sha256'], 'runtime tasks changed')
        require(m['direct_sha256'] == policy['direct_manifest_sha256'], 'Direct changed')
        rows = jsonl(md/m['requests_file'])
        index = validate_requests(tasks, ev, rows)
        require([r['logical_id'] for r in rows] == [r['logical_id'] for r in m['requests']], 'manifest order changed')
        for r in rows:
            if r['status'] != 'ready':
                continue
            actual = 'naareq:'+digest(dict(version=r['versions']['request'], g_id=r['g_id'],
                                          messages=r['messages'], input_ids=r['input_ids'], decode=r['decode']))
            require(r['request_sha256'] == actual, 'physical request hash mismatch')
        manifests.append(m); indices.append(index)
    old, new = manifests
    require(old['logical_slots_sha256'] == new['logical_slots_sha256'], 'logical source changed')
    # Model scheduling may be reordered before execution; each model retains
    # the same frozen task/arm sequence and its own independent time budget.
    for model in ('G0e', 'Qwen35'):
        require([k for k, r in indices[0].items() if r['model_label'] == model] ==
                [k for k, r in indices[1].items() if r['model_label'] == model], 'within-model slot order changed')
    require(old['bindings'] == new['bindings'], 'model bindings changed')
    require(new['caps']['max_gpu_seconds'] == 57600 and new['caps']['max_physical_calls'] == 1920, 'authorized total budget')
    counts, transitions = Counter(), []
    for lid, before in indices[0].items():
        after = indices[1][lid]
        require(before['status'] == after['status'], 'slot eligibility changed')
        arm = before['arm']
        if before['status'] != 'ready':
            counts['structural_unchanged'] += 1
            continue
        ids_changed = before['trace']['delivered_ids'] != after['trace']['delivered_ids']
        counts[arm+'_delivered_ids_changed'] += ids_changed
        if arm in 'CD':
            require(not ids_changed, 'Direct evidence changed: '+arm)
            require(before['trace']['delivered_text_sha256'] == after['trace']['delivered_text_sha256'], 'Direct source text changed')
        if arm != 'D':
            # A shared speaker-label clarification can alter packing before
            # execution. Disclose it; immutable tasks and legal evidence are
            # the user-required boundary, not byte-identical old CPU prompts.
            require(before['decode'] == after['decode'], 'decode changed')
            unchanged = all(before[k] == after[k] for k in ('messages', 'input_ids', 'request_sha256'))
            counts[arm+'_exact_unchanged' if unchanged else arm+'_request_changed'] += 1
        else:
            require(before['request_sha256'] != after['request_sha256'], 'D semantic repair did not change request')
            counts['D_same_evidence_new_request'] += 1
        transitions.append(dict(logical_id=lid, arm=arm, old_request_sha256=before['request_sha256'], new_request_sha256=after['request_sha256'], delivered_ids_changed=ids_changed))
    diagnostic = audit_evidence(tasks, root/'runtime', jsonl(root/'direct/direct.jsonl'), indices[1])
    receipt = dict(protocol='naa-wp2-joint-freeze-audit-v1', evaluation_rules_sha256=sha(a.policy),
                   dataset_freeze_sha256=sha(root/'FREEZE.json'), frozen_artifact_files=len(read(root/'FREEZE.json')['artifacts']),
                   old_manifest_sha256=digest(old), new_manifest_sha256=digest(new),
                   old_model_order=old['model_order'], new_model_order=new['model_order'],
                   old_requests_sha256=old['requests_sha256'], new_requests_sha256=new['requests_sha256'],
                   counts=dict(counts), model_output_read=False, model_calls=0,
                   coverage_classes={m: dict(Counter(v[m]['coverage_class'] for v in diagnostic.values())) for m in ('G0e', 'Qwen35')})
    out = Path(a.out); out.mkdir(parents=True, exist_ok=False)
    (out/'JOINT_FREEZE_AUDIT.json').write_text(json.dumps(receipt, indent=2)+'\n')
    (out/'REQUEST_TRANSITIONS.private.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in transitions))
    (out/'EVIDENCE_DIAGNOSTICS.private.json').write_text(json.dumps(diagnostic, indent=2)+'\n')
    return receipt


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for key in ('artifacts', 'policy', 'old', 'new', 'out'):
        p.add_argument('--'+key, required=True)
    print(json.dumps(audit(p.parse_args()), indent=2))
