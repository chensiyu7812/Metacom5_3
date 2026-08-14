#!/usr/bin/env python3
"""Build the zero-call, content-bound 50-call MS/MP V1.1 judge manifest."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.io import canonical_json, read_jsonl, sha256_file, sha256_text, write_json, write_jsonl  # noqa: E402
from metacom_pm.text import dialogue_text  # noqa: E402
from metacom_pm.v1_5_function_observability_v2_blind_review import FunctionObservabilityV2BlindReview, function_prompt_messages  # noqa: E402
from metacom_pm.v1_5_mp_function_pair_blind_review import MPFunctionPairBlindReview, mp_function_pair_prompt_messages  # noqa: E402
from metacom_pm.v1_5_rs_ms_quality_risk_blind_review import RSMSQualityBlindReview, quality_prompt_messages  # noqa: E402
from metacom_pm.v1_5_source_aware_risk_blind_review import SourceAwareRiskBlindReview, source_aware_risk_prompt_messages  # noqa: E402

MS_CASES = ROOT / "outputs/pm_v1_5_paper1_ms_v1_1_panel_20260813/development_cases_private.jsonl"
MP_CASES = ROOT / "outputs/pm_v1_5_paper1_mp_v1_1_panel_20260813/development_cases_private.jsonl"
MS_RESULTS = ROOT / "outputs/pm_v1_5_paper1_ms_v1_1_panel_live_retry2_20260813/generator_results_private.jsonl"
MP_RESULTS = ROOT / "outputs/pm_v1_5_paper1_mp_v1_1_panel_live_20260813/generator_results_private.jsonl"
STATES = ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"
CONFIG = ROOT / "configs/paper1_ms_mp_v1_1_blind_review_execution_v1.json"
ENDPOINTS = ROOT / "configs/paper1_rs_ms_quality_risk_measurement_endpoints_v1.json"
OUT = ROOT / "outputs/pm_v1_5_paper1_ms_mp_v1_1_blind_review_manifest_20260813"
MODEL = "gpt-5.6-sol"
ENDPOINT_KEY = "openai_gpt_5_6_sol"
PROVIDER_KEYS = frozenset({"messages", "temperature", "max_output_tokens", "seed", "schema_sha256"})


def stable_hex(*values: object, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(map(str, values)).encode()).hexdigest()[:length]


def public(messages: list[dict[str, str]], schema: type, logical_id: str) -> dict[str, Any]:
    return {
        "messages": messages,
        "temperature": 0.0,
        "max_output_tokens": 500,
        "seed": 20260813 + int(stable_hex(logical_id, length=8), 16) % 100000,
        "schema_sha256": sha256_text(canonical_json(schema.model_json_schema())),
    }


def main() -> None:
    if OUT.exists():
        raise RuntimeError("manifest directory already exists; refusing overwrite")
    states = {r["state_id"]: r for r in read_jsonl(STATES)}
    calls: list[dict[str, Any]] = []
    private_map: list[dict[str, Any]] = []
    full_context_by_case: dict[tuple[str, str], str] = {}
    quality_position_index = {"MS": 0, "MP": 0}
    mp_function_position_index = 0

    def add_call(*, kind: str, component: str, case: dict[str, Any], id_key: str,
                 item_id: str, messages: list[dict[str, str]], schema: type, **private: Any) -> None:
        logical_id = f"v11judge_{stable_hex(kind, item_id)}"
        pub = public(messages, schema, logical_id)
        calls.append({
            "logical_call_id": logical_id, "kind": kind, "component": component,
            "case_id": case["case_id"], "owner_cluster": case["runtime_owner_key"],
            id_key: item_id, "messages_sha256": sha256_text(canonical_json(messages)),
            "public_call": pub, **private,
        })

    for component, case_path, result_path in (
        ("MS", MS_CASES, MS_RESULTS), ("MP", MP_CASES, MP_RESULTS),
    ):
        cases = read_jsonl(case_path)
        results = {(r["case_id"], r["arm"]): r for r in read_jsonl(result_path)}
        for case in cases:
            cid, owner = case["case_id"], case["runtime_owner_key"]
            full = dialogue_text(states[case["state_id"]]["visible_current_session_dialogue"])
            full_context_by_case[(component, cid)] = full
            treat_arm = "MS+R0" if component == "MS" else "MP+R0"
            if (cid, treat_arm) not in results:
                private_map.append({"component": component, "case_id": cid, "owner_cluster": owner, "measured": False})
                continue
            baseline, treated = results[(cid, "M0+R0")]["reply"], results[(cid, treat_arm)]["reply"]
            source = case["ms_exact_source"] if component == "MS" else case["mp_exact_source"]

            pair_id = f"v11q_{stable_hex(component, cid)}"
            treated_at_a = quality_position_index[component] % 2 == 0
            quality_position_index[component] += 1
            qa, qb = (treated, baseline) if treated_at_a else (baseline, treated)
            qm = quality_prompt_messages(pair_id=pair_id, dialogue=full, reply_a=qa, reply_b=qb)
            add_call(kind=f"{component.lower()}_quality", component=component, case=case,
                     id_key="pair_id", item_id=pair_id, messages=qm, schema=RSMSQualityBlindReview,
                     a_arm=treat_arm if treated_at_a else "M0+R0", b_arm="M0+R0" if treated_at_a else treat_arm)

            risk_ids = {}
            for arm, reply in (("M0+R0", baseline), (treat_arm, treated)):
                item_id = f"v11r_{stable_hex(component, cid, arm)}"
                label = ("strictly past user-owned MS source; reference for truth and relevance checking"
                         if component == "MS" else
                         "profile source; reference for truth/relevance checking, literal exposure is forbidden")
                rm = source_aware_risk_prompt_messages(item_id=item_id, full_dialogue=full,
                    authorized_resource_label=label, authorized_resource_text=source, reply=reply)
                add_call(kind=f"{component.lower()}_risk", component=component, case=case,
                         id_key="item_id", item_id=item_id, messages=rm, schema=SourceAwareRiskBlindReview,
                         arm=arm)
                risk_ids[arm] = item_id

            function_id = None
            if component == "MS" and case["stratum"] in {"CLEAR_USE", "ASK"}:
                function_id = f"v11msf_{stable_hex(cid)}"
                fm = function_prompt_messages(blind_item_id=function_id, current_context=full,
                    authorized_resource_label="strictly past user-owned MS source",
                    authorized_resource_text=source, reply=treated)
                add_call(kind="ms_function", component=component, case=case, id_key="blind_item_id",
                         item_id=function_id, messages=fm, schema=FunctionObservabilityV2BlindReview,
                         arm_judged=treat_arm)
            elif component == "MP" and case["stratum"] == "CONSTRAIN_eligible":
                function_id = f"v11mpf_{stable_hex(cid)}"
                mp_at_a = mp_function_position_index % 2 == 0
                mp_function_position_index += 1
                fa, fb = (treated, baseline) if mp_at_a else (baseline, treated)
                fm = mp_function_pair_prompt_messages(pair_id=function_id, full_dialogue=full,
                    profile_field=case["profile_field"], authorized_profile_source=source,
                    reply_a=fa, reply_b=fb)
                add_call(kind="mp_function_pair", component=component, case=case, id_key="pair_id",
                         item_id=function_id, messages=fm, schema=MPFunctionPairBlindReview,
                         mp_position="A" if mp_at_a else "B")
            private_map.append({"component": component, "case_id": cid, "owner_cluster": owner,
                "measured": True, "quality_pair_id": pair_id, "risk_ids": risk_ids,
                "function_id": function_id})

    calls.sort(key=lambda r: stable_hex("order", r["logical_call_id"]))
    provider_text = canonical_json([r["public_call"]["messages"] for r in calls])
    input_paths = [MS_CASES, MP_CASES, MS_RESULTS, MP_RESULTS, STATES, CONFIG, ENDPOINTS,
        ROOT / "data/pm_v1_5_contracts/paper1_ms_mp_v1_1_development_gate_v1.json",
        ROOT / "data/pm_v1_5_contracts/paper1_ms_v1_1_panel_generation_closeout_v1.json",
        ROOT / "data/pm_v1_5_contracts/paper1_mp_v1_1_panel_generation_closeout_v1.json",
        ROOT / "src/metacom_pm/v1_5_rs_ms_quality_risk_blind_review.py",
        ROOT / "src/metacom_pm/v1_5_source_aware_risk_blind_review.py",
        ROOT / "src/metacom_pm/v1_5_function_observability_v2_blind_review.py",
        ROOT / "src/metacom_pm/v1_5_mp_function_pair_blind_review.py",
        ROOT / "scripts/v1_5/340l_run_paper1_ms_mp_v1_1_blind_review_v1_5.py",
        ROOT / "scripts/v1_5/341l_aggregate_paper1_ms_mp_v1_1_blind_review_v1_5.py",
        Path(__file__)]
    bindings = {str(p.relative_to(ROOT)): sha256_file(p) for p in input_paths}
    identity_material = {
        "protocol": "pm-v1.5-ms-mp-v1-1-blind-review-identity-v1", "model": MODEL,
        "endpoint_key": ENDPOINT_KEY, "output_directory": "outputs/pm_v1_5_paper1_ms_mp_v1_1_blind_review_live_20260813",
        "absolute_usd_cap": 1.1, "bindings": bindings,
        "calls": [{"logical_call_id": r["logical_call_id"], "kind": r["kind"],
                   "messages_sha256": r["messages_sha256"], "public_call": r["public_call"]} for r in calls],
    }
    run_identity = sha256_text(canonical_json(identity_material))
    counts = {k: sum(r["kind"] == k for r in calls) for k in
              ("ms_quality", "mp_quality", "ms_risk", "mp_risk", "ms_function", "mp_function_pair")}
    checks = {
        "exact_50_calls": len(calls) == 50,
        "expected_kind_counts": counts == {"ms_quality": 6, "mp_quality": 7, "ms_risk": 12, "mp_risk": 14, "ms_function": 6, "mp_function_pair": 5},
        "provider_projection_exact": all(set(r["public_call"]) == PROVIDER_KEYS for r in calls),
        "full_context_present": all(
            any(full_context_by_case[(r["component"], r["case_id"])] in m["content"]
                for m in r["public_call"]["messages"])
            for r in calls
        ),
        "arm_labels_absent_from_provider_text": not any(x in provider_text for x in ("M0+R0", "MS+R0", "MP+R0", "arm_judged")),
        "private_telemetry_absent_from_provider_text": not any(x in provider_text for x in ("used_evidence_ids", "generator_claimed")),
        "positions_balanced": (
            sum(r.get("a_arm") == "MS+R0" for r in calls if r["kind"] == "ms_quality") == 3
            and sum(r.get("a_arm") == "MP+R0" for r in calls if r["kind"] == "mp_quality") in (3, 4)
            and sum(r.get("mp_position") == "A" for r in calls if r["kind"] == "mp_function_pair") in (2, 3)
        ),
        "logical_ids_unique": len({r["logical_call_id"] for r in calls}) == len(calls),
        "owner_unique_within_each_panel": len({r["runtime_owner_key"] for r in read_jsonl(MS_CASES)}) == 9 and len({r["runtime_owner_key"] for r in read_jsonl(MP_CASES)}) == 8,
    }
    if not all(checks.values()):
        raise RuntimeError(f"manifest checks failed: {checks}")
    OUT.mkdir(parents=True)
    write_jsonl(OUT / "calls_private.jsonl", calls)
    write_jsonl(OUT / "private_map.jsonl", private_map)
    report = {
        "protocol": "pm-v1.5-paper1-ms-mp-v1-1-blind-review-manifest-v1",
        "status": "PREFLIGHT_READY_EXPLICIT_USER_APPROVAL_REQUIRED_BEFORE_ANY_JUDGE_CALL",
        "run_identity": run_identity, "judge_model": MODEL, "endpoint_key": ENDPOINT_KEY,
        "call_counts": {**counts, "quality_total": 13, "risk_total": 26, "function_total": 11, "total": 50},
        "estimated_usd": 0.894, "absolute_usd_cap_proposed": 1.1,
        "cost_basis": "Conservative: quality 13*$0.012 + source-aware risk 26*$0.020 + MS Function 6*$0.018 + MP pair-Function 5*$0.022.",
        "measurement_scope": "Frozen development gate only; no selector or formal external-test claim.",
        "checks": checks, "bindings": bindings, "api_calls": 0,
    }
    write_json(OUT / "report.json", report)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
