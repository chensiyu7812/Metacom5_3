#!/usr/bin/env python3
"""Validate sealed submissions and prepare offline teacher-reference diagnostics.

No provider call, adjudication of new items, PM label, or authority mutation.
Generated responses and individual rationales remain in ignored outputs only.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, sha256_file, sha256_text, write_json
from metacom_pm.paper1.api_budget import CumulativePaper1ApiBudgetLedger
from metacom_pm.paper1.evaluation.human_reference import read_rating_json, validate_rated_sheet
from metacom_pm.paper1.evaluation.pairwise_teacher import (
    build_pairwise_teacher_prompt, pairwise_teacher_identity_payload,
)
from metacom_pm.paper1.evaluation.teacher_diagnostics import index_presentations, reference_comparison
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config


class StaticFormData(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.active = False
        self.blocks = []

    def handle_starttag(self, tag, attrs):
        if tag == "script" and dict(attrs).get("id") == "form-data":
            self.active = True
            self.blocks.append("")

    def handle_data(self, data):
        if self.active:
            self.blocks[-1] += data

    def handle_endtag(self, tag):
        if tag == "script":
            self.active = False


def unique_object(pairs):
    value = {}
    for key, item in pairs:
        if key in value:
            raise ValueError("duplicate JSON key")
        value[key] = item
    return value


def jsonl(path):
    return [json.loads(line, object_pairs_hook=unique_object)
            for line in path.read_text().splitlines() if line.strip()]


def checked_hash(path, expected):
    actual = sha256_file(path)
    if actual != expected:
        raise ValueError(f"frozen source hash mismatch: {path.name}")
    return actual


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--human-a", type=Path, required=True)
    parser.add_argument("--ai-b-html", type=Path, required=True)
    parser.add_argument("--followup", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert_pre_outcome_locked(load_public_only_config(PROJECT / "configs/paper1_public_only.yaml"))
    authority = PROJECT / "data/paper1_authority"
    closeout_path = authority / "paper1_human_review_closeout_20260917_v1.json"
    closeout = read_rating_json(closeout_path)
    sources = {"human_A": args.human_a, "exploratory_AI_B": args.ai_b_html,
               "six_case_followup": args.followup}
    sources = {k: {"path": str(p.resolve()), "sha256": checked_hash(p, closeout["source_sha256"][k])}
               for k, p in sources.items()}
    manifest_path = authority / "paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json"
    manifest = read_rating_json(manifest_path)
    identity_path = authority / "paper1_gemini_pairwise_teacher_identity_20260908_v2.json"
    checked_hash(identity_path, manifest["teacher_identity_sha256"])
    identity = read_rating_json(identity_path)
    for key, value in pairwise_teacher_identity_payload().items():
        if value != identity["prompt_identity"][key]:
            raise ValueError("current teacher prompt/schema differs from frozen identity")

    html = StaticFormData()
    html.feed(args.ai_b_html.read_text())
    if len(html.blocks) != 1:
        raise ValueError("expected exactly one static form-data block")
    ai_b = json.loads(html.blocks[0], object_pairs_hook=unique_object)["sheet"]
    human_a = read_rating_json(args.human_a)
    counts = {}
    blanks = {}
    for role, rated in (("RATER_A", human_a), ("RATER_B", ai_b)):
        binding = manifest["sheets"][role]
        path = PROJECT / binding["path"]
        checked_hash(path, binding["sha256"])
        blanks[role] = read_rating_json(path)
        counts[role] = validate_rated_sheet(blanks[role], rated)
        if counts[role]["presentations"] != binding["presentations"]:
            raise ValueError("submission count differs from frozen manifest")
    a, b = index_presentations(human_a["items"]), index_presentations(ai_b["items"])
    blind_path = authority / "paper1_pairwise_teacher_blind_key_20260904_v1.jsonl"
    checked_hash(blind_path, manifest["source_sha256"]["blind_key"])
    blind = index_presentations(jsonl(blind_path))
    if not a.keys() == b.keys() == blind.keys():
        raise ValueError("presentation identity sets differ")
    for pid in a:
        for field in ("task", "task_input", "reference_material", "response_A", "response_B"):
            if a[pid][field] != b[pid][field]:
                raise ValueError("A/B presentation content or orientation differs")

    request_binding = identity["exact_request_manifest"]
    request_path = PROJECT / request_binding["path"]
    checked_hash(request_path, request_binding["sha256"])
    requests = jsonl(request_path)
    if index_presentations(requests).keys() != a.keys():
        raise ValueError("teacher requests differ from submitted presentations")
    for row in requests:
        item = a[row["presentation_id"]]
        prompt = build_pairwise_teacher_prompt(
            task=item["task"], task_input=item["task_input"],
            response_a=item["response_A"], response_b=item["response_B"],
            reference_material=item["reference_material"],
        )
        if row["body"]["contents"] != [{"parts": [{"text": prompt}], "role": "user"}]:
            raise ValueError("teacher input differs from the original English sheet")
        for field, text in (("body_sha256", canonical_json(row["body"])),
                            ("prompt_sha256", prompt)):
            if sha256_text(text) != row[field]:
                raise ValueError(f"teacher request {field} mismatch")
        reference_sha = sha256_text(item["reference_material"]) if item["reference_material"] is not None else None
        if row["reference_sha256"] != reference_sha:
            raise ValueError("teacher request reference hash mismatch")
        if row["request_model"] != identity["model"]["request_model"]:
            raise ValueError("teacher model drift")

    followup = read_rating_json(args.followup)
    f = index_presentations(followup["items"])
    cases = index_presentations(closeout["cases"])
    if f.keys() != cases.keys() or len(f) != 6:
        raise ValueError("six-case identity mismatch")
    rows = []
    for pid, item in a.items():
        row = {"presentation_id": pid, "item_number_A": item["item_number"],
               "item_number_AI_B": b[pid]["item_number"], "task": item["task"],
               "base_pair_id": blind[pid]["base_pair_id"], "A_arm": blind[pid]["A_arm"],
               "reverse_duplicate": blind[pid]["reverse_duplicate"],
               "reference_verdict": item["verdict"], "reference_rationale": item["rationale"],
               "candidate_verdict": b[pid]["verdict"], "candidate_rationale": b[pid]["rationale"]}
        if pid in f:
            if f[pid]["original_a_item_number"] != item["item_number"] or f[pid]["task"] != item["task"]:
                raise ValueError("followup item/task differs from its presentation")
            row["followup"] = f[pid]
            row["closeout"] = cases[pid]
        rows.append(row)
    human_followup, assistant_review = copy.deepcopy(rows), copy.deepcopy(rows)
    for row in human_followup:
        if row["presentation_id"] in f:
            row["reference_verdict"] = f[row["presentation_id"]]["verdict"]
    for row in assistant_review:
        if row["presentation_id"] in cases:
            row["reference_verdict"] = cases[row["presentation_id"]]["assistant_sensitivity_verdict"]
    missing_teacher = [{**r, "candidate_verdict": None} for r in rows]
    ledger_path = PROJECT / "outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl"
    if not ledger_path.exists():
        raise ValueError("existing cumulative cost ledger is required")
    ledger = CumulativePaper1ApiBudgetLedger(ledger_path)
    input_tokens = sum(r["offline_input_tokens_o200k_base"] for r in requests)
    output_tokens = sum(r["maximum_output_tokens"] for r in requests)
    estimate = (Decimal(input_tokens) * Decimal("0.10") + Decimal(output_tokens) * Decimal("0.40")) / 1000000
    result = {
        "protocol": "paper1-teacher-review-intake-result-v1", "date": "2026-09-17",
        "status": "OFFLINE_INPUTS_VALIDATED_TEACHER_EXECUTION_PENDING",
        "sources": sources, "closeout_sha256": sha256_file(closeout_path),
        "human_sheet_manifest_sha256": sha256_file(manifest_path),
        "validation": counts, "provenance": closeout["provenance"],
        "original_A_vs_exploratory_AI_B": reference_comparison(rows),
        "human_followup_vs_exploratory_AI_B": reference_comparison(human_followup),
        "assistant_fact_review_sensitivity_vs_exploratory_AI_B": reference_comparison(assistant_review),
        "sensitivity_limit": "Posthoc cases were discussed with AI findings visible; sensitivity is not independent validation or a new human reference.",
        "candidate_Gemini_vs_original_A": reference_comparison(missing_teacher),
        "teacher_request_preflight": {
            "path": request_binding["path"], "sha256": sha256_file(request_path),
            "presentations": len(requests), "by_task": dict(Counter(r["task"] for r in requests)),
            "English_payload_matches_sealed_sheets": True,
            "human_ratings_or_closeout_added_to_prompt": False,
            "offline_tokenizer": "o200k_base_proxy_not_provider_token_count",
            "estimated_first_attempts_usd": str(estimate), "retry_cost_included": False,
            "stage_hard_cap_usd": "0.10", "guaranteed_worst_case": False,
            "pending": ["reference-protocol scoped decision", "separate paid-call authorization",
                        "provider model metadata/countTokens and per-call budget reservations",
                        "resumable live runner implementation and mocked transport tests"]
        },
        "API_budget": {"ledger_sha256": sha256_file(ledger_path),
                       "accounted_cumulative_usd": str(ledger.accounted_cost_usd),
                       "remaining_usd": str(ledger.remaining_usd), "new_cost_usd": "0"},
        "training_labels_created": 0, "formal_outcome_calls": 0, "PM_training_runs": 0,
        "new_human_sheets": 0,
    }
    args.output.mkdir(parents=True, exist_ok=True)
    # All source reads/validation completed before any artifact writes.
    write_json(args.output / "reference_trace.json", rows)
    write_json(args.output / "intake_result.json", result)
    write_json(args.output / "closeout_record.json", closeout)
    print(json.dumps({"status": result["status"], "output": str(args.output),
                      "presentations": len(rows), "requests": len(requests),
                      "accounted_cumulative_usd": str(ledger.accounted_cost_usd)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
