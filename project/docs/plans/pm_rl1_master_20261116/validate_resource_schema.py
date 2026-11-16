#!/usr/bin/env python3
"""Validate the design schema with synthetic structural fixtures only.

These in-memory fixtures are NOT research examples, labels or generated data.
They intentionally use placeholder identities. This script does not establish
source hashes, semantic fidelity, chronological eligibility or reward validity.

Run with the existing environment (no installation or model loading needed):
  /opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python \
      project/docs/plans/pm_rl1_master_20261116/validate_resource_schema.py
"""
import argparse
import copy
import datetime
import json
import re
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker


def structural_value(spec, definitions):
    """Create placeholder values, never corpus contents or semantic truth."""
    if "$ref" in spec:
        return structural_value(definitions[spec["$ref"].split("/")[-1]], definitions)
    if "const" in spec:
        return spec["const"]
    if "enum" in spec:
        return spec["enum"][0]
    if "anyOf" in spec:
        return structural_value(spec["anyOf"][0], definitions)
    kind = spec.get("type")
    if isinstance(kind, list):
        kind = kind[0]
    if kind == "object":
        return {key: structural_value(spec["properties"][key], definitions)
                for key in spec.get("required", [])}
    if kind == "array":
        return [structural_value(spec["items"], definitions)
                for _ in range(spec.get("minItems", 0))]
    if kind == "string":
        if spec.get("format") == "date-time":
            return "2026-11-16T01:00:00+09:00"
        return "0" * 64 if "pattern" in spec else "STRUCTURE_FIXTURE_ONLY"
    if kind in ("integer", "number"):
        return spec.get("minimum", 0)
    if kind == "boolean":
        return False
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schema", type=Path,
                        default=Path(__file__).with_name("resource_schemas.json"))
    args = parser.parse_args()
    schema = json.loads(args.schema.read_text())
    Draft202012Validator.check_schema(schema)
    formats = FormatChecker()

    @formats.checks("date-time", raises=ValueError)
    def valid_timestamp(value):
        # jsonschema's optional RFC3339 dependency is absent in this existing
        # environment. Explicitly validate the timezone-bearing timestamps
        # used by this contract instead of silently skipping format checks.
        if not isinstance(value, str):
            return True
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}[Tt]\d{2}:\d{2}:\d{2}"
                            r"(?:\.\d+)?(?:[Zz]|[+-]\d{2}:\d{2})", value):
            return False
        timestamp = datetime.datetime.fromisoformat(value.upper().replace("Z", "+00:00"))
        return timestamp.tzinfo is not None

    validator = Draft202012Validator(schema, format_checker=formats)
    definitions = schema["$defs"]
    valid, invalid = {}, {}

    # Seven resource variants plus source, provenance, index and pending
    # evaluation are the original eleven structural acceptance fixtures.
    for variant in definitions["resource_record"]["oneOf"]:
        record = structural_value(definitions["resource_record"], definitions)
        for key, spec in variant["properties"].items():
            if key != "availability":
                record[key] = structural_value(spec, definitions)
        if record["head"] != "RS":
            record["availability"]["source_session_rank"] = 0
        if record["head"] == "MS":
            record["availability"]["source_complete"] = True
        name = record["representation"]
        valid[name] = record
        wrong = copy.deepcopy(record)
        wrong["head"] = "MS" if record["head"] != "MS" else "RS"
        invalid[name + "_wrong_head"] = wrong

    for kind in ("source_record", "provenance_record", "index_record"):
        valid[kind] = structural_value(definitions[kind], definitions)

    pending = structural_value(definitions["evaluation_record"], definitions)
    pending.update(status="pending_generation", measurement_mode="paired_off",
                   request_identity="TARGET_REQUEST_FIXTURE",
                   actual_reply_sha256=None, judgment=None, score=None,
                   baseline_request_identity="OFF_REQUEST_FIXTURE",
                   baseline_actual_reply_sha256=None)
    valid["pending_generation"] = pending
    original_fixture_count = len(valid)
    assert original_fixture_count == 11

    # Direct OFF comparisons need both reply identities when measured.
    for judgment, score in (("better", 1), ("equivalent", 0), ("worse", -1)):
        measured = copy.deepcopy(pending)
        measured.update(status="measured", judgment=judgment, score=score,
                        actual_reply_sha256="1" * 64,
                        baseline_actual_reply_sha256="2" * 64)
        valid["paired_off_" + judgment] = measured

    no_reward_yet = copy.deepcopy(valid["paired_off_better"])
    no_reward_yet["score"] = None
    valid["paired_label_without_reward_conversion"] = no_reward_yet

    absolute = copy.deepcopy(valid["paired_off_better"])
    absolute.update(measurement_mode="absolute", judgment=None, score=3.0,
                    baseline_request_identity=None,
                    baseline_actual_reply_sha256=None)
    valid["absolute_measurement"] = absolute

    pending_score = copy.deepcopy(pending)
    pending_score.update(status="pending_score", actual_reply_sha256="1" * 64)
    valid["pending_score"] = pending_score

    uncertain = copy.deepcopy(valid["paired_off_better"])
    uncertain.update(status="completed_uncertain", judgment="uncertain",
                     score=None, semantic_review_round=1)
    valid["completed_uncertain_pair"] = uncertain
    uncertain_absolute = copy.deepcopy(absolute)
    uncertain_absolute.update(status="completed_uncertain", judgment="uncertain",
                              score=None, semantic_review_round=1)
    valid["completed_uncertain_absolute"] = uncertain_absolute

    bad = copy.deepcopy(pending)
    bad["score"] = 0
    invalid["missing_measurement_filled_with_zero"] = bad
    bad = copy.deepcopy(pending)
    bad["hidden_gold"] = "FORBIDDEN_EXTRA_FIELD"
    invalid["evaluation_extra_field"] = bad
    bad = copy.deepcopy(pending_score)
    bad["actual_reply_sha256"] = None
    invalid["pending_score_without_actual_reply"] = bad
    bad = copy.deepcopy(valid["paired_off_better"])
    bad["baseline_actual_reply_sha256"] = None
    invalid["measured_pair_without_baseline_reply"] = bad
    bad = copy.deepcopy(valid["paired_off_better"])
    bad["score"] = -1
    invalid["paired_judgment_reward_sign_mismatch"] = bad
    bad = copy.deepcopy(absolute)
    bad["baseline_request_identity"] = "UNDECLARED_COMPARATOR"
    invalid["absolute_measurement_with_hidden_comparator"] = bad
    bad = copy.deepcopy(valid["ms_sum_v1"])
    bad["source_refs"].append(copy.deepcopy(bad["source_refs"][0]))
    invalid["session_summary_from_multiple_sources"] = bad
    bad = copy.deepcopy(valid["ms_sum_v1"])
    bad["availability"]["source_complete"] = False
    invalid["session_summary_from_incomplete_source"] = bad
    bad = copy.deepcopy(valid["rs_method_v1"])
    bad["owner_id"] = "PRIVATE_OWNER"
    invalid["global_RS_owner_binding"] = bad
    bad = copy.deepcopy(valid["ms_sum_v1"])
    bad["reading_view"]["gold_score"] = 1
    invalid["reader_extra_evaluation_field"] = bad
    bad = copy.deepcopy(valid["ms_sum_v1"])
    bad["availability"]["built_at"] = "NOT_A_TIMESTAMP"
    invalid["invalid_build_timestamp"] = bad
    bad = copy.deepcopy(uncertain)
    bad["score"] = 0
    invalid["completed_uncertain_filled_with_zero"] = bad
    bad = copy.deepcopy(uncertain)
    bad["baseline_actual_reply_sha256"] = None
    invalid["completed_uncertain_pair_without_baseline_reply"] = bad
    bad = copy.deepcopy(uncertain)
    bad["semantic_review_round"] = 2
    invalid["unbounded_semantic_rereview"] = bad

    for name, record in valid.items():
        errors = sorted(validator.iter_errors(record), key=lambda error: str(error.path))
        if errors:
            raise AssertionError(f"Expected valid fixture {name}: {errors[0].message}")
    for name, record in invalid.items():
        if validator.is_valid(record):
            raise AssertionError(f"Expected rejected fixture accepted: {name}")

    print(json.dumps({
        "status": "PASS_SCHEMA_STRUCTURE_ONLY",
        "metaschema": "Draft 2020-12; format checks enabled",
        "original_legal_fixtures": original_fixture_count,
        "additional_feedback_fixtures": len(valid) - original_fixture_count,
        "legal_fixtures_total": len(valid),
        "resource_variants": 7,
        "rejection_fixtures": len(invalid),
        "rejected_cases": sorted(invalid),
        "fixtures_are_research_samples": False,
        "not_validated": ["real source hashes and cross-record identity",
                          "semantic support and summary completeness",
                          "strict-past eligibility and family isolation",
                          "runtime Observation sanitization",
                          "same-prefix and same-G paired OFF binding",
                          "natural-support benefit or reward qualification"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
