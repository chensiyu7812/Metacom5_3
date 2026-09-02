#!/usr/bin/env python3
"""Materialize the frozen 32-item/29-session v9 DEV requalification package.

The source is the committed precalibration human-audit sample and sanitized
public runtime, not the unavailable historical private v6 result path.  The
projection preserves proposal IDs, rendered candidate semantics, exact seeker
spans, owner/session identity and old DEV labels.  Prior-memory tables and
version links are deliberately absent: v9 requalifies whether each candidate
is supported by its current-session spans without reconstructing private data.
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
import re
import sys
from pathlib import Path
from typing import Any


PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import append_jsonl, sha256_file, write_json  # noqa: E402
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users  # noqa: E402
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config  # noqa: E402
from metacom_pm.paper1.semantic_memory.contracts import (  # noqa: E402
    ExtractorSessionOutput,
    MEHistoricalOutcomeType,
    MPProfileFieldType,
    ProposedMEMemoryUnit,
    ProposedMPMemoryUnit,
    SupportingSpan,
)
from metacom_pm.paper1.semantic_memory.grounding import validate_proposal_grounding  # noqa: E402
from metacom_pm.paper1.semantic_memory.input_projection import build_session_compile_input  # noqa: E402


MP_PATTERN = re.compile(r"^Profile fact \[([^]]+)\]: (.+)$", re.DOTALL)
ME_PATTERN = re.compile(
    r"^Past action: (.+?)(?:\.)? User-observed outcome \[([^]]+)\]: (.+)$", re.DOTALL
)


def _spans(example: dict[str, Any]) -> tuple[SupportingSpan, ...]:
    return tuple(
        SupportingSpan(
            span_id=f"{example['memory_id']}:devspan:{index}",
            turn_id=raw["turn_id"],
            exact_text=raw["exact_supporting_span"],
        )
        for index, raw in enumerate(example["exact_source_turns"], start=1)
    )


def _proposal(memory_class: str, example: dict[str, Any]):
    spans = _spans(example)
    common = {
        "proposal_id": example["memory_id"],
        "supporting_spans": spans,
        "entities": (),
        "linked_prior_relations": (),
    }
    if memory_class == "MP":
        match = MP_PATTERN.fullmatch(example["rendered_candidate"])
        if match is None or match.group(1) != example["stratum"]:
            raise RuntimeError(f"MP rendered candidate drifted: {example['memory_id']}")
        return ProposedMPMemoryUnit(
            **common,
            profile_field_type=MPProfileFieldType(example["stratum"]),
            factual_claim=match.group(2),
        )
    match = ME_PATTERN.fullmatch(example["rendered_candidate"])
    if match is None or match.group(2) != example["stratum"]:
        raise RuntimeError(f"ME rendered candidate drifted: {example['memory_id']}")
    action_span_ids = (spans[0].span_id,)
    outcome_span_ids = (spans[-1].span_id,)
    return ProposedMEMemoryUnit(
        **common,
        historical_outcome_type=MEHistoricalOutcomeType(example["stratum"]),
        action=match.group(1),
        observed_outcome=match.group(3),
        action_span_ids=action_span_ids,
        observed_outcome_span_ids=outcome_span_ids,
    )


def build_rows(
    *, runtime: Path, audit: Path, dev_plan: Path
) -> list[dict[str, Any]]:
    users = load_sanitized_runtime_users(runtime)
    user_by_id = {user.owner_id: user for user in users}
    audit_payload = json.loads(audit.read_text(encoding="utf-8"))
    plan = json.loads(dev_plan.read_text(encoding="utf-8"))
    plan_by_id = {row["memory_id"]: row for row in plan["rows"]}
    examples: list[tuple[str, dict[str, Any]]] = []
    for memory_class in ("MP", "ME"):
        examples.extend(
            (memory_class, row)
            for row in audit_payload["fixed_seed_stratified_examples"][memory_class]["examples"]
        )
    if len(examples) != 32 or {row["memory_id"] for _, row in examples} != set(plan_by_id):
        raise RuntimeError("committed audit sample is not the exact frozen 32-item old DEV set")
    grouped: dict[tuple[str, str], list[tuple[str, dict[str, Any]]]] = defaultdict(list)
    for memory_class, example in examples:
        old = plan_by_id[example["memory_id"]]
        if old["memory_class"] != memory_class:
            raise RuntimeError("old DEV class identity drifted")
        if old["old_dev_verdict"] != example["precalibration_human_audit_verdict"]:
            raise RuntimeError("old DEV human verdict drifted")
        grouped[(example["owner_id"], example["source_session_id"])].append(
            (memory_class, example)
        )
    if len(grouped) != 29:
        raise RuntimeError("v9 DEV package must contain exactly 29 source sessions")

    rows: list[dict[str, Any]] = []
    for owner_id, session_id in sorted(grouped):
        session = user_by_id[owner_id].session_by_id(session_id)
        source = build_session_compile_input(owner_id=owner_id, session=session)
        proposals = [_proposal(memory_class, example) for memory_class, example in grouped[(owner_id, session_id)]]
        for memory_class, example in grouped[(owner_id, session_id)]:
            for expected_turn in example["exact_source_turns"]:
                actual = next(turn for turn in source.turns if turn.turn_id == expected_turn["turn_id"])
                if actual.role.value != "seeker" or actual.content != expected_turn["full_turn_text"]:
                    raise RuntimeError("committed audit exact source turn drifted")
        extractor = ExtractorSessionOutput(
            owner_id=owner_id,
            session_id=session_id,
            mp_facts=tuple(item for item in proposals if isinstance(item, ProposedMPMemoryUnit)),
            me_experiences=tuple(item for item in proposals if isinstance(item, ProposedMEMemoryUnit)),
        )
        invalid = [
            result
            for result in (validate_proposal_grounding(source, item) for item in extractor.proposals)
            if not result.valid
        ]
        if invalid:
            raise RuntimeError(f"v9 DEV reconstructed proposal grounding failed: {invalid}")
        rows.append(
            {
                "protocol": "paper1-semantic-memory-v9-dev-package-row-v1",
                "source": source.model_dump(mode="json"),
                "extractor": extractor.model_dump(mode="json"),
                "old_dev": [
                    {
                        "memory_id": example["memory_id"],
                        "memory_class": memory_class,
                        "old_human_label": plan_by_id[example["memory_id"]]["old_dev_verdict"],
                        "old_human_reason": plan_by_id[example["memory_id"]]["old_dev_reason"],
                    }
                    for memory_class, example in grouped[(owner_id, session_id)]
                ],
                "prior_memory_table_role": "intentionally_empty_current_session_support_requalification",
                "outcome_calls": 0,
            }
        )
    return rows


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--audit", type=Path, required=True)
    parser.add_argument("--dev-plan", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    locks = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(locks)
    if args.out.exists() or args.report.exists():
        raise RuntimeError("refusing to overwrite v9 DEV package evidence")
    rows = build_rows(runtime=args.runtime, audit=args.audit, dev_plan=args.dev_plan)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    for row in rows:
        append_jsonl(args.out, row)
    report = {
        "protocol": "paper1-semantic-memory-v9-dev-package-report-v1",
        "status": "FROZEN_READY_FOR_AUTHORIZED_V9_DEV",
        "scope": "OLD_DEV_32_ITEMS_IN_29_SOURCE_SESSIONS_ONLY",
        "source": {
            "sanitized_runtime_sha256": sha256_file(args.runtime),
            "precalibration_audit_sha256": sha256_file(args.audit),
            "old_dev_plan_sha256": sha256_file(args.dev_plan),
        },
        "package_sha256": sha256_file(args.out),
        "source_sessions": len(rows),
        "items": sum(len(row["old_dev"]) for row in rows),
        "prior_memory_tables": "EMPTY_BY_FROZEN_PROJECTION",
        "full_401_compile_authorized": False,
        "outcome_calls": 0,
        "locks": {key: value["status"] for key, value in locks.items() if key.endswith("OUTCOME_LOCK")},
    }
    write_json(args.report, report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
