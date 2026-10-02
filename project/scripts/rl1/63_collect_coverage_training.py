#!/usr/bin/env python3
"""Collect this finite executor experiment, its development review, and costs."""
from collections import Counter
import hashlib
import html
import json
from pathlib import Path
import statistics
import sys
from xml.etree import ElementTree

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

OUT = PROJECT / 'outputs/pm_rl1/executor_training_20260930_v1'
SOURCE = PROJECT / 'outputs/pm_rl1/executor_coverage_20260929_v1'
PACK = SOURCE / 'qualified_inputs'


def read(path):
    return json.loads(path.read_text())


def save(name, value):
    with (OUT / name).open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def main():
    training = Path(read(OUT / 'training_pointer.json')['run_dir'])
    diagnostic = Path(read(OUT / 'diagnostic_pointer.json')['run_dir'])
    author = Path(read(SOURCE / 'author_pointer.json')['run_dir'])
    tr, reload = read(training / 'summary.json'), read(training / 'reload.json')
    ds, au = read(diagnostic / 'summary.json'), read(author / 'summary.json')
    contract = read(PACK / 'condition_contract_private.json')
    conditions = {(c['index'], c['condition']): c for c in contract['conditions']}
    assert len(au['rows']) == 82 and len(ds['rows']) == 72 and tr['steps'] == 21
    assert reload['passed'] and tr['frozen_base_hash_before'] == tr['frozen_base_hash_after']
    observations = read(OUT / 'diagnostic_observations_private.json')
    assert {(r['index'], r['condition']) for r in observations['rows']} == {(c['index'], c['condition']) for c in contract['conditions'] if c['split'] == 'dev'}
    for row in ds['rows']:
        req = read(diagnostic / (row['request_id'] + '.request.json'))
        raw = read(diagnostic / (row['request_id'] + '.raw.json'))
        c = conditions[row['index'], row['condition']]
        assert req['messages'] == c['messages'] and digest(req['messages']) == row['messages_identity']
        assert raw['request_id'] == req['request_id'] and raw['runtime_identity'] == req['executor_identity']
    epochs = read(training / 'epochs.json')
    selection = read(training / 'selection.json')
    assert selection == min(epochs, key=lambda e: (e['dev']['nll'], e['epoch']))
    metrics = [dict(arm='base', **{k: read(training / 'baseline_dev.json')[k] for k in ('nll', 'body_nll', 'eot_nll')})]
    metrics += [dict(arm=f"epoch_{e['epoch']}", **{k: e['dev'][k] for k in ('nll', 'body_nll', 'eot_nll')}) for e in epochs]
    lengths = {}
    for arm in ('base', 'epoch_1', 'epoch_2', 'epoch_3'):
        group = [r for r in ds['rows'] if r['arm'] == arm]
        values = [r['output_tokens'] for r in group if r['output_tokens'] is not None]
        lengths[arm] = dict(count=len(group), min=min(values), median=statistics.median(values), max=max(values),
            natural_stops=sum(r['finish_reason'] == 'natural_stop' for r in group))
    preserved = {}
    for name in ('preexisting_files.json', 'prior_artifact_files.json'):
        old = read(OUT / name)
        mismatches = [p for p, h in old.items() if sha256_file(PROJECT.parent / p) != h]
        assert not mismatches, mismatches
        preserved[name] = dict(count=len(old), unchanged=True)
    tests = ElementTree.parse(OUT / 'pytest.xml').getroot().find('testsuite').attrib
    summary = dict(status='FINITE_SUPERVISED_EXECUTOR_RUN_COMPLETE',
        admission=read(OUT / 'admission_summary.json'), metrics=metrics, selected_epoch=selection['epoch'],
        optimizer_steps=tr['steps'], trainable_parameters=tr['trainable_parameters'],
        frozen_base_unchanged=True, reload_passed=True, reload_nll_delta=reload['absolute_nll_delta'],
        generation_lengths=lengths,
        cost=dict(new_author_calls=82, reused_author_calls=26, diagnostic_calls=72,
            author_natural_ends=sum(r['finish_reason'] == 'natural_stop' for r in au['rows']),
            diagnostic_natural_ends=sum(r['finish_reason'] == 'natural_stop' for r in ds['rows']),
            author_total_seconds=au['total_seconds'], training_total_seconds=tr['total_seconds'],
            reload_total_seconds=reload['total_seconds'], diagnostic_total_seconds=ds['total_seconds'],
            paid_api_usd=0, new_human_labels=0, retries=0),
        tests={k: tests[k] for k in ('tests', 'failures', 'errors', 'skipped')}, preserved=preserved,
        limitations=['AI-assisted admission; not independent human labels', 'Dev outcomes reused for development; no held-out quality claim',
            'NLL and response length are not support quality or resource benefit', 'Reward qualification and natural-support PPO remain pending'])
    save('results_summary.json', summary)
    escape = lambda x: html.escape(x, quote=True)
    cards = []
    obs_map = {(r['index'], r['condition']): r for r in observations['rows']}
    for c in contract['conditions']:
        if c['split'] != 'dev':
            continue
        group = [r for r in ds['rows'] if (r['index'], r['condition']) == (c['index'], c['condition'])]
        cards.append(f"<section><h2>{c['index']} / {escape(c['owner'])} / {c['condition']} {tuple(c['counts'])}</h2>"
            + '<details><summary>精确共同输入</summary><pre>' + escape(json.dumps(c['messages'], ensure_ascii=False, indent=2)) + '</pre></details><div class="grid">')
        for row in group:
            raw = read(diagnostic / (row['request_id'] + '.raw.json'))
            cards.append('<article><h3>' + escape(row['arm']) + f" · {row['output_tokens']} tokens</h3><p>"
                + escape(row['finish_reason']) + '</p><pre>' + escape(raw['text']) + '</pre></article>')
        cards.append('</div><p class="note">开发诊断：' + escape(obs_map[c['index'], c['condition']]['note']) + '</p></section>')
    new_reviews = read(OUT / 'admission_reviews_private.json')['rows']
    cards.append('<h1>82 条新增作者回复与逐条审核</h1><p>此处的接受/拒绝是开发者 AI 弱监督准入，不是人评，也不是 reward。</p>')
    for r in new_reviews:
        raw = read(author / (r['request_identity'] + '.raw.json'))
        req = read(author / (r['request_identity'] + '.request.json'))
        cards.append(f"<details><summary>{r['index']} / {r['condition']} / seed {r['seed']} · {r['status']}</summary>"
            + '<p>' + escape(r['rationale']) + '</p><pre>' + escape(raw['text']) + '</pre><details><summary>精确输入</summary><pre>'
            + escape(json.dumps(req['messages'], ensure_ascii=False, indent=2)) + '</pre></details></details>')
    page = '<!doctype html><html lang="zh"><meta charset="utf-8"><title>PM-RL1 执行器训练与开发诊断</title>'
    page += '<style>body{max-width:1500px;margin:28px auto;padding:0 20px;font:16px/1.6 system-ui;color:#172333;background:#f4f6f8}section{background:white;border:1px solid #ccd5df;border-radius:10px;margin:24px 0;padding:18px}.grid{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:15px}article{border:1px solid #d7dce1;padding:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 system-ui}summary{cursor:pointer;padding:10px}h2{font-size:21px}h3{font-size:17px}.note{background:#eef3f8;padding:12px}@media(max-width:1100px){.grid{grid-template-columns:repeat(2,minmax(0,1fr))}}@media(max-width:650px){.grid{grid-template-columns:1fr}}</style>'
    page += '<h1>PM-RL1 执行器训练与开发诊断</h1><p>同一输入的 base 与三个 epoch。checkpoint 仅按预先规定的开发 NLL 选择；此浏览页不是盲审表或独立效果验证。</p>'
    page += '<pre>' + escape(json.dumps(dict(metrics=metrics, lengths=lengths), ensure_ascii=False, indent=2)) + '</pre>' + ''.join(cards) + '</html>'
    with (OUT / 'review.html').open('x') as f:
        f.write(page)
    print(json.dumps({k: summary[k] for k in ('status', 'metrics', 'selected_epoch', 'generation_lengths', 'cost', 'tests')}, ensure_ascii=False))


if __name__ == '__main__':
    main()
