#!/usr/bin/env python3
"""Bind the selected P2 executor after behavior selection and a fresh reload.

The existing source-scoped request wrapper adds coordinator provenance to the
cache key, without changing any model-visible message or decoding setting.
"""
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.bound_generation import PROTOCOL

OUT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P2'


def read(path):
    return json.loads(path.read_text())


def main():
    target = OUT / 'executor_freeze.json'
    if target.exists():
        raise RuntimeError('executor already frozen')
    dataset = read(OUT / 'dataset_freeze.json')
    for name, expected in dataset['files'].items():
        assert sha256_file(PROJECT / name) == expected, name
    selection = read(OUT / 'executor_selection.json')
    training = Path(read(OUT / 'training_pointer.json')['run_dir'])
    diagnostic = Path(read(OUT / 'diagnostic_pointer.json')['run_dir'])
    guards = [OUT / 'dataset_freeze.json', OUT / 'executor_selection.json',
              OUT / 'behavior_reviews_private.json', training / 'summary.json',
              training / 'runtime.json', training / 'epochs.json',
              diagnostic / 'summary.json', diagnostic / 'protocol.json',
              PROJECT / 'src/metacom_pm/rl1/generation.py',
              PROJECT / 'src/metacom_pm/rl1/bound_generation.py',
              PROJECT / 'scripts/rl1/89_select_p2_executor.py', Path(__file__)]
    assert sha256_file(OUT / 'behavior_reviews_private.json') == selection['review_sha256']
    assert sha256_file(diagnostic / 'summary.json') == selection['diagnostic_summary_sha256']
    assert sha256_file(PROJECT / 'scripts/rl1/89_select_p2_executor.py') == selection['script_sha256']
    # Epoch 1 also records the unchanged base runtime before adapter loading.
    epoch_one = read(diagnostic / 'epoch_1.runtime.json')
    assert digest({k: v for k, v in epoch_one.items() if k != 'identity'}) == epoch_one['identity']
    base = {k: v for k, v in epoch_one.items() if k != 'identity'}
    base['adapter'] = None
    guards.append(diagnostic / 'epoch_1.runtime.json')
    if selection['selected'] == 'base':
        assert selection['status'] == 'BASE_SELECTED_NO_ADAPTER_PASSED'
        primary = base
    else:
        assert selection['status'] == 'ADAPTER_SELECTED_RELOAD_PENDING'
        chosen = read(training / 'selection.json')
        reload = read(training / 'reload.json')
        assert reload['passed'] and reload['fresh_process'] and reload['training_updates'] == 0
        assert chosen['checkpoint'] == selection['selected_checkpoint'] == reload['checkpoint']
        assert chosen['behavior_review_sha256'] == selection['review_sha256']
        runtime_path = diagnostic / (selection['selected'] + '.runtime.json')
        actual = read(runtime_path)
        primary = {k: v for k, v in actual.items() if k != 'identity'}
        assert digest(primary) == actual['identity']
        assert {k: v for k, v in primary.items() if k != 'adapter'} == {k: v for k, v in base.items() if k != 'adapter'}
        assert primary['adapter']['files'] == chosen['adapter_files']
        assert primary['adapter']['path'] == chosen['checkpoint']
        for name, expected in chosen['adapter_files'].items():
            path = Path(chosen['checkpoint']) / name
            assert sha256_file(path) == expected
            guards.append(path)
        guards.extend([training / 'selection.json', training / 'reload.json', runtime_path])
    for name, expected in base['model_files'].items():
        assert sha256_file(Path(base['model_dir']) / name) == expected, name
    runtimes = {}
    for arm, runtime in [('primary', primary), ('base', base)]:
        scoped = dict(runtime, request_protocol=PROTOCOL,
                      binding_code_sha256=sha256_file(PROJECT / 'src/metacom_pm/rl1/bound_generation.py'))
        runtimes[arm] = dict(scoped, identity=digest(scoped))
    freeze = dict(status='FROZEN_FOR_COMMON_POOL_NOT_REWARD_QUALIFICATION',
        selected=selection['selected'], primary_runtime=runtimes['primary'],
        base_runtime=runtimes['base'],
        renderer_identity=read(OUT / 'slot_freeze.json')['renderer_identity'],
        terminal_draw_identity='pm-rl1-completion-v2-terminal-greedy-seed0',
        request_identity='Existing BoundResourceEnv/BoundNaturalGenerator provenance protocol; actor/critic never receive provenance',
        selection_rule=selection['rule'],
        source_supervision='AI weak supervision; same Qwen author/reviewer plus finite coordinator AI audit',
        quality_gain_established=False, natural_support_reward_qualified=False,
        eligible_for_natural_support_ppo=False,
        eligibility_scope='At P2 freeze only: a separately bound calibrated P3 measurement protocol is required before P4; this snapshot does not claim that future calibration has already happened.',
        files={str(p.relative_to(PROJECT)): sha256_file(p) for p in sorted(set(guards))})
    with target.open('x') as f:
        f.write(json.dumps(freeze, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(status=freeze['status'], selected=selection['selected'],
        executor_identity=runtimes['primary']['identity'], new_G=0, new_J=0)))


if __name__ == '__main__':
    main()
