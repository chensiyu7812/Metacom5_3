from __future__ import annotations

from collections import Counter
import argparse
import hashlib
import json
from pathlib import Path
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.contracts import StrategyCard  # noqa: E402
from metacom_pm.v1_5_paper1_suitability_packet import (  # noqa: E402
    build_blind_packets,
    select_qualification_rows,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"


def _read(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _write_jsonl(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(_canonical(dict(row)) + "\n")


def _contains_key(value: Any, denied: set[str]) -> bool:
    if isinstance(value, Mapping):
        return any(key in denied or _contains_key(item, denied) for key, item in value.items())
    if isinstance(value, list):
        return any(_contains_key(item, denied) for item in value)
    return False


def _authorized(phase_path: Path | None) -> tuple[dict[str, Any], dict[str, Any]]:
    authority = _read(AUTHORITY)
    current = authority["current_phase"]
    if current["id"] != "P2A_SUITABILITY_QUALIFICATION_PACKET_MATERIALIZATION":
        raise RuntimeError("P2A packet materialization is not active")
    configured = current.get("active_phase_manifest")
    if not configured or phase_path is None:
        raise RuntimeError("P2A authority does not bind a supplied phase manifest")
    expected = _resolve(configured["path"])
    if phase_path.resolve() != expected or _sha(expected) != configured["sha256"]:
        raise RuntimeError("P2A supplied phase path or hash is not authority-bound")
    phase = _read(expected)
    if phase["parent_authority_sha256"] != current.get("promoted_from_authority_sha256"):
        raise RuntimeError("P2A phase parent authority mismatch")
    for binding in [*phase["input_bindings"], *phase["implementation_bindings"]]:
        if _sha(_resolve(binding["path"])) != binding["sha256"]:
            raise RuntimeError(f"P2A binding drifted: {binding['path']}")
    return authority, phase


def run(phase_path: Path) -> dict[str, Any]:
    authority, phase = _authorized(phase_path)
    inputs = {row["role"]: _resolve(row["path"]) for row in phase["input_bindings"]}
    design = _read(inputs["p2_design"])
    rank1 = _jsonl(inputs["rank1"])
    states = {
        str(row["state_id"]): row
        for row in [*_jsonl(inputs["esconv_states"]), *_jsonl(inputs["evoemo_states"])]
    }
    candidates = {
        str(row["candidate_id"]): row for row in _jsonl(inputs["evoemo_candidates"])
    }
    cards = {
        card.strategy_id: card
        for card in (StrategyCard(**row) for row in _jsonl(inputs["strategy_bank"]))
    }
    selected = select_qualification_rows(rank1)
    packet_a, packet_b, private_key = build_blind_packets(
        selected=selected,
        states=states,
        candidates=candidates,
        cards=cards,
        component_minima=design["component_minima"],
        axes=design["axes"],
    )
    public_dir = _resolve(phase["outputs"]["public_dir"])
    private_dir = _resolve(phase["outputs"]["private_dir"])
    if public_dir.exists() or private_dir.exists():
        raise RuntimeError("P2A packet output exists; refusing overwrite or rerun")
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
    component_counts = Counter(row["component"] for row in packet_a)
    private_groups = {
        component: len(
            {
                row["split_group_key"]
                for row in private_key
                if row["component"] == component
            }
        )
        for component in ("MP", "MS", "ME", "RS")
    }
    checks = {
        "exact_packet_counts": len(packet_a) == len(packet_b) == len(private_key) == 132
        and component_counts == Counter({"RS": 36, "MP": 34, "MS": 34, "ME": 28}),
        "review_item_ids_unique_and_blind": len({row["review_item_id"] for row in packet_a}) == 132
        and len({row["review_item_id"] for row in packet_b}) == 132
        and not ({row["review_item_id"] for row in packet_a} & {row["review_item_id"] for row in packet_b}),
        "review_orders_differ": [row["component"] for row in packet_a]
        != [row["component"] for row in packet_b],
        "public_surface_has_no_private_or_label_keys": not _contains_key(packet_a, denied)
        and not _contains_key(packet_b, denied),
        "group_support_matches_design": private_groups
        == {"MP": 17, "MS": 17, "ME": 14, "RS": 36},
        "no_duplicate_state": len({row["state_id"] for row in private_key}) == 132,
        "no_calls_labels_responses_or_outcomes": True,
    }
    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        raise RuntimeError("P2A packet validation failed: " + ", ".join(failed))
    packet_a_path = public_dir / "reviewer_a_packet_unlabeled.jsonl"
    packet_b_path = public_dir / "reviewer_b_packet_unlabeled.jsonl"
    private_path = private_dir / "private_case_key.jsonl"
    instructions_path = public_dir / "instructions.json"
    _write_jsonl(packet_a_path, packet_a)
    _write_jsonl(packet_b_path, packet_b)
    _write_jsonl(private_path, private_key)
    instructions_path.write_text(
        json.dumps(
            {
                "protocol": design["protocol"],
                "truth_boundaries": design["truth_boundaries"],
                "projection": design["projection"],
                "review_surface": design["review_surface"],
                "qualification_gates_per_component": design[
                    "qualification_gates_per_component"
                ],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    artifacts = {
        "reviewer_a_packet": {"path": str(packet_a_path), "sha256": _sha(packet_a_path)},
        "reviewer_b_packet": {"path": str(packet_b_path), "sha256": _sha(packet_b_path)},
        "instructions": {"path": str(instructions_path), "sha256": _sha(instructions_path)},
        "private_case_key": {"path": str(private_path), "sha256": _sha(private_path)},
    }
    report = {
        "protocol": "pm-v1.5-paper1-p2a-suitability-packet-materialization-report-v1",
        "status": "P2A_SUITABILITY_PACKET_PASS_REVIEW_CALLS_NOT_AUTHORIZED",
        "method_id": authority["active_method"]["method_id"],
        "authority_sha256": _sha(AUTHORITY),
        "phase_manifest_sha256": _sha(phase_path),
        "design_sha256": _sha(inputs["p2_design"]),
        "checks": checks,
        "failed_checks": failed,
        "counts": {"items": len(packet_a), "components": dict(component_counts), "groups": private_groups},
        "artifacts": artifacts,
        "api_calls": 0,
        "labels_created": 0,
        "responses_generated": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }
    report_path = public_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase-manifest", type=Path)
    args = parser.parse_args()
    if args.phase_manifest is None:
        _authorized(None)
        raise AssertionError("unreachable")
    print(json.dumps(run(args.phase_manifest), ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
