#!/usr/bin/env python3
"""Freeze a zero-call ESC-RANK plan for the completed four-generator G0 screen."""

from __future__ import annotations

import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
SOURCE_LEDGER = PROJECT_ROOT / "outputs" / "v3_g0_four_generator_full_screen_v1_20260814" / "private_turn_ledger.jsonl"
SOURCE_CLOSEOUT = AUTHORITY / "g0_four_generator_full_screen_closeout_v1.json"
SCORER = PROJECT_ROOT / "scripts" / "v3" / "24_score_g0_four_generator_esc_rank.py"
BASE_SCORER = PROJECT_ROOT / "scripts" / "v3" / "13_score_g0_esc_rank.py"
DERIVATIVE = PROJECT_ROOT / "scripts" / "v3" / "14_derive_g0_esc_rank_anchored_scores.py"
OUT = AUTHORITY / "g0_four_generator_esc_rank_preflight_v1.json"
EXPECTED = {
    "llama31_8b_incumbent": 24,
    "nemotron3_nano_30b_a3b_default_thinking": 21,
    "qwen37_plus_nonthinking": 24,
    "qwen37_plus_thinking_upper_bound": 24,
}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def main() -> int:
    closeout = json.loads(SOURCE_CLOSEOUT.read_text(encoding="utf-8"))
    source_identity = closeout["run_identity"]
    turns: dict[tuple[str, str], set[int]] = defaultdict(set)
    for line in SOURCE_LEDGER.read_text(encoding="utf-8").splitlines():
        if not line:
            continue
        row = json.loads(line)
        if row.get("run_identity") != source_identity:
            raise RuntimeError("source ledger identity drifted")
        if row.get("event") == "supporter_succeeded":
            turns[(row["candidate_id"], row["screen_id"])].add(int(row["turn"]))
    counts: dict[str, int] = defaultdict(int)
    for (candidate_id, _), observed in turns.items():
        if observed == {1, 2, 3, 4, 5}:
            counts[candidate_id] += 1
    if dict(sorted(counts.items())) != EXPECTED:
        raise RuntimeError(f"complete-dialogue inventory drifted: {dict(counts)}")

    identity_payload = {
        "protocol": "metacom-v3-g0-four-generator-esc-rank-identity-v1",
        "source_generation_identity": source_identity,
        "source_ledger_sha256": _sha(SOURCE_LEDGER),
        "candidate_dialogue_counts": EXPECTED,
        "dimensions": ["Fluency", "Expression", "Empathy", "Information", "Humanoid", "Skill", "Overall"],
        "local_inference_calls": sum(EXPECTED.values()) * 7,
        "esc_eval_commit": "9ad46e7b5e247e824dae4633910eaa82be668beb",
        "esc_rank_revision": "450bf2eb5376c79e371aaf432925810243de1527",
        "internlm2_revision": "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2",
        "scorer_sha256": _sha(SCORER),
        "base_scorer_dependency_sha256": _sha(BASE_SCORER),
        "anchored_derivative_sha256": _sha(DERIVATIVE),
        "primary_parser": "full-string ^[0-4]$ or INVALID",
        "sensitivity_parser": "exact adapter-specific labelled sentence or full-string ordinal",
    }
    score_identity = hashlib.sha256(_canonical(identity_payload).encode("utf-8")).hexdigest()
    report = {
        "protocol": "metacom-v3-g0-four-generator-esc-rank-preflight-v1",
        "date": "2026-08-14",
        "status": "ZERO_CALL_PREFLIGHT_PASS_LOCAL_INFERENCE_REQUIRES_IDENTITY_SPECIFIC_APPROVAL",
        "api_calls": 0,
        "paid_calls": 0,
        "estimated_usd": 0,
        "source_generation_identity": source_identity,
        "source_ledger_sha256": identity_payload["source_ledger_sha256"],
        "score_run_identity": score_identity,
        "complete_dialogues": sum(EXPECTED.values()),
        "candidate_dialogue_counts": EXPECTED,
        "local_inference_calls": identity_payload["local_inference_calls"],
        "hardware_plan": "Load pinned InternLM2-chat-7B plus seven pinned English ESC-RANK adapters on RTX A6000 (cuda:1); deterministic decoding.",
        "measurement": identity_payload,
        "decision_boundary": {
            "reliability_eligible_selection_set": [
                "llama31_8b_incumbent",
                "qwen37_plus_nonthinking",
                "qwen37_plus_thinking_upper_bound",
            ],
            "nemotron_policy": "Score 21 complete dialogues descriptively only; missing trajectories and reliability hard failure remain in force.",
            "esc_rank_role": "Recognized external seven-dimension descriptive profile; no sole average and no absolute pass/fail cutoff.",
            "quality_selection": "NOT_AUTHORIZED_BY_THIS_IDENTITY",
            "judge_calls": "NOT_AUTHORIZED_BY_THIS_IDENTITY",
        },
        "identity_payload_sha256": score_identity,
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
