#!/usr/bin/env python3
"""Evaluator-only ESConv strategy-family sanity diagnostic for RS retrieval.

ESConv target supporter strategy annotations are public evaluator metadata.  The
active authority permits them only for retriever family-match diagnostics;
they are never PM features, ON/OFF labels, applicability gold, or Paper-1
outcomes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from metacom_pm.paper1.rs.zero_outcome_census import build_rs_decision_states

PROTOCOL = "pm-paper1-esconv-rs-strategy-family-match-evaluator-only-v1"
STATUS = "EVALUATOR_ONLY_RETRIEVER_DIAGNOSTIC_NOT_PM_GOLD_NOT_A_FREEZE"


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(_canonical(row) + "\n" for row in rows), encoding="utf-8")


def _target_strategy_by_state(
    *, esconv_path: Path, split_manifest_path: Path
) -> dict[str, str]:
    data = json.loads(esconv_path.read_text(encoding="utf-8"))
    split_rows = [
        json.loads(line)
        for line in split_manifest_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    by_dialogue = {
        row["dialogue_id"]: data[row["index"]]["dialog"] for row in split_rows
    }
    states = build_rs_decision_states(
        esconv_path=esconv_path,
        split_manifest_path=split_manifest_path,
        source_splits=("train", "validation"),
        exclude_evoemo_overlap=True,
        query_preceding_turns=6,
    )
    result: dict[str, str] = {}
    for state in states:
        target = by_dialogue[state.source_dialogue_id][state.decision_turn_index]
        if target.get("speaker") != "supporter":
            raise ValueError("RS decision target is not a supporter turn")
        strategy = " ".join(
            str((target.get("annotation") or {}).get("strategy") or "Others").split()
        )
        if not strategy:
            raise ValueError("empty target strategy annotation")
        result[state.state_id] = strategy
    return result


def main() -> int:
    project = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser()
    parser.add_argument("--esconv", type=Path, default=project / "data/external/ESConv.json")
    parser.add_argument(
        "--split-manifest",
        type=Path,
        default=project / "data/strategy/esconv_split_manifest_v1_5.jsonl",
    )
    parser.add_argument(
        "--retriever-surface",
        type=Path,
        default=project
        / "data/paper1_public_rs/esconv_rs_retriever_comparison_surface_v1.jsonl",
    )
    parser.add_argument(
        "--out-dir", type=Path, default=project / "data/paper1_evaluator_only_rs"
    )
    args = parser.parse_args()

    target_strategy = _target_strategy_by_state(
        esconv_path=args.esconv,
        split_manifest_path=args.split_manifest,
    )
    surface = [
        json.loads(line)
        for line in args.retriever_surface.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]
    if {row["state_id"] for row in surface} != set(target_strategy):
        raise ValueError("retriever surface and evaluator target identities differ")

    evaluator_rows: list[dict[str, Any]] = []
    aggregate: dict[str, Counter[str]] = defaultdict(Counter)
    by_split: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    by_split_family: dict[
        str, dict[str, dict[str, Counter[str]]]
    ] = defaultdict(lambda: defaultdict(lambda: defaultdict(Counter)))
    by_family: dict[str, dict[str, Counter[str]]] = defaultdict(
        lambda: defaultdict(Counter)
    )
    for row in surface:
        gold = target_strategy[row["state_id"]]
        method_rows = []
        for ranking in row["rankings"]:
            labels = ranking["source_strategy_annotations"]
            at1 = labels[0] == gold
            at3 = gold in labels[:3]
            method = ranking["method"]
            aggregate[method].update(total=1, match_at_1=int(at1), match_at_3=int(at3))
            by_split[method][row["source_split"]].update(
                total=1, match_at_1=int(at1), match_at_3=int(at3)
            )
            by_split_family[method][row["source_split"]][gold].update(
                total=1, match_at_1=int(at1), match_at_3=int(at3)
            )
            by_family[method][gold].update(
                total=1, match_at_1=int(at1), match_at_3=int(at3)
            )
            method_rows.append(
                {
                    "method": method,
                    "strategy_family_match_at_1": at1,
                    "strategy_family_match_at_3": at3,
                }
            )
        evaluator_rows.append(
            {
                "protocol": PROTOCOL,
                "evaluator_only": True,
                "state_id": row["state_id"],
                "source_split": row["source_split"],
                "target_strategy_annotation": gold,
                "method_diagnostics": method_rows,
            }
        )

    rows_path = args.out_dir / "esconv_rs_strategy_family_match_evaluator_only_v1.jsonl"
    summary_path = args.out_dir / "esconv_rs_strategy_family_match_summary_v1.json"
    _write_jsonl(rows_path, evaluator_rows)
    method_summary = {}
    for method, counts in aggregate.items():
        split_summary = {}
        for split, split_counts in sorted(by_split[method].items()):
            family_counts = by_split_family[method][split]
            split_summary[split] = {
                **dict(split_counts),
                "strategy_family_match_at_1": (
                    split_counts["match_at_1"] / split_counts["total"]
                ),
                "strategy_family_match_at_3": (
                    split_counts["match_at_3"] / split_counts["total"]
                ),
                "macro_strategy_family_match_at_1": sum(
                    value["match_at_1"] / value["total"]
                    for value in family_counts.values()
                )
                / len(family_counts),
                "macro_strategy_family_match_at_3": sum(
                    value["match_at_3"] / value["total"]
                    for value in family_counts.values()
                )
                / len(family_counts),
            }
        family_summary = {
            family: {
                **dict(family_counts),
                "strategy_family_match_at_1": (
                    family_counts["match_at_1"] / family_counts["total"]
                ),
                "strategy_family_match_at_3": (
                    family_counts["match_at_3"] / family_counts["total"]
                ),
            }
            for family, family_counts in sorted(by_family[method].items())
        }
        method_summary[method] = {
            **dict(counts),
            "strategy_family_match_at_1": counts["match_at_1"] / counts["total"],
            "strategy_family_match_at_3": counts["match_at_3"] / counts["total"],
            "macro_strategy_family_match_at_1": sum(
                value["strategy_family_match_at_1"]
                for value in family_summary.values()
            )
            / len(family_summary),
            "macro_strategy_family_match_at_3": sum(
                value["strategy_family_match_at_3"]
                for value in family_summary.values()
            )
            / len(family_summary),
            "by_effect_state_split": split_summary,
            "by_target_strategy_family": family_summary,
        }
    summary = {
        "protocol": PROTOCOL,
        "status": STATUS,
        "scope": {
            "authority_allowed_use": "retriever_strategy_family_sanity_diagnostic_only",
            "evaluator_only": True,
            "PM_feature": False,
            "RS_ON_OFF_gold": False,
            "candidate_applicability_gold": False,
            "Generator_outcome": False,
            "Paper1_capability_metric": False,
            "winner_selected": False,
            "pass_fail_gate": False,
            "formal_outcome_calls": 0,
        },
        "counts": {
            "states": len(evaluator_rows),
            "states_by_effect_split": dict(
                sorted(Counter(row["source_split"] for row in surface).items())
            ),
            "target_strategy_annotation_counts": dict(
                sorted(Counter(target_strategy.values()).items())
            ),
        },
        "methods": method_summary,
        "interpretation": (
            "Family match asks whether a retrieved source card shares the coarse "
            "human ESConv strategy annotation of the target supporter turn. It does "
            "not establish that the card is contextually applicable, worth opening, "
            "or beneficial to the frozen Generator."
        ),
        "provenance": {
            "esconv_sha256": _sha256(args.esconv),
            "split_manifest_sha256": _sha256(args.split_manifest),
            "retriever_surface_sha256": _sha256(args.retriever_surface),
            "script_sha256": _sha256(Path(__file__).resolve()),
            "evaluator_rows_path": str(rows_path.relative_to(project)),
            "evaluator_rows_sha256": _sha256(rows_path),
        },
    }
    _write_json(summary_path, summary)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
