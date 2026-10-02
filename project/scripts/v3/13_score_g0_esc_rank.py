#!/usr/bin/env python3
"""Score completed G0 ESC-Eval dialogues with the pinned official adapters.

The published prompts and dialogue transformation are reused byte-for-byte
from the pinned ESC-Eval score.py. The two path defects are repaired at load
time, and only a full-string ordinal 0..4 is accepted.
"""

from __future__ import annotations

import argparse
import ast
import gc
import hashlib
import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
AUTHORITY_DIR = PROJECT_ROOT / "data" / "v3_authority"
PREFLIGHT_PATH = AUTHORITY_DIR / "g0_generator_bakeoff_preflight_v1.json"
ROLE_REVISION = "2e2a4733d2e71da242f348aad165fe171acd5df7"
RANK_REVISION = "450bf2eb5376c79e371aaf432925810243de1527"
BASE_REVISION = "c2ba64483dc50b3f8eb2d8271c4b9877a79ed2e2"
ESC_EVAL_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
SCORE_PY_SHA256 = "1d775462adc7687d84ceb19d3648c3c917abf7ceed8b052b1fed8e4740f12724"
DIMENSIONS = [
    ("Fluency", "fluency", "fluecy"),
    ("Expression", "diversity", "diversity"),
    ("Empathy", "empathic", "empathy"),
    ("Information", "suggestion", "suggection effectiveness"),
    ("Humanoid", "human", "humanoid"),
    ("Skill", "tech", "emotional knowledge"),
    ("Overall", "overall", "human preference"),
]


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")


def _official_prompt_en(score_py: Path) -> list[str]:
    if _sha_file(score_py) != SCORE_PY_SHA256:
        raise RuntimeError("official score.py hash drifted")
    tree = ast.parse(score_py.read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "prompt_EN" for target in node.targets):
            prompts = ast.literal_eval(node.value)
            if isinstance(prompts, list) and len(prompts) == 7 and all(isinstance(row, str) for row in prompts):
                return prompts
    raise RuntimeError("official prompt_EN was not found as a seven-string literal")


def _dialogues(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = defaultdict(list)
    for row in events:
        if row.get("event") == "supporter_succeeded":
            grouped[(row["screen_id"], row["card_key"], row["candidate_id"])].append(row)
    complete: list[dict[str, Any]] = []
    opening = "Hello, I'm your personal assistant. You can confide in me about any worries or concerns you may have!"
    for (screen_id, card_key, candidate_id), rows in sorted(grouped.items()):
        rows.sort(key=lambda row: row["turn"])
        if [row["turn"] for row in rows] != [1, 2, 3, 4, 5]:
            continue
        dialogue = ["AI assistant：" + opening]
        for row in rows:
            dialogue.extend(["ESC-Role：" + row["seeker_text"], "AI assistant：" + row["supporter_text"]])
        complete.append(
            {
                "screen_id": screen_id,
                "card_key": card_key,
                "candidate_id": candidate_id,
                "dialogue": dialogue,
            }
        )
    return complete


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--esc-eval", required=True, type=Path)
    parser.add_argument("--rank-path", required=True, type=Path)
    parser.add_argument("--base-path", required=True, type=Path)
    parser.add_argument("--dialogue-ledger", required=True, type=Path)
    parser.add_argument("--approved-identity", required=True)
    parser.add_argument("--device", default="cuda:0")
    parser.add_argument(
        "--out",
        type=Path,
        default=PROJECT_ROOT / "outputs" / "v3_g0_esc_rank_scores_20260813",
    )
    args = parser.parse_args()
    preflight = json.loads(PREFLIGHT_PATH.read_text(encoding="utf-8"))
    if args.approved_identity != preflight["run_identity"]:
        raise RuntimeError("approved identity does not match the frozen G0 preflight")
    git_head = subprocess.run(
        ["git", "-C", str(args.esc_eval), "rev-parse", "HEAD"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()
    if git_head != ESC_EVAL_COMMIT:
        raise RuntimeError("ESC-Eval checkout is not at the frozen commit")
    if args.rank_path.resolve().name != RANK_REVISION or args.base_path.resolve().name != BASE_REVISION:
        raise RuntimeError("ESC-RANK or InternLM2 path is not at its frozen revision")
    prompts = _official_prompt_en(args.esc_eval / "score.py")
    dialogues = _dialogues(_read_jsonl(args.dialogue_ledger))
    if not dialogues:
        raise RuntimeError("no complete five-turn dialogue is available to score")

    import torch
    from peft import PeftMixedModel
    from transformers import AutoModelForCausalLM, AutoTokenizer
    from metacom_pm.esc_rank_runtime import parse_strict_ordinal

    tokenizer = AutoTokenizer.from_pretrained(str(args.base_path), local_files_only=True, trust_remote_code=True)
    base = AutoModelForCausalLM.from_pretrained(
        str(args.base_path),
        local_files_only=True,
        trust_remote_code=True,
        torch_dtype=torch.float16,
        device_map={"": args.device},
    ).eval()
    model = PeftMixedModel.from_pretrained(
        base,
        str(args.rank_path / "fluency_en"),
        adapter_name="fluency",
    )
    for _, adapter, _ in DIMENSIONS[1:]:
        model.load_adapter(str(args.rank_path / f"{adapter}_en"), adapter_name=adapter)

    args.out.mkdir(parents=True, exist_ok=True)
    ledger_path = args.out / "private_score_ledger.jsonl"
    existing = _read_jsonl(ledger_path)
    indexed = {(row["screen_id"], row["candidate_id"], row["adapter"]): row for row in existing}
    for dialogue in dialogues:
        official_dialogue = "\n\n".join(dialogue["dialogue"])
        official_dialogue = official_dialogue.replace("AI assistant", "**AI助手**").replace("ESC-Role：", "**用户**")
        for index, (paper_name, adapter, dimension_phrase) in enumerate(DIMENSIONS):
            key = (dialogue["screen_id"], dialogue["candidate_id"], adapter)
            if key in indexed:
                continue
            prompt = (
                prompts[index]
                + "Dialogue between user and AI assistant: \n"
                + official_dialogue.strip()
                + "\nBased on the rules, give your "
                + dimension_phrase
                + " score (The number only) to the Dialogue."
            )
            model.set_adapter(adapter)
            with torch.inference_mode():
                raw, _ = model.chat(tokenizer, prompt, do_sample=False, temperature=0.0, history=[])
            record = {
                "protocol": "metacom-v3-g0-esc-rank-score-v1",
                "run_identity": preflight["run_identity"],
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
            _write_jsonl(ledger_path, existing)

    by_candidate: dict[str, dict[str, Any]] = {}
    for candidate_id in sorted({row["candidate_id"] for row in existing}):
        rows = [row for row in existing if row["candidate_id"] == candidate_id]
        by_candidate[candidate_id] = {
            "dialogues": len({row["screen_id"] for row in rows}),
            "dimension_calls": len(rows),
            "valid_ordinals": sum(row["ordinal"] is not None for row in rows),
            "invalid_ordinals": sum(row["ordinal"] is None for row in rows),
            "dimension_distributions": {
                adapter: {str(value): sum(row["adapter"] == adapter and row["ordinal"] == value for row in rows) for value in range(5)}
                for _, adapter, _ in DIMENSIONS
            },
        }
    summary = {
        "protocol": "metacom-v3-g0-esc-rank-summary-v1",
        "run_identity": preflight["run_identity"],
        "official_prompt_sha256": SCORE_PY_SHA256,
        "strict_parser": "full-string ^[0-4]$ or INVALID",
        "candidates": by_candidate,
        "formal_generator_qualification": False,
        "selection_rule": "Report all dimensions and invalid rate separately; do not select by a sole average.",
    }
    (args.out / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    del model, base, tokenizer
    gc.collect()
    torch.cuda.empty_cache()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
