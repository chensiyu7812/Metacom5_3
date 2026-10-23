#!/usr/bin/env python3
"""Promote an explicit allowlist of research summaries, never whole run folders.

This builds repository files only; it does not push, generate, train or call APIs.
All source artifacts remain byte-identical. Historical hashes identify the
recorded runs, not the later portability fixes in the publication commit.
"""
import argparse
from contextlib import redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import shutil

PUBLIC = {
 'engineering_20260928_v1': ['cost_reassessment.json','validation.json','census.json','capacity_probe.json','retrieval_manifest.json'],
 'evaluation_preparation_20260928_v1': ['asset_audit.json','manifest.json'],
 'measurement_pilot_20260928_v1': ['measurement_analysis.json','measured_cost_update.json','analysis_manifest.json','closeout.json'],
 'measurement_bottleneck_audit_20260929_v1': ['audit.json'],
 'measurement_resolution_20260929_v1': ['analysis_final.json','e0_comparison.json','measurement_use_decision.json','cost_closeout.json','executor_encoding_probe.json','public_observation_feature_probe.json','e0_value_update_verification.json'],
 'source_and_capacity_20260928_v1': ['dataset_freeze.json','additional_source_family_checks.json','manifest.json','capacity_probe.json','retrieval_manifest.json'],
 'executor_pilot_20260929_v1': ['stage_status.json','admission_summary.json','cost_accounting.json','continuation_scope.json','verification.json'],
 'executor_pilot_20260929_v2': ['admission_summary.json','generation_preflight.json','selection.json'],
 'source_repair_20260929_v2': ['stage_status.json','artifact_validation.json','cost_accounting.json','prior_prefix_projection_audit.json'],
 'executor_engineering_20260929_v1': ['engineering_scope.json'],
 'executor_coverage_20260929_v1': ['stopping_probe_results.json','selection.json','verification.json','closeout_manifest.json','encoding_reaudit.json'],
 'executor_training_20260930_v1': ['results_summary.json','admission_summary.json','executor_freeze.json','closeout_manifest.json'],
 'r04b_measurement_20260930_v1': ['results_summary.json','decision.json','protocol.json','models.json','capacity_census.json','validation.json','stability_and_equivalence_diagnostics.json','closeout_manifest.json'],
 'dataset_diagnostics_20260930_v1': ['census.json','capacity.json','audit_readiness.json','feature_use_contract.json','closeout.json',
    'esconv_dialogue_features.csv','owner_features.csv','history_session_features.csv','owner_history_tokens.csv',
    'qa_train_dev_features.csv','summary_train_dev_features.csv','qa_audit_registry.csv','memory_unit_features.csv',
    'rs_treatment_features.csv','prefix_features.csv','sft_features.csv','capacity_prefix_features.csv','reachable_plan_features.csv'],
}

def digest(path):
    h=sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def main(source_root, destination_root):
    source=source_root/'project/outputs/pm_rl1'
    dest=destination_root/'project/docs/reviews/20260930/pm_rl1'
    dest.mkdir(parents=True,exist_ok=True)
    if (dest/'MANIFEST.json').exists():raise RuntimeError('Snapshot already exists')
    records=[]
    def copy(src,target):
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,target)
        records.append(dict(source=str(src.relative_to(source_root)),path=str(target.relative_to(dest)),
                            source_sha256=digest(src),published_sha256=digest(target),transformation='none'))
    for run,names in PUBLIC.items():
        for name in names:copy(source/run/name,dest/run/name)
    copy(source/'dataset_diagnostics_20260930_v1/semantic_review_findings_private.json',
         dest/'dataset_diagnostics_20260930_v1/semantic_review_findings.json')
    copy(source/'dataset_diagnostics_20260930_v1/input_manifest.json',
         dest/'dataset_diagnostics_20260930_v1/source_input_manifest.json')
    # Published notebook reads checked-in summaries, never private local runs.
    src=source/'dataset_diagnostics_20260930_v1/dataset_diagnostics.ipynb';nb=json.loads(src.read_text())
    first=next(c for c in nb['cells'] if c['cell_type']=='code')
    first['source']=("from pathlib import Path\nimport json, csv\n"
        "relative = Path('project/docs/reviews/20260930/pm_rl1/dataset_diagnostics_20260930_v1')\n"
        "OUT = next((p if (p/'census.json').is_file() else p/relative) for p in (Path.cwd(), *Path.cwd().parents) if (p/'census.json').is_file() or (p/relative/'census.json').is_file())\n"
        "def read(name): return json.loads((OUT/name).read_text())\n"
        "s = read('census.json')\nc = read('capacity.json')\nprint('Loaded published research summaries')\n").splitlines(keepends=True)
    for c in nb['cells']:
        c['source']=[s.replace('semantic_review_findings_private.json','semantic_review_findings.json') for s in c['source']]
    nb['metadata']['publication_note']='Portable view of published summaries. Original execution and source-input hashes remain in local provenance; no new experiment.'
    # Stdlib-only cells are actually executed, in order, from this checkout.
    namespace={};count=0
    for c in nb['cells']:
        if c['cell_type']!='code':continue
        count+=1;buf=io.StringIO()
        with redirect_stdout(buf):exec(''.join(c['source']),namespace)
        c['execution_count']=count;c['outputs']=[dict(output_type='stream',name='stdout',text=buf.getvalue().splitlines(keepends=True))]
    target=dest/'dataset_diagnostics_20260930_v1/dataset_diagnostics.ipynb'
    target.write_text(json.dumps(nb,ensure_ascii=False,indent=2)+'\n')
    records.append(dict(source=str(src.relative_to(source_root)),path=str(target.relative_to(dest)),source_sha256=digest(src),
        published_sha256=digest(target),transformation='portable published-summary paths; five stdlib cells rerun, no Jupyter kernel'))
    inventory=[]
    for path in sorted(source.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts:
            inventory.append(dict(path=str(path.relative_to(source_root)),bytes=path.stat().st_size,sha256=digest(path)))
    (dest/'LOCAL_ARTIFACT_INVENTORY.json').write_text(json.dumps(dict(scope='Local PM-RL1 artifact metadata only; raw calls, blinding maps and checkpoints are not published',files=inventory),ensure_ascii=False,indent=2)+'\n')
    (dest/'MANIFEST.json').write_text(json.dumps(dict(status='PUBLIC_RESEARCH_SNAPSHOT',source_branch_base='ba6917069cc6257ca8e64729509ce0f27e3cdc9b',
        publication_policy='All pending code/docs/contracts/tests plus selected source-backed summaries. No raw provider payloads, human sheets, blinding keys or model weights.',
        historical_hash_policy='Recorded run/code identities remain unchanged. Later CI portability fixes do not retroactively identify an old experiment.',
        new_experiments=0,new_api_usd=0,notebook_cells_executed=count,files=records),ensure_ascii=False,indent=2)+'\n')
    print('Published',len(records),'summary artifacts; inventoried',len(inventory),'local artifacts.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--source-root',type=Path,required=True)
    parser.add_argument('--destination-root',type=Path,default=Path(__file__).resolve().parents[3])
    args=parser.parse_args();main(args.source_root.resolve(),args.destination_root.resolve())
