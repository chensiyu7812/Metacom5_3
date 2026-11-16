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
from metacom_pm.paper1.evaluation.teacher_reasoning_format import reasoning_first_prompt, parse_reasoning_result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", required=True, choices=["selene_mini_8b", "compassjudger2_7b", "qwen35_9b"])
    parser.add_argument("--output", type=Path)
    parser.add_argument("--request-file", type=Path, help="prepared same-pair Summary evidence/completion diagnostic")
    parser.add_argument("--resume-from", type=Path, help="skip completed presentations from an equivalent generation configuration")
    parser.add_argument("--prepare-only", action="store_true", help="validate continuation and requests without loading the model")
    parser.add_argument("--reasoning-first", action="store_true", help="Selene output-format-only development diagnostic")
    args = parser.parse_args()
    candidate = args.candidate
    thinking = candidate == "qwen35_9b"
    authorization = read_json(base.AUTHORITY)
    assert authorization["local_execution_authorized"] and candidate in authorization["candidate_keys"]
    model_dir = Path("/opt/tokkio-data0/tokkio_models/paper1_judges") / candidate
    out = args.output or base.PROJECT / "outputs/paper1_pairwise_teacher/local_comparison_20260917_v2" / candidate
    out.mkdir(parents=True, exist_ok=True)
    if args.request_file:
        assert candidate in {"compassjudger2_7b", "qwen35_9b"} or (candidate == "selene_mini_8b" and args.reasoning_first)
        source = args.request_file
        rows = read_json(source)
        assert len(rows) == 52 and len({r["presentation_id"] for r in rows}) == 52
        assert all(r["task"] == "Summary" and r["development_variant"] in
                   {"same_answers_full_history", "natural_answers_full_history"} for r in rows)
    else:
        rows, source = base.requests(candidate)
    if args.reasoning_first:
        assert candidate == "selene_mini_8b" and args.output
        for row in rows:
            row["messages"][0]["content"] = reasoning_first_prompt(row["messages"][0]["content"])
    verdict_parser = parse_reasoning_result if args.reasoning_first else parse_local_verdict
    config = read_json(model_dir / "config.json")
    native_context = config.get("text_config", config)["max_position_embeddings"]
    context = min(native_context, 131072 if thinking else 32768)
    identity = {
        "protocol": "paper1-local-natural-end-development-v1", "candidate": candidate,
        "model": base.CANDIDATES[candidate][0], "revision": base.CANDIDATES[candidate][1],
        "authority_sha256": sha256_file(base.AUTHORITY), "source_sha256": sha256_file(source),
        "runner_sha256": sha256_file(Path(__file__)), "request_builder_sha256": sha256_file(Path(base.__file__)),
        "helper_sha256": sha256_file(base.PROJECT / "src/metacom_pm/paper1/evaluation/local_teacher.py"),
        "response_format": "reasoning_then_result" if args.reasoning_first else "JSON",
        "reasoning_format_helper_sha256": sha256_file(base.PROJECT / "src/metacom_pm/paper1/evaluation/teacher_reasoning_format.py") if args.reasoning_first else None,
        "model_files": {p.name: sha256_file(p) for p in sorted(model_dir.iterdir())
                        if p.is_file() and p.suffix in {".json", ".safetensors", ".jinja", ".txt"}},
        "native_context": native_context, "served_context": context,
        "output_token_cap": None, "normal_stop": "model_EOS_EOT", "timeout_seconds": 900 if thinking else 300,
        "exact_cycle_guard": {"block_tokens": 32, "consecutive_repeats": 4},
        "temperature": 1.0 if thinking else 0, "seed": 20260917,
        "seed_policy": "paired_source_presentation_seed_for_Summary_diagnostics" if thinking and args.request_file else "presentation_hash_offset_for_Qwen_else_fixed_greedy",
        "top_p": 0.95 if thinking else 1, "top_k": 20 if thinking else -1, "thinking": thinking,
        "min_p": 0.0, "presence_penalty": 1.5 if thinking else 0.0, "repetition_penalty": 1.0,
        "sampling_reference": "https://huggingface.co/Qwen/Qwen3.5-9B/blob/c202236235762e1c871ad0ccb60c8ee5ba337b9a/README.md#best-practices" if thinking else "greedy",
        "dtype": "bfloat16", "concurrency": 4,
        "backend": "vllm", "prefix_caching": False,
        "packages": {p: importlib.metadata.version(p) for p in ["torch", "transformers", "vllm"]},
        "API_cost_usd": 0, "formal_labels": False,
        "budget_accounting": "cumulative_engine_wall_time_not_overlapping_request_durations",
        "continuation_of": str(args.resume_from) if args.resume_from else None,
    }
    identity_hash = sha256_text(canonical_json(identity))
    manifest = out / "manifest.json"
    if manifest.exists() and read_json(manifest)["identity_sha256"] != identity_hash:
        raise RuntimeError("resume identity changed")
    base.atomic_json(manifest, {"identity_sha256": identity_hash, **identity})
    (out / "runner_snapshot.py").write_bytes(Path(__file__).read_bytes())
    (out / "authority_snapshot.json").write_bytes(base.AUTHORITY.read_bytes())
    resumed = {}
    if args.resume_from:
        previous_identity = read_json(args.resume_from / "manifest.json")
        for key in ["candidate", "model", "revision", "source_sha256", "helper_sha256", "model_files", "served_context",
                    "temperature", "top_p", "top_k", "thinking", "dtype", "concurrency", "backend", "packages", "seed_policy",
                    "seed", "normal_stop", "output_token_cap", "timeout_seconds", "exact_cycle_guard", "prefix_caching",
                    "presence_penalty", "repetition_penalty", "min_p"]:
            if previous_identity[key] != identity[key]:
                raise RuntimeError("continuation generation configuration changed: " + key)
        if previous_identity.get("response_format", "JSON") != identity["response_format"]:
            raise RuntimeError("continuation response format changed")
        if previous_identity.get("reasoning_format_helper_sha256") != identity["reasoning_format_helper_sha256"]:
            raise RuntimeError("continuation reasoning-format implementation changed")
        previous_requests = {r["presentation_id"]: r for r in read_json(args.resume_from / "requests.json")}
        for row in rows:
            prior = previous_requests[row["presentation_id"]]
            assert row["messages"] == prior["messages"] and row["task"] == prior["task"]
        resumed = {p.stem: read_json(p) for p in (args.resume_from / "responses").glob("*.json")}
        for pid, response in resumed.items():
            assert response["request_sha256"] == previous_requests[pid]["request_sha256"]
            assert response["identity_sha256"] == previous_identity["identity_sha256"]
    pending = []
    for row in rows:
        row["request_sha256"] = sha256_text(canonical_json({"identity": identity_hash, "request": row}))
        saved = out / "responses" / (row["presentation_id"] + ".json")
        if saved.exists():
            assert read_json(saved)["request_sha256"] == row["request_sha256"]
        elif row["presentation_id"] not in resumed:
            pending.append(row)
    base.atomic_json(out / "requests.json", rows)
    if args.prepare_only:
        print(json.dumps({"candidate": candidate, "validated_prior_responses": len(resumed),
                          "pending": len(pending), "new_model_calls": 0}), flush=True)
        return
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
    prior_segment_wall = read_json(out / "progress.json").get("engine_wall_seconds", 0) if (out / "progress.json").exists() else 0
    # The interrupted preliminary Qwen prefill has no completed response timer.
    # Conservatively reserve its full 900-second timeout once in this run family.
    previous = 900 + sum(read_json(p).get("engine_wall_seconds", read_json(p).get("seconds", 0))
                         for p in out.parent.glob("*/progress.json"))

    def save(pid, raw, tokens, finish, stop_detail):
        item = active.pop(pid)
        record = {k: v for k, v in item["row"].items() if k != "messages"}
        seconds = time.monotonic() - item["start"]
        record.update(identity_sha256=identity_hash, started_at=item["started_at"], completed_at=utc_now(),
            input_tokens=item["input_tokens"], raw_output=raw, output_tokens=len(tokens),
            output_token_ids_sha256=sha256_text(canonical_json(tokens)), finish_reason=finish,
            stop_detail=stop_detail, natural_end=finish == "stop", candidate_verdict=None,
            seconds=seconds, status="INCOMPLETE")
        if finish == "stop":
            try:
                value = verdict_parser(raw, thinking=thinking)
                record.update(status="SUCCEEDED", candidate_verdict=value["verdict"], rationale=value["rationale"])
            except ValueError as exc:
                record.update(status="PARSE_FAILED", parse_error=str(exc))
        base.atomic_json(out / "responses" / (pid + ".json"), record)
        saved = [read_json(p) for p in (out / "responses").glob("*.json")]
        progress = {"candidate": candidate, "scheduled": len(rows), "attempted": len(saved),
            "statuses": dict(Counter(r["status"] for r in saved)),
            "finishes": dict(Counter(r["finish_reason"] for r in saved)),
            "seconds": sum(r["seconds"] for r in saved), "engine_wall_seconds": prior_segment_wall + time.monotonic() - start_run,
            "prior_generation_wall_seconds_including_interrupted_reserve": previous,
            "completed_in_prior_segment": len(resumed),
            "API_cost_usd": 0}
        base.atomic_json(out / "progress.json", progress)
        print(json.dumps({**progress, "last_task": record["task"], "last_tokens": len(tokens)}), flush=True)

    while pending or active:
        while pending and len(active) < 4 and previous + time.monotonic() - start_run < authorization["local_generation_wall_budget_seconds"]:
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
            seed = (20260917 + int(sha256_text(row.get("seed_key", pid))[:8], 16)) % (2**32) if thinking else 20260917
            engine.add_request(pid, {"prompt_token_ids": ids}, SamplingParams(temperature=identity["temperature"],
                top_p=identity["top_p"], top_k=identity["top_k"], min_p=identity["min_p"],
                presence_penalty=identity["presence_penalty"], repetition_penalty=identity["repetition_penalty"],
                max_tokens=context-len(ids), seed=seed))
        if not active:
            if pending:
                print(json.dumps({"stop": "local_runtime_budget", "pending": len(pending),
                                  "accounted_wall_seconds": previous + time.monotonic() - start_run}), flush=True)
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
