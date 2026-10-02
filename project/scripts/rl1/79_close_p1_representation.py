#!/usr/bin/env python3
"""Close P1 from bound local evidence; no models, reward or human labels.

The semantic notes below record the coordinator's inspected development cases.
They are neither an automatic evaluator nor independent human gold.
"""
import argparse
from collections import Counter
import html
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest

P1 = PROJECT / 'outputs/pm_rl1/completion_20260930_v2/P1'


def save(path, value):
    content = json.dumps(value, ensure_ascii=False, indent=2) + '\n'
    if path.exists():
        if path.read_text() != content:
            raise ValueError('refuse to overwrite different result: ' + str(path))
        return
    path.write_text(content)


def load_run(folder, expected):
    freeze = json.loads((folder / 'renderer_freeze.json').read_text())
    for name, value in freeze['files'].items():
        assert sha256_file(folder / name) == value, name
    for name, value in freeze['source_files'].items():
        assert sha256_file(PROJECT / name) == value, name
    run = Path(json.loads((folder / 'diagnostic_pointer.json').read_text())['run_dir'])
    summary = json.loads((run / 'summary.json').read_text())
    assert summary['status'] == 'COMPLETE' and len(summary['rows']) == expected
    assert summary['generator_calls'] == expected
    for row in summary['rows']:
        rid = row['request_id']
        request = json.loads((run / (rid + '.request.json')).read_text())
        raw = json.loads((run / (rid + '.raw.json')).read_text())
        assert digest({k: v for k, v in request.items() if k != 'request_id'}) == rid
        assert request['request_id'] == raw['request_id'] == rid
        assert raw['runtime_identity'] == request['executor_identity']
        assert raw['finish_reason'] == row['finish_reason'] == 'natural_stop'
        assert raw['text'].strip() and not row['cache_hit']
    return freeze, run, summary


def main(out):
    freeze, old_run, old = load_run(out, 72)
    direct_freeze, direct_run, direct = load_run(out / 'interface_repair_v3', 16)
    registry = json.loads((out / 'source_review_registry.json').read_text())
    capacities = json.loads((out / 'capacity_prefix_private.json').read_text())
    specs = json.loads((out / 'episode_specs_private.json').read_text())
    cases = []
    # These 16 texts were individually inspected, including the residual error.
    for row in direct['rows']:
        rid = row['request_id']
        raw_path = direct_run / (rid + '.raw.json')
        response = json.loads(raw_path.read_text())['text']
        residual = row['arm'] == 'old_lora_epoch3' and row['index'] == 102 and row['condition'] == 'OFF'
        if residual:
            assert 'When I said "I had similar situation like yours,"' in response
        cases.append(dict(request_id=rid, raw_sha256=sha256_file(raw_path),
            index=row['index'], condition=row['condition'], arm=row['arm'],
            direct_reply_observed=True, unnecessary_refusal_observed=False,
            invented_AI_family_biography_observed=False,
            historical_speaker_misattribution_observed=residual,
            finding=('Calls the historical supporter utterance "When I said" despite denying personal experience.'
                     if residual else 'Direct response observed; this is not a q/m quality qualification.'),
            additional_caution=('Imports past MS family/college details into present framing without reconfirmation; '
                'not classified as proven false by this review.' if row['index']==102 and
                row['condition']=='MEMORY' and row['arm']=='old_lora_epoch3' else None)))
    mother = []
    for row in old['rows']:
        if row['index'] != 102:
            continue
        raw_path = old_run / (row['request_id'] + '.raw.json')
        response = json.loads(raw_path.read_text())['text']
        lora = row['arm'] == 'old_lora_epoch3'
        mother.append(dict(request_id=row['request_id'], raw_sha256=sha256_file(raw_path),
            condition=row['condition'], arm=row['arm'], representation=row['representation'],
            invented_AI_family_biography_observed=lora and row['representation']=='old',
            unnecessary_refusal_observed=lora and row['representation']=='new',
            response_excerpt=response[:800]))
    review = dict(version='p1-development-interface-review-v1',
        reviewer='Codex coordinator AI-assisted inspection; not independent human gold',
        independent_test=False, usable_as_training_reward=False,
        original_summary_sha256=sha256_file(old_run/'summary.json'),
        repair_summary_sha256=sha256_file(direct_run/'summary.json'),
        inspected_original_mother_cases=mother, inspected_repair_cases=cases,
        unreviewed_original_replies_for_semantic_totals=60,
        conclusions=dict(direct_reply_repair_cases=16, residual_attribution_cases=1,
            mother_old_lora_old_biography_cases=3, mother_old_lora_v2_refusal_cases=3),
        limitation='Adaptive development evidence, six prefixes, three dev owners; MEMORY is MS in all six original prefixes. '
            'No claim of MP/ME generation efficacy, universal role correctness, support-quality gain or reliable reward.')
    save(out/'diagnostic_review_private.json', review)

    sections = []
    for index in sorted({r['index'] for r in old['rows']}):
        turns = specs[index]['prefix']['turns']
        prefix = '\n'.join(t['role'] + ': ' + t['content'] for t in turns)
        replies = []
        for run, results in ((old_run, old), (direct_run, direct)):
            for row in results['rows']:
                if row['index'] != index:
                    continue
                request = json.loads((run/(row['request_id']+'.request.json')).read_text())
                response = json.loads((run/(row['request_id']+'.raw.json')).read_text())['text']
                title = f"{row['arm']} / {row['representation']} / {row['condition']}"
                replies.append('<article><h3>'+html.escape(title)+'</h3><p class="id">'+row['request_id']+
                    '</p><pre>'+html.escape(response)+'</pre><details><summary>实际交付的输入</summary><pre>'+
                    html.escape(json.dumps(request['messages'],ensure_ascii=False,indent=2))+'</pre></details></article>')
        sections.append(f'<section id="p{index}"><h2>开发前缀 {index}</h2><details><summary>当前对话原文</summary><pre>'+
            html.escape(prefix)+'</pre></details><div class="grid">'+''.join(replies)+'</div></section>')
    page = ('<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>PM-RL1 P1 开发回归</title><style>body{font:16px system-ui;margin:2rem auto;max-width:1450px;padding:0 1rem;'
        'color:#203043;background:#f5f7fa}a{color:#245fac}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.6 system-ui}'
        '.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:1rem}article{background:white;padding:1rem;'
        'border:1px solid #ccd6e0;border-radius:8px}.id{font:11px monospace;overflow-wrap:anywhere}section{margin:3rem 0}'
        'summary{cursor:pointer}</style><h1>P1 开发回归：原定72条＋接口修复16条</h1>'
        '<p>本地审阅页。六个开发前缀；AI辅助分析，不是人评、训练奖励或独立测试。旧结果完整保留。</p>'
        '<p>v2：当前输入整体JSON；direct_v3：最新一句保留原生user消息，历史作为带说话者的引用背景。'
        '旧LoRA仍有把历史supporter的话认作自己所说的残留错误。MEMORY条件均为MS。</p><nav>'+
        ' · '.join(f'<a href="#p{i}">前缀{i}</a>' for i in sorted({r['index'] for r in old['rows']}))+
        '</nav>'+''.join(sections)+'</html>')
    page_path = out/'diagnostic_review.html'
    if page_path.exists() and page_path.read_text()!=page:
        raise ValueError('review page changed')
    page_path.write_text(page)

    baseline = PROJECT/'docs/reviews/20260930/pm_rl1/LOCAL_ARTIFACT_INVENTORY.json'
    inventory = json.loads(baseline.read_text())['files']
    for entry in inventory:
        path = PROJECT.parent/entry['path']
        assert path.stat().st_size == entry['bytes'] and sha256_file(path) == entry['sha256'], entry['path']
    suite = ET.parse(out/'tests_final.xml').getroot()
    totals = {k:sum(int(s.attrib.get(k,0)) for s in suite.iter('testsuite'))
              for k in ('tests','failures','errors','skipped')}
    assert totals['tests']==176 and totals['failures']==totals['errors']==totals['skipped']==0
    rows = old['rows']+direct['rows']
    closeout = dict(phase='P1', status='COMPLETE_WITH_DISCLOSED_LIMITS',
        successor_permission='P2 executor preparation; no reward qualification or formal natural PPO',
        active_renderer='DirectReplyRenderer', active_renderer_identity=direct_freeze['new_renderer_identity'],
        input_freezes={str(p.relative_to(PROJECT)):sha256_file(p) for p in
            (out/'renderer_freeze.json',out/'interface_repair_v3/renderer_freeze.json')},
        source_reviews=dict(mp_new=72,mp_total=173,mp_new_counts=registry['mp_counts'],
            me_new=24,human_tasks=0,review_kind='AI assisted source-only; not human gold'),
        capacity=dict(prefixes=114,train=96,dev=18,
            reachable=sum(c['reachable'] for c in capacities),
            same_repaired_inventory_old_delivery_reachable=sum(c['old_delivery_reachable'] for c in capacities),
            original_memory_diagnostic_heads=dict(Counter(str(tuple(r['counts'])) for r in old['rows']
                if r['condition']=='MEMORY' and r['arm']=='base' and r['representation']=='new'))),
        actual=dict(original_G=72,explicit_additional_interface_G=16,total_G=88,
            J=0,API_usd=0,natural_stop=88,quality_retries=0,
            output_tokens=sum(r['output_tokens'] for r in rows),
            generation_seconds=sum(r['seconds'] for r in rows),
            diagnostic_process_elapsed_seconds=old['elapsed_seconds']+direct['elapsed_seconds'],
            retrieval_process_elapsed_seconds=freeze['seconds'],
            timing_scope='Measured process/generation wall time, not exclusive GPU occupancy or total analyst time'),
        tests=totals,old_artifacts_unchanged=len(inventory),
        review_summary=review['conclusions'],
        remaining=['Old LoRA residual historical-speaker misattribution',
            'MP/ME generation effects and multi-resource capability unverified',
            'Most source units not exhaustively reviewed; unknown remains unknown',
            'No calibrated q/m reward or formal natural-task PPO',
            'No test semantic review or test projection built in P1'],
        outputs={name:sha256_file(out/name) for name in
            ('diagnostic_review_private.json','diagnostic_review.html','tests_final.xml','capacity.json','source_review_registry.json')},
        script_sha256=sha256_file(Path(__file__)))
    save(out/'phase_closeout.json',closeout)
    print(json.dumps(closeout,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,default=P1);main(p.parse_args().out)
