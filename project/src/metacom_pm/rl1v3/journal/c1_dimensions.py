"""Read-only dimensional reconciliation of the frozen J06/C1 development table.

No model, revised reference, new policy or semantic judge is implemented here.
Public outputs are allowlisted anonymous numbers. Full evidence stays private.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

from ..io import file_sha256, object_sha256, write_json_once, write_jsonl_once
from .selective_memory import choose

ARMS = ('STOP', 'MS', 'RS', 'MS_RS')
DIMENSIONS = ('fact', 'support', 'joint')
ATOM_BOUNDS = {'supported': [1, 1], 'partial': [0, 0], 'omitted': [0, 0],
               'unsupported': [0, 0], 'unresolved': [0, 1]}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def conjunction(bounds):
    require(bool(bounds), 'empty requirement set')
    require(all(v in ([0, 0], [0, 1], [1, 1]) for v in bounds), 'invalid interval')
    return [min(v[i] for v in bounds) for i in (0, 1)]


def support_bounds(verdicts):
    require(bool(verdicts) and set(verdicts) <= {'pass', 'fail', 'uncertain'}, 'invalid verdict')
    return [0, 0] if 'fail' in verdicts else [0, 1] if 'uncertain' in verdicts else [1, 1]


def paired_delta(left, right, dimension):
    # The same unresolved physical endpoint is its own control, not two unknowns.
    if left['request_id'] == right['request_id']:
        require(left[dimension] == right[dimension], 'shared endpoint disagreement')
        return [0, 0]
    a, b = left[dimension], right[dimension]
    return [a[0] - b[1], a[1] - b[0]]


def aggregate(rows):
    return {d: [sum(r[d][i] for r in rows) for i in (0, 1)] for d in DIMENSIONS}


def compare(left, right):
    require(len(left) == len(right), 'unpaired comparison')
    result = {}
    for d in DIMENSIONS:
        pairs = [(a['task'], paired_delta(a, b, d)) for a, b in zip(left, right)]
        require(all(a['task'] == b['task'] for a, b in zip(left, right)), 'task order mismatch')
        result[d] = dict(paired_delta=[sum(v[i] for _, v in pairs) for i in (0, 1)],
                         confirmed_gain=[t for t, v in pairs if v[0] > 0],
                         confirmed_loss=[t for t, v in pairs if v[1] < 0],
                         unresolved=[t for t, v in pairs if v[0] != v[1]])
    return result


def quote_offsets(text, quotes):
    spans = []
    for quote in quotes:
        require(isinstance(quote, str) and bool(quote) and quote in text, 'evidence quote missing')
        start = text.index(quote)
        spans.append(dict(start=start, end=start + len(quote), quote=quote))
    return spans


def taskwise_markdown(rows):
    def cell(bounds):
        return '?' if bounds == [0, 1] else str(bounds[0])
    def triple(cells):
        return '/'.join(cell(cells[d]) for d in DIMENSIONS)
    scope = {'explicit_history_answer': '明确历史问答', 'brief_current_reflection': '简短反映',
             'brief_current_acknowledgement': '简短确认'}
    lines = ['# C1 原观察逐题分维度表', '',
             '每格依次为事实/支持/联合；1=原开发观察确定完成，0=确定未完成，?=[0,1]。',
             '分母固定24题、6来源组；不是独立人评或置信区间，未重评分。C1只选既有STOP/MS端点。', '',
             '|题|组|原可见要求类型|STOP|MS|RS|MS→RS|C1选臂|C1|',
             '|---|---|---|---|---|---|---|---|---|']
    for r in rows:
        values = [r['task'], r['source_group'], scope[r['request_scope']]]
        values += [triple(r['cells'][arm]) for arm in ARMS]
        values += [r['c1_arm'], triple(r['cells'][r['c1_arm']])]
        lines.append('|' + '|'.join(values) + '|')
    return '\n'.join(lines) + '\n'


def reconcile(joint_root, old_taskwise, prior_manifest, out):
    root, old_taskwise, out = Path(joint_root), Path(old_taskwise), Path(out)
    require(not out.exists(), 'new diagnostic directory required')
    hashes = {}

    def read(path, lines=False):
        path = Path(path)
        hashes[str(path)] = file_sha256(path)
        text = path.read_text()
        return [json.loads(s) for s in text.splitlines()] if lines else json.loads(text)

    old = read(old_taskwise)
    protected = read(prior_manifest)
    for name, digest in protected['inputs_sha256'].items():
        require(file_sha256(name) == digest, 'previous input changed: ' + name)
    tasks = read(root / 'source-bundle-v1/TASKS.runtime.jsonl', True)
    specs = {r['task_id']: r for r in read(root / 'source-bundle-v1/EVALSPEC.private.jsonl', True)}
    source_manifest = read(root / 'source-bundle-v1/MANIFEST.json')
    for name, digest in source_manifest['files_sha256'].items():
        require(file_sha256(root / 'source-bundle-v1' / name) == digest, 'frozen source bundle changed')
    joined = {r['logical_id']: r for r in read(root / 'analysis-v2/JOINED_ENDPOINTS_PRIVATE.jsonl', True)}
    side = read(root / 'fact-review-v1/CONTEXT_SCOPE_UNCERTAINTY_PRIVATE.json')
    disputes = {(r['logical_id'], r['atom_id']): r for r in side['affected_atoms']}
    actual, facts, supports, returns = {}, {}, {}, {}
    for n in range(1, 7):
        for dest, path in (
            (actual, root / f'actual-v1/batch-{n:02d}/ACTUAL_RESPONSES_PRIVATE.jsonl'),
            (facts, root / f'fact-review-v1/BATCH_{n:02d}_FACT_REVIEW_PRIVATE.jsonl'),
            (supports, root / f'support-review-v1/BATCH{n:02d}_SUPPORT_PRIVATE.jsonl'),
        ):
            for row in read(path, True):
                require(row['logical_id'] not in dest, 'duplicate logical row')
                dest[row['logical_id']] = row
        jobs = list((root.parent / f'J{n}_run1').glob('job-*'))
        require(len(jobs) == 1, 'ambiguous original run')
        for path in sorted(jobs[0].glob('*-REQUEST_RETURNED.json')):
            event = read(path)
            require(event['request_id'] not in returns, 'duplicate actual return')
            returns[event['request_id']] = event['output']
    require(len(tasks) == 24 and all(len(x) == 96 for x in (actual, facts, supports, joined, returns)),
            'original complete table required')
    old_rows = {(r['task'], r['arm']): r for r in old['rows']}
    require(len(old_rows) == len(old['rows']) == 96, 'old anonymous cells incomplete')
    choices = {r['task']: r['candidate_choice'] for r in old['feature_audit']}
    groups, rows, private, task_rows = {}, [], [], []
    for index, task in enumerate(tasks, 1):
        label, spec = f'J{index:02d}', specs[task['task_id']]
        expected_fact_ids = {v['id'] for v in spec['personal_fact_references']}
        expected_req = {v['id'] for v in spec['requirements']}
        expected_prohib = {v['id'] for v in spec['prohibitions']}
        selected = choose(task['query'])
        require(selected == choices[label], 'C1 rule or visible task changed')
        stratum = spec['needs_stratum_private']
        request_scope = ('explicit_history_answer' if stratum in ('memory_only', 'both') else
                         'brief_current_reflection' if stratum == 'RS_only' else 'brief_current_acknowledgement')
        four = {}
        for arm in ARMS:
            matches = [a for a in actual.values() if a['task_id'] == task['task_id'] and a['arm'] == arm]
            require(len(matches) == 1, 'missing or duplicate task arm')
            a = matches[0]
            f, s, j = facts[a['logical_id']], supports[a['logical_id']], joined[a['logical_id']]
            answer = returns[a['request_id']]
            require(answer == a['output'] and object_sha256(answer) == a['output_sha256'], 'reply identity mismatch')
            require(a['technical_status'] == 'eos', 'technical status changed')
            require(object_sha256(spec) == a['evalspec_sha256'], 'EvalSpec identity mismatch')
            for view in (f, s, j):
                require(all(view[k] == a[k] for k in ('logical_id', 'request_id', 'output_sha256', 'evalspec_sha256')),
                        'observation identity mismatch')
                require(view['formal_reward'] is None, 'unqualified observation promoted')
            require({v['id'] for v in f['fact_atoms']} == expected_fact_ids, 'fact coverage changed')
            require(set(s['requirements']) == expected_req and set(s['prohibitions']) == expected_prohib,
                    'support coverage changed')
            atom_intervals, evidence = [], []
            for atom in f['fact_atoms']:
                bounds = ATOM_BOUNDS[atom['status']]
                dispute = disputes.get((a['logical_id'], atom['id']))
                if dispute:
                    require(dispute['original_status'] == atom['status'], 'sidecar base mismatch')
                    bounds = dispute['completion_interval']
                atom_intervals.append(bounds)
                evidence.append(dict(dimension='fact', item=atom['id'], original_status=atom['status'],
                                     interval=bounds, quotes=quote_offsets(answer['text'], atom['output_quotes'])))
            fi = conjunction(atom_intervals)
            verdicts = []
            for field in ('requirements', 'prohibitions'):
                for item_id, item in s[field].items():
                    verdicts.append(item['verdict'])
                    evidence.append(dict(dimension='support', item=item_id, verdict=item['verdict'],
                                         quotes=quote_offsets(answer['text'], item['output_quotes'])))
            si = support_bounds(verdicts)
            ji = conjunction([fi, si])
            require([fi, si, ji] == [j[d + '_interval'] for d in DIMENSIONS], 'original joined result differs')
            groups.setdefault(j['source_group'], f'G{len(groups) + 1:02d}')
            row = dict(task=label, source_group=groups[j['source_group']], arm=arm,
                       request_id=a['request_id'], fact=fi, support=si, joint=ji,
                       input_tokens=answer['input_tokens'], output_tokens=len(answer['token_ids']))
            require(all(row[k] == old_rows[label, arm][k] for k in row), 'published table differs')
            four[arm] = row
            rows.append(row)
            private.append(dict(**row, original_query=task['query'], original_evalspec=spec,
                                full_reply=answer['text'], original_fact_review=f, original_support_review=s,
                                evidence_offsets=evidence, output_sha256=a['output_sha256']))
        task_rows.append(dict(task=label, source_group=four['MS']['source_group'], request_scope=request_scope,
                              original_reference_atom_count=len(expected_fact_ids),
                              explicit_exhaustive_field_question=request_scope == 'explicit_history_answer',
                              factual_integrity_required=True, all_reference_atoms_required_by_frozen_metric=True,
                              background_outside_requested_scope_need_not_be_repeated=True,
                              c1_arm=selected, cells={arm: {d: four[arm][d] for d in DIMENSIONS} for arm in ARMS},
                              c1_minus_ms={d: paired_delta(four[selected], four['MS'], d) for d in DIMENSIONS}))
    by_task = {r['task']: {a: next(x for x in rows if x['task'] == r['task'] and x['arm'] == a) for a in ARMS}
               for r in task_rows}
    selected_rows = [by_task[r['task']][r['c1_arm']] for r in task_rows]
    ms_rows = [by_task[r['task']]['MS'] for r in task_rows]
    summaries = {a: aggregate([by_task[t][a] for t in by_task]) for a in ARMS}
    summaries['C1'] = aggregate(selected_rows)
    require(summaries['MS'] == dict(fact=[19, 22], support=[19, 22], joint=[18, 20]), 'MS expected reconciliation failed')
    require(summaries['C1'] == dict(fact=[18, 20], support=[20, 23], joint=[16, 19]), 'C1 expected reconciliation failed')
    checks = read(root / 'packages-v5/READ_CHECKS.private.jsonl', True)
    require(len(checks) == 96, 'actual CPU path coverage')
    require(all(r['MP_ME_masked'] and r['after_stop_rejected'] for r in checks), 'original masks changed')
    for r in checks:
        expected = {'STOP': [], 'MS': ['MS'], 'RS': ['RS'], 'MS_RS': ['MS', 'RS']}[r['arm']]
        require(r['order'] == expected and [s['head'] for s in r['steps']] == expected, 'nonoriginal action path')
    paths = {(r['task_id'], r['arm']): r for r in checks}
    for task in tasks:
        single, double = paths[task['task_id'], 'MS'], paths[task['task_id'], 'MS_RS']
        require(single['steps'][0]['reading_sha256'] == double['steps'][0]['reading_sha256'], 'MS changes with later read')
    msrs = [by_task[t]['MS_RS'] for t in by_task]
    result = dict(protocol='c1-dimensions-original-observations-v1', base_commit='4e78c03988167909a9291df4883214c51a018823',
                  tasks=24, actual_replies_reconciled=96, source_groups=len(groups),
                  summaries=summaries, c1_vs_ms=compare(selected_rows, ms_rows),
                  c1_choices=dict(Counter(r['arm'] for r in selected_rows)),
                  second_head_after_ms=dict(legal_executed=24, head='RS', candidate_count=1,
                      joint_effect=compare(msrs, ms_rows),
                      extra_input_tokens=sum(r['input_tokens'] for r in msrs)-sum(r['input_tokens'] for r in ms_rows),
                      learned_or_read_conditioned_selection_tested=False, one_shot_comparison_tested=False),
                  request_scope_counts=dict(Counter(r['request_scope'] for r in task_rows)),
                  old_inputs_unchanged=len(protected['inputs_sha256']), old_scores_and_C1_changed=False,
                  interval_type='completion bounds, not confidence intervals',
                  qualification='assistant development diagnosis; task author, not independent human judge',
                  formal_reward=None, pending_real_human_review=5, new_model_calls=0, SC36_outputs_read=False)
    out.mkdir(parents=True)
    write_json_once(out / 'SUMMARY_PUBLIC.json', result)
    write_json_once(out / 'TASKWISE_PUBLIC.json', dict(protocol=result['protocol'], rows=task_rows))
    write_json_once(out / 'CELLS96_PUBLIC.json', dict(rows=[{k: v for k, v in r.items() if k != 'request_id'} for r in rows]))
    (out / 'TASKWISE_PUBLIC_ZH.md').write_text(taskwise_markdown(task_rows))
    write_jsonl_once(out / 'FULL_EVIDENCE_PRIVATE.jsonl', private)
    write_json_once(out / 'MANIFEST_PRIVATE.json', dict(inputs_sha256=hashes,
        code_sha256=file_sha256(__file__), policy_code_sha256=file_sha256(Path(__file__).with_name('selective_memory.py')),
        outputs_sha256={p.name: file_sha256(p) for p in out.iterdir() if p.is_file()}, new_model_calls=0))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('joint-root', 'old-taskwise', 'prior-manifest', 'out'):
        parser.add_argument('--' + name, required=True)
    result = reconcile(**vars(parser.parse_args()))
    print(json.dumps({k: result[k] for k in ('actual_replies_reconciled', 'summaries', 'old_inputs_unchanged')}, indent=2))


if __name__ == '__main__':
    main()
