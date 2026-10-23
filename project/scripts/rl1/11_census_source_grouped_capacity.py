#!/usr/bin/env python3
"""Outcome-free, full rendered budget census for the 162 source-grouped prefixes.

No generation or scoring. Retains B=2048 as predeclared in the user plan.
"""
from collections import defaultdict
from dataclasses import asdict, replace
import json
from pathlib import Path
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import iter_jsonl, sha256_file, sha256_text
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units
from metacom_pm.paper1.llama_tokenizer import build_llama_token_counter
from metacom_pm.paper1.embeddings.bge_m3 import BgeM3Encoder
from metacom_pm.paper1.rs.strategy_bank import build_strategy_source_catalog
from metacom_pm.rl1.data import build_prefixes, as_of_memory, ranked_memory
from metacom_pm.rl1.env import ResourceEnv
from metacom_pm.rl1.render import Renderer
from metacom_pm.rl1.schema import EpisodeSpec, Resource, HEADS, digest
from metacom_pm.rl1.evidence import prefix_from_dict

ENGINEERING = PROJECT / "outputs/pm_rl1/engineering_20260928_v1"
OUT = PROJECT / "outputs/pm_rl1/source_and_capacity_20260928_v1"
MODEL = Path("/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77")


def save(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / name).write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n")


def main():
    import numpy as np
    import torch
    from transformers import AutoTokenizer, AutoConfig
    started = time.monotonic()
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise RuntimeError("bind exactly one GPU")
    if torch.cuda.mem_get_info(0)[0] < 6 * 1024 ** 3:
        raise RuntimeError("BGE preflight needs 6 GiB free")
    source = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
    units_path = PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl"
    users = load_sanitized_runtime_users(source)
    units = load_accepted_multi_view_units(units_path, users=users)
    user_map = {u.owner_id: u for u in users}
    unit_map = defaultdict(list)
    for u in units:
        unit_map[u.owner_id].append(u)
    prefixes, census = build_prefixes(users)
    counter = build_llama_token_counter(MODEL / "tokenizer.json")
    tokenizer = AutoTokenizer.from_pretrained(MODEL, local_files_only=True)
    render = Renderer(count_text=counter,
        count_chat=lambda m: len(tokenizer.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=sha256_file(MODEL / "tokenizer.json"),
                                       template=tokenizer.chat_template)),
        context_limit=AutoConfig.from_pretrained(MODEL, local_files_only=True).max_position_embeddings)
    probes = tuple(prefix_from_dict(r) for r in json.loads((OUT / "prefixes_private.json").read_text()))
    assert len(probes) == 162
    candidates = [as_of_memory(p, user=user_map[p.owner_id], units=unit_map[p.owner_id], token_counter=counter)
                  for p in probes]
    unique = {c.candidate_id: c for group in candidates for cs in group.values() for c in cs}

    cards = build_strategy_source_catalog(esconv_path=PROJECT / "data/external/ESConv.json",
                  split_manifest_path=PROJECT / "data/strategy/esconv_split_manifest_v1_5.jsonl")
    card_map = {c.card_id: c for c in cards}
    alias_path = PROJECT / "data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl"
    aliases = list(iter_jsonl(alias_path))
    rs_texts = []
    all_seed_ids = {f"esconv_{int(s.session_id[3:]):04d}" for u in users for s in u.sessions
                    if s.session_id.startswith("esc") and s.session_id[3:].isdigit()}
    for a in aliases:
        if all_seed_ids.intersection(a["source_dialogue_ids"]):
            raise ValueError("RS source overlaps EvoEmo seed")
        text = card_map[a["representative_source_card_id"]].retrieval_text + "\n" + a["rendered_card_text"]
        if sha256_text(text) != a["representative_retrieval_text_sha256"]:
            raise ValueError("RS retrieval-document identity mismatch")
        if sha256_text(a["rendered_card_text"]) != a["rendered_card_text_sha256"]:
            raise ValueError("RS treatment identity mismatch")
        rs_texts.append(text)
    print(json.dumps(dict(stage="encode", prefixes=len(probes), memory_documents=len(unique), rs_documents=len(aliases))), flush=True)
    encoder = BgeM3Encoder()
    runtime = asdict(encoder.runtime_identity)
    retrieval = dict(protocol="pm-rl1-full-prefix-bge-v1", binding=asdict(encoder.binding), runtime=runtime,
                     rs_alias_sha256=sha256_file(alias_path), query="entire public current-session prefix",
                     tie_break="candidate_id", probe_only=True)
    embedding_cache = ENGINEERING / ("rs_vectors_" + digest(retrieval) + ".npy")
    if embedding_cache.exists():
        bound = json.loads(embedding_cache.with_suffix(".json").read_text())
        if bound != dict(texts_sha256=digest(rs_texts), vectors_sha256=sha256_file(embedding_cache)):
            raise ValueError("RS embedding-cache integrity mismatch")
        rs_vecs = np.load(embedding_cache, allow_pickle=False)
    else:
        rs_vecs = np.asarray(encoder.encode(rs_texts), dtype=np.float32)
        np.save(embedding_cache, rs_vecs, allow_pickle=False)
        embedding_cache.with_suffix(".json").write_text(json.dumps(dict(
            texts_sha256=digest(rs_texts), vectors_sha256=sha256_file(embedding_cache))))
    ids = sorted(unique)
    vectors = dict(zip(ids, encoder.encode([unique[i].content for i in ids])))
    query_vectors = encoder.encode([p.query for p in probes])
    specs, capacities, traces = [], [], []
    for p, group, query in zip(probes, candidates, query_vectors):
        inventory = ranked_memory(p, group, vectors, query)
        scores = rs_vecs @ np.asarray(query, dtype=np.float32)
        order = sorted(range(len(aliases)), key=lambda i: (-float(scores[i]), aliases[i]["treatment_id"]))
        inventory["RS"] = tuple(Resource(aliases[i]["treatment_id"], "RS", aliases[i]["rendered_card_text"],
            float(scores[i]), counter(aliases[i]["rendered_card_text"]), None, None, None, "not_applicable",
            tuple(aliases[i]["source_dialogue_ids"])) for i in order)
        spec = EpisodeSpec(p, tuple(inventory[h] for h in HEADS), digest(retrieval),
                           "ENGINEERING_UNBOUND_X", "MEASUREMENT_NOT_FROZEN", "greedy-development-draw-0")
        # Private inventories include all candidates. Public observations are
        # saved separately to demonstrate the whitelist boundary.
        # Capacity-only pass: keep no model outputs or giant duplicate inventories.
        for budget in (1024, 2048, 4096):
            env = ResourceEnv(replace(spec, resource_budget=budget), render)
            capacities.append(dict(prefix=p.identity, plain_prefix_tokens=counter(p.query), budget=budget,
                feasible_plans=sum(env.observe().initial_plan_mask), initial_action_mask=env.observe().action_mask,
                inventory_counts=[len(x) for x in spec.inventory]))
    save("capacity_probe.json", capacities)
    save("retrieval_manifest.json", dict(**retrieval, renderer_identity=render.identity,
           elapsed_seconds=time.monotonic() - started, script_sha256=sha256_file(Path(__file__)),
           artifact_sha256={f: sha256_file(OUT / f) for f in ("prefixes_private.json", "capacity_probe.json", "source_exposure_v2.json")},
           outcome_calls=0, api_cost_usd=0, resource_budget=2048,
           budget_decision="retain predeclared B=2048; do not tune using pilot scores",
           limitations=["source grouping excludes exact shared descendants; semantic cross-family links remain an audit limitation", "prior-exposed test is not sealed"]))
    print(json.dumps(dict(stage="done", seconds=time.monotonic() - started, rows=len(capacities))), flush=True)


if __name__ == "__main__":
    main()
