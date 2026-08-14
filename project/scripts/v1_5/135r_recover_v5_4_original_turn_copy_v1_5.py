#!/usr/bin/env python3
"""One-shot paraphrase recovery for two V2 original-current-turn copies."""

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

spec = importlib.util.spec_from_file_location("v54_author_v2", ROOT / "scripts/v1_5/134l_run_v5_4_source_prefix_locked_authoring_v2_v1_5.py")
runner = importlib.util.module_from_spec(spec); assert spec and spec.loader; spec.loader.exec_module(runner)

PROTOCOL = "pm-v1.5-v5.4-source-prefix-locked-authoring-v2.1-original-turn-paraphrase-recovery"
DIR = runner.DIR
TARGETS = {"v54pair_acb4e40db7a6da82bacc", "v54pair_0909edb41240ff250bd8"}


def main() -> None:
    packet = {str(row["pair_id"]): row for row in runner._jsonl(runner.PACKET)}; completed = {str(row["pair_id"]): row for row in runner._jsonl(runner.COMPLETED)}
    audit = json.loads((DIR / "authoring_v2_machine_audit_report.json").read_text())
    if set(audit["original_turn_copy_ids"]) != TARGETS or len(completed) != 48: raise SystemExit("documented original-copy target set changed")
    configs = json.loads(runner.ENDPOINTS.read_text()); clients = {}
    ledger = PersistentAttemptLedger(DIR / "authoring_v2_original_turn_copy_recovery_ledger.jsonl", stage="v5_4_original_turn_copy_recovery", expected_calls={"recovery_" + key: 1 for key in TARGETS}, maximum_total_attempts=2)
    try:
        for index, pair_id in enumerate(sorted(TARGETS), start=1):
            item = packet[pair_id]; endpoint_key = str(item["assigned_author_endpoint"]); endpoint = runner._endpoint(configs["candidates"][endpoint_key])
            if endpoint_key not in clients: clients[endpoint_key] = make_client(endpoint)
            original = str(item["original_current_user_turn_for_world_and_tone_only"])
            messages = runner._messages(item) + [{"role": "user", "content": "Paraphrase-only recovery: preserve both private A/B meanings and the minimal-pair frame, but neither output may be normalized-exactly equal to this original public current turn: " + json.dumps(original)}]
            reservation = ledger.reserve("recovery_" + pair_id, record_ids={"pair_id": pair_id, "author": endpoint_key}, prompt_sha256=sha256_text(canonical_json(messages))); response = None
            try:
                response, parsed = clients[endpoint_key].chat(messages, temperature=0.0, max_tokens=runner.MAX_OUTPUT_TOKENS, seed=20260810 + index, response_schema=runner.UserTurnPair, retries=1)
                if parsed is None: raise ValueError("structured recovery pair missing")
                row = runner._validate(parsed, item, endpoint_key)
                if runner._normalize(row["variant_A_current_user_turn"]) == runner._normalize(original) or runner._normalize(row["variant_B_current_user_turn"]) == runner._normalize(original): raise ValueError("original current turn still copied")
                row.update({"execution_protocol": PROTOCOL, "original_turn_copy_recovery": True}); ledger.finish(reservation, succeeded=True, request_hash=response.request_hash, usage=response.usage, error=None, result=row, metadata={"model": endpoint.model}); completed[pair_id] = row; write_jsonl(runner.COMPLETED, list(completed.values()))
            except Exception as exc:
                ledger.finish(reservation, succeeded=False, request_hash=response.request_hash if response else None, usage=response.usage if response else None, error=f"{type(exc).__name__}: {exc}", metadata={"model": endpoint.model})
    finally:
        for client in clients.values(): client.close()
    success = all(completed[key].get("execution_protocol") == PROTOCOL for key in TARGETS)
    report = {"protocol": PROTOCOL, "status": "RECOVERY_COMPLETE" if success else "RECOVERY_INCOMPLETE_STOP", "target_pair_ids": sorted(TARGETS), "semantic_assignment_changed": False, "authors_changed": False, "response_effect_or_judge_calls": 0, "private_paired_outcome_key_read": False}
    write_json(DIR / "authoring_v2_original_turn_copy_recovery_report.json", report); print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()
