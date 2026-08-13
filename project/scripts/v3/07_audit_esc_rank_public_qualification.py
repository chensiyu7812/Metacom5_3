#!/usr/bin/env python3
"""Audit whether the public ESC-RANK artifacts can support a local pass line.

This is a zero-inference audit. It inspects pinned Git/Hugging Face trees and
emits no role-card, dialogue, prompt, or human-label text.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any


ESC_EVAL_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
ESC_RANK_REVISION = "450bf2eb5376c79e371aaf432925810243de1527"
ESC_ROLE_REVISION = "2e2a4733d2e71da242f348aad165fe171acd5df7"
INTERNLM2_REVISION_OBSERVED_20260813 = "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2"

DIMENSIONS = [
    "fluency",
    "expression",
    "empathy",
    "information",
    "skill",
    "humanoid",
    "overall",
]

# Table 4 in ACL Anthology 2024.emnlp-main.883. Values are EN/ZH.
PUBLISHED_ESC_RANK_TABLE4 = {
    "hard_accuracy_percent": {
        "fluency": [88.45, 81.66],
        "expression": [65.72, 68.39],
        "empathy": [69.70, 77.02],
        "information": [75.10, 77.02],
        "skill": [79.72, 68.61],
        "humanoid": [57.51, 70.77],
        "overall": [57.89, 55.45],
        "average": [70.53, 71.27],
    },
    "within_one_point_accuracy_percent": {
        "fluency": [99.87, 99.24],
        "expression": [99.49, 99.67],
        "empathy": [99.10, 98.71],
        "information": [98.97, 99.46],
        "skill": [96.79, 99.57],
        "humanoid": [98.84, 98.17],
        "overall": [99.49, 99.35],
        "average": [98.93, 99.17],
    },
}


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree(repo: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in _git(repo, "ls-tree", "-rl", "HEAD").splitlines():
        prefix, path = line.split("\t", 1)
        mode, object_type, object_id, size = prefix.split()
        rows.append(
            {
                "mode": mode,
                "object_type": object_type,
                "object_id": object_id,
                "git_blob_bytes": int(size),
                "path": path,
            }
        )
    return rows


def _lfs_size(repo: Path, path: str) -> int | None:
    content = _git(repo, "show", f"HEAD:{path}")
    match = re.search(r"^size (\d+)$", content, flags=re.MULTILINE)
    return int(match.group(1)) if match else None


def _json_shape(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return {"json_type": "array", "records": len(payload)}
    if isinstance(payload, dict):
        return {"json_type": "object", "records": len(payload)}
    return {"json_type": type(payload).__name__, "records": None}


def audit(esc_eval: Path, esc_rank: Path, esc_role: Path) -> dict[str, Any]:
    observed = {
        "esc_eval": _git(esc_eval, "rev-parse", "HEAD"),
        "esc_rank": _git(esc_rank, "rev-parse", "HEAD"),
        "esc_role": _git(esc_role, "rev-parse", "HEAD"),
    }
    expected = {
        "esc_eval": ESC_EVAL_COMMIT,
        "esc_rank": ESC_RANK_REVISION,
        "esc_role": ESC_ROLE_REVISION,
    }
    if observed != expected:
        raise ValueError(f"unexpected public revisions: {observed}")

    score_path = esc_eval / "score.py"
    score_code = score_path.read_text(encoding="utf-8")
    rank_tree = _tree(esc_rank)
    role_tree = _tree(esc_role)
    primary_adapter_paths = [
        row["path"]
        for row in rank_tree
        if re.fullmatch(r"[^/]+/adapter_model\.safetensors", row["path"])
    ]
    all_adapter_paths = [
        row["path"] for row in rank_tree if row["path"].endswith("adapter_model.safetensors")
    ]
    primary_adapter_sizes = [_lfs_size(esc_rank, path) for path in primary_adapter_paths]
    role_weight_paths = [
        row["path"] for row in role_tree if re.fullmatch(r"model-\d+-of-\d+\.safetensors", row["path"])
    ]
    role_weight_sizes = [_lfs_size(esc_role, path) for path in role_weight_paths]

    public_eval_json = [
        "data/test_en.json",
        "data/test_zh.json",
        "result/2024-06-24/Qwen_7B_en.json",
        "result/2024-06-24/Qwen_7B_zh.json",
        "result/2024-06-24/llama3_en.json",
        "result/2024-06-24/llama3_zh.json",
        "score/Qwen_7B_en.json",
        "score/Qwen_7B_zh.json",
        "score/llama3_en.json",
        "score/llama3_zh.json",
    ]
    public_shapes = {
        path: _json_shape(esc_eval / path)
        for path in public_eval_json
        if (esc_eval / path).is_file()
    }
    rank_names = {row["path"] for row in rank_tree}
    result_files = sorted(path for path in rank_names if path.endswith("all_results.json"))
    result_keys: set[str] = set()
    for path in result_files:
        payload = json.loads(_git(esc_rank, "show", f"HEAD:{path}"))
        result_keys.update(payload)

    return {
        "protocol": "metacom-v3-esc-rank-public-qualification-audit-v1",
        "date": "2026-08-13",
        "status": "PUBLIC_SCORER_REPLAYABLE_ONLY_AFTER_REPAIR_HUMAN_CALIBRATION_NOT_INDEPENDENTLY_REPRODUCIBLE",
        "contains_role_card_dialogue_prompt_or_label_text": False,
        "api_calls": 0,
        "model_weights_downloaded": 0,
        "model_inference_calls": 0,
        "sources": {
            "paper": {
                "identity": "ACL Anthology 2024.emnlp-main.883",
                "reported_dialogues_approx": 8500,
                "reported_manual_dimension_scores": 59654,
                "dimensions": DIMENSIONS,
                "annotation_process": "one initial score followed by secondary review; not two retained independent labels",
                "annotators": 14,
                "split": "random 7:1:2 train/validation/test",
                "raw_split_row_identities_public": False,
                "inter_reviewer_agreement_reported": False,
                "published_scorer_table": PUBLISHED_ESC_RANK_TABLE4,
                "accuracy_soft_definition": "prediction within one ordinal point of the accepted score",
            },
            "ESC-Eval": {
                "commit": observed["esc_eval"],
                "score_py_sha256": _sha256(score_path),
                "public_example_shapes": public_shapes,
                "public_human_label_rows": 0,
                "public_train_validation_test_identity_manifest_present": False,
            },
            "ESC-RANK": {
                "hub_id": "haidequanbu/ESC-RANK",
                "revision": observed["esc_rank"],
                "license_claim": "apache-2.0 model-card metadata",
                "primary_language_dimension_adapters": len(primary_adapter_paths),
                "primary_adapter_lfs_bytes": sum(size or 0 for size in primary_adapter_sizes),
                "all_adapter_weight_files_including_checkpoint": len(all_adapter_paths),
                "training_result_files": len(result_files),
                "training_result_keys": sorted(result_keys),
                "validation_or_test_predictions_present": False,
                "validation_or_test_human_labels_present": False,
                "adapter_base_revision_pinned": False,
            },
            "ESC-Role": {
                "hub_id": "haidequanbu/ESC-Role",
                "revision": observed["esc_role"],
                "license_claim": "apache-2.0 model-card metadata",
                "weight_shards": len(role_weight_paths),
                "weight_lfs_bytes": sum(size or 0 for size in role_weight_sizes),
            },
            "InternLM2_base": {
                "hub_id": "internlm/internlm2-chat-7b",
                "official_code_uses_floating_identifier": True,
                "local_wrapper_revision_to_pin": INTERNLM2_REVISION_OBSERVED_20260813,
            },
        },
        "static_execution_findings": [
            {
                "severity": "BLOCKING_FOR_UNMODIFIED_REPLAY",
                "finding": "first fluency adapter paths use ./ESC-RANK1 while the published adapter tree is ./ESC-RANK",
                "present": "./ESC-RANK1/fluency" in score_code and "./ESC-RANK1/fluency_en" in score_code,
            },
            {
                "severity": "BLOCKING_FOR_EXACT_REPRODUCTION",
                "finding": "InternLM2 base model revision is not pinned by official code or adapter metadata",
                "present": 'from_pretrained("internlm/internlm2-chat-7b"' in score_code,
            },
            {
                "severity": "MEASUREMENT_DEFECT",
                "finding": "official parser accepts the first occurrence of any digit 0..4 anywhere in free-form output",
                "present": 'if(label in response)' in score_code,
            },
            {
                "severity": "CONSTRUCT_WARNING",
                "finding": "the Information rubric rewards recommendation count and can conflict with low-burden support",
                "present": "There are more than 5 suggestions" in score_code,
            },
            {
                "severity": "TEXT_TRANSFORM_WARNING",
                "finding": "the scorer rewrites the English AI-assistant role marker to a Chinese role marker",
                "present": '.replace("AI assistant","**AI助手**")' in score_code,
            },
        ],
        "qualification_decision": {
            "official_paper_construct_anchor": "QUALIFIED_WITH_STATED_BOUNDARIES",
            "official_655_card_exam_identity": "QUALIFIED",
            "official_scorer_as_descriptive_secondary_metric": "ELIGIBLE_AFTER_LOCAL_PATH_REVISION_AND_STRICT_PARSER_REPAIR",
            "official_scorer_as_absolute_pass_fail_instrument": "UNQUALIFIED_NO_PUBLIC_ROW_LEVEL_HUMAN_CALIBRATION",
            "published_model_table_as_reference_distribution": "DESCRIPTIVE_ONLY_DIFFERENT_MODEL_RUNTIME_AND_UNPUBLISHED_ROW_IDENTITIES",
            "required_local_parser": "accept only a full-string ordinal matching ^[0-4]$; otherwise INVALID",
            "required_reporting": [
                "all seven dimensions separately",
                "hard ordinal score distribution",
                "invalid/completion rate",
                "low-burden guardrail separately",
                "no sole Average-based verdict",
            ],
        },
        "p0_methodological_resolution": {
            "decision": "Do not search indefinitely for unavailable public labels and do not invent a calibrated ESC-RANK cutoff.",
            "next_phase_use": "Run repaired ESC-RANK as a recognized descriptive benchmark; use same-stack paired reference, ESC-Judge order-swap sensitivity, mechanical reliability, executor realization, and a separately frozen human anchor for decisions.",
            "does_not_authorize": ["weight download", "inference", "judge calls", "fine-tuning"],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--esc-rank", required=True, type=Path)
    parser.add_argument("--esc-role", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    result = audit(args.esc_eval, args.esc_rank, args.esc_role)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(rendered, encoding="utf-8")
    print(
        json.dumps(
            {
                "status": result["status"],
                "public_human_label_rows": result["sources"]["ESC-Eval"]["public_human_label_rows"],
                "primary_adapters": result["sources"]["ESC-RANK"]["primary_language_dimension_adapters"],
                "api_calls": result["api_calls"],
                "output_sha256": hashlib.sha256(rendered.encode("utf-8")).hexdigest(),
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
