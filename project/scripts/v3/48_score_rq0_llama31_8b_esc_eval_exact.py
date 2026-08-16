#!/usr/bin/env python3
"""Score the exact-format Llama run with the pinned ESC-Eval score.py path."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import subprocess
from collections import Counter
from pathlib import Path
from statistics import mean


ROOT = Path(__file__).resolve().parents[2]
sys_path = ROOT / "src"
import sys
sys.path.insert(0, str(sys_path))
BASE_SCORER_PATH = Path(__file__).with_name("13_score_g0_esc_rank.py")
DERIVATIVE_PATH = Path(__file__).with_name("14_derive_g0_esc_rank_anchored_scores.py")


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


base_scorer = _load(BASE_SCORER_PATH, "rq0_exact_base_scorer")
derivative = _load(DERIVATIVE_PATH, "rq0_exact_label_audit")


def _legacy_official_parse(raw: str) -> int:
    for label in ("0", "1", "2", "3", "4"):
        if label in raw:
            return int(label)
    return -1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--rank-path", required=True, type=Path)
    parser.add_argument("--base-path", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--preflight", required=True, type=Path)
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    preflight = json.loads(args.preflight.read_text(encoding="utf-8"))
    if args.approved_identity != preflight["score_identity"]:
        raise RuntimeError("score identity mismatch")
    if hashlib.sha256(args.result.read_bytes()).hexdigest() != preflight["result_sha256"]:
        raise RuntimeError("official-format result drifted")
    result = json.loads(args.result.read_text(encoding="utf-8"))
    if len(result) != 331:
        raise RuntimeError("exact scoring requires all 331 official dialogues")
    head = subprocess.run(
        ["git", "-C", str(args.esc_eval), "rev-parse", "HEAD"],
        check=True, capture_output=True, text=True,
    ).stdout.strip()
    measurement = preflight["measurement"]
    if head != measurement["esc_eval_commit"]:
        raise RuntimeError("ESC-Eval checkout drifted")
    if args.rank_path.resolve().name != measurement["esc_rank_revision"]:
        raise RuntimeError("ESC-RANK revision drifted")
    if args.base_path.resolve().name != measurement["internlm2_revision"]:
        raise RuntimeError("InternLM2 revision drifted")
    prompts = base_scorer._official_prompt_en(args.esc_eval / "score.py")

    import torch
    from peft import PeftMixedModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from metacom_pm.esc_rank_runtime import parse_strict_ordinal

    tokenizer = AutoTokenizer.from_pretrained(str(args.base_path), local_files_only=True, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        str(args.base_path), local_files_only=True, trust_remote_code=True,
        torch_dtype=torch.float16, device_map={"": args.device},
    ).eval()
    model = PeftMixedModel.from_pretrained(
        base, str(args.rank_path / "fluency_en"), adapter_name="fluency"
    )
    for _, adapter, _ in base_scorer.DIMENSIONS[1:]:
        model.load_adapter(str(args.rank_path / f"{adapter}_en"), adapter_name=adapter)

    args.out.mkdir(parents=True, exist_ok=True)
    ledger_path = args.out / "private_score_ledger.jsonl"
    rows = base_scorer._read_jsonl(ledger_path)
    if any(row.get("score_identity") != preflight["score_identity"] for row in rows):
        raise RuntimeError("existing score ledger contains another identity")
    indexed = {(row["dialogue_index"], row["adapter"]): row for row in rows}
    for dialogue_index in sorted(result, key=int):
        dialogue = "\n\n".join(result[dialogue_index])
        dialogue = dialogue.replace("AI assistant", "**AI助手**").replace("ESC-Role：", "**用户**")
        for dimension_index, (paper_name, adapter, dimension_phrase) in enumerate(base_scorer.DIMENSIONS):
            key = (dialogue_index, adapter)
            if key in indexed:
                continue
            prompt = (
                prompts[dimension_index]
                + "Dialogue between user and AI assistant: \n"
                + dialogue.strip()
                + "\nBased on the rules, give your "
                + dimension_phrase
                + " score (The number only) to the Dialogue."
            )
            model.set_adapter(adapter)
            with torch.inference_mode():
                raw, _ = model.chat(
                    tokenizer, prompt, do_sample=False, temperature=0.0, history=[]
                )
            record = {
                "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-score-v1",
                "score_identity": preflight["score_identity"],
                "source_generation_identity": preflight["source_generation_identity"],
                "dialogue_index": dialogue_index,
                "paper_dimension": paper_name,
                "adapter": adapter,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "raw_output": raw,
                "official_legacy_ordinal": _legacy_official_parse(raw),
                "exact_label_ordinal": derivative.parse_anchored_ordinal(raw, adapter),
                "strict_ordinal": parse_strict_ordinal(raw),
            }
            rows.append(record)
            indexed[key] = record
            base_scorer._write_jsonl(ledger_path, rows)

    dimensions = {}
    parser_disagreements = 0
    for paper_name, adapter, _ in base_scorer.DIMENSIONS:
        subset = [row for row in rows if row["adapter"] == adapter]
        legacy = [row["official_legacy_ordinal"] for row in subset]
        exact = [row["exact_label_ordinal"] for row in subset if row["exact_label_ordinal"] is not None]
        parser_disagreements += sum(
            row["exact_label_ordinal"] is not None
            and row["official_legacy_ordinal"] != row["exact_label_ordinal"]
            for row in subset
        )
        dimensions[paper_name] = {
            "adapter": adapter,
            "dialogues": len(subset),
            "official_legacy_mean_itt": mean(legacy),
            "official_legacy_distribution": dict(sorted(Counter(legacy).items())),
            "exact_label_valid": len(exact),
            "exact_label_mean_valid": mean(exact) if exact else None,
            "strict_single_digit_valid": sum(row["strict_ordinal"] is not None for row in subset),
        }
    summary = {
        "protocol": "metacom-v3-rq0-llama31-8b-esc-eval-exact-score-summary-v1",
        "status": (
            "COMPLETE_OFFICIAL_PROFILE_PARSER_AUDIT_PASS"
            if len(rows) == 2317 and parser_disagreements == 0
            else "COMPLETE_PROFILE_PARSER_AUDIT_BLOCKED"
        ),
        "source_generation_identity": preflight["source_generation_identity"],
        "score_identity": preflight["score_identity"],
        "dialogues": 331,
        "dimension_calls": len(rows),
        "dimensions": dimensions,
        "official_parser": "first substring in ordered labels 0,1,2,3,4; -1 if none",
        "parser_disagreements_where_exact_label_valid": parser_disagreements,
        "official_pass_line": None,
        "score_ledger_sha256": hashlib.sha256(ledger_path.read_bytes()).hexdigest(),
    }
    (args.out / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    del model, base, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
