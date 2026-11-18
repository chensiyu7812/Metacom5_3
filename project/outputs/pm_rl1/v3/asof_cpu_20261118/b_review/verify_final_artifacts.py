"""Independent B artifact audit against pinned Git evidence; no A compiler import."""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import subprocess

PR12 = '8ba20d21da4bdcbb552946241563bd41dbe46c6c'
PR13 = 'ea2f5bde04caba4590b26c80a572d66caa4a2d08'
V3 = 'project/outputs/pm_rl1/v3/'


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def lines(path):
    return [json.loads(x) for x in path.read_text().splitlines()]


def git_json(root, commit, path, jsonl=False):
    raw = subprocess.check_output(['git', '-C', str(root), 'show', commit + ':' + path]).decode()
    return [json.loads(x) for x in raw.splitlines()] if jsonl else json.loads(raw)


def verify(root, out):
    base = root / (V3 + 'asof_cpu_20261118')
    cpu = base / 'cpu_v3'
    checks = []
    manifest = json.loads((cpu / 'MANIFEST.json').read_text())
    assert digest({k: v for k, v in manifest.items() if k != 'manifest_sha256'}) == manifest['manifest_sha256']
    assert all(sha(cpu / path) == expected for path, expected in manifest['outputs'].items())
    assert all(sha(root / path) == expected for path, expected in manifest['code'].items())
    checks.append('cpu_v3 manifest, all output hashes and current code hashes')

    original54 = git_json(root, PR13, V3 + 'resource_architecture_review_20261118/cpu/PROPOSED_JOBS.json')
    copied54 = json.loads((cpu / 'FIXED_54_PROPOSAL_COPY.json').read_text())
    assert original54 == copied54
    matrix54 = lines(cpu / 'INPUT_54_ELIGIBILITY.jsonl')
    assert len(matrix54) == len(original54['jobs']) == 54
    for old, new in zip(original54['jobs'], matrix54):
        assert (old['plan_job_id'], old['prefix_id'], old['subset'], old['existing_request_id']) == (
            new['plan_job_id'], new['prefix_id'], new['subset'], new['old_request_id'])
        expected = 'BLOCKED' if 'MP' in old['subset'] else 'ELIGIBLE' if old['subset'] in ('OFF', 'MS') else 'LEGACY_DIAGNOSTIC'
        assert new['status'] == expected
        assert new['quality'] is None and new['result'] is None
        assert new['worth_reading'] is None and new['relevant_but_need_not_mention'] is None
    checks.append('54 original job identities, order, prefixes, subsets and request mappings unchanged')

    original83 = git_json(root, PR12, V3 + 'relevance_review_20261118/REVIEW_SAMPLES.jsonl', True)
    selection = json.loads((cpu / 'FIXED_83_SELECTION.json').read_text())
    assert selection == [dict(sample_id=r['sample_id'], selected_record_id=r['selected_record_id']) for r in original83]
    matrix83 = lines(cpu / 'SAMPLE_83_ELIGIBILITY.jsonl')
    assert len(matrix83) == len(original83) == 83
    for old, new in zip(original83, matrix83):
        assert new['sample_id'] == old['sample_id']
        assert new['selected']['record_id'] == old['selected_record_id']
        expected = 'BLOCKED' if old['selected_record_id'] is None or old['head'] == 'MP' else 'ELIGIBLE' if old['head'] == 'MS' else 'LEGACY_DIAGNOSTIC'
        assert new['status'] == expected
    all_candidates = lines(cpu / 'ALL_SAMPLE_CANDIDATE_ELIGIBILITY.jsonl')
    assert [(r['sample_id'], r['record_id'], r['rank']) for r in all_candidates] == [
        (r['sample_id'], c['record_id'], i + 1) for r in original83 for i, c in enumerate(r['legal_candidates'])]
    checks.append('83 original selections and every candidate occurrence retained')

    requests = git_json(root, PR12, V3 + 'G0e_binding_20261118/CPU_REQUESTS_ONLY.jsonl', True)
    preserved = lines(cpu / 'OLD_120_REQUEST_PRESERVATION.jsonl')
    assert len(requests) == len(preserved) == 120
    for old, new in zip(requests, preserved):
        assert (old['request_id'], old['prefix_id'], old['terminal_key_sha256']) == (
            new['request_id'], new['prefix_id'], new['terminal_key_sha256'])
        assert digest(old['input_ids']) == new['input_ids_sha256']
        assert digest(old['messages']) == new['messages_sha256']
        assert new['generated'] is False and new['retokenized'] is False
    checks.append('120 old request, key, messages and native token ID hashes preserved')

    bindings = git_json(root, PR12, V3 + 'G0e_binding_20261118/KEY_BINDINGS.jsonl', True)
    by_id = {r['request_id']: r for r in requests}
    by_binding = {r['request_sha256']: r for r in bindings}
    typed = lines(cpu / 'TYPED_REQUEST_PROPOSALS.jsonl')
    assert len(typed) == 54
    for job, new in zip(original54['jobs'], typed):
        old = by_id[job['existing_request_id']]
        readings = by_binding[old['request_id']]['new_trace']['readings']
        assert new['messages'][0] == old['messages'][0]
        if readings:
            for view in readings:
                assert '<evidence>' + html.escape(view['reading_text']) + '</evidence>' in new['messages'][1]['content']
            assert new['messages'][2:] == old['messages'][2:]
        else:
            assert new['messages'] == old['messages']
        assert new['executable'] is False and new['legacy_result_reuse'] is False
        assert new['input_ids'] is None and new['terminal_result'] is None
    checks.append('54 typed proposals preserve identical source evidence and visible prefixes; no results reused')

    raw_rows = lines(root / (V3 + 'A1_preparation/final/registry/sources.jsonl'))
    source_map = {(r['source']['owner_id'], r['source']['session_id']): r['source'] for r in raw_rows}
    oracle = json.loads((base / 'b_review/RAW_FRONTIER_ORACLE.json').read_text())
    snapshot_paths = list((cpu / 'snapshots').glob('*.json'))
    assert len(snapshot_paths) == oracle['cut_count'] == 65
    for cut in oracle['cuts']:
        snapshot = json.loads((cpu / 'snapshots' / f"{cut['owner_id']}-r{cut['cutoff_rank']:02d}.json").read_text())
        assert digest({k: v for k, v in snapshot.items() if k != 'snapshot_sha'}) == snapshot['snapshot_sha']
        expected = cut['expected_sources']
        actual = snapshot['source_frontier']['sources']
        assert [(r['session_id'], r['chronological_rank'], r['family_id'], r['transcript_sha256']) for r in actual] == [
            (r['session_id'], r['rank'], r['family_id'], r['transcript_sha256']) for r in expected]
        assert all(r['review_status'] != 'human_approved' for r in snapshot['ledger_prefix'])
    ledger = lines(cpu / 'LEDGER.jsonl')
    assert len(ledger) == 93
    assert sum(r['kind'] == 'MS_RAW' for r in ledger) == 68
    assert all(r['review_status'] != 'human_approved' for r in ledger)
    checks.append('65 persisted snapshots match independent RAW oracle; 68 RAW commits and 93 ledger rows; zero human approvals')

    migration = lines(root / (V3 + 'A1b_preparation/measured_v1/bank/migration.jsonl'))
    quarantined = {r['old_id']: r for r in migration if r['old_head'] == 'MP' and r['status'] == 'quarantine'}
    risk = json.loads((cpu / 'LEGACY_LATEST_RISK.json').read_text())
    assert len(quarantined) == risk['quarantined_count'] == len(risk['cases']) == 324
    assert set(quarantined) == {r['old_id'] for r in risk['cases']}
    for row in risk['cases']:
        assert row['replacement_ids'] == quarantined[row['old_id']]['replacement_ids']
        assert all(rank > row['rank'] for rank in row['replacement_ranks'])
        assert row['readmitted_to_bank'] is False
        for ref in row['source_refs']:
            source = source_map[(ref['owner_id'], ref['session_id'])]
            turn = source['turns'][ref['turn_index']]
            assert source['chronological_rank'] == ref['source_rank']
            assert turn['role'] == ref['speaker']
            assert turn['text'][ref['start_char']:ref['end_char']] == ref['exact_quote']
    checks.append('324 original quarantined MP identities and exact RAW spans retained; all replacements later; none readmitted')

    human = json.loads((base / 'human_review/MANIFEST.json').read_text())
    assert human['human_approved_count'] == 0 and len(human['items']) == 5
    for item in human['items']:
        assert item['status'] == 'pending'
        packet = json.loads((base / 'human_review' / f"item_{item['item']:02d}_FULL_RAW.json").read_text())
        assert packet['source'] == source_map[(item['owner'], item['session'])]
    checks.append('all five requested human items remain pending and retain complete original RAW')

    rs = json.loads((cpu / 'RS_FOUR_INPUTS.json').read_text())
    assert [r['arm'] for r in rs] == ['R0', 'F-resident', 'METHOD', 'METHOD+CASE']
    assert rs[0]['extra_text'] == ''
    assert rs[3]['extra_text'].startswith(rs[2]['extra_text'] + '\nExternal case;')
    assert len({r['prefix_context_sha256'] for r in rs}) == 1
    assert len({digest(r['method_ids']) for r in rs}) == 1
    assert all(r['runtime_callable'] is False and r['outcome'] is None for r in rs)
    checks.append('RS four arms use same prefix/method set; METHOD+CASE only appends case; all non-executable')

    result = dict(protocol='ws-b-independent-final-artifact-audit-v1', status='pass',
        inputs=dict(cpu_manifest_sha256=sha(cpu / 'MANIFEST.json'), pr12=PR12, pr13=PR13),
        checks=checks, sample_83=dict(Counter(r['status'] for r in matrix83)),
        input_54=dict(Counter(r['status'] for r in matrix54)),
        candidate_occurrences=len(all_candidates), snapshots=65, completed_raw_sessions=68,
        ledger_rows=93, old_requests=120, latest_quarantined_mp=324,
        human_approved=0, qualification='engineering_only', model_calls=0)
    with out.open('x') as stream:
        json.dump(result, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    verify(args.root, args.out)
