from __future__ import annotations

import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.contracts import StrategyCard  # noqa: E402
from metacom_pm.v1_5_paper1_suitability_packet import (  # noqa: E402
    build_blind_packets,
    select_qualification_rows,
)


PUBLIC = ROOT / "outputs/pm_v1_5_paper1_p2a_suitability_packet"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_p2a_suitability_packet_private"
DESIGN = ROOT / "data/pm_v1_5_contracts/paper1_p2_atomic_suitability_design_candidate_v1.json"
OUT = (
    ROOT
    / "outputs/pm_v1_5_paper1_p2a_suitability_packet_final_audit_20260810"
    / "report.json"
)


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contains(value: Any, denied: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(key in denied or _contains(item, denied) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains(item, denied) for item in value)
    return False


def main() -> None:
    design = _read(DESIGN)
    report = _read(PUBLIC / "report.json")
    packet_a = _jsonl(PUBLIC / "reviewer_a_packet_unlabeled.jsonl")
    packet_b = _jsonl(PUBLIC / "reviewer_b_packet_unlabeled.jsonl")
    private = _jsonl(PRIVATE / "private_case_key.jsonl")
    rank1 = _jsonl(ROOT / "outputs/pm_v1_5_paper1_p1b_actual_rank1/actual_rank1_unlabeled.jsonl")
    states = {
        str(row["state_id"]): row
        for row in [
            *_jsonl(ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/esconv_states_unlabeled.jsonl"),
            *_jsonl(ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_states_unlabeled.jsonl"),
        ]
    }
    candidates = {
        str(row["candidate_id"]): row
        for row in _jsonl(ROOT / "outputs/pm_v1_5_paper1_p1_public_surface/evoemo_candidates_unlabeled.jsonl")
    }
    cards = {
        card.strategy_id: card
        for card in (
            StrategyCard(**row)
            for row in _jsonl(ROOT / "data/strategy/strategy_cards_v1_5_minimal.jsonl")
        )
    }
    expected_a, expected_b, expected_private = build_blind_packets(
        selected=select_qualification_rows(rank1),
        states=states,
        candidates=candidates,
        cards=cards,
        component_minima=design["component_minima"],
        axes=design["axes"],
    )
    denied = {
        "state_id",
        "split_group_key",
        "actual_rank1_id",
        "diagnostic_stratum",
        "selection_score",
        "top1_top2_margin",
        "suitability_label",
        "expected_label",
    }
    checks = {
        "materializer_report_pass": report["status"]
        == "P2A_SUITABILITY_PACKET_PASS_REVIEW_CALLS_NOT_AUTHORIZED",
        "artifact_hashes_match_report": all(
            _sha(Path(binding["path"])) == binding["sha256"]
            for binding in report["artifacts"].values()
        ),
        "selection_and_packet_recompute_exactly": packet_a == expected_a
        and packet_b == expected_b
        and private == expected_private,
        "public_has_no_private_or_label_keys": not _contains(packet_a, denied)
        and not _contains(packet_b, denied),
        "reviewer_ids_and_orders_are_independent": not (
            {row["review_item_id"] for row in packet_a}
            & {row["review_item_id"] for row in packet_b}
        )
        and [row["review_item_id"] for row in packet_a]
        != [row["review_item_id"] for row in packet_b],
        "private_key_is_physical_and_complete": len(private) == 132
        and not any("case_key" in row for row in [*packet_a, *packet_b]),
        "no_calls_labels_responses_training_or_outcomes": report["api_calls"] == 0
        and report["labels_created"] == 0
        and report["responses_generated"] == 0
        and report["pm_trained"] is False
        and report["external_outcomes_read"] is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    final = {
        "protocol": "pm-v1.5-paper1-p2a-suitability-packet-final-audit-v1",
        "status": (
            "P2A_SUITABILITY_PACKET_FINAL_PASS_REVIEW_PHASE_MAY_BE_DESIGNED"
            if not failed
            else "P2A_SUITABILITY_PACKET_FINAL_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "counts": report["counts"],
        "artifact_hashes": report["artifacts"],
        "api_calls": 0,
        "labels_created": 0,
        "responses_generated": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(final, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(final, ensure_ascii=False, sort_keys=True))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
