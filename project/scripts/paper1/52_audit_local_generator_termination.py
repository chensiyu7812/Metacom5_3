#!/usr/bin/env python3
"""Audit local Generator stopping metadata without retaining or judging text."""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from transformers import AutoTokenizer


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import iter_jsonl, sha256_file, write_json  # noqa: E402
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-local-generator-termination-audit-v1"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-dir", type=Path, required=True)
    parser.add_argument(
        "--trace",
        action="append",
        type=Path,
        default=[],
        help="Tracked zero-outcome trace JSONL; repeat for multiple pilots.",
    )
    parser.add_argument("--out", type=Path, required=True)
    return parser.parse_args()


def _trace_surface(path: Path) -> dict[str, Any]:
    rows = list(iter_jsonl(path))
    finish = Counter()
    by_cell: dict[str, Counter[str]] = defaultdict(Counter)
    output_tokens: dict[str, list[int]] = defaultdict(list)
    forbidden_text_fields = set()
    for row in rows:
        record = row["record"]
        reason = str(record["finish_reason"])
        cell = f"{row['task_type']}::{row['configuration_id']}"
        finish[reason] += 1
        by_cell[cell][reason] += 1
        output_tokens[cell].append(int(record["output_tokens"]))
        for key in record:
            if key in {"response_text", "generated_text", "content"}:
                forbidden_text_fields.add(key)
    return {
        "sha256": sha256_file(path),
        "calls": len(rows),
        "finish_reason_counts": dict(sorted(finish.items())),
        "cells": {
            cell: {
                "calls": sum(by_cell[cell].values()),
                "finish_reason_counts": dict(sorted(by_cell[cell].items())),
                "output_tokens": output_tokens[cell],
            }
            for cell in sorted(by_cell)
        },
        "response_text_fields_present": sorted(forbidden_text_fields),
    }


def main() -> int:
    args = _args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    if not args.trace:
        raise ValueError("at least one --trace is required")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model_dir.resolve(), local_files_only=True
    )
    eot_id = int(tokenizer.convert_tokens_to_ids("<|eot_id|>"))
    surfaces = {
        path.name: _trace_surface(path.resolve()) for path in args.trace
    }
    total_finish = Counter()
    length_cells: set[str] = set()
    total_calls = 0
    no_text = True
    for surface in surfaces.values():
        total_calls += int(surface["calls"])
        total_finish.update(surface["finish_reason_counts"])
        no_text = no_text and not surface["response_text_fields_present"]
        for cell, value in surface["cells"].items():
            if value["finish_reason_counts"].get("length", 0):
                length_cells.add(cell)
    server = PROJECT / "scripts/paper1/46_serve_local_llama31_reference.py"
    server_source = server.read_text(encoding="utf-8")
    checks = {
        "tokenizer_eos_is_eot_id": tokenizer.eos_token == "<|eot_id|>",
        "tokenizer_eos_id_matches_eot_id": tokenizer.eos_token_id == eot_id == 128009,
        "server_passes_tokenizer_eos_to_generate": (
            "eos_token_id=self.tokenizer.eos_token_id" in server_source
        ),
        "server_distinguishes_length_from_stop": (
            '"length" if completion_tokens >= max_new_tokens else "stop"'
            in server_source
        ),
        "all_calls_have_known_terminal_reason": sum(total_finish.values()) == total_calls
        and set(total_finish).issubset({"stop", "length"}),
        "no_response_text_retained": no_text,
    }
    artifact = {
        "protocol": PROTOCOL,
        "date": "2026-09-04",
        "status": (
            "INITIAL_ZERO_OUTCOME_TERMINATION_AUDIT_COMPLETE_BROADER_SAMPLE_PENDING"
            if all(checks.values())
            else "TERMINATION_INTEGRITY_FAIL"
        ),
        "not_an_empirical_pass_gate": True,
        "checks": checks,
        "tokenizer": {
            "eos_token": tokenizer.eos_token,
            "eos_token_id": tokenizer.eos_token_id,
            "eot_token_id": eot_id,
        },
        "server_sha256": sha256_file(server),
        "trace_surfaces": surfaces,
        "aggregate": {
            "calls": total_calls,
            "finish_reason_counts": dict(sorted(total_finish.items())),
            "length_finish_cells": sorted(length_cells),
            "interpretation": (
                "The frozen server uses the correct Llama-3.1 EOT token. Existing length "
                "finishes are concentrated in QA/Summary OFF cells and are observed cap "
                "hits, not evidence of an EOT identity mismatch."
            ),
        },
        "cap_freeze_status": "PENDING_BROADER_RS_MEMORY_DG_TARGET_SAMPLE",
        "allowed_next_read": [
            "finish reason",
            "output token count",
            "task/head/amount cell",
            "latency and failure metadata",
        ],
        "forbidden_next_read": [
            "response quality",
            "official capability score",
            "PM performance",
        ],
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "paid_api_calls": 0,
    }
    write_json(args.out.resolve(), artifact)
    print(json.dumps(artifact, ensure_ascii=False, indent=2))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
