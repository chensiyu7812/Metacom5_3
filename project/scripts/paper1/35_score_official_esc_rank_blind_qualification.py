#!/usr/bin/env python3
"""Score only the frozen 24-item blind qualification set with official ESC-RANK.

This is an evaluator-qualification runner, not a formal ESC-Eval runner.  It
refuses any input other than the pre-outcome frozen blind package and requires
the versioned official-parser runtime qualification to be READY first.
"""

from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import importlib.metadata
import json
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.esc_eval_official_parser import (  # noqa: E402
    official_parser_diagnostics,
    parse_official_ordinal,
)
from metacom_pm.esc_rank_runtime import (  # noqa: E402
    ESC_EVAL_COMMIT,
    ESC_RANK_REVISION,
    INTERNLM2_REVISION,
    repair_official_adapter_paths,
)
from metacom_pm.paper1.evaluator_qualification import assert_blind_payload  # noqa: E402
from metacom_pm.paper1.outcome_lock import (  # noqa: E402
    assert_pre_outcome_locked,
    load_public_only_config,
)


SCORE_PY_SHA256 = "1d775462adc7687d84ceb19d3648c3c917abf7ceed8b052b1fed8e4740f12724"
BLIND_INPUT_SHA256 = "3cc69f6aa0ef4a833146d19e7c9e7c2625338af7ddc4729546ca91266733f655"
MODEL_IDENTITY_SHA256 = "c2015762aea474e85ef4f4bbf6a13494639f34b54c896e610b6d9d511f73dd12"
OFFICIAL_PARSER_SEMANTICS = (
    "first label in label_order whose character is contained in raw response; invalid if none"
)
DIMENSIONS = (
    ("Fluency", "fluency", "fluecy"),
    ("Expression", "diversity", "diversity"),
    ("Empathy", "empathic", "empathy"),
    ("Information", "suggestion", "suggection effectiveness"),
    ("Humanoid", "human", "humanoid"),
    ("Skillful", "tech", "emotional knowledge"),
    ("Overall", "overall", "human preference"),
)


def sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def load_frozen_blind_rows(path: Path) -> list[dict[str, Any]]:
    if sha_file(path) != BLIND_INPUT_SHA256:
        raise RuntimeError("frozen 24-item blind qualification input hash drifted")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 24:
        raise RuntimeError("official qualification requires exactly 24 frozen blind items")
    assert_blind_payload(rows)
    ids: set[str] = set()
    for row in rows:
        if set(row) != {"blind_item_id", "dialogue", "protocol"}:
            raise RuntimeError("blind row schema drifted")
        if row["protocol"] != "pm-paper1-esc-evaluator-judge-blind-input-v1":
            raise RuntimeError("blind input protocol drifted")
        item_id = row["blind_item_id"]
        if not isinstance(item_id, str) or not item_id or item_id in ids:
            raise RuntimeError("blind item identity is invalid or duplicated")
        ids.add(item_id)
        if not isinstance(row["dialogue"], list) or not row["dialogue"]:
            raise RuntimeError("blind dialogue must be non-empty")
        if not all(isinstance(turn, str) and turn for turn in row["dialogue"]):
            raise RuntimeError("blind dialogue contains an invalid turn")
    return rows


def official_prompts(score_py: Path) -> list[str]:
    if sha_file(score_py) != SCORE_PY_SHA256:
        raise RuntimeError("official score.py hash drifted")
    tree = ast.parse(repair_official_adapter_paths(score_py.read_text(encoding="utf-8")))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "prompt_EN" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, list) and len(value) == 7 and all(isinstance(x, str) for x in value):
                return value
    raise RuntimeError("official seven English prompts were not found")


def validate_contract(
    *, manifest: dict[str, Any], runtime: dict[str, Any], esc_eval: Path, rank_path: Path,
    base_path: Path,
) -> None:
    official = manifest["official_identity"]
    expected = {
        "esc_eval_commit": ESC_EVAL_COMMIT,
        "score_py_sha256": SCORE_PY_SHA256,
        "esc_rank_revision": ESC_RANK_REVISION,
        "internlm2_revision": INTERNLM2_REVISION,
    }
    if any(official.get(key) != value for key, value in expected.items()):
        raise RuntimeError("resolved manifest official identity drifted")
    parser = manifest.get("official_parser", {})
    if parser.get("label_order") != ["0", "1", "2", "3", "4"]:
        raise RuntimeError("official parser label order drifted")
    if parser.get("semantics") != OFFICIAL_PARSER_SEMANTICS:
        raise RuntimeError("official parser semantics drifted")
    if runtime.get("status") != "READY" or runtime.get("formal_ESC_Eval") is not False:
        raise RuntimeError("official runtime qualification is absent, drifted, or not READY")
    if runtime.get("counts", {}).get("official_valid_parses") != 42:
        raise RuntimeError("runtime qualification did not preserve 42 official parses")
    if runtime.get("exact_raw_output_reproducibility") is not True:
        raise RuntimeError("runtime qualification raw outputs were not deterministic")
    if runtime.get("official_identity") != official:
        raise RuntimeError("runtime and manifest official identities differ")
    if git_head(esc_eval) != ESC_EVAL_COMMIT:
        raise RuntimeError("ESC-Eval checkout drifted")
    if rank_path.resolve().name != ESC_RANK_REVISION:
        raise RuntimeError("ESC-RANK snapshot drifted")
    if base_path.resolve().name != INTERNLM2_REVISION:
        raise RuntimeError("InternLM2 snapshot drifted")
    pins = dict(manifest["dependency_pins"])
    pins.update(manifest.get("auxiliary_runtime_pins", {}))
    for package, expected_version in pins.items():
        actual = importlib.metadata.version(package)
        if actual != expected_version:
            raise RuntimeError(
                f"dependency drift {package}: expected {expected_version}, got {actual}"
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", type=Path, required=True)
    parser.add_argument("--rank-path", type=Path, required=True)
    parser.add_argument("--base-path", type=Path, required=True)
    parser.add_argument("--blind-input", type=Path, required=True)
    parser.add_argument("--resolved-manifest", type=Path, required=True)
    parser.add_argument("--runtime-report", type=Path, required=True)
    parser.add_argument("--judge-rows-out", type=Path, required=True)
    parser.add_argument("--trace-out", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    args = parser.parse_args()

    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    if args.judge_rows_out.exists() or args.trace_out.exists():
        raise RuntimeError("refusing to overwrite an existing qualification artifact")
    rows = load_frozen_blind_rows(args.blind_input)
    manifest = json.loads(args.resolved_manifest.read_text(encoding="utf-8"))
    runtime = json.loads(args.runtime_report.read_text(encoding="utf-8"))
    validate_contract(
        manifest=manifest,
        runtime=runtime,
        esc_eval=args.esc_eval,
        rank_path=args.rank_path,
        base_path=args.base_path,
    )
    prompts = official_prompts(args.esc_eval / "score.py")

    import torch
    from peft import PeftMixedModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("qualification requires exactly one visible CUDA GPU")
    total_mib = int(torch.cuda.get_device_properties(0).total_memory // 1024**2)
    if total_mib < 24576:
        raise RuntimeError(f"qualification requires >=24576 MiB, found {total_mib}")
    torch.cuda.reset_peak_memory_stats()
    load_started = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.base_path), local_files_only=True, trust_remote_code=True
    )
    base = AutoModelForCausalLM.from_pretrained(
        str(args.base_path), local_files_only=True, trust_remote_code=True,
        torch_dtype=torch.float16, device_map={"": args.device},
    ).eval()
    model = PeftMixedModel.from_pretrained(
        base, str(args.rank_path / "fluency_en"), adapter_name="fluency"
    )
    for _paper_dimension, adapter, _phrase in DIMENSIONS[1:]:
        model.load_adapter(str(args.rank_path / f"{adapter}_en"), adapter_name=adapter)
    load_seconds = time.perf_counter() - load_started

    judge_rows: list[dict[str, Any]] = []
    traces: list[dict[str, Any]] = []
    for item_index, row in enumerate(rows, start=1):
        official_dialogue = "\n\n".join(row["dialogue"])
        official_dialogue = official_dialogue.replace("AI assistant", "**AI助手**").replace(
            "ESC-Role：", "**用户**"
        )
        item_started = time.perf_counter()
        scores: dict[str, int | None] = {}
        for index, (paper_dimension, adapter, phrase) in enumerate(DIMENSIONS):
            prompt = (
                prompts[index]
                + "Dialogue between user and AI assistant: \n"
                + official_dialogue.strip()
                + "\nBased on the rules, give your "
                + phrase
                + " score (The number only) to the Dialogue."
            )
            model.set_adapter(adapter)
            torch.cuda.synchronize()
            started = time.perf_counter()
            with torch.inference_mode():
                raw, _ = model.chat(
                    tokenizer, prompt, do_sample=False, temperature=0.0, history=[]
                )
            torch.cuda.synchronize()
            ordinal = parse_official_ordinal(raw)
            scores[paper_dimension] = ordinal
            traces.append(
                {
                    "blind_item_id": row["blind_item_id"],
                    "paper_dimension": paper_dimension,
                    "adapter": adapter,
                    "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                    "raw_output": raw,
                    "official_parsed_ordinal": ordinal,
                    "official_parse_valid": ordinal is not None,
                    **official_parser_diagnostics(raw),
                    "latency_seconds": time.perf_counter() - started,
                }
            )
        item_latency = time.perf_counter() - item_started
        parse_valid = all(value is not None for value in scores.values())
        judge_rows.append(
            {
                "blind_item_id": row["blind_item_id"],
                "candidate_id": "ESC_RANK",
                "cost_usd": 0.0,
                "latency_seconds": item_latency,
                "model_identity_sha256": MODEL_IDENTITY_SHA256,
                "parse_valid": parse_valid,
                "protocol": "pm-paper1-esc-evaluator-candidate-score-v1",
                "scores": scores if parse_valid else {name: None for name, _, _ in DIMENSIONS},
            }
        )
        print(f"qualified blind item {item_index}/24", flush=True)

    rendered_rows = "".join(
        json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in judge_rows
    )
    args.judge_rows_out.parent.mkdir(parents=True, exist_ok=True)
    args.trace_out.parent.mkdir(parents=True, exist_ok=True)
    args.judge_rows_out.write_text(rendered_rows, encoding="utf-8")
    trace_report = {
        "protocol": "pm-paper1-official-esc-rank-blind-qualification-trace-v1",
        "status": "READY" if all(row["parse_valid"] for row in judge_rows) else "BLOCKED",
        "scope": "frozen_24_item_zero_outcome_evaluator_qualification_only",
        "official_identity": manifest["official_identity"],
        "model_identity_sha256": MODEL_IDENTITY_SHA256,
        "repository_commit": git_head(PROJECT.parent),
        "runner_sha256": sha_file(Path(__file__).resolve()),
        "official_parser_module_sha256": sha_file(
            PROJECT / "src/metacom_pm/esc_eval_official_parser.py"
        ),
        "blind_input_sha256": sha_file(args.blind_input),
        "resolved_manifest_sha256": sha_file(args.resolved_manifest),
        "runtime_report_sha256": sha_file(args.runtime_report),
        "judge_rows_sha256": hashlib.sha256(rendered_rows.encode()).hexdigest(),
        "gpu": {
            "total_mib": total_mib,
            "load_seconds": load_seconds,
            "peak_allocated_mib": torch.cuda.max_memory_allocated() / 1024**2,
            "peak_reserved_mib": torch.cuda.max_memory_reserved() / 1024**2,
        },
        "counts": {
            "items": len(judge_rows),
            "dimension_calls": len(traces),
            "valid_items": sum(row["parse_valid"] for row in judge_rows),
            "valid_dimension_parses": sum(row["official_parse_valid"] for row in traces),
            "strict_diagnostic_valid_parses": sum(
                row["strict_full_string_valid"] for row in traces
            ),
            "multiple_official_label_hit_diagnostics": sum(
                row["multiple_official_label_hits"] for row in traces
            ),
        },
        "latency_seconds": {
            "mean_item": statistics.fmean(row["latency_seconds"] for row in judge_rows),
            "median_item": statistics.median(row["latency_seconds"] for row in judge_rows),
        },
        "cost_method": "local already-provisioned GPU; incremental API cost recorded as 0 USD",
        "traces": traces,
        "outcome_calls": 0,
        "formal_ESC_Eval": False,
        "PM_training_calls": 0,
    }
    args.trace_out.write_text(
        json.dumps(trace_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    del model, base, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    print(json.dumps({key: value for key, value in trace_report.items() if key != "traces"}, indent=2))
    return 0 if trace_report["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
