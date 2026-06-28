#!/usr/bin/env python3
if __name__ == "__main__":
    from pathlib import Path
    import argparse

    from metacom_pm.config import endpoint_from_config, load_config
    from metacom_pm.m2b import run_m2b_audit

    ROOT = Path(__file__).resolve().parents[1]
    p = argparse.ArgumentParser()
    p.add_argument("--config", type=Path, default=ROOT / "configs/experiment.yaml")
    p.add_argument("--endpoint", default="training_judge_gemini_flash_lite")
    p.add_argument(
        "--out-dir",
        type=Path,
        default=ROOT / "outputs/m2b_selected_set_omission_gemini_flash_lite_v3",
    )
    p.add_argument(
        "--full-judging-attestation",
        type=Path,
        default=ROOT / "outputs/full_judging_gemini_flash_lite_v3/artifact_attestation.json",
    )
    p.add_argument("--max-rows", type=int, default=None)
    p.add_argument("--overwrite", action="store_true")
    a = p.parse_args()
    ep = endpoint_from_config(load_config(a.config), a.endpoint)
    print(run_m2b_audit(
        ROOT / "data/synthetic/runtime_states.jsonl",
        ROOT / "data/synthetic/memory_backend.jsonl",
        ROOT / "outputs/synthetic_sweep/action_outcomes.jsonl",
        a.full_judging_attestation,
        a.out_dir,
        endpoint=ep,
        max_rows=a.max_rows,
        overwrite=a.overwrite,
    ))
