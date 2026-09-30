#!/usr/bin/env python3
"""Freeze 12 train pilot inputs before outcomes; audit exact-source exposure.

One top-ranked resource per prefix, RS/MP/MS/ME cyclically (3 each). If that
head is unavailable or illegal, record unavailable; never select by output.
This development pilot does not certify a semantically clean final test.
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
from metacom_pm.rl1.evidence import legal_evidence, prefix_from_dict

ENGINEERING = PROJECT / "outputs/pm_rl1/engineering_20260928_v1"
PREP = PROJECT / "outputs/pm_rl1/evaluation_preparation_20260928_v1"
OUT = PROJECT / "outputs/pm_rl1/measurement_pilot_20260928_v1"
MODEL = Path("/opt/tokkio-data0/tokkio_models/huggingface/hub/models--NousResearch--Meta-Llama-3.1-8B-Instruct/snapshots/d10aef7999a2b5ba950ab3974312feeedbfe0b77")


def save(name, obj):
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / name
    text = json.dumps(obj, ensure_ascii=False, indent=2) + "\n"
    if path.exists():
        raise RuntimeError("frozen output exists: " + str(path))
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)


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
    roster = json.loads((PREP / "pilot_roster_private_DRAFT.json").read_text())["rows"]
    probes = tuple(prefix_from_dict(r["prefix"]) for r in roster)
    assert len(probes) == 12 and len({p.owner_id for p in probes}) == 12 and all(p.split == "train" for p in probes)
    # Exact transcript-family descendants remain a construction-domain flag.
    shared = census["shared_transcript_groups"]
    old_pair_path = PROJECT / "data/paper1_authority/paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"
    old_pairs = list(iter_jsonl(old_pair_path))
    exposure_rows = []
    for p in prefixes:
        user = user_map[p.owner_id]
        refs = [r for r in old_pairs if r["owner_or_dialogue_group"] == p.owner_id]
        full_session_exposures = []
        for session in user.sessions:
            rendered = "\n".join(f"{t.role}: {t.content}" for t in session.turns)
            matches = [r["base_pair_id"] for r in refs if rendered in r.get("reference_material", "")]
            if matches:
                full_session_exposures.append(dict(session=session.session_id, rank=session.chronological_rank,
                    relation="past" if session.chronological_rank < p.cutoff_rank else "current" if session.chronological_rank == p.cutoff_rank else "future",
                    exact_full_transcript_in_old_reference_pair_ids=matches))
        shared_ancestors = [g for g in shared if any(r["owner"] == p.owner_id and r["rank"] <= p.cutoff_rank for r in g)]
        exposure_rows.append(dict(prefix=p.identity, owner=p.owner_id, split=p.split,
            exact_shared_family_or_descendant=bool(shared_ancestors), shared_ancestors=shared_ancestors,
            full_session_exposures=full_session_exposures,
            old_reference_pair_ids=[r["base_pair_id"] for r in refs],
            current_complete_session_previously_in_reference=any(x["relation"] == "current" for x in full_session_exposures)))
    save("source_exposure_audit.json", dict(status="EXACT_SOURCE_AUDIT_COMPLETE_SEMANTIC_EXPOSURE_NOT_CERTIFIED",
        scope="exact complete transcripts in 80 prior development references; not every historical prompt or semantic fact paraphrase",
        old_pair_sha256=sha256_file(old_pair_path), source_sha256=sha256_file(source),
        shared_groups=shared, rows=exposure_rows,
        conclusions=["pilot uses train owners only and excludes known shared-session descendants",
                     "new parameter holdout does not imply research-team-unseen data",
                     "all final-test exposure exclusions and semantic fact families require a separate freeze"],
        declared_test_status="PRIOR_EXPOSED_BENCHMARK_NOT_UNTOUCHED_TEST"))
    assert not any(r["exact_shared_family_or_descendant"] for r in exposure_rows if r["prefix"] in {p.identity for p in probes})
    evidence_rows, keys = [], []
    for p in probes:
        e, key = legal_evidence(p, user_map[p.owner_id])
        evidence_rows.append(dict(prefix_identity=p.identity, evidence=e, evidence_identity=digest(e)))
        keys.append(key)
    save("legal_evidence_private.json", evidence_rows)
    save("coordinator_only/evidence_source_map.json", keys)
    save("input_freeze.json", dict(status="PILOT_INPUTS_FROZEN_BEFORE_OUTCOMES",
        roster_sha256=sha256_file(PREP / "pilot_roster_private_DRAFT.json"),
        sources={str(source): sha256_file(source), str(units_path): sha256_file(units_path)},
        rows=roster, on_rule="one GET: pilot index 1..12 cycles RS, MP, MS, ME; unavailable/illegal is missing, no fallback",
        budget=2048, budget_scope="pilot only; formal budget awaits full capacity census",
        repeated_draw_rule="condition index (pilot_index-1)%4, separate predeclared stochastic draw, no cache collapse",
        generator_draw="greedy-development-draw-0", model_output_cap=None,
        control_rule="OFF as original; at most one source-verifiable factual edit; style must preserve semantics; invalid controls remain missing",
        independent_review_rule="first 6 OFF/ON; next 3 original/damage; last 3 original/style, fixed blind order"))
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
    for index, (p, group, query) in enumerate(zip(probes, candidates, query_vectors)):
        inventory = ranked_memory(p, group, vectors, query)
        scores = rs_vecs @ np.asarray(query, dtype=np.float32)
        order = sorted(range(len(aliases)), key=lambda i: (-float(scores[i]), aliases[i]["treatment_id"]))
        inventory["RS"] = tuple(Resource(aliases[i]["treatment_id"], "RS", aliases[i]["rendered_card_text"],
            float(scores[i]), counter(aliases[i]["rendered_card_text"]), None, None, None, "not_applicable",
            tuple(aliases[i]["source_dialogue_ids"])) for i in order)
        spec = EpisodeSpec(p, tuple(inventory[h] for h in HEADS), digest(retrieval),
                           "PILOT_UNBOUND_X", "MEASUREMENT_CANDIDATE_ONLY", "greedy-development-draw-0")
        # Private inventories include all candidates. Public observations are
        # saved separately to demonstrate the whitelist boundary.
        specs.append(asdict(spec))
        for budget in (1024, 2048, 4096):
            env = ResourceEnv(replace(spec, resource_budget=budget), render)
            capacities.append(dict(prefix=p.identity, plain_prefix_tokens=counter(p.query), budget=budget,
                feasible_plans=sum(env.observe().initial_plan_mask), initial_action_mask=env.observe().action_mask,
                inventory_counts=[len(x) for x in spec.inventory]))
        env = ResourceEnv(spec, render)
        observations = [asdict(env.observe())]
        # One preassigned head per prefix, three prefixes per head.
        assigned_action = index % 4 + 1
        legal = env.observe().action_mask[assigned_action]
        for action in (assigned_action,):
            if env.observe().action_mask[action]:
                env.step(action, expected_state_hash=env.state_hash)
                observations.append(asdict(env.observe()))
        env.step(0, expected_state_hash=env.state_hash)
        restored = ResourceEnv.restore(spec, render, json.loads(json.dumps(env.snapshot())))
        assert restored.state_hash == env.state_hash
        traces.append(dict(prefix=p.identity, pilot_index=index+1, assigned_action=assigned_action,
                           on_available=legal, observations=observations, snapshot=env.snapshot(),
                           pending_request=env.generation_request()))
    save("episode_specs_private.json", specs)
    save("mechanical_traces.json", traces)
    save("capacity_probe.json", capacities)
    save("retrieval_manifest.json", dict(**retrieval, pilot_input_freeze_sha256=sha256_file(OUT / "input_freeze.json"), renderer_identity=render.identity,
           elapsed_seconds=time.monotonic() - started, script_sha256=sha256_file(Path(__file__)),
           artifact_sha256={f: sha256_file(OUT / f) for f in ("episode_specs_private.json", "mechanical_traces.json", "capacity_probe.json", "legal_evidence_private.json", "source_exposure_audit.json", "input_freeze.json")},
           outcome_calls=0, api_cost_usd=0, limitations=census["pending"]))
    print(json.dumps(dict(stage="done", seconds=time.monotonic() - started, capacities=capacities)), flush=True)


if __name__ == "__main__":
    main()
