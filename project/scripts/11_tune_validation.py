#!/usr/bin/env python3
if __name__ == "__main__":
    from pathlib import Path
    import argparse
    from metacom_pm.io import iter_jsonl
    from metacom_pm.selection import tune_validation_policies
    ROOT = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument('--fold-mode', choices=['user','semantic'], default='user')
    p.add_argument('--fold', type=int, default=0)
    p.add_argument('--checkpoint', type=Path, required=True)
    p.add_argument('--out', type=Path, default=ROOT/'outputs/selection.json')
    p.add_argument('--judging-dir', type=Path,
                   default=ROOT/'outputs/full_judging_gemini_flash_lite_v3',
                   help='Directory containing full judging JSONL files')
    p.add_argument('--m2b-path', type=Path,
                   default=ROOT/'outputs/m2b_selected_set_omission_gemini_flash_lite_v3/memory_selected_set_omission_judgments.jsonl',
                   help='Selected-set omission labels from scripts/09b_run_m2b_audit.py')
    p.add_argument('--allow-no-m2b', action='store_true',
                   help='Non-reportable debugging only: tune without selected-set omission labels')
    a = p.parse_args()
    jdir = a.judging_dir
    if not jdir.exists():
        raise FileNotFoundError(f"Judging dir not found: {jdir}. Pass --judging-dir.")
    fold = next(x for x in iter_jsonl(ROOT/'data/synthetic/folds.jsonl')
                if x['mode']==a.fold_mode and int(x['fold'])==a.fold)
    result = tune_validation_policies(
        ROOT/'data/synthetic/runtime_states.jsonl',
        ROOT/'outputs/synthetic_sweep/action_outcomes.jsonl',
        jdir/'response_pair_judgments.jsonl',
        jdir/'memory_omission_judgments.jsonl',
        jdir/'memory_use_judgments.jsonl',
        jdir/'strategy_use_judgments.jsonl',
        jdir/'strategy_omission_judgments.jsonl',
        ROOT/'data/strategy/strategy_cards.jsonl',
        a.checkpoint,
        set(fold['validation_card_ids']),
        a.out,
        m2b_path=(None if a.allow_no_m2b else a.m2b_path),
        require_m2b=not a.allow_no_m2b,
    )
    print({
        "out": str(a.out),
        "best_fixed_action": result["best_fixed_action"],
        "budget_matched_fixed_action": result["budget_matched_fixed_action"],
        "pm": result["pm"],
        "strong_rule": result["strong_rule"],
        "pm_grid_diagnostics": result["pm_grid_diagnostics"],
        "selection_margins": result["selection_margins"],
    })
