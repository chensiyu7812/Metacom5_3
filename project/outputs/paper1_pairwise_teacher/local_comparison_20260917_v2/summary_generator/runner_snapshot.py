#!/usr/bin/env python3
"""Resumable, local-only judge development and Summary natural-end diagnostic.

Uses EOS rather than a task output-token ceiling. Context exhaustion, timeout,
and exact-cycle interruption are distinct incomplete outcomes. All raw outputs
stay in the ignored outputs directory. Never constructs formal PM labels.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, utc_now
from metacom_pm.paper1.evaluation.local_teacher import (
    natural_finish_reason, parse_local_verdict, repeated_tail,
)

AUTHORITY = PROJECT / "data/paper1_authority/paper1_pragmatic_teacher_development_20260917_v1.json"
CANDIDATES = {
    "selene_mini_8b": ("AtlaAI/Selene-1-Mini-Llama-3.1-8B", "427792f1c3e2073cb7da216924fd884b1ba496e0"),
    "compassjudger2_7b": ("opencompass/CompassJudger-2-7B-Instruct", "f913ec1569c282f02530028fedc1ce9832024ebf"),
    "qwen35_9b": ("Qwen/Qwen3.5-9B", "c202236235762e1c871ad0ccb60c8ee5ba337b9a"),
    "summary_generator": ("meta/llama-3.1-8b-instruct", "d10aef7999a2b5ba950ab3974312feeedbfe0b77"),
}
OLD_FORMAT_NOTE = "\n\nFormatting requirement: return only the JSON object. The rationale must contain between 1 and 600 characters."


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def requests(candidate):
    root = PROJECT / "outputs/paper1_pairwise_teacher"
    if candidate == "summary_generator":
        source = root / "private_generator_requests_20260904_v1.jsonl"
        rows = [json.loads(line) for line in source.read_text().splitlines()]
        result = [{"presentation_id": r["request_id"], "task": r["task"], "arm": r["arm"],
                   "messages": r["request"]["messages"], "old_request_sha256": r["request_sha256"],
                   "base_pair_ids": r["base_pair_ids"]} for r in rows if r["task"] == "Summary"]
        assert len(result) == 26
        return result, source
    source = root / "local_comparison_proposal_20260917_v1/selene_mini_8b_requests.jsonl"
    rows = [json.loads(line) for line in source.read_text().splitlines()]
    result = []
    for r in rows:
        messages = r["body"]["messages"]
        assert len(messages) == 1 and messages[0]["content"].endswith(OLD_FORMAT_NOTE)
        prompt = messages[0]["content"][:-len(OLD_FORMAT_NOTE)]
        result.append({"presentation_id": r["presentation_id"], "task": r["task"],
                       "messages": [{"role": "user", "content": prompt}]})
    assert len(result) == 160 and len({r["presentation_id"] for r in result}) == 160
    return result, source


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, choices=CANDIDATES)
    parser.add_argument("--model-dir", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--limit", type=int, help="development prefix; resumed by omitting this flag")
    args = parser.parse_args()
    authorization = read_json(AUTHORITY)
    if not authorization["local_execution_authorized"] or args.candidate not in authorization["candidate_keys"]:
        raise RuntimeError("candidate outside researcher-authorized local scope")
    candidate = args.candidate
    model_dir = args.model_dir or Path("/opt/tokkio-data0/tokkio_models/paper1_judges") / candidate
    out = args.output or PROJECT / "outputs/paper1_pairwise_teacher/local_comparison_20260917_v2" / candidate
    out.mkdir(parents=True, exist_ok=True)
    rows, source = requests(candidate)
    thinking = candidate == "qwen35_9b"
    config = read_json(model_dir / "config.json")
    context = config.get("text_config", config)["max_position_embeddings"]
    identity = {
        "protocol": "paper1-local-natural-end-development-v1", "candidate": candidate,
        "model": CANDIDATES[candidate][0], "revision": CANDIDATES[candidate][1],
        "authority_sha256": sha256_file(AUTHORITY), "source_sha256": sha256_file(source),
        "runner_sha256": sha256_file(Path(__file__)),
        "helper_sha256": sha256_file(PROJECT / "src/metacom_pm/paper1/evaluation/local_teacher.py"),
        "model_files": {p.name: sha256_file(p) for p in sorted(model_dir.iterdir())
                        if p.is_file() and p.suffix in {".json", ".safetensors", ".jinja", ".txt"}},
        "context_limit": context, "output_token_cap": None, "normal_stop": "model_EOS_EOT",
        "timeout_seconds": 900 if thinking else 300,
        "exact_cycle_guard": {"block_tokens": 32, "consecutive_repeats": 4},
        "thinking": thinking, "temperature": 0.6 if thinking else 0,
        "top_p": 0.95 if thinking else None, "top_k": 20 if thinking else None,
        "seed_policy": "20260917_plus_first_8_hex_of_presentation_sha256",
        "dtype": "bfloat16", "attention": "sdpa", "concurrency": 1,
        "packages": {p: importlib.metadata.version(p) for p in ["torch", "transformers", "huggingface_hub"]},
        "API_cost_usd": 0, "formal_labels": False,
    }
    identity_hash = sha256_text(canonical_json(identity))
    manifest_path = out / "manifest.json"
    if manifest_path.exists() and read_json(manifest_path)["identity_sha256"] != identity_hash:
        raise RuntimeError("resume identity changed; use a distinct development run directory")
    atomic_json(manifest_path, {"identity_sha256": identity_hash, **identity})
    for row in rows:
        row["request_sha256"] = sha256_text(canonical_json({"identity": identity_hash, "request": row}))
    atomic_json(out / "requests.json", rows)
    pending = []
    for row in rows:
        saved = out / "responses" / (row["presentation_id"] + ".json")
        if saved.exists():
            old = read_json(saved)
            if old["request_sha256"] != row["request_sha256"]:
                raise RuntimeError("cached response request mismatch")
        else:
            pending.append(row)
    if args.limit is not None:
        pending = pending[:args.limit]
    if not pending:
        print(json.dumps({"candidate": candidate, "pending": 0}), flush=True)
        return

    import torch
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList
    torch.set_num_threads(4)
    if torch.cuda.get_device_name(0) != "NVIDIA RTX A6000":
        raise RuntimeError("this development run is bound to A6000")
    tokenizer = AutoTokenizer.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False)
    loader = transformers.AutoModelForImageTextToText if thinking else AutoModelForCausalLM
    print(json.dumps({"loading": candidate, "pending": len(pending), "context": context}), flush=True)
    model = loader.from_pretrained(model_dir, local_files_only=True, trust_remote_code=False,
                                  dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda:0")
    model.eval()
    eos = model.generation_config.eos_token_id or tokenizer.eos_token_id
    eos = [eos] if isinstance(eos, int) else eos
    if candidate == "summary_generator":
        eos = [tokenizer.eos_token_id]  # Preserve the existing reference server's EOT.
    atomic_json(out / "runtime.json", {"created_at": utc_now(), "gpu": torch.cuda.get_device_name(0),
                "cuda": torch.version.cuda, "eos_ids": eos, "chat_template_sha256": sha256_text(tokenizer.chat_template),
                "model_class": type(model).__name__, "identity_sha256": identity_hash})

    class Guard(StoppingCriteria):
        def __init__(self, prompt_len):
            self.prompt_len = prompt_len
            self.start = time.monotonic()
            self.reason = None

        def __call__(self, input_ids, scores, **kwargs):
            if time.monotonic() - self.start >= identity["timeout_seconds"]:
                self.reason = "timeout"
            elif input_ids.shape[-1] - self.prompt_len >= 128 and repeated_tail(input_ids[0, -128:].tolist()):
                self.reason = "repetition_guard"
            return self.reason is not None

    for row in pending:
        spent = sum(read_json(p).get("seconds", 0) for p in out.parent.glob("*/responses/*.json"))
        if spent >= authorization["local_generation_wall_budget_seconds"]:
            print(json.dumps({"stop": "local_runtime_budget", "seconds": spent}), flush=True)
            break
        kwargs = {"enable_thinking": True} if thinking else {}
        rendered = tokenizer.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=True, **kwargs)
        encoded = tokenizer(rendered, add_special_tokens=False, return_tensors="pt", truncation=False)
        n = encoded.input_ids.shape[-1]
        if n >= context:
            raise RuntimeError("complete input exceeds model context; never truncate evidence")
        encoded = {k: v.to("cuda:0") for k, v in encoded.items()}
        seed = (20260917 + int(sha256_text(row["presentation_id"])[:8], 16)) % (2**32)
        torch.manual_seed(seed)
        torch.cuda.manual_seed_all(seed)
        guard = Guard(n)
        record = {k: v for k, v in row.items() if k != "messages"}
        record.update(started_at=utc_now(), identity_sha256=identity_hash, input_tokens=n, seed=seed)
        with (out / "attempts.jsonl").open("a") as handle:
            handle.write(canonical_json({"event": "start", **record}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        start = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        try:
            generation = dict(max_new_tokens=context-n, do_sample=thinking, eos_token_id=eos,
                              pad_token_id=tokenizer.pad_token_id or eos[0], use_cache=True,
                              forced_eos_token_id=None, stopping_criteria=StoppingCriteriaList([guard]))
            if thinking:
                generation.update(temperature=0.6, top_p=0.95, top_k=20)
            else:
                generation.update(temperature=None, top_p=None, top_k=None)
            with torch.inference_mode():
                output = model.generate(**encoded, **generation)
            new_ids = output[0, n:].tolist()
            raw = tokenizer.decode(new_ids, skip_special_tokens=True)
            finish = natural_finish_reason(new_ids, eos, guard.reason, context-n)
            record.update(raw_output=raw, output_tokens=len(new_ids), output_token_ids_sha256=sha256_text(canonical_json(new_ids)),
                          finish_reason=finish, natural_end=finish == "stop", candidate_verdict=None)
            if candidate == "summary_generator":
                record["status"] = "COMPLETED" if finish == "stop" else "INCOMPLETE"
            elif finish == "stop":
                try:
                    parsed = parse_local_verdict(raw, thinking=thinking)
                    record.update(status="SUCCEEDED", candidate_verdict=parsed["verdict"], rationale=parsed["rationale"])
                except ValueError as exc:
                    record.update(status="PARSE_FAILED", parse_error=str(exc))
            else:
                record["status"] = "INCOMPLETE"
            del output
        except Exception as exc:
            record.update(status="EXECUTION_FAILED", error=type(exc).__name__ + ": " + str(exc),
                          candidate_verdict=None, natural_end=False)
        record.update(seconds=time.monotonic()-start, completed_at=utc_now(),
                      peak_allocated_bytes=torch.cuda.max_memory_allocated())
        atomic_json(out / "responses" / (row["presentation_id"] + ".json"), record)
        saved = [read_json(p) for p in sorted((out / "responses").glob("*.json"))]
        summary = {"candidate": candidate, "scheduled": len(rows), "attempted": len(saved),
                   "statuses": dict(Counter(r["status"] for r in saved)),
                   "finishes": dict(Counter(r.get("finish_reason", "execution_failed") for r in saved)),
                   "seconds": sum(r["seconds"] for r in saved), "API_cost_usd": 0}
        atomic_json(out / "progress.json", summary)
        print(json.dumps({**summary, "last_task": row["task"], "last_tokens": record.get("output_tokens"),
                          "last_seconds": round(record["seconds"], 2)}), flush=True)
        del encoded
        torch.cuda.empty_cache()
        if record["status"] == "EXECUTION_FAILED":
            raise RuntimeError(record["error"])


if __name__ == "__main__":
    main()
