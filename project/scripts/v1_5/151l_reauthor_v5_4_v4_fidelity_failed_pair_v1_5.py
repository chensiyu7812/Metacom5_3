#!/usr/bin/env python3
"""Outcome-blind reauthoring of the single adjudicated V4 fidelity failure."""

from __future__ import annotations

import argparse
from difflib import SequenceMatcher
import importlib.util
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-v4-fidelity-failed-pair-reauthor-v1"
PAIR_ID = "v54v4pair_f58fd8f19371663cdb"
DIR = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810"
PACKET = DIR / "authoring_v4_packet_private_outcome_blind.jsonl"
AUTHORED = DIR / "authored_pairs_v4_after_rank1_repair_outcome_blind.jsonl"
ADJUDICATION = ROOT / "outputs/pm_v1_5_v5_4_v4_fidelity_v2_20260810/single_flag_adjudication_report.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
HELPER = ROOT / "scripts/v1_5/146l_reauthor_v5_4_v4_rank1_absent_pair_v1_5.py"
REPAIR = DIR / "fidelity_failed_pair_reauthor_v1_outcome_blind.jsonl"
MERGED = DIR / "authored_pairs_v4_after_fidelity_repair_outcome_blind.jsonl"


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def helper():
    spec = importlib.util.spec_from_file_location("v4_reauthor_helper", HELPER)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def norm(text: str) -> str:
    return " ".join(re.findall(r"[a-z0-9']+", text.casefold()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    packet = {row["pair_id"]: row for row in rows(PACKET)}
    authored = {row["pair_id"]: row for row in rows(AUTHORED)}
    source, old = packet[PAIR_ID], authored[PAIR_ID]
    adjudication = json.loads(ADJUDICATION.read_text())
    if adjudication["pair_projections"].get(PAIR_ID) != "FAIL":
        raise RuntimeError("target pair is not the frozen adjudicated failure")
    module = helper()
    configs = json.loads(ENDPOINTS.read_text())
    endpoint_key = source["assigned_author_endpoint"]
    ep = module._endpoint(configs["candidates"][endpoint_key])
    system = """Reauthor exactly one outcome-blind CURRENT USER minimal pair after a construction-fidelity failure. Keep the exact public prefix unchanged and write no assistant response.

Trusted facts: Jamie is anxious during pregnancy; stress affects partner Dan; friend Ann relationship is strained due to prior social-media issues. The old B turn failed because "I haven't told Dan the details about Ann" invented a non-disclosure history. Do not assert who has or has not been told anything, and invent no action/result/time/motive.

Variant A must keep Ann visible but make the immediate goal independent of Ann-specific relationship personalization, focusing on self-directed coping. Variant B must keep Ann visible and leave an incremental relationship-approach slot that the verified Ann fact can personalize, without restating the social-media cause. Keep the same user, entity, central topic, tone, syntax, and similar length; change only the current goal. Return only the strict schema."""
    payload = {
        "pair_id": PAIR_ID,
        "exact_locked_prefix": source["exact_public_source_visible_prefix_locked"],
        "original_public_current_turn_world_tone": source["original_current_user_turn_for_world_and_tone_only"],
        "old_pair": {"A": old["variant_A_current_user_turn"], "B": old["variant_B_current_user_turn"]},
        "response_effect_or_oracle_outcome_visible": False,
    }
    messages = [{"role": "system", "content": system}, {"role": "user", "content": canonical_json(payload)}]
    preflight = {
        "protocol": PROTOCOL, "status": "LIVE_READY", "logical_calls": 1,
        "maximum_physical_attempts": 2, "accepted_usd_cap_required": 0.05,
        "assigned_author_endpoint": endpoint_key, "adjudication_sha256": sha256_file(ADJUDICATION),
        "response_effect_or_oracle_outcome_visible": False,
    }
    write_json(DIR / "fidelity_failed_pair_reauthor_v1_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.05:
        raise SystemExit("live repair requires --accept-usd-cap 0.05")
    call_key = "v4fidrepair_" + sha256_text(PROTOCOL + PAIR_ID)[:20]
    ledger = PersistentAttemptLedger(
        DIR / "fidelity_failed_pair_reauthor_v1_attempt_ledger.jsonl", stage=PROTOCOL,
        expected_calls={call_key: 2}, maximum_total_attempts=2,
    )
    client = make_client(ep)
    repaired = None
    try:
        while repaired is None and not ledger.exhausted(call_key):
            reservation = ledger.reserve(call_key, record_ids={"pair_id": PAIR_ID}, prompt_sha256=sha256_text(canonical_json(messages)))
            response = None
            try:
                response, parsed = client.chat(messages, temperature=0.0, max_tokens=550, seed=20260810, response_schema=module.Pair, retries=1)
                if parsed is None or parsed.pair_id != PAIR_ID:
                    raise ValueError("schema/identity")
                a = " ".join(parsed.variant_A_current_user_turn.split())
                b = " ".join(parsed.variant_B_current_user_turn.split())
                aw, bw = len(a.split()), len(b.split())
                similarity = SequenceMatcher(None, norm(a), norm(b)).ratio()
                if "ann" not in norm(a).split() or "ann" not in norm(b).split():
                    raise ValueError("Ann absent")
                if "haven't told" in b.casefold() or "have not told" in b.casefold():
                    raise ValueError("unsupported non-disclosure retained")
                if not 8 <= aw <= 80 or not 8 <= bw <= 80 or max(aw, bw) / min(aw, bw) > 1.5 or similarity < 0.25:
                    raise ValueError("minimal pair surface")
                repaired = {
                    **old,
                    "protocol": PROTOCOL,
                    "variant_A_current_user_turn": a,
                    "variant_B_current_user_turn": b,
                    "pair_character_similarity": similarity,
                    "pair_word_length_ratio": max(aw, bw) / min(aw, bw),
                    "supersedes_authored_sha256": sha256_text(canonical_json(old)),
                    "repair_reason": "ADJUDICATED_UNSUPPORTED_NON_DISCLOSURE_HISTORY_IN_VARIANT_B",
                    "response_effect_or_oracle_outcome_read": False,
                }
                ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=repaired, metadata={"endpoint": endpoint_key, "model": ep.model})
            except Exception as exc:
                ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": ep.model})
                messages += [{"role": "user", "content": "Return both complete turns again. Keep Ann in both and do not invent any disclosure or non-disclosure to Dan."}]
    finally:
        client.close()
    if repaired is None:
        raise SystemExit("fidelity repair exhausted")
    write_jsonl(REPAIR, [repaired])
    authored[PAIR_ID] = repaired
    write_jsonl(MERGED, list(authored.values()))
    report = {
        "protocol": PROTOCOL, "status": "PAIR_REAUTHORED_OUTCOME_BLIND_AWAITING_RANK1_AND_DUAL_REREVIEW",
        "pair_id": PAIR_ID, "attempts": ledger.started_attempts,
        "response_effect_or_oracle_outcome_read": False,
        "repair_sha256": sha256_file(REPAIR), "merged_sha256": sha256_file(MERGED),
    }
    write_json(DIR / "fidelity_failed_pair_reauthor_v1_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
