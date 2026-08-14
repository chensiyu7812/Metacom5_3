#!/usr/bin/env python3
"""Materialize a zero-API MS meaning-absorption qualification preflight."""

from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_component_general_v3 import (  # noqa: E402
    V3Candidate,
    all_sixteen_action_ids,
    build_component_general_plan_v3,
)
from metacom_pm.v1_5_ms_same_stack_feasibility import SameStackGeneratorOutput  # noqa: E402
from metacom_pm.v1_5_response_program_v3 import response_generation_messages_v3  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
CLOSEOUT = ROOT / "data/pm_v1_5_contracts/paper1_v3_ms_atomic_checkpoint_closeout_v1.json"
LABELS = ROOT / "outputs/pm_v1_5_paper1_v3_ms_single_teacher_label_freeze_20260811/ms_teacher_labels.jsonl"
PACKET = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811/reviewer_a_packet.jsonl"
GENERATOR_CONFIG = ROOT / "configs/experiment.yaml"
OUT = ROOT / "outputs/pm_v1_5_paper1_v3_ms_executor_qualification_preflight_v3_20260811"
CURRENT_GOAL = "Respond supportively to the latest visible seeker turn. Advance its immediate emotional-support goal without inventing facts, overloading the reply, or assuming a past fact is still current."
ACTIONS = ("M0+R0", "MS+R0", "M0+RS", "MS+RS")


def read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rows(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def stable_hex(*values: object, length: int = 24) -> str:
    text = "\u241f".join(str(value) for value in values)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]


def stratum(row: dict[str, Any]) -> str:
    if row["low_information_rank1"]:
        return "LOW_INFORMATION"
    if row["exact_or_containment_current_echo"]:
        return "CURRENT_ECHO"
    return "ORDINARY_ATOMIC"


def choose_cases(labels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_group: dict[str, dict[int, list[dict[str, Any]]]] = defaultdict(lambda: defaultdict(list))
    for row in labels:
        if row["binary_suitability_label"] is not None:
            by_group[row["split_group_key"]][int(row["binary_suitability_label"])].append(row)
    desired_negative_strata = (
        "LOW_INFORMATION", "CURRENT_ECHO", "ORDINARY_ATOMIC", "LOW_INFORMATION",
        "CURRENT_ECHO", "ORDINARY_ATOMIC", "LOW_INFORMATION", "CURRENT_ECHO",
    )
    selected_groups: list[str] = []
    for wanted in desired_negative_strata:
        candidates = [
            group
            for group, classes in by_group.items()
            if group not in selected_groups
            and classes[1]
            and any(stratum(row) == wanted for row in classes[0])
        ]
        candidates.sort(key=lambda group: stable_hex("MS_EXECUTOR_GROUP", wanted, group))
        if not candidates:
            raise RuntimeError(f"cannot assign distinct group to negative stratum {wanted}")
        selected_groups.append(candidates[0])

    selected: list[dict[str, Any]] = []
    for group_index, group in enumerate(selected_groups):
        positives = sorted(by_group[group][1], key=lambda row: stable_hex("MS_EXECUTOR_POS", row["case_key"]))
        negatives = by_group[group][0]
        wanted = desired_negative_strata[group_index]
        pool = sorted(
            [row for row in negatives if stratum(row) == wanted],
            key=lambda row: stable_hex("MS_EXECUTOR_NEG", row["case_key"]),
        )
        if not pool:
            raise RuntimeError(f"assigned group lost required negative stratum {wanted}")
        positive = dict(positives[0])
        negative = dict(pool[0])
        positive["qualification_class"] = "TEACHER_SUITABLE"
        negative["qualification_class"] = "TEACHER_NOT_SUITABLE"
        selected.extend((positive, negative))
    return selected


def current_context(item: dict[str, Any]) -> str:
    return "\n".join(
        f"{str(span['speaker']).upper()}: {str(span['content']).strip()}"
        for span in item["visible_spans"]
    )


def main() -> None:
    if OUT.exists():
        raise RuntimeError("MS executor qualification preflight exists; refusing overwrite")
    authority = read(AUTHORITY)
    active = authority["active_v3_phase"]
    if active["id"] != "MS_EXECUTOR_QUALIFICATION_DESIGN":
        raise RuntimeError("MS executor qualification design is not active")
    binding = active["active_phase_manifest"]
    if binding["path"] != str(CLOSEOUT.relative_to(ROOT)) or binding["sha256"] != sha256_file(CLOSEOUT):
        raise RuntimeError("MS checkpoint closeout binding drifted")

    labels = rows(LABELS)
    packet = {row["review_item_id"]: row for row in rows(PACKET) if row["component"] == "MS"}
    selected = choose_cases(labels)
    qualification_cases = []
    physical_calls = []
    for case_index, label in enumerate(selected, 1):
        item = packet[label["review_item_id"]]
        if len(item["candidate_spans"]) != 1:
            raise RuntimeError("qualification requires one atomic MS candidate span")
        exact_source = str(item["candidate_spans"][0]["content"]).strip()
        context = current_context(item)
        case_id = "msq_" + stable_hex(label["case_key"], label["qualification_class"])
        evidence_id = "msev_" + stable_hex(label["case_key"], exact_source)
        seed = 20260811 + int(stable_hex("SEED", case_id, length=8), 16) % 100000
        rotation = int(stable_hex("ORDER", case_id, length=8), 16) % len(ACTIONS)
        ordered_actions = ACTIONS[rotation:] + ACTIONS[:rotation]
        qualification_cases.append({
            "protocol": "pm-v1.5-paper1-v3-ms-executor-qualification-case-v1",
            "qualification_case_id": case_id,
            "case_key": label["case_key"],
            "state_id": label["state_id"],
            "split_group_key": label["split_group_key"],
            "runtime_owner_key": label["runtime_owner_key"],
            "teacher_decision": label["teacher_decision"],
            "qualification_class": label["qualification_class"],
            "negative_stratum": stratum(label) if label["binary_suitability_label"] == 0 else None,
            "review_item_id": label["review_item_id"],
            "actual_rank1_id": label["actual_rank1_id"],
            "evidence_id": evidence_id,
            "current_context": context,
            "current_goal": CURRENT_GOAL,
            "exact_source": exact_source,
            "seed": seed,
        })
        for order, action in enumerate(ordered_actions, 1):
            ms_on = action in {"MS+R0", "MS+RS"}
            rs_on = action in {"M0+RS", "MS+RS"}
            candidates: dict[str, V3Candidate | None] = {component: None for component in ("MP", "MS", "ME", "RS")}
            if ms_on:
                candidates["MS"] = V3Candidate(
                    component="MS",
                    evidence_id=evidence_id,
                    meaning_cue=(
                        "Interpret the single strictly past user-owned source supplied below as a "
                        "tentative continuity cue; do not treat it as current or quote it."
                    ),
                    exact_source=exact_source,
                    owner_id=label["runtime_owner_key"],
                    time_status="STRICTLY_PAST_NOT_ASSUMED_CURRENT",
                    allowed_response_change="If it materially helps, use the past meaning to acknowledge continuity or ask a more informed current-oriented question.",
                    forbidden_inference="Do not copy the user's first-person wording, assume the past remains true, infer a trait or cause, or expose a memory record.",
                    burden_units=1,
                )
            if rs_on:
                candidates["RS"] = V3Candidate(
                    component="RS",
                    evidence_id="rs_open_nonleading_v1",
                    meaning_cue="Offer one open, non-leading invitation that helps the user identify what feels most important or manageable now.",
                    exact_source="Frozen strategy card: one open, non-leading, low-burden invitation.",
                    owner_id=None,
                    time_status="CURRENT_STRATEGY_CARD",
                    allowed_response_change="Make the reply's primary act one open, non-leading question or invitation.",
                    forbidden_inference="Do not presuppose the answer, force disclosure, add a second task, or override a stop boundary.",
                    burden_units=1,
                )
            plan = build_component_general_plan_v3(
                requested_action_id=action,
                current_user_id=label["runtime_owner_key"],
                candidates=candidates,
                pair_relations={"MS-RS": "COMPLEMENTARY"} if ms_on and rs_on else None,
            )
            messages = response_generation_messages_v3(
                current_context=context,
                current_goal=CURRENT_GOAL,
                plan=plan,
            )
            physical_calls.append({
                "protocol": "pm-v1.5-paper1-v3-ms-executor-qualification-call-v1",
                "physical_call_id": "msqcall_" + stable_hex(case_id, action, seed),
                "qualification_case_id": case_id,
                "state_id": label["state_id"],
                "split_group_key": label["split_group_key"],
                "runtime_owner_key": label["runtime_owner_key"],
                "qualification_class_private": label["qualification_class"],
                "requested_action_id": action,
                "within_state_call_order": order,
                "seed": seed,
                "temperature": 0.7,
                "max_output_tokens": 512,
                "messages": messages,
                "messages_sha256": sha256_text(canonical_json(messages)),
                "response_schema": SameStackGeneratorOutput.model_json_schema(),
                "response_schema_sha256": sha256_text(canonical_json(SameStackGeneratorOutput.model_json_schema())),
                "plan_accounting": {
                    "requested_action_id": plan.accounting.requested_action_id,
                    "structurally_eligible_action_id": plan.accounting.structurally_eligible_action_id,
                    "jointly_planned_action_id": plan.accounting.jointly_planned_action_id,
                },
            })

    by_case = defaultdict(list)
    for row in physical_calls:
        by_case[row["qualification_case_id"]].append(row)
    prompt_texts = [canonical_json(row["messages"]) for row in physical_calls]
    cases_by_id = {row["qualification_case_id"]: row for row in qualification_cases}
    system_source_counts = {
        row["physical_call_id"]: row["messages"][0]["content"].count(
            cases_by_id[row["qualification_case_id"]]["exact_source"]
        )
        for row in physical_calls
    }
    group_class_counts = Counter((row["split_group_key"], row["qualification_class"]) for row in qualification_cases)
    checks = {
        "exact_16_states_64_calls": len(qualification_cases) == 16 and len(physical_calls) == 64,
        "eight_groups_each_with_one_suitable_and_one_not": len({row["split_group_key"] for row in qualification_cases}) == 8 and set(group_class_counts.values()) == {1} and len(group_class_counts) == 16,
        "negative_strata_exact_3_low_3_echo_2_ordinary": Counter(row["negative_stratum"] for row in qualification_cases if row["negative_stratum"]) == Counter({"LOW_INFORMATION": 3, "CURRENT_ECHO": 3, "ORDINARY_ATOMIC": 2}),
        "each_state_has_four_nonexclusive_actions": all({row["requested_action_id"] for row in calls} == set(ACTIONS) for calls in by_case.values()),
        "same_seed_within_state": all(len({row["seed"] for row in calls}) == 1 for calls in by_case.values()),
        "visible_context_ends_with_seeker": all(
            row["current_context"].splitlines()[-1].startswith("SEEKER:")
            for row in qualification_cases
        ),
        "ms_source_once_in_system_when_on_zero_when_off": all(
            system_source_counts[row["physical_call_id"]]
            == (1 if row["requested_action_id"] in {"MS+R0", "MS+RS"} else 0)
            for row in physical_calls
        ),
        "v3_meaning_absorption_prompt_only": all("Literal mention and lexical overlap are not required" in text and "Use this exact prior-user statement" not in text for text in prompt_texts),
        "safe_nonuse_instruction_present": all("leave it unused and still produce a safe current-context-grounded reply" in text for text in prompt_texts),
        "no_one_memory_cap_and_global_16_actions_unchanged": len(all_sixteen_action_ids()) == 16,
        "ms_rs_pair_is_complementary_not_suppressive": all(row["plan_accounting"]["jointly_planned_action_id"] == row["requested_action_id"] for row in physical_calls),
        "teacher_class_never_provider_visible": all("TEACHER_SUITABLE" not in text and "TEACHER_NOT_SUITABLE" not in text for text in prompt_texts),
        "response_schema_frozen": len({row["response_schema_sha256"] for row in physical_calls}) == 1,
        "no_api_calls": True,
        "no_pm_refit": True,
        "no_mp_or_me_work": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    OUT.mkdir(parents=True)
    cases_path = OUT / "qualification_cases_private.jsonl"
    calls_path = OUT / "physical_call_plan_private.jsonl"
    write_jsonl(cases_path, qualification_cases)
    write_jsonl(calls_path, physical_calls)
    report = {
        "protocol": "pm-v1.5-paper1-v3-ms-executor-qualification-preflight-report-v1",
        "status": "MS_V3_EXECUTOR_QUALIFICATION_PREFLIGHT_PASS_LIVE_PHASE_MAY_BE_DESIGNED" if not failed else "MS_V3_EXECUTOR_QUALIFICATION_PREFLIGHT_FAIL",
        "checks": checks,
        "failed_checks": failed,
        "sample": {
            "states": len(qualification_cases),
            "groups": len({row["split_group_key"] for row in qualification_cases}),
            "teacher_suitable": sum(row["qualification_class"] == "TEACHER_SUITABLE" for row in qualification_cases),
            "teacher_not_suitable": sum(row["qualification_class"] == "TEACHER_NOT_SUITABLE" for row in qualification_cases),
            "negative_strata": dict(Counter(row["negative_stratum"] for row in qualification_cases if row["negative_stratum"])),
        },
        "actions": {action: sum(row["requested_action_id"] == action for row in physical_calls) for action in ACTIONS},
        "generator": {
            "config": "configs/experiment.yaml:endpoints.generator",
            "model": "meta/llama-3.1-8b-instruct",
            "temperature": 0.7,
            "max_output_tokens": 512,
            "paired_seed_per_state": True,
            "planned_physical_calls": 64,
            "maximum_transport_attempts_per_call": 2,
            "explicit_usd_cap": 0.05,
        },
        "qualification_measurement": {
            "machine": ["structured completion", "guard status", "no internal-label/scaffold leak", "no unauthorized evidence ID", "no forced literal or lexical-use gate"],
            "offline_source_aware": ["MS functional contribution", "owner/time correctness", "past-not-current handling", "safe nonuse"],
            "paired": ["quality", "literal risk events", "function", "cost"],
            "generator_claimed_used_evidence_is_not_function_gold": True,
        },
        "artifacts": {
            "cases": {"path": str(cases_path.relative_to(ROOT)), "sha256": sha256_file(cases_path)},
            "calls": {"path": str(calls_path.relative_to(ROOT)), "sha256": sha256_file(calls_path)},
        },
        "source_hashes": {
            "authority": sha256_file(AUTHORITY),
            "checkpoint_closeout": sha256_file(CLOSEOUT),
            "labels": sha256_file(LABELS),
            "packet": sha256_file(PACKET),
            "generator_config": sha256_file(GENERATOR_CONFIG),
            "response_program_v3": sha256_file(ROOT / "src/metacom_pm/v1_5_response_program_v3.py"),
            "component_general_v3": sha256_file(ROOT / "src/metacom_pm/v1_5_component_general_v3.py"),
        },
        "api_calls": 0,
        "pm_fits": 0,
        "live_execution_authorized_by_this_report": False,
        "next": "INDEPENDENTLY_AUDIT_SAMPLE_PROMPTS_AND_HASH_BIND_EXACT_64_CALL_LIVE_PHASE",
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
