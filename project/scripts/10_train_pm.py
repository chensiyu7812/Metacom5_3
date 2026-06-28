#!/usr/bin/env python3
if __name__ == "__main__":
    from pathlib import Path
    import argparse
    from metacom_pm.io import iter_jsonl
    from metacom_pm.training import train_pm
    ROOT = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument('--fold-mode', choices=['user','semantic'], default='user')
    p.add_argument('--fold', type=int, default=0)
    p.add_argument('--feature-mode', choices=['full','text_only','metadata_only','catalog_only','text_metadata'],
                   default='text_metadata',
                   help='text_metadata is the V3.3 main model; full/catalog_only are catalog-fingerprint diagnostics')
    p.add_argument('--seed', type=int, default=17)
    p.add_argument('--out-dir', type=Path, default=ROOT/'outputs/models')
    p.add_argument('--strict-split', action='store_true')
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
    fold = next(x for x in iter_jsonl(ROOT/'data/synthetic/folds.jsonl')
                if x['mode']==a.fold_mode and int(x['fold'])==a.fold)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    stem = f'{a.feature_mode}_{a.fold_mode}_fold{a.fold}_seed{a.seed}'
    print(train_pm(
        ROOT/'data/synthetic/runtime_states.jsonl',
        jdir/'response_pair_judgments.jsonl',
        jdir/'memory_omission_judgments.jsonl',
        jdir/'memory_use_judgments.jsonl',
        jdir/'strategy_use_judgments.jsonl',
        jdir/'strategy_omission_judgments.jsonl',
        set(fold['train_card_ids']),
        set(fold['validation_card_ids']),
        a.out_dir/f'{stem}.joblib',
        a.out_dir/f'{stem}.json',
        m2b_path=(None if a.allow_no_m2b else a.m2b_path),
        m2b_attestation_path=(None if a.allow_no_m2b else a.m2b_attestation),
        feature_mode=a.feature_mode,
        require_m2b=not a.allow_no_m2b,
        seed=a.seed,
        strict_split=a.strict_split,
    ))
