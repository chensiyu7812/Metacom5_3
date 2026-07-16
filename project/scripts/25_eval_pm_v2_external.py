#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from metacom_pm.artifacts import (
    require_artifact_attestation,
    require_content_addressed_attestation,
)
from metacom_pm.config import endpoint_from_config, load_config
from metacom_pm.freeze import require_study_freeze
from metacom_pm.io import canonical_json, sha256_file, sha256_text
from metacom_pm.pm_v2_external_eval import (
    expected_external_units,
    run_external_response_evaluation,
)
from metacom_pm.pm_v2_evoemo import compare_observed_cost_matched_turns
from metacom_pm.pm_v2_external_schema_smoke import (
    require_external_pointwise_schema_smoke_pass,
)
from metacom_pm.pm_v2_judging import (
    composite_spec_from_config,
    labeling_settings_from_config,
)
from metacom_pm.pm_v2_forced_swap import require_forced_swap_key_claim

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--run", action="store_true")
    parser.add_argument("--config", type=Path, default=ROOT / "configs" / "experiment.yaml")
    parser.add_argument("--pm-v2-config", type=Path, default=ROOT / "configs" / "pm_v2.yaml")
    parser.add_argument("--freeze", type=Path, default=ROOT / "outputs" / "pm_v2_study_freeze.json")
    parser.add_argument("--evoemo", type=Path, default=ROOT / "data" / "external" / "evo_emo.json")
    parser.add_argument(
        "--turn-paths",
        type=Path,
        nargs="+",
        default=[
            ROOT / "outputs" / "evoemo_selective" / "turns.jsonl",
            ROOT / "outputs" / "evoemo_pm_v2" / "turns.jsonl",
            ROOT / "outputs" / "evoemo_pm_v2_cost_matched_fixed" / "turns.jsonl",
            ROOT / "outputs" / "evoemo_pm_v2_me_r0_fixed" / "turns.jsonl",
        ],
    )
    parser.add_argument(
        "--generation-attestations",
        type=Path,
        nargs="+",
        default=[
            ROOT / "outputs" / "evoemo_selective" / "artifact_attestation.json",
            ROOT / "outputs" / "evoemo_pm_v2" / "artifact_attestation.json",
            ROOT / "outputs" / "evoemo_pm_v2_cost_matched_fixed" / "artifact_attestation.json",
            ROOT / "outputs" / "evoemo_pm_v2_me_r0_fixed" / "artifact_attestation.json",
        ],
    )
    parser.add_argument("--out-dir", type=Path, default=ROOT / "outputs" / "pm_v2_external_response")
    parser.add_argument("--max-api-calls", type=int, default=6000)
    parser.add_argument("--max-estimated-usd", type=float, default=20.0)
    parser.add_argument("--max-input-tokens-per-call", type=int, default=12000)
    parser.add_argument("--accept-cost-estimate-sha256")
    parser.add_argument(
        "--key-claim-verification",
        type=Path,
        default=ROOT / "outputs" / "pm_v2_forced_swap" / "summary.json",
    )
    parser.add_argument(
        "--key-claim-verification-attestation",
        type=Path,
        default=ROOT
        / "outputs"
        / "pm_v2_forced_swap"
        / "artifact_attestation.json",
    )
    parser.add_argument(
        "--pointwise-schema-smoke-summary",
        type=Path,
        default=ROOT
        / "outputs"
        / "pm_v2_external_pointwise_schema_smoke"
        / "summary.json",
    )
    parser.add_argument(
        "--pointwise-schema-smoke-attestation",
        type=Path,
        default=ROOT
        / "outputs"
        / "pm_v2_external_pointwise_schema_smoke"
        / "artifact_attestation.json",
    )
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    if args.run and args.overwrite:
        raise RuntimeError(
            "paid API runs prohibit --overwrite; use a new output directory"
        )

    config = load_config(args.config)
    pm_v2_config = load_config(args.pm_v2_config)
    verification = require_study_freeze(
        args.freeze,
        release_root=ROOT,
        config_path=args.config,
        required_files=[args.pm_v2_config, args.evoemo],
    )
    freeze_data = json.loads(args.freeze.read_text(encoding="utf-8"))
    freeze_sha = str(verification["freeze_sha256"])
    external_contract = (freeze_data.get("notes") or {}).get(
        "external_evaluation_contract"
    ) or {}
    generation_contract = (freeze_data.get("notes") or {}).get("generation_contract") or {}
    expected_external_estimand = {
        "external_estimand": "quality_risk_observed_cost_componentwise_pareto_v1",
        "risk_composite_basis": "requested_action_applicable_fields",
        "single_external_utility_claim_allowed": False,
    }
    for key, expected in expected_external_estimand.items():
        if external_contract.get(key) != expected:
            raise RuntimeError(f"study freeze external estimand mismatch: {key}")
    fixed_baseline_artifacts = external_contract.get("fixed_baseline_artifacts") or {}
    if not bool(external_contract.get("require_raw_per_family_health")):
        raise RuntimeError("study freeze does not require raw per-family judge health")
    frozen_conditions = [str(value) for value in external_contract.get("conditions") or []]
    if not frozen_conditions:
        raise RuntimeError("study freeze lacks an external condition matrix")
    conditions = frozen_conditions
    treatment = str(external_contract.get("treatment") or "")
    judge_seed = int(external_contract.get("judge_seed"))
    labeling = labeling_settings_from_config(pm_v2_config)
    for key in (
        "composite_support_exact_match_rate",
        "maximum_absolute_composite_support_correlation",
    ):
        if float(labeling[key]) != float(external_contract[key]):
            raise RuntimeError(f"external composite/support gate changed after freeze: {key}")
    turn_indices = [
        int(value) for value in external_contract.get("turn_indices") or []
    ]
    evaluation_unit_contract = dict(
        external_contract.get("evaluation_unit_contract") or {}
    )
    if evaluation_unit_contract != generation_contract.get(
        "evaluation_unit_contract"
    ):
        raise RuntimeError("generation/external evaluation-unit contracts differ")
    if len(args.turn_paths) != len(args.generation_attestations):
        raise ValueError("each turn path requires one generation attestation")
    attested_conditions = set()
    fixed_conditions_verified: set[str] = set()
    turn_path_by_condition: dict[str, Path] = {}
    for turn_path, attestation_path in zip(args.turn_paths, args.generation_attestations):
        attestation = json.loads(attestation_path.read_text(encoding="utf-8"))
        stage = str(attestation.get("stage") or "")
        if stage == "evoemo_generation":
            baseline_dir = turn_path.resolve().parent
            result = require_content_addressed_attestation(
                attestation_path,
                required_stage="evoemo_generation",
                relocated_inputs={
                    "evoemo": args.evoemo,
                    "run_manifest": baseline_dir / "run_manifest.json",
                    "fixed_tracks": ROOT
                    / "outputs"
                    / "evoemo_fixed_tracks"
                    / "fixed_seeker_tracks.jsonl",
                    "fixed_tracks_attestation": ROOT
                    / "outputs"
                    / "evoemo_fixed_tracks"
                    / "artifact_attestation.json",
                    "checkpoint": ROOT
                    / "outputs"
                    / "final_model_m2b_stable"
                    / "pm_final.joblib",
                    "selection": ROOT / "outputs" / "selection_stable.json",
                    "strategy_bank": ROOT
                    / "data"
                    / "strategy"
                    / "strategy_cards.jsonl",
                },
                relocated_outputs={
                    "turns": turn_path,
                    "summary": baseline_dir / "generation_summary.json",
                },
            )
        else:
            result = require_artifact_attestation(
                attestation_path,
                required_output_paths={"turns": turn_path},
            )
        parameters = attestation.get("parameters") or {}
        values = parameters.get("conditions") or [parameters.get("condition")]
        attested_conditions.update(str(value) for value in values if value)
        if len(values) == 1 and values[0]:
            condition = str(values[0])
            if condition in turn_path_by_condition:
                raise RuntimeError(f"duplicate generation turn input for {condition}")
            turn_path_by_condition[condition] = turn_path
        if stage == "evoemo_pm_v2_generation" and result.get(
            "study_freeze_sha256"
        ) != freeze_sha:
            raise RuntimeError("PM-v2 generation attestation uses a different study freeze")
        frozen_parameter_checks = [
            ("protocol", generation_contract.get("protocol")),
            ("simulator_id", generation_contract.get("simulator_id")),
            ("max_turns", generation_contract.get("max_turns")),
            ("seeds", generation_contract.get("seeds")),
        ]
        if stage == "evoemo_pm_v2_generation":
            frozen_parameter_checks.extend(
                [
                    (
                        "maximum_cost_matched_relative_deviation",
                        generation_contract.get(
                            "maximum_cost_matched_relative_deviation"
                        ),
                    ),
                    (
                        "generator_retries",
                        generation_contract.get("generator_retries"),
                    ),
                    (
                        "generator_pricing_usd_per_mtok",
                        generation_contract.get(
                            "generator_pricing_usd_per_mtok"
                        ),
                    ),
                    (
                        "input_token_safety_factor",
                        generation_contract.get("input_token_safety_factor"),
                    ),
                    (
                        "fail_on_reported_input_overrun",
                        generation_contract.get("fail_on_reported_input_overrun"),
                    ),
                    (
                        "evaluation_unit_contract",
                        generation_contract.get("evaluation_unit_contract"),
                    ),
                    (
                        "paid_generation_scope",
                        generation_contract.get("paid_generation_scope"),
                    ),
                ]
            )
        for key, expected in frozen_parameter_checks:
            if parameters.get(key) != expected:
                raise RuntimeError(
                    f"generation attestation {attestation_path} violates frozen {key}"
                )
        if stage == "evoemo_generation":
            manifest_path = turn_path.resolve().parent / "run_manifest.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            endpoint_contract = {
                "model": str(manifest.get("generator_model") or ""),
                "family": str(manifest.get("generator_family") or ""),
                "base_url": str(manifest.get("generator_base_url") or ""),
            }
            for condition in (str(value) for value in values if value):
                frozen_artifact = fixed_baseline_artifacts.get(condition)
                if frozen_artifact is None:
                    continue
                exact_checks = {
                    "stage": stage,
                    "turns_sha256": sha256_file(turn_path),
                    "attestation_sha256": result["attestation_sha256"],
                    "attestation_file_sha256": sha256_file(attestation_path),
                    "run_manifest_sha256": sha256_file(manifest_path),
                    "generator_endpoint": endpoint_contract,
                    "generator_endpoint_sha256": sha256_text(
                        canonical_json(endpoint_contract)
                    ),
                    "protocol": parameters.get("protocol"),
                    "simulator_id": parameters.get("simulator_id"),
                    "max_turns": parameters.get("max_turns"),
                    "seeds": parameters.get("seeds"),
                }
                for key, actual in exact_checks.items():
                    if frozen_artifact.get(key) != actual:
                        raise RuntimeError(
                            f"fixed external baseline artifact mismatch: "
                            f"{condition}/{key}"
                        )
                fixed_conditions_verified.add(condition)
    if set(conditions) - attested_conditions:
        raise RuntimeError("generation attestations do not cover the frozen conditions")
    if set(fixed_baseline_artifacts) != fixed_conditions_verified:
        raise RuntimeError(
            "fixed external baselines are not all backed by their frozen legacy "
            "turn/attestation artifacts"
        )
    frozen_judges = external_contract.get("judge_endpoints") or []
    frozen_names = [str(row["name"]) for row in frozen_judges]
    endpoints = [endpoint_from_config(config, name) for name in frozen_names]
    for endpoint, frozen in zip(endpoints, frozen_judges):
        current_sha = sha256_text(
            canonical_json(
                {
                    "model": endpoint.model,
                    "family": endpoint.family,
                    "base_url": endpoint.base_url,
                }
            )
        )
        if current_sha != frozen.get("sha256"):
            raise RuntimeError("judge endpoint contract changed after study freeze")
    full_expected_units = expected_external_units(
        args.evoemo,
        seeds=[int(value) for value in generation_contract["seeds"]],
        simulator_id=str(generation_contract["simulator_id"]),
        turn_indices=turn_indices,
    )
    if (
        evaluation_unit_contract.get("evaluation_turn_indices") != turn_indices
        or evaluation_unit_contract.get("expected_unit_count")
        != len(full_expected_units)
        or evaluation_unit_contract.get("expected_units_sha256")
        != sha256_text(canonical_json(full_expected_units))
    ):
        raise RuntimeError("frozen external evaluation-unit universe is stale")
    forced_contract = external_contract.get("forced_swap") or {}
    if not bool(forced_contract.get("exclude_sample_from_full_evaluation")):
        raise RuntimeError("study freeze does not require pilot/full sample separation")
    forced_verification = require_forced_swap_key_claim(
        args.key_claim_verification,
        args.key_claim_verification_attestation,
        study_freeze_sha256=freeze_sha,
        full_expected_units=full_expected_units,
        forced_contract=forced_contract,
    )
    pointwise_schema_smoke_contract = external_contract.get(
        "pointwise_schema_smoke"
    ) or {}
    pointwise_schema_smoke_verification = (
        require_external_pointwise_schema_smoke_pass(
            args.pointwise_schema_smoke_summary,
            args.pointwise_schema_smoke_attestation,
            study_freeze_sha256=freeze_sha,
            contract=pointwise_schema_smoke_contract,
            forced_swap_selected_units_sha256=sha256_text(
                canonical_json(sorted(forced_verification["excluded_units"]))
            ),
        )
    )
    excluded_units = set(forced_verification["excluded_units"])
    expected_units = [
        unit for unit in full_expected_units if unit not in excluded_units
    ]
    if len(expected_units) + len(excluded_units) != len(full_expected_units):
        raise RuntimeError("pilot/full external unit partition is not exact")
    cost_match_tolerance = float(
        external_contract["maximum_cost_matched_relative_deviation"]
    )
    try:
        observed_cost_match = compare_observed_cost_matched_turns(
            turn_path_by_condition["pm_v2"],
            turn_path_by_condition["pm_v2_cost_matched_fixed"],
            maximum_relative_deviation=cost_match_tolerance,
            expected_units=expected_units,
        )
    except KeyError as exc:
        raise RuntimeError(
            "full external evaluation lacks the learned/fixed cost-match turn pair"
        ) from exc
    if observed_cost_match["status"] != "PASS":
        raise RuntimeError(
            "observed PM-v2 versus fixed input-token deviation exceeds the frozen limit"
        )
    result = run_external_response_evaluation(
        evoemo_path=args.evoemo,
        turn_paths=args.turn_paths,
        conditions=conditions,
        treatment=treatment,
        turn_indices=turn_indices,
        endpoints=endpoints,
        out_dir=args.out_dir,
        run=bool(args.run),
        max_api_calls=args.max_api_calls,
        expected_units=expected_units,
        full_expected_units=full_expected_units,
        composite_spec=composite_spec_from_config(pm_v2_config),
        labeling=labeling,
        minimum_low_mad_coverage_per_dimension=float(
            external_contract["minimum_low_mad_coverage_per_dimension"]
        ),
        minimum_low_mad_coverage_per_condition_dimension=float(
            external_contract[
                "minimum_low_mad_coverage_per_condition_dimension"
            ]
        ),
        required_conditions=frozen_conditions,
        generation_attestation_paths=args.generation_attestations,
        study_freeze_sha256=freeze_sha,
        require_key_claim_verification=bool(
            external_contract.get("require_forced_swap_or_human_check_for_key_claims")
        ),
        key_claim_verification_path=args.key_claim_verification,
        key_claim_verification_attestation_path=(
            args.key_claim_verification_attestation
        ),
        excluded_unit_ids=forced_verification["excluded_unit_ids"],
        pilot_selection_contract_sha256=forced_verification[
            "sample_selection_contract_sha256"
        ],
        full_expected_units_sha256=sha256_text(canonical_json(full_expected_units)),
        observed_cost_match_report=observed_cost_match,
        accept_cost_estimate_sha256=args.accept_cost_estimate_sha256,
        max_estimated_usd=args.max_estimated_usd,
        max_input_tokens_per_call=args.max_input_tokens_per_call,
        pricing_usd_per_mtok=external_contract["judge_pricing_usd_per_mtok"],
        api_cost_planning=external_contract["api_cost_planning"],
        primary_bootstrap_cluster=str(
            external_contract["primary_bootstrap_cluster"]
        ),
        sensitivity_bootstrap_cluster=str(
            external_contract["sensitivity_bootstrap_cluster"]
        ),
        pointwise_schema_smoke_summary_path=args.pointwise_schema_smoke_summary,
        pointwise_schema_smoke_attestation_path=(
            args.pointwise_schema_smoke_attestation
        ),
        pointwise_schema_smoke_verification=pointwise_schema_smoke_verification,
        estimated_response_output_tokens=int(
            pointwise_schema_smoke_contract[
                "estimated_response_output_tokens"
            ]
        ),
        estimated_risk_output_tokens=int(
            pointwise_schema_smoke_contract["estimated_risk_output_tokens"]
        ),
        overwrite=args.overwrite,
        seed=judge_seed,
    )
    print(result)


if __name__ == "__main__":
    main()
