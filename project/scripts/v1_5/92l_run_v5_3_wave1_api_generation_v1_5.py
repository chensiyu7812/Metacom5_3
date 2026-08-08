#!/usr/bin/env python3
"""Run the separately authorized, staged Wave-1 catalog generation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.api import (  # noqa: E402
    RetryableProviderError, make_client, parse_audited_json_surface,
)
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import (  # noqa: E402
    append_jsonl, canonical_json, read_json, sha256_file, sha256_text, utc_now, write_json,
)
from metacom_pm.v1_5_v5_3_wave1_generation import (  # noqa: E402
    assemble_user, chunk_prompt, chunk_ranges, preference_assignments,
    validate_world, world_prompt,
)


CONFIG = ROOT / "configs/experiment.yaml"
CONTRACT = ROOT / "data/pm_v1_5_contracts/v5_3_complete_training_data_generation_v2.json"
ASSIGNMENTS = ROOT / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v1.json"
EXISTING_USERS = (
    ROOT / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users"
)
VALIDATOR = ROOT / "scripts/v1_5/82l_validate_formal_longitudinal_user_v1_5.py"
PREFLIGHT = ROOT / "outputs/pm_v1_5_v5_3_wave1_api_generation_preflight_v1/execution_preflight.json"
DEFAULT_OUT = ROOT / "outputs/pm_v1_5_v5_3_wave1_api_generation_v1"


def _cost(usage: dict[str, int], author: str, preflight: dict[str, Any]) -> float:
    pricing = preflight["pricing_usd_per_mtok"][author]
    return (
        int(usage.get("prompt_tokens") or 0) / 1_000_000 * float(pricing["input"])
        + int(usage.get("completion_tokens") or 0) / 1_000_000 * float(pricing["output"])
    )


def _fresh(path: Path) -> None:
    if path.exists() and any(path.iterdir()):
        raise RuntimeError(f"output directory is not fresh: {path}")
    path.mkdir(parents=True, exist_ok=True)


def _ordered_assignments(rows: list[dict[str, Any]], canaries: list[str]) -> list[dict[str, Any]]:
    by_id = {row["user_id"]: row for row in rows}
    if len(by_id) != len(rows) or any(user_id not in by_id for user_id in canaries):
        raise RuntimeError("invalid or duplicate Wave-1 assignments")
    return [by_id[user_id] for user_id in canaries] + [
        row for row in rows if row["user_id"] not in canaries
    ]


def _call(
    *, client: Any, messages: list[dict[str, str]], max_tokens: int,
    temperature: float, user_id: str, stage: str, author: str,
    attempts_path: Path, usage_total: dict[str, int], cost_state: dict[str, float],
    authorized_ceiling: float, preflight: dict[str, Any],
) -> dict[str, Any]:
    try:
        result, _ = client.chat(
            messages,
            response_schema=None,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=None,
            retries=1,
        )
    except Exception as exc:
        failed_usage = dict(exc.usage or {}) if isinstance(exc, RetryableProviderError) else {}
        for key in usage_total:
            usage_total[key] += int(failed_usage.get(key) or 0)
        failed_cost = _cost(failed_usage, author, preflight)
        cost_state["usd"] += failed_cost
        append_jsonl(
            attempts_path,
            {
                "user_id": user_id,
                "content_author": author,
                "stage": stage,
                "status": "provider_error",
                "error": f"{type(exc).__name__}: {exc}",
                "usage": failed_usage,
                "proxy_cost_usd": round(failed_cost, 9),
            },
        )
        if cost_state["usd"] > authorized_ceiling:
            raise RuntimeError("authorized Wave-1 cost ceiling exceeded") from exc
        raise
    for key in usage_total:
        usage_total[key] += int(result.usage.get(key) or 0)
    call_cost = _cost(result.usage, author, preflight)
    cost_state["usd"] += call_cost
    attempt = {
        "user_id": user_id,
        "content_author": author,
        "stage": stage,
        "request_hash": result.request_hash,
        "messages_sha256": sha256_text(canonical_json(messages)),
        "raw_provider_text": result.text,
        "usage": result.usage,
        "provider_finish_reason": result.provider_finish_reason,
        "normalized_finish_reason": result.normalized_finish_reason,
        "latency_ms": result.latency_ms,
        "proxy_cost_usd": round(call_cost, 9),
    }
    try:
        parsed, audit = parse_audited_json_surface(result.text)
        if not isinstance(parsed, dict):
            raise ValueError("provider output must be one JSON object")
    except Exception as exc:
        attempt["parse_status"] = "failed"
        attempt["parse_error"] = f"{type(exc).__name__}: {exc}"
        append_jsonl(attempts_path, attempt)
        raise
    attempt["parse_status"] = "passed"
    attempt["json_surface_audit"] = audit
    append_jsonl(attempts_path, attempt)
    if cost_state["usd"] > authorized_ceiling:
        raise RuntimeError("authorized Wave-1 cost ceiling exceeded")
    return parsed


def _validate_user(user_path: Path, validation_dir: Path) -> dict[str, Any]:
    command = [
        sys.executable,
        str(VALIDATOR),
        "--input", str(user_path),
        "--contract", str(CONTRACT),
        "--out-dir", str(validation_dir),
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        env={**__import__("os").environ, "PYTHONPATH": str(ROOT / "src")},
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            "validator process failed: " + (completed.stderr or completed.stdout)[-2000:]
        )
    report = read_json(validation_dir / "report.json")
    if report["status"] != "MACHINE_PASS_BATCH_AND_SEMANTIC_REVIEW_PENDING":
        raise RuntimeError(f"user did not machine-validate: {report['status']}")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--run-identity", required=True)
    parser.add_argument("--maximum-usd", required=True, type=float)
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    preflight = read_json(PREFLIGHT)
    if str(preflight.get("status", "")).startswith("SUPERSEDED"):
        raise RuntimeError("full-batch Wave-1 API identity was superseded before authorization")
    if args.run_identity != preflight["run_identity"]:
        raise RuntimeError("run identity differs from frozen Wave-1 preflight")
    if abs(args.maximum_usd - float(preflight["requested_authorization_ceiling_usd"])) > 1e-12:
        raise RuntimeError("cost authorization differs from frozen ceiling")
    if not args.run:
        print(json.dumps({"status": "DRY_RUN", "api_calls": 0, "run_identity": args.run_identity}))
        return

    _fresh(args.out_dir)
    write_json(
        args.out_dir / "approval_receipt.json",
        {
            "protocol": "pm-v1.5-v5.3-wave1-api-generation-approval-v1",
            "run_identity": args.run_identity,
            "maximum_usd": args.maximum_usd,
            "recorded_at_utc": utc_now(),
        },
    )
    rows = read_json(ASSIGNMENTS)["rows"]
    order = _ordered_assignments(
        rows, preflight["execution_order"]["canary_users_first"]
    )
    preference_map = preference_assignments(rows, EXISTING_USERS)
    contract = read_json(CONTRACT)
    targets = contract["catalog_targets"]
    contract_excerpt = {
        "relationships_per_user_schedule": targets["relationships_per_user_schedule"],
        "events_per_user_schedule": targets["events_per_user_schedule"],
    }
    config = load_config(CONFIG)
    endpoints = {
        "chatgpt_pro": endpoint_from_config(config, "final_judge"),
        "claude": endpoint_from_config(config, "final_judge_claude"),
    }
    for author, endpoint in endpoints.items():
        frozen = preflight["endpoints"][author]
        if endpoint.model != frozen["model"] or endpoint.base_url != frozen["base_url"]:
            raise RuntimeError(f"endpoint drift for {author}")

    attempts_path = args.out_dir / "physical_attempt_ledger.jsonl"
    outcomes_path = args.out_dir / "user_outcomes.jsonl"
    generated_dir = args.out_dir / "generated_users"
    generated_dir.mkdir()
    usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
    cost_state = {"usd": 0.0}
    clients: dict[str, Any] = {}
    completed_users = 0
    terminal_error: dict[str, Any] | None = None
    started = utc_now()
    try:
        for ordinal, assignment in enumerate(order, 1):
            user_id = assignment["user_id"]
            author = assignment["content_author"]
            if author not in clients:
                clients[author] = make_client(endpoints[author])
            client = clients[author]
            try:
                messages = world_prompt(
                    assignment, preference_map[user_id], contract_excerpt
                )
                world = _call(
                    client=client,
                    messages=messages,
                    max_tokens=6000,
                    temperature=float(preflight["sampling"]["temperature"]),
                    user_id=user_id,
                    stage="world_chronology_plan",
                    author=author,
                    attempts_path=attempts_path,
                    usage_total=usage,
                    cost_state=cost_state,
                    authorized_ceiling=args.maximum_usd,
                    preflight=preflight,
                )
                validate_world(
                    world, assignment, preference_map[user_id], contract_excerpt
                )
                write_json(args.out_dir / f"{user_id}_world.json", world)

                chunks: list[dict[str, Any]] = []
                max_outputs = [8000, 8000, 12000]
                for chunk_index, ((start, end), max_tokens) in enumerate(
                    zip(chunk_ranges(int(assignment["session_count"])), max_outputs, strict=True),
                    1,
                ):
                    messages = chunk_prompt(assignment, world, start, end)
                    chunk = _call(
                        client=client,
                        messages=messages,
                        max_tokens=max_tokens,
                        temperature=float(preflight["sampling"]["temperature"]),
                        user_id=user_id,
                        stage=f"session_chunk_{chunk_index}",
                        author=author,
                        attempts_path=attempts_path,
                        usage_total=usage,
                        cost_state=cost_state,
                        authorized_ceiling=args.maximum_usd,
                        preflight=preflight,
                    )
                    chunks.append(chunk)
                    write_json(args.out_dir / f"{user_id}_chunk_{chunk_index}.json", chunk)

                user = assemble_user(assignment, world, chunks)
                user_path = generated_dir / f"{user_id}.json"
                write_json(user_path, user)
                validation_dir = args.out_dir / "validation" / user_id
                report = _validate_user(user_path, validation_dir)
                completed_users += 1
                append_jsonl(
                    outcomes_path,
                    {
                        "ordinal": ordinal,
                        "user_id": user_id,
                        "content_author": author,
                        "status": "MACHINE_PASS_BATCH_AND_SEMANTIC_REVIEW_PENDING",
                        "user_sha256": sha256_file(user_path),
                        "validation_report_sha256": sha256_file(validation_dir / "report.json"),
                        "hard_issue_count": report["users"][0]["hard_issue_count"],
                    },
                )
            except Exception as exc:
                terminal_error = {
                    "ordinal": ordinal,
                    "user_id": user_id,
                    "stage": "generation_or_machine_validation",
                    "error": f"{type(exc).__name__}: {exc}",
                }
                append_jsonl(
                    outcomes_path,
                    {"ordinal": ordinal, "user_id": user_id, "status": "STOPPED", **terminal_error},
                )
                break
            # The first two rows are the cross-provider canaries by construction.
            if ordinal == 2 and completed_users != 2:
                raise RuntimeError("both provider canaries must validate before scale-out")
    finally:
        for client in clients.values():
            client.close()

    status = "COMPLETE_AWAITING_BATCH_AND_SEMANTIC_REVIEW" if completed_users == 13 else "STOPPED_FAIL_CLOSED"
    manifest = {
        "protocol": "pm-v1.5-v5.3-wave1-api-generation-execution-v1",
        "status": status,
        "run_identity": args.run_identity,
        "started_at_utc": started,
        "completed_at_utc": utc_now(),
        "users_planned": 13,
        "users_completed": completed_users,
        "logical_calls_completed": sum(1 for _ in open(attempts_path, encoding="utf-8")) if attempts_path.exists() else 0,
        "usage": usage,
        "proxy_cost_usd": round(cost_state["usd"], 9),
        "authorized_ceiling_usd": args.maximum_usd,
        "terminal_error": terminal_error,
        "preflight_sha256": sha256_file(PREFLIGHT),
        "assignments_sha256": sha256_file(ASSIGNMENTS),
        "contract_sha256": sha256_file(CONTRACT),
        "api_calls": sum(1 for _ in open(attempts_path, encoding="utf-8")) if attempts_path.exists() else 0,
        "training_label_or_external_exam_text_read": False,
    }
    if attempts_path.exists():
        manifest["physical_attempt_ledger_sha256"] = sha256_file(attempts_path)
    if outcomes_path.exists():
        manifest["user_outcomes_sha256"] = sha256_file(outcomes_path)
    write_json(args.out_dir / "run_manifest.json", manifest)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    if status != "COMPLETE_AWAITING_BATCH_AND_SEMANTIC_REVIEW":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
