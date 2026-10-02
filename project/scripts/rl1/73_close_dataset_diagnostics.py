#!/usr/bin/env python3
"""Verify preservation and independent recomputation, then freeze this audit."""
from hashlib import sha256
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[3]
PROJECT=ROOT/'project'
OUT=PROJECT/'outputs/pm_rl1/dataset_diagnostics_20260930_v1'
RECOMPUTE=Path('/tmp/pmrl1_dataset_recompute_20260930_check')

def read(path):return json.loads(path.read_text())
def digest(path):return sha256(path.read_bytes()).hexdigest()

def main():
    if (OUT/'closeout.json').exists():raise RuntimeError('Already closed')
    before=read(OUT/'preexisting_files.json')
    for path,expected in before.items():assert digest(ROOT/path)==expected,path
    previous_record=read(OUT/'prior_closeout_verified.json')
    previous=ROOT/previous_record['file']
    assert digest(previous)==previous_record['sha256']
    old=read(previous)['artifacts']
    # Previous manifest paths are relative to project, exactly as its own verifier.
    for path,expected in old.items():assert digest(PROJECT/path)==expected,path
    for key,record in read(OUT/'input_manifest.json').items():
        assert digest(Path(record['path']))==record['sha256'],key
    matched=[]
    for path in sorted(RECOMPUTE.iterdir()):
        if path.is_file():
            assert digest(path)==digest(OUT/path.name),path.name
            matched.append(path.name)
    assert len(matched)>=20
    test=subprocess.run(['/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python','-m','pytest','-q',
        'project/tests/test_rl1_dataset_diagnostics.py'],cwd=ROOT,text=True,capture_output=True)
    assert test.returncode==0,test.stdout+test.stderr
    feature_use=dict(status='offline_analysis_only_no_runtime_wiring',
        observable_candidates=['current prefix lexical markers','visible speaker roles','resource token cost','source age','raw resource type','same-head acquired counts'],
        analysis_or_evaluator_only=['gold answers','gold evidence IDs and inferred answerability','semantic review judgments','observed on/off outcome differences','judge correctness'],
        policy='No analysis CSV or gold-derived field is passed to actor, critic, retriever or Generator. No new reward formula.')
    (OUT/'feature_use_contract.json').write_text(json.dumps(feature_use,ensure_ascii=False,indent=2)+'\n')
    tracked=list(p for p in OUT.iterdir() if p.is_file())
    tracked += list((PROJECT/'scripts/rl1').glob('6[9]_*.py')) + list((PROJECT/'scripts/rl1').glob('7[0-3]_*.py'))
    tracked += [PROJECT/'tests/test_rl1_dataset_diagnostics.py',PROJECT/'docs/PM_RL1_DATASET_DIAGNOSTICS_AND_RESEARCH_PATH_20260930_ZH.md']
    summary=dict(status='DATASET_CENSUS_AND_SOURCE_DIAGNOSIS_COMPLETE_NOT_RUNTIME_REPAIR',
        input_files_verified=13,preexisting_files_unchanged=len(before),previous_artifacts_unchanged=len(old),
        independent_recompute_identical_files=matched,tests=dict(returncode=test.returncode,output=test.stdout.strip(),cases=6),
        notebook_code_cells_executed=5,semantic_sample_reviewed=20,targeted_source_traces=5,
        new_api_usd=0,model_calls=0,training_runs=0,new_human_forms=0,test_gold_semantics_inspected=False,
        source_repairs_applied=0,runtime_changed=False,official_benchmark_changed=False,
        report='docs/PM_RL1_DATASET_DIAGNOSTICS_AND_RESEARCH_PATH_20260930_ZH.md',
        next_action='Versioned train/dev source/identity repair package, then fixed executor representation/coverage contrasts. Reward remains unqualified for natural-support PPO.',
        artifacts={str(p.relative_to(PROJECT)):digest(p) for p in sorted(set(tracked))})
    (OUT/'closeout.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({k:v for k,v in summary.items() if k!='artifacts'},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
