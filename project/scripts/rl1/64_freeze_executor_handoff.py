#!/usr/bin/env python3
"""Freeze the selected research executor and a blinded DEVELOPMENT pair pool.

All 18 fixed dev conditions are retained. No judge requests, preference labels,
test exam, new human form, or natural-support RL qualification are created.
"""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

OUT = PROJECT / 'outputs/pm_rl1/executor_training_20260930_v1'
PACK = PROJECT / 'outputs/pm_rl1/executor_coverage_20260929_v1/qualified_inputs'


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    path = OUT / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    tr = Path(read(OUT / 'training_pointer.json')['run_dir'])
    dg = Path(read(OUT / 'diagnostic_pointer.json')['run_dir'])
    selection, reload = read(tr / 'selection.json'), read(tr / 'reload.json')
    assert reload['passed'] and reload['fresh_process']
    assert selection == min(read(tr / 'epochs.json'), key=lambda x: (x['dev']['nll'], x['epoch']))
    selected_arm = f"epoch_{selection['epoch']}"
    manifests = {arm: read(dg / (arm + '.runtime.json')) for arm in ('base', selected_arm)}
    base = {k: v for k, v in manifests['base'].items() if k not in ('adapter', 'identity')}
    adapted = {k: v for k, v in manifests[selected_arm].items() if k not in ('adapter', 'identity')}
    assert base == adapted
    for name, expected in selection['adapter_files'].items():
        assert sha256_file(Path(selection['checkpoint']) / name) == expected
    contract = read(PACK / 'condition_contract_private.json')
    evidence = read(PACK / 'legal_evidence_private.json')
    rows = read(dg / 'summary.json')['rows']
    notes = {(r['index'], r['condition']): r for r in read(OUT / 'diagnostic_observations_private.json')['rows']}
    materials, keys = [], []
    for c in contract['conditions']:
        if c['split'] != 'dev':
            continue
        erow = evidence[c['index'] - 1]
        assert erow['prefix_identity'] == c['prefix_identity'] and digest(erow['evidence']) == erow['evidence_identity']
        pair = {}
        for arm in ('base', selected_arm):
            row = next(r for r in rows if r['arm'] == arm and r['index'] == c['index'] and r['condition'] == c['condition'])
            req = read(dg / (row['request_id'] + '.request.json'))
            raw = read(dg / (row['request_id'] + '.raw.json'))
            assert req['messages'] == c['messages'] and raw['finish_reason'] == 'natural_stop'
            pair[arm] = dict(text=raw['text'], request_id=row['request_id'], raw_identity=digest(raw))
        pid = digest(dict(prefix=c['prefix_identity'], messages=c['messages_identity'],
                          requests=[pair[a]['request_id'] for a in ('base', selected_arm)]))
        order = ('base', selected_arm) if int(pid[:8], 16) % 2 == 0 else (selected_arm, 'base')
        # Case IDs are administrative only. Hidden key contains method, condition,
        # resource counts and developer observations; payload contains none.
        cid = f'C{len(materials) + 1:03d}'
        payload = dict(case_id=cid, evidence=erow['evidence'],
                       response_A=pair[order[0]]['text'], response_B=pair[order[1]]['text'])
        materials.append(payload)
        keys.append(dict(case_id=cid, pair_identity=pid, payload_identity=digest(payload),
            owner=c['owner'], prefix_identity=c['prefix_identity'], index=c['index'], condition=c['condition'], counts=c['counts'],
            evidence_identity=erow['evidence_identity'], generator_visible_messages=c['messages'],
            A=dict(arm=order[0], **pair[order[0]]), B=dict(arm=order[1], **pair[order[1]]),
            developer_observation=notes[c['index'], c['condition']]['note'],
            independent_preference_gold=None))
    assert len(materials) == 18
    save('measurement_handoff/blind_materials_private.json', materials)
    save('measurement_handoff/coordinator_only/blind_key_private.json', keys)
    save('measurement_handoff/manifest.json', dict(status='DEVELOPMENT_POOL_READY_FOR_INTERFACE_ADAPTATION_NOT_A_FROZEN_JUDGE_EXAM',
        pairs=18, prefixes=len({k['prefix_identity'] for k in keys}), owners=len({k['owner'] for k in keys}),
        selection='All 18 predeclared dev diagnostic conditions; base versus NLL-selected checkpoint; no favorable-pair filtering',
        prior_outputs_known=True, independent_confirmation=False, judge_calls=0, new_human_forms=0, test_items=0,
        evidence='Identical complete legal current/past evidence for both replies; never reduced to one policy\'s retrieved resources',
        blindness='Method, checkpoint, resource count, cost and developer notes are stored only in coordinator key',
        next_steps=['Bind the two predeclared judge interfaces and context limits using primary model documentation',
            'Combine with previously evidenced source/error and style controls; freeze the finite run before judge execution',
            'Retain raw component results, uncertain and technical missingness; do not invent scalar reward or preference gold'],
        scalar_reward_frozen=False,
        files={p: sha256_file(OUT / 'measurement_handoff' / p) for p in
               ('blind_materials_private.json', 'coordinator_only/blind_key_private.json')}))
    save('executor_freeze.json', dict(version='X_l_coverage_20260930_v1',
        status='RESEARCH_EXECUTOR_VERSION_FROZEN_WITH_OBSERVED_FAILURES',
        selection_rule='Minimum token-weighted dev response+EOT NLL; no generation-based checkpoint replacement',
        selected_epoch=selection['epoch'], checkpoint=selection['checkpoint'], adapter_files=selection['adapter_files'],
        base_runtime_identity=manifests['base']['identity'], learned_runtime_identity=manifests[selected_arm]['identity'],
        renderer_identity=contract['renderer_identity'], same_inference_prompt=True,
        dataset_sha256=sha256_file(OUT / 'accepted_dataset_private.json'),
        dataset_freeze_sha256=sha256_file(OUT / 'dataset_freeze.json'),
        training_runtime_sha256=sha256_file(tr / 'runtime.json'), selection_sha256=sha256_file(tr / 'selection.json'),
        reload_sha256=sha256_file(tr / 'reload.json'), diagnostic_protocol_sha256=sha256_file(dg / 'protocol.json'),
        qualified_for_controlled_development_comparison=True, support_quality_improvement_established=False,
        natural_support_reward_qualified=False, eligible_for_natural_support_ppo=False,
        source_scope='Only reviewed selected inputs; unselected global memory inventory is not certified',
        supervision_scope='All four resource heads, but accepted training has only 0/1/2 resources; no 3/4-GET or repeated-same-head training coverage',
        observed_failure='Selected checkpoint invents assistant maternal experiences under OFF/R/L for dev prefix 15; preserve as negative result',
        no_automatic_retraining_or_reselection=True,
        runner_sha256=sha256_file(Path(__file__))))
    print(json.dumps(dict(executor='X_l_coverage_20260930_v1', selected_epoch=selection['epoch'],
                         dev_pairs=len(materials), judge_calls=0, natural_support_ppo=False)))


if __name__ == '__main__':
    main()
