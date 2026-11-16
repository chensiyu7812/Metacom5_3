"""Offline preparation only; imports existing payload builder, never a transport."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
from decimal import Decimal
import hashlib
import json
import os
import statistics
import sys

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
REPO = BASE.parents[3]
sys.path.insert(0, str(BASE / "paired_diagnostic_20261019_v1"))
import paired as p
from paired import s

VERSION = "pmrl1-anchor-calibration-proposal-v1-20261020"


def read(path):
    return json.loads(Path(path).read_text())


def write(name, data):
    path = HERE / name
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x") as f:
        f.write(data if isinstance(data, str) else json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    path.chmod(0o600)


def main():
    os.umask(0o077)
    selection = read(HERE / "selection_lock.json")
    old_protocol = read(BASE / "reward_noise_execution_20261020_v1/protocol.json")
    financial = read(BASE / "reward_noise_runs/pmrl1-resource-decision-noise-v1-20261020/live/financial_closeout.json")
    ledger = REPO / "project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
    assert s.sha(ledger) == financial["ledger_sha256"]
    starts = {root: len([f for f in (BASE / root).rglob("*.started.json") if "management" not in f.parts])
              for root in ("live_runs", "paired_diagnostic_runs", "action_stage_runs", "reward_noise_runs")}
    assert 66 + sum(starts.values()) == 201
    assert financial["unsettled"] == []
    prompt_path = BASE / "reference_delta_20261020_v2/coordinator/judge_frozen_prompt.txt"
    baseline = prompt_path.read_text()
    assert s.sha(prompt_path) == old_protocol["frozen_prompt_sha256"]
    examples = read(HERE / "EXAMPLES_EN.json")
    calibrated = baseline + "\n\n" + (HERE / "COMMON_TASK_ADDITION_EN.txt").read_text() + "\n\n" + json.dumps(examples, ensure_ascii=False, indent=2) + "\n"
    write("BASELINE_PROMPT_EN.txt", baseline)
    write("CALIBRATED_PROMPT_EN.txt", calibrated)

    noise = BASE / "reward_noise_proposal_20261020_v1"
    old_endpoints = {r["row_id"]: r for r in read(noise / "selected_endpoints.json")}
    transfer = BASE / "rs_transfer_preparation_20261019_v1"
    jobs = {j["slot_id"]: j for j in read(transfer / "jobs_private.json")}
    exposure = {r["index"]: r for r in read(transfer / "inventory.json")["contexts"]}
    targets = []
    immutable = {str(prompt_path): s.sha(prompt_path), str(ledger): s.sha(ledger)}
    example_source_text = {t["text"] for e in examples for t in e["fictional_complete_record"]}
    example_replies = {c["reply_fragment"] for e in examples for c in e["checks"]}
    for group in selection["contexts"]:
        for target_id in group["targets"]:
            if target_id in old_endpoints:
                e = old_endpoints[target_id]
                payload = read(noise / e["payload_file"])
                user = json.loads(payload["messages"][1]["content"])
                evidence, reply = user["legal_evidence"], user["reply"]
                binding = {k: e[k] for k in ("request_path", "raw_path", "request_file_sha256", "raw_file_sha256",
                    "reply_identity", "reply_text_sha256", "prefix_identity", "evidence_identity", "owner",
                    "executor_identity", "renderer_identity", "draw_identity", "resource_tokens")}
                item_exposure = {"known_regression": True, "seen_in_reference_development": True,
                                 "independent_validation": False, "prior_model_scores_exist": True}
            else:
                j = jobs[target_id]
                assert j["arm"] == "baseline"  # no revised RS generator mixed into this judge experiment
                source_path = transfer / f"sources/dev_{j['index']:03d}.json"
                evidence = read(source_path)
                request_path = transfer / "execution" / (target_id + ".request.json")
                raw_path = transfer / "execution" / (target_id + ".raw.json")
                request, raw = read(request_path), read(raw_path)
                assert raw["finish_reason"] == "natural_stop" and raw["request_id"] == j["request"]["request_id"]
                # The generation request file is a receipt that contains the prepared request.
                assert j["request"]["request_id"] in request_path.read_text()
                reply = raw["text"]
                binding = dict(request_path=str(request_path), raw_path=str(raw_path),
                    request_file_sha256=s.sha(request_path), raw_file_sha256=s.sha(raw_path),
                    reply_identity=s.digest({"generation_request": raw["request_id"], "reply": reply}),
                    reply_text_sha256=hashlib.sha256(reply.encode()).hexdigest(),
                    prefix_identity=exposure[j["index"]]["prefix_identity"], evidence_identity=s.digest(evidence),
                    owner=exposure[j["index"]]["owner"], resource_tokens=j["resource_tokens"],
                    **{k: j["request"][k] for k in ("executor_identity", "renderer_identity", "draw_identity")})
                item_exposure = {k: exposure[j["index"]][k] for k in ("overlap_with_prior_four", "historical_exposure_metadata", "independence")}
                item_exposure.update(known_regression=False, prior_model_scores_exist=False,
                    generation_and_review_previously_seen=True, independent_validation=False)
                immutable[str(source_path)] = s.sha(source_path)
            assert binding["executor_identity"] == "4666e72612aef698567b2e14fd3315463c451cde64f5cad1299199aaf9e0e811"
            for key in ("request", "raw"):
                assert s.sha(binding[key + "_path"]) == binding[key + "_file_sha256"]
                immutable[binding[key + "_path"]] = binding[key + "_file_sha256"]
            assert s.digest(evidence) == binding["evidence_identity"]
            turns = list(evidence["current_prefix"]) + [t for session in evidence["legal_past_sessions"] for t in session["turns"]]
            assert not example_source_text.intersection(t["text"] for t in turns)
            assert all(fragment not in reply for fragment in example_replies)
            write(f"sources/{target_id}.json", evidence)
            write(f"replies/{target_id}.txt", reply)
            target = dict(target_id=target_id, index=group["index"], purpose=group["purpose"],
                          binding=binding, exposure=item_exposure, payloads={},
                          full_source_turns=len(turns), current_turns=len(evidence["current_prefix"]),
                          source_path=f"sources/{target_id}.json", reply_path=f"replies/{target_id}.txt",
                          human_exact_q=None, human_exact_m=None, reference_is_not_gold=True)
            for arm, prompt in (("baseline", baseline), ("calibrated", calibrated)):
                messages, schema = p.payload({"evidence": evidence, "reply": reply}, "joint")
                messages[0]["content"] = prompt
                screen = p.input_guard(messages)
                data = {"messages": messages, "schema": schema}
                file = f"payloads/{target_id}__{arm}.json"
                write(file, data)
                target["payloads"][arm] = dict(file=file, sha256=s.sha(HERE/file),
                    identity=s.digest(data), screen=screen,
                    serialized_bytes=len(s.canonical(messages).encode()))
            a, b = [read(HERE / target["payloads"][arm]["file"]) for arm in ("baseline", "calibrated")]
            assert a["messages"][1:] == b["messages"][1:] and a["schema"] == b["schema"]
            targets.append(target)
    assert len(targets) == 10
    write("targets.json", targets)

    schedule = []
    presentations = [(t["target_id"], 1) for t in targets] + [(t, 2) for t in selection["repeats"]]
    target_map = {t["target_id"]: t for t in targets}
    for i, (target, draw) in enumerate(presentations):
        for arm in (("baseline", "calibrated") if i % 2 == 0 else ("calibrated", "baseline")):
            t = target_map[target]
            schedule.append(dict(position=len(schedule)+1, target_id=target, arm=arm, draw=draw,
                item_key=f"{target}__{arm}", component="joint",
                slot_id=f"{VERSION}__{target}__{arm}__draw{draw}",
                payload_identity=t["payloads"][arm]["identity"],
                prompt_revision_count=2 if arm=="baseline" else 3,
                state="NOT_AUTHORIZED_NOT_STARTED"))
    assert len(schedule) == len({r["slot_id"] for r in schedule}) == 24
    write("SCHEDULE_24.json", schedule)
    historical = read(BASE / "reward_noise_execution_20261020_v1/derived_1792474528960608601/per_request_results.json")
    usage = [r["usage"] for r in historical]
    outs = [u["completion_tokens"] for u in usage]
    # Byte/token ratio from actual old requests is only a planning scenario.
    ratios = []
    for row in historical:
        req = read(BASE / "reward_noise_runs/pmrl1-resource-decision-noise-v1-20261020/live" / (row["slot_id"] + ".request.json"))
        ratios.append(row["usage"]["prompt_tokens"] / len(s.canonical(req["messages"]).encode()))
    estimated_tokens = sum(target_map[r["target_id"]]["payloads"][r["arm"]]["serialized_bytes"] * statistics.mean(ratios) for r in schedule)
    scenarios = {name: (estimated_tokens * .3 + 24 * output * 1.2) / 1e6
                 for name, output in (("observed_min_output", min(outs)), ("observed_mean_output", statistics.mean(outs)), ("observed_max_output", max(outs)))}
    budget = dict(current_attempts=201, proposed_calls=24, cumulative_cap=225, capacity=289,
        after_stage_capacity=64, conditional_old_acceptance_reserve=59, recovery_reserve=4,
        remaining_after_conditional_reserves=1,
        old_acceptance_not_automatically_valid_for_new_measurement=True,
        current_trial_spent_usd=financial["trial_accounted_usd"], current_shared_total_usd=financial["shared_accounted_usd"],
        shared_boundary_usd="1.50724291", current_shared_followup_usd="0.8456142", known_unsettled_usd="0",
        proposed_stage_spend_plus_unsettled_cap_usd="1.15", trial_cap_usd="2", shared_followup_cap_usd="20",
        stage_and_opening_trial_max_usd=str(Decimal(".8456142")+Decimal("1.15")),
        reservation_per_request_usd="0.786432",
        reservation_formula="1048576*0.30/1000000 + 393216*1.20/1000000",
        completed_spend_ceiling_before_next_stage_reservation_usd="0.363568",
        all_24_simultaneous_worst_liability_usd="18.874368", serial_only=True,
        complete_batch_not_guaranteed=True, output_limit_unchanged=393216,
        public_price_url="https://api-docs.deepseek.com/quick_start/pricing/",
        public_model_url="https://api-docs.deepseek.com/quick_start/pricing",
        public_rechecked_date="2026-10-20", model_mapping="DeepSeek-V4.1-Flash-1017",
        peak_usd_per_million={"input_miss":.3, "input_hit":.006, "output":1.2},
        input_estimation="Observed prior provider-token/UTF8-byte ratio, applied to these actual prepared payloads; not exact tokenizer count or a reservation.",
        estimated_input_tokens_all_24=estimated_tokens,
        historical_output_min_mean_max=[min(outs), statistics.mean(outs), max(outs)],
        peak_no_cache_scenarios_usd=scenarios, scenarios_not_confidence_bounds=True,
        calibration_prompt_may_change_output_lengths=True,
        ledger_sha256=s.sha(ledger), new_paid_calls_now=0, new_management_calls_now=0)
    write("budget.json", budget)
    policy = dict(singleton_semantic_error_continue=True, singleton_complete_mechanical_failure_continue=True,
        global_consecutive_technical_stop=2, arm_consecutive_technical_stop=2,
        other_arm_success_does_not_reset=True, truncated_or_missing_usage_stop=True,
        incomplete_started_no_retry=True, service_data_integrity_failure_stop=True, retries=0,
        semantic_unknown_is_missing=True, no_repair=True, original_stops_released=False,
        policy_status="PROPOSED_SEPARATE_DIAGNOSTIC_NOT_REACTIVATION")
    files = [HERE/"selection_lock.json", HERE/"COMMON_TASK_ADDITION_EN.txt", HERE/"EXAMPLES_EN.json",
             HERE/"BASELINE_PROMPT_EN.txt", HERE/"CALIBRATED_PROMPT_EN.txt", HERE/"targets.json", HERE/"SCHEDULE_24.json", HERE/"budget.json"]
    files += sorted((HERE/"payloads").glob("*.json"))
    files += [Path(p.__file__), Path(s.__file__), Path(s.judge.__file__),
              BASE/"outer_format_v1_20261015/outer_format_v1.py"]
    immutable.update({str(f): s.sha(f) for f in files})
    protocol = dict(version=VERSION, status="PROPOSED_NOT_AUTHORIZED", created_at=datetime.now(ZoneInfo("Asia/Tokyo")).isoformat(),
        config=old_protocol["config"], final_interface=old_protocol["final_interface"],
        arms={"baseline":dict(prompt_file="BASELINE_PROMPT_EN.txt",semantic_revision_count=2),
              "calibrated":dict(prompt_file="CALIBRATED_PROMPT_EN.txt",semantic_revision_count_if_approved=3)},
        current_semantic_revision_count=2, proposed_additional_semantic_revision=1, applied_now=False,
        schedule=schedule, diagnostic_policy=policy, max_new_calls=24, baseline_cumulative=201,
        cumulative_cap=225, capacity=289, all_targets_same_frozen_executor=True,
        statistics=dict(distinct_replies=10,contexts=5,owners=3,known_regression_replies=4,
                        other_exposed_dev_replies=6,independent_validation_cases=0),
        treatment="New aligned task requirement PLUS fictional source-controlled demonstrations as one package; not attribution to examples alone.",
        human_task_issued=False, new_human_labels_required_for_this_diagnostic=False,
        qualify_reward=False, activate_natural_RL=False,
        immutable_files=immutable, original_stop_hashes=read(BASE/"reward_noise_execution_20261020_v1/provenance/old_stops.json"),
        source_reuse_notice="All source bodies are existing legal development records. No sealed labels or PM test content opened.",
        authority_requested=dict(max_calls=24,cumulative_cap=225,stage_liability_usd="1.15",
            management_requests={"models":1,"user/balance":1},credential_process_only=True,
            outbound="Existing single reply, full legal current/past sources and IDs, frozen schema, original judge prompt; calibrated arm additionally sends exactly the proposed task addition and six fictional demonstration records. No actual researcher answers, scores, names, review records, model outputs or expected target labels.",
            added_researcher_derived_task_rule="Conditional identity clarification; not raw annotation export.",
            no_account_setting_change=True,no_upload=True),
        runner="Reuse paired.run with per-slot frozen payload/runtime metadata; no new transport or parser.",
        real_launch_requires_fresh_approval_and_preflight=True)
    protocol["identity"] = s.digest(protocol)
    write("protocol.json", protocol)
    write("PUBLIC_SERVICE_NOTE.json", {"checked_at": protocol["created_at"], "model":budget["model_mapping"],
        "alias_not_immutable":True,"pricing_url":budget["public_price_url"],
        "observation":"Official public documentation reviewed without credentials/account/model requests.",
        "prices":budget["peak_usd_per_million"],"context":1048576,"output_limit":393216,
        "future_account_identity_and_fingerprint_recheck_required":True})
    print(json.dumps({"identity":protocol["identity"],"targets":len(targets),"slots":len(schedule),"budget_scenarios":scenarios,"largest_input_screen_bytes":max(v["screen"]["serialized_messages_utf8_bytes"] for t in targets for v in t["payloads"].values())},indent=2))


if __name__ == "__main__":
    main()
