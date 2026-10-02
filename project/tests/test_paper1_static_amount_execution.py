from __future__ import annotations

import importlib.util
import json
from decimal import Decimal
from pathlib import Path

import pytest

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json, write_jsonl

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts/paper1"


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


generation = load("static_amount_generation", "79_run_static_amount_generation.py")
scoring = load("static_official_scoring_runner", "80_execute_official_static_scoring.py")
analysis = load("static_amount_analysis", "81_analyze_static_amount_calibration.py")

GENERATOR_CONFIG = {"model": "meta/llama-3.1-8b-instruct", "native_context_tokens": 131072, "seed": 0}


def messages(text: str) -> list[dict]:
    return [{"role": "user", "content": text}]


def build_package(root: Path, *, targets=("t1", "t2")) -> Path:
    """A miniature package with the same identity structure as the real one."""
    package = root / "package"
    package.mkdir(parents=True)
    write_json(package / "generator_config.json", GENERATOR_CONFIG)
    config_hash = sha256_text(canonical_json(GENERATOR_CONFIG))
    requests, design = [], []
    for index, target in enumerate(targets):
        for head, k in [(None, 0), ("MP", 1), ("MP", 2), ("MP", 3), ("MP", 4)]:
            body = messages(f"{target}|{head}|{k}")
            request_hash = sha256_text(canonical_json(
                {"generator_config_sha256": config_hash, "messages": body}))
            request_id = f"amount_gen_{target}_{head}_{k}"
            row = {"request_id": request_id, "request_sha256": request_hash,
                   "generator_config_sha256": config_hash, "target_id": target, "task": "qa",
                   "owner_id": f"p{index}", "outer_fold": index, "group_component_id": f"c{index}",
                   "analysis_weight": 1, "inclusion_probability": 1.0, "head": head, "k": k,
                   "messages": body, "input_tokens": 100 + k, "rendered_resource_tokens": k,
                   "candidate_ids": [], "candidate_content_sha256": [],
                   "microblock_index": index, "within_microblock_index": k}
            requests.append(row)
            for analytical_head in ([head] if head else ["MP"]):
                design.append({key: row[key] for key in
                               ["request_id", "target_id", "task", "owner_id", "outer_fold",
                                "group_component_id", "analysis_weight", "k", "input_tokens"]}
                              | {"head": analytical_head})
    write_jsonl(package / "generator_requests.jsonl", requests)
    write_jsonl(package / "analytical_design.jsonl", design)
    write_json(package / "scorer_config.json", {
        "model": "gpt-4o-2024-11-20", "provider_max_output_tokens": 16384, "context_tokens": 128000,
        "project_retry_max": 1, "temperature": "OMITTED_AS_UPSTREAM",
        "max_completion_tokens": "OMITTED_AS_UPSTREAM",
        "source_sha256": {"qa": "x", "summary": "y"}, "new_paid_execution_authorized": False})
    write_json(package / "preparation_summary.json", {
        "generator_calls": len(requests), "sample_targets": len(targets),
        "package_artifacts": {p.name: sha256_file(p) for p in sorted(package.glob("*.json*"))
                              if p.name != "preparation_summary.json"}})
    return package


def test_package_loader_accepts_the_prepared_identity_and_counts_one_shared_off_per_target(tmp_path):
    package = build_package(tmp_path)
    summary, requests = generation.load_package(package)
    assert summary["generator_calls"] == len(requests) == 10
    assert sum(1 for r in requests if r["head"] is None) == 2


def test_package_loader_rejects_a_file_changed_after_preparation(tmp_path):
    package = build_package(tmp_path)
    rows = [json.loads(line) for line in (package / "generator_requests.jsonl").read_text().splitlines()]
    rows[0]["input_tokens"] = 999
    write_jsonl(package / "generator_requests.jsonl", rows)
    with pytest.raises(RuntimeError, match="changed since preparation"):
        generation.load_package(package)


def test_package_loader_rejects_messages_that_do_not_match_their_request_hash(tmp_path):
    package = build_package(tmp_path)
    rows = [json.loads(line) for line in (package / "generator_requests.jsonl").read_text().splitlines()]
    rows[0]["messages"] = messages("silently edited prompt")
    write_jsonl(package / "generator_requests.jsonl", rows)
    summary = json.loads((package / "preparation_summary.json").read_text())
    summary["package_artifacts"]["generator_requests.jsonl"] = sha256_file(
        package / "generator_requests.jsonl")
    write_json(package / "preparation_summary.json", summary)
    with pytest.raises(RuntimeError, match="does not match its messages"):
        generation.load_package(package)


def test_two_targets_never_share_one_off_row(tmp_path):
    package = build_package(tmp_path)
    rows = [json.loads(line) for line in (package / "generator_requests.jsonl").read_text().splitlines()]
    for row in rows:
        if row["head"] is None:
            row["target_id"] = "t1"
    write_jsonl(package / "generator_requests.jsonl", rows)
    summary = json.loads((package / "preparation_summary.json").read_text())
    summary["package_artifacts"]["generator_requests.jsonl"] = sha256_file(
        package / "generator_requests.jsonl")
    write_json(package / "preparation_summary.json", summary)
    with pytest.raises(RuntimeError, match="shared true-OFF"):
        generation.load_package(package)


def write_generations(package: Path, out: Path, *, finish="stop", only=None):
    rows = [json.loads(line) for line in (package / "generator_requests.jsonl").read_text().splitlines()]
    (out / "responses").mkdir(parents=True, exist_ok=True)
    for row in rows:
        if only is not None and row["request_id"] not in only:
            continue
        write_json(out / "responses" / (row["request_id"] + ".json"), {
            "request_id": row["request_id"], "request_sha256": row["request_sha256"],
            "target_id": row["target_id"], "task": row["task"], "raw_output": "an answer",
            "output_tokens": 12, "finish_reason": finish, "natural_end": finish == "stop",
            "status": "COMPLETED" if finish == "stop" else "INCOMPLETE", "seconds": 1.0})
    return out


def write_scores(package: Path, out: Path, *, quality_by_k=None, status="SCORED"):
    rows = [json.loads(line) for line in (package / "generator_requests.jsonl").read_text().splitlines()]
    (out / "scores").mkdir(parents=True, exist_ok=True)
    for row in rows:
        quality = (quality_by_k or {}).get(row["k"], 0.5)
        official = ({"task": "qa", "official_score": 1, "primary_metric": "official_llm_as_a_judge_score_normalized",
                     "quality": quality} if status == "SCORED" else None)
        write_json(out / "scores" / (row["request_id"] + ".json"), {
            "request_id": row["request_id"], "target_id": row["target_id"], "task": row["task"],
            "call_hash": "hash_" + row["request_id"], "status": status, "official": official})
    return out


def test_analysis_reports_real_coverage_and_never_writes_an_unobserved_score(tmp_path):
    package = build_package(tmp_path)
    rows, coverage = analysis.collect(package, tmp_path / "gen", tmp_path / "score")
    assert coverage["analytical_rows"] == len(rows) == 10
    assert coverage["rows_with_quality"] == 0
    assert coverage["row_gaps_by_reason"] == {"not_generated": 10}
    assert all(r["quality"] is None for r in rows)


def test_an_incomplete_generation_is_a_disclosed_gap_rather_than_a_zero(tmp_path):
    package = build_package(tmp_path)
    write_generations(package, tmp_path / "gen", finish="timeout")
    write_scores(package, tmp_path / "score")
    rows, coverage = analysis.collect(package, tmp_path / "gen", tmp_path / "score")
    assert coverage["rows_with_quality"] == 0
    assert coverage["row_gaps_by_reason"] == {"generation_timeout": 10}
    assert coverage["generations_incomplete"] == {"timeout": 10}
    assert all(r["quality"] is None for r in rows)


def test_an_official_parse_failure_is_a_disclosed_gap_rather_than_a_zero(tmp_path):
    package = build_package(tmp_path)
    write_generations(package, tmp_path / "gen")
    write_scores(package, tmp_path / "score", status="OFFICIAL_PARSE_FAILED")
    rows, coverage = analysis.collect(package, tmp_path / "gen", tmp_path / "score")
    assert coverage["official_scores_parsed"] == 0
    assert coverage["row_gaps_by_reason"] == {"official_official_parse_failed": 10}
    assert all(r["quality"] is None for r in rows)


def test_scores_join_through_the_shared_off_response_without_regenerating_it(tmp_path):
    package = build_package(tmp_path)
    write_generations(package, tmp_path / "gen")
    write_scores(package, tmp_path / "score", quality_by_k={0: 0.1, 1: 0.9, 2: 0.9, 3: 0.9, 4: 0.9})
    rows, coverage = analysis.collect(package, tmp_path / "gen", tmp_path / "score")
    assert coverage["rows_with_quality"] == 10
    assert coverage["generations_present"] == 10
    off_rows = [r for r in rows if r["k"] == 0]
    assert len(off_rows) == 2 and {r["quality"] for r in off_rows} == {0.1}


def test_analysis_rejects_a_generation_that_belongs_to_another_package(tmp_path):
    package = build_package(tmp_path)
    other = build_package(tmp_path / "other", targets=("t1", "t2"))
    out = write_generations(other, tmp_path / "gen")
    stray = json.loads((out / "responses" / "amount_gen_t1_MP_1.json").read_text())
    stray["request_sha256"] = "0" * 64
    write_json(out / "responses" / "amount_gen_t1_MP_1.json", stray)
    with pytest.raises(RuntimeError, match="does not belong to this package"):
        analysis.collect(package, out, tmp_path / "score")


def test_scoring_worst_case_reserves_the_full_native_output_allowance(tmp_path):
    package = build_package(tmp_path)
    scorer_config = json.loads((package / "scorer_config.json").read_text())
    payload = {"estimated_input_tokens_with_framing_reserve": 1000}
    expected = (Decimal(1000) * Decimal("2.5") + Decimal(16384) * Decimal("10")) / Decimal(1_000_000)
    assert scoring.worst_case_usd(payload, scorer_config) == expected
    assert scoring.observed_usd({"prompt_tokens": 1000, "completion_tokens": 10}) < expected


def test_scoring_cost_manifest_counts_measured_prediction_inputs(tmp_path):
    package = build_package(tmp_path)
    scorer_config = json.loads((package / "scorer_config.json").read_text())

    class FakeLedger:
        accounted_cost_usd = Decimal("1.5")
        remaining_usd = Decimal("48.5")

        def accounted_stage_cost_usd(self, stage):
            return Decimal("0")

    payloads = [{"task": "qa", "call_hash": f"h{i}",
                 "estimated_input_tokens_with_framing_reserve": 500 + i} for i in range(3)]
    costs = scoring.cost_manifest({}, payloads, scorer_config, FakeLedger())
    assert costs["official_calls_to_make"] == 3
    assert costs["observed_total_input_tokens"] == 500 + 501 + 502
    assert costs["input_token_counts_are_measured_from_real_predictions"] is True
    assert costs["output_cost_is_unknown_until_executed"] is True
