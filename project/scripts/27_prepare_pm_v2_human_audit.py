#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import random
from collections import defaultdict
from pathlib import Path

from metacom_pm.config import load_config
from metacom_pm.contracts import ActionOutcome
from metacom_pm.io import iter_jsonl, sha256_file, sha256_text, write_json
from metacom_pm.pm_v2_contracts import ActionLabel, CompositeSpec
from metacom_pm.pm_v2_data import load_states

ROOT = Path(__file__).resolve().parents[1]

RESPONSE_FIELDS = (
    "emotional_support",
    "personalization",
    "memory_appropriateness",
    "factual_grounding",
    "temporal_consistency",
    "non_intrusiveness",
)
RISK_FIELDS = (
    "selected_context_misuse",
    "unnecessary_exposure",
    "stale_or_conflicting_use",
    "unsupported_personal_claim",
    "memory_omission",
    "strategy_overuse",
    "strategy_omission",
)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pm-v2-config", type=Path, default=ROOT / "configs" / "pm_v2.yaml")
    parser.add_argument("--states", type=Path, default=ROOT / "data" / "pm_v2" / "pm_v2_states.jsonl")
    parser.add_argument("--outcomes", type=Path, default=ROOT / "outputs" / "pm_v2_sweep" / "action_outcomes.jsonl")
    parser.add_argument("--labels", type=Path, default=ROOT / "outputs" / "pm_v2_judging" / "action_labels.jsonl")
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "pm_v2_human_audit")
    parser.add_argument("--seed", type=int, default=4701)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    config = load_config(args.pm_v2_config)
    audit_cfg = config["human_label_audit"]
    items = int(audit_cfg["items"])
    quality_cfg = config["quality_composite"]
    spec = CompositeSpec(
        version=str(quality_cfg["version"]),
        weights={str(key): float(value) for key, value in quality_cfg["weights"].items()},
    )

    states = load_states(args.states)
    card_to_state = {state.card_id: state for state in states}
    labels = [ActionLabel.model_validate(row) for row in iter_jsonl(args.labels)]
    label_map = {(label.state_id, label.action_id): label for label in labels}
    outcomes = [ActionOutcome.model_validate(row) for row in iter_jsonl(args.outcomes)]
    outcome_map = {
        (card_to_state[row.card_id].state_id, row.action_id): row
        for row in outcomes
        if row.card_id in card_to_state
    }
    by_regime = defaultdict(list)
    for state in states:
        candidates = [
            label
            for label in labels
            if label.state_id == state.state_id
            and (label.state_id, label.action_id) in outcome_map
        ]
        if not candidates:
            continue
        best = max(candidates, key=lambda label: spec.score(label.response))
        selected = {best.action_id, "M0+R0"}
        high_resource = max(
            candidates,
            key=lambda label: (label.observed_input_tokens, label.action_id),
        )
        selected.add(high_resource.action_id)
        regime = str(state.provenance.get("regime") or "unknown")
        for action_id in selected:
            if (state.state_id, action_id) in outcome_map:
                by_regime[regime].append((state, action_id))
    regimes = sorted(by_regime)
    if not regimes:
        raise RuntimeError("no auditable state-action pairs")
    rng = random.Random(args.seed)
    selected_pairs = []
    per_regime = max(1, items // len(regimes))
    for regime in regimes:
        rows = list(by_regime[regime])
        rng.shuffle(rows)
        selected_pairs.extend(rows[:per_regime])
    remaining = [
        row
        for regime in regimes
        for row in by_regime[regime]
        if row not in selected_pairs
    ]
    rng.shuffle(remaining)
    selected_pairs.extend(remaining[: max(0, items - len(selected_pairs))])
    selected_pairs = selected_pairs[:items]
    if len(selected_pairs) != items:
        raise RuntimeError(f"human audit could only sample {len(selected_pairs)} of {items} items")
    rng.shuffle(selected_pairs)

    args.out_dir.mkdir(parents=True, exist_ok=True)
    packet_path = args.out_dir / "human_rating_packet.csv"
    key_path = args.out_dir / "human_rating_key.json"
    if packet_path.exists() and not args.overwrite:
        raise FileExistsError(f"refusing to overwrite {packet_path}; pass --overwrite")
    packet_fields = [
        "annotator_id",
        "item_id",
        "current_user_text",
        "recent_dialogue",
        "authorized_user_context",
        "selected_context",
        "candidate_response",
        *RESPONSE_FIELDS,
        *RISK_FIELDS,
        "notes",
    ]
    key_rows = []
    with packet_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=packet_fields)
        writer.writeheader()
        for state, action_id in selected_pairs:
            outcome = outcome_map[(state.state_id, action_id)]
            item_id = "ha_" + sha256_text(
                f"{state.state_id}|{action_id}|{outcome.request_hash}"
            )[:20]
            selected_context = "\n".join(
                [f"MEMORY: {item.text}" for item in outcome.memory_view]
                + [f"STRATEGY: {card.guidance_text}" for card in outcome.strategy_view]
            )
            writer.writerow(
                {
                    "annotator_id": "",
                    "item_id": item_id,
                    "current_user_text": state.current_user_text,
                    "recent_dialogue": "\n".join(
                        f"{turn.role}: {turn.content}"
                        for turn in state.current_session_history
                    ),
                    "authorized_user_context": str(
                        state.provenance.get("authorized_user_context") or ""
                    ),
                    "selected_context": selected_context or "[none]",
                    "candidate_response": outcome.response,
                    **{field: "" for field in (*RESPONSE_FIELDS, *RISK_FIELDS)},
                    "notes": "",
                }
            )
            label = label_map[(state.state_id, action_id)]
            key_rows.append(
                {
                    "item_id": item_id,
                    "state_id": state.state_id,
                    "card_id": state.card_id,
                    "action_id": action_id,
                    "regime": state.provenance.get("regime"),
                    "llm_response": label.response.model_dump(mode="json"),
                    "llm_risk": label.risk.model_dump(mode="json"),
                    "outcome_request_hash": outcome.request_hash,
                }
            )
    report = {
        "status": "PREPARED",
        "n_items": len(key_rows),
        "packet": str(packet_path),
        "pm_v2_config": str(args.pm_v2_config),
        "pm_v2_config_sha256": sha256_file(args.pm_v2_config),
        "human_audit_config": audit_cfg,
        "quality_composite_version": spec.version,
        "key_rows": key_rows,
        "instructions": {
            "response_scale": "1-5; use each dimension independently",
            "risk_scale": "0-3; 0=no observed issue, 3=major issue",
            "minimum_annotators": int(audit_cfg["minimum_annotators"]),
            "do_not_reveal": "action_id, policy name, LLM scores",
        },
    }
    write_json(key_path, report)
    print({key: value for key, value in report.items() if key != "key_rows"})


if __name__ == "__main__":
    main()
