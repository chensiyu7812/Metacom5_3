#!/usr/bin/env python3
"""Six local development calls: three preselected train prefixes, OFF and MS/MP.

Uses actual frozen retrieval inventories. J is not yet validated: all successful
episodes remain pending_score, with no fabricated reward or training updates.
"""
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import sha256_file
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter
from metacom_pm.rl1.schema import EpisodeSpec, PrefixSpec, PublicTurn, Resource, digest
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.generation import LocalNaturalGenerator
from metacom_pm.rl1.cache import AttemptCache

OUT = PROJECT / "outputs/pm_rl1/engineering_20260928_v1"
MODEL = Path("/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77")


def save(path, obj):
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")
    temp.replace(path)


def main():
    source_manifest = json.loads((OUT / "retrieval_manifest.json").read_text())
    for filename, expected in source_manifest["artifact_sha256"].items():
        if sha256_file(OUT / filename) != expected:
            raise RuntimeError("engineering inventory changed: " + filename)
    raw_specs = json.loads((OUT / "episode_specs_private.json").read_text())
    assert len(raw_specs) == 3 and all(s["prefix"]["split"] == "train" for s in raw_specs)
    print(json.dumps(dict(stage="loading_local_generator")), flush=True)
    generator = LocalNaturalGenerator(MODEL)
    print(json.dumps(dict(stage="loaded", seconds=generator.load_seconds, identity=generator.identity)), flush=True)
    run_dir = OUT / "generation" / generator.identity
    run_dir.mkdir(parents=True, exist_ok=True)
    save(run_dir / "runtime.json", dict(**generator.manifest, identity=generator.identity, load_seconds=generator.load_seconds))
    cache = AttemptCache(run_dir / "attempts.sqlite")
    counter = build_llama_token_counter(MODEL / "tokenizer.json")
    render = Renderer(count_text=counter,
        count_chat=lambda m: len(generator.tokenizer.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=sha256_file(MODEL / "tokenizer.json"), template=generator.tokenizer.chat_template)),
        context_limit=generator.policy.context_limit)
    if render.identity != source_manifest["renderer_identity"]:
        raise ValueError("capacity/generation renderer mismatch")
    results = []
    for raw in raw_specs:
        prefix = PrefixSpec(**{**raw["prefix"], "turns": tuple(PublicTurn(**t) for t in raw["prefix"]["turns"])})
        inventory = tuple(tuple(Resource(**{**r, "source_ids": tuple(r["source_ids"])}) for r in items) for items in raw["inventory"])
        spec = EpisodeSpec(**{**raw, "prefix": prefix, "inventory": inventory, "executor_identity": generator.identity})
        for arm in ("OFF", "mechanical_MS_MP"):
            env = ResourceEnv(spec, render)
            if arm != "OFF":
                for action in (3, 2):
                    if env.observe().action_mask[action]:
                        env.step(action, expected_state_hash=env.state_hash)
            env.step(0, expected_state_hash=env.state_hash)
            request = env.generation_request()
            save(run_dir / (request["request_id"] + ".request.json"), request)
            cached = cache.claim(request)
            if cached is None:
                try:
                    response = generator.generate(request)
                except Exception as exc:
                    response = dict(request_id=request["request_id"], runtime_identity=generator.identity,
                                    finish_reason="exception", text="", exception_type=type(exc).__name__,
                                    error=str(exc), api_cost_usd=0)
                cache.finish(request["request_id"], response)
            else:
                response = cached
            env.accept_generation(**{k: response[k] for k in ("request_id", "runtime_identity", "finish_reason", "text")})
            save(run_dir / (request["request_id"] + ".response.json"), response)
            save(run_dir / (request["request_id"] + ".episode.json"), env.snapshot())
            row = dict(prefix=prefix.identity, arm=arm, request_id=request["request_id"], cache_hit=cached is not None,
                       phase=env.phase, finish_reason=response["finish_reason"],
                       input_tokens=response.get("input_tokens"), output_tokens=response.get("output_tokens"),
                       seconds=response.get("generation_seconds"), resource_tokens=spec.resource_budget - env.observe().remaining_tokens)
            results.append(row)
            save(run_dir / "summary.json", dict(status="DEVELOPMENT_GENERATION_ONLY", rows=results,
                api_cost_usd=0, judge_calls=0, training_updates=0, test_prefixes=0,
                caveat="six train calls are service smoke evidence, not quality effects or throughput for all study stages"))
            print(json.dumps(row), flush=True)
            if response["finish_reason"] == "exception":
                raise RuntimeError("local generation failed; raw exception saved, no automatic retry")
    save(OUT / "generation_smoke_pointer.json", dict(run_dir=str(run_dir), runtime_identity=generator.identity,
        summary_sha256=sha256_file(run_dir / "summary.json"), rows=len(results)))


if __name__ == "__main__":
    main()
