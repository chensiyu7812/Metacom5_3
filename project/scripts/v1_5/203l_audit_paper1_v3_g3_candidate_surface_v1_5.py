from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping


ROOT = Path(__file__).resolve().parents[2]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from metacom_pm.v1_5_memory_realization_v2 import is_low_information_turn  # noqa: E402
from metacom_pm.v1_5_v5_2_atomic_memory import compile_atomic_reusable_outcome  # noqa: E402


AUTHORITY = ROOT / "data/pm_v1_5_contracts/active_method_authority_v1.json"
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_v3_g3_candidate_surface_audit_phase_v1.json"
DEFAULT_OUTPUT = ROOT / "outputs/pm_v1_5_paper1_v3_g3_candidate_surface_audit_20260811"
_TOKEN = re.compile(r"[a-z0-9']+")
_FORBIDDEN_RUNTIME_KEYS = {
    "summary",
    "observation",
    "event_timeline",
    "event_outcome",
    "influenced_by",
    "qa_answer",
    "qa_evidence",
    "future_supporter_reply",
    "supporter_response_outcome",
}


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


def _sha_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _tokens(value: object) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(str(value or "").lower()))


def _contains_token_phrase(container: object, phrase: object) -> bool:
    haystack = _tokens(container)
    needle = _tokens(phrase)
    if not haystack or not needle or len(needle) > len(haystack):
        return False
    return any(
        haystack[index : index + len(needle)] == needle
        for index in range(len(haystack) - len(needle) + 1)
    )


def _containment_echo(left: object, right: object) -> bool:
    a = _tokens(left)
    b = _tokens(right)
    if not a or not b:
        return False
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return any(
        longer[index : index + len(shorter)] == shorter
        for index in range(len(longer) - len(shorter) + 1)
    )


def _forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in _FORBIDDEN_RUNTIME_KEYS:
                found.add(normalized)
            found.update(_forbidden_keys(child))
    elif isinstance(value, list):
        for child in value:
            found.update(_forbidden_keys(child))
    return found


def _current_visible_text(state: Mapping[str, Any]) -> str:
    return "\n".join(
        str(turn.get("content") or "")
        for turn in state["visible_current_session_dialogue"]
        if str(turn.get("speaker") or "").lower() == "seeker"
    )


def _concentration(counter: Counter[str]) -> dict[str, Any]:
    total = sum(counter.values())
    shares = [count / total for count in counter.values()] if total else []
    return {
        "unique_candidates": len(counter),
        "top_candidate_count": max(counter.values(), default=0),
        "top_candidate_share": max(shares, default=0.0),
        "hhi": sum(share * share for share in shares),
    }


def _bound_inputs() -> tuple[dict[str, Any], dict[str, Any], dict[str, Path]]:
    authority = _read(AUTHORITY)
    phase = _read(PHASE)
    binding = authority["current_phase"]["system_feasibility_design_candidate"][
        "component_general_v3_g3_candidate_surface_audit"
    ]
    if binding["path"] != str(PHASE.relative_to(ROOT)) or binding["sha256"] != _sha(PHASE):
        raise RuntimeError("G3 phase is not authority hash-bound")
    if binding["execution_authority"] is not True and binding.get("status") != (
        "G3_CANDIDATE_SURFACE_COMPLETE_MP_MS_G4_PACKET_DESIGN_READY_ME_PROVISIONAL"
    ):
        raise RuntimeError("G3 audit is neither active nor authority-bound complete")
    if phase["status"] != "G3_ZERO_API_PUBLIC_CANDIDATE_SURFACE_AUDIT_AUTHORIZED_ONCE":
        raise RuntimeError("G3 phase status does not authorize this audit")
    inputs = {row["role"]: _resolve(row["path"]) for row in phase["input_bindings"]}
    for row in phase["input_bindings"]:
        if _sha(inputs[row["role"]]) != row["sha256"]:
            raise RuntimeError(f"bound input drifted: {row['role']}")
    return authority, phase, inputs


def build_audit() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    authority, phase, inputs = _bound_inputs()
    states = _jsonl(inputs["evoemo_states"])
    candidates = _jsonl(inputs["evoemo_candidates"])
    rank_rows_all = _jsonl(inputs["actual_rank1_unlabeled"])
    groups = _jsonl(inputs["canonical_groups"])
    rank_rows = [
        row
        for row in rank_rows_all
        if row.get("dataset") == "EvoEmo" and row.get("component") in {"MP", "MS", "ME"}
    ]
    state_by_id = {str(row["state_id"]): row for row in states}
    candidate_by_id = {str(row["candidate_id"]): row for row in candidates}
    canonical_group_by_owner: dict[str, str] = {}
    for row in groups:
        if row.get("dataset") != "EvoEmo":
            continue
        for owner in row["runtime_owners"]:
            canonical_group_by_owner[f"evo::{owner}"] = str(row["split_group_key"])

    key_counter = Counter((str(row["state_id"]), str(row["component"])) for row in rank_rows)
    expected_keys = {
        (str(state["state_id"]), component)
        for state in states
        for component in ("MP", "MS", "ME")
    }
    present_by_state: dict[str, set[str]] = defaultdict(set)
    candidate_reuse: dict[str, Counter[str]] = defaultdict(Counter)
    field_counts: Counter[str] = Counter()
    group_present_counts: dict[str, Counter[str]] = defaultdict(Counter)
    diagnostics: list[dict[str, Any]] = []
    join_missing = 0
    owner_mismatch = 0
    group_mismatch = 0
    strict_past_failure = 0
    source_hash_mismatch = 0
    future_visible_failure = 0
    me_exact_span_failure = 0
    me_compiler_failure = 0
    leakage_keys: set[str] = set()

    for state in states:
        leakage_keys.update(_forbidden_keys(state))
        dialogue = state["visible_current_session_dialogue"]
        if (
            not dialogue
            or str(dialogue[-1].get("speaker") or "").lower() != "seeker"
            or int(dialogue[-1].get("raw_turn_index")) != int(state["raw_current_turn_index"])
        ):
            future_visible_failure += 1
        if canonical_group_by_owner.get(str(state["runtime_owner_key"])) != str(
            state["split_group_key"]
        ):
            group_mismatch += 1

    for row in rank_rows:
        leakage_keys.update(_forbidden_keys(row))
        state = state_by_id.get(str(row["state_id"]))
        component = str(row["component"])
        diagnostic: dict[str, Any] = {
            "protocol": "pm-v1.5-paper1-v3-g3-candidate-surface-diagnostic-v1",
            "state_id": str(row["state_id"]),
            "component": component,
            "runtime_owner_key": str(row["runtime_owner_key"]),
            "split_group_key": str(row["split_group_key"]),
            "outer_fold": row.get("outer_fold"),
            "candidate_present": bool(row["candidate_present"]),
            "actual_rank1_id": row.get("actual_rank1_id"),
            "strict_past_pool_count": int(row["strict_past_pool_count"]),
            "selection_method": row.get("selection_method"),
            "selection_score": row.get("selection_score"),
            "top1_top2_margin": row.get("top1_top2_margin"),
            "hard_off_reason": row.get("hard_off_reason"),
            "candidate_age_sessions": None,
            "proxy_flags_are_not_labels": True,
            "suitability_label": None,
        }
        if state is None:
            join_missing += 1
            diagnostics.append(diagnostic)
            continue
        if str(row["runtime_owner_key"]) != str(state["runtime_owner_key"]):
            owner_mismatch += 1
        if not row["candidate_present"]:
            diagnostics.append(diagnostic)
            continue
        present_by_state[str(row["state_id"])].add(component)
        candidate_id = str(row["actual_rank1_id"])
        candidate = candidate_by_id.get(candidate_id)
        if candidate is None:
            join_missing += 1
            diagnostics.append(diagnostic)
            continue
        candidate_reuse[component][candidate_id] += 1
        connected_group = canonical_group_by_owner.get(str(row["runtime_owner_key"]))
        if connected_group:
            group_present_counts[component][connected_group] += 1
        if str(candidate["runtime_owner_key"]) != str(state["runtime_owner_key"]):
            owner_mismatch += 1
        available = int(candidate["available_after_session_index"])
        current_session = int(state["source_session_index"])
        if available >= current_session:
            strict_past_failure += 1
        diagnostic["candidate_age_sessions"] = current_session - available
        literal = " ".join(str(candidate["literal_text"]).split())
        if row["actual_rank1_increment_sha256"] != _sha_text(literal):
            source_hash_mismatch += 1
        current_visible = _current_visible_text(state)
        if component == "MP":
            field = str(candidate.get("profile_field") or "")
            field_counts[field] += 1
            value = str(candidate["literal_text"]).split(":", 1)[-1].strip()
            diagnostic.update(
                {
                    "profile_field": field,
                    "scope_match_level": row["retrieval_observations"].get(
                        "scope_match_level"
                    ),
                    "exact_profile_value_already_visible": _contains_token_phrase(
                        current_visible, value
                    ),
                }
            )
        elif component == "MS":
            diagnostic.update(
                {
                    "atomic_single_seeker_turn": candidate.get("source_turn_index")
                    is not None
                    and "\n" not in str(candidate["literal_text"]),
                    "low_information_rank1": is_low_information_turn(literal),
                    "exact_or_containment_current_echo": _containment_echo(
                        literal, state["current_user_text"]
                    ),
                    "candidate_word_count": len(_tokens(literal)),
                    "semantic_review_needed_for_stale_wrong_event_or_material_use": True,
                }
            )
        elif component == "ME":
            action = str(candidate.get("action_span") or "")
            result = str(candidate.get("result_span") or "")
            exact_spans = bool(action and result and action in str(candidate["literal_text"]) and result in str(candidate["literal_text"]))
            compiler_valid = compile_atomic_reusable_outcome(str(candidate["literal_text"])) is not None
            if not exact_spans:
                me_exact_span_failure += 1
            if not compiler_valid:
                me_compiler_failure += 1
            diagnostic.update(
                {
                    "typed_action_and_result_exact": exact_spans,
                    "compiler_valid": compiler_valid,
                    "action_word_count": len(_tokens(action)),
                    "result_word_count": len(_tokens(result)),
                    "semantic_review_needed_for_action_readiness_and_transfer": True,
                }
            )
        diagnostics.append(diagnostic)

    component_counts: dict[str, dict[str, Any]] = {}
    for component in ("MP", "MS", "ME"):
        rows = [row for row in diagnostics if row["component"] == component]
        present = [row for row in rows if row["candidate_present"]]
        component_counts[component] = {
            "rows": len(rows),
            "present": len(present),
            "absent": len(rows) - len(present),
            "availability_rate": len(present) / len(rows) if rows else 0.0,
            "connected_groups_with_present_candidate": len(group_present_counts[component]),
            "runtime_owners_with_present_candidate": len(
                {row["runtime_owner_key"] for row in present}
            ),
            "reuse": _concentration(candidate_reuse[component]),
        }
    mp_rows = [row for row in diagnostics if row["component"] == "MP" and row["candidate_present"]]
    ms_rows = [row for row in diagnostics if row["component"] == "MS" and row["candidate_present"]]
    me_rows = [row for row in diagnostics if row["component"] == "ME" and row["candidate_present"]]
    co_presence = Counter(
        "+".join(component for component in ("MP", "MS", "ME") if component in present_by_state.get(str(state["state_id"]), set())) or "NONE"
        for state in states
    )
    structural_checks = {
        "input_hashes_match": all(
            _sha(inputs[row["role"]]) == row["sha256"]
            for row in phase["input_bindings"]
        ),
        "state_ids_unique": len(state_by_id) == len(states),
        "candidate_ids_unique": len(candidate_by_id) == len(candidates),
        "exactly_one_row_per_state_component": set(key_counter) == expected_keys
        and all(count == 1 for count in key_counter.values())
        and len(rank_rows) == len(expected_keys),
        "all_suitability_labels_null": all(row.get("suitability_label") is None for row in rank_rows)
        and all(row["suitability_label"] is None for row in diagnostics),
        "candidate_and_state_joins_complete": join_missing == 0,
        "owner_integrity": owner_mismatch == 0,
        "canonical_connected_group_integrity": group_mismatch == 0
        and len(set(canonical_group_by_owner.values())) == phase["expected_denominators"]["connected_groups"],
        "strict_past_integrity": strict_past_failure == 0,
        "source_hash_integrity": source_hash_mismatch == 0,
        "visible_dialogue_ends_at_current_seeker_turn": future_visible_failure == 0,
        "typed_me_exact_spans": me_exact_span_failure == 0,
        "typed_me_compiler_valid": me_compiler_failure == 0,
        "forbidden_runtime_leakage_zero": not leakage_keys,
        "expected_denominators_match": len(states) == phase["expected_denominators"]["evoemo_states"]
        and component_counts["MP"]["present"] == phase["expected_denominators"]["MP_present"]
        and component_counts["MS"]["present"] == phase["expected_denominators"]["MS_present"]
        and component_counts["ME"]["present"] == phase["expected_denominators"]["ME_present"],
        "co_present_components_remain_separate_rows": co_presence["MP+MS+ME"] > 0
        and len(rank_rows) == len(states) * 3,
    }
    failed = [name for name, passed in structural_checks.items() if not passed]
    findings = [
        {
            "id": "G3-MP-FIELD-SKEW",
            "severity": "MEDIUM",
            "finding": "MP actual Rank-1 is dominated by job-scope candidates; field-stratified packet sampling is required.",
            "evidence": {"field_counts": dict(field_counts)},
            "impact": "An unstratified packet or model could mostly learn work-related scope instead of general profile-based personalization.",
        },
        {
            "id": "G3-MS-HARD-NEGATIVE-STRATA",
            "severity": "EXPECTED_HIGH_VALUE_NEGATIVES",
            "finding": "Atomic MS Rank-1 includes low-information and current-echo candidates that must remain candidate-present anchored negatives when semantically inappropriate.",
            "evidence": {
                "low_information_rows": sum(bool(row["low_information_rank1"]) for row in ms_rows),
                "current_echo_rows": sum(bool(row["exact_or_containment_current_echo"]) for row in ms_rows),
            },
            "impact": "Treating source-session lineage as positive would reproduce the historical Thanks/echo memory misuse failure.",
        },
        {
            "id": "G3-ME-SPARSE-TRANSFER",
            "severity": "MEDIUM",
            "finding": "ME is structurally valid but sparse and reuses a small number of action-result candidates.",
            "evidence": {
                "present_rows": len(me_rows),
                "connected_groups": component_counts["ME"]["connected_groups_with_present_candidate"],
                **component_counts["ME"]["reuse"],
            },
            "impact": "ME stays provisional until G4 shows both suitable and unsuitable action-readiness/transfer cases across real groups.",
        },
        {
            "id": "G3-NONEXCLUSIVE-CO-PRESENCE",
            "severity": "POSITIVE_CAPACITY",
            "finding": "The public surface contains states with MP, MS, and ME simultaneously present; none were collapsed into a single memory choice.",
            "evidence": {"co_presence": dict(co_presence)},
            "impact": "G4 can label each component independently and later preserve the full multi-memory action.",
        },
    ]
    report = {
        "protocol": "pm-v1.5-paper1-v3-g3-candidate-surface-audit-v1",
        "status": (
            "G3_CANDIDATE_SURFACE_PASS_MP_MS_G4_PACKET_DESIGN_READY_ME_PROVISIONAL"
            if not failed
            else "G3_CANDIDATE_SURFACE_FAIL_CLOSED"
        ),
        "structural_checks": structural_checks,
        "failed_checks": failed,
        "grain": phase["intended_grain"],
        "counts": {
            "states": len(states),
            "diagnostic_rows": len(diagnostics),
            "runtime_owners": len({str(state["runtime_owner_key"]) for state in states}),
            "connected_groups": len(set(canonical_group_by_owner.values())),
            "components": component_counts,
            "co_presence": dict(co_presence),
        },
        "diagnostics": {
            "MP": {
                "field_counts": dict(field_counts),
                "exact_profile_value_already_visible": sum(
                    bool(row["exact_profile_value_already_visible"]) for row in mp_rows
                ),
            },
            "MS": {
                "atomic_single_seeker_turn": sum(
                    bool(row["atomic_single_seeker_turn"]) for row in ms_rows
                ),
                "low_information_rank1": sum(
                    bool(row["low_information_rank1"]) for row in ms_rows
                ),
                "exact_or_containment_current_echo": sum(
                    bool(row["exact_or_containment_current_echo"]) for row in ms_rows
                ),
            },
            "ME": {
                "typed_action_and_result_exact": sum(
                    bool(row["typed_action_and_result_exact"]) for row in me_rows
                ),
                "compiler_valid": sum(bool(row["compiler_valid"]) for row in me_rows),
                "action_readiness_and_transfer": "REQUIRES_G4_ANCHORED_SEMANTIC_DECISION",
            },
        },
        "head_decisions": {
            "MP": "G4_PACKET_DESIGN_READY_STRATIFY_BY_FIELD_GROUP_AND_CURRENT_REDUNDANCY",
            "MS": "G4_PACKET_DESIGN_READY_PRESERVE_LOW_INFORMATION_ECHO_STALE_WRONG_EVENT_NEGATIVES",
            "ME": "G4_PACKET_DESIGN_PROVISIONAL_REQUIRE_BIDIRECTIONAL_READINESS_AND_TRANSFER_SUPPORT",
        },
        "findings": findings,
        "feature_allowlist_by_head": phase["primary_feature_allowlist_by_head"],
        "forbidden_runtime_keys_found": sorted(leakage_keys),
        "hashes": {
            "authority_sha256": _sha(AUTHORITY),
            "phase_sha256": _sha(PHASE),
            "inputs": {row["role"]: row["sha256"] for row in phase["input_bindings"]},
        },
        "api_calls": 0,
        "labels_created": 0,
        "pm_fit": False,
        "generator_calls": 0,
        "reviewer_calls": 0,
        "external_outcomes_read": False,
    }
    return diagnostics, report


def _render_html(report: Mapping[str, Any]) -> str:
    component_rows = "".join(
        "<tr>"
        f"<td>{escape(component)}</td>"
        f"<td>{values['present']:,}</td>"
        f"<td>{values['availability_rate']:.1%}</td>"
        f"<td>{values['connected_groups_with_present_candidate']}</td>"
        f"<td>{values['reuse']['unique_candidates']}</td>"
        f"<td>{values['reuse']['top_candidate_share']:.1%}</td>"
        "</tr>"
        for component, values in report["counts"]["components"].items()
    )
    finding_rows = "".join(
        "<tr>"
        f"<td>{escape(row['id'])}</td>"
        f"<td>{escape(row['severity'])}</td>"
        f"<td>{escape(row['finding'])}</td>"
        f"<td>{escape(row['impact'])}</td>"
        "</tr>"
        for row in report["findings"]
    )
    check_rows = "".join(
        f"<tr><td>{escape(name)}</td><td class={'pass' if passed else 'fail'}>{'PASS' if passed else 'FAIL'}</td></tr>"
        for name, passed in report["structural_checks"].items()
    )
    return f"""<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8"><title>PM V1.5 V3 G3 Candidate Surface Audit</title>
<style>
body{{font-family:system-ui,-apple-system,sans-serif;max-width:1180px;margin:32px auto;padding:0 24px;color:#17202a;background:#f7f9fb}}
h1,h2{{color:#102a43}} .hero{{background:white;border-left:6px solid #16836f;padding:22px;border-radius:10px;box-shadow:0 2px 12px #0001}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:18px 0}} .card{{background:white;padding:16px;border-radius:9px}}
.value{{font-size:1.7rem;font-weight:700}} table{{width:100%;border-collapse:collapse;background:white;margin:12px 0 26px}}
th,td{{padding:10px;border-bottom:1px solid #d9e2ec;text-align:left;vertical-align:top}} th{{background:#eaf2f8}} .pass{{color:#087f5b;font-weight:700}} .fail{{color:#c92a2a;font-weight:700}}
code{{background:#e9ecef;padding:2px 5px;border-radius:4px}} .note{{color:#52606d}}
</style></head><body>
<div class="hero"><h1>PM V1.5 Paper 1 — V3 G3 公共候选面审计</h1>
<p><strong>结论：</strong>{escape(report['status'])}</p>
<p>MP 与 atomic MS 可以进入 G4 标注包设计；ME 结构合法但保持 provisional，必须在 G4 证明 action-readiness 与 transfer 的双向支持。所有 suitability 决定按组件非排他保存。</p></div>
<div class="grid"><div class="card"><div class="value">{report['counts']['states']:,}</div>states</div>
<div class="card"><div class="value">{report['counts']['diagnostic_rows']:,}</div>state×component rows</div>
<div class="card"><div class="value">{report['counts']['connected_groups']}</div>connected groups</div>
<div class="card"><div class="value">{report['counts']['co_presence'].get('MP+MS+ME',0)}</div>all-memory co-present states</div></div>
<h2>候选面</h2><table><thead><tr><th>Head</th><th>Present</th><th>Availability</th><th>Groups</th><th>Unique candidates</th><th>Top reuse share</th></tr></thead><tbody>{component_rows}</tbody></table>
<h2>关键发现</h2><table><thead><tr><th>ID</th><th>Severity</th><th>Finding</th><th>Impact</th></tr></thead><tbody>{finding_rows}</tbody></table>
<h2>结构与泄漏机器门</h2><table><tbody>{check_rows}</tbody></table>
<p class="note">低信息、current echo、current redundancy 是未标注的困难候选 strata，不是自动负标签。stale、wrong-event、material use、action readiness 与 transfer 留给 G4 anchored semantic decision。</p>
<p class="note">API calls=0；labels created=0；PM fit=false；generator/reviewer calls=0。</p>
</body></html>"""


def write_outputs(output_dir: Path) -> dict[str, Any]:
    diagnostics, report = build_audit()
    if output_dir.exists():
        raise RuntimeError("G3 output directory already exists; refusing to overwrite")
    output_dir.mkdir(parents=True)
    diagnostic_path = output_dir / "candidate_surface_diagnostics_unlabeled.jsonl"
    with diagnostic_path.open("w", encoding="utf-8") as handle:
        for row in diagnostics:
            handle.write(_canonical(row) + "\n")
    report = dict(report)
    report["artifacts"] = {
        "diagnostic_rows": {
            "path": str(diagnostic_path),
            "sha256": _sha(diagnostic_path),
            "rows": len(diagnostics),
        },
        "report_html": {"path": str(output_dir / "report.html")},
    }
    report_path = output_dir / "report.json"
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    html_path = output_dir / "report.html"
    html_path.write_text(_render_html(report), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    if args.validate_only:
        _, report = build_audit()
    else:
        report = write_outputs(args.output_dir)
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
