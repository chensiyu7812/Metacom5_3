#!/usr/bin/env python3
"""Lock conditions before reading reply text or scoring. No model calls."""
from collections import Counter, defaultdict
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

ROOT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2'
OUT = ROOT / 'P3/calibration'
SEED = 'pm-rl1-p3-owner-separated-condition-selection-20261001-v1'


def read(p):
    return json.loads(p.read_text())


def order(tag, value):
    return digest([SEED, tag, value])


def main():
    OUT.mkdir(exist_ok=True)
    target = OUT / 'selection_lock_private.json'
    if target.exists():
        raise RuntimeError('selection already locked')
    common = ROOT / 'P3/common_evidence'
    freeze = read(common / 'input_freeze.json')
    for name, sha in freeze['files'].items():
        assert sha256_file(common / name) == sha, name
    for name, sha in freeze['source_files'].items():
        assert sha256_file(PROJECT / name) == sha, name
    mappings = read(common / 'source_map_private.json')
    evidence = read(common / 'evidence_pool_private.json')
    known_path = ROOT / 'P3/known_behavior_cases_private.json'
    known = {r['index'] for r in read(known_path)['rows']}
    by_index = {r['index']: r for r in mappings}
    dev_owners = {by_index[i]['owner'] for i in known}
    assert len(dev_owners) == 3
    development = [r for r in mappings if r['owner'] in dev_owners]
    validation = [r for r in mappings if r['owner'] not in dev_owners]
    assert len(development) == 18 and len(validation) == 24
    assert all(r['split'] == 'train' for r in validation)

    # Owner is the conservative fact-family envelope: all of that person's
    # events, entities, updates and repeated prefixes stay on the same side.
    session_hash_owners = defaultdict(set)
    for row in mappings:
        e = evidence[row['prefix_identity']]
        for session in e['legal_past_sessions']:
            session_hash_owners[digest([(t['role'], t['text']) for t in session['turns']])].add(row['owner'])
    cross_owner = [sorted(v) for v in session_hash_owners.values() if len(v) > 1]
    if cross_owner:
        raise ValueError('whole-session reuse across owners requires grouping before selection')

    chosen_dev = set(known)
    while len(chosen_dev) < 8:
        counts = Counter(by_index[i]['owner'] for i in chosen_dev)
        candidates = [r for r in development if r['index'] not in chosen_dev]
        chosen_dev.add(min(candidates, key=lambda r: (counts[r['owner']], order('dev-prefix', r['prefix_identity'])))['index'])
    owners = sorted({r['owner'] for r in validation})
    chosen_val = {min([r for r in validation if r['owner'] == owner],
        key=lambda r: order('validation-first', r['prefix_identity']))['index'] for owner in owners}
    remaining = sorted([r for r in validation if r['index'] not in chosen_val],
                       key=lambda r: order('validation-extra', r['prefix_identity']))
    chosen_val.update(r['index'] for r in remaining[:4])
    reserve = [r['index'] for r in remaining[4:]]
    assert len(chosen_val) == 16 and len(reserve) == 8

    paths = {}
    summaries = {}
    for name in ('primary', 'secondary'):
        pointer = ROOT / f'P2/common_pool/{name}_generation_pointer.json'
        paths[name] = Path(read(pointer)['run_dir'])
        summaries[name] = read(paths[name] / 'summary.json')['rows']
        assert all(r['finish_reason'] == 'natural_stop' for r in summaries[name])
    secondary = {(r['index'], r['plan_index']): r for r in summaries['secondary']}
    dev_order = sorted(chosen_dev, key=lambda i: order('contrast-allocation', by_index[i]['prefix_identity']))
    executor_indices = set(dev_order[:4])
    natural = []
    for group, indexes in [('development', sorted(chosen_dev)), ('validation', sorted(chosen_val)), ('reserve', reserve)]:
        for index in indexes:
            slots = [r for r in summaries['primary'] if r['index'] == index]
            off = next(r for r in slots if r['plan_index'] == 0)
            contrast = 'executor' if index in executor_indices else 'resource'
            if contrast == 'executor':
                candidates = [r for r in slots if (index, r['plan_index']) in secondary]
                left = min(candidates, key=lambda r: order('executor-plan', [r['prefix_identity'], r['counts']]))
                right = secondary[index, left['plan_index']]
                arms = ['primary', 'secondary']
            else:
                candidates = [r for r in slots if r['plan_index'] != 0]
                left = off
                right = min(candidates, key=lambda r: order('resource-plan', [r['prefix_identity'], r['counts']]))
                arms = ['primary', 'primary']
            natural.append(dict(group=group, index=index, owner=by_index[index]['owner'],
                prefix_identity=by_index[index]['prefix_identity'], contrast=contrast,
                pair_id=order('pair', [group, index, contrast])[:20],
                sides=[dict(arm=arm, **row, raw_path=str(paths[arm] / (row['request_id'] + '.raw.json')))
                       for arm, row in zip(arms, [left, right])]))
    result = dict(protocol=SEED, status='CONDITIONS_LOCKED_BEFORE_REPLY_READING_OR_SCORING',
        development_owners=sorted(dev_owners), validation_owners=owners,
        fact_family_rule='Whole owner history envelope, including all event/subject/time updates. No owner crosses the partition.',
        exact_whole_past_session_cross_owner_duplicates=cross_owner,
        semantic_limit='Not a claim that generic topics or every paraphrased cross-owner source are unique.',
        known_development_indices=sorted(known), natural_pairs=natural,
        control_slots=dict(development=[102, 104, 97, 96, 105, 111, 100, 109],
                           validation=[88, 64, 77, 38, 24, 40, 16, 49]),
        control_types=['identity', 'subject', 'currentness', 'intent_to_result',
                       'equivalent_wording', 'equivalent_wording', 'general_support', 'general_support'],
        control_selection='Source eligibility only; coordinator-authored targeted contrasts, not human gold.',
        reserve_trigger='Only fewer than eight clear natural human preferences; never low scorer agreement.',
        limitations=['Executor contrasts occur only in development, as secondary replies exist only for those three owners.',
                    'Validation labels will be sealed, but texts and sources are development research material, not a pristine final test.',
                    'Repeated pairs within owner are dependent; report pair, prefix and owner counts.'],
        reply_contents_read_by_this_script=0, model_calls=0,
        source_files={str(p.relative_to(PROJECT)): sha256_file(p) for p in [
            common / 'input_freeze.json', known_path, Path(__file__),
            *[p / 'summary.json' for p in paths.values()]]})
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps(dict(path=str(target), sha256=sha256_file(target),
        development_indices=sorted(chosen_dev), validation_indices=sorted(chosen_val), reserve_indices=reserve,
        natural_contrasts=dict(Counter(r['contrast'] for r in natural if r['group'] != 'reserve')))))


if __name__ == '__main__':
    main()
