#!/usr/bin/env python3
"""Descriptive response characteristics and source-bound case cards, not labels."""
from __future__ import annotations

import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, write_json, sha256_file


def main():
    root = PROJECT / "outputs/paper1_pairwise_teacher"
    current = root / "local_comparison_20260917_v2"
    binding = read_json(PROJECT / "data/paper1_authority/paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json")["sheets"]["RATER_A"]
    source = PROJECT / binding["path"]
    assert sha256_file(source) == binding["sha256"]
    items = {r["presentation_id"]: r for r in read_json(source)["items"]}
    references = read_json(root / "gemini_qualification_v2/aligned_results.json")
    counts = defaultdict(Counter)
    examples = {
        "teacher_present_b731abb35e5b5ba3fcfcc7bc": "Both replies decline the father-history question; original A selects B, while Qwen selects A and explicitly calls it slightly better for concision/coherence. Neither answer supplies the requested fact. The example exposes a materiality-boundary problem beyond human agreement or order stability.",
        "teacher_present_f872c642a1ec8f102fe30057": "California is explicit in the reference and response B. Original A was uncertain; six-case followup corrected it. Selene JSON rationale identifies B but verdict selects A.",
        "teacher_present_c95de7645121e8efa114a409": "Short Summary reference omits therapy/father details and only mentions earlier part-time employment. Full prior source supports those details and later full-time employment; judge rationale must separate factual support from relevance and coverage.",
        "teacher_present_e6d54335f0f918872758b7c9": "Qwen gives incompatible decisive preferences: one orientation favors detailed actionable advice, the reverse favors a complete concise reply and less overload. Original A marks equivalent. The case illustrates instability in judging material net benefit, not a proved preference of the real user.",
    }
    cards, identical_pairs = [], []
    for reference in references:
        if reference["reverse_duplicate"]:
            continue
        item = items[reference["presentation_id"]]
        if item["response_A"] == item["response_B"]:
            identical_pairs.append({"base_pair_id": reference["base_pair_id"],
                "presentation_id": reference["presentation_id"], "task": reference["task"],
                "expected_comparative_verdict": "equivalent"})
        for position in ["A", "B"]:
            arm = reference["A_arm"] if position == "A" else ("OFF" if reference["A_arm"] == "ON" else "ON")
            text = item["response_" + position].strip().replace("’", "'")
            count = counts[(reference["task"], arm)]
            count["base_pair_response_presentations"] += 1
            count["explicit_refusal_prefix"] += int(text.startswith(("I can't", "I cannot")))
        pid = reference["presentation_id"]
        if pid in examples:
            cards.append({"presentation_id": pid, "base_pair_id": reference["base_pair_id"],
                "A_arm": reference["A_arm"], "observation": examples[pid],
                **{key: item[key] for key in ["task_input", "reference_material", "response_A", "response_B"]},
                **{key: reference[key] for key in ["original_A", "human_followup", "assistant_fact_sensitivity"]}})
    output = {"source_sheet_sha256": binding["sha256"], "kind": "descriptive_development_audit_not_new_human_labels",
        "denominator": "80 base pairs, with shared replies counted once per base-pair presentation; not 160 independent generation samples",
        "refusal_rule": "Leading I can't / I cannot after curly-apostrophe normalization. Descriptive only; not an automatic quality or exclusion rule.",
        "by_task_arm": [{"task": key[0], "arm": key[1], **value} for key, value in sorted(counts.items())],
        "exactly_identical_response_pairs": identical_pairs,
        "case_cards": cards, "new_calls": 0, "formal_labels": False}
    write_json(current / "existing_response_characteristics.json", output)
    print(output["by_task_arm"])


if __name__ == "__main__":
    main()
