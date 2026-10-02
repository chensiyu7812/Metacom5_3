#!/usr/bin/env python3
"""Read-only evaluation inventory, preliminary pilot roster and unscored examples.

No model loading, requests, new replies, labels, training, or dataset freeze.
Old reference sheets remain immutable. Example blind keys stay coordinator-only.
"""
from collections import Counter, defaultdict
from hashlib import sha256
from html import escape
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.io import read_json, sha256_file, iter_jsonl
from metacom_pm.paper1.data.memory_source import load_sanitized_runtime_users
from metacom_pm.rl1.schema import digest, PrefixSpec, PublicTurn

AUTH = PROJECT / "data/paper1_authority"
ENGINEERING = PROJECT / "outputs/pm_rl1/engineering_20260928_v1"
OUT = PROJECT / "outputs/pm_rl1/evaluation_preparation_20260928_v1"


def write(name, value):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def main():
    files_checked = {}
    esc_ref = read_json(AUTH / "paper1_esc_evaluator_dual_human_reference_20260823_v1.json")
    for rater, item in esc_ref["source_submissions"].items():
        path = PROJECT / item["path"]
        assert sha256_file(path) == item["stored_sha256"]
        raw = read_json(path)
        assert len(raw["submission"]) == item["complete_items"] == 24
        files_checked[str(path)] = sha256_file(path)
    esc_result = read_json(AUTH / "paper1_official_esc_rank_qualification_closeout_20260902_v1.json")
    closeout = read_json(AUTH / "paper1_human_review_closeout_20260917_v1.json")
    intake = read_json(PROJECT / "outputs/paper1_pairwise_teacher/review_closeout_20260917_v1/intake_result.json")
    for name, item in intake["sources"].items():
        path = Path(item["path"])
        assert sha256_file(path) == item["sha256"] == closeout["source_sha256"][name]
        files_checked[str(path)] = sha256_file(path)
    trace = read_json(PROJECT / "outputs/paper1_pairwise_teacher/review_closeout_20260917_v1/reference_trace.json")
    assert len(trace) == 96
    bases = [r for r in trace if not r["reverse_duplicate"]]
    assert len(bases) == 80
    sheet_manifest = read_json(AUTH / "paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json")
    for row in sheet_manifest["sheets"].values():
        path = PROJECT / row["path"]
        assert sha256_file(path) == row["sha256"]
        files_checked[str(path)] = sha256_file(path)
    gemini = read_json(AUTH / "paper1_gemini_qualification_closeout_20260917_v1.json")
    local = read_json(AUTH / "paper1_local_teacher_development_closeout_20260917_v1.json")
    for relative, expected in local["aggregate_artifacts"].items():
        path = PROJECT.parent / relative
        assert sha256_file(path) == expected
        files_checked[str(path)] = expected
    old_pairs = list(iter_jsonl(AUTH / "paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"))
    old_owners = Counter(r["owner_or_dialogue_group"] for r in old_pairs if r["task"] != "ESC")
    history_owners = sorted({r["owner_id"] for r in sheet_manifest["DG_reference_lineage"]})
    census = read_json(ENGINEERING / "census.json")
    test_owners = sorted(o for o, split in census["owner_split"].items() if split == "test")
    audit = dict(status="ASSET_AUDIT_NOT_NEW_JUDGE_QUALIFICATION", checked_file_sha256=files_checked,
        esc_24=dict(actual_reference="two independent human sheets", items=24, dimensions=7,
            original_human_dimension_ratings=336,
            source=esc_ref["source_submissions"], official_result=esc_result["blind_human_qualification"],
            status=esc_result["status"], usable_scope="official old ESC-Eval protocol, not automatically current-turn reward"),
        pairwise_96=dict(actual_reference=closeout["provenance"], base_pairs=80, reversed_presentations=16,
            task_counts=dict(Counter(r["task"] for r in bases)),
            joint_A_counts=dict(Counter(r["reference_verdict"] for r in bases)),
            A_vs_exploratory_B_base_matches=sum(r["reference_verdict"] == r["candidate_verdict"] for r in bases),
            gemini_status=gemini["status"], valid_presentations=gemini["operational"]["status_counts"],
            actual_goal="old task-defined material pairwise effect, not q/m absolute current-turn scoring"),
        local_teacher_disposition=local["disposition"], local_teacher_calls=local["judge_presentations"],
        existing_natural_turn_rubric=str(AUTH / "paper1_natural_turn_appropriateness_rubric_v1.json"),
        new_rl1=read_json(ENGINEERING / "validation.json"),
        exposure=dict(proposed_test_owners=test_owners,
            old_memory_pair_counts={o: old_owners[o] for o in test_owners},
            old_DG_complete_history_test_owners=sorted(set(test_owners) & set(history_owners)),
            interpretation="owner overlap is an exposure warning, not proof of training contamination; audit exact source/fact/suffix use before a clean-test claim",
            automatically_reassigned_or_deleted_owners=False),
        new_model_calls=0, new_human_ratings=0, paid_api_usd=0)
    write("asset_audit.json", audit)

    prefixes = read_json(ENGINEERING / "prefixes_private.json")
    by_owner = defaultdict(list)
    for raw in prefixes:
        if raw["split"] == "train":
            # Development roster only. Keep the known shared-session family
            # and its descendants out of this small pilot until adjudicated.
            if raw["owner_id"] == "p13" and raw["cutoff_rank"] >= 14:
                continue
            by_owner[raw["owner_id"]].append(raw)
    assert len(by_owner) == 12
    roster = []
    owners = sorted(by_owner, key=lambda o: digest(["rl1-measurement-owner-v1", o]))
    for i, owner in enumerate(owners):
        raw = min(by_owner[owner], key=lambda p: digest(["rl1-measurement-prefix-v1", p]))
        prefix = PrefixSpec(**{**raw, "turns": tuple(PublicTurn(**t) for t in raw["turns"])})
        roster.append(dict(pilot_index=i + 1, prefix_identity=prefix.identity, prefix=raw,
            four_planned_conditions=["actual_OFF", "actual_fixed_legal_ON", "single_damage_control", "meaning_preserving_style_control"],
            repeat_condition_index=i % 4,
            independent_pair_type="OFF_ON" if i < 6 else "original_damage" if i < 9 else "original_style",
            generation_status="NOT_MATERIALIZED", on_plan_status="NEEDS_SOURCE_AND_CAPACITY_CHECK"))
    write("pilot_roster_private_DRAFT.json", dict(status="DRAFT_12_TRAIN_OWNERS_NOT_FROZEN_EXAM",
        selection="one per train owner, fixed hash within existing preliminary train prefixes; known p13 shared-session descendants excluded",
        limitations=["historical exposure/fact-family audit incomplete", "ON treatment not materialized or frozen",
                     "no guarantee that a valid single-damage/style control exists for every selected prefix",
                     "do not replace an uninformative natural pair merely to obtain positive benefit"], rows=roster))

    users = {u.owner_id: u for u in load_sanitized_runtime_users(PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json")}
    pointer = read_json(ENGINEERING / "generation_smoke_pointer.json")
    run = Path(pointer["run_dir"])
    assert sha256_file(run / "summary.json") == pointer["summary_sha256"]
    result_rows = read_json(run / "summary.json")["rows"]
    specs = read_json(ENGINEERING / "episode_specs_private.json")
    examples, keys = [], []
    for spec in specs:
        p = spec["prefix"]
        prefix = PrefixSpec(**{**p, "turns": tuple(PublicTurn(**t) for t in p["turns"])})
        rows = [r for r in result_rows if r["prefix"] == prefix.identity]
        assert len(rows) == 2
        ordered = sorted(rows, key=lambda r: digest(["rl1-example-blind-order-v1", r["request_id"]]))
        evidence = []
        source_map = []
        for ordinal, session in enumerate(s for s in users[p["owner_id"]].sessions if s.chronological_rank < p["cutoff_rank"]):
            sid = f"H{ordinal+1:03d}"
            evidence.append(dict(id=sid, date=session.timestamp,
                turns=[dict(id=f"{sid}:T{i:03d}", role=t.role, text=t.content) for i,t in enumerate(session.turns)]))
            source_map.append(dict(blind_session=sid, actual_session=session.session_id, rank=session.chronological_rank))
        responses, mapping = {}, {}
        for label, row in zip(("A", "B"), ordered):
            response = read_json(run / (row["request_id"] + ".response.json"))
            assert response["finish_reason"] == "natural_stop"
            responses[label] = response["text"]
            mapping[label] = dict(arm=row["arm"], request_id=row["request_id"],
                                  response_sha256=sha256_file(run / (row["request_id"] + ".response.json")))
        item_id = "example_" + digest(["rl1-example-v1", prefix.identity])[:16]
        examples.append(dict(item_id=item_id, status="UNSCORED_DEVELOPMENT_EXAMPLE_NOT_PILOT_OR_TEST",
            task="Evaluate only the new reply to the current final seeker turn. Both replies have the same legal evidence.",
            current_prefix=[dict(id=f"C:T{i:03d}", **t) for i,t in enumerate(p["turns"])],
            legal_past_sessions=evidence, replies=responses,
            review=dict(q_A=None, m_A=None, q_B=None, m_B=None, pairwise=None,
                        response_and_source_spans=[], uncertainty=None, reviewer_identity=None)))
        keys.append(dict(item_id=item_id, prefix_identity=prefix.identity, owner=p["owner_id"],
                         source_map=source_map, response_mapping=mapping))
    write("reviewer_examples_UNSCORED.json", dict(status="THREE_EXISTING_TRAIN_PAIRS_FOR_SCHEMA_DISCUSSION",
        warning="Not the 12-prefix measurement exam, not final evaluation, no expected numerical answers are supplied.",
        reviewer_must_not_receive="coordinator_only directory or resource/arm identities", items=examples))
    write("coordinator_only/example_blind_key.json", keys)
    sections = []
    for i, item in enumerate(examples, 1):
        current = "".join(f'<p><b>{escape(t["id"])} · {escape(t["role"])}</b><br>{escape(t["content"])}</p>'
                          for t in item["current_prefix"])
        history = "".join('<details><summary>' + escape(s["id"] + " · " + s["date"]) + '</summary>' +
            "".join(f'<p><b>{escape(t["id"])} · {escape(t["role"])}</b><br>{escape(t["text"])}</p>'
                    for t in s["turns"]) + '</details>' for s in item["legal_past_sessions"])
        answers = "".join(f'<article><h3>匿名回复 {label}</h3><p class="reply">{escape(answer)}</p></article>'
                           for label, answer in item["replies"].items())
        sections.append(f'<section><h2>示例 {i}</h2><p class="muted">{escape(item["item_id"])}</p>' +
            '<h3>当前公开前缀</h3>' + current + '<div class="answers">' + answers + '</div>' +
            '<p>待记录：每条回复的 q / m、关键回复片段、对应来源片段、总体比较、无法判断的原因。</p>' +
            '<details><summary>展开完整合法过去历史（按日期与会话索引）</summary>' + history + '</details></section>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PM-RL1 · 未评分评审材料样例</title><style>
body{font:16px/1.7 system-ui,sans-serif;color:#1d2a35;background:#f5f7fa;max-width:1100px;margin:auto;padding:24px}
section,header{background:white;padding:24px;margin:20px 0;border:1px solid #dfe5eb;border-radius:8px}
.answers{display:grid;grid-template-columns:1fr 1fr;gap:20px}article{background:#f2f6fa;padding:18px;border-radius:6px}
p{overflow-wrap:anywhere}.reply{white-space:pre-wrap}.muted{color:#687580}summary{cursor:pointer;font-weight:600;padding:10px 0}
details details{margin:8px 16px;border-top:1px solid #e0e6ed}h1{font-size:25px}h2{font-size:22px}h3{font-size:18px}
@media(max-width:700px){body{padding:8px}.answers{grid-template-columns:1fr}section,header{padding:16px}}
</style><header><h1>PM-RL1 · 未评分评审材料样例</h1>
<p>三对既有 train 开发回复，用于检查新的评审材料格式。只读，尚未开始评分；它们不是 12 前缀测量卷或正式 test。</p>
<p>只评价最后用户发言之后的新回复。两条匿名回复共享完整合法证据；过去的好回答不计入新回复质量。当前公开更正优先；supporter 的猜测和建议不自动成为用户事实。</p>
<p>质量 q：0 严重失配，1 明显问题，2 基本回应但有重要不足，3 贴合适当，4 充分满足当前需要。误用 m：0 未发现，0.25 局部失准，1 实质误用。证据不足保留无法判断。多引用历史、更多建议或更长回复不自动加分。</p>
<p>原始英文是证据文本；中文只作操作说明。引用来源时记录 H…:T… 或 C:T… 编号及原文。评审前不提供方法、取用量、训练分数或期望答案。</p></header>'''
    (OUT / "reviewer_examples_UNSCORED.html").write_text(page + "".join(sections) + "</html>")
    assert all(sha256_file(Path(p)) == h for p, h in files_checked.items())
    write("manifest.json", dict(script_sha256=sha256_file(Path(__file__)),
        artifacts={str(p.relative_to(OUT)): sha256_file(p) for p in sorted(OUT.rglob("*"))
                   if p.is_file() and p.name != "manifest.json"},
        checked_original_sources_unchanged=True, api_calls=0, generation_calls=0, judgement_calls=0))
    print(json.dumps(dict(verified_old_files=len(files_checked), independent_ESC_sheets=2,
        pairwise_base_pairs=len(bases), pilot_draft_prefixes=len(roster), unscored_example_pairs=len(examples),
        test_exposure=audit["exposure"], calls=0), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
