from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from metacom_pm.v1_5_g4_nonexclusive_suitability_packet import (  # noqa: E402
    build_fresh_controls,
    build_packets,
    public_surface_signature,
    select_cases,
)
from metacom_pm.v1_5_paper1_suitability_review import (  # noqa: E402
    build_reviewer_controls as build_retired_controls,
)


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g4a_packet_materialization_phase_v2.json"
DEFAULT_PUBLIC = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_20260811"
DEFAULT_PRIVATE = ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_v2_private_20260811"


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _forbidden_public_keys(value: Any) -> set[str]:
    forbidden = {
        "case_key",
        "state_id",
        "runtime_owner_key",
        "split_group_key",
        "outer_fold",
        "selection_score",
        "top1_top2_margin",
        "proxy_flags",
        "suitability_label",
        "gold_decision",
        "gold_primary_reason_code",
        "future_supporter_reply",
        "summary",
        "observation",
        "event_timeline",
        "event_outcome",
        "influenced_by",
        "qa_answer",
        "qa_evidence",
        "pm_prediction",
    }
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).lower()
            if normalized in forbidden:
                found.add(normalized)
            found.update(_forbidden_public_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_forbidden_public_keys(child))
    return found


def _control_content_signature(row: Mapping[str, Any]) -> str:
    payload = {
        "component": row["component"],
        "visible": [span["content"] for span in row["visible_spans"]],
        "candidate": [span["content"] for span in row["candidate_spans"]],
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _codebook() -> str:
    return """# G4A 非排他资源适用性审核手册

本包只判断：**这个组件的 actual Rank-1 候选，是否适合用于当前下一条 supporter 回复。**

每个条目只属于一个 component。不要在 MP、MS、ME 之间选赢家；你看不到其他 component 是刻意的。
同一个底层 state 可以在另一个 component 包里再次出现，而且 MP/MS/ME 可以同时全部 SUITABLE。

## 唯一主决定

- `SUITABLE`：候选能在当前边界内实现该 component minimum，并带来当前未见的具体用途。
- `NOT_SUITABLE`：冻结材料已足以确认不应使用；选择一个最主要的负 reason code。
- `SEMANTIC_ABSTAIN`：冻结可见 state 与候选不足以解决 bounded 判断。它不是低信心分数，也不能默认改成 NOT。

四项 checklist 只表示你已经考虑：target/entity/function、nonredundant increment、component minimum、
current boundary。不要分别输出四个 YES/NO/UNKNOWN；旧四轴量表已经停用。

## 组件边界

- MP：必须静默改变约束、现实细节、framing 或必要前提。只念 profile、当前已说出、装饰性提及或刻板推断均 NOT。
- MS：严格过去的原子 user evidence 必须改变理解、一个问题、约束或当前 option。寒暄、感谢、current echo、
  wrong event、stale/resolved、同主题但无 response change 均 NOT。
- ME：过去 action-result 必须能作为 tentative user-owned evidence 或可拒绝 option。typed/完整不自动为正；
  当前不需要行动、不可迁移、已尝试/已拒绝或边界禁止均 NOT。

## 提交格式

只提交 review_item_id、decision、primary_reason_code、visible_span_ids、candidate_span_ids、
checklist_attested=`ALL_FOUR_CONSIDERED`。证据只用包内预编号 V/C span ID，不复制长文本。

不要判断 response quality、risk、cost、未来 generator 是否会执行，也不要猜 PM 或实验臂。
"""


def _html(report: Mapping[str, Any]) -> str:
    checks = "".join(
        f"<tr><td>{escape(name)}</td><td>{'PASS' if value else 'FAIL'}</td></tr>"
        for name, value in report["checks"].items()
    )
    counts = report["counts"]
    return f"""<!doctype html><html><head><meta charset='utf-8'><title>G4A packet audit</title>
<style>body{{font-family:system-ui;max-width:1050px;margin:2rem auto;line-height:1.45}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.4rem;text-align:left}}code{{background:#eee;padding:.1rem .25rem}}</style></head><body>
<h1>G4A nonexclusive suitability packet audit</h1>
<p><strong>Status:</strong> {escape(str(report['status']))}</p>
<p>Public cases: MP={counts['MP']}, MS={counts['MS']}, ME={counts['ME']}, total={counts['total']}.</p>
<p>Fresh controls per reviewer: {counts['controls_per_reviewer']}. API calls, labels and PM fits are all zero.</p>
<h2>Machine checks</h2><table><tr><th>Check</th><th>Result</th></tr>{checks}</table>
<h2>Interpretation</h2><p>The packet preserves one case per state × component × actual Rank-1. Cross-component reuse of a state is deliberate and hidden only for blinding; it is not a one-memory choice.</p>
</body></html>"""


def materialize(public_dir: Path, private_dir: Path) -> dict[str, Any]:
    authority = _read(AUTHORITY)
    phase = _read(PHASE)
    binding = authority["current_phase"]["system_feasibility_design_candidate"][
        "component_general_v3_g4a_packet_materialization_v2"
    ]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != _sha(PHASE):
        raise RuntimeError("G4A phase is not authority hash-bound")
    if binding["execution_authority"] is not True:
        raise RuntimeError("G4A one-time materialization is not active")
    if phase["status"] != "G4A_V2_ZERO_API_CONTROL_REPAIR_AND_PACKET_REMATERIALIZATION_AUTHORIZED_ONCE":
        raise RuntimeError("G4A phase status does not authorize materialization")
    inputs = {row["role"]: _resolve(row["path"]) for row in phase["input_bindings"]}
    for row in phase["input_bindings"]:
        if _sha(inputs[row["role"]]) != row["sha256"]:
            raise RuntimeError(f"bound input drifted: {row['role']}")
    if (public_dir / "report.json").exists() or (private_dir / "private_case_key.jsonl").exists():
        raise FileExistsError("G4A successful-looking output already exists; overwrite forbidden")

    design = _read(inputs["g4_design"])
    diagnostics = _jsonl(inputs["g3_diagnostics"])
    states = {str(row["state_id"]): row for row in _jsonl(inputs["evoemo_states"])}
    candidates = {
        str(row["candidate_id"]): row for row in _jsonl(inputs["evoemo_candidates"])
    }
    rank1 = {
        (str(row["state_id"]), str(row["component"])): row
        for row in _jsonl(inputs["actual_rank1_unlabeled"])
        if row.get("dataset") == "EvoEmo" and row.get("component") in {"MP", "MS", "ME"}
    }
    selected, shared_state_by_group = select_cases(diagnostics)
    reviewer_a, reviewer_b, private_key = build_packets(
        selected=selected, states=states, candidates=candidates, design=design
    )
    control_a, control_b, control_key = build_fresh_controls(design)

    counts = Counter(str(row["component"]) for row in private_key)
    group_counts: dict[str, Counter[str]] = defaultdict(Counter)
    for row in private_key:
        group_counts[str(row["component"])][str(row["split_group_key"])] += 1
    selected_keys = {(row["state_id"], row["component"]): row for row in private_key}
    shared_ok = all(
        all((state_id, component) in selected_keys for component in ("MP", "MS", "ME"))
        for state_id in shared_state_by_group.values()
    )
    mp_selected = {row["state_id"] for row in private_key if row["component"] == "MP"}
    ms_selected = {row["state_id"] for row in private_key if row["component"] == "MS"}
    me_candidate_ids = {
        row["actual_rank1_id"] for row in private_key if row["component"] == "ME"
    }
    all_mp_flags = {
        str(row["state_id"])
        for row in diagnostics
        if row["component"] == "MP"
        and row["candidate_present"]
        and row.get("exact_profile_value_already_visible")
    }
    all_ms_low = {
        str(row["state_id"])
        for row in diagnostics
        if row["component"] == "MS" and row["candidate_present"] and row.get("low_information_rank1")
    }
    all_ms_echo = {
        str(row["state_id"])
        for row in diagnostics
        if row["component"] == "MS"
        and row["candidate_present"]
        and row.get("exact_or_containment_current_echo")
    }
    all_me_candidates = {
        str(row["actual_rank1_id"])
        for row in diagnostics
        if row["component"] == "ME" and row["candidate_present"]
    }
    rank1_match = all(
        rank1[(row["state_id"], row["component"])]["actual_rank1_id"]
        == row["actual_rank1_id"]
        for row in private_key
    )
    a_signatures = {public_surface_signature(row) for row in reviewer_a}
    b_signatures = {public_surface_signature(row) for row in reviewer_b}
    a_order = [public_surface_signature(row) for row in reviewer_a]
    b_order = [public_surface_signature(row) for row in reviewer_b]
    old_controls, _old_key = build_retired_controls()
    old_control_signatures = {_control_content_signature(row) for row in old_controls}
    new_control_signatures = {_control_content_signature(row) for row in control_a}
    v1_controls = _jsonl(
        ROOT / "outputs/pm_v1_5_paper1_v3_g4a_packet_20260811/reviewer_a_controls.jsonl"
    )
    v1_control_signatures = {_control_content_signature(row) for row in v1_controls}
    control_distribution = Counter(row["gold_decision"] for row in control_key)
    control_component_distribution = {
        component: Counter(
            row["gold_decision"] for row in control_key if row["component"] == component
        )
        for component in ("MP", "MS", "ME")
    }
    public_rows = reviewer_a + reviewer_b + control_a + control_b
    forbidden_found = sorted(_forbidden_public_keys(public_rows))
    checks = {
        "exact_component_denominators": counts == {"MP": 204, "MS": 204, "ME": 99},
        "total_507_unique_component_cases": len(private_key) == 507
        and len({(row["state_id"], row["component"]) for row in private_key}) == 507,
        "actual_rank1_binding_exact": rank1_match,
        "mp_12_per_17_groups": len(group_counts["MP"]) == 17
        and set(group_counts["MP"].values()) == {12},
        "ms_12_per_17_groups": len(group_counts["MS"]) == 17
        and set(group_counts["MS"].values()) == {12},
        "me_99_all_15_groups_cap7": len(group_counts["ME"]) == 15
        and sum(group_counts["ME"].values()) == 99
        and max(group_counts["ME"].values()) <= 7,
        "all_three_shared_states_preserved": len(shared_state_by_group) == 14 and shared_ok,
        "all_mp_current_redundancy_flags_included": all_mp_flags <= mp_selected
        and len(all_mp_flags) == 12,
        "all_ms_low_information_and_echo_included": all_ms_low <= ms_selected
        and all_ms_echo <= ms_selected
        and len(all_ms_low) == 21
        and len(all_ms_echo) == 32,
        "all_23_me_candidates_represented": me_candidate_ids == all_me_candidates
        and len(me_candidate_ids) == 23,
        "reviewer_packets_same_cases_different_order": len(reviewer_a) == len(reviewer_b) == 507
        and a_signatures == b_signatures
        and a_order != b_order,
        "reviewer_ids_are_disjoint": not (
            {row["review_item_id"] for row in reviewer_a}
            & {row["review_item_id"] for row in reviewer_b}
        ),
        "public_payload_has_no_private_or_outcome_keys": forbidden_found == [],
        "private_public_join_complete": all(
            row["reviewer_a_item_id"] in {item["review_item_id"] for item in reviewer_a}
            and row["reviewer_b_item_id"] in {item["review_item_id"] for item in reviewer_b}
            for row in private_key
        ),
        "fresh_controls_36_each_and_new_surfaces": len(control_a) == len(control_b) == len(control_key) == 36
        and not (old_control_signatures & new_control_signatures),
        "v2_changes_exactly_six_control_surfaces": len(
            v1_control_signatures & new_control_signatures
        )
        == 30
        and len(new_control_signatures - v1_control_signatures) == 6
        and len(v1_control_signatures - new_control_signatures) == 6,
        "fresh_control_distribution_exact": control_distribution
        == {"SUITABLE": 15, "NOT_SUITABLE": 15, "SEMANTIC_ABSTAIN": 6}
        and all(
            distribution
            == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2}
            for distribution in control_component_distribution.values()
        ),
        "public_cases_have_no_labels": all(
            "gold_decision" not in row and "suitability_label" not in row
            for row in reviewer_a + reviewer_b + control_a + control_b
        ),
        "selection_proxy_flags_private_and_not_labels": all(
            row["proxy_flags_are_not_labels"] is True and row["suitability_label"] is None
            for row in private_key
        ),
    }
    failed = [name for name, passed in checks.items() if not passed]
    report: dict[str, Any] = {
        "protocol": "pm-v1.5-paper1-v3-g4a-packet-materialization-report-v2",
        "status": (
            "G4A_V2_PACKET_MATERIALIZATION_PASS_REVIEW_EXECUTION_NOT_AUTHORIZED"
            if not failed
            else "G4A_PACKET_MATERIALIZATION_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "counts": {
            "MP": counts["MP"],
            "MS": counts["MS"],
            "ME": counts["ME"],
            "total": len(private_key),
            "controls_per_reviewer": len(control_a),
            "all_three_shared_groups": len(shared_state_by_group),
        },
        "diagnostic_coverage": {
            "MP_current_redundancy": len(all_mp_flags),
            "MS_low_information": len(all_ms_low),
            "MS_current_echo": len(all_ms_echo),
            "ME_unique_candidates": len(me_candidate_ids),
        },
        "forbidden_public_keys_found": forbidden_found,
        "hashes": {
            "authority_sha256_at_execution": _sha(AUTHORITY),
            "phase_sha256": _sha(PHASE),
            "g4_design_sha256": _sha(inputs["g4_design"]),
        },
        "api_calls": 0,
        "reviewer_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
        "generator_calls": 0,
        "external_outcomes_read": False,
    }
    if failed:
        return report

    public_dir.mkdir(parents=True, exist_ok=False)
    private_dir.mkdir(parents=True, exist_ok=False)
    _write_jsonl(public_dir / "reviewer_a_packet.jsonl", reviewer_a)
    _write_jsonl(public_dir / "reviewer_b_packet.jsonl", reviewer_b)
    _write_jsonl(public_dir / "reviewer_a_controls.jsonl", control_a)
    _write_jsonl(public_dir / "reviewer_b_controls.jsonl", control_b)
    _write_jsonl(private_dir / "private_case_key.jsonl", private_key)
    _write_jsonl(private_dir / "control_gold_key.jsonl", control_key)
    (public_dir / "CODEBOOK_ZH.md").write_text(_codebook(), encoding="utf-8")
    report["artifacts"] = {}
    for path in [
        public_dir / "reviewer_a_packet.jsonl",
        public_dir / "reviewer_b_packet.jsonl",
        public_dir / "reviewer_a_controls.jsonl",
        public_dir / "reviewer_b_controls.jsonl",
        public_dir / "CODEBOOK_ZH.md",
        private_dir / "private_case_key.jsonl",
        private_dir / "control_gold_key.jsonl",
    ]:
        report["artifacts"][path.name] = {
            "path": str(path.relative_to(ROOT)),
            "sha256": _sha(path),
        }
    (public_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    (public_dir / "report.html").write_text(_html(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-dir", type=Path, default=DEFAULT_PUBLIC)
    parser.add_argument("--private-dir", type=Path, default=DEFAULT_PRIVATE)
    args = parser.parse_args()
    report = materialize(args.public_dir, args.private_dir)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
