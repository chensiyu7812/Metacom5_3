#!/usr/bin/env python3
"""Additional offline parsing view; no model retry or semantic answer repair."""
from collections import Counter
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.quote_normalization import parse_typographic_view,VERSION
OUT=PROJECT/'outputs/pm_rl1/measurement_pilot_20260928_v1'


def main():
    ptr=json.loads((OUT/'judge_pointer.json').read_text());run=Path(ptr['run_dir'])
    summary=json.loads((run/'summary.json').read_text());assert sha256_file(run/'summary.json')==ptr['summary_sha256']
    jobs={j['job_id']:j for j in json.loads((OUT/'exam_private.json').read_text())['jobs']}
    dest=OUT/'typographic_parser_v2';dest.mkdir(exist_ok=True);rows=[];recovered=[]
    for r in summary['rows']:
        j=jobs[r['job_id']];raw=json.loads((run/(r['request_id']+'.raw.json')).read_text())
        result=parse_typographic_view(raw['text'],evidence=j['evidence'],reply=j['reply'],
            runtime_identity=ptr['runtime_identity'],draw_id=j['draw_id'],finish_reason=raw['finish_reason'])
        (dest/(r['request_id']+'.measurement.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
        rows.append(dict(**{k:v for k,v in r.items() if k not in ('q','m','measurement_status','error')},
            q=result['q'],m=result['m'],measurement_status=result['measurement_status'],error=result.get('error'),
            strict_parser_status=r['measurement_status'],quote_transformations=result.get('quote_transformations',[])))
        if r['q'] is None and result['q'] is not None:recovered.append(r['job_id'])
        if r['q'] is not None:assert (r['q'],r['m'])==(result['q'],result['m'])
    by={(r['pilot_index'],r['condition'],r['repeat']):r for r in rows}
    paired={}
    for label,right in [('natural','ON'),('damage','damage'),('style','style')]:
        diffs=[]
        for i in range(1,13):
            a=by.get((i,'OFF',0));b=by.get((i,right,0))
            if a and b and a['q'] is not None and b['q'] is not None:
                diffs.append(dict(pilot_index=i,delta_q=b['q']-a['q'],delta_m=b['m']-a['m'],
                    delta_utility=(b['q']-a['q'])/4-(b['m']-a['m'])))
        paired[label]=dict(valid_pairs=len(diffs),rows=diffs)
    repeated=[]
    for r in rows:
        if r['repeat']!=1:continue
        a=by.get((r['pilot_index'],r['condition'],0))
        if a and a['q'] is not None and r['q'] is not None:
            repeated.append(dict(pilot_index=r['pilot_index'],condition=r['condition'],
                delta_q=r['q']-a['q'],delta_m=r['m']-a['m'],delta_utility=(r['q']-a['q'])/4-(r['m']-a['m'])))
    report=dict(status='ADDITIONAL_TYPOGRAPHY_ONLY_VIEW_NOT_NEW_JUDGE_RUN',parser_version=VERSION,
        rows=rows,status_counts=dict(Counter(r['measurement_status'] for r in rows)),recovered_from_strict=len(recovered),
        recovered_job_ids=recovered,comparisons=paired,repeat=dict(valid_pairs=len(repeated),rows=repeated,
        utility_changed=sum(r['delta_utility']!=0 for r in repeated),abs_utility_delta_gt_full_resource_penalty=sum(abs(r['delta_utility'])>.05 for r in repeated)),
        no_semantic_scores_changed=True,raw_preserved=True,new_model_calls=0,reward_eligible=False,
        script_sha256=sha256_file(Path(__file__)),parser_code_sha256=sha256_file(PROJECT/'src/metacom_pm/rl1/quote_normalization.py'))
    (dest/'analysis.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in ['status_counts','recovered_from_strict','comparisons','repeat']},ensure_ascii=False,indent=2))


if __name__=='__main__':main()
