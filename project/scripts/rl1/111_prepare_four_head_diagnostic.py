#!/usr/bin/env python3
"""Offline preparation only. Read opened train/dev; never open test or credentials."""
from collections import Counter, defaultdict
from dataclasses import asdict, replace
from decimal import Decimal
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.rl1.schema import EpisodeSpec, Resource, digest
from metacom_pm.rl1.evidence import prefix_from_dict, evidence_turns
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.diagnostic_scope import DIAGNOSTIC, DISPOSITIONS, AMBIGUITY_TYPES, VERSION
from metacom_pm.rl1.diagnostic_session import save_once, read
from metacom_pm.rl1.observation_features import PlanAwareFeatureEncoder
from metacom_pm.rl1.representation_direct import DirectReplyRenderer
from metacom_pm.rl1.bound_generation import BoundResourceEnv
from metacom_pm.paper1.embeddings.bge_m3 import FROZEN_BGE_M3_BINDING

BASE = PROJECT / "outputs/pm_rl1/judge_selection_preparation_20261014_v1"
Q = PROJECT / "outputs/pm_rl1/completion_20260930_v2"
OUT = BASE / "four_head_diagnostic_preparation_20261020_v1"
LEDGER = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
HISTORY = ("live_runs", "paired_diagnostic_runs", "action_stage_runs",
           "reward_noise_runs", "anchor_calibration_runs")


def sha(p):
    h = hashlib.sha256()
    with Path(p).open("rb") as f:
        for block in iter(lambda:f.read(1024*1024), b""):
            h.update(block)
    return h.hexdigest()


def spec_from(raw):
    return EpisodeSpec(**dict(raw, prefix=prefix_from_dict(raw["prefix"]),
        inventory=tuple(tuple(Resource(**dict(r, source_ids=tuple(r["source_ids"])))
                              for r in rows) for rows in raw["inventory"])))


def prepare():
    os.umask(0o077)
    OUT.mkdir(parents=True, exist_ok=True, mode=0o700)
    OUT.chmod(0o700)
    starts = [p for d in HISTORY for p in (BASE / d).rglob("*.started.json")
              if "management" not in p.parts]
    if 66 + len(starts) != 225:
        raise ValueError("actual score count changed; preserve history and reconcile")
    prior = read(BASE / "anchor_calibration_preparation_20261020_v1/protocol.json")
    events = [json.loads(x) for x in LEDGER.read_text().splitlines()]
    reservations = {x["reservation_id"]:x for x in events if x["event"] == "RESERVED"}
    settlements = {x["reservation_id"]:x for x in events if x["event"] == "SETTLED"}
    trial_id = prior["financial_baseline"]["financial_trial_identity"]
    def accounted(ids):
        return sum((Decimal(settlements[k]["actual_cost_usd"]) if k in settlements else
                    Decimal(reservations[k]["maximum_cost_usd"]) for k in ids), Decimal(0))
    total = Decimal(".03079930") + accounted(reservations)
    trial = accounted([k for k, v in reservations.items() if v.get("selection_trial") == trial_id])
    if set(reservations) - set(settlements):
        raise ValueError("unsettled prior liability; do not reset")
    originals = {str(p):sha(p) for p in starts}
    for d in HISTORY:
        originals.update({str(p):sha(p) for p in (BASE / d).rglob("STOP.json")})
    originals[str(LEDGER)] = sha(LEDGER)
    save_once(OUT / "provenance/history_before.json", originals)
    executor = read(Q / "P2/executor_freeze.json")
    runtime = executor["primary_runtime"]
    if ({p:importlib.metadata.version(p) for p in runtime["packages"]} != runtime["packages"]
            or importlib.metadata.version("peft") != runtime["adapter"]["peft_version"]):
        raise ValueError("use existing paper1-py311 plus original SFT vendor; no dependency substitution")
    slots = read(Q / "P2/common_pool/slots_private.json")["rows"]
    # Bind by full prefix identity, never assume that display indices are zero based.
    all_specs = [spec_from(x) for x in read(Q / "P1/episode_specs_private.json")]
    assert all(x.prefix.split in ("train", "dev") for x in all_specs)
    by_prefix = {x.prefix.identity:x for x in all_specs}
    pool_ids = {x["prefix_identity"] for x in slots}
    owners = defaultdict(list)
    for pid in pool_ids:
        s = by_prefix[pid]
        owners[(s.prefix.split, s.prefix.owner_id)].append(pid)
    for key in owners:
        owners[key].sort(key=lambda p:digest(("four-head-diagnostic-v1", p)))
    train_owners = sorted(o for split, o in owners if split == "train")
    dev_owners = sorted(o for split, o in owners if split == "dev")
    train = [owners["train", o][j] for j in range(2) for o in train_owners]
    dev = [owners["dev", o][j] for j in range(2) for o in dev_owners]
    assert len(train) == 24 and len(dev) == 6 and len(train_owners) == 12 and len(dev_owners) == 3
    repeated_owners = sorted(train_owners, key=lambda o:digest(("repeat-owner", o)))[:8]
    schedule = train + [owners["train", o][0] for o in repeated_owners]
    evidence = read(Q / "P3/common_evidence/evidence_pool_private.json")
    selected = train + dev
    for pid in selected:
        evidence_turns(evidence[pid])
        assert evidence[pid]["current_prefix"] == [
            dict(id=f"C:T{i:03d}", role=t.role, text=t.content)
            for i, t in enumerate(by_prefix[pid].prefix.turns)]
    # Exact prior baseline prompt (revision 2); calibrated examples are NOT included.
    payload = read(next((BASE / "anchor_calibration_preparation_20261020_v1/payloads").glob("*baseline.json")))
    prompt = payload["messages"][0]["content"]
    system_path = OUT / "joint_system_prompt.json"
    save_once(system_path, dict(content=prompt, provenance="unchanged revision-2 baseline"))
    measurement_id = digest(dict(config=prior["config"], system=prompt,
        final_interface=prior["final_interface"], purpose=DIAGNOSTIC, version=VERSION))
    bge_binding = asdict(FROZEN_BGE_M3_BINDING)
    bge_runtime = dict(torch_version=importlib.metadata.version("torch"),
        sentence_transformers_version=importlib.metadata.version("sentence-transformers"),
        weights_sha256_verified=bge_binding["model_safetensors_sha256"])
    # This is an expected identity. Actual weights/runtime must still be checked at load.
    text_identity = digest(dict(binding=bge_binding, runtime=bge_runtime))
    encoder = PlanAwareFeatureEncoder(None, embedding_dimension=1024, text_encoder_identity=text_identity)
    specs = {pid:replace(by_prefix[pid], executor_identity=runtime["identity"],
        judge_identity=measurement_id, draw_identity=executor["terminal_draw_identity"]) for pid in selected}
    from transformers import AutoTokenizer
    tokenizer = AutoTokenizer.from_pretrained(runtime["model_dir"], local_files_only=True)
    if digest(tokenizer.chat_template) != runtime["chat_template_sha256"]:
        raise ValueError("frozen tokenizer chat template changed")
    renderer = DirectReplyRenderer(count_text=lambda t:len(tokenizer.encode(t, add_special_tokens=False)),
        count_chat=lambda m:len(tokenizer.apply_chat_template(m, tokenize=True, add_generation_prompt=True)),
        tokenizer_identity=read(Q / "P1/renderer_freeze.json")["tokenizer_identity"],
        context_limit=runtime["policy"]["context_limit"])
    if renderer.identity != executor["renderer_identity"]:
        raise ValueError("frozen renderer mismatch")
    bge_dir = Path("/home/tokkio/.cache/huggingface/hub/models--BAAI--bge-m3/snapshots") / bge_binding["revision"]
    bt = AutoTokenizer.from_pretrained(bge_dir, local_files_only=True)
    sizes, plan_sizes = [], []
    for pid, spec in specs.items():
        env = BoundResourceEnv(spec, renderer)
        o = env.observe()
        sizes.append(len(bt.encode("\n".join(f"{t.role}: {t.content}" for t in o.current_prefix))))
        for head, rows in zip(("RS", "MP", "MS", "ME"), spec.inventory):
            for rank, resource in enumerate(rows[:4], 1):
                # Encoder uses only currently acquired text; this offline length
                # check admits future observations without exposing them to actor.
                text = json.dumps(dict(head=head, rank=rank, source_time=resource.source_time,
                                       content=resource.content), ensure_ascii=False, sort_keys=True)
                sizes.append(len(bt.encode(text)))
        plan_sizes.append(sum(o.initial_plan_mask))
        if pid in dev and not o.action_mask[1]:
            raise ValueError("preselected FixedRS1 unreachable; no replacement case")
    if max(sizes) > 8192:
        raise ValueError("BGE would truncate an admitted observation")
    generation_dir = Path(read(Q / "P2/common_pool/primary_generation_pointer.json")["run_dir"])
    cache = {}
    summary = read(generation_dir / "summary.json")["rows"]
    for row in summary:
        rid = row["request_id"]
        reqpath = generation_dir / (rid + ".request.json")
        rawpath = generation_dir / (rid + ".raw.json")
        req, raw = read(reqpath), read(rawpath)
        if (sha(rawpath) != row["raw_sha256"] or raw["request_id"] != rid
                or digest({k:v for k,v in req.items() if k != "request_id"}) != rid
                or raw["finish_reason"] != "natural_stop"
                or raw["runtime_identity"] != runtime["identity"]):
            raise ValueError("historical generation cache invalid")
        cache[rid] = dict(request_path=str(reqpath), request_sha256=sha(reqpath),
                          raw_path=str(rawpath), raw_sha256=sha(rawpath))
    fixed_cache = {}
    for pid in selected:
        env = BoundResourceEnv(specs[pid], renderer)
        env.step(0, expected_state_hash=env.state_hash)
        req = env.generation_request()
        assert req["request_id"] in cache
        fixed_cache[pid] = req["request_id"]
        if pid in dev:
            fixed = BoundResourceEnv(specs[pid], renderer)
            fixed.step(1, expected_state_hash=fixed.state_hash)
            fixed.step(0, expected_state_hash=fixed.state_hash)
            assert fixed.generation_request()["request_id"] in cache
    manifest, batches, dev_phases = {}, [[], []], {"initial_dev":[], "post_dev":[]}
    for i, pid in enumerate(schedule):
        tid = f"train_{i+1:02d}"
        manifest[tid] = dict(prefix_identity=pid, split="train", spec_identity=specs[pid].identity,
            evidence_identity=digest(evidence[pid]), condition="sampled_policy", planned_repeat=i >= 24)
        batches[i//16].append(tid)
    for i, pid in enumerate(dev):
        for condition, phase in (("policy_initial", "initial_dev"), ("FixedRS1", "initial_dev"),
                                 ("policy_post32", "post_dev")):
            tid = f"dev_{i+1:02d}_{condition}"
            manifest[tid] = dict(prefix_identity=pid, split="dev", spec_identity=specs[pid].identity,
                evidence_identity=digest(evidence[pid]), condition=condition, planned_repeat=False)
            dev_phases[phase].append(tid)
    data = dict(specs={p:asdict(s) for p,s in specs.items()},
                evidence={p:evidence[p] for p in selected}, generation_cache=cache)
    save_once(OUT / "inputs_private.json", data)
    limits = dict(judge_calls=80, cumulative=305, selection_acceptance_capacity=369,
        new_generations=44, stage_usd="3", trial_usd="4.25", shared_usd="20",
        native_single_reserve_usd="0.786432", management_requests={"models":1, "user/balance":1},
        policy_updates=2, train_trajectories=32, max_gpu_loads=4, idle_wait_seconds_per_load=300,
        final_evaluation_planning_hold_usd="12")
    approval_scope = dict(credential_process_read_authorized=True,
        official_account_management=limits["management_requests"],
        outbound_scope=["unchanged revision-2 system prompt and new-AI identity",
                        "one complete reply and stable units", "corresponding full legal sources and stable IDs"],
        no_human_or_coordinator_annotations_sent=True, gpu_uuid="GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4",
        accepted_research_change="weak_proxy_random_init_diagnostic_only",
        approved_ambiguity_categories=list(AMBIGUITY_TYPES),
        final_evaluation_hold_usd="12")
    # The frozen G environment intentionally has no jsonschema. Reuse the
    # existing judge environment through local IPC instead of installing into G.
    import subprocess
    judge_python = "/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python"
    command = "import json,importlib.metadata as m; print(json.dumps({p:m.version(p) for p in ['jsonschema','referencing','rpds-py','attrs']}))"
    env = dict(os.environ, PYTHONPATH=str(PROJECT / "src"), CUDA_VISIBLE_DEVICES="")
    observed = subprocess.run([judge_python, "-c", command], env=env, check=True,
                              capture_output=True, text=True, timeout=30)
    judge_packages = json.loads(observed.stdout)
    # All files are bound before real execution. No key file is part of a manifest.
    code = list((PROJECT / "src/metacom_pm/rl1").glob("*.py")) + [
        PROJECT / "src/metacom_pm/paper1/embeddings/bge_m3.py",
        PROJECT / "scripts/rl1/92_run_p2_common_pool.py",
        PROJECT / "scripts/rl1/111_prepare_four_head_diagnostic.py",
        PROJECT / "scripts/rl1/112_run_four_head_diagnostic.py",
        BASE / "selection.py", BASE / "adapters.py", BASE / "resume_engineering.py",
        BASE / "outer_format_v1_20261015/outer_format_v1.py",
        BASE / "outer_format_v1_20261015/deepseek_access.py",
        BASE / "paired_diagnostic_20261019_v1/paired.py",
        BASE / "paired_diagnostic_20261019_v1/live.py"]
    immutable = {str(p):sha(p) for p in code + [system_path, OUT / "inputs_private.json",
                    PROJECT / "docs/pm_rl1_completion_20260930_v2/execution_contract.json"]}
    protocol = stamp(dict(version=VERSION, status="PROPOSED RESEARCH CHANGE — NOT AUTHORIZED",
        run_dir=str(BASE / "four_head_diagnostic_runs" / VERSION), initialization="random_seed17_diagnostic_only",
        executor_identity=runtime["identity"], executor_runtime=runtime, renderer_identity=renderer.identity,
        renderer_tokenizer_identity=read(Q / "P1/renderer_freeze.json")["tokenizer_identity"], measurement_identity=measurement_id,
        rubric_identity=digest(prompt), draw_identity=executor["terminal_draw_identity"],
        encoder_identity=encoder.identity, text_encoder_identity=text_identity,
        bge_binding=bge_binding, bge_expected_runtime=bge_runtime, bge_local_dir=str(bge_dir),
        generator_python="/opt/tokkio-data0/tokkio_envs/paper1-py311/bin/python",
        generator_vendor="/opt/tokkio-data0/tokkio_envs/pmrl1_sft_vendor_20260929",
        judge_python=judge_python, judge_packages=judge_packages,
        process_boundary="private local stdin/stdout IPC, child has no visible GPU; existing environments unchanged",
        config=prior["config"], final_interface=prior["final_interface"],
        semantic_revisions_used_historically=3, active_prompt_revision=2, new_prompt_revisions=0,
        public_price_table_identity=read(BASE / "anchor_calibration_execution_20261020_v1/execution_code_binding.json")["public_price_table_identity"],
        reward=dict(alpha=1, **{"lambda":.05}, gamma=1, resource_tokens=2048),
        feedback_dispositions=DISPOSITIONS, ambiguity_types=AMBIGUITY_TYPES,
        approval_scope=approval_scope, limits=limits,
        trajectory_manifest=manifest, train_batches=batches, dev_phases=dev_phases,
        immutable_files=immutable, historical_started_hashes={str(p):sha(p) for p in starts},
        old_stop_hashes={k:v for k,v in originals.items() if k.endswith("/STOP.json")},
        financial_baseline=dict(ledger_path=str(LEDGER), ledger_sha256=sha(LEDGER),
            ledger_bytes=LEDGER.stat().st_size, financial_trial_identity=trial_id,
            trial_accounted_usd=str(trial), shared_total_usd=str(total), known_unsettled=0),
        input_admission=dict(selected_train=24, repeated_train_trajectories=8, selected_dev=6,
            maximum_BGE_input_tokens=max(sizes), BGE_limit=8192,
            feasible_terminal_plan_counts=plan_sizes, full_inputs_untruncated=True),
        prepared_date_jst="2026-10-21", continued_from="2026-10-20 interrupted preparation",
        evaluation_scope="exposed development only; no final/qualification labels opened"))
    save_once(OUT / "protocol.json", protocol)
    save_once(OUT / "APPROVAL_REQUIRED.json", dict(status="PENDING",
        protocol_identity=protocol["identity"], scope=DIAGNOSTIC,
        natural_updates_authorized=False, model_requests_authorized=False,
        feedback_dispositions=DISPOSITIONS, old_stops_released=False, reward_qualified=False,
        max_trajectories=32, max_updates=2, retries=0, initialization=protocol["initialization"],
        limits=limits, user_authorization_reference=None, **approval_scope))
    mean = Decimal(".128058") / 12
    old_budget = read(BASE / "research_completion_review_20261019_v1/budget_worksheet.json")
    budget_rows = [
        ("random_initialization", 0, 0, "CPU initialization; not BC"),
        ("train_true_OFF", 24, 0, "24 cached exact G; new proxy J"),
        ("train_ON", 32, 32, "upper bound; exact terminals share cache"),
        ("dev_OFF", 6, 0, "six cached exact G"),
        ("dev_FixedRS1", 6, 0, "six cached exact G; not original FixedDev"),
        ("dev_initial_and_post_policy", 12, 12, "one fixed greedy endpoint per policy/prefix"),
        ("original_BC_initialization_separate", 336, 0, "not included in diagnostic; no qualified targets/checkpoint"),
        ("original_FixedDev_pool_separate", 250, 0, "not included; original 15-plan menu"),
        ("old_qualification_reserve_conditional", 59, None, "unchanged target applicability must be decided"),
        ("old_recovery_reserve_not_authorized", 4, None, "capacity hold only"),
        ("final_20_policy_instances_x48", 960, 960, "future upper bound; no test content read")]
    costs = [dict(name=n, maximum_new_J=j, maximum_new_G=g, note=note,
                  historical_mean_estimate_usd=str(mean*j),
                  planning_half_to_twice_mean_usd=[str(mean*j/2), str(mean*j*2)])
             for n,j,g,note in budget_rows]
    save_once(OUT / "budget.json", dict(rows=costs, observed_reference_calls=12,
        observed_mean_usd=str(mean), uncertainty="scenario range, NOT confidence interval or guarantee",
        native_single_reservation_usd=".786432", all_80_native_max_usd=str(Decimal(".786432")*80),
        proposed_limits=limits, current_trial_usd=str(trial),
        completion_of_80_not_guaranteed=True,
        capacity_math="225+80=305; proposed capacity369 leaves64=59 acceptance+4 recovery+1; current289 cannot cover",
        full_research_scenarios=[dict(episodes_per_seed=x["episodes_per_seed"],
            components=x["components"], core_J_slots=x["core_J_slots"],
            slots_with_original_reserves=x["scenario_J_with_old_acceptance_and_reserves"],
            current_mean_cost_core=str(mean*x["core_J_slots"]),
            current_mean_cost_with_reserves=str(mean*x["scenario_J_with_old_acceptance_and_reserves"]),
            selected=False, exact_de_duplication_complete=False) for x in old_budget["scenarios"]]))
    save_once(OUT / "preparation_receipt.json", dict(protocol_identity=protocol["identity"],
        actual_scoring_attempts=225, real_new_calls=0, real_natural_updates=0,
        cache_rows_verified=len(cache), BC_train_prefixes=24, BC_legal_cached_responses=336,
        BC_qualified_labels=0, BC_checkpoint_available=False, fixed_dev_cached_responses=250,
        train_owners=12, dev_owners=3, dev_independent_of_training_owners=True,
        dev_unexposed_or_independent_validation=False, admission=protocol["input_admission"],
        weights_loaded=False, account_queried=False, credentials_read=False))
    print(json.dumps(dict(protocol=protocol["identity"], cache=len(cache),
        max_bge_tokens=max(sizes), trial_usd=str(trial), phase="prepared_not_authorized")))


if __name__ == "__main__":
    prepare()
