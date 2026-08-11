#!/usr/bin/env python3
"""One-shot V2.1 paraphrase recovery for the sole candidate-copy failure."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.attempt_ledger import PersistentAttemptLedger  # noqa: E402
from metacom_pm.io import canonical_json, sha256_text, write_json, write_jsonl  # noqa: E402


RUNNER_PATH = ROOT / "scripts/v1_5/134l_run_v5_4_source_prefix_locked_authoring_v2_v1_5.py"
spec = importlib.util.spec_from_file_location("v54_author_v2", RUNNER_PATH)
runner = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(runner)

PROTOCOL = "pm-v1.5-v5.4-source-prefix-locked-authoring-v2.1-candidate-copy-recovery"
DIR = ROOT / "outputs/pm_v1_5_v5_4_source_prefix_locked_authoring_v2_20260810"
MISSING_ID = "v54pair_ad22d07ce64e9e3a327a"


def main() -> None:
    packet = {str(row["pair_id"]): row for row in runner._jsonl(runner.PACKET)}
    completed = {str(row["pair_id"]): row for row in runner._jsonl(runner.COMPLETED)}
    missing = sorted(set(packet) - set(completed))
    if missing != [MISSING_ID]:
        raise SystemExit(f"expected sole documented candidate-copy failure; got {missing}")
    item = packet[MISSING_ID]
    configs = json.loads(runner.ENDPOINTS.read_text())
    endpoint_key = str(item["assigned_author_endpoint"])
    if endpoint_key != "anthropic_claude_haiku_4_5":
        raise SystemExit("documented recovery author identity changed")
    endpoint = runner._endpoint(configs["candidates"][endpoint_key])
    forbidden_exact = str(item["frozen_candidate_text"])
    messages = runner._messages(item) + [{
        "role": "user",
        "content": "Transport/content recovery only: the previous pair copied this exact candidate surface and was rejected. Preserve the same A/B semantics, but paraphrase any needed fact so the following exact substring does not occur anywhere: " + json.dumps(forbidden_exact),
    }]
    ledger = PersistentAttemptLedger(
        DIR / "authoring_v2_candidate_copy_recovery_ledger.jsonl",
        stage="v5_4_source_prefix_locked_candidate_copy_recovery",
        expected_calls={"recovery_" + MISSING_ID: 1}, maximum_total_attempts=1,
    )
    reservation = ledger.reserve("recovery_" + MISSING_ID, record_ids={"pair_id": MISSING_ID, "author": endpoint_key}, prompt_sha256=sha256_text(canonical_json(messages)))
    client = make_client(endpoint); response = None
    try:
        try:
            response, parsed = client.chat(messages, temperature=0.0, max_tokens=runner.MAX_OUTPUT_TOKENS, seed=20260810, response_schema=runner.UserTurnPair, retries=1)
            if parsed is None: raise ValueError("structured recovery pair missing")
            row = runner._validate(parsed, item, endpoint_key)
            row.update({"execution_protocol": PROTOCOL, "candidate_copy_recovery": True})
            ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"endpoint": endpoint_key, "model": endpoint.model})
            completed[MISSING_ID] = row; write_jsonl(runner.COMPLETED, list(completed.values()))
        except Exception as exc:
            ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"endpoint": endpoint_key, "model": endpoint.model})
    finally:
        client.close()
    report = {"protocol": PROTOCOL, "status": "RECOVERY_COMPLETE" if len(completed) == 48 else "RECOVERY_FAILED_STOP", "pair_id": MISSING_ID, "completed_pairs": len(completed), "author_changed": False, "semantic_assignment_changed": False, "candidate_exact_copy_still_forbidden": True, "response_effect_or_judge_calls": 0, "private_paired_outcome_key_read": False}
    write_json(DIR / "authoring_v2_candidate_copy_recovery_report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
