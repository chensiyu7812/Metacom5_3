#!/usr/bin/env python3
"""Materialize the zero-call fair E-I-A/guardrail judge canary."""

from __future__ import annotations

import hashlib
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
from metacom_pm.v3_generator_fair_judge import (  # noqa: E402
    AbsoluteGuardrailReview,
    EIAPairReview,
    EIA_CRITERIA,
    eia_messages,
    guardrail_messages,
)

AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
PROTOCOL = AUTHORITY / "generator_fair_selection_protocol_v1.json"
CARD_MANIFEST = AUTHORITY / "g0_research_aligned_screening_manifest_v2.jsonl"
SOURCE_LEDGER = PROJECT_ROOT / "outputs" / "v3_g0_four_generator_full_screen_v1_20260814" / "private_turn_ledger.jsonl"
ENDPOINTS = PROJECT_ROOT / "configs" / "paper1_rs_ms_quality_risk_measurement_endpoints_v1.json"
INSTRUMENT = PROJECT_ROOT / "src" / "metacom_pm" / "v3_generator_fair_judge.py"
RUNNER = PROJECT_ROOT / "scripts" / "v3" / "26_run_g0_fair_judge_canary.py"
OUT = PROJECT_ROOT / "outputs" / "v3_g0_fair_judge_canary_manifest_20260814"
PREFLIGHT = AUTHORITY / "g0_fair_judge_canary_preflight_v1.json"
CANDIDATES = ["llama31_8b_incumbent", "qwen37_plus_nonthinking", "qwen37_plus_thinking_upper_bound"]
PAIRS = [(CANDIDATES[0], CANDIDATES[1]), (CANDIDATES[0], CANDIDATES[2]), (CANDIDATES[1], CANDIDATES[2])]
CONSTRUCTS = ["Exploration", "Insight", "Action"]
SELECTED_ORDERS = [1, 2, 3, 4, 11, 14]


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha_file(path: Path) -> str:
    return sha_bytes(path.read_bytes())


def stable(*values: object, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(map(str, values)).encode()).hexdigest()[:length]


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def conversation(rows: list[dict[str, Any]]) -> str:
    rows = sorted(rows, key=lambda row: row["turn"])
    if [row["turn"] for row in rows] != [1, 2, 3, 4, 5]:
        raise RuntimeError("canary requires a complete five-turn dialogue")
    lines = ["Supporter: Hello, I'm your personal assistant. You can confide in me about any worries or concerns you may have!"]
    for row in rows:
        lines.extend([f"Seeker: {row['seeker_text']}", f"Supporter: {row['supporter_text']}"])
    return "\n".join(lines)


def main() -> int:
    protocol = json.loads(PROTOCOL.read_text(encoding="utf-8"))
    cards = [row for row in read_jsonl(CARD_MANIFEST) if row["development_order"] in SELECTED_ORDERS]
    if len(cards) != 6 or sorted(row["source"] for row in cards) != ["EPITOME", "ESconv", "ESconv", "ExTES", "MHP", "Psych"]:
        raise RuntimeError("source-stratified six-card selection drifted")
    events = [row for row in read_jsonl(SOURCE_LEDGER) if row.get("event") == "supporter_succeeded"]
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        grouped[(row["screen_id"], row["candidate_id"])].append(row)
    selected_screens = {row["screen_id"] for row in cards}
    conversations = {
        (screen, candidate): conversation(rows)
        for (screen, candidate), rows in grouped.items()
        if screen in selected_screens and candidate in CANDIDATES
    }

    calls: list[dict[str, Any]] = []
    private_map: list[dict[str, Any]] = []
    repeat_screens = {row["screen_id"] for row in cards if row["development_order"] in {1, 2}}
    for card in cards:
        screen = card["screen_id"]
        for pair_index, (left, right) in enumerate(PAIRS):
            for construct in CONSTRUCTS:
                base_key = stable(screen, left, right, construct)
                for orientation, (a, b) in (("AB", (left, right)), ("BA", (right, left))):
                    unit_id = f"eia_{stable(base_key, orientation)}"
                    messages = eia_messages(unit_id=unit_id, construct=construct, conversation_a=conversations[(screen, a)], conversation_b=conversations[(screen, b)])
                    calls.append({"logical_call_id": unit_id, "kind": "eia", "screen_id": screen, "construct": construct, "orientation": orientation, "messages": messages, "schema": "EIAPairReview", "repeat_of": None})
                    private_map.append({"logical_call_id": unit_id, "candidate_a": a, "candidate_b": b, "canonical_pair": [left, right], "card_key": card["card_key"]})
                if screen in repeat_screens:
                    unit_id = f"repeat_{stable(base_key)}"
                    messages = eia_messages(unit_id=unit_id, construct=construct, conversation_a=conversations[(screen, left)], conversation_b=conversations[(screen, right)])
                    calls.append({"logical_call_id": unit_id, "kind": "eia_repeat", "screen_id": screen, "construct": construct, "orientation": "AB_REPEAT", "messages": messages, "schema": "EIAPairReview", "repeat_of": f"eia_{stable(base_key, 'AB')}"})
                    private_map.append({"logical_call_id": unit_id, "candidate_a": left, "candidate_b": right, "canonical_pair": [left, right], "card_key": card["card_key"]})
        for candidate in CANDIDATES:
            item_id = f"guard_{stable(screen, candidate)}"
            messages = guardrail_messages(item_id=item_id, conversation=conversations[(screen, candidate)])
            calls.append({"logical_call_id": item_id, "kind": "guardrail", "screen_id": screen, "construct": None, "orientation": None, "messages": messages, "schema": "AbsoluteGuardrailReview", "repeat_of": None})
            private_map.append({"logical_call_id": item_id, "candidate": candidate, "card_key": card["card_key"]})

    calls.sort(key=lambda row: stable("execution-order", row["logical_call_id"]))
    if (sum(row["kind"] == "eia" for row in calls), sum(row["kind"] == "eia_repeat" for row in calls), sum(row["kind"] == "guardrail" for row in calls), len(calls)) != (108, 18, 18, 144):
        raise RuntimeError("canary call accounting drifted")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "calls_private.jsonl").write_text("".join(canonical(row) + "\n" for row in calls), encoding="utf-8")
    (OUT / "private_blinding_map.jsonl").write_text("".join(canonical(row) + "\n" for row in private_map), encoding="utf-8")
    endpoint = json.loads(ENDPOINTS.read_text(encoding="utf-8"))["candidates"]["openai_gpt_5_6_sol"]
    prompt_chars = sum(sum(len(message["content"]) for message in row["messages"]) for row in calls)
    estimated_input_tokens = int(prompt_chars / 4)
    expected_output_tokens = len(calls) * 260
    point_estimate = estimated_input_tokens * endpoint["input_usd_per_million_tokens"] / 1_000_000 + expected_output_tokens * endpoint["output_usd_per_million_tokens"] / 1_000_000
    payload = {
        "protocol": "metacom-v3-g0-fair-judge-canary-identity-v1",
        "fair_protocol_sha256": sha_file(PROTOCOL),
        "source_ledger_sha256": sha_file(SOURCE_LEDGER),
        "card_manifest_sha256": sha_file(CARD_MANIFEST),
        "calls_sha256": sha_file(OUT / "calls_private.jsonl"),
        "blinding_map_sha256": sha_file(OUT / "private_blinding_map.jsonl"),
        "instrument_sha256": sha_file(INSTRUMENT),
        "runner_sha256": sha_file(RUNNER),
        "endpoint_config_sha256": sha_file(ENDPOINTS),
        "judge_model": endpoint["model"],
        "logical_calls": len(calls),
        "schemas": {"EIAPairReview": EIAPairReview.model_json_schema(), "AbsoluteGuardrailReview": AbsoluteGuardrailReview.model_json_schema()},
        "construct_criteria": EIA_CRITERIA,
    }
    identity = sha_bytes(canonical(payload).encode())
    report = {
        "protocol": "metacom-v3-g0-fair-judge-canary-preflight-v1",
        "date": "2026-08-14",
        "status": "ZERO_CALL_PREFLIGHT_PASS_IDENTITY_SPECIFIC_APPROVAL_REQUIRED",
        "run_identity": identity,
        "api_calls": 0,
        "cards": [{key: row[key] for key in ("screen_id", "card_key", "source", "development_order")} for row in cards],
        "candidates": CANDIDATES,
        "call_accounting": {"eia_dual_order": 108, "repeatability": 18, "absolute_guardrail": 18, "total": 144},
        "judge": {key: endpoint[key] for key in ("model", "family", "base_url", "input_usd_per_million_tokens", "output_usd_per_million_tokens", "openai_reasoning_effort")},
        "budget": {"prompt_characters": prompt_chars, "estimated_input_tokens_char_div_4": estimated_input_tokens, "expected_output_tokens_260_per_call": expected_output_tokens, "point_estimate_usd": point_estimate, "suggested_ceiling_usd": round(point_estimate * 1.35 + 0.1, 2)},
        "canary_boundary": "Qualifies judge validity, orientation stability, repeatability, and resolution only; cannot select or tune a generator.",
        "identity_payload_sha256": identity,
        "private_manifest_hashes": {"calls": payload["calls_sha256"], "blinding_map": payload["blinding_map_sha256"]},
    }
    PREFLIGHT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
