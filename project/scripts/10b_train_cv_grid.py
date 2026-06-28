#!/usr/bin/env python3
if __name__ == "__main__":
    from pathlib import Path
    import argparse
    from metacom_pm.io import iter_jsonl, write_json
    from metacom_pm.training import train_pm
    ROOT = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument('--fold-modes', nargs='+', default=['user','semantic'])
    p.add_argument('--feature-modes', nargs='+',
                   default=['text_only','metadata_only','text_metadata','catalog_only','full'])
    p.add_argument('--seeds', type=int, nargs='+', default=[17,29,43,71,101])
    p.add_argument('--out-dir', type=Path, default=ROOT/'outputs/models_cv')
    p.add_argument('--strict-split', action='store_true')
    p.add_argument('--judging-dir', type=Path,
                   default=ROOT/'outputs/full_judging_gemini_flash_lite_v3',
                   help='Directory containing full judging JSONL files')
    p.add_argument('--m2b-path', type=Path,
                   default=ROOT/'outputs/m2b_selected_set_omission_gemini_flash_lite_v3/memory_selected_set_omission_judgments.jsonl',
                   help='Selected-set omission labels from scripts/09b_run_m2b_audit.py')
    p.add_argument('--allow-no-m2b', action='store_true',
                   help='Non-reportable debugging only: train without selected-set omission labels')
    a = p.parse_args()
    jdir = a.judging_dir
    if not jdir.exists():
        raise FileNotFoundError(f"Judging dir not found: {jdir}. Pass --judging-dir.")
    a.out_dir.mkdir(parents=True, exist_ok=True)
    folds = list(iter_jsonl(ROOT/'data/synthetic/folds.jsonl'))
    reports = []
    for fold in folds:
        if fold['mode'] not in a.fold_modes:
            continue
        for mode in a.feature_modes:
            for seed in a.seeds:
                stem = f"{mode}_{fold['mode']}_fold{fold['fold']}_seed{seed}"
                reports.append(train_pm(
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
                    feature_mode=mode,
                    require_m2b=not a.allow_no_m2b,
                    seed=seed,
                    strict_split=a.strict_split,
                ))
    write_json(a.out_dir/'grid_summary.json', {'n_models': len(reports), 'reports': reports})
    print({'n_models': len(reports)})
