#!/usr/bin/env python3
"""Bind the pre-review coordinator AI notes; never upgrade automated refusals.

The notes were written after inspecting the fixed 37 source/input/reply cases,
before the automated reviewer outputs. This is a deterministic recording step,
not an independent human judgment or a new semantic classifier.
"""
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
OUT = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P2'


def read(path):
    return json.loads(path.read_text())


def main():
    target = OUT / 'coordinator_audit_decisions_private.json'
    if target.exists():
        raise RuntimeError('coordinator disposition already recorded')
    note_path = OUT / 'coordinator_pre_review_notes_private.json'
    prior = read(note_path)
    assert prior['status'] == 'COMPLETE_BEFORE_AUTOMATED_REVIEW'
    bound = read(OUT / 'review_format_v2/review_jobs_freeze.json')['files']
    assert bound[str(note_path.relative_to(PROJECT))] == sha256_file(note_path)
    original = {r['slot_id']: r for r in read(OUT / 'provisional_admission_private.json')['rows']}
    wanted = set(read(OUT / 'coordinator_audit_slots.json')['slot_ids'])
    assert len(prior['rows']) == len(wanted) == 37
    assert {r['slot_id'] for r in prior['rows']} == wanted
    rows = []
    for note in prior['rows']:
        source = original[note['slot_id']]
        assert source['author_raw_sha256'] == note['author_raw_sha256']
        assert sha256_file(Path(source['author_raw_path'])) == source['author_raw_sha256']
        assert sha256_file(Path(source['review_raw_path'])) == source['review_raw_sha256']
        observation = note['observation']
        assert observation in ('no_confirmed_error', 'reject', 'uncertain')
        override = None
        if observation in ('reject', 'uncertain') and source['status'] == 'accept':
            override = observation
        elif observation == 'reject' and source['status'] == 'uncertain':
            override = 'reject'
        rows.append(dict(slot_id=note['slot_id'], audit_index=note['audit_index'],
            author_raw_sha256=source['author_raw_sha256'], review_raw_sha256=source['review_raw_sha256'],
            prior_observation=observation, automatic_status=source['status'],
            rationale=note['rationale'], override_status=override,
            final_initial_status=override or source['status']))
    result = dict(status='COMPLETE', independent_human_gold=False,
        scope='Fixed 37-case source/input/reply coordinator AI audit, including known identity case; not a calibrated error-rate estimate',
        automatic_upgrades=0, rows=rows,
        cross_counts=dict(Counter(r['prior_observation'] + ' / ' + r['automatic_status'] for r in rows)),
        downgrades=sum(r['override_status'] is not None for r in rows),
        source_files={str(p.relative_to(PROJECT)): sha256_file(p) for p in
            [note_path, OUT / 'coordinator_audit_slots.json',
             OUT / 'provisional_admission_private.json', Path(__file__)]})
    with target.open('x') as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({k: v for k, v in result.items() if k not in ('rows', 'source_files')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
