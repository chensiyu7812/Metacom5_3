from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from metacom_pm.v1_5_component_general_v3 import (  # noqa: E402
    PAIR_KEYS,
    V3Candidate,
    all_sixteen_action_ids,
    build_component_general_plan_v3,
)
from metacom_pm.v1_5_response_program_v3 import (  # noqa: E402
    execute_response_program_v3,
    response_generation_messages_v3,
)
from metacom_pm.v1_5b_policy_runtime import (  # noqa: E402
    COMPONENTS,
    action_component_bits,
    compile_component_bits,
)


PHASE = ROOT / "data/pm_v1_5_contracts/paper1_component_general_v3_g2_implementation_phase_v1.json"
AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/pm_v1_5_paper1_component_general_v3_g2_validation_20260811/report.json"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _candidate(component: str) -> V3Candidate:
    return V3Candidate(
        component=component,  # type: ignore[arg-type]
        evidence_id=f"validate-{component.lower()}",
        meaning_cue=f"bounded {component} meaning",
        exact_source=f"auditable {component} source",
        owner_id=None if component == "RS" else "validation-owner",
        time_status="CURRENT_CARD" if component == "RS" else "STRICTLY_PAST",
        allowed_response_change=f"bounded {component} response change",
        forbidden_inference="no unsupported present fact or causal claim",
    )


class _Parsed:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    def model_dump(self, mode: str = "json") -> dict[str, Any]:
        if mode != "json":
            raise AssertionError("validator expected json model dump")
        return self.payload


class _OneShotClient:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload
        self.calls = 0

    def chat(self, messages, response_schema=None):
        self.calls += 1
        return {"raw_validation_completion": self.calls}, _Parsed(self.payload)


def validate() -> dict[str, Any]:
    phase = _read(PHASE)
    authority = _read(AUTHORITY)
    binding = authority["current_phase"]["system_feasibility_design_candidate"][
        "component_general_v3_g2_implementation"
    ]
    repair_path = _resolve(phase["repair_contract"]["path"])
    plan_path = _resolve(phase["human_plan"]["path"])
    implementation_paths = [
        _resolve(path)
        for path in phase["allowed_new_implementation_paths"]
    ]
    old_evidence_ok = all(
        _sha(_resolve(row["path"])) == row["sha256"]
        for row in phase["old_evidence_must_remain_unchanged"]
    )

    candidates = {component: _candidate(component) for component in COMPONENTS}
    sixteen_plans = [
        build_component_general_plan_v3(
            requested_action_id=action,
            current_user_id="validation-owner",
            candidates=candidates,
            pair_relations={pair: "UNKNOWN" for pair in PAIR_KEYS},
        )
        for action in all_sixteen_action_ids()
    ]
    full_action = compile_component_bits({component: True for component in COMPONENTS})
    full_plan = next(plan for plan in sixteen_plans if plan.requested_action_id == full_action)
    prompt = response_generation_messages_v3(
        current_context="I feel overwhelmed today.",
        current_goal="Offer grounded support.",
        plan=full_plan,
    )[0]["content"]
    safe_reply = "That sounds exhausting. What would feel most manageable right now?"
    safe_client = _OneShotClient(
        {
            "reply": safe_reply,
            "used_evidence_ids": [],
            "realized_response_act": "support",
        }
    )
    persisted_raw: list[tuple[int, Any]] = []
    safe_execution = execute_response_program_v3(
        client=safe_client,
        response_schema=object(),
        current_context="I feel overwhelmed today.",
        current_goal="Offer grounded support.",
        plan=full_plan,
        raw_persist=lambda attempt, raw: persisted_raw.append((attempt, raw)),
    )

    checks = {
        "phase_protocol_and_status": phase["protocol"]
        == "pm-v1.5-paper1-component-general-v3-g2-implementation-phase-v1"
        and phase["status"] == "G2_ZERO_API_IMPLEMENTATION_AND_TESTS_AUTHORIZED_ONCE",
        "phase_is_authority_bound": binding["path"]
        == "data/pm_v1_5_contracts/paper1_component_general_v3_g2_implementation_phase_v1.json"
        and binding["sha256"] == _sha(PHASE)
        and (
            binding["execution_authority"] is True
            or (
                binding["execution_authority"] is False
                and binding["status"]
                == "G2_COMPONENT_GENERAL_V3_IMPLEMENTATION_COMPLETE_G3_SURFACE_AUDIT_MAY_BE_DESIGNED"
            )
        ),
        "repair_and_plan_hashes_match": _sha(repair_path)
        == phase["repair_contract"]["sha256"]
        and _sha(plan_path) == phase["human_plan"]["sha256"],
        "old_v2_evidence_unchanged": old_evidence_ok,
        "implementation_tree_complete": all(path.is_file() for path in implementation_paths),
        "all_sixteen_unique": len(all_sixteen_action_ids()) == 16
        and len(set(all_sixteen_action_ids())) == 16,
        "all_sixteen_preserve_eligible_requested_bits": all(
            plan.structurally_eligible_action_id == plan.requested_action_id
            and plan.jointly_planned_action_id == plan.requested_action_id
            and plan.accounting.jointly_planned == action_component_bits(plan.requested_action_id)
            for plan in sixteen_plans
        ),
        "full_action_keeps_all_four_bits": all(full_plan.accounting.jointly_planned.values()),
        "full_action_has_all_six_pair_relations": {pair.pair for pair in full_plan.pair_plans}
        == set(PAIR_KEYS)
        and all(pair.suppresses_component is False for pair in full_plan.pair_plans),
        "no_literal_or_lexical_obligation": all(
            not resource.literal_mention_required and not resource.lexical_overlap_required
            for resource in full_plan.resources
        )
        and "Literal mention and lexical overlap are not required" in prompt
        and "Use this exact prior-user statement" not in prompt,
        "five_layers_separate": tuple(full_plan.accounting.__dataclass_fields__)[3:8]
        == (
            "requested",
            "structurally_eligible",
            "jointly_planned",
            "generator_claimed",
            "offline_verified_functional",
        ),
        "safe_nonuse_keeps_reply": safe_execution.status == "clean_safe_personal_nonuse"
        and safe_execution.response.reply == safe_reply
        and safe_execution.calls_made == 1
        and not any(safe_execution.accounting.generator_claimed.values()),
        "raw_completion_persisted_before_guard_contract": len(persisted_raw) == 1
        and persisted_raw[0][0] == 1
        and persisted_raw[0][1] == safe_execution.raw_results[0],
        "zero_api_and_no_labels_or_fit": all(phase["forbidden"].values()),
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-component-general-v3-g2-validation-v1",
        "status": (
            "G2_COMPONENT_GENERAL_V3_IMPLEMENTATION_PASS_G3_SURFACE_AUDIT_MAY_BE_DESIGNED"
            if not failed
            else "G2_COMPONENT_GENERAL_V3_IMPLEMENTATION_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "hashes": {
            "phase_sha256": _sha(PHASE),
            "authority_sha256": _sha(AUTHORITY),
            "repair_contract_sha256": _sha(repair_path),
            "human_plan_sha256": _sha(plan_path),
            "implementation": {
                str(path.relative_to(ROOT)): _sha(path)
                for path in implementation_paths
                if path.is_file()
            },
        },
        "actions_compiled": 16,
        "full_action_planned_bits": dict(full_plan.accounting.jointly_planned),
        "api_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
        "generator_calls": 0,
        "reviewer_calls": 0,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = validate()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
