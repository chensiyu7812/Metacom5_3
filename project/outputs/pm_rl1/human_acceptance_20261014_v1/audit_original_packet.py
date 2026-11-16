#!/usr/bin/env python3
"""Read-only P3 packet/mapping preflight; never decrypt or infer human answers.

Output is always a new directory. Original packet, freeze and score files are
read-only. The private-key file is checked by the existing freeze hash only;
its bytes and hash are never returned or copied into outputs.
"""
from __future__ import annotations
import argparse
from collections import Counter
import csv
import hashlib
import html
import json
from pathlib import Path
import re
import subprocess
import sys
import zipfile


def reject_duplicates(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise ValueError('duplicate JSON field: ' + k)
        out[k] = v
    return out


def read(path):
    return json.loads(path.read_text(), object_pairs_hook=reject_duplicates)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def text_sha(value):
    return hashlib.sha256(value.encode()).hexdigest()


def canonical(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode()).hexdigest()


def inspect(repo, packet_zip):
    project = repo / 'project'
    p3 = project / 'outputs/pm_rl1/completion_20260930_v2/P3'
    packet = p3 / 'calibration'
    source_paths = set()
    frozen_checks = 0
    # Verify the original freeze manifests without calling a mutating script.
    for directory, filename in [(p3/'common_evidence', 'input_freeze.json'),
                                (packet, 'packet_freeze.json'),
                                (p3/'candidate_v1', 'candidate_freeze.json')]:
        freeze_path = directory / filename
        source_paths.add(freeze_path)
        freeze = read(freeze_path)
        for name, expected in freeze['files'].items():
            assert sha(directory/name) == expected, name
            frozen_checks += 1
            if not name.endswith('.pem'):
                source_paths.add(directory/name)
        for name, expected in freeze['source_files'].items():
            assert sha(project/name) == expected, name
            frozen_checks += 1
            source_paths.add(project/name)
    assert packet_zip.read_bytes() == (packet/packet_zip.name).read_bytes()
    with zipfile.ZipFile(packet_zip) as z:
        members = z.namelist()
        assert set(members) == {'rater_1.html', 'rater_2.html', '填写说明.txt'}
        for name in members:
            assert z.read(name) == (packet/'human_handoff_final'/name).read_bytes(), name
        forms = {}
        for rater in ('rater_1', 'rater_2'):
            found = re.search(r'<script id="form-data" type="application/json">(.*?)</script>',
                              z.read(rater+'.html').decode(), re.S)
            assert found
            form = json.loads(found.group(1), object_pairs_hook=reject_duplicates)
            assert form == read(packet/(rater+'_form.json'))
            assert canonical({k:v for k,v in form.items() if k!='form_identity'}) == form['form_identity']
            forms[rater] = form
    bundle = read(packet/'pairs_private.json')
    all_pairs = bundle['pairs']
    active = {p['pair_id']:p for p in all_pairs if p['group'] != 'reserve'}
    assert len(active) == 40 and len(all_pairs) == 48
    assert {forms[r]['packet_identity'] for r in forms} == {bundle['packet_identity']}
    pool = read(p3/'common_evidence/evidence_pool_private.json')
    by_rater = {}
    for rater, form in forms.items():
        mapping = read(packet/(rater+'_map_private.json'))
        assert len(form['items']) == len(mapping) == 40
        assert len({i['item_id'] for i in form['items']}) == 40
        bound = {}
        for order, item in enumerate(form['items'], 1):
            m = mapping[item['item_id']]
            p = active[m['pair_id']]
            assert m['group'] == p['group'] and m['kind'] == p['kind'] and m['owner'] == p['owner']
            assert item['source_key'] == p['prefix_identity']
            assert form['sources'][item['source_key']] == pool[item['source_key']]
            expected = p['replies'][::-1] if m['swapped'] else p['replies']
            assert [item['A'], item['B']] == expected
            assert p['pair_id'] not in bound
            bound[p['pair_id']] = dict(order=order, item=item, mapping=m)
        assert set(bound) == set(active)
        by_rater[rater] = bound
    refs = read(p3/'candidate_v1/pair_score_map_private.json')
    score_jobs = {(r['pair_id'], r['side']):r['job_id'] for r in refs}
    result_doc = project/'docs/pm_rl1_completion_20260930_v2/p3_development_results.json'
    result = read(result_doc)
    run = p3/'candidate_v1/development'/result['runtime_identity']
    summary = read(run/'summary.json')
    expected = result['source_receipts'][str((run/'summary.json').relative_to(project))]
    assert sha(run/'summary.json') == expected
    measurements = {r['job_id']:r for r in summary['rows']}
    rows = []
    for pair_id, p in active.items():
        a, b = (by_rater[r][pair_id] for r in ('rater_1','rater_2'))
        reversed_order = a['mapping']['swapped'] != b['mapping']['swapped']
        assert a['item']['A'] == b['item']['B' if reversed_order else 'A']
        assert a['item']['B'] == b['item']['A' if reversed_order else 'B']
        jobs = [score_jobs[pair_id, side] for side in (0,1)]
        available = all(j in measurements for j in jobs)
        assert available == (p['group'] == 'development')
        row = dict(pair_id=pair_id, group=p['group'], kind=p['kind'],
            contrast=p.get('contrast','control'), control_type=p.get('control_type',''),
            owner=p['owner'], prefix_identity=p['prefix_identity'],
            source_index=p['index'], rater_1_order=a['order'], rater_1_item_id=a['item']['item_id'],
            rater_2_order=b['order'], rater_2_item_id=b['item']['item_id'],
            rater_1_A_canonical_side=int(a['mapping']['swapped']),
            rater_2_A_canonical_side=int(b['mapping']['swapped']),
            rater_1_A_equals_rater_2='B' if reversed_order else 'A',
            rater_1_A_sha256=text_sha(a['item']['A']), rater_1_B_sha256=text_sha(a['item']['B']),
            same_reply_text=a['item']['A']==a['item']['B'],
            source_binding='VERIFIED', replies_and_AB_binding='VERIFIED',
            existing_first_scores_available=available,
            human_submission_received=False, human_fields_status='NOT_INSPECTABLE_EXPORT_NOT_RECEIVED',
            work_flag_12_membership='UNKNOWN', preference_usable=None, risk_A_usable=None, risk_B_usable=None,
            label_access='DEVELOPMENT_ONLY_WHEN_RECEIVED' if p['group']=='development' else 'SEALED_UNTIL_FINAL_MEASUREMENT_FREEZE')
        rows.append(row)
    rows.sort(key=lambda r:r['rater_1_order'])
    strata = []
    for group in ('development','validation'):
        for kind in ('natural','control'):
            selected = [r for r in rows if r['group']==group and r['kind']==kind]
            strata.append(dict(group=group, kind=kind, pairs=len(selected),
                owners=len({r['owner'] for r in selected}), prefixes=len({r['prefix_identity'] for r in selected}),
                first_scores_available_pairs=sum(r['existing_first_scores_available'] for r in selected),
                human_pairs_inspected=0))
    owners = {g:{r['owner'] for r in rows if r['group']==g} for g in ('development','validation')}
    assert not owners['development'] & owners['validation']
    groups = Counter(r['group'] for r in rows)
    assert groups == {'development':16,'validation':24}
    freeze_candidates = [str(p.relative_to(p3)) for p in p3.rglob('*measurement*freeze*.json')]
    assert not freeze_candidates, 'A new final freeze exists; inspect authority before continuing'
    source_paths.update([packet_zip, result_doc, run/'summary.json', p3/'candidate_v1/pair_score_map_private.json',
        project/'docs/PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md',
        project/'docs/pm_rl1_completion_20260930_v2/runbook.md',
        project/'src/metacom_pm/rl1/human_calibration.py',
        project/'src/metacom_pm/rl1/calibration_decision.py'])
    manifest = [{'path':str(p), 'sha256':sha(p), 'bytes':p.stat().st_size} for p in sorted(source_paths)]
    observed_jobs = [m for m in measurements.values() if m['group']=='development']
    assert len(observed_jobs)==32
    summary_out = dict(status='PREFLIGHT_PASS_HUMAN_EXPORT_REQUIRED',
        repository_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=repo,text=True).strip(),
        repository_branch=subprocess.check_output(['git','branch','--show-current'],cwd=repo,text=True).strip(),
        original_zip_sha256=sha(packet_zip), original_zip_members=members,
        packet_identity=bundle['packet_identity'],
        form_identities={r:f['form_identity'] for r,f in forms.items()},
        freeze_file_checks=frozen_checks, pair_groups=dict(groups), strata=strata,
        active_pairs=len(rows), reserve_pairs=8, active_owners=len(set.union(*owners.values())),
        active_prefixes=len({r['prefix_identity'] for r in rows}),
        reversed_AB_between_forms=sum(r['rater_1_A_equals_rater_2']=='B' for r in rows),
        equal_text_pairs=sum(r['same_reply_text'] for r in rows),
        same_prefix_multiple_pairs=sum(n>1 for n in Counter(r['prefix_identity'] for r in rows).values()),
        initial_development_scoring_jobs=len(observed_jobs),
        initial_structure_valid=sum(m['measurement_status']=='measured_candidate' for m in observed_jobs),
        extra_recheck_probes=len(measurements)-len(observed_jobs),
        active_unique_reply_jobs=len({score_jobs[r['pair_id'],i] for r in rows for i in (0,1)}),
        final_measurement_freeze_found=False, human_exports_received=0,
        human_answers_decrypted=0, validation_answers_decrypted=0,
        human_preference_valid_count=None, human_risk_valid_count=None,
        human_problem_12_count=None, new_model_calls=0, new_API_usd=0,
        note='No received export is not evidence of missing answers or invalid completed human work.')
    return summary_out, rows, manifest


def write_outputs(out, summary, rows, manifest):
    out.mkdir(parents=True, exist_ok=False)
    for name,value in [('preflight_summary.json',summary),('input_manifest.json',manifest)]:
        (out/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n')
    with (out/'expected_40_pair_audit_private.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    with (out/'strata.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=list(summary['strata'][0]));writer.writeheader();writer.writerows(summary['strata'])
    assert all(sha(Path(r['path']))==r['sha256'] for r in manifest), 'Input changed during audit'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo',type=Path,required=True)
    parser.add_argument('--packet-zip',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    summary, rows, manifest=inspect(args.repo.resolve(),args.packet_zip.resolve())
    write_outputs(args.out.resolve(),summary,rows,manifest)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
