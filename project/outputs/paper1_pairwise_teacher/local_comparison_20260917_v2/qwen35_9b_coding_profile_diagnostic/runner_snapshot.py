#!/usr/bin/env python3
"""Local judge development with continuous batching and natural EOS."""
from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import time
from collections import Counter
from pathlib import Path

spec = importlib.util.spec_from_file_location("local_runner", Path(__file__).with_name("67_run_local_teacher_comparison.py"))
base = importlib.util.module_from_spec(spec)
spec.loader.exec_module(base)
from metacom_pm.io import canonical_json, read_json, sha256_file, sha256_text, utc_now
from metacom_pm.paper1.evaluation.local_teacher import parse_local_verdict, repeated_tail


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, choices=["selene_mini_8b", "compassjudger2_7b", "qwen35_9b"])
    args = parser.parse_args()
    candidate = args.candidate
    thinking = candidate == "qwen35_9b"
    authorization = read_json(base.AUTHORITY)
    assert authorization["local_execution_authorized"] and candidate in authorization["candidate_keys"]
    model_dir = Path("/opt/tokkio-data0/tokkio_models/paper1_judges") / candidate
    out = base.PROJECT / "outputs/paper1_pairwise_teacher/local_comparison_20260917_v2" / candidate
    out.mkdir(parents=True, exist_ok=True)
    rows, source = base.requests(candidate)
    config = read_json(model_dir / "config.json")
    native_context = config.get("text_config", config)["max_position_embeddings"]
    context = min(native_context, 32768)
    identity = {
        "protocol": "paper1-local-natural-end-development-v1", "candidate": candidate,
        "model": base.CANDIDATES[candidate][0], "revision": base.CANDIDATES[candidate][1],
        "authority_sha256": sha256_file(base.AUTHORITY), "source_sha256": sha256_file(source),
        "runner_sha256": sha256_file(Path(__file__)), "request_builder_sha256": sha256_file(Path(base.__file__)),
        "helper_sha256": sha256_file(base.PROJECT / "src/metacom_pm/paper1/evaluation/local_teacher.py"),
        "model_files": {p.name: sha256_file(p) for p in sorted(model_dir.iterdir())
                        if p.is_file() and p.suffix in {".json", ".safetensors", ".jinja", ".txt"}},
        "native_context": native_context, "served_context": context,
        "output_token_cap": None, "normal_stop": "model_EOS_EOT", "timeout_seconds": 900 if thinking else 300,
        "exact_cycle_guard": {"block_tokens": 32, "consecutive_repeats": 4},
        "temperature": 0.6 if thinking else 0, "seed": 20260917,
        "seed_policy": "presentation_hash_offset_for_Qwen_else_fixed_greedy",
        "top_p": 0.95 if thinking else 1, "top_k": 20 if thinking else -1, "thinking": thinking,
        "dtype": "bfloat16", "concurrency": 4,
        "backend": "vllm", "prefix_caching": False,
        "packages": {p: importlib.metadata.version(p) for p in ["torch", "transformers", "vllm"]},
        "API_cost_usd": 0, "formal_labels": False,
    }
    identity_hash = sha256_text(canonical_json(identity))
    manifest = out / "manifest.json"
    if manifest.exists() and read_json(manifest)["identity_sha256"] != identity_hash:
        raise RuntimeError("resume identity changed")
    base.atomic_json(manifest, {"identity_sha256": identity_hash, **identity})
    (out / "runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    pending = []
    for row in rows:
        row["request_sha256"] = sha256_text(canonical_json({"identity": identity_hash, "request": row}))
        saved = out / "responses" / (row["presentation_id"] + ".json")
        if saved.exists():
            assert read_json(saved)["request_sha256"] == row["request_sha256"]
        else:
            pending.append(row)
    base.atomic_json(out / "requests.json", rows)
    if not pending:
        return

    import torch
    from vllm import LLM, SamplingParams
    assert torch.cuda.get_device_name(0) == "NVIDIA RTX A6000"
    model_options = {"language_model_only": True} if thinking else {}
    llm = LLM(model=str(model_dir), dtype="bfloat16", max_model_len=context,
              gpu_memory_utilization=0.88, max_num_seqs=4, max_num_batched_tokens=4096,
              enforce_eager=True, enable_prefix_caching=False, seed=20260917, **model_options)
    tokenizer = llm.get_tokenizer()
    engine = llm.llm_engine
    base.atomic_json(out / "runtime.json", {"created_at": utc_now(), "gpu": torch.cuda.get_device_name(0),
        "identity_sha256": identity_hash, "chat_template_sha256": sha256_text(tokenizer.chat_template),
        "timings_are_batched_and_not_formal_latency": True})
    active = {}
    start_run = time.monotonic()
    previous = sum(read_json(p).get("seconds", 0) for p in out.parent.glob("*/responses/*.json"))
    spent = previous

    def save(pid, raw, tokens, finish, stop_detail):
        nonlocal spent
        item = active.pop(pid)
        record = {k: v for k, v in item["row"].items() if k != "messages"}
        seconds = time.monotonic() - item["start"]
        spent += seconds
        record.update(identity_sha256=identity_hash, started_at=item["started_at"], completed_at=utc_now(),
            input_tokens=item["input_tokens"], raw_output=raw, output_tokens=len(tokens),
            output_token_ids_sha256=sha256_text(canonical_json(tokens)), finish_reason=finish,
            stop_detail=stop_detail, natural_end=finish == "stop", candidate_verdict=None,
            seconds=seconds, status="INCOMPLETE")
        if finish == "stop":
            try:
                value = parse_local_verdict(raw, thinking=thinking)
                record.update(status="SUCCEEDED", candidate_verdict=value["verdict"], rationale=value["rationale"])
            except ValueError as exc:
                record.update(status="PARSE_FAILED", parse_error=str(exc))
        base.atomic_json(out / "responses" / (pid + ".json"), record)
        saved = [read_json(p) for p in (out / "responses").glob("*.json")]
        progress = {"candidate": candidate, "scheduled": 160, "attempted": len(saved),
            "statuses": dict(Counter(r["status"] for r in saved)),
            "finishes": dict(Counter(r["finish_reason"] for r in saved)),
            "seconds": sum(r["seconds"] for r in saved), "engine_wall_seconds": time.monotonic() - start_run,
            "API_cost_usd": 0}
        base.atomic_json(out / "progress.json", progress)
        print(json.dumps({**progress, "last_task": record["task"], "last_tokens": len(tokens)}), flush=True)

    while pending or active:
        while pending and len(active) < 4 and spent < authorization["local_generation_wall_budget_seconds"]:
            row = pending.pop(0)
            template_options = {"enable_thinking": True} if thinking else {}
            ids = tokenizer.apply_chat_template(row["messages"], tokenize=True, return_dict=False,
                                                add_generation_prompt=True, **template_options)
            if len(ids) >= context:
                raise RuntimeError("complete evidence exceeds served context; never truncate")
            pid = row["presentation_id"]
            active[pid] = {"row": row, "input_tokens": len(ids), "start": time.monotonic(), "started_at": utc_now()}
            with (out / "attempts.jsonl").open("a") as handle:
                handle.write(canonical_json({"event": "start", "presentation_id": pid,
                    "request_sha256": row["request_sha256"], "started_at": active[pid]["started_at"]}) + "\n")
                handle.flush()
                os.fsync(handle.fileno())
            seed = (20260917 + int(sha256_text(pid)[:8], 16)) % (2**32) if thinking else 20260917
            engine.add_request(pid, {"prompt_token_ids": ids}, SamplingParams(temperature=identity["temperature"],
                top_p=identity["top_p"], top_k=identity["top_k"], max_tokens=context-len(ids), seed=seed))
        if not active:
            break
        for output in engine.step():
            pid = output.request_id
            if pid not in active:
                continue
            answer = output.outputs[0]
            finish = None
            if output.finished:
                finish = "stop" if answer.finish_reason == "stop" else "context_exhausted"
            elif time.monotonic() - active[pid]["start"] >= identity["timeout_seconds"]:
                finish = "timeout"
            elif repeated_tail(list(answer.token_ids)):
                finish = "repetition_guard"
            if finish:
                if not output.finished:
                    engine.abort_request([pid])
                save(pid, answer.text, list(answer.token_ids), finish, answer.stop_reason)


if __name__ == "__main__":
    main()
