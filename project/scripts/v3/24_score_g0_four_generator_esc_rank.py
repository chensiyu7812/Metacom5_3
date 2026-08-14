#!/usr/bin/env python3
"""Score the frozen four-generator G0 dialogues with pinned ESC-RANK adapters."""

from __future__ import annotations

import argparse
import gc
import hashlib
import importlib.util
import json
import subprocess
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
AUTHORITY = PROJECT_ROOT / "data" / "v3_authority"
PREFLIGHT = AUTHORITY / "g0_four_generator_esc_rank_preflight_v1.json"
BASE_SCORER_PATH = Path(__file__).with_name("13_score_g0_esc_rank.py")
spec = importlib.util.spec_from_file_location("v3_base_esc_rank_scorer", BASE_SCORER_PATH)
assert spec is not None and spec.loader is not None
base_scorer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base_scorer)


def _counts(dialogues: list[dict[str, Any]]) -> dict[str, int]:
    return {
        candidate_id: sum(row["candidate_id"] == candidate_id for row in dialogues)
        for candidate_id in sorted({row["candidate_id"] for row in dialogues})
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--rank-path", required=True, type=Path)
    parser.add_argument("--base-path", required=True, type=Path)
    parser.add_argument("--dialogue-ledger", required=True, type=Path)
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--device", default="cuda:1")
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()

    preflight = json.loads(PREFLIGHT.read_text(encoding="utf-8"))
    score_identity = preflight["score_run_identity"]
    source_identity = preflight["source_generation_identity"]
    if args.approved_identity != score_identity:
        raise RuntimeError("approved identity does not match the frozen ESC-RANK preflight")
    if hashlib.sha256(args.dialogue_ledger.read_bytes()).hexdigest() != preflight["source_ledger_sha256"]:
        raise RuntimeError("source dialogue ledger hash drifted")
    events = base_scorer._read_jsonl(args.dialogue_ledger)
    if any(row.get("run_identity") != source_identity for row in events):
        raise RuntimeError("source dialogue ledger contains a different generation identity")
    dialogues = base_scorer._dialogues(events)
    if len(dialogues) != preflight["complete_dialogues"] or _counts(dialogues) != preflight["candidate_dialogue_counts"]:
        raise RuntimeError("complete-dialogue inventory drifted")

    git_head = subprocess.run(
        ["git", "-C", str(args.esc_eval), "rev-parse", "HEAD"], check=True, capture_output=True, text=True
    ).stdout.strip()
    measurement = preflight["measurement"]
    if git_head != measurement["esc_eval_commit"]:
        raise RuntimeError("ESC-Eval checkout is not at the frozen commit")
    if args.rank_path.resolve().name != measurement["esc_rank_revision"]:
        raise RuntimeError("ESC-RANK path is not at the frozen revision")
    if args.base_path.resolve().name != measurement["internlm2_revision"]:
        raise RuntimeError("InternLM2 path is not at the frozen revision")
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
    model = PeftMixedModel.from_pretrained(base, str(args.rank_path / "fluency_en"), adapter_name="fluency")
    for _, adapter, _ in base_scorer.DIMENSIONS[1:]:
        model.load_adapter(str(args.rank_path / f"{adapter}_en"), adapter_name=adapter)

    args.out.mkdir(parents=True, exist_ok=True)
    ledger_path = args.out / "private_score_ledger.jsonl"
    existing = base_scorer._read_jsonl(ledger_path)
    indexed = {(row["screen_id"], row["candidate_id"], row["adapter"]): row for row in existing}
    if any(row.get("run_identity") != score_identity for row in existing):
        raise RuntimeError("existing score ledger contains a different scoring identity")
    for dialogue in dialogues:
        official_dialogue = "\n\n".join(dialogue["dialogue"])
        official_dialogue = official_dialogue.replace("AI assistant", "**AI助手**").replace("ESC-Role：", "**用户**")
        for index, (paper_name, adapter, dimension_phrase) in enumerate(base_scorer.DIMENSIONS):
            key = (dialogue["screen_id"], dialogue["candidate_id"], adapter)
            if key in indexed:
                continue
            prompt = (
                prompts[index] + "Dialogue between user and AI assistant: \n" + official_dialogue.strip()
                + "\nBased on the rules, give your " + dimension_phrase
                + " score (The number only) to the Dialogue."
            )
            model.set_adapter(adapter)
            with torch.inference_mode():
                raw, _ = model.chat(tokenizer, prompt, do_sample=False, temperature=0.0, history=[])
            record = {
                "protocol": "metacom-v3-g0-four-generator-esc-rank-score-v1",
                "run_identity": score_identity,
                "source_generation_identity": source_identity,
                "screen_id": dialogue["screen_id"],
                "card_key": dialogue["card_key"],
                "candidate_id": dialogue["candidate_id"],
                "paper_dimension": paper_name,
                "adapter": adapter,
                "prompt_sha256": hashlib.sha256(prompt.encode("utf-8")).hexdigest(),
                "raw_output": raw,
                "ordinal": parse_strict_ordinal(raw),
            }
            existing.append(record)
            indexed[key] = record
            base_scorer._write_jsonl(ledger_path, existing)

    by_candidate: dict[str, dict[str, Any]] = {}
    for candidate_id in sorted(preflight["candidate_dialogue_counts"]):
        rows = [row for row in existing if row["candidate_id"] == candidate_id]
        by_candidate[candidate_id] = {
            "dialogues": len({row["screen_id"] for row in rows}),
            "dimension_calls": len(rows),
            "valid_ordinals": sum(row["ordinal"] is not None for row in rows),
            "invalid_ordinals": sum(row["ordinal"] is None for row in rows),
            "dimension_distributions": {
                adapter: {str(value): sum(row["adapter"] == adapter and row["ordinal"] == value for row in rows) for value in range(5)}
                for _, adapter, _ in base_scorer.DIMENSIONS
            },
        }
    summary = {
        "protocol": "metacom-v3-g0-four-generator-esc-rank-summary-v1",
        "run_identity": score_identity,
        "source_generation_identity": source_identity,
        "primary_parser": "full-string ^[0-4]$ or INVALID",
        "candidates": by_candidate,
        "formal_generator_qualification": False,
        "selection_rule": "Report seven dimensions and invalid rate separately; no sole average or absolute pass cutoff.",
        "nemotron_boundary": "Descriptive 21-complete-dialogue subset only; reliability hard failure remains in force.",
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    del model, base, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
