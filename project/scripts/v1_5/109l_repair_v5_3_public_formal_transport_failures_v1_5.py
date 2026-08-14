#!/usr/bin/env python3
"""Replay only transport-failed formal arms, then rejudge their fixed groups."""

from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
BASE_PATH = ROOT / "scripts/v1_5/100l_run_v5_3_public_learnability_canary_v1_5.py"
SPEC = importlib.util.spec_from_file_location("v53_transport_repair_base", BASE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError("cannot load Q/F base runner")
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)

from metacom_pm.api import make_client  # noqa: E402
from metacom_pm.config import endpoint_from_config, load_config  # noqa: E402
from metacom_pm.io import stable_hex, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_qrf_judge import (  # noqa: E402
    BatchedContributionJudgment,
    BatchedFunctionalUseJudgment,
    aggregate_on_minus_off,
    contribution_messages,
    functional_use_messages,
    validate_response_excerpts,
)
from metacom_pm.v1_5_v5_3_typed_response_program import (  # noqa: E402
    evidence_aware_generation_messages,
    execute_typed_response,
)


PROTOCOL = "pm-v1.5-v5.3-public-formal-qf-v1"
OUT = ROOT / "outputs/pm_v1_5_v5_3_public_formal_qf_20260809"
MANIFEST = ROOT / "outputs/pm_v1_5_v5_3_public_formal_effect_manifest_20260809/effect_group_manifest_private.jsonl"
TRANSPORT_MARKERS = ("rate_limited_429", "request_timeout_408", "http_5xx", "network_timeout")


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _needs_repair(result: dict) -> bool:
    return not result.get("transport_repair") and any(
        any(marker in str(call.get("error", "")) for marker in TRANSPORT_MARKERS)
        and not call.get("will_retry_identical_request", False)
        for call in result.get("call_records", [])
        if call.get("role") == "generator"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fold", type=int, required=True, choices=range(1, 7))
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--accept-usd-cap", type=float)
    args = parser.parse_args()
    path = OUT / "shards" / f"fold_{args.fold}_results.jsonl"
    results = _jsonl(path)
    targets = [row for row in results if _needs_repair(row)]
    print({"fold": args.fold, "transport_failed_groups": len(targets)})
    if not args.live or not targets:
        return
    if args.accept_usd_cap is None or args.accept_usd_cap < 0.02:
        raise SystemExit("transport repair requires --accept-usd-cap 0.02")
    manifests = {row["effect_group_id"]: row for row in _jsonl(MANIFEST)}
    config = load_config(ROOT / "configs/experiment.yaml")
    gen_client = make_client(endpoint_from_config(config, "generator"))
    judge_client = make_client(endpoint_from_config(config, "training_judge"))
    aliases = BASE._aliases(list(manifests.values()))
    archive = OUT / "transport_repairs" / f"fold_{args.fold}_before.jsonl"
    archived = _jsonl(archive) if archive.exists() else []
    try:
        for result in targets:
            source = manifests[result["effect_group_id"]]
            archived.append(result)
            repair_calls = []
            for replicate in result["generated"]:
                for arm in ("ON", "OFF"):
                    old = replicate[arm]
                    if not any(marker in " ".join(old.get("first_pass_errors", [])) for marker in TRANSPORT_MARKERS):
                        continue
                    on = arm == "ON"
                    program = BASE._program(
                        source, on=on,
                        aliases=aliases.get(str(source.get("user_id")), ()),
                    )
                    wrapper = BASE.RecordingSeedClient(
                        gen_client, seed=int(replicate["seed"]), temperature=0.7,
                        max_tokens=512, retries=1, transport_retries=1,
                    )
                    execution = execute_typed_response(
                        wrapper, BASE.GeneratorSchema,
                        evidence_aware_generation_messages(
                            current_context=BASE._context(source), program=program,
                        ),
                        program,
                    )
                    if execution.status != "clean":
                        raise RuntimeError("transport replay did not produce a clean arm")
                    replicate[arm] = {
                        "reply": execution.response.reply,
                        "status": execution.status,
                        "requested_action_id": execution.requested_action_id,
                        "realized_action_id": execution.realized_action_id,
                        "first_pass_errors": list(execution.first_pass_errors),
                    }
                    repair_calls.extend({"role": "transport_repair_generator", "arm": arm, **call} for call in wrapper.calls)

            responses = {
                f"{rep['replicate_id']}_{arm}": rep[arm]["reply"]
                for rep in result["generated"] for arm in ("ON", "OFF")
            }
            forward = [{"replicate_id": rep["replicate_id"], "response_a": rep["ON"]["reply"], "response_b": rep["OFF"]["reply"]} for rep in result["generated"]]
            reverse = [{"replicate_id": rep["replicate_id"], "response_a": rep["OFF"]["reply"], "response_b": rep["ON"]["reply"]} for rep in result["generated"]]
            seed = int(stable_hex(PROTOCOL, source["effect_group_id"], "judge", n=8), 16) & 0x7FFFFFFF
            _, qf, calls = BASE._judge_call(judge_client, BatchedContributionJudgment, contribution_messages(visible_dialogue=source["visible_dialogue"], pairs=forward), seed=seed, max_tokens=2100)
            repair_calls.extend({"role": "transport_repair_quality_forward", **call} for call in calls)
            _, qr, calls = BASE._judge_call(judge_client, BatchedContributionJudgment, contribution_messages(visible_dialogue=source["visible_dialogue"], pairs=reverse), seed=seed + 1, max_tokens=2100)
            repair_calls.extend({"role": "transport_repair_quality_reverse", **call} for call in calls)
            if qf is None or qr is None:
                raise RuntimeError("transport repair quality rejudge incomplete")
            validate_response_excerpts(qf, responses)
            validate_response_excerpts(qr, responses)
            on_responses = [{"replicate_id": rep["replicate_id"], "response": rep["ON"]["reply"]} for rep in result["generated"]]
            _, functional, calls = BASE._judge_call(judge_client, BatchedFunctionalUseJudgment, functional_use_messages(visible_dialogue=source["visible_dialogue"], candidate=source["candidate"], on_responses=on_responses), seed=seed + 3, max_tokens=1800)
            repair_calls.extend({"role": "transport_repair_function", **call} for call in calls)
            if functional is None:
                raise RuntimeError("transport repair function rejudge incomplete")
            result["quality_forward"] = qf.model_dump(mode="json")
            result["quality_reverse"] = qr.model_dump(mode="json")
            result["quality_effect"] = aggregate_on_minus_off(qf, qr)
            result["functional"] = functional.model_dump(mode="json")
            result["call_records"].extend(repair_calls)
            result["transport_repair"] = {
                "status": "REPAIRED_IDENTICAL_STATE_AND_SEED",
                "archived_before_path": str(archive.relative_to(ROOT)),
            }
    finally:
        gen_client.close()
        judge_client.close()
    write_jsonl(archive, archived)
    write_jsonl(path, results)
    print({"remaining_transport_failed_groups": sum(_needs_repair(row) and not row.get("transport_repair") for row in results)})


if __name__ == "__main__":
    main()
