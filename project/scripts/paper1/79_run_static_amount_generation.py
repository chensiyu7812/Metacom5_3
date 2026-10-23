#!/usr/bin/env python3
"""Resumable natural-end Generator executor for the static amount-calibration batch.

Runs exactly the 1,924 prepared requests of static_sample_20260917_v1 on the
frozen Llama-3.1-8B stack. Free and local: no paid API, no formal outcome, no
k* freeze, no PM training. Output uses EOS/EOT with no task-level token cap;
timeout, exact-cycle interruption and context exhaustion are recorded as
distinct incomplete outcomes rather than complete answers or zero scores.

Resume is identity-checked per request, so an interrupted run never regenerates
a completed request and never binds a response to the wrong request. The shared
true-OFF condition exists once per target in the package and is generated once.
"""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import sys
import time
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_file, sha256_text, utc_now, write_json
from metacom_pm.paper1.evaluation.local_teacher import natural_finish_reason, repeated_tail
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

AUTHORITY = PROJECT / "data/paper1_authority/paper1_static_amount_calibration_execution_20260917_v1.json"
CONFIG = PROJECT / "configs/paper1_public_only.yaml"
MODEL_DIR = Path("/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct"
                 "/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77")
PROTOCOL = "paper1-static-amount-generation-v1"


def atomic_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")
    tmp.replace(path)


def load_package(package: Path) -> tuple[dict, list[dict]]:
    summary = read_json(package / "preparation_summary.json")
    for name, digest in summary["package_artifacts"].items():
        if sha256_file(package / name) != digest:
            raise RuntimeError(f"calibration package file changed since preparation: {name}")
    requests = list(iter_jsonl(package / "generator_requests.jsonl"))
    if len(requests) != summary["generator_calls"]:
        raise RuntimeError("package request count disagrees with the preparation summary")
    if len({r["request_id"] for r in requests}) != len(requests):
        raise RuntimeError("duplicate request identity in the prepared package")
    config_hashes = {r["generator_config_sha256"] for r in requests}
    expected = sha256_text(canonical_json(read_json(package / "generator_config.json")))
    if config_hashes != {expected}:
        raise RuntimeError("prepared requests are not bound to the packaged Generator config")
    off_rows = [r for r in requests if r["head"] is None]
    if not len(off_rows) == len({r["target_id"] for r in off_rows}) == summary["sample_targets"]:
        raise RuntimeError("the shared true-OFF condition is not exactly one row per target")
    for row in requests:
        rebuilt = sha256_text(canonical_json({"generator_config_sha256": row["generator_config_sha256"],
                                              "messages": row["messages"]}))
        if rebuilt != row["request_sha256"]:
            raise RuntimeError(f"prepared request hash does not match its messages: {row['request_id']}")
    return summary, requests


def verify_device(authority: dict) -> "object":
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("no visible CUDA device; the frozen Generator is not run on CPU")
    if torch.cuda.device_count() != 1:
        raise RuntimeError("bind exactly one visible device with CUDA_VISIBLE_DEVICES")
    name = torch.cuda.get_device_name(0)
    if name != "NVIDIA RTX A6000":
        raise RuntimeError(f"static amount generation is bound to the A6000; visible device is {name}")
    free, total = torch.cuda.mem_get_info(0)
    required = authority["gpu_policy"]["free_memory_preflight_bytes"]
    if free < required:
        raise RuntimeError(
            f"A6000 free memory {free / 1024 ** 3:.2f} GiB is below the {required / 1024 ** 3:.2f} GiB preflight; "
            "other-project jobs keep priority and no fallback device is used")
    return torch


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_sample_20260917_v1")
    parser.add_argument("--out", type=Path,
                        default=PROJECT / "outputs/paper1_calibration/static_generation_20260917_v1")
    parser.add_argument("--limit", type=int, help="attempt at most this many pending requests, then stop")
    parser.add_argument("--preflight-only", action="store_true",
                        help="validate package, authorization and device without loading the model")
    args = parser.parse_args()

    authority = read_json(AUTHORITY)
    if not authority.get("local_generation_authorized"):
        raise RuntimeError("local static amount generation is not authorized")
    if authority.get("new_paid_API_calls_authorized"):
        raise RuntimeError("this executor never makes paid calls")
    assert_pre_outcome_locked(load_public_only_config(CONFIG))

    summary, requests = load_package(args.package)
    if authority["package"]["generator_requests_sha256"] != sha256_file(args.package / "generator_requests.jsonl"):
        raise RuntimeError("authorized package request manifest changed")

    generator_config = read_json(args.package / "generator_config.json")
    identity = {
        "protocol": PROTOCOL,
        "package": str(args.package.relative_to(PROJECT)),
        "package_summary_sha256": sha256_file(args.package / "preparation_summary.json"),
        "authority_sha256": sha256_file(AUTHORITY),
        "runner_sha256": sha256_file(Path(__file__)),
        "helper_sha256": sha256_file(PROJECT / "src/metacom_pm/paper1/evaluation/local_teacher.py"),
        "generator_config": generator_config,
        "model_dir": str(MODEL_DIR),
        "model_files": {p.name: sha256_file(p) for p in sorted(MODEL_DIR.iterdir())
                        if p.is_file() and p.suffix in {".json", ".safetensors"}},
        "packages": {p: importlib.metadata.version(p) for p in ["torch", "transformers", "huggingface_hub"]},
        "scheduled_requests": len(requests),
        "API_cost_usd": 0,
        "formal_outcomes": 0,
    }
    identity_hash = sha256_text(canonical_json(identity))
    args.out.mkdir(parents=True, exist_ok=True)
    manifest_path = args.out / "manifest.json"
    if manifest_path.exists() and read_json(manifest_path)["identity_sha256"] != identity_hash:
        raise RuntimeError("resume identity changed; use a distinct generation run directory")
    atomic_json(manifest_path, {"identity_sha256": identity_hash, **identity})

    responses = args.out / "responses"
    pending = []
    completed = 0
    for row in requests:
        saved_path = responses / (row["request_id"] + ".json")
        if not saved_path.exists():
            pending.append(row)
            continue
        saved = read_json(saved_path)
        if saved["request_sha256"] != row["request_sha256"] or saved["request_id"] != row["request_id"]:
            raise RuntimeError(f"cached response identity disagrees with the package: {row['request_id']}")
        if saved.get("identity_sha256") != identity_hash:
            raise RuntimeError(f"cached response came from a different run identity: {row['request_id']}")
        completed += 1

    if args.limit is not None:
        pending = pending[:args.limit]
    print(json.dumps({"scheduled": len(requests), "already_completed": completed,
                      "pending_this_invocation": len(pending)}), flush=True)
    if args.preflight_only:
        verify_device(authority)
        print(json.dumps({"status": "PREFLIGHT_OK"}), flush=True)
        return
    if not pending:
        print(json.dumps({"status": "NOTHING_PENDING"}), flush=True)
        return

    torch = verify_device(authority)
    import transformers
    from transformers import AutoModelForCausalLM, AutoTokenizer, StoppingCriteria, StoppingCriteriaList

    torch.set_num_threads(4)
    tokenizer = AutoTokenizer.from_pretrained(str(MODEL_DIR), local_files_only=True, trust_remote_code=False)
    if sha256_text(tokenizer.chat_template) != generator_config["chat_template_sha256"]:
        raise RuntimeError("chat template differs from the packaged Generator identity")
    if sha256_file(MODEL_DIR / "tokenizer.json") != generator_config["tokenizer_json_sha256"]:
        raise RuntimeError("tokenizer.json differs from the packaged Generator identity")
    context = generator_config["native_context_tokens"]
    print(json.dumps({"loading": "frozen_generator", "pending": len(pending), "context": context}), flush=True)
    model = AutoModelForCausalLM.from_pretrained(
        str(MODEL_DIR), local_files_only=True, trust_remote_code=False,
        dtype=torch.bfloat16, attn_implementation="sdpa").to("cuda:0")
    model.eval()
    # The frozen reference backend passes only tokenizer.eos_token_id to generate,
    # which script 52 audited as <|eot_id|> == 128009. The wider generation_config
    # eos list is deliberately not used, so stopping matches the frozen stack.
    if tokenizer.eos_token != "<|eot_id|>" or tokenizer.eos_token_id != 128009:
        raise RuntimeError("tokenizer EOT identity differs from the audited frozen backend")
    eos = [int(tokenizer.eos_token_id)]
    atomic_json(args.out / "runtime.json", {
        "created_at": utc_now(), "gpu": torch.cuda.get_device_name(0), "cuda": torch.version.cuda,
        "eos_ids": eos, "model_class": type(model).__name__, "identity_sha256": identity_hash,
        "transformers": transformers.__version__})

    timeout_seconds = generator_config["technical_timeout_seconds"]
    guard_config = generator_config["exact_cycle_guard"]

    class Guard(StoppingCriteria):
        def __init__(self, prompt_len: int) -> None:
            self.prompt_len = prompt_len
            self.start = time.monotonic()
            self.reason: str | None = None

        def __call__(self, input_ids, scores, **kwargs) -> bool:
            generated = input_ids.shape[-1] - self.prompt_len
            window = guard_config["block_tokens"] * guard_config["repeats"]
            if time.monotonic() - self.start >= timeout_seconds:
                self.reason = "timeout"
            elif generated >= window and repeated_tail(input_ids[0, -window:].tolist(),
                                                      block=guard_config["block_tokens"],
                                                      repeats=guard_config["repeats"]):
                self.reason = "repetition_guard"
            return self.reason is not None

    attempts_path = args.out / "attempts.jsonl"
    for row in pending:
        rendered = tokenizer.apply_chat_template(row["messages"], tokenize=False, add_generation_prompt=True)
        encoded = tokenizer(rendered, add_special_tokens=False, return_tensors="pt", truncation=False)
        n = int(encoded.input_ids.shape[-1])
        if n != row["input_tokens"]:
            raise RuntimeError(f"rendered input length {n} differs from the prepared {row['input_tokens']}")
        if n >= context:
            raise RuntimeError("complete input exceeds model context; never truncate assigned evidence")
        encoded = {k: v.to("cuda:0") for k, v in encoded.items()}
        torch.manual_seed(generator_config["seed"])
        torch.cuda.manual_seed_all(generator_config["seed"])
        guard = Guard(n)
        record = {k: v for k, v in row.items() if k != "messages"}
        record.update(started_at=utc_now(), identity_sha256=identity_hash, protocol=PROTOCOL,
                      seed=generator_config["seed"], API_cost_usd=0)
        with attempts_path.open("a") as handle:
            handle.write(canonical_json({"event": "start", "request_id": row["request_id"],
                                         "request_sha256": row["request_sha256"],
                                         "input_tokens": n, "at": record["started_at"]}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        start = time.monotonic()
        torch.cuda.reset_peak_memory_stats()
        try:
            with torch.inference_mode():
                output = model.generate(
                    **encoded, max_new_tokens=context - n, do_sample=False,
                    temperature=None, top_p=None, top_k=None,
                    eos_token_id=eos, pad_token_id=tokenizer.pad_token_id or eos[0],
                    use_cache=True, forced_eos_token_id=None,
                    stopping_criteria=StoppingCriteriaList([guard]))
            new_ids = output[0, n:].tolist()
            finish = natural_finish_reason(new_ids, eos, guard.reason, context - n)
            record.update(raw_output=tokenizer.decode(new_ids, skip_special_tokens=True),
                          output_tokens=len(new_ids),
                          output_token_ids_sha256=sha256_text(canonical_json(new_ids)),
                          finish_reason=finish, natural_end=finish == "stop",
                          status="COMPLETED" if finish == "stop" else "INCOMPLETE")
            del output
        except Exception as exc:
            record.update(raw_output=None, output_tokens=None, finish_reason="execution_failed",
                          natural_end=False, status="EXECUTION_FAILED",
                          error=f"{type(exc).__name__}: {exc}")
        record.update(seconds=time.monotonic() - start, completed_at=utc_now(),
                      peak_allocated_bytes=int(torch.cuda.max_memory_allocated()))
        with attempts_path.open("a") as handle:
            handle.write(canonical_json({"event": "end", "request_id": row["request_id"],
                                         "status": record["status"], "finish_reason": record["finish_reason"],
                                         "output_tokens": record.get("output_tokens"),
                                         "seconds": record["seconds"], "at": record["completed_at"]}) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        if record["status"] == "EXECUTION_FAILED":
            # A technical failure is never stored as an answer; it stays a retryable gap.
            print(json.dumps({"request_id": row["request_id"], "error": record["error"]}), flush=True)
            raise RuntimeError(record["error"])
        atomic_json(responses / (row["request_id"] + ".json"), record)
        saved = [read_json(p) for p in sorted(responses.glob("*.json"))]
        progress = {"protocol": PROTOCOL, "scheduled": len(requests), "completed_records": len(saved),
                    "statuses": dict(Counter(r["status"] for r in saved)),
                    "finish_reasons": dict(Counter(r["finish_reason"] for r in saved)),
                    "natural_end": sum(1 for r in saved if r["natural_end"]),
                    "generation_seconds": sum(r["seconds"] for r in saved),
                    "output_tokens": sum(r["output_tokens"] or 0 for r in saved),
                    "API_cost_usd": 0, "formal_outcomes": 0, "k_star_frozen": False,
                    "identity_sha256": identity_hash, "updated_at": utc_now()}
        atomic_json(args.out / "progress.json", progress)
        print(json.dumps({**{k: progress[k] for k in ["completed_records", "natural_end", "statuses"]},
                          "last": row["request_id"], "task": row["task"], "head": row["head"], "k": row["k"],
                          "out_tokens": record.get("output_tokens"),
                          "seconds": round(record["seconds"], 2)}), flush=True)
        del encoded
        torch.cuda.empty_cache()


if __name__ == "__main__":
    main()
