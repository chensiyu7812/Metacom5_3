#!/usr/bin/env python3
"""Record individual review and freeze the deduplicated old/new accepted union."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import HEADS, digest
from metacom_pm.rl1.executor_coverage import admitted_supplement, merge_accepted, coverage
from metacom_pm.rl1.executor_engineering import admitted_rows

OUT = PROJECT / 'outputs/pm_rl1/executor_training_20260930_v1'
SOURCE = PROJECT / 'outputs/pm_rl1/executor_coverage_20260929_v1'
PACK = SOURCE / 'qualified_inputs'
OLD = PROJECT / 'outputs/pm_rl1/executor_engineering_20260929_v1'


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    with (OUT / name).open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    binding = importlib.util.spec_from_file_location('source_gate', PROJECT / 'scripts/rl1/59_author_coverage_supplement.py')
    gate = importlib.util.module_from_spec(binding)
    binding.loader.exec_module(gate)
    contract, work, receipt = gate.preflight()
    run = Path(read(SOURCE / 'author_pointer.json')['run_dir'])
    jobs = read(run / 'jobs.json')
    runtime = read(run / 'runtime.json')
    assert runtime['contract_sha256'] == sha256_file(PACK / 'condition_contract_private.json')
    assert runtime['preflight_identity'] == digest(receipt)
    expected = {(j['index'], j['condition'], j['seed']) for j in work['jobs'] if j['action'] == 'generate_once'}
    assert {(j['index'], j['condition'], j['seed']) for j in jobs} == expected and len(jobs) == len(expected) == 82
    summary = read(run / 'summary.json')
    assert {r['request_id'] for r in summary['rows']} == {j['request_id'] for j in jobs}
    decisions = read(OUT / 'decisions_private.json')
    assert set(decisions) == {f'{i}/{c}/{s}' for i, c, s in expected}
    evidence = read(PACK / 'legal_evidence_private.json')
    requests, raws, reviews = {}, {}, []
    guards = [PACK / 'condition_contract_private.json', PACK / 'freeze_manifest.json',
        SOURCE / 'author_pointer.json', run / 'jobs.json', run / 'runtime.json', run / 'summary.json',
        OUT / 'decisions_private.json', Path(__file__), PROJECT / 'src/metacom_pm/rl1/executor_coverage.py',
        PROJECT / 'src/metacom_pm/rl1/executor_encoding.py', PROJECT / 'src/metacom_pm/rl1/executor_engineering.py']
    guards += [PROJECT / p for p in contract['source_guard']]
    for j in jobs:
        rid = j['request_id']
        req_path, raw_path = run / (rid + '.request.json'), run / (rid + '.raw.json')
        req, raw = read(req_path), read(raw_path)
        assert req['executor_identity'] == runtime['identity']
        decision = decisions[f"{j['index']}/{j['condition']}/{j['seed']}"]
        accepted = decision['status'] == 'accept'
        review = dict(**decision, request_identity=rid, raw_identity=digest(raw),
            messages_identity=digest(req['messages']), evidence_identity=evidence[j['index'] - 1]['evidence_identity'],
            index=j['index'], condition=j['condition'], seed=j['seed'], split=j['split'],
            checks=dict(technical_completion=raw['finish_reason'] == 'natural_stop', exact_input=True,
                        semantic_source_time_task_admission=accepted),
            unresolved_claims=[decision['rationale']] if decision['status'] == 'uncertain' else [],
            review_scope='Complete exact visible prefix/resources and output read; selected-source full-context audit inherited. AI-assisted weak supervision, not human gold or a reward.')
        reviews.append(review)
        requests[rid], raws[rid] = req, raw
        guards.extend((req_path, raw_path))
    review_doc = dict(reviewer=contract['admission']['reviewer'], independent_human_truth=False,
        contract_sha256=sha256_file(PACK / 'condition_contract_private.json'),
        author_runtime_sha256=sha256_file(run / 'runtime.json'),
        decision_table_sha256=sha256_file(OUT / 'decisions_private.json'), repairs=0, old_q_m_used=False, rows=reviews)
    new_rows = admitted_supplement(contract, jobs, requests, raws, {r['request_identity']: r for r in reviews}, evidence)
    old_contract = read(OLD / 'condition_contract_private.json')
    old_run = Path(read(OLD / 'author_pointer.json')['run_dir'])
    old_jobs = read(old_run / 'jobs.json')
    old_requests = {j['request_id']: read(old_run / (j['request_id'] + '.request.json')) for j in old_jobs}
    old_raws = {j['request_id']: read(old_run / (j['request_id'] + '.raw.json')) for j in old_jobs}
    old_reviews = {r['request_identity']: r for r in read(OLD / 'admission_reviews_private.json')['rows']}
    old_rows = admitted_rows(old_contract, old_jobs, old_requests, old_raws, old_reviews)
    assert old_rows == read(OLD / 'accepted_dataset_private.json')['rows'] and len(old_rows) == 90
    guards += [OLD / p for p in ('condition_contract_private.json', 'author_pointer.json',
        'admission_reviews_private.json', 'accepted_dataset_private.json')]
    guards += [old_run / (j['request_id'] + suffix) for j in old_jobs for suffix in ('.request.json', '.raw.json')]
    normalized_old = [dict(r, counts=[int(h == r['head']) for h in HEADS], provenance_batch='repaired_pilot_v2',
        resource_behavior='original_review_preserved') for r in old_rows]
    merged, duplicates = merge_accepted(normalized_old, new_rows)
    save('admission_reviews_private.json', review_doc)
    save('accepted_dataset_private.json', dict(status='SOURCE_REVIEWED_AI_WEAK_SUPERVISION_NOT_HUMAN_GOLD', rows=merged,
        dataset_identity=digest(merged), old_accepted=90, newly_accepted=len(new_rows), exact_duplicates=duplicates,
        input_contract_sha256=sha256_file(PACK / 'condition_contract_private.json'),
        reviews_sha256=sha256_file(OUT / 'admission_reviews_private.json'), old_dataset_sha256=sha256_file(OLD / 'accepted_dataset_private.json')))
    reused = [dict(index=j['index'], condition=j['condition'], seed=j['seed'],
        origin_request_id=j['provenance']['origin_request_id'],
        original_status=old_reviews[j['provenance']['origin_request_id']]['status'],
        original_review_identity=digest(old_reviews[j['provenance']['origin_request_id']]))
        for j in work['jobs'] if j['action'] == 'reuse_existing']
    save('reused_review_provenance.json', reused)
    accepted_cells = Counter((r['index'], r['condition']) for r in reviews if r['status'] == 'accept')
    accepted_cells.update((r['index'], r['condition']) for r in reused if r['original_status'] == 'accept')
    cov = coverage(merged)
    save('admission_summary.json', dict(new_statuses=dict(Counter(r['status'] for r in reviews)),
        new_by_split={s: dict(Counter(r['status'] for r in reviews if r['split'] == s)) for s in ('train', 'dev')},
        reused_statuses=dict(Counter(r['original_status'] for r in reused)), coverage=cov,
        missing_supplement_cells=[dict(index=c['index'], condition=c['condition']) for c in contract['conditions']
                                  if not accepted_cells[c['index'], c['condition']]],
        all_four_heads_and_combinations_represented=all(cov['train']['by_head'].values()) and cov['train']['multiple_resources'] > 0,
        duplicates_removed=len(duplicates), repairs=0, new_human_labels=0, paid_API_usd=0,
        statement='Structural training coverage, not resource-use competence, reward qualification, or independent support-quality evidence.'))
    # Bind every input and review before any parameter update. New trainer must
    # verify these hashes; old sources/results are never rewritten.
    guards += [OUT / p for p in ('admission_reviews_private.json', 'accepted_dataset_private.json',
                               'reused_review_provenance.json', 'admission_summary.json')]
    save('dataset_freeze.json', dict(status='FROZEN_BEFORE_PARAMETER_UPDATES',
        contract=str(PACK / 'condition_contract_private.json'), dataset_identity=digest(merged),
        files={str(p.relative_to(PROJECT)): sha256_file(p) for p in sorted(set(guards))}))
    print(json.dumps(dict(new_statuses=dict(Counter(r['status'] for r in reviews)), coverage=cov, duplicates=len(duplicates))))


if __name__ == '__main__':
    main()
