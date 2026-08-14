from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4a_packet_materialization_phase_v2.json"
PUBLIC = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811"
PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811"
DEFAULT_OUTPUT = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_audit_20260811"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _surface_signature(row: Mapping[str, Any]) -> str:
    payload = {key: value for key, value in row.items() if key not in {"review_item_id", "review_position"}}
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _control_content_signature(row: Mapping[str, Any]) -> str:
    payload = {
        "component": row["component"],
        "visible": [span["content"] for span in row["visible_spans"]],
        "candidate": [span["content"] for span in row["candidate_spans"]],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _html(report: Mapping[str, Any]) -> str:
    rows = "".join(
        f"<tr><td>{escape(key)}</td><td>{'PASS' if value else 'FAIL'}</td></tr>"
        for key, value in report["checks"].items()
    )
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>G4A V2 independent audit</title>
<style>body{{font-family:system-ui;max-width:1050px;margin:2rem auto;line-height:1.45}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.4rem}}</style></head><body>
<h1>G4A V2 independent packet audit</h1><p><strong>{escape(str(report['status']))}</strong></p>
<p>This audit independently re-reads the materialized files. It creates no labels and makes no reviewer/API call.</p>
<table><tr><th>Check</th><th>Result</th></tr>{rows}</table></body></html>"""


def audit() -> dict[str, Any]:
    phase = _read(PHASE)
    design = _read(ROOT / "data/pm_v1_5_contracts/paper1_v3_g4_nonexclusive_suitability_design_v1.json")
    report = _read(PUBLIC / "report.json")
    packet_a = _jsonl(PUBLIC / "reviewer_a_packet.jsonl")
    packet_b = _jsonl(PUBLIC / "reviewer_b_packet.jsonl")
    controls_a = _jsonl(PUBLIC / "reviewer_a_controls.jsonl")
    controls_b = _jsonl(PUBLIC / "reviewer_b_controls.jsonl")
    case_key = _jsonl(PRIVATE / "private_case_key.jsonl")
    control_key = _jsonl(PRIVATE / "control_gold_key.jsonl")
    v1_controls = _jsonl(
        ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_20260811/reviewer_a_controls.jsonl"
    )

    count_by_component = Counter(row["component"] for row in case_key)
    group_by_component: dict[str, set[str]] = defaultdict(set)
    state_components: dict[str, set[str]] = defaultdict(set)
    for row in case_key:
        group_by_component[row["component"]].add(row["split_group_key"])
        state_components[row["state_id"]].add(row["component"])
    all_three_groups = {
        row["split_group_key"]
        for row in case_key
        if state_components[row["state_id"]] == {"MP", "MS", "ME"}
    }
    a_surfaces = {_surface_signature(row) for row in packet_a}
    b_surfaces = {_surface_signature(row) for row in packet_b}
    v1_control_surfaces = {_control_content_signature(row) for row in v1_controls}
    v2_control_surfaces = {_control_content_signature(row) for row in controls_a}
    gold_by_a_id = {row["reviewer_a_item_id"]: row for row in control_key}
    mp_positive_no_exact_value_echo = True
    for item in controls_a:
        gold = gold_by_a_id[item["review_item_id"]]
        if item["component"] != "MP" or gold["gold_decision"] != "SUITABLE":
            continue
        visible = " ".join(span["content"].lower() for span in item["visible_spans"])
        candidate_value = item["candidate_spans"][0]["content"].split(":", 1)[-1].strip().lower()
        if candidate_value in visible:
            mp_positive_no_exact_value_echo = False
    retired_axis_names = {
        "current_target_fit",
        "specific_increment_available",
        "component_minimum_possible_now",
        "current_boundary_permits",
    }
    public_text = json.dumps(packet_a + packet_b + controls_a + controls_b, ensure_ascii=False)
    allowed_codes_valid = True
    packet_by_a_id = {row["review_item_id"]: row for row in controls_a}
    for gold in control_key:
        item = packet_by_a_id[gold["reviewer_a_item_id"]]
        decision = gold["gold_decision"]
        reason = gold["gold_primary_reason_code"]
        contract = item["decision_contract"]
        allowed = (
            contract["suitable_reason_codes"]
            if decision == "SUITABLE"
            else contract["not_suitable_reason_codes"]
            if decision == "NOT_SUITABLE"
            else contract["abstain_reason_codes"]
        )
        if reason not in allowed:
            allowed_codes_valid = False

    artifact_hashes_valid = all(
        _sha(ROOT / artifact["path"]) == artifact["sha256"]
        for artifact in report["artifacts"].values()
    )
    checks = {
        "terminal_materialization_report_pass": report["status"]
        == phase["required_terminal_status"]
        and report["failed_checks"] == [],
        "artifact_hashes_recompute": artifact_hashes_valid,
        "public_packet_hashes_equal_frozen_v1_carry": _sha(PUBLIC / "reviewer_a_packet.jsonl")
        == phase["carry_invariants"]["reviewer_a_packet_sha256"]
        and _sha(PUBLIC / "reviewer_b_packet.jsonl")
        == phase["carry_invariants"]["reviewer_b_packet_sha256"]
        and _sha(PRIVATE / "private_case_key.jsonl")
        == phase["carry_invariants"]["private_case_key_sha256"],
        "exact_507_component_cases": len(case_key) == 507
        and count_by_component == {"MP": 204, "MS": 204, "ME": 99}
        and len({(row["state_id"], row["component"]) for row in case_key}) == 507,
        "group_support_exact": {
            component: len(groups) for component, groups in group_by_component.items()
        }
        == {"MP": 17, "MS": 17, "ME": 15},
        "nonexclusive_all_three_preserved": len(all_three_groups) == 14
        and any(components == {"MP", "MS", "ME"} for components in state_components.values()),
        "reviewer_packets_same_surfaces_independent_ids": len(packet_a) == len(packet_b) == 507
        and a_surfaces == b_surfaces
        and not (
            {row["review_item_id"] for row in packet_a}
            & {row["review_item_id"] for row in packet_b}
        ),
        "controls_exact_36_and_six_surface_delta": len(controls_a) == len(controls_b) == len(control_key) == 36
        and len(v1_control_surfaces & v2_control_surfaces) == 30
        and len(v2_control_surfaces - v1_control_surfaces) == 6,
        "control_class_balance_per_component": all(
            Counter(
                row["gold_decision"] for row in control_key if row["component"] == component
            )
            == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2}
            for component in ("MP", "MS", "ME")
        ),
        "control_reason_codes_valid": allowed_codes_valid,
        "mp_positive_controls_no_exact_profile_value_echo": mp_positive_no_exact_value_echo,
        "retired_four_axis_outputs_absent": not any(name in public_text for name in retired_axis_names),
        "public_has_no_gold_or_private_join_keys": all(
            key not in public_text
            for key in (
                "gold_decision",
                "gold_primary_reason_code",
                "case_key",
                "state_id",
                "split_group_key",
                "outer_fold",
                "selection_score",
                "suitability_label",
            )
        ),
        "no_reviews_labels_or_fit": report["reviewer_calls"] == 0
        and report["labels_created"] == 0
        and report["pm_fit"] is False
        and report["api_calls"] == 0,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-v3-g4a-packet-v2-independent-audit-v1",
        "status": (
            "G4A_V2_PACKET_INDEPENDENT_AUDIT_PASS_G4B_REVIEW_PHASE_MAY_BE_DESIGNED"
            if not failed
            else "G4A_V2_PACKET_INDEPENDENT_AUDIT_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            "public_cases": len(case_key),
            "MP": count_by_component["MP"],
            "MS": count_by_component["MS"],
            "ME": count_by_component["ME"],
            "fresh_controls": len(control_key),
            "all_three_groups": len(all_three_groups),
        },
        "hashes": {
            "phase_sha256": _sha(PHASE),
            "materialization_report_sha256": _sha(PUBLIC / "report.json"),
            "reviewer_a_packet_sha256": _sha(PUBLIC / "reviewer_a_packet.jsonl"),
            "reviewer_b_packet_sha256": _sha(PUBLIC / "reviewer_b_packet.jsonl"),
            "private_case_key_sha256": _sha(PRIVATE / "private_case_key.jsonl"),
        },
        "api_calls": 0,
        "reviewer_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = audit()
    args.output_dir.mkdir(parents=True, exist_ok=False)
    (args.output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (args.output_dir / "report.html").write_text(_html(report), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
