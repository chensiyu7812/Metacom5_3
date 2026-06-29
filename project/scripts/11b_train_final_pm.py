#!/usr/bin/env python3
if __name__ == "__main__":
    from pathlib import Path
    import argparse
    from metacom_pm.io import iter_jsonl
    from metacom_pm.training import train_pm
    ROOT = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument('--feature-mode', choices=['full','text_only','metadata_only','catalog_only','text_metadata','text_metadata_stable'],
                   default='text_metadata')
    p.add_argument('--seed', type=int, default=17)
    p.add_argument('--out-dir', type=Path, default=ROOT/'outputs/final_model')
    p.add_argument('--judging-dir', type=Path,
                   default=ROOT/'outputs/full_judging_gemini_flash_lite_v3',
                   help='Directory containing full judging JSONL files')
    p.add_argument('--m2b-path', type=Path,
                   default=ROOT/'outputs/m2b_selected_set_omission_gemini_flash_lite_v3/memory_selected_set_omission_judgments.jsonl',
                   help='Selected-set omission labels from scripts/09b_run_m2b_audit.py')
    p.add_argument('--m2b-attestation', type=Path,
                   default=ROOT/'outputs/m2b_selected_set_omission_gemini_flash_lite_v3/artifact_attestation.json',
                   help='Artifact attestation for --m2b-path')
    p.add_argument('--allow-no-m2b', action='store_true',
                   help='Non-reportable debugging only: train without selected-set omission labels')
    a = p.parse_args()
    jdir = a.judging_dir
    if not jdir.exists():
        raise FileNotFoundError(f"Judging dir not found: {jdir}. Pass --judging-dir.")
    a.out_dir.mkdir(parents=True, exist_ok=True)
    cards = {x['card_id'] for x in iter_jsonl(ROOT/'data/synthetic/runtime_states.jsonl')}
    print(train_pm(
        ROOT/'data/synthetic/runtime_states.jsonl',
        jdir/'response_pair_judgments.jsonl',
        jdir/'memory_omission_judgments.jsonl',
        jdir/'memory_use_judgments.jsonl',
        jdir/'strategy_use_judgments.jsonl',
        jdir/'strategy_omission_judgments.jsonl',
        cards,
        set(),
        a.out_dir/'pm_final.joblib',
        a.out_dir/'pm_final_report.json',
        m2b_path=(None if a.allow_no_m2b else a.m2b_path),
        m2b_attestation_path=(None if a.allow_no_m2b else a.m2b_attestation),
        feature_mode=a.feature_mode,
        require_m2b=not a.allow_no_m2b,
        seed=a.seed,
    ))
