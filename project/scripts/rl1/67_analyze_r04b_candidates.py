#!/usr/bin/env python3
"""Native outcomes and true denominators; no post-hoc calibrated reward or tie rule."""
import collections
import html
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.measurement_candidates import paired_native_status,render_evidence
OUT=PROJECT/'outputs/pm_rl1/r04b_measurement_20260930_v1'


def read(p):return json.loads(p.read_text())


def main():
    for name,expected in read(OUT/'freeze.json')['files'].items():
        if sha256_file(Path(name))!=expected:raise ValueError('freeze mismatch: '+name)
    jobs=read(OUT/'jobs_private.json');cases=read(OUT/'blind_cases_private.json')
    keys={k['case_id']:k for k in read(OUT/'coordinator_only/expectations_private.json')}
    raw={}
    for j in jobs:
        p=OUT/'runs'/j['model']/(j['job_id']+'.raw.json');x=read(p)
        if x['job_id']!=j['job_id'] or x['input_identity']!=j['input_identity']:raise ValueError('raw/input mismatch')
        raw[j['model'],j['case_id'],j['draw'],j.get('side')]=x
    pairs=[];sections=[]
    for c in cases:
        cid=c['case_id'];k=keys[cid]
        f=raw['prometheus',cid,'forward',None];r=raw['prometheus',cid,'reverse',None]
        missing=dict(status='technical_missing',native_choice=None)
        p=paired_native_status(f.get('parsed',missing),r.get('parsed',missing))
        sa=raw['skywork',cid,'primary','A'];sb=raw['skywork',cid,'primary','B']
        ready=sa['finish_reason']==sb['finish_reason']=='scored'
        delta=sa['score']-sb['score'] if ready else None
        pref=('A' if delta>0 else 'B' if delta<0 else 'equal_numeric_scores') if ready else None
        row=dict(case_id=cid,category=k['category'],expected_developer_direction=k['expected_preference'],
            prometheus=dict(**p,forward=f.get('parsed'),reverse=r.get('parsed')),
            skywork=dict(score_A=sa.get('score'),score_B=sb.get('score'),delta_A_minus_B=delta,native_preference=pref),
            calibrated_four_way_label=None,independent_human_gold=False)
        repeat=raw.get(('prometheus',cid,'repeat_forward',None))
        if repeat:
            row['prometheus']['repeat']=dict(parsed=repeat.get('parsed'),
                same_output_tokens=f.get('output_token_ids')==repeat.get('output_token_ids'),
                same_choice=f.get('parsed',missing)['native_choice']==repeat.get('parsed',missing)['native_choice'],
                both_parsed=all(x.get('parsed',missing)['status']=='parsed_native_binary' for x in [f,repeat]))
            ra=raw['skywork',cid,'repeat','A'];rb=raw['skywork',cid,'repeat','B']
            row['skywork']['repeat']=dict(score_A=ra.get('score'),score_B=rb.get('score'),
                both_scored=all(x['finish_reason']=='scored' for x in [sa,sb,ra,rb]),
                identical_scores=(sa.get('score'),sb.get('score'))==(ra.get('score'),rb.get('score')))
        pairs.append(row)
        esc=lambda x:html.escape(str(x))
        sections.append(f'<section id="{cid}"><h2>{cid} · {esc(k["category"])}</h2>'
            f'<div class="pair"><article><h3>A</h3><pre>{esc(c["response_A"])}</pre></article>'
            f'<article><h3>B</h3><pre>{esc(c["response_B"])}</pre></article></div>'
            f'<p>Skywork: A={sa.get("score")}, B={sb.get("score")}; native delta={delta}</p>'
            f'<details><summary>Prometheus forward / reverse / repeat</summary><pre>{esc(f.get("text"))}</pre><hr><pre>{esc(r.get("text"))}</pre>'
            f'<hr><pre>{esc(repeat.get("text") if repeat else "not scheduled")}</pre></details>'
            f'<details><summary>Complete common legal evidence</summary><pre>{esc(render_evidence(c["evidence"]))}</pre></details>'
            f'<details><summary>Private development key (not human gold)</summary><pre>{esc(json.dumps(k,ensure_ascii=False,indent=2))}</pre></details></section>')
    stats={}
    for category in sorted({p['category'] for p in pairs}):
        rows=[p for p in pairs if p['category']==category]
        directional=[p for p in rows if p['expected_developer_direction'] in ('A','B')]
        stats[category]=dict(pairs=len(rows),
            prometheus_status=dict(collections.Counter(p['prometheus']['status'] for p in rows)),
            prometheus_consistent_expected_direction=sum(p['prometheus']['native_preference']==p['expected_developer_direction'] for p in directional),
            directional_reference_count=len(directional),
            skywork_available=sum(p['skywork']['delta_A_minus_B'] is not None for p in rows),
            skywork_expected_direction=sum(p['skywork']['native_preference']==p['expected_developer_direction'] for p in directional))
    summaries={m:read(OUT/'runs'/m/'summary.json') for m in ['prometheus','skywork']}
    summary=dict(status='NATIVE_CANDIDATE_EXPERIMENT_COMPLETE_NOT_REWARD_QUALIFICATION',
        cases=len(pairs),by_category=stats,
        calls={m:dict(planned=len(s['rows']),finish_reasons=dict(collections.Counter(r['finish_reason'] for r in s['rows'])),
            load_seconds=s['load_seconds'],wall_seconds=s['total_wall_seconds']) for m,s in summaries.items()},
        prometheus_parse_counts=dict(collections.Counter(x.get('parsed',{}).get('status','technical_missing') for (m,*_),x in raw.items() if m=='prometheus')),
        global_context_coverage='see capacity_census.json; complete turns or missing, never truncation',
        independent_human_preferences=0,calibrated_equivalence=False,calibrated_uncertainty=False,
        structured_factual_detector_validated=False,reward_mapping=None,natural_support_ppo_eligible=False,
        costs=dict(api_usd=0,local_cost_not_monetized=True),
        limitations=['Development controls authored by coordinating AI; actual pairs have no independent gold.',
          'Current run tests native ordering, not a validated four-way support-quality measurement.',
          'Order conflict, raw equality and small score gaps do not establish semantic equivalence.',
          'Scalar reward has no rationale or A/B position metric; those are not applicable.',
          'Repeated prompts/reversed pairs and same-prefix conditions are not independent observations.'])
    for name,x in [('pair_results_private.json',pairs),('results_summary.json',summary)]:
        (OUT/name).write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n')
    (OUT/'review.html').write_text('<!doctype html><meta charset="utf-8"><title>R04B finite native judge experiment</title><style>body{font:16px system-ui;max-width:1500px;margin:30px auto;padding:20px;background:#f6f7f9;color:#182234}section{background:white;padding:22px;margin:22px 0;border:1px solid #bbc6d2}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:15px/1.5 system-ui}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}article{padding:16px;background:#eef3f7}summary{cursor:pointer;padding:12px}</style><h1>R04B · 40 development pairs</h1><p>Actual executor pairs and source-bound controls. Developer expectations are not human gold. Native scores/forced A-B are not calibrated reward or four-way labels. Private development review only.</p>'+''.join(sections))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
