#!/usr/bin/env python3
"""Freeze an eight-state V5.4 generator and dual-measurement canary preflight."""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.io import canonical_json, sha256_file, stable_hex, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-effect-canary-preflight-v1"
MANIFEST_DIR = ROOT / "outputs/pm_v1_5_v5_4_development_effect_manifest_20260810"
MANIFEST = MANIFEST_DIR / "effect_group_manifest_private.jsonl"
MANIFEST_REPORT = MANIFEST_DIR / "report.json"
JUDGES = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
EXPERIMENT = ROOT / "configs/experiment.yaml"
TRANSITION = ROOT / "data/pm_v1_5_contracts/v5_4_actual_outcome_learnability_transition_v1.json"
OUT = ROOT / "outputs/pm_v1_5_v5_4_effect_canary_preflight_20260810"
COMPONENTS = ("MP", "MS", "ME", "RS")
REVIEWERS = ("anthropic_claude_haiku_4_5", "openai_gpt_5_mini")
USD_CAP = 1.0


def rows(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def select_canary(manifest: list[dict]) -> list[dict]:
    selected = []
    for component in COMPONENTS:
        candidates = sorted(
            [row for row in manifest if row["component"] == component],
            key=lambda row: stable_hex(PROTOCOL, component, row["state_id"], n=24),
        )
        first = candidates[0]
        second = next(row for row in candidates[1:] if row["pair_id_split_binding"] != first["pair_id_split_binding"] and row["source_cluster_id_split_binding"] != first["source_cluster_id_split_binding"])
        selected.extend((first, second))
    return selected


def main() -> None:
    manifest_report = json.loads(MANIFEST_REPORT.read_text())
    transition = json.loads(TRANSITION.read_text())
    judge_config = json.loads(JUDGES.read_text())
    manifest = rows(MANIFEST)
    if manifest_report["status"] != "DEVELOPMENT_EFFECT_MANIFEST_FROZEN_MEASUREMENT_AND_COST_PREFLIGHT_PENDING":
        raise RuntimeError("development manifest not ready")
    if not transition["current_authorization"]["measurement_schema_and_clear_control_preflight"]:
        raise RuntimeError("measurement preflight not authorized")
    canary = select_canary(manifest)
    input_proxy_tokens_per_group = []
    for row in canary:
        visible_chars = len(canonical_json(row["visible_dialogue"])) + len(row["actual_rank1_candidate_text"])
        assumed_six_response_chars = 6 * 1200
        input_proxy_tokens_per_group.append((visible_chars + assumed_six_response_chars) / 4)
    output_tokens_per_reviewer_group = 1800 * 2 + 2400 + 1800
    judge_usd_upper = 0.0
    reviewer_breakdown = {}
    for reviewer in REVIEWERS:
        cfg = judge_config["candidates"][reviewer]
        safety = judge_config["request_contract"]["input_token_safety_factor_by_transport"][cfg["transport"]]
        input_tokens = sum(input_proxy_tokens_per_group) * 4 * safety
        output_tokens = len(canary) * output_tokens_per_reviewer_group
        usd = input_tokens * cfg["input_usd_per_million_tokens"] / 1_000_000 + output_tokens * cfg["output_usd_per_million_tokens"] / 1_000_000
        judge_usd_upper += usd
        reviewer_breakdown[reviewer] = {"input_token_upper_proxy": round(input_tokens), "output_token_upper": output_tokens, "usd_upper_proxy": usd}
    checks = {
        "8_states": len(canary) == 8,
        "2_states_each_component": Counter(row["component"] for row in canary) == Counter({component: 2 for component in COMPONENTS}),
        "two_families_and_source_clusters_each_component": all(len({row["pair_id_split_binding"] for row in canary if row["component"] == component}) == 2 and len({row["source_cluster_id_split_binding"] for row in canary if row["component"] == component}) == 2 for component in COMPONENTS),
        "manifest_identity_frozen": manifest_report["manifest_identity"] == "v54devmanifest_5d0164fea7ecbf7c99ce071f",
        "usd_upper_within_cap": judge_usd_upper <= USD_CAP,
        "response_effect_or_oracle_absent": all(not row["response_effect_or_oracle_present"] for row in canary),
    }
    passed = all(checks.values())
    OUT.mkdir(parents=True, exist_ok=True)
    write_jsonl(OUT / "canary_effect_groups_private.jsonl", canary)
    preflight = {
        "protocol": PROTOCOL,
        "status": "CANARY_PREFLIGHT_FROZEN_RUNNER_AND_SCHEMA_TEST_PENDING" if passed else "CANARY_PREFLIGHT_FAIL_NO_LIVE_CALLS",
        "checks": checks,
        "logical_calls": {
            "generator": len(canary) * 3 * 2,
            "quality_ab_ba_dual_reviewer": len(canary) * 2 * 2,
            "absolute_risk_dual_reviewer": len(canary) * 2,
            "function_dual_reviewer": len(canary) * 2,
            "total": len(canary) * (6 + 4 + 2 + 2),
        },
        "identities": {
            "generator": "configs/experiment.yaml:endpoints.generator/meta/llama-3.1-8b-instruct",
            "reviewers": list(REVIEWERS),
            "temperature_generator": 0.7,
            "temperature_reviewers": 0.0,
            "generator_max_output_tokens": 512,
            "paired_seeds": "copied exactly from the frozen development manifest",
        },
        "execution_invariants": [
            "the generator receives the typed resource inside the prompt and writes one integrated reply; no post-generation concatenation",
            "every provider structured reply is persisted before guard/fallback, including rejected replies",
            "one generator physical attempt per logical arm; only a no-valid-completion transport failure may repeat the identical request once",
            "guard failure is a valid deployment-ITT fallback outcome and never deletes a row",
            "quality, absolute risk, and function are separate reviewer calls; candidate applicability and cost are not asked inside quality",
            "reviewer disagreement remains unresolved and is never changed to OFF or zero"
        ],
        "measurement_canary_gates": {
            "schema_and_identity_completion": "100 percent",
            "literal_response_excerpt_validation": "100 percent for nonempty excerpts",
            "quality_ab_ba_underlying_direction_consistency": ">=0.70 over resolved replicate judgments",
            "dual_reviewer_quality_direction_raw_agreement": ">=0.70",
            "dual_reviewer_function_raw_agreement": ">=0.80",
            "dual_reviewer_absolute_material_event_raw_agreement": ">=0.80",
            "raw_provider_reply_persisted_before_guard": "100 percent",
            "failure": "stop before the remaining 88 states; repair only runner/schema in a new version, never states, candidates, seeds, or observed responses"
        },
        "cost": {
            "reviewer_breakdown": reviewer_breakdown,
            "judge_usd_upper_proxy": judge_usd_upper,
            "accepted_usd_cap_required": USD_CAP,
            "generator_pricing": "NVIDIA hosted prototype endpoint currently free/rate-limited",
        },
        "live_execution_allowed": False,
        "live_blockers": ["implement raw-first-pass-persisting runner", "schema regression tests", "explicit --live --accept-usd-cap 1.0"],
        "construction_assignment_used": False,
        "response_effect_or_oracle_read": False,
        "api_calls": 0,
        "source_hashes": {"manifest": sha256_file(MANIFEST), "manifest_report": sha256_file(MANIFEST_REPORT), "judges": sha256_file(JUDGES), "experiment": sha256_file(EXPERIMENT), "transition": sha256_file(TRANSITION)},
    }
    preflight["canary_identity"] = "v54canary_" + stable_hex(canonical_json(preflight), canonical_json(canary), n=24)
    write_json(OUT / "preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
