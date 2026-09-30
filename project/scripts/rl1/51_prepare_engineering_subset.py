#!/usr/bin/env python3
"""Explicitly post-hoc optimizer smoke. Preserve the failed original gate.

Keep all 90 accepted responses; do not redraw, relabel or repair any response.
Missing cells are reported and prohibit research/RL qualification.
"""
import json
from pathlib import Path
import sys
PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.io import sha256_file
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.executor_engineering import admitted_rows
SOURCE=PROJECT/'outputs/pm_rl1/executor_pilot_20260929_v2'
OUT=PROJECT/'outputs/pm_rl1/executor_engineering_20260929_v1'

def save(name,obj):
    OUT.mkdir(parents=True,exist_ok=True)
    with (OUT/name).open('x') as f:f.write(json.dumps(obj,ensure_ascii=False,indent=2)+'\n')

def main():
    original=json.loads((SOURCE/'condition_contract_private.json').read_text())
    summary=json.loads((SOURCE/'admission_summary.json').read_text())
    assert summary['gate']['passed'] is False
    contract=dict(original,status='POST_HOC_ENGINEERING_ONLY',eligible_for_research_or_rl=False,
        original_contract_sha256=sha256_file(SOURCE/'condition_contract_private.json'),
        original_admission_summary_sha256=sha256_file(SOURCE/'admission_summary.json'),
        post_hoc_change='After observing missing cells, authorize only optimizer/reload/diagnostic checks on ALL accepted rows; no change to original gate or individual semantic decisions.',
        limitation='Dev NLL is conditional on accepted weak targets with missing cells. It cannot measure helpfulness or qualify an executor for research/RL.',
        intended_updates='same 3 epochs and optimizer as original; no hyperparameter search or response regeneration',
        missing_original_cells=summary['missing_prefix_conditions'])
    contract['admission']=dict(original['admission'],version='posthoc-engineering-admission-v1',
        coverage_gate='Every original sampled owner and OFF/R/L labels represented per split; at least 4 historical-uptake train prefixes; retain EVERY individually accepted reply.',
        full_factorial_research_gate_passed=False)
    save('condition_contract_private.json',contract)
    review=json.loads((SOURCE/'admission_reviews_private.json').read_text())
    review=dict(review,contract_sha256=sha256_file(OUT/'condition_contract_private.json'),
        original_review_sha256=sha256_file(SOURCE/'admission_reviews_private.json'),
        original_contract_sha256=sha256_file(SOURCE/'condition_contract_private.json'),
        individual_decisions_unchanged=True)
    save('admission_reviews_private.json',review)
    pointer=json.loads((SOURCE/'author_pointer.json').read_text());save('author_pointer.json',pointer)
    run=Path(pointer['run_dir']);jobs=json.loads((run/'jobs.json').read_text())
    requests={j['request_id']:json.loads((run/(j['request_id']+'.request.json')).read_text()) for j in jobs}
    raws={j['request_id']:json.loads((run/(j['request_id']+'.raw.json')).read_text()) for j in jobs}
    rows=admitted_rows(contract,jobs,requests,raws,{r['request_identity']:r for r in review['rows']})
    assert {r['request_id'] for r in rows}=={r['request_identity'] for r in review['rows'] if r['status']=='accept'}
    save('engineering_scope.json',dict(status='ENGINEERING_ONLY_NOT_RESEARCH_OR_RL_QUALIFIED',
        original_batch=str(SOURCE),original_gate_passed=False,post_hoc=True,
        accepted_rows=len(rows),train=sum(r['split']=='train' for r in rows),dev=sum(r['split']=='dev' for r in rows),
        unchanged_review_rows_identity=digest(review['rows']),missing_cells=summary['missing_prefix_conditions'],
        planned_new_author_calls=0,planned_new_human_calls=0,planned_paid_api_calls=0,
        purpose='Exercise response-only masks, finite updates, frozen base, epoch dev selection, independent reload and 36 same-input dev generations.',
        code_hashes={n:sha256_file(PROJECT/n) for n in ['src/metacom_pm/rl1/executor_engineering.py','scripts/rl1/51_prepare_engineering_subset.py','scripts/rl1/52_train_engineering_subset.py','scripts/rl1/53_diagnose_engineering_subset.py']}))
    print(json.dumps(dict(status='POST_HOC_ENGINEERING_ONLY',rows=len(rows),original_gate_passed=False)))
if __name__=='__main__':main()
