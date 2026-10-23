#!/usr/bin/env python3
"""Apply the predeclared severe-regression exclusion, then response NLL rule."""
from collections import Counter
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
OUT=PROJECT/'outputs/pm_rl1/completion_20260930_v2/P2'


def read(p):return json.loads(p.read_text())


def main():
    training=Path(read(OUT/'training_pointer.json')['run_dir'])
    if (training/'selection.json').exists() or (OUT/'executor_selection.json').exists():raise RuntimeError('already selected')
    diagnostic=Path(read(OUT/'diagnostic_pointer.json')['run_dir'])
    summary=read(diagnostic/'summary.json');assert summary['status']=='COMPLETE_BEHAVIOR_REVIEW_PENDING'
    rows={r['request_id']:r for r in summary['rows']};assert len(rows)==36
    review_path=OUT/'behavior_reviews_private.json';review=read(review_path)
    assert review['independent_human_gold'] is False and review['status']=='COMPLETE'
    assert len(review['rows'])==36 and {r['request_id'] for r in review['rows']}==set(rows)
    bad=set();technical=set()
    for r in review['rows']:
        row=rows[r['request_id']];raw_path=diagnostic/(r['request_id']+'.raw.json');raw=read(raw_path)
        req=read(diagnostic/(r['request_id']+'.request.json'))
        assert sha256_file(raw_path)==r['raw_sha256'] and r['rationale']
        assert r['status'] in ('no_confirmed_severe_error','confirmed_severe_error','uncertain','technical_failure')
        if raw['finish_reason']!='natural_stop' or not raw['text'].strip():technical.add(row['arm'])
        if r['status']=='technical_failure':
            assert raw['finish_reason']!='natural_stop' or not raw['text'].strip(), 'technical label must match raw completion'
        if r['status']=='confirmed_severe_error':
            assert r['output_quote'] and r['output_quote'] in raw['text']
            assert r['source_quote'] and any(r['source_quote'] in m['content'] for m in req['messages'])
            assert r['error_type'] in ('AI_biography','historical_speaker','claim_subject','currentness','action_outcome')
            bad.add(row['arm'])
    epochs=read(training/'epochs.json');eligible=[e for e in epochs if f"epoch_{e['epoch']}" not in bad|technical]
    def save(p,v):
        with p.open('x') as f:f.write(json.dumps(v,ensure_ascii=False,indent=2)+'\n')
    selected=min(eligible,key=lambda e:(e['dev']['nll'],e['epoch'])) if eligible else None
    if selected:save(training/'selection.json',dict(selected,behavior_review_sha256=sha256_file(review_path)))
    result=dict(status='ADAPTER_SELECTED_RELOAD_PENDING' if selected else 'BASE_SELECTED_NO_ADAPTER_PASSED',
        selected='epoch_'+str(selected['epoch']) if selected else 'base',
        confirmed_severe_exclusions=sorted(bad),technical_exclusions=sorted(technical),
        eligible_epochs=[e['epoch'] for e in eligible],
        review_statuses=dict(Counter(r['status'] for r in review['rows'])),
        rule='Exclude source-confirmed severe regressions, then minimum token-weighted dev response+EOT NLL; earlier epoch ties; base fallback',
        review_sha256=sha256_file(review_path),diagnostic_summary_sha256=sha256_file(diagnostic/'summary.json'),
        selected_checkpoint=selected['checkpoint'] if selected else None,
        selected_dev_nll=selected['dev']['nll'] if selected else None,
        quality_gain_claim=False,reward_qualified=False,script_sha256=sha256_file(Path(__file__)))
    save(OUT/'executor_selection.json',result);print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
