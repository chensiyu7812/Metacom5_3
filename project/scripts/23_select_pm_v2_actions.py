#!/usr/bin/env python3
from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path

import numpy as np

from metacom_pm.contracts import RuntimeState, parse_action_id
from metacom_pm.io import append_jsonl, iter_jsonl, write_json
from metacom_pm.pm_v2_data import runtime_to_pmv2_state
from metacom_pm.pm_v2_model import PMV2Model

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--checkpoint", type=Path, default=ROOT / "outputs" / "pm_v2_model" / "pm_v2.joblib")
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "pm_v2_external_selection")
    parser.add_argument("--strategy-catalog-count", type=int, default=0)
    parser.add_argument("--strategy-estimated-tokens", type=int, default=240)
    args = parser.parse_args()

    model = PMV2Model.load(args.checkpoint)
    args.out_dir.mkdir(parents=True, exist_ok=True)
    decisions_path = args.out_dir / "decisions.jsonl"
    decisions_path.write_text("", encoding="utf-8")
    actions = []
    ood = []
    for row in iter_jsonl(args.runtime):
        runtime = RuntimeState.model_validate(row)
        state = runtime_to_pmv2_state(
            runtime,
            strategy_catalog_count=args.strategy_catalog_count,
            strategy_estimated_tokens=args.strategy_estimated_tokens,
        )
        decision = model.choose(state)
        append_jsonl(decisions_path, decision.model_dump(mode="json"))
        actions.append(decision.chosen_action)
        ood.append(decision.ood_fallback_used)
    counts = Counter(actions)
    probabilities = np.asarray(list(counts.values()), dtype=float) / max(len(actions), 1)
    entropy = float(-np.sum(probabilities * np.log2(probabilities))) if len(actions) else 0.0
    report = {
        "status": "COMPLETE",
        "n": len(actions),
        "action_distribution": dict(counts),
        "action_entropy_bits": entropy,
        "m0_rate": float(np.mean([not bool(parse_action_id(action)[0]) for action in actions])) if actions else 0.0,
        "r0_rate": float(np.mean([parse_action_id(action)[1].value == "R0" for action in actions])) if actions else 0.0,
        "ood_fallback_rate": float(np.mean(ood)) if ood else 0.0,
        "decisions_path": str(decisions_path),
    }
    write_json(args.out_dir / "summary.json", report)
    print(report)


if __name__ == "__main__":
    main()
