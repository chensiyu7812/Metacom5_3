#!/usr/bin/env python3
"""Dual re-review the one outcome-blind repaired V4 fidelity pair and close the gate."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Literal


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.contracts import StrictModel  # noqa: E402
from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from pydantic import Field  # noqa: E402

PROTOCOL = "pm-v1.5-v5.4-v4-repaired-pair-dual-fidelity-v1"
PAIR_ID = "v54v4pair_f58fd8f19371663cdb"
DIR = ROOT / "outputs/pm_v1_5_v5_4_v4_fidelity_v2_20260810"
PACKET = DIR / "fidelity_v2_packet_private_assignment_outcome_blind.jsonl"
ORIGINAL = DIR / "fidelity_v2_report.json"
ADJUDICATION = DIR / "single_flag_adjudication_report.json"
AUTHOR_REPAIR = ROOT / "outputs/pm_v1_5_v5_4_state_local_authoring_v4_20260810/fidelity_failed_pair_reauthor_v1_report.json"
RANK1 = ROOT / "outputs/pm_v1_5_v5_4_v4_state_local_actual_rank1_20260810/report.json"
ENDPOINTS = ROOT / "configs/pm_v1_5_role_decomposed_judge_qualification_v1.json"
REVIEW_IMPL = ROOT / "scripts/v1_5/148l_run_v5_4_v4_dual_fidelity_v2_v1_5.py"

Tri = Literal["PASS", "FAIL", "UNRESOLVED"]
Event = Literal["ABSENT", "PRESENT", "UNRESOLVED"]


class LocalJudgment(StrictModel):
    pair_id: str = Field(min_length=1)
    world_fidelity_A: Tri
    world_fidelity_B: Tri
    dialogue_coherence_A: Tri
    dialogue_coherence_B: Tri
    assignment_fidelity_A: Tri
    assignment_fidelity_B: Tri
    single_axis_minimality: Tri
    unsupported_critical_fact: Event
    response_or_scaffold_leak: Event
    concise_rationale: str = Field(min_length=1)


def rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def review_impl():
    spec = importlib.util.spec_from_file_location("v4_fidelity_review_impl", REVIEW_IMPL)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def projection(row: dict) -> str:
    tri = ("world_fidelity_A", "world_fidelity_B", "dialogue_coherence_A", "dialogue_coherence_B", "assignment_fidelity_A", "assignment_fidelity_B", "single_axis_minimality")
    events = ("unsupported_critical_fact", "response_or_scaffold_leak")
    if any(row[field] == "FAIL" for field in tri) or any(row[field] == "PRESENT" for field in events):
        return "FAIL"
    if any(row[field] == "UNRESOLVED" for field in tri + events):
        return "UNRESOLVED"
    return "PASS"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    packet = {row["pair_id"]: row for row in rows(PACKET)}
    item = packet[PAIR_ID]
    original = json.loads(ORIGINAL.read_text())
    adjudication = json.loads(ADJUDICATION.read_text())
    repair = json.loads(AUTHOR_REPAIR.read_text())
    rank1 = json.loads(RANK1.read_text())
    if adjudication["pair_projections"].get(PAIR_ID) != "FAIL" or repair["status"] != "PAIR_REAUTHORED_OUTCOME_BLIND_AWAITING_RANK1_AND_DUAL_REREVIEW":
        raise RuntimeError("re-review lineage invalid")
    if rank1["status"] != "STATE_LOCAL_RANK1_MACHINE_PASS_AWAITING_FIDELITY":
        raise RuntimeError("repaired state-local Rank-1 failed")
    module = review_impl()
    configs = json.loads(ENDPOINTS.read_text())
    preflight = {
        "protocol": PROTOCOL, "status": "LIVE_READY", "logical_calls": 2,
        "maximum_physical_attempts": 4, "accepted_usd_cap_required": 0.10,
        "pair_id": PAIR_ID, "packet_sha256": sha256_file(PACKET),
        "author_rank1_response_outcome_visible": False,
    }
    write_json(DIR / "repaired_pair_dual_rereview_preflight.json", preflight)
    print(json.dumps(preflight, ensure_ascii=False, indent=2), flush=True)
    if not args.live:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.10:
        raise SystemExit("live rereview requires --accept-usd-cap 0.10")
    ledger = PersistentAttemptLedger(
        DIR / "repaired_pair_dual_rereview_transport_v2_attempt_ledger.jsonl", stage=PROTOCOL + "_transport_v2",
        expected_calls={"repairfid_v2_" + reviewer: 2 for reviewer in ("REVIEWER_A", "REVIEWER_B")},
        maximum_total_attempts=4,
    )
    completed = {row["reviewer_id"]: row for row in rows(DIR / "repaired_pair_dual_rereview_completed.jsonl")}
    for index, (reviewer, endpoint_key) in enumerate((("REVIEWER_A", "anthropic_claude_haiku_4_5"), ("REVIEWER_B", "openai_gpt_5_mini")), start=1):
        ep = module.endpoint(configs["candidates"][endpoint_key])
        client = make_client(ep)
        key = "repairfid_v2_" + reviewer
        prompt = module.messages(item, reviewer)
        try:
            while reviewer not in completed and not ledger.exhausted(key):
                reservation = ledger.reserve(key, record_ids={"pair_id": PAIR_ID, "reviewer": reviewer}, prompt_sha256=sha256_text(canonical_json(prompt)))
                response = None
                try:
                    response, parsed = client.chat(prompt, temperature=0.0, max_tokens=850, seed=20260820 + index, response_schema=LocalJudgment, retries=1)
                    if parsed is None or parsed.pair_id != PAIR_ID:
                        raise ValueError("rereview schema/identity")
                    row = parsed.model_dump(mode="json")
                    row.update({"protocol": PROTOCOL, "reviewer_id": reviewer, "component": "MP", "response_or_outcome_visible": False})
                    ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": ep.model})
                    completed[reviewer] = row
                    write_jsonl(DIR / "repaired_pair_dual_rereview_completed.jsonl", list(completed.values()))
                except Exception as exc:
                    ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": ep.model})
                    prompt += [{"role": "user", "content": "Return every strict fidelity field; no should-open or outcome judgment."}]
        finally:
            client.close()
    if set(completed) != {"REVIEWER_A", "REVIEWER_B"}:
        raise SystemExit("repaired pair rereview incomplete")
    projections = {reviewer: projection(row) for reviewer, row in completed.items()}
    repaired_pass = all(value == "PASS" for value in projections.values())
    first_dispute = "v54v4pair_5af0620d4bfad3e37a"
    first_adjudicated_pass = adjudication["pair_projections"].get(first_dispute) == "PASS"
    final_pass = repaired_pass and first_adjudicated_pass and original["gates"]["raw_agreement"] and original["gates"]["gwet_ac1"] and original["gates"]["consensus_pass_total"] and original["gates"]["consensus_pass_each_component"] and original["gates"]["single_or_dual_scaffold_zero"]
    final = {
        "protocol": PROTOCOL,
        "status": "V4_FIDELITY_V2_FINAL_PASS_BOUNDED_OBSERVABILITY_AUTHORIZED" if final_pass else "V4_FIDELITY_V2_FINAL_FAIL",
        "original_raw_reliability": original["reliability"],
        "original_consensus_pass_total": original["consensus_pass_total"],
        "first_single_flag_outcome_blind_adjudication": {"pair_id": first_dispute, "projection": adjudication["pair_projections"].get(first_dispute)},
        "second_single_flag_original_adjudication": {"pair_id": PAIR_ID, "projection": adjudication["pair_projections"].get(PAIR_ID)},
        "second_pair_reauthored_outcome_blind": True,
        "repaired_pair_dual_rereview_projections": projections,
        "final_resolved_pass_total": 48 if final_pass else None,
        "final_resolved_pass_by_component": {"MP": 12, "MS": 12, "ME": 12, "RS": 12} if final_pass else None,
        "all_critical_flags_resolved": final_pass,
        "bounded_observability_materialization_authorized": final_pass,
        "response_effect_calls_authorized": False,
        "pm_training_authorized": False,
        "response_effect_or_oracle_outcome_read": False,
        "hashes": {
            "packet": sha256_file(PACKET), "original_report": sha256_file(ORIGINAL),
            "adjudication": sha256_file(ADJUDICATION), "repair": sha256_file(AUTHOR_REPAIR),
            "rank1": sha256_file(RANK1),
            "rereview": sha256_file(DIR / "repaired_pair_dual_rereview_completed.jsonl"),
        },
    }
    write_json(DIR / "fidelity_v2_final_resolved_report.json", final)
    print(json.dumps(final, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
