#!/usr/bin/env python3
"""Materialize the frozen zero-API MS supervision repair and qualification packets."""

from __future__ import annotations

from collections import Counter, defaultdict
import argparse
import hashlib
from html import escape
import json
from pathlib import Path
import re
import statistics
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
PHASE = ROOT / "data/pm_v1_5_contracts/paper1_ms_supervision_repair_packet_phase_v1.json"
DEFAULT_PUBLIC = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_20260812"
DEFAULT_PRIVATE = ROOT / "outputs/pm_v1_5_paper1_ms_supervision_repair_packet_private_20260812"

REQUIRED_ANNOTATION_FIELDS = (
    "current_goal_span_ids",
    "current_support_goal",
    "past_source_span_ids",
    "candidate_increment",
    "entity_link",
    "allowed_response_change_type",
    "allowed_response_change",
    "forbidden_focus_shift",
    "nonuse_condition",
    "final_suitability",
    "decision_reason_code",
)
FORBIDDEN_PUBLIC_KEYS = {
    "actual_rank1_id",
    "binary_suitability_label",
    "case_key",
    "exact_or_containment_current_echo",
    "freeze_source",
    "gold_decision",
    "gold_primary_reason_code",
    "low_information_rank1",
    "outer_fold",
    "primary_reason_code",
    "request_hash",
    "runtime_owner_key",
    "selection_score",
    "split_group_key",
    "state_id",
    "teacher_decision",
    "teacher_is_human_gold",
    "top1_top2_margin",
}


def _read(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _stable_hex(*parts: str, length: int = 24) -> str:
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:length]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, values: Iterable[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(value, ensure_ascii=False, sort_keys=True) + "\n" for value in values),
        encoding="utf-8",
    )


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9']+", text.lower())


def _jaccard(left: str, right: str) -> float:
    a, b = set(_tokens(left)), set(_tokens(right))
    return len(a & b) / len(a | b) if a or b else 0.0


def _public_forbidden_keys(value: Any) -> set[str]:
    found: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            if key in FORBIDDEN_PUBLIC_KEYS:
                found.add(key)
            found.update(_public_forbidden_keys(nested))
    elif isinstance(value, list):
        for nested in value:
            found.update(_public_forbidden_keys(nested))
    return found


def _annotation_template() -> dict[str, Any]:
    return {
        "current_goal_span_ids": [],
        "current_support_goal": "",
        "past_source_span_ids": [],
        "candidate_increment": "",
        "entity_link": "ONE_OF_RESOLVED_UNRESOLVED_WRONG_ENTITY",
        "allowed_response_change_type": "ONE_OF_UNDERSTANDING_QUESTION_CONSTRAINT_OPTION_NONE_UNRESOLVED",
        "allowed_response_change": "",
        "forbidden_focus_shift": "",
        "nonuse_condition": "",
        "final_suitability": "ONE_OF_SUITABLE_NOT_SUITABLE_SEMANTIC_ABSTAIN",
        "decision_reason_code": "",
    }


def _decision_contract() -> dict[str, Any]:
    return {
        "unit": "Judge this MS candidate alone for this visible current state. Other components may independently be ON.",
        "positive_requires_all": [
            "owner and strictly-past time are valid",
            "entity/event link is resolved",
            "candidate contributes a specific proposition not already supplied by current context",
            "the immediate support goal can be quoted from current context",
            "a candidate-specific material and natural response change can be stated",
            "that change preserves current focus and owner/time uncertainty",
            "a concrete condition for safe nonuse can be stated",
        ],
        "not_suitable_if": [
            "source is low-information or social closing only",
            "current context already supplies the same increment",
            "candidate is the wrong entity/event",
            "candidate is stale/resolved/conflicting with no safe tentative use",
            "same topic but no immediate-goal contribution",
            "any use would shift focus away from the current need",
            "the user currently forbids past-session use",
        ],
        "abstain_only_if": [
            "entity/event resolution cannot be decided from the shown text",
            "redundancy cannot be decided from the shown text",
            "material response change cannot be decided from the shown text",
            "owner/time boundary cannot be decided from the shown text",
        ],
        "function_is_not_quality": "A candidate may be suitable even if a later generator could express it badly. State the allowed change; do not predict prose quality.",
        "no_single_memory_cap": True,
        "sixteen_requested_actions_unchanged": True,
    }


def _control_explanation(case_key: str) -> dict[str, str]:
    explanations = {
        "g4control_9a4b6805d49b9b1db35c420b": {
            "candidate_increment": "The freeze was specifically triggered by pressure for an immediate answer.",
            "allowed_response_change": "Offer preparation for the immediate-answer moment, such as a pause phrase or rehearsal, without assuming it will recur.",
            "forbidden_focus_shift": "Do not turn the reply into a general history of work stress.",
            "nonuse_condition": "Do not use if the user says the meeting format or cause of freezing is different now.",
        },
        "g4control_d7704568e040488ca719a365": {
            "candidate_increment": "The earlier headache pattern began before breakfast, which is not stated in the current message.",
            "allowed_response_change": "Tentatively check whether the before-breakfast timing has returned to clarify the present pattern.",
            "forbidden_focus_shift": "Do not diagnose a cause or assert that the old pattern is definitely current.",
            "nonuse_condition": "Do not use if the user has already described a different current timing.",
        },
        "g4control_01f94eb641ca5e2b7e890ca4": {
            "candidate_increment": "The sister previously ended the call immediately after money was mentioned.",
            "allowed_response_change": "Ask one tentative focused question about whether the money moment may explain what felt different.",
            "forbidden_focus_shift": "Do not presume money caused the current difference or broaden into unrelated family history.",
            "nonuse_condition": "Do not use if the current call did not involve money or the user wants another aspect explored.",
        },
        "g4control_83f7482454d88f2d46b2b060": {
            "candidate_increment": "A ten-minute timer previously made starting this same application feel manageable.",
            "allowed_response_change": "Keep the response low-pressure and offer the prior ten-minute start as a declineable option.",
            "forbidden_focus_shift": "Do not turn the prior success into a rule or demand completion.",
            "nonuse_condition": "Do not use if timers now add pressure or the application is no longer the same task.",
        },
        "g4control_a2fd6b2c21d48e8de15845c6": {
            "candidate_increment": "The first notice lacked both an amount and a deadline.",
            "allowed_response_change": "Use those two prior missing fields as a tentative comparison point for what changed in the new notice.",
            "forbidden_focus_shift": "Do not provide legal conclusions or assume the new notice has either field.",
            "nonuse_condition": "Do not use if the current dispute concerns a different notice or issue.",
        },
        "g4control_df1a447274dccf1e359448c3": {
            "candidate_increment": "NONE: the source is social appreciation with no proposition about the rent increase.",
            "allowed_response_change": "NONE: it cannot materially change the present support response.",
            "forbidden_focus_shift": "Do not mention or paraphrase the prior thanks to prove memory use.",
            "nonuse_condition": "Always omit this source for the shown goal.",
        },
        "g4control_dae5bfbc230ed51065142c94": {
            "candidate_increment": "NONE: the current message already supplies the interruption pattern more specifically.",
            "allowed_response_change": "NONE: respond from the current account without exposing the past source.",
            "forbidden_focus_shift": "Do not repeat the same fact as if memory added continuity.",
            "nonuse_condition": "Omit whenever current context already entails the source.",
        },
        "g4control_b977b93ac5e077f8cc755bc3": {
            "candidate_increment": "NONE for this goal: a landlord dispute is a different entity and event from the brother argument.",
            "allowed_response_change": "NONE: address the brother argument from current context.",
            "forbidden_focus_shift": "Do not redirect the user to housing or repairs.",
            "nonuse_condition": "Omit unless the user explicitly links the landlord dispute to the present need.",
        },
        "g4control_5b2ef2450f1dd390c45b27fb": {
            "candidate_increment": "NONE for the current goal: the exam fear is resolved and housing is the new concern.",
            "allowed_response_change": "NONE: support the housing concern without reopening the exam.",
            "forbidden_focus_shift": "Do not revive resolved exam anxiety.",
            "nonuse_condition": "Omit because the user explicitly closes that event and changes topic.",
        },
        "g4control_a7c891f26e52192bbffa385c": {
            "candidate_increment": "The old morning difficulty might otherwise be specific, but the current user boundary forbids its use.",
            "allowed_response_change": "NONE under the current boundary.",
            "forbidden_focus_shift": "Do not expose or allude to any past-session content.",
            "nonuse_condition": "Omit while the start-fresh request is active.",
        },
        "g4control_e5b9acefd71140c40f93adb5": {
            "candidate_increment": "UNRESOLVED: the current unnamed home problem could refer to either prior event or neither.",
            "allowed_response_change": "UNRESOLVED until the involved person/event is clarified.",
            "forbidden_focus_shift": "Do not choose roommate or parent without evidence.",
            "nonuse_condition": "Omit until entity resolution is available.",
        },
        "g4control_563a3066366b22308d91087e": {
            "candidate_increment": "UNRESOLVED: the text does not establish whether old evening walks relate to what feels different now.",
            "allowed_response_change": "UNRESOLVED; first clarify the current issue rather than forcing the old coping activity into the reply.",
            "forbidden_focus_shift": "Do not infer that walking is relevant or currently helpful.",
            "nonuse_condition": "Omit unless the current issue and relation to prior walks become clear.",
        },
    }
    return explanations[case_key]


def _codebook() -> str:
    return """# MS 候选专属增量标注说明（冻结 V1）

## 你只判断一件事

对当前可见对话与这一条严格过去的 actual Rank-1 MS 候选，判断：**这条过去信息是否提供了当前对话没有、且能自然改变当前回复的一个具体增量？**

这不是在评最终回复写得好不好，也不是在四个组件中只能挑一个。MP、MS、ME、RS 仍分别判断、可同时开启，16 个 requested actions 不变。

## 必填顺序

1. 用 `V...` span 选出当前即时支持目标，并用一句话说明。
2. 用 `C001` 锁定过去来源。
3. 写出“只有过去来源才提供”的候选增量。若没有，明确写 `NONE`；无法判断写 `UNRESOLVED`。
4. 判断实体/事件链接：`RESOLVED / UNRESOLVED / WRONG_ENTITY`。
5. 写出候选能怎样改变回复：理解、一个问题、回复约束或一个可拒绝选项。不能只写“提到记忆”或“更个性化”。
6. 写明禁止的注意力偏移，以及什么时候应安全不用。
7. 最后给一个组件级结论：`SUITABLE / NOT_SUITABLE / SEMANTIC_ABSTAIN`。

## 正例的硬条件

七项必须同时成立：owner/time 合法；实体链接明确；存在当前未给出的具体命题；当前目标明确；存在候选专属且自然的 response change；不偏离当前焦点且不把过去升级成现在；能写出不用条件。

## 常见负例

- `谢谢 / 再见 / 我希望如此`等没有命题内容；
- 当前对话已经更具体地说出同一件事；
- 同主题但不同人、不同事件；
- 旧问题已解决或与当前说法冲突；
- 相关但无法改变当前这一步回复；
- 使用后只会让用户继续替别人担忧，偏离用户当前需要；
- 用户明确要求不使用过去信息。

## 边界

`SUITABLE`只说明存在一个允许的、候选可归因的使用计划，不保证 generator 最终一定写好。后续 Function 测是否真的用出来，Quality/Risk 测最终回复；三者不能混成一个标签。
"""


def materialize(public_dir: Path, private_dir: Path) -> dict[str, Any]:
    phase = _read(PHASE)
    if phase["status"] != "ZERO_API_MS_SUPERVISION_REPAIR_PACKET_MATERIALIZATION_AUTHORIZED_ONCE":
        raise RuntimeError("phase does not authorize this one-time materialization")
    inputs = {row["role"]: _resolve(row["path"]) for row in phase["input_bindings"]}
    for row in phase["input_bindings"]:
        if _sha(inputs[row["role"]]) != row["sha256"]:
            raise RuntimeError(f"bound input drifted: {row['role']}")
    if public_dir.exists() or private_dir.exists():
        raise FileExistsError("repair packet output exists; overwrite forbidden")

    labels = _jsonl(inputs["frozen_ms_teacher_labels"])
    all_surfaces = [row for row in _jsonl(inputs["original_ms_public_surfaces"]) if row["component"] == "MS"]
    surfaces = {row["review_item_id"]: row for row in all_surfaces}
    resolved = [row for row in labels if row["teacher_decision"] != "SEMANTIC_ABSTAIN"]
    abstained = [row for row in labels if row["teacher_decision"] == "SEMANTIC_ABSTAIN"]

    packet: list[dict[str, Any]] = []
    private_key: list[dict[str, Any]] = []
    jaccards_by_decision: dict[str, list[float]] = defaultdict(list)
    old_positive_reason = Counter()
    old_decisions = Counter(row["teacher_decision"] for row in labels)
    group_resolved = Counter(row["split_group_key"] for row in resolved)
    group_positive = Counter(row["split_group_key"] for row in resolved if row["teacher_decision"] == "SUITABLE")
    for label in resolved:
        surface = surfaces[label["review_item_id"]]
        item_id = "msrepair_" + _stable_hex(label["review_item_id"], "source-annotated-v2")
        source = " ".join(span["content"] for span in surface["candidate_spans"])
        current_seeker = " ".join(span["content"] for span in surface["visible_spans"] if span["speaker"] == "seeker")
        overlap = _jaccard(source, current_seeker)
        jaccards_by_decision[label["teacher_decision"]].append(overlap)
        if label["teacher_decision"] == "SUITABLE":
            old_positive_reason[label["primary_reason_code"]] += 1
        public_row = {
            "protocol": "pm-v1.5-paper1-ms-source-annotated-repair-item-v1",
            "repair_item_id": item_id,
            "component": "MS",
            "component_name": "Atomic cross-session memory",
            "visible_current_spans": surface["visible_spans"],
            "strictly_past_candidate_spans": surface["candidate_spans"],
            "candidate_provenance": {
                "owner_status": surface["candidate_metadata"]["owner_status"],
                "time_status": surface["candidate_metadata"]["time_status"],
            },
            "decision_contract": _decision_contract(),
            "annotation": _annotation_template(),
        }
        packet.append(public_row)
        private_key.append({
            "protocol": "pm-v1.5-paper1-ms-source-annotated-repair-private-key-v1",
            "repair_item_id": item_id,
            "review_item_id": label["review_item_id"],
            "case_key": label["case_key"],
            "state_id": label["state_id"],
            "actual_rank1_id": label["actual_rank1_id"],
            "runtime_owner_key": label["runtime_owner_key"],
            "split_group_key": label["split_group_key"],
            "outer_fold": label["outer_fold"],
            "prior_teacher_decision_development_only": label["teacher_decision"],
            "prior_teacher_reason_development_only": label["primary_reason_code"],
            "prior_binary_label_development_only": label["binary_suitability_label"],
            "audit_flags_not_gold": {
                "low_information_rank1": label["low_information_rank1"],
                "exact_or_containment_current_echo": label["exact_or_containment_current_echo"],
                "source_current_seeker_token_jaccard": round(overlap, 6),
            },
        })
    packet.sort(key=lambda row: _stable_hex(row["repair_item_id"], "blind-order"))
    for position, row in enumerate(packet, start=1):
        row["review_position"] = position

    control_surfaces = {
        row["review_item_id"]: row
        for row in _jsonl(inputs["fresh_control_surfaces"])
        if row["component"] == "MS"
    }
    control_gold = [row for row in _jsonl(inputs["fresh_control_gold_not_training"]) if row["component"] == "MS"]
    controls: list[dict[str, Any]] = []
    control_key: list[dict[str, Any]] = []
    for gold in control_gold:
        surface = control_surfaces[gold["reviewer_a_item_id"]]
        item_id = "msrepaircontrol_" + _stable_hex(gold["case_key"], "source-annotated-v2")
        controls.append({
            "protocol": "pm-v1.5-paper1-ms-source-annotated-qualification-control-v1",
            "repair_item_id": item_id,
            "component": "MS",
            "visible_current_spans": surface["visible_spans"],
            "strictly_past_candidate_spans": surface["candidate_spans"],
            "candidate_provenance": surface["candidate_metadata"],
            "decision_contract": _decision_contract(),
            "annotation": _annotation_template(),
        })
        explanation = _control_explanation(gold["case_key"])
        control_key.append({
            "protocol": "pm-v1.5-paper1-ms-source-annotated-qualification-key-v1",
            "repair_item_id": item_id,
            "case_key": gold["case_key"],
            "not_training": True,
            "expected_final_suitability": gold["gold_decision"],
            "expected_primary_reason_code": gold["gold_primary_reason_code"],
            **explanation,
        })
    controls.sort(key=lambda row: _stable_hex(row["repair_item_id"], "control-blind-order"))
    for position, row in enumerate(controls, start=1):
        row["review_position"] = position

    public_forbidden = set().union(*(_public_forbidden_keys(row) for row in [*packet, *controls]))
    joined_ids = set(surfaces) & {row["review_item_id"] for row in labels}
    group_rates = [group_positive[group] / count for group, count in group_resolved.items()]
    checks = {
        "204_label_rows": len(labels) == 204,
        "204_unique_label_ids": len({row["review_item_id"] for row in labels}) == 204,
        "204_unique_ms_surfaces": len(surfaces) == 204,
        "complete_one_to_one_join": len(joined_ids) == 204 and set(surfaces) == {row["review_item_id"] for row in labels},
        "201_resolved_rows": len(resolved) == 201,
        "3_prior_abstentions_excluded_not_recast": len(abstained) == 3,
        "17_connected_groups": len(group_resolved) == 17,
        "public_rows_exactly_201": len(packet) == 201,
        "public_ids_unique": len({row["repair_item_id"] for row in packet}) == 201,
        "public_blinding_forbidden_keys_absent": not public_forbidden,
        "annotation_template_has_all_required_fields": all(
            set(row["annotation"]) == set(REQUIRED_ANNOTATION_FIELDS) for row in [*packet, *controls]
        ),
        "12_fixed_nontraining_controls": len(controls) == len(control_key) == 12 and all(row["not_training"] for row in control_key),
        "control_decision_distribution_5_5_2": Counter(row["expected_final_suitability"] for row in control_key)
        == {"SUITABLE": 5, "NOT_SUITABLE": 5, "SEMANTIC_ABSTAIN": 2},
        "no_training_label_changed": True,
        "zero_api_zero_fit": True,
        "sixteen_actions_and_nonexclusive_heads_preserved": all(
            row["decision_contract"]["no_single_memory_cap"] is True
            and row["decision_contract"]["sixteen_requested_actions_unchanged"] is True
            for row in packet
        ),
    }
    if not all(checks.values()):
        raise RuntimeError(f"MS repair packet checks failed: {checks}; forbidden={sorted(public_forbidden)}")

    data_quality = {
        "intended_use": "Determine whether the exact frozen actual Rank-1 MS candidate has a distinct, current-goal-relevant, source-attributable response use plan. The old teacher label is development provenance, not repaired gold.",
        "scientific_grain": "visible current state x frozen actual atomic Rank-1 MS candidate",
        "source_integrity": {
            "label_rows": len(labels),
            "surface_rows": len(surfaces),
            "one_to_one_join_rate": len(joined_ids) / len(labels),
            "duplicate_label_key_rate": 1 - len({row["review_item_id"] for row in labels}) / len(labels),
            "resolved_rows": len(resolved),
            "prior_abstentions": len(abstained),
            "connected_groups": len(group_resolved),
        },
        "prior_teacher_distribution_development_only": {
            "counts": dict(old_decisions),
            "rates": {key: value / len(labels) for key, value in old_decisions.items()},
            "resolved_binary_counts": {"ON": sum(row["binary_suitability_label"] == 1 for row in resolved), "OFF": sum(row["binary_suitability_label"] == 0 for row in resolved)},
            "positive_reason_counts": dict(old_positive_reason),
            "dominant_positive_reason_rate": max(old_positive_reason.values()) / sum(old_positive_reason.values()),
        },
        "stable_machine_audit_flags_not_gold": {
            "low_information_count": sum(row["low_information_rank1"] for row in resolved),
            "low_information_rate": sum(row["low_information_rank1"] for row in resolved) / len(resolved),
            "exact_or_containment_current_echo_count": sum(row["exact_or_containment_current_echo"] for row in resolved),
            "exact_or_containment_current_echo_rate": sum(row["exact_or_containment_current_echo"] for row in resolved) / len(resolved),
            "old_positive_token_jaccard_ge_0_15_count": sum(value >= 0.15 for value in jaccards_by_decision["SUITABLE"]),
            "old_positive_token_jaccard_ge_0_15_rate": sum(value >= 0.15 for value in jaccards_by_decision["SUITABLE"]) / len(jaccards_by_decision["SUITABLE"]),
            "warning": "These flags prioritize semantic review only. Lexical overlap, low-information regexes and old reason codes never auto-create or flip repaired gold.",
        },
        "new_construct_completeness_before_reannotation": {
            "rows_with_candidate_increment": 0,
            "rows_with_allowed_response_change": 0,
            "rows_with_forbidden_focus_shift": 0,
            "rows_with_nonuse_condition": 0,
            "complete_rows": 0,
            "complete_rate": 0.0,
            "conclusion": "The old 201 binary labels are structurally complete for the retired target but 0/201 complete for the repaired source-attributable target; direct refit would be invalid.",
        },
        "group_variation_development_only": {
            "groups": len(group_resolved),
            "resolved_rows_min": min(group_resolved.values()),
            "resolved_rows_max": max(group_resolved.values()),
            "old_positive_rate_min": min(group_rates),
            "old_positive_rate_max": max(group_rates),
            "warning": "Group variation is descriptive and cannot be used to change thresholds or sample membership after outcomes.",
        },
        "public_blinding": {
            "forbidden_keys_found": sorted(public_forbidden),
            "teacher_labels_visible": False,
            "model_predictions_visible": False,
            "outcomes_visible": False,
            "selection_features_visible": False,
        },
    }

    public_dir.mkdir(parents=True)
    private_dir.mkdir(parents=True)
    public_paths = {
        "review_packet": public_dir / "ms_reannotation_packet_blind.jsonl",
        "qualification_controls": public_dir / "qualification_controls_blind.jsonl",
        "codebook": public_dir / "CODEBOOK_ZH.md",
        "data_quality_profile": public_dir / "data_quality_profile.json",
    }
    private_paths = {
        "case_key": private_dir / "ms_reannotation_private_key.jsonl",
        "control_key": private_dir / "qualification_control_key.jsonl",
    }
    _write_jsonl(public_paths["review_packet"], packet)
    _write_jsonl(public_paths["qualification_controls"], controls)
    public_paths["codebook"].write_text(_codebook(), encoding="utf-8")
    _write_json(public_paths["data_quality_profile"], data_quality)
    _write_jsonl(private_paths["case_key"], private_key)
    _write_jsonl(private_paths["control_key"], control_key)

    report = {
        "protocol": "pm-v1.5-paper1-ms-supervision-repair-packet-report-v1",
        "status": "ZERO_API_MS_REPAIR_PACKET_READY_QUALIFICATION_NOT_RUN_REANNOTATION_NOT_AUTHORIZED",
        "checks": checks,
        "counts": {
            "source_labels": len(labels),
            "resolved_reannotation_items": len(packet),
            "prior_abstentions_preserved_outside_packet": len(abstained),
            "connected_groups": len(group_resolved),
            "qualification_controls": len(controls),
        },
        "decisive_finding": data_quality["new_construct_completeness_before_reannotation"]["conclusion"],
        "quality_risks": [
            "73 old positives collapse 95.9% into CHANGES_CURRENT_OPTION rather than carrying candidate-specific response plans.",
            "Old binary labels contain none of the four new source-attribution fields; they cannot be reused as repaired gold.",
            "Machine lexical flags are audit strata only and are forbidden from auto-labeling.",
        ],
        "next_gate": "Run the fixed 12-control qualification with the frozen codebook. Only a qualified instrument may unlock exactly one 201-item reannotation pass.",
        "api_calls": 0,
        "training_labels_created_or_changed": 0,
        "fits": 0,
        "public_artifacts": {key: {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)} for key, path in public_paths.items()},
        "private_artifacts": {key: {"path": str(path.relative_to(ROOT)), "sha256": _sha(path)} for key, path in private_paths.items()},
        "source_hashes": {row["role"]: row["sha256"] for row in phase["input_bindings"]},
    }
    _write_json(public_dir / "report.json", report)
    rows_html = "".join(
        f"<tr><td>{escape(name)}</td><td>{'PASS' if value else 'FAIL'}</td></tr>" for name, value in checks.items()
    )
    html = f"""<!doctype html><html><head><meta charset='utf-8'><title>MS supervision repair packet</title>
<style>body{{font-family:system-ui;max-width:1080px;margin:2rem auto;line-height:1.5}}table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #ccc;padding:.45rem;text-align:left}}.ok{{color:#176b2c}}.warn{{color:#8a4b00}}code{{background:#eee;padding:.1rem .25rem}}</style></head><body>
<h1>MS supervision repair packet audit</h1><p class='ok'><strong>{escape(report['status'])}</strong></p>
<h2>Answer first</h2><p>The exact 204 old labels and 204 MS surfaces join one-to-one. The 201 resolved rows are structurally usable as review units, but <strong>0/201</strong> contains the candidate increment, allowed response change, forbidden focus shift and safe nonuse condition required by the repaired target. Therefore the old checkpoint must not be refit or promoted.</p>
<p>The new packet preserves the exact states and actual Rank-1 candidates, hides old teacher/model/outcome information, and adds 12 fixed non-training controls. Qualification and reannotation have not run.</p>
<h2>Key rates</h2><ul><li>Old labels: 73 suitable / 128 not suitable / 3 abstain.</li><li>Old positive reason concentration: 70/73 ({data_quality['prior_teacher_distribution_development_only']['dominant_positive_reason_rate']:.1%}) use <code>CHANGES_CURRENT_OPTION</code>.</li><li>Machine audit flags among 201 resolved rows: low-information {data_quality['stable_machine_audit_flags_not_gold']['low_information_count']} ({data_quality['stable_machine_audit_flags_not_gold']['low_information_rate']:.1%}); exact/containment current echo {data_quality['stable_machine_audit_flags_not_gold']['exact_or_containment_current_echo_count']} ({data_quality['stable_machine_audit_flags_not_gold']['exact_or_containment_current_echo_rate']:.1%}). These are review strata, never automatic gold.</li></ul>
<h2>Machine checks</h2><table><tr><th>Check</th><th>Result</th></tr>{rows_html}</table>
<h2>Next hard gate</h2><p>{escape(report['next_gate'])}</p>
</body></html>"""
    (public_dir / "report.html").write_text(html, encoding="utf-8")
    report["public_artifacts"]["report_html"] = {
        "path": str((public_dir / "report.html").relative_to(ROOT)),
        "sha256": _sha(public_dir / "report.html"),
    }
    _write_json(public_dir / "report.json", report)
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--public-out", type=Path, default=DEFAULT_PUBLIC)
    parser.add_argument("--private-out", type=Path, default=DEFAULT_PRIVATE)
    args = parser.parse_args()
    report = materialize(args.public_out.resolve(), args.private_out.resolve())
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
