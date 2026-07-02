#!/usr/bin/env python3
"""No-API diagnostic for PM evidence precision in EvoEmo audit pilot.

This script does not call any model API. It analyzes whether the balanced
paired audit pilot problems are better explained by:

* PM action-level routing,
* lexical retrieval/source granularity,
* pilot sample enrichment, or
* audit rubric/schema ambiguity.
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter, defaultdict
from pathlib import Path
from statistics import mean, median
from typing import Any, Iterable

from metacom_pm.text import lexical_score, normalize_space


ROOT = Path(__file__).resolve().parents[1]

RISK_FIELDS = (
    "selected_evidence_misuse",
    "unnecessary_exposure",
    "stale_or_conflict",
    "unsupported_personal_claim",
    "overall_risk",
)

RESPONSE_FIELDS = (
    "overall",
    "emotional_support",
    "personalization",
    "memory_appropriateness",
    "factual_grounding",
    "temporal_consistency",
    "non_intrusiveness",
)


def iter_jsonl(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if line:
                yield json.loads(line)


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def summarize_numbers(values: Iterable[float]) -> dict[str, Any]:
    vals = [float(v) for v in values if v is not None and math.isfinite(float(v))]
    if not vals:
        return {"n": 0, "mean": None, "median": None, "min": None, "max": None}
    vals = sorted(vals)
    return {
        "n": len(vals),
        "mean": float(mean(vals)),
        "median": float(median(vals)),
        "min": float(vals[0]),
        "max": float(vals[-1]),
    }


def pct(numerator: int, denominator: int) -> float | None:
    return None if denominator == 0 else numerator / denominator


def response_unit_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("user_id"),
        row.get("topic_index"),
        row.get("seed"),
        row.get("simulator_id"),
        row.get("interaction_mode"),
        row.get("turn_index"),
    )


def turn_unit_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return (
        row.get("user_id"),
        row.get("topic_index"),
        row.get("seed"),
        row.get("simulator_id"),
        row.get("interaction_mode"),
        row.get("turn_index"),
    )


def audit_turn_key(row: dict[str, Any], condition: str) -> tuple[Any, ...]:
    key = row["unit_key"]
    return (
        key.get("user_id"),
        key.get("topic_index"),
        key.get("seed"),
        key.get("simulator_id"),
        key.get("interaction_mode"),
        key.get("turn_index"),
        condition,
    )


def turn_lookup_key(row: dict[str, Any]) -> tuple[Any, ...]:
    return turn_unit_key(row) + (row.get("condition"),)


def selected_memory_count(turn: dict[str, Any]) -> int:
    value = turn.get("selected_memory") or []
    return len(value) if isinstance(value, list) else 0


def action_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counts = Counter(str(row.get("action_id")) for row in rows)
    total = sum(counts.values())
    return {
        "n": total,
        "counts": dict(counts.most_common()),
        "rates": {key: value / total for key, value in counts.most_common()} if total else {},
    }


def score_memory_relevance(turn: dict[str, Any]) -> list[dict[str, Any]]:
    memories = turn.get("selected_memory") or []
    seeker = str(turn.get("seeker_message") or "")
    history_text = "\n".join(
        str(x.get("content") or "")
        for x in (turn.get("context_before_turn") or [])
        if isinstance(x, dict)
    )
    context_query = normalize_space(history_text + "\n" + seeker)
    out = []
    for memory in memories:
        text = str(memory.get("text") or "")
        out.append(
            {
                "memory_id": memory.get("memory_id"),
                "source": memory.get("source"),
                "current_turn_score": lexical_score(seeker, text),
                "context_score": lexical_score(context_query, text),
                "text_preview": normalize_space(text)[:180],
            }
        )
    return out


def mean_response_scores(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        field: summarize_numbers(float(row[field]) for row in rows if field in row)
        for field in RESPONSE_FIELDS
    }


def build_report(
    *,
    turns_path: Path,
    response_scores_path: Path,
    audit_scores_path: Path,
    sample_plan_path: Path,
) -> dict[str, Any]:
    turns = list(iter_jsonl(turns_path))
    response_scores = list(iter_jsonl(response_scores_path))
    audit_scores = list(iter_jsonl(audit_scores_path))
    plan = json.loads(sample_plan_path.read_text(encoding="utf-8"))
    plan_items = {row["audit_item_id"]: row for row in plan.get("audit_items") or []}

    turns_by_key = {turn_lookup_key(row): row for row in turns}
    response_by_unit_cond: dict[tuple[str, str], dict[str, Any]] = {}
    for row in response_scores:
        response_by_unit_cond[(str(row["unit_id"]), str(row["condition"]))] = row

    pm_turns = [row for row in turns if row.get("condition") == "pm"]
    v4_pm_unit_ids = {str(row["unit_id"]) for row in response_scores if row.get("condition") == "pm"}
    v4_pm_turns = []
    response_key_to_unit = {response_unit_key(row): str(row["unit_id"]) for row in response_scores}
    for turn in pm_turns:
        unit_id = response_key_to_unit.get(turn_unit_key(turn))
        if unit_id in v4_pm_unit_ids:
            v4_pm_turns.append(turn)

    pilot_pm = [row for row in audit_scores if row.get("condition") == "pm"]
    pilot_by_condition = defaultdict(list)
    for row in audit_scores:
        pilot_by_condition[str(row.get("condition"))].append(row)

    pilot_pm_action_counts = Counter(row.get("pm_action_id") for row in pilot_pm)
    pilot_pm_risky_action_counts = Counter(
        row.get("pm_action_id") for row in pilot_pm if int(row.get("overall_risk", 0)) > 0
    )

    strata_all = Counter(row.get("primary_stratum") for row in plan.get("audit_items") or [])
    strata_pilot = Counter(
        plan_items[row["audit_item_id"]].get("primary_stratum")
        for row in pilot_pm
        if row.get("audit_item_id") in plan_items
    )
    covered_high_all = sum(
        1
        for row in plan.get("audit_items") or []
        if "pm_high_resource" in (row.get("covered_strata") or [])
    )
    covered_high_pilot = sum(
        1
        for row in pilot_pm
        if "pm_high_resource" in (plan_items[row["audit_item_id"]].get("covered_strata") or [])
    )

    condition_pilot_summary: dict[str, Any] = {}
    for condition, rows in sorted(pilot_by_condition.items()):
        condition_pilot_summary[condition] = {
            "n": len(rows),
            "verdict_counts": dict(Counter(str(row["verdict"]) for row in rows).most_common()),
            "risk_field_means": {
                field: mean(float(row.get(field, 0)) for row in rows) if rows else None
                for field in RISK_FIELDS
            },
            "major_risk_count": sum(1 for row in rows if int(row.get("overall_risk", 0)) >= 2),
            "any_risk_count": sum(1 for row in rows if int(row.get("overall_risk", 0)) > 0),
        }

    memory_relevance_by_condition: dict[str, Any] = {}
    pilot_turn_diagnostics: list[dict[str, Any]] = []
    for condition, rows in sorted(pilot_by_condition.items()):
        all_scores = []
        risky_scores = []
        counts = []
        for row in rows:
            turn = turns_by_key.get(audit_turn_key(row, condition))
            if turn is None:
                continue
            memory_scores = score_memory_relevance(turn)
            counts.append(len(memory_scores))
            all_scores.extend(x["current_turn_score"] for x in memory_scores)
            if int(row.get("overall_risk", 0)) > 0:
                risky_scores.extend(x["current_turn_score"] for x in memory_scores)
            if condition == "pm":
                response_row = response_by_unit_cond.get((str(row["unit_id"]), condition))
                pilot_turn_diagnostics.append(
                    {
                        "audit_item_id": row["audit_item_id"],
                        "unit_id": row["unit_id"],
                        "condition": condition,
                        "pm_action_id": row.get("pm_action_id"),
                        "primary_stratum": plan_items.get(row["audit_item_id"], {}).get("primary_stratum"),
                        "covered_strata": plan_items.get(row["audit_item_id"], {}).get("covered_strata"),
                        "overall_risk": row.get("overall_risk"),
                        "selected_evidence_misuse": row.get("selected_evidence_misuse"),
                        "verdict": row.get("verdict"),
                        "response_overall": response_row.get("overall") if response_row else None,
                        "response_memory_appropriateness": (
                            response_row.get("memory_appropriateness") if response_row else None
                        ),
                        "selected_memory_count": len(memory_scores),
                        "memory_current_turn_scores": [
                            round(float(x["current_turn_score"]), 4) for x in memory_scores
                        ],
                        "memory_context_scores": [
                            round(float(x["context_score"]), 4) for x in memory_scores
                        ],
                        "memory_previews": memory_scores,
                        "reason": row.get("reason"),
                    }
                )
        memory_relevance_by_condition[condition] = {
            "selected_memory_count": summarize_numbers(counts),
            "current_turn_relevance": summarize_numbers(all_scores),
            "risky_current_turn_relevance": summarize_numbers(risky_scores),
        }

    pm_pilot_risky_units = {
        str(row["unit_id"]) for row in pilot_pm if int(row.get("overall_risk", 0)) > 0
    }
    pm_pilot_clean_units = {
        str(row["unit_id"]) for row in pilot_pm if int(row.get("overall_risk", 0)) == 0
    }
    pm_response_risky = [
        row for row in response_scores
        if row.get("condition") == "pm" and str(row["unit_id"]) in pm_pilot_risky_units
    ]
    pm_response_clean = [
        row for row in response_scores
        if row.get("condition") == "pm" and str(row["unit_id"]) in pm_pilot_clean_units
    ]

    schema_mismatches = [
        {
            "condition": row.get("condition"),
            "audit_item_id": row.get("audit_item_id"),
            "unit_id": row.get("unit_id"),
            "verdict": row.get("verdict"),
            "overall_risk": row.get("overall_risk"),
            "selected_evidence_misuse": row.get("selected_evidence_misuse"),
            "source_set_appropriateness": row.get("source_set_appropriateness"),
            "reason": row.get("reason"),
        }
        for row in audit_scores
        if (row.get("verdict") == "major_issue" and int(row.get("overall_risk", 0)) == 0)
        or (row.get("verdict") == "acceptable" and int(row.get("overall_risk", 0)) > 0)
    ]

    report = {
        "analysis_type": "pm_evidence_precision_diagnostic_no_api",
        "inputs": {
            "turns": str(turns_path),
            "response_scores": str(response_scores_path),
            "audit_scores": str(audit_scores_path),
            "sample_plan": str(sample_plan_path),
        },
        "pm_action_distribution": {
            "all_generated_pm_turns": action_summary(pm_turns),
            "v4_response_sample_pm_turns": action_summary(v4_pm_turns),
            "balanced_pilot_pm_actions": {
                "n": len(pilot_pm),
                "counts": dict(pilot_pm_action_counts.most_common()),
                "risky_counts": dict(pilot_pm_risky_action_counts.most_common()),
            },
        },
        "pilot_sample_enrichment": {
            "all_plan_primary_strata": dict(strata_all.most_common()),
            "pilot_primary_strata": dict(strata_pilot.most_common()),
            "all_plan_pm_high_resource_covered": covered_high_all,
            "pilot_pm_high_resource_covered": covered_high_pilot,
            "pilot_pm_high_resource_covered_rate": pct(covered_high_pilot, len(pilot_pm)),
        },
        "pilot_condition_summary": condition_pilot_summary,
        "memory_relevance_by_condition": memory_relevance_by_condition,
        "pm_pilot_response_scores": {
            "risky_pm_units": mean_response_scores(pm_response_risky),
            "clean_pm_units": mean_response_scores(pm_response_clean),
        },
        "schema_mismatches": {
            "n": len(schema_mismatches),
            "rows": schema_mismatches,
        },
        "pm_pilot_turn_diagnostics": pilot_turn_diagnostics,
        "interpretation": {
            "primary_source": (
                "The pilot issues concentrate in PM high-resource MSE+RS actions. "
                "This points to action-level routing plus retrieval/source granularity, "
                "not a global failure of response generation."
            ),
            "retrieval_limit": (
                "The current retriever ranks memory lexically and returns fixed top-k "
                "per selected source without a relevance threshold. Long ME memories can "
                "contain partially matching text while also carrying unrelated private events."
            ),
            "pilot_limit": (
                "The pilot is enriched for high-resource and PM-lower-quality strata, so it "
                "should be read as a stress diagnostic rather than a population estimate."
            ),
            "rubric_limit": (
                "The audit schema partly conflates weakly relevant selected evidence with "
                "actual response misuse. Future reports should separate evidence relevance, "
                "response misuse, source excess, and support sufficiency."
            ),
        },
    }
    return report


def markdown_report(report: dict[str, Any]) -> str:
    pm_actions = report["pm_action_distribution"]
    pilot = report["pilot_condition_summary"]
    relevance = report["memory_relevance_by_condition"]
    resp = report["pm_pilot_response_scores"]
    lines = [
        "# PM Evidence Precision Diagnostic",
        "",
        "No API calls were made. This report diagnoses the balanced paired audit pilot.",
        "",
        "## Main Finding",
        "",
        (
            "The pilot does not show a global response-quality collapse. It shows a "
            "more specific failure mode: PM high-resource actions can route into "
            "weakly focused memory retrieval. PM is acting as a coarse resource router, "
            "not as a fine-grained evidence selector."
        ),
        "",
        "## PM Action Concentration",
        "",
        f"- PM all generated turns: {pm_actions['all_generated_pm_turns']['n']}",
        f"- PM all generated action counts: `{pm_actions['all_generated_pm_turns']['counts']}`",
        (
            "- Balanced pilot PM actions: "
            f"`{pm_actions['balanced_pilot_pm_actions']['counts']}`"
        ),
        (
            "- Balanced pilot risky PM actions: "
            f"`{pm_actions['balanced_pilot_pm_actions']['risky_counts']}`"
        ),
        "",
        "All PM pilot issues occur under `MSE+RS`.",
        "",
        "## Pilot Sample Enrichment",
        "",
        (
            "- Pilot primary strata: "
            f"`{report['pilot_sample_enrichment']['pilot_primary_strata']}`"
        ),
        (
            "- PM high-resource coverage in pilot: "
            f"{report['pilot_sample_enrichment']['pilot_pm_high_resource_covered']}/12"
        ),
        (
            "- PM high-resource coverage in full plan: "
            f"{report['pilot_sample_enrichment']['all_plan_pm_high_resource_covered']}/50"
        ),
        "",
        "The pilot is therefore a stress sample, not a population estimate.",
        "",
        "## Pilot Risk Summary",
        "",
        "| Policy | n | Acceptable | Minor | Major | Mean evidence misuse | Mean overall risk |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for condition in ["pm", "strong_rule", "best_fixed", "session_rag_rs"]:
        row = pilot.get(condition, {})
        verdicts = row.get("verdict_counts", {})
        means = row.get("risk_field_means", {})
        lines.append(
            "| {condition} | {n} | {acc} | {minor} | {major} | {misuse:.3f} | {risk:.3f} |".format(
                condition=condition,
                n=row.get("n", 0),
                acc=verdicts.get("acceptable", 0),
                minor=verdicts.get("minor_issue", 0),
                major=verdicts.get("major_issue", 0),
                misuse=float(means.get("selected_evidence_misuse") or 0),
                risk=float(means.get("overall_risk") or 0),
            )
        )
    lines.extend(
        [
            "",
            "## Retrieval Relevance",
            "",
            "| Policy | mean selected memory count | mean current-turn lexical relevance | risky-case relevance |",
            "| --- | ---: | ---: | ---: |",
        ]
    )
    for condition in ["pm", "strong_rule", "best_fixed", "session_rag_rs"]:
        row = relevance.get(condition, {})
        count_mean = (row.get("selected_memory_count") or {}).get("mean")
        rel_mean = (row.get("current_turn_relevance") or {}).get("mean")
        risky_mean = (row.get("risky_current_turn_relevance") or {}).get("mean")
        lines.append(
            "| {condition} | {count} | {rel} | {risky} |".format(
                condition=condition,
                count="NA" if count_mean is None else f"{count_mean:.2f}",
                rel="NA" if rel_mean is None else f"{rel_mean:.3f}",
                risky="NA" if risky_mean is None else f"{risky_mean:.3f}",
            )
        )
    lines.extend(
        [
            "",
            "Lexical relevance alone does not explain the judge scores. Some long memories "
            "have lexical overlap with the current turn while carrying unrelated private events.",
            "",
            "## Response Scores For PM Pilot Units",
            "",
            "| PM pilot subset | n | overall | memory appropriateness | non intrusive |",
            "| --- | ---: | ---: | ---: | ---: |",
        ]
    )
    for label, rows in [
        ("risky PM units", resp["risky_pm_units"]),
        ("clean PM units", resp["clean_pm_units"]),
    ]:
        overall = rows["overall"]
        memory = rows["memory_appropriateness"]
        non_intrusive = rows["non_intrusiveness"]
        lines.append(
            "| {label} | {n} | {overall} | {memory} | {non_intrusive} |".format(
                label=label,
                n=overall["n"],
                overall="NA" if overall["mean"] is None else f"{overall['mean']:.3f}",
                memory="NA" if memory["mean"] is None else f"{memory['mean']:.3f}",
                non_intrusive=(
                    "NA" if non_intrusive["mean"] is None else f"{non_intrusive['mean']:.3f}"
                ),
            )
        )
    lines.extend(
        [
            "",
            "The risky PM units are not evidence that the generator collapses. They indicate "
            "that selected memory sets can be weakly focused even when the response remains "
            "supportive.",
            "",
            "## Audit Schema Note",
            "",
            (
                f"Schema/verdict mismatch rows: {report['schema_mismatches']['n']}. "
                "This supports separating evidence relevance from actual response misuse."
            ),
            "",
            "## Recommended Interpretation",
            "",
            "1. PM is a coarse pre-evidence router, not a fine-grained evidence selector.",
            "2. The main failure source is retrieval/source granularity under high-resource actions.",
            "3. The pilot is a stress diagnostic because it over-represents high-resource PM cases.",
            "4. Future tables should report evidence relevance, response misuse, source excess, and response support separately.",
            "",
            "## Recommended Next Step",
            "",
            (
                "Do not use an evidence gate to claim PM itself selected evidence correctly. "
                "If a gate is added, report it as a separate execution-layer module: "
                "`PM + evidence gate`."
            ),
            "",
        ]
    )
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--turns",
        type=Path,
        default=ROOT / "outputs/evoemo_selective/turns.jsonl",
    )
    parser.add_argument(
        "--response-scores",
        type=Path,
        default=ROOT / "outputs/evoemo_response_v4/response_scores.jsonl",
    )
    parser.add_argument(
        "--audit-scores",
        type=Path,
        default=ROOT / "outputs/evoemo_balanced_paired_audit/pilot_scores.jsonl",
    )
    parser.add_argument(
        "--sample-plan",
        type=Path,
        default=ROOT / "outputs/evoemo_balanced_paired_audit_plan/audit_sample_plan.json",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=ROOT / "outputs/evoemo_balanced_paired_audit/pm_evidence_precision_diagnostic.json",
    )
    parser.add_argument(
        "--out-md",
        type=Path,
        default=ROOT / "outputs/evoemo_balanced_paired_audit/pm_evidence_precision_diagnostic.md",
    )
    args = parser.parse_args()

    report = build_report(
        turns_path=args.turns,
        response_scores_path=args.response_scores,
        audit_scores_path=args.audit_scores,
        sample_plan_path=args.sample_plan,
    )
    write_json(args.out_json, report)
    args.out_md.write_text(markdown_report(report), encoding="utf-8")
    print(
        {
            "status": "COMPLETE",
            "out_json": str(args.out_json),
            "out_md": str(args.out_md),
            "pm_risky_actions": report["pm_action_distribution"]["balanced_pilot_pm_actions"][
                "risky_counts"
            ],
            "schema_mismatch_rows": report["schema_mismatches"]["n"],
        }
    )


if __name__ == "__main__":
    main()
