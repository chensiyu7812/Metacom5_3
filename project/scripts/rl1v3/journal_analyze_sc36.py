"""Paired field diagnostics for SC36, preserving the original strict scorer.

No model, new semantic judge, answer repair, or reward qualification. Old fence
diagnostics are read from their historical sidecar, never substituted for S36.
"""
import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from metacom_pm.rl1v3.io import file_sha256, object_sha256, write_json_once


def jl(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines()]


def transition(old, new):
    if old is None or new is None:
        return 'unassessed'
    return {(False, False): 'retained_failure', (False, True): 'repair',
            (True, False): 'regression', (True, True): 'retained_success'}[bool(old), bool(new)]


def count_field(rows, key):
    values = [row[key] for row in rows]
    return dict(pass_count=sum(v is True for v in values), fail_count=sum(v is False for v in values),
                unassessed=sum(v is None for v in values), total=len(values))


def analyze(root, old_sidecar, out):
    root, old_sidecar, out = map(Path, (root, old_sidecar, out))
    old_rows = {row['request_id']: row for row in jl(old_sidecar)}
    assert len(old_rows) == 36
    endpoints = [row for n in (1, 2) for row in jl(root/f'SC{n}_results_v1/ENDPOINTS_CONSTRAINED_PRIVATE.jsonl')]
    assert len(endpoints) == 36 and len({e['binding']['request_id'] for e in endpoints}) == 36
    rows = []; old_source_sha = file_sha256(old_sidecar)
    for e in endpoints:
        b, ev, answer = e['binding'], e['evaluation'], e['actual_output']
        old = old_rows[b['original_request_id']]
        assert old['original_output_sha256'] == e['old_output_sha256']
        assert old['original_strict_score'] == e['old_strict_score']
        assert old['task_id'] == b['task_id'] and old['arm'] == b['arm']
        score, fields = ev['strict_score'], ev['field_diagnostics']
        parsed = json.loads(answer['text']) if ev['format_status'] == 'pass' else None
        assert answer is None or answer['input_tokens'] == old['actual_cost']['input_tokens']
        body = old['body_diagnostic']; body_contract = old['body_contract_diagnostic']
        unknown = fields['unknown_contract']
        available = fields['all_required_evidence_supplied']
        value = fields['value_correct']
        r = dict(task_id=b['task_id'], arm=b['arm'], task_category=e['task_category'],
            source_group=old['source_group'], request_id=b['request_id'],
            output_sha256=e['output_sha256'], old_output_sha256=e['old_output_sha256'],
            technical_status=ev['technical_status'],
            format_pass=True if ev['format_status']=='pass' else False if ev['format_status']=='fail' else None,
            **fields, strict_success=score['task_success'] if score else None,
            strict_evidence_correct=score['evidence_correct'] if score else None,
            epistemic_compliance=score['epistemic_compliance'] if score else None,
            reasonable_unknown=(unknown and (value or not available)) if parsed else None,
            known_answer_unanswered_despite_supply=(unknown and not value and available) if parsed else None,
            wrong_value_asserted=(parsed['value']!='unknown' and not value) if parsed else None,
            unknown_protocol_valid=unknown if parsed and parsed['value']=='unknown' else None,
            action_stage_value_correct=value if e['task_category']=='explicit_stage' else None,
            old_strict_success=e['old_strict_score']['task_success'],
            old_format_pass=e['old_strict_score']['structural_status']=='pass',
            old_body_value_match=body['value_correct'] if body else None,
            old_body_contract_match=body_contract['task_success'] if body_contract else None,
            old_body_diagnostic_posthoc_only=True, original_labels_changed=False,
            input_tokens=answer['input_tokens'] if answer else None,
            output_tokens=len(answer['token_ids']) if answer else None,
            generation_seconds=answer['seconds'] if answer else None,
            grammar_cpu_mask_seconds=answer.get('constraint_measurement',{}).get('cpu_mask_seconds') if answer else None,
            old_input_tokens=old['actual_cost']['input_tokens'],
            old_output_tokens=old['actual_cost']['output_tokens'], old_generation_seconds=old['actual_cost']['seconds'],
            formal_reward=None)
        r['old_to_new_strict'] = transition(r['old_strict_success'], r['strict_success'])
        r['old_body_to_new_value_diagnostic'] = transition(r['old_body_value_match'], value)
        r['old_body_to_new_contract_diagnostic'] = transition(r['old_body_contract_match'], r['strict_success'])
        rows.append(r)
    by_task = defaultdict(dict)
    for r in rows: by_task[r['task_id']][r['arm']] = r
    pairs = []
    for task, arms in sorted(by_task.items()):
        assert set(arms) == {'BASE','RAW'}
        a, b = arms['BASE'], arms['RAW']
        pair = dict(task_id=task, source_group=a['source_group'], task_category=a['task_category'])
        for name in ('format_pass','value_correct','strict_success','epistemic_compliance'):
            pair[name] = dict(BASE=a[name], RAW=b[name], transition=transition(a[name], b[name]))
        pair['input_tokens'] = dict(BASE=a['input_tokens'],RAW=b['input_tokens'])
        pair['output_tokens'] = dict(BASE=a['output_tokens'],RAW=b['output_tokens'])
        pair['generation_seconds'] = dict(BASE=a['generation_seconds'],RAW=b['generation_seconds'])
        pairs.append(pair)
    tracked = ['format_pass','value_correct','strict_success','strict_evidence_correct',
        'epistemic_compliance','quote_exact_source_substring','quote_supplied','required_literal_in_quote',
        'speaker_source_match','reported_date_source_match','unknown_protocol_valid',
        'reasonable_unknown','known_answer_unanswered_despite_supply','wrong_value_asserted','action_stage_value_correct']
    def aggregate(subset):
        flags={'reasonable_unknown','known_answer_unanswered_despite_supply','wrong_value_asserted'}
        def occurrences(name):
            counted=count_field(subset,name)
            return dict(occurrences=counted['pass_count'],nonoccurrences=counted['fail_count'],
                        unassessed=counted['unassessed'],total=counted['total'])
        return dict(rows=len(subset),fields={name:count_field(subset,name) for name in tracked if name not in flags},
            observed_flags={name:occurrences(name) for name in sorted(flags)},
            old_to_new_strict=dict(Counter(r['old_to_new_strict'] for r in subset)),
            old_body_to_new_value_diagnostic=dict(Counter(r['old_body_to_new_value_diagnostic'] for r in subset)),
            old_body_to_new_contract_diagnostic=dict(Counter(r['old_body_to_new_contract_diagnostic'] for r in subset)))
    summary=dict(protocol='sc36-paired-field-analysis-v1',logical_rows=36,tasks=18,
        old_posthoc_sidecar_sha256=old_source_sha,analysis_script_sha256=file_sha256(__file__),
        by_arm={arm:aggregate([r for r in rows if r['arm']==arm]) for arm in ('BASE','RAW')},
        by_category={c:aggregate([r for r in rows if r['task_category']==c]) for c in sorted({r['task_category'] for r in rows})},
        by_source_group={g:aggregate([r for r in rows if r['source_group']==g]) for g in sorted({r['source_group'] for r in rows})},
        BASE_RAW_transitions={k:dict(Counter(p[k]['transition'] for p in pairs)) for k in ('format_pass','value_correct','strict_success','epistemic_compliance')},
        limitations=['Original strict score is unchanged; old body matches are posthoc diagnostics, not old success.',
            'Exact finite source values do not certify general semantic understanding or natural support.',
            'Citation contract mismatch is not automatically an invented fact; inspect full private source.',
            'Unassessed fields retain their denominator and are not zero-filled.',
            'Correct abstention can be epistemically compliant without completing a known-answer task.'],
        formal_reward=None)
    out.mkdir(parents=True,exist_ok=False)
    write_json_once(out/'SC36_TASKWISE_PUBLIC.json',dict(rows=rows,pairs=pairs))
    write_json_once(out/'SC36_SUMMARY_PUBLIC.json',summary)
    mark={True:'✓',False:'×',None:'?'}
    table=['# SC36逐题BASE→RAW与原S36对照\n',
        '原S36全部严格格式/任务失败保持。下表列新SC36；值/任务是原严格评分器口径，问号为未评。完整字段与成本见SC36_TASKWISE_PUBLIC.json。\n',
        '|题|类型|新格式 B/R|新值 B/R|新严格任务 B/R|BASE→RAW任务|新输入 B/R|新输出 B/R|新生成秒 B/R|',
        '|---|---|---|---|---|---|---:|---:|---:|']
    for p in pairs:
        def status(k):return '/'.join(mark[p[k][a]] for a in ('BASE','RAW'))
        def nums(k):return '/'.join(str(p[k][a]) for a in ('BASE','RAW'))
        secs='/'.join(f"{p['generation_seconds'][a]:.3f}" if p['generation_seconds'][a] is not None else '?' for a in ('BASE','RAW'))
        table.append('|'+ '|'.join([p['task_id'],p['task_category'],status('format_pass'),status('value_correct'),status('strict_success'),p['strict_success']['transition'],nums('input_tokens'),nums('output_tokens'),secs])+'|')
    (out/'SC36_TASKWISE_ZH.md').write_text('\n'.join(table)+'\n')
    return {arm:summary['by_arm'][arm] for arm in ('BASE','RAW')}


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    for name in ('root','old-sidecar','out'):p.add_argument('--'+name,required=True)
    print(json.dumps(analyze(**vars(p.parse_args())),indent=2))
