#!/usr/bin/env python3
"""P0/P1 + P2 status + P3-min. Offline, new output directory, no model calls.

Reads only explicit train/dev artifacts and already-opened development reviews.
The mixed train/test raw corpus is deliberately not opened. Source coverage is
reported, not fabricated. A local tokenizer is the only model-related loader.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import asdict
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import runpy
import sys
import time

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.rl1.schema import EpisodeSpec, Resource, HEADS, digest
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.resource_opportunity import capacity, candidate_capacity, lexical_overlap, measured_contrasts, dominated_same_input
from metacom_pm.rl1.temporal_evidence_ledger import TemporalEvidenceLedger, SourceTurn

BASE = "outputs/pm_rl1/completion_20260930_v2"


def unique_json(data):
    def pairs(items):
        result = {}
        for k,v in items:
            if k in result:
                raise ValueError(f"duplicate JSON key: {k}")
            result[k] = v
        return result
    return json.loads(data, object_pairs_hook=pairs)


class Inputs:
    def __init__(self, project):
        self.project = project
        self.hashes = {}

    def read(self, path):
        path = Path(path)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("project-relative explicit input required")
        # No recursive discovery of test/sealed source artifacts.
        if any("sealed" in s.lower() for s in path.parts):
            raise ValueError("sealed input forbidden")
        data = (self.project / path).read_bytes()
        self.hashes[str(path)] = hashlib.sha256(data).hexdigest()
        if path.suffix == ".jsonl":
            return [unique_json(line) for line in data.splitlines() if line.strip()]
        return unique_json(data)

    def frozen(self, directory, filename):
        freeze = self.read(directory + "/" + filename)
        for name, expected in freeze.get("files", {}).items():
            path = directory + "/" + name
            self.read(path)
            if self.hashes[path] != expected:
                raise ValueError(f"frozen artifact changed: {path}")
        return freeze

    def text(self, path):
        if Path(path).is_absolute() or ".." in Path(path).parts:
            raise ValueError("project-relative explicit text input required")
        data=(self.project/path).read_bytes()
        self.hashes[path]=hashlib.sha256(data).hexdigest()
        return data.decode()


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x") as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n")
    path.chmod(0o600)


def source_bank(inp):
    root = BASE + "/P3/common_evidence"
    inp.frozen(root, "input_freeze.json")
    evidence = inp.read(root + "/evidence_pool_private.json")
    mappings = inp.read(root + "/source_map_private.json")
    bank = {}
    for m in mappings:
        if m["split"] not in ("train", "dev"):
            raise ValueError("test source mapping forbidden")
        p = prefix_from_dict(m["prefix"])
        e = evidence[p.identity]
        if p.identity != m["prefix_identity"] or digest(e) != m["evidence_identity"]:
            raise ValueError("source identity mismatch")
        byid = {s["id"]:s for s in e["legal_past_sessions"]}
        for sm in m["source_map"]:
            if sm["rank"] >= p.cutoff_rank:
                raise ValueError("non-past evidence")
            s = byid[sm["blind_id"]]
            value = dict(owner=m["owner"], session=sm["session"], rank=sm["rank"], date=s["date"],
                         turns=[dict(index=i, speaker=t["role"], text=t["text"]) for i,t in enumerate(s["turns"])])
            key = (m["owner"], sm["session"])
            if key in bank and bank[key]["content"] != value:
                raise ValueError("conflicting duplicate source session")
            bank.setdefault(key, dict(content=value, origins=[]))["origins"].append(
                dict(path=root + "/evidence_pool_private.json", prefix_identity=p.identity, blind_id=sm["blind_id"]))
    return evidence, bank


def make_ledger(prefix, bank, provenance_identity):
    turns = []
    # Filter before indexing/derivation. Later prefix evidence is not a free input.
    for (owner, sid), item in bank.items():
        s = item["content"]
        if owner == prefix.owner_id and s["rank"] < prefix.cutoff_rank:
            turns.extend(SourceTurn(owner, sid, s["rank"], t["index"], t["speaker"], t["text"], s["date"])
                         for t in s["turns"])
    turns.extend(SourceTurn(prefix.owner_id, prefix.session_id, prefix.cutoff_rank, i, t.role, t.content, prefix.timestamp)
                 for i,t in enumerate(prefix.turns))
    return TemporalEvidenceLedger(prefix, turns, provenance_identity=provenance_identity)


def check_j1_package(inp, stage):
    """Rebuild the real prepared request bodies with public, provider-free code."""
    from metacom_pm.rl1 import diagnostic_engine as engine
    prep="outputs/pm_rl1/completion_preparation_20261022"
    requests={r["identity"]:r for r in inp.read(prep+"/primary_requests_private.json")}
    materials={r["key"]:r for r in inp.read(prep+"/stage_materials_private.json")}
    protocol_dir="outputs/pm_rl1/judge_selection_preparation_20261014_v1/feedback_source_evidence_preparation_20261022_v2"
    protocol=inp.read(protocol_dir+"/protocol.json")
    prompt=inp.text(protocol_dir+"/JOINT_PROMPT_EN.txt")
    if digest(protocol["config"])!=stage["single_config_identity"] or hashlib.sha256(prompt.encode()).hexdigest()!=stage["single_prompt_sha256"]:
        raise ValueError("J1 config/prompt identity changed")
    for mapping in stage["mapping"]:
        item=materials[mapping["material_key"]]
        messages,schema=engine.payload(item,"joint")
        messages[0]["content"]=prompt+'\nOUTPUT CONTRACT pmrl1-primary-full-schema-v1:\n'+json.dumps(schema,ensure_ascii=False)
        identity=digest(dict(config=protocol["config"],messages=messages,schema=schema))
        prepared=requests[mapping["request_identity"]]
        if (identity!=mapping["request_identity"] or prepared["wire_body"]!=engine.api_body(protocol["config"],messages)
                or prepared["local_schema"]!=schema or prepared["evidence_identity"]!=digest(item["evidence"])
                or prepared["response_identity"]!=digest(item["reply"])):
            raise ValueError("J1 prepared wire/schema/source binding changed")
    freeze=inp.read("outputs/pm_rl1/development_closeout_20261014_v1/measurement_freeze_DRAFT_current_v1.json")
    return dict(requests_rebuilt=len(requests),known_regression=sum(r["purpose"]=="known_regression" for r in materials.values()),
                new_development_reply_slots=sum(r["purpose"]!="known_regression" for r in materials.values()),
                public_engine_matches_prepared_wire=True,transport_called=False,
                historical_freeze_status=freeze["status"],historical_freeze_identity=freeze["identity"],
                historical_freeze_is_current_S_A_qualification=False)


def run(project, output, model):
    start = time.monotonic()
    inp = Inputs(project)
    contract = inp.read("docs/pm_rl1_completion_20260930_v2/execution_contract.json")
    if contract["invariants"]["max_gets"] != 4 or contract["invariants"]["resource_tokens"] != 2048:
        raise ValueError("research baseline changed")
    protected = inp.read("outputs/pm_rl1/root_cause_20261023_v4/PROTECTED_HASHES.json")
    for path, expected in protected.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest() != expected:
            raise ValueError("protected artifact differs from baseline")
    freeze = inp.frozen(BASE + "/P1", "renderer_freeze.json")
    active = inp.frozen(BASE + "/P1/interface_repair_v3", "renderer_freeze.json")
    closeout = inp.read(BASE + "/P1/phase_closeout.json")
    raw_specs = inp.read(BASE + "/P1/episode_specs_private.json")
    old_specs = inp.read(BASE + "/P1/old_delivery_specs_private.json")
    if len(raw_specs) != 114 or any(s["prefix"]["split"] not in ("train", "dev") for s in raw_specs):
        raise ValueError("expected 114 train/dev prefixes")
    evidence, bank = source_bank(inp)
    projections = inp.read(BASE + "/P1/source_projection_private.json")
    reviews = inp.read(BASE + "/P1/source_review_registry.json")
    review_map = {r["unit_id"]:r for r in reviews["mp"] + reviews["me"]}
    aliases = inp.read("data/paper1_public_rs/esconv_rs_exact_canonical_treatments_v1.jsonl")
    alias_map = {r["treatment_id"]:r for r in aliases}
    splits = {r["dialogue_id"]:r for r in inp.read("data/strategy/esconv_split_manifest_v1_5.jsonl")}
    for a in aliases:
        if hashlib.sha256(a["rendered_card_text"].encode()).hexdigest() != a["rendered_card_text_sha256"]:
            raise ValueError("RS text hash mismatch")
        if any(splits[s]["split"] != "train" or splits[s]["excluded_for_evoemo_overlap"] for s in a["source_dialogue_ids"]):
            raise ValueError("RS split/seed contamination")
    # Explicit local tokenizer only. No AutoModel/BGE/service import or fallback.
    from transformers import AutoTokenizer
    from metacom_pm.paper1.llama_tokenizer import LLAMA_TOKENIZER_JSON_SHA256
    token_hash = hashlib.sha256((model / "tokenizer.json").read_bytes()).hexdigest()
    if token_hash != LLAMA_TOKENIZER_JSON_SHA256:
        raise ValueError("tokenizer identity mismatch")
    tok = AutoTokenizer.from_pretrained(model, local_files_only=True, trust_remote_code=False)
    @lru_cache(maxsize=32768)
    def count(text):
        return len(tok.encode(text, add_special_tokens=False))
    config = unique_json((model / "config.json").read_bytes())
    renderer = DirectReplyRenderer(count_text=count,
        count_chat=lambda m:len(tok.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=digest(dict(tokenizer=token_hash, template=tok.chat_template)),
        context_limit=config["max_position_embeddings"])
    if renderer.identity != active["new_renderer_identity"] or renderer.identity != closeout["active_renderer_identity"]:
        raise ValueError("active renderer differs")
    specs = [EpisodeSpec(**dict(s,prefix=prefix_from_dict(s["prefix"]),
        inventory=tuple(tuple(Resource(**dict(r,source_ids=tuple(r["source_ids"]))) for r in h) for h in s["inventory"]))) for s in raw_specs]
    prior_cap = inp.read(BASE + "/P1/capacity_prefix_private.json")
    rows, capacities, ledger_stats = [], [], []
    ledger_seconds = 0
    for index,spec in enumerate(specs):
        p = spec.prefix
        plans = capacity(spec, renderer)
        if [r["reachable"] for r in plans] != prior_cap[index]["initial_plan_mask"]:
            raise ValueError("capacity changed from frozen P1")
        capacity_by_plan = {tuple(r["counts"]):r for r in plans}
        for old in prior_cap[index]["resource_costs"]:
            if capacity_by_plan[tuple(old["counts"])]["resource_tokens"] != old["tokens"]:
                raise ValueError("actual resource token cost changed")
        capacities.append(dict(index=index,prefix_identity=p.identity,owner=p.owner_id,split=p.split,plans=plans,
                               available_before_top4=projections[index]["projection"]["after"]))
        t0 = time.monotonic()
        ledger = make_ledger(p, bank, digest(dict(evidence=inp.hashes[BASE+"/P3/common_evidence/evidence_pool_private.json"],
                                                mapping=inp.hashes[BASE+"/P3/common_evidence/source_map_private.json"])))
        semantic_duplicates = Counter(digest(r.content) for h in spec.inventory for r in h)
        for h,items in enumerate(spec.inventory):
            for rank,r in enumerate(items,1):
                record = unique_json(r.content)
                original = old_specs[index]["inventory"][h][rank-1]
                if original["candidate_id"] != r.candidate_id or count(r.content) != r.raw_tokens:
                    raise ValueError("inventory/raw token binding changed")
                row = dict(index=index,prefix_identity=p.identity,owner=p.owner_id,split=p.split,head=r.head,
                    candidate_id=r.candidate_id,source_ids=r.source_ids,source_rank=r.source_rank,source_time=r.source_time,
                    content_identity=digest(r.content),raw_tokens=r.raw_tokens,
                    inventory_path=BASE+"/P1/episode_specs_private.json",inventory_pointer=f"/{index}/inventory/{h}/{rank-1}",
                    **candidate_capacity(spec,renderer,plans,h,rank),
                    raw_source_available=False,owner_time_metadata="verified",source_spans=[],source_check="unverified",
                    compiler_semantics="unverified",current_relevance="unverified",semantic_redundancy="unverified",
                    generator_uptake="unverified",matched_attribution="not_identified",
                    identical_content_candidates_in_prefix=semantic_duplicates[digest(r.content)],
                    source_review=review_map.get(r.source_ids[0]),training_label=False)
                diagnostic_text = record.get("past_report", record.get("full_source_conversation", record.get("historical_move", "")))
                row["lexical_overlap"] = lexical_overlap(diagnostic_text,p)
                if r.head == "RS":
                    a = alias_map[r.candidate_id]
                    if tuple(a["source_dialogue_ids"]) != r.source_ids or a["rendered_card_text"] != original["content"]:
                        raise ValueError("RS source alias binding mismatch")
                    row.update(source_check="canonical_alias_text_and_all_train_ids_verified",
                               raw_source_available=False,raw_source_scope="source_dialogue_spans_not_loaded",
                               source_split="train",evoemo_seed_exclusion="all_alias_ids_verified",
                               strategy_families=a["atomic_move_families"],applicability_conditions=None,cautions=None)
                else:
                    source = next((bank[(p.owner_id,sid)] for sid in r.source_ids if (p.owner_id,sid) in bank),None)
                    if source is not None:
                        s = source["content"]
                        if s["rank"] != r.source_rank or s["date"] != r.source_time:
                            raise ValueError("source rank/date mismatch")
                        row.update(raw_source_available=True,source_origins=source["origins"])
                        if r.head == "MS":
                            transcript = "\n".join(f"{t['speaker']}: {t['text']}" for t in s["turns"])
                            if transcript != record["full_source_conversation"] or transcript != original["content"]:
                                raise ValueError("MS full transcript mismatch")
                            row["source_check"] = "complete_raw_session_roles_and_text_verified"
                        else:
                            for e in record["evidence"]:
                                span = ledger.locate_quote(s['session'],e["speaker"],e["start_char"],e["end_char"],e["quote"])
                                if span["speaker"] != e["speaker"]:
                                    raise ValueError("speaker mismatch")
                                row["source_spans"].append(span)
                            row["source_check"] = "exact_spans_roles_and_offsets_verified"
                            row["original_turn_id_check"] = "unverified_raw_idx_not_same_namespace_as_blinded_ordinal"
                            row["original_declared_turn_indices"] = [e["turn_index"] for e in record["evidence"]]
                            row["ledger_claim_id"] = ledger.add_claim(candidate_id=r.candidate_id,head=r.head,
                                statement=record["past_report"],spans=row["source_spans"],
                                input_source_keys=[s["source_key"] for s in row["source_spans"]],
                                derivation_method="map_existing_frozen_resource_fields_no_new_extraction",
                                derivation_identity=digest(r.content),stage=record.get("action_stage","unknown"),
                                event_time=record.get("event_time"),outcome=record.get("observed_outcome"),
                                review_status="existing_source_review_not_human_gold" if row["source_review"] else "unverified")
                rows.append(row)
        exported = ledger.export()
        write(output/"ledgers_private"/(p.identity+".json"),exported)
        hits = ledger.lookup(p.turns[-1].content,limit=5)
        write(output/"queries_private"/(p.identity+".json"),dict(prefix_identity=p.identity,hits=hits,
                                                               primary_ranking_changed=False))
        ledger_seconds += time.monotonic()-t0
        ledger_stats.append(dict(prefix_identity=p.identity,identity=exported["identity"],
            source_turns=len(exported["source_turns"]),sessions=len(exported["session_directory"]),
            claims=len(exported["claims"]),relations=len(exported["relations"])))
    print(json.dumps(dict(stage="capacity_and_index_done",prefixes=len(specs),candidates=len(rows))),flush=True)
    pool_freeze = inp.frozen(BASE+"/P2/common_pool","input_freeze.json")
    slots = {r["slot_id"]:r for r in inp.read(BASE+"/P2/common_pool/slots_private.json")["rows"]}
    response_rows = []
    primary_by_messages = {}
    secondary_matches = []
    for kind in ("primary","secondary"):
        pointer = inp.read(BASE+f"/P2/common_pool/{kind}_generation_pointer.json")
        run_dir = BASE+"/P2/common_pool/generation/"+Path(pointer["run_dir"]).name
        summary = inp.read(run_dir+"/summary.json")
        for r in summary["rows"]:
            if r["split"] not in ("train","dev"):
                raise ValueError("test response forbidden")
            rid = r["request_id"]
            raw_path,req_path = run_dir+"/"+rid+".raw.json",run_dir+"/"+rid+".request.json"
            raw,req = inp.read(raw_path),inp.read(req_path)
            spec = specs[r["index"]]
            if (inp.hashes[raw_path] != r["raw_sha256"] or raw["request_id"] != rid
                    or digest({k:v for k,v in req.items() if k!="request_id"}) != rid
                    or raw["source_provenance_identity"] != digest(req["provenance"])
                    or raw["runtime_identity"] != req["executor_identity"]
                    or req["messages"] != renderer.messages(spec,tuple(r["counts"]))
                    or req["renderer_identity"] != renderer.identity
                    or req["provenance"]["prefix_identity"] != spec.prefix.identity
                    or req["provenance"]["retrieval_identity"] != spec.retrieval_identity
                    or req["provenance"]["inventory_identity"] != digest([[asdict(r) for r in head] for head in spec.inventory])
                    or req["provenance"]["canonical_counts"] != r["counts"]
                    or raw["finish_reason"] != "natural_stop" or not raw["text"]
                    or len(tok.apply_chat_template(req["messages"],tokenize=True,add_generation_prompt=True)) != r["input_tokens"]
                    or renderer.cost(spec,tuple(r["counts"])) != r["resource_tokens"]):
                raise ValueError("generation/source/renderer identity failed")
            row = dict(r,executor_identity=req["executor_identity"],renderer_identity=req["renderer_identity"],
                evidence_identity=digest(evidence[spec.prefix.identity]),response_identity=digest(raw["text"]),
                raw_path=raw_path,request_path=req_path,uptake="unverified",q=None,m=None)
            key = digest(req["messages"])
            if kind == "primary":
                if req["messages"] != slots[r["slot_id"]]["messages"]:
                    raise ValueError("original slot mismatch")
                primary_by_messages[key] = row
                response_rows.append(row)
            else:
                left = primary_by_messages[key]
                if left["executor_identity"] == row["executor_identity"]:
                    raise ValueError("secondary executor unexpectedly equal")
                secondary_matches.append(dict(primary_request_id=left["request_id"],secondary_request_id=rid,
                    primary_raw_path=left["raw_path"],secondary_raw_path=raw_path,prefix_identity=spec.prefix.identity,
                    counts=r["counts"],same_messages_identity=key,
                    same_reply=left["response_identity"]==row["response_identity"],quality_effect="unverified"))
    if len(response_rows)!=586 or len(secondary_matches)!=53:
        raise ValueError("pool coverage changed")
    contrasts = measured_contrasts(response_rows)
    matched = {(r["prefix_identity"],r["head"],r["rank"]) for r in contrasts}
    for r in rows:
        if (r["prefix_identity"],r["head"],r["rank"]) in matched:
            r["matched_attribution"]="matched_generation_available_quality_unverified"
    dominated = dominated_same_input(response_rows)
    old_audit = runpy.run_path(str(project/"docs/reviews/20261023/pm_rl1_root_cause/replay.py"))["audit"]
    prior_profile,prior_private = old_audit(project)
    if {r["request_id"] for r in dominated} != {r["request_id"] for r in prior_private["higher_cost_same_content_rows"]}:
        raise ValueError("same-content cost domination reconciliation failed")
    inp.hashes.update(prior_private["source_hashes"])
    # Existing opened human references; no new answer or semantic label is created.
    human = inp.read("outputs/pm_rl1/human_acceptance_20261014_v2/intake/development_comparisons_private.json")
    human_by_request=defaultdict(list)
    for pair in human:
        if pair["kind"] != "natural":continue
        for side in pair["canonical_sides"]:
            human_by_request[side["request_id"]].append(dict(pair_id=pair["pair_id"],contrast=pair["contrast"],
                human_direction=pair["human_direction"],judge_direction=pair["judge_direction"],
                canonical_request_ids=[s["request_id"] for s in pair["canonical_sides"]],
                qualification="old_opened_development_single_researcher_not_qm_gold"))
    for r in response_rows:r["existing_human_references"]=human_by_request[r["request_id"]]
    # Exact shared source spans, not a claim that two resources mean the same thing.
    span_users=defaultdict(list)
    for r in rows:
        for span in r["source_spans"]:
            span_users[(r["prefix_identity"],digest(span))].append(r["candidate_id"])
    shared_spans=[dict(prefix_identity=p,span_identity=s,candidate_ids=sorted(set(ids)),
                       semantic_equivalence="unverified") for (p,s),ids in span_users.items() if len(set(ids))>1]
    owner_summary=[]
    for owner in sorted({s.prefix.owner_id for s in specs}):
        rs=[r for r in rows if r["owner"]==owner]
        owner_summary.append(dict(owner=owner,split=rs[0]["split"],prefixes=len({r["prefix_identity"] for r in rs}),
            by_head={h:dict(candidates=sum(r["head"]==h for r in rs),
                           unreachable=sum(r["head"]==h and not r["reachable_in_any_plan"] for r in rs)) for h in HEADS}))
    case_register=inp.read("docs/reviews/20261023/pm_rl1_root_cause/CASE_REGISTER.json")
    for case in case_register["cases"]:
        data=(project/case["source"]).read_bytes()
        if hashlib.sha256(data).hexdigest()!=case["source_sha256"]:
            raise ValueError("historical qualitative evidence changed")
        inp.hashes[case["source"]]=case["source_sha256"]
    case_ledger=dict(status="EVIDENCE_LOCATIONS_NOT_NEW_SEMANTIC_LABELS",historical_cases=case_register["cases"],
        current_cases=[dict(id="MS_PREFIX0_RANK3",layer="retrieval/ranking",candidate_ledger_index=next(i for i,r in enumerate(rows) if r["index"]==0 and r["head"]=="MS" and r["rank"]==3),
                            finding="isolated 951 tokens fits; required ranked prefix 2152 exceeds 2048",semantic_value="unverified"),
                       dict(id="SAME_CONTENT_HIGHER_COST",layer="policy-learning",evidence_file="DOMINATED_PRIVATE.json",count=len(dominated),
                            finding="measured support set cost dominance; no q/m assigned"),
                       dict(id="TURN_ID_NAMESPACE",layer="source-compiler",finding="source idx and evaluator blinded ordinal must not be equated",disposition="audit adapter fixed; raw idx mapping still unverified")],
        per_candidate_file="CANDIDATE_LEDGER_PRIVATE.json",per_response_file="RESPONSE_LEDGER_PRIVATE.json",
        matched_contrast_file="MATCHED_CONTRASTS_PRIVATE.json",existing_human_file="EXISTING_HUMAN_REFERENCES_PRIVATE.json")
    stage = inp.read("outputs/pm_rl1/completion_preparation_20261022/STAGE_MATERIALS.json")
    budget = inp.read("outputs/pm_rl1/completion_preparation_20261022/BUDGET_SCENARIOS.json")
    j1 = dict(materials=stage,offline_wire_check=check_j1_package(inp,stage),budget_proposal=budget["stage"],requests_sent_this_run=0,
              qualification="NOT_ESTABLISHED",human_return_status="no_new_return_registered_in_current_project_state",
              new_stage_approval=False,production_adapter="not_validated_for_selected_full_S_A_stage",
              historical_308_are_not_independent_failures=True,
              exits=["select_S_then_frozen_qualification","select_A_then_frozen_qualification","close_candidate_then_B0_J2_decision"],
              new_capacity_if_259_calls=308+259,old_proposed_capacity_566_is_historical=True)
    stats = {}
    for head in HEADS:
        hr = [r for r in rows if r["head"]==head]
        stats[head]=dict(candidate_occurrences=len(hr),unique_candidate_ids=len({r["candidate_id"] for r in hr}),
            source_check_counts=dict(Counter(r["source_check"] for r in hr)),
            reachable=sum(r["reachable_in_any_plan"] for r in hr),
            individually_over_budget=sum(r["individually_over_budget"] for r in hr),
            preceding_or_combined_budget_block=sum(r["preceding_or_combined_budget_block"] for r in hr),
            matched_candidate_occurrences=sum(r["matched_attribution"]!="not_identified" for r in hr),
            semantic_compilation_unverified=len(hr),uptake_unverified=len(hr),
            first_candidate_blocked_prefixes=sum(r["rank"]==1 and not r["reachable_in_any_plan"] for r in hr),
            prefixes_with_any_blocked_candidate=len({r["prefix_identity"] for r in hr if not r["reachable_in_any_plan"]}),
            exact_literal_repetition=sum(r["lexical_overlap"]["exact_text_in_prefix"] for r in hr))
    profile = dict(status="OFFLINE_PACKAGE_COMPLETE_WITH_LIMITS",date="2026-10-29",
        scope=dict(prefixes=114,split=dict(Counter(s.prefix.split for s in specs)),
                   owners_by_split={split:len({s.prefix.owner_id for s in specs if s.prefix.split==split}) for split in ("train","dev")},
                   response_prefixes=42,primary_responses=586,secondary_matched_pairs=53,
                   new_model_loads=0,new_model_calls=0,training_updates=0,new_human_tasks=0,
                   audit_script_test_or_sealed_content_read=False,audit_script_mixed_raw_corpus_opened=False,
                   local_tokenizer_only=True,operator_mixed_corpus_output_incident=True),
        by_head=stats,total_reachable_plans=sum(r["reachable"] for c in capacities for r in c["plans"]),
        same_content_higher_cost=len(dominated),matched_add_one_contrasts=len(contrasts),
        same_reply_matched_contrasts=sum(r["same_reply"] for r in contrasts),
        shared_exact_source_span_groups=len(shared_spans),
        all_pool_and_renderer_bindings_verified=True,rs_aliases_checked=len(aliases),
        rs_source_split_and_seed_exclusion_all_ids=True,rs_near_duplicate_leakage="unverified",
        exact_sources=dict(legal_history_sessions=len(bank),source_complete_prefixes=42,
                           missing_source_candidate_occurrences=sum(r["head"]!="RS" and not r["raw_source_available"] for r in rows)),
        index=dict(instances=len(ledger_stats),claims=sum(r["claims"] for r in ledger_stats),
                   semantic_relations=0,new_summaries=0,new_RS_conditions=0,primary_environment_unchanged=True),
        timing=dict(total_seconds=time.monotonic()-start,index_build_export_query_seconds=ledger_seconds,
                    scope="offline CPU + local tokenizer + filesystem; not model/online latency"),
        original_root_audit_reproduced=True,independent_owner_sample_size_not_prefix_count=True,
        limitations=["Only frozen top4 ranks persisted; beyond-top4 BGE ranks/vectors not reconstructed.",
                     "42 legal evidence packages reused; missing raw source coverage stays unverified.",
                     "Raw source turn idx is not the blinded ordinal; quotes matched uniquely, raw idx mapping unverified.",
                     "Operator head command emitted mixed raw corpus before repair; exposure incident disclosed separately, not used by audit/index.",
                     "Exact quote checks do not certify entailment, relevance, adoption or quality.",
                     "All new indices remain construction-only; no active rank, resource, prompt or reward change.",
                     "No newly returned human labels or qualified feedback; no natural PM training."])
    for name,value in [("PROFILE.json",profile),("CANDIDATE_LEDGER_PRIVATE.json",rows),
                       ("CAPACITY_PRIVATE.json",capacities),("RESPONSE_LEDGER_PRIVATE.json",response_rows),
                       ("MATCHED_CONTRASTS_PRIVATE.json",contrasts),("DOMINATED_PRIVATE.json",dominated),
                       ("EXECUTOR_PAIRS_PRIVATE.json",secondary_matches),("INDEX_IDENTITIES.json",ledger_stats),
                       ("J1_READINESS.json",j1),("EXISTING_HUMAN_REFERENCES_PRIVATE.json",human),
                       ("CASE_LEDGER_PRIVATE.json",case_ledger),("SHARED_SPANS_PRIVATE.json",shared_spans),
                       ("OWNER_SUMMARY.json",owner_summary),
                       ("REPRODUCED_ROOT_PROFILE.json",prior_profile),("INPUT_HASHES_PRIVATE.json",inp.hashes)]:
        write(output/name,value)
    code_paths=[Path(__file__).relative_to(project),Path("src/metacom_pm/rl1/temporal_evidence_ledger.py"),
                Path("src/metacom_pm/rl1/resource_opportunity.py"),Path("src/metacom_pm/rl1/schema.py"),
                Path("src/metacom_pm/rl1/render.py"),Path("src/metacom_pm/rl1/representation.py"),
                Path("src/metacom_pm/rl1/representation_direct.py"),Path("src/metacom_pm/rl1/diagnostic_engine.py")]
    write(output/"SOURCE_CODE_HASHES.json",{str(p):hashlib.sha256((project/p).read_bytes()).hexdigest() for p in code_paths})
    for path,expected in protected.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=expected:
            raise ValueError("protected artifact modified during audit")
    for path,expected in inp.hashes.items():
        if hashlib.sha256((project/path).read_bytes()).hexdigest()!=expected:
            raise ValueError("audit input modified during run")
    write(output/"PROTECTED_HASHES.json",protected)
    write(output/"OUTPUT_MANIFEST.json",{str(p.relative_to(output)):hashlib.sha256(p.read_bytes()).hexdigest()
                                        for p in sorted(output.rglob("*.json"))})
    return profile


if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project",type=Path,default=PROJECT)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--tokenizer-dir",type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():raise SystemExit("New output directory required; never overwrite prior runs")
    args.output.mkdir(parents=True,mode=0o700)
    try:
        profile=run(args.project.resolve(),args.output,args.tokenizer_dir)
    except Exception as exc:
        write(args.output/"FAILURE.json",dict(status="FAILED_CLOSED",type=type(exc).__name__,message=str(exc),
                                             model_calls=0,training_updates=0))
        raise
    print(json.dumps(profile,ensure_ascii=False))
