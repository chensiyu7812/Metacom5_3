#!/usr/bin/env python3
"""Pinned ESC-RANK runtime qualification harness for a >=24 GiB GPU.

This harness must only receive public baseline/overlap qualification dialogues.
It refuses PM arms, k labels, calibration/confirmatory role cards, or outcome
fields.  Building the harness does not authorize executing it.
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
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402

SCORE_PY_SHA256 = "1d775462adc7687d84ceb19d3648c3c917abf7ceed8b052b1fed8e4740f12724"
DIMENSIONS = (
    ("Fluency", "fluency", "fluecy"),
    ("Expression", "diversity", "diversity"),
    ("Empathy", "empathic", "empathy"),
    ("Information", "suggestion", "suggection effectiveness"),
    ("Humanoid", "human", "humanoid"),
    ("Skillful", "tech", "emotional knowledge"),
    ("Overall", "overall", "human preference"),
)
FORBIDDEN_KEYS = {
    "pm_identity", "arm", "on_off", "k", "token_budget", "ours", "baseline",
    "outcome", "score", "winner", "confirmatory_role_card", "calibration_role_card",
}
OFFICIAL_PARSER_SEMANTICS = (
    "first label in label_order whose character is contained in raw response; invalid if none"
)


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _tree_sha(path: Path) -> str:
    rows = []
    for item in sorted(candidate for candidate in path.rglob("*") if candidate.is_file()):
        rows.append(f"{item.relative_to(path).as_posix()}\t{_sha_file(item)}")
    return hashlib.sha256("\n".join(rows).encode()).hexdigest()


def _git_head(path: Path) -> str:
    return subprocess.run(
        ["git", "-C", str(path), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


def _prompts(score_py: Path) -> list[str]:
    if _sha_file(score_py) != SCORE_PY_SHA256:
        raise RuntimeError("official score.py hash drifted")
    source = score_py.read_text(encoding="utf-8")
    repaired = repair_official_adapter_paths(source)
    tree = ast.parse(repaired)
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "prompt_EN" for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, list) and len(value) == 7 and all(isinstance(x, str) for x in value):
                return value
    raise RuntimeError("official seven English prompts were not found")


def _gpu_total_mib(cuda: Any | None = None) -> int:
    if cuda is None:
        import torch

        cuda = torch.cuda
    if not cuda.is_available():
        raise RuntimeError("qualification harness requires an available CUDA GPU")
    if cuda.device_count() != 1:
        raise RuntimeError("qualification harness requires exactly one visible GPU")
    return int(cuda.get_device_properties(0).total_memory // 1024**2)


def _load_dialogues(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) < 3:
        raise RuntimeError("runtime qualification requires at least three blind dialogues")
    for row in rows:
        if not isinstance(row.get("blind_item_id"), str) or not row["blind_item_id"]:
            raise RuntimeError("qualification dialogue must have a blind_item_id")
        if set(row) & FORBIDDEN_KEYS:
            raise RuntimeError(f"qualification dialogue exposes forbidden keys: {set(row) & FORBIDDEN_KEYS}")
        if row.get("source_role") not in {
            "public_baseline",
            "public_overlap_only",
            "controlled_semantics_preserving_probe",
        }:
            raise RuntimeError("qualification dialogue source_role is not isolated")
        if not isinstance(row.get("dialogue"), list) or not row["dialogue"]:
            raise RuntimeError("qualification dialogue must be a non-empty string list")
        if not all(isinstance(value, str) and value for value in row["dialogue"]):
            raise RuntimeError("qualification dialogue contains an invalid turn")
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", type=Path, required=True)
    parser.add_argument("--rank-path", type=Path, required=True)
    parser.add_argument("--base-path", type=Path, required=True)
    parser.add_argument("--qualification-dialogues", type=Path, required=True)
    parser.add_argument("--patch-manifest", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--repeats", type=int, default=2)
    args = parser.parse_args()
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    if args.repeats < 2:
        raise RuntimeError("determinism qualification requires at least two repeats")
    total_mib = _gpu_total_mib()
    if total_mib < 24576:
        raise RuntimeError(f"ESC-RANK qualification requires >=24576 MiB, found {total_mib}")

    manifest = json.loads(args.patch_manifest.read_text(encoding="utf-8"))
    parser_contract = manifest.get("official_parser", {})
    if parser_contract.get("label_order") != ["0", "1", "2", "3", "4"]:
        raise RuntimeError("patch manifest official parser label order drifted")
    if parser_contract.get("semantics") != OFFICIAL_PARSER_SEMANTICS:
        raise RuntimeError("patch manifest official parser semantics drifted")
    if parser_contract.get("strict_full_string_role") != "supplemental_diagnostic_only":
        raise RuntimeError("strict parser must remain supplemental only")
    if manifest["official_identity"]["esc_eval_commit"] != ESC_EVAL_COMMIT:
        raise RuntimeError("patch manifest ESC-Eval identity drifted")
    if manifest["official_identity"]["score_py_sha256"] != SCORE_PY_SHA256:
        raise RuntimeError("patch manifest score.py identity drifted")
    if _git_head(args.esc_eval) != ESC_EVAL_COMMIT:
        raise RuntimeError("ESC-Eval checkout drifted")
    if args.rank_path.resolve().name != ESC_RANK_REVISION:
        raise RuntimeError("ESC-RANK snapshot directory is not the pinned revision")
    if args.base_path.resolve().name != INTERNLM2_REVISION:
        raise RuntimeError("InternLM2 snapshot directory is not the pinned revision")
    if _tree_sha(args.rank_path) != manifest["required_runtime_inventory"]["esc_rank_tree_sha256"]:
        raise RuntimeError("ESC-RANK adapter tree hash mismatch")
    if _tree_sha(args.base_path) != manifest["required_runtime_inventory"]["internlm2_tree_sha256"]:
        raise RuntimeError("InternLM2 tree hash mismatch")
    dependency_pins = dict(manifest["dependency_pins"])
    dependency_pins.update(manifest.get("auxiliary_runtime_pins", {}))
    for package, version in dependency_pins.items():
        actual = importlib.metadata.version(package)
        if actual != version:
            raise RuntimeError(f"dependency drift {package}: expected {version}, got {actual}")
    prompts = _prompts(args.esc_eval / "score.py")
    dialogues = _load_dialogues(args.qualification_dialogues)

    import torch
    from peft import PeftMixedModel
    from transformers import AutoModelForCausalLM, AutoTokenizer

    torch.cuda.reset_peak_memory_stats()
    cold_start = time.perf_counter()
    tokenizer = AutoTokenizer.from_pretrained(
        str(args.base_path), local_files_only=True, trust_remote_code=True
    )
    base = AutoModelForCausalLM.from_pretrained(
        str(args.base_path),
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map={"": args.device},
    ).eval()
    model = PeftMixedModel.from_pretrained(
        base, str(args.rank_path / "fluency_en"), adapter_name="fluency"
    )
    for _paper_name, adapter, _phrase in DIMENSIONS[1:]:
        model.load_adapter(str(args.rank_path / f"{adapter}_en"), adapter_name=adapter)
    cold_load_seconds = time.perf_counter() - cold_start
    cold_peak_allocated = torch.cuda.max_memory_allocated()
    cold_peak_reserved = torch.cuda.max_memory_reserved()

    records = []
    for row in dialogues:
        official_dialogue = "\n\n".join(row["dialogue"])
        official_dialogue = official_dialogue.replace("AI assistant", "**AI助手**").replace(
            "ESC-Role：", "**用户**"
        )
        for repeat in range(args.repeats):
            for index, (paper_name, adapter, phrase) in enumerate(DIMENSIONS):
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
                official_ordinal = parse_official_ordinal(raw)
                diagnostics = official_parser_diagnostics(raw)
                records.append(
                    {
                        "qualification_item_id": row["blind_item_id"],
                        "repeat": repeat,
                        "paper_dimension": paper_name,
                        "adapter": adapter,
                        "prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
                        "raw_output": raw,
                        "parsed_ordinal": official_ordinal,
                        "official_parsed_ordinal": official_ordinal,
                        "official_parse_valid": official_ordinal is not None,
                        **diagnostics,
                        "latency_seconds": time.perf_counter() - started,
                    }
                )

    vectors: dict[tuple[str, int], tuple[int | None, ...]] = {}
    for row in dialogues:
        item_id = row["blind_item_id"]
        for repeat in range(args.repeats):
            vector = tuple(
                next(
                    record["parsed_ordinal"]
                    for record in records
                    if record["qualification_item_id"] == item_id
                    and record["repeat"] == repeat
                    and record["paper_dimension"] == paper_name
                )
                for paper_name, _adapter, _phrase in DIMENSIONS
            )
            vectors[(item_id, repeat)] = vector
    official_vector_deterministic = all(
        len({vectors[(row["blind_item_id"], repeat)] for repeat in range(args.repeats)}) == 1
        for row in dialogues
    )
    raw_output_deterministic = all(
        len(
            {
                record["raw_output"]
                for record in records
                if record["qualification_item_id"] == row["blind_item_id"]
                and record["paper_dimension"] == paper_name
            }
        )
        == 1
        for row in dialogues
        for paper_name, _adapter, _phrase in DIMENSIONS
    )
    official_parse_complete = all(record["official_parse_valid"] for record in records)
    latencies = [record["latency_seconds"] for record in records]
    result = {
        "protocol": "pm-paper1-esc-rank-runtime-qualification-v2",
        "status": (
            "READY"
            if official_parse_complete
            and official_vector_deterministic
            and raw_output_deterministic
            else "BLOCKED"
        ),
        "official_identity": manifest["official_identity"],
        "runtime_code_identity": {
            "repository_commit": _git_head(PROJECT.parent),
            "harness_sha256": _sha_file(Path(__file__).resolve()),
            "esc_rank_runtime_module_sha256": _sha_file(
                PROJECT / "src/metacom_pm/esc_rank_runtime.py"
            ),
            "official_parser_module_sha256": _sha_file(
                PROJECT / "src/metacom_pm/esc_eval_official_parser.py"
            ),
        },
        "parser_binding": {
            "primary": "exact pinned ESC-Eval score.py label_list contains semantics",
            "label_order": ["0", "1", "2", "3", "4"],
            "invalid_local_sentinel": None,
            "strict_full_string_parser_role": "supplemental diagnostic only",
            "multiple_label_hit_role": "supplemental diagnostic only; official first-label semantics preserved",
        },
        "patch_manifest_sha256": _sha_file(args.patch_manifest),
        "qualification_dialogues_sha256": _sha_file(args.qualification_dialogues),
        "gpu": {
            "total_mib": total_mib,
            "cold_load_seconds": cold_load_seconds,
            "peak_allocated_mib": cold_peak_allocated / 1024**2,
            "peak_reserved_mib": cold_peak_reserved / 1024**2,
        },
        "counts": {
            "dialogues": len(dialogues),
            "repeats": args.repeats,
            "dimension_passes": len(records),
            "valid_parses": sum(record["official_parse_valid"] for record in records),
            "official_valid_parses": sum(record["official_parse_valid"] for record in records),
            "strict_diagnostic_valid_parses": sum(
                record["strict_full_string_valid"] for record in records
            ),
            "multiple_official_label_hit_diagnostics": sum(
                record["multiple_official_label_hits"] for record in records
            ),
        },
        "latency_seconds": {
            "mean_dimension": statistics.fmean(latencies),
            "median_dimension": statistics.median(latencies),
            "mean_seven_dimension_vector": statistics.fmean(latencies) * 7,
        },
        "exact_parsed_vector_reproducibility": official_vector_deterministic,
        "exact_official_vector_reproducibility": official_vector_deterministic,
        "exact_raw_output_reproducibility": raw_output_deterministic,
        "records": records,
        "outcome_calls": 0,
        "formal_ESC_Eval": False,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    del model, base, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    print(json.dumps({key: value for key, value in result.items() if key != "records"}, indent=2))
    return 0 if result["status"] == "READY" else 1


if __name__ == "__main__":
    raise SystemExit(main())
