#!/usr/bin/env python3
"""Repair one provenance-only ID copy error and finish GPT Function review."""

from __future__ import annotations

import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
BASE_PATH = ROOT / "scripts/v1_5/237l_run_paper1_v3_ms_executor_function_proxy_reviews_v1_5.py"
spec = importlib.util.spec_from_file_location("function_proxy_v1_runner_gpt_id_repair", BASE_PATH)
if spec is None or spec.loader is None:
    raise RuntimeError("cannot load V1 Function proxy runner")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)

from metacom_pm.io import sha256_file, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_ms_executor_function_review import MSExecutorFunctionReview, validate_review  # noqa: E402


SOURCE_DIR = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_only_reviews_20260811"
REVIEWS = SOURCE_DIR / "reviews.jsonl"
REVIEWS_SHA256 = "e170810af6b3dc41621dfb083c28d80bc40b118c91f67f5a7cda780d1c49d484"
RAW = SOURCE_DIR / "raw_attempts_before_gold.jsonl"
RAW_SHA256 = "b729565df814929626e7fee2b64a78bbac38c1c9cd7b9013b84a2a19f62bb3c9"
PLAN = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_only_preflight_20260811/call_plan_private.jsonl"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_function_gpt_id_repair_continuation_20260811"


def bootstrap() -> None:
    if sha256_file(REVIEWS) != REVIEWS_SHA256 or sha256_file(RAW) != RAW_SHA256:
        raise RuntimeError("source GPT review artifacts drifted")
    accepted = runner.rows(REVIEWS)
    raw = runner.rows(RAW)[-1]
    if len(accepted) != 33 or raw["stage"] != "PUBLIC" or raw["parsed_before_gold"] is None:
        raise RuntimeError("unexpected GPT continuation surface")
    expected_id = raw["blind_item_id"]
    returned_id = raw["parsed_before_gold"]["blind_item_id"]
    if not (len(expected_id) == len(returned_id) + 2 and expected_id.startswith(returned_id)):
        raise RuntimeError("ID error is not the frozen two-character suffix omission")
    public = {row["blind_item_id"]: row for row in runner.rows(runner.PUBLIC)}
    calls = {row["logical_call_id"]: row for row in runner.rows(PLAN)}
    payload = dict(raw["parsed_before_gold"])
    payload["blind_item_id"] = expected_id
    repaired = validate_review(MSExecutorFunctionReview.model_validate(payload), public[expected_id])
    call = calls[raw["logical_call_id"]]
    repaired.update(
        {
            "protocol": "pm-v1.5-paper1-v3-ms-executor-function-proxy-review-v1",
            "reviewer_id": raw["reviewer_id"],
            "endpoint_key": call["endpoint_key"],
            "model": call["model"],
            "stage": raw["stage"],
            "request_hash": raw["request_hash"],
            "provenance_id_suffix_repaired": True,
        }
    )
    combined = [*accepted, repaired]
    OUT.mkdir(parents=True, exist_ok=True)
    target = OUT / "reviews.jsonl"
    if target.exists():
        if runner.rows(target) != combined:
            raise RuntimeError("GPT carry set drifted")
    else:
        write_jsonl(target, combined)
    write_json(
        OUT / "carry_forward_receipt.json",
        {
            "protocol": "pm-v1.5-paper1-v3-ms-function-gpt-id-repair-carry-v1",
            "accepted_reviews_sha256": REVIEWS_SHA256,
            "raw_source_sha256": RAW_SHA256,
            "reviews_carried": 33,
            "reviews_recovered_zero_api": 1,
            "repaired_field": "blind_item_id two-character suffix only",
            "label_or_evidence_changed": False,
            "remaining_public_calls": 10,
        },
    )


if __name__ == "__main__":
    bootstrap()
    runner.PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_executor_function_gpt_id_repair_execution_phase_v1.json"
    runner.CONFIG = ROOT / "configs/paper1_v3_ms_executor_function_gpt_id_repair_execution_v1.json"
    runner.PLAN = PLAN
    runner.OUT = OUT
    runner.STAGE = "paper1_v3_ms_executor_function_gpt_id_repair_continuation_v1"
    runner.CAP = 0.5
    runner.main()
