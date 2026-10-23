#!/usr/bin/env python3
"""Materialize two independently ordered, blinded 96-presentation sheets."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import (  # noqa: E402
    iter_jsonl,
    read_json,
    sha256_file,
    stable_hex,
    write_json,
)
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


PROTOCOL = "paper1-pairwise-teacher-human-sheet-v1"


def _args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base-pairs",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--presentations",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_presentation_plan_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--blind-key",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_blind_key_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--instrument",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_human_instrument_20260904_v1.json",
    )
    parser.add_argument(
        "--generation-result",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_local_generation_result_20260904_v1.json",
    )
    parser.add_argument(
        "--private-requests",
        type=Path,
        default=PROJECT
        / "outputs/paper1_pairwise_teacher/private_generator_requests_20260904_v1.jsonl",
    )
    parser.add_argument(
        "--response-cache",
        type=Path,
        default=PROJECT
        / "outputs/paper1_pairwise_teacher/local_generator_success_cache_v1",
    )
    parser.add_argument(
        "--private-out-dir",
        type=Path,
        default=PROJECT / "outputs/paper1_pairwise_teacher/human_sheets_v1",
    )
    parser.add_argument(
        "--authority-out",
        type=Path,
        default=PROJECT
        / "data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260904_v1.json",
    )
    return parser.parse_args()


def _dg_visible_prefix(off_request: dict[str, Any]) -> str:
    lines = []
    for message in off_request["messages"]:
        if message["role"] == "assistant":
            lines.append(f"supporter: {message['content']}")
        elif message["role"] == "user":
            lines.append(f"seeker: {message['content']}")
    if len(lines) != 2:
        raise RuntimeError("first-turn DG OFF request does not contain one visible exchange")
    return "\n".join(lines)


def main() -> int:
    args = _args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    instrument = read_json(args.instrument)
    generation = read_json(args.generation_result)
    if generation.get("status") != "PASS_142_LOCAL_RESPONSES_READY_FOR_BLINDED_SHEETS":
        raise RuntimeError("142 local Generator responses are not ready")
    base = {row["base_pair_id"]: row for row in iter_jsonl(args.base_pairs)}
    presentations = list(iter_jsonl(args.presentations))
    blind = {row["presentation_id"]: row for row in iter_jsonl(args.blind_key)}
    private_requests = {
        row["request_id"]: row for row in iter_jsonl(args.private_requests)
    }
    pair_map = {
        row["base_pair_id"]: row for row in generation["base_pair_response_map"]
    }
    if len(base) != 80 or len(presentations) != 96 or len(blind) != 96 or len(pair_map) != 80:
        raise RuntimeError("human-sheet denominators drifted")

    response_text: dict[str, str] = {}
    for request_id in private_requests:
        cached = read_json(args.response_cache / f"{request_id}.json")
        if cached["request_id"] != request_id:
            raise RuntimeError("local Generator response cache identity mismatch")
        response_text[request_id] = str(cached["accepted_text"])

    items: list[dict[str, Any]] = []
    for presentation in presentations:
        presentation_id = presentation["presentation_id"]
        key = blind[presentation_id]
        base_row = base[key["base_pair_id"]]
        responses = pair_map[key["base_pair_id"]]
        arm_a = key["A_arm"]
        arm_b = key["B_arm"]
        if {arm_a, arm_b} != {"ON", "OFF"}:
            raise RuntimeError("blind key does not map one ON and one OFF arm")
        if base_row["task"] == "DG":
            off_request_id = responses["OFF"]["request_id"]
            task_input = _dg_visible_prefix(private_requests[off_request_id]["request"])
        else:
            task_input = base_row["task_input"]
        items.append(
            {
                "presentation_id": presentation_id,
                "task": base_row["task"],
                "task_input": task_input,
                "reference_material": base_row["reference_material"],
                "response_A": response_text[responses[arm_a]["request_id"]],
                "response_B": response_text[responses[arm_b]["request_id"]],
                "verdict": None,
                "rationale": None,
            }
        )
    if len({item["presentation_id"] for item in items}) != 96:
        raise RuntimeError("human sheet presentation IDs are not unique")

    sheets = {}
    for rater_id in ("RATER_A", "RATER_B"):
        ordered = sorted(
            items,
            key=lambda item: stable_hex(
                "paper1-pairwise-teacher-human-sheet-order-v1",
                rater_id,
                item["presentation_id"],
                n=32,
            ),
        )
        sheet = {
            "protocol": PROTOCOL,
            "rater_id": rater_id,
            "status": "READY_FOR_INDEPENDENT_RATING",
            "instrument": instrument,
            "items": [
                {"item_number": index, **item}
                for index, item in enumerate(ordered, 1)
            ],
        }
        path = args.private_out_dir / f"paper1_pairwise_teacher_{rater_id.lower()}_sheet_v1.json"
        write_json(path, sheet)
        sheets[rater_id] = {
            "path": str(path.relative_to(PROJECT)),
            "sha256": sha256_file(path),
            "presentations": 96,
        }
    order_a = [item["presentation_id"] for item in read_json(PROJECT / sheets["RATER_A"]["path"])["items"]]
    order_b = [item["presentation_id"] for item in read_json(PROJECT / sheets["RATER_B"]["path"])["items"]]
    if set(order_a) != set(order_b) or order_a == order_b:
        raise RuntimeError("rater sheets must have the same items in independent orders")

    authority = {
        "protocol": "paper1-pairwise-teacher-human-sheet-manifest-v1",
        "date": "2026-09-04",
        "status": "ACTIVE_96_PRESENTATION_SHEETS_READY_RATINGS_PENDING",
        "source_sha256": {
            "base_pairs": sha256_file(args.base_pairs),
            "presentations": sha256_file(args.presentations),
            "blind_key": sha256_file(args.blind_key),
            "instrument": sha256_file(args.instrument),
            "local_generation_result": sha256_file(args.generation_result),
        },
        "sheets": sheets,
        "blinding": {
            "same_A_B_orientation": True,
            "independent_item_order": True,
            "on_off_hidden": True,
            "head_and_k_hidden": True,
            "base_pair_id_hidden": True,
            "reverse_duplicate_flag_hidden": True,
            "resource_bundle_hidden": True,
        },
        "primary_judgements_after_completion": 192,
        "paid_api_calls": 0,
        "formal_outcome_calls": 0,
        "pm_training_runs": 0,
        "locks": {
            name: config[name]["status"]
            for name in (
                "RQ1_RS_CALIBRATION_OUTCOME_LOCK",
                "RQ2_MEMORY_CALIBRATION_OUTCOME_LOCK",
                "RQ1_CONFIRMATORY_OUTCOME_LOCK",
                "RQ2_CONFIRMATORY_OUTCOME_LOCK",
            )
        },
    }
    write_json(args.authority_out, authority)
    print({
        "status": authority["status"],
        "sheets": sheets,
        "formal_outcome_calls": 0,
        "paid_api_calls": 0,
    })
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
