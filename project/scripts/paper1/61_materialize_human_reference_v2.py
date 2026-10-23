#!/usr/bin/env python3
"""Build the authorized V2 human forms and exact teacher requests, offline.

All response text stays under ignored outputs/. Original V1 files are immutable.
--check reconstructs and compares the package without writing anything.
"""
from __future__ import annotations

import argparse
import copy
from collections import Counter
from decimal import Decimal
import io
import json
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.io import canonical_json, iter_jsonl, read_json, sha256_bytes, sha256_file, sha256_text
from metacom_pm.paper1.data.memory_source import enumerate_targets, load_sanitized_runtime_users
from metacom_pm.paper1.evaluation.human_reference import (
    REFERENCE_PROTOCOL, build_dg_reference, reference_from_view, render_rating_html,
    upgrade_human_sheet, validate_rated_sheet,
)
from metacom_pm.paper1.evaluation.pairwise_teacher import (
    DG_REFERENCE_INSTRUCTION, build_pairwise_teacher_prompt, pairwise_teacher_identity_payload,
)
from metacom_pm.paper1.outcome_lock import assert_pre_outcome_locked, load_public_only_config

AUTH = PROJECT / "data/paper1_authority"
OUTPUT = PROJECT / "outputs/paper1_pairwise_teacher/human_sheets_v2"
DATE = "2026-09-08"
NAMES = {
    "amendment": "paper1_pairwise_teacher_reference_amendment_20260908_v2.json",
    "instrument": "paper1_pairwise_teacher_human_instrument_20260908_v2.json",
    "design": "paper1_pairwise_teacher_human_reference_design_20260908_v2.json",
    "identity": "paper1_gemini_pairwise_teacher_identity_20260908_v2.json",
    "manifest": "paper1_pairwise_teacher_human_sheet_manifest_20260908_v2.json",
    "plan": "paper1_pairwise_teacher_qualification_plan_v3.json",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--rebuild-unrated", action="store_true", help="replace only this not-yet-rated V2 package during preparation")
    args = parser.parse_args()
    if args.check and args.rebuild_unrated:
        parser.error("--check and --rebuild-unrated are mutually exclusive")
    config = load_public_only_config(PROJECT / "configs/paper1_public_only.yaml")
    assert_pre_outcome_locked(config)
    pending: dict[Path, bytes] = {}

    def put(path: Path, obj) -> str:
        if isinstance(obj, bytes):
            data = obj
        elif isinstance(obj, str):
            data = obj.encode("utf-8")
        else:
            data = (json.dumps(obj, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
        pending[path] = data
        return sha256_bytes(data)

    def rel(path: Path) -> str:
        return str(path.relative_to(PROJECT))

    old_manifest_path = AUTH / "paper1_pairwise_teacher_human_sheet_manifest_20260904_v1.json"
    old_manifest = read_json(old_manifest_path)
    old_instrument_path = AUTH / "paper1_pairwise_teacher_human_instrument_20260904_v1.json"
    base_path = AUTH / "paper1_pairwise_teacher_base_pair_preflight_20260904_v1.jsonl"
    blind_path = AUTH / "paper1_pairwise_teacher_blind_key_20260904_v1.jsonl"
    presentations_path = AUTH / "paper1_pairwise_teacher_presentation_plan_20260904_v1.jsonl"
    generation_path = AUTH / "paper1_pairwise_teacher_local_generation_result_20260904_v1.json"
    binding_path = AUTH / "paper1_pairwise_teacher_generator_request_binding_20260904_v1.json"
    source_paths = {
        "base_pairs": base_path, "presentations": presentations_path, "blind_key": blind_path,
        "instrument": old_instrument_path, "local_generation_result": generation_path,
    }
    for name, path in source_paths.items():
        if sha256_file(path) != old_manifest["source_sha256"][name]:
            raise RuntimeError(f"frozen V1 source hash mismatch: {name}")
    generation, binding = read_json(generation_path), read_json(binding_path)
    if generation["request_binding_sha256"] != sha256_file(binding_path):
        raise RuntimeError("original request binding hash mismatch")
    base = {r["base_pair_id"]: r for r in iter_jsonl(base_path)}
    blind = {r["presentation_id"]: r for r in iter_jsonl(blind_path)}
    presentations = list(iter_jsonl(presentations_path))
    pair_map = {r["base_pair_id"]: r for r in generation["base_pair_response_map"]}
    if len(base) != 80 or len(blind) != 96 or len(presentations) != 96 or len(pair_map) != 80:
        raise RuntimeError("frozen presentation denominator changed")
    originals = {}
    for rater, metadata in old_manifest["sheets"].items():
        path = PROJECT / metadata["path"]
        if sha256_file(path) != metadata["sha256"]:
            raise RuntimeError(f"V1 original has changed: {rater}")
        originals[rater] = read_json(path)
        for item in originals[rater]["items"]:
            key = blind[item["presentation_id"]]
            for side in ("A", "B"):
                arm_record = pair_map[key["base_pair_id"]][key[side + "_arm"]]
                if sha256_text(item["response_" + side]) != arm_record["response_sha256"]:
                    raise RuntimeError("original response differs from frozen generation")
    runtime_path = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
    raw_path = PROJECT / "data/external/evo_emo.json"
    units_path = PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl"
    for name, path in (("memory_source_sha256", runtime_path), ("raw_data_sha256", raw_path), ("multi_view_session_results_sha256", units_path)):
        if sha256_file(path) != binding["source"][name]:
            raise RuntimeError(f"public source identity changed: {name}")
    users = load_sanitized_runtime_users(runtime_path)
    by_owner = {u.owner_id: u for u in users}
    targets = {t.target_id: t for t in enumerate_targets(users)}
    raw_users = {u["id"]: u for u in read_json(raw_path)}
    dg_views, dg_audits = {}, {}
    for row in base.values():
        if row["task"] != "DG" or row["target_id"] in dg_views:
            continue
        target = targets[row["target_id"]]
        view, audit = build_dg_reference(user=by_owner[target.owner_id], target=target, excerpt=row["reference_material"])
        # Verify every displayed role/content against the original public transcript.
        raw_sessions = {s["id"]: s for s in raw_users[target.owner_id]["dialog_history"]}
        for sid, shown in zip(audit["source_session_ids"], view["sessions"], strict=True):
            raw = raw_sessions[sid]
            if shown != {"timestamp": raw["timestamp"], "turns": [{"role": t["role"], "content": t["content"]} for t in raw["dialogue"]]}:
                raise RuntimeError("displayed history differs from raw public source")
        dg_views[target.target_id], dg_audits[target.target_id] = view, audit
    units = {u["memory_id"]: u for r in iter_jsonl(units_path) for u in r["accepted_units"]}
    checked_candidates = 0
    for row in binding["dg_dynamic_retrieval"]:
        audit = dg_audits[row["target_id"]]
        for cid in row["candidate_ids"]:
            if cid.startswith("ms::"):
                _, owner, sid = cid.split("::")
            else:
                unit = units[cid.split("::", 1)[1]]
                owner, sid = unit["owner_id"], unit["source_session_id"]
            if owner != audit["owner_id"] or sid not in audit["source_session_ids"]:
                raise RuntimeError("DG candidate source is outside the displayed strict-past history")
            checked_candidates += 1

    amendment = {
        "protocol": REFERENCE_PROTOCOL, "date": DATE,
        "status": "ACTIVE_RESEARCHER_AUTHORIZED_REFERENCE_CORRECTION",
        "human_authority": "project/docs/PM_PAPER1_HUMAN_REFERENCE_V2_AMENDMENT_20260908_ZH.md",
        "researcher_authorization": {
            "authorized": True,
            "instruction": "行吧，那做吧，应该怎样做，最能支持主张的，怎样最能校准的，就怎么来。生成新的人评卷子吧。",
            "scope": "correct DG reference evidence and deliver new independent human sheets; retain 80/16/96 design",
            "paid_calls_authorized": False,
        },
        "audit_timing": "response text inspected for instrument adequacy before human or Gemini verdict collection",
        "reference_rule": "same-owner raw history with chronological_rank < target.cutoff_rank, plus unchanged topic-related historical excerpt",
        "selection_reads_response_content": False,
        "reference_supplement_selection_reads_response_content": False,
        "human_and_teacher_reference_identical": True,
        "hidden_new_scenario_narrative_included": False,
        "changed": ["DG evidence scope", "DG evidence interpretation clarification", "offline human form and strict ingest", "duplicate JSON parser enforcement"],
        "preserved": ["80 base pairs", "16 reversal presentations", "96 presentations per each of 2 raters", "142 generated responses", "questions and rater order", "A/B mapping", "task allocation", "four verdict meanings", "PM estimand and learner", "official benchmark metrics", "API caps", "all outcome locks"],
        "superseded_for_new_ratings": [old_manifest_path.name, old_instrument_path.name],
        "old_generations_remain_valid": True,
        "regeneration_required": False,
        "prior_ratings_may_be_silently_pooled": False,
        "adjudication": "predeclared_consensus_after_both_primary_files_sealed_and_before_Gemini_verdicts_seen",
        "no_consensus": "uncertain",
        "new_empirical_pass_gate": False,
        "teacher_target_isolation": "still required in subsequent formal calibration/effect manifests; no fold change by this amendment",
        "paid_api_calls": 0, "formal_outcome_calls": 0, "pm_training_runs": 0,
        "locks": generation["locks"],
    }
    put(AUTH / NAMES["amendment"], amendment)
    instrument = read_json(old_instrument_path)
    instrument.update({"protocol": "paper1-pairwise-teacher-human-instrument-v2", "date": DATE,
                       "status": "ACTIVE_REFERENCE_V2_FROZEN_HUMAN_RATINGS_PENDING"})
    instrument["task_rubrics"]["DG"]["shown"][0] = "task-related historical excerpt and complete strict-past raw history"
    instrument["task_rubrics"]["DG"]["evidence_instruction"] = DG_REFERENCE_INSTRUCTION
    instrument["reference_protocol"] = REFERENCE_PROTOCOL
    instrument["submission"] = {"editable_fields_only": ["verdict", "rationale"], "rationale_language": "Chinese or English", "partial_save_allowed": True, "adjudication": "separate_after_primary_ratings_sealed"}
    instrument_hash = put(AUTH / NAMES["instrument"], instrument)

    presentation_targets = {pid: base[key["base_pair_id"]]["target_id"] for pid, key in blind.items()}
    sheets, metadata = {}, {}
    for rater, original in originals.items():
        sheet = upgrade_human_sheet(original, instrument=instrument, presentation_targets=presentation_targets, dg_views=dg_views)
        validate_rated_sheet(sheet, sheet, require_complete=False)
        folder = OUTPUT / rater
        stem = f"paper1_pairwise_teacher_{rater.lower()}_sheet_v2"
        json_path, html_path = folder / (stem + ".json"), folder / (stem + ".html")
        json_hash = put(json_path, sheet)
        html_hash = put(html_path, render_rating_html(sheet, sheet_sha256=json_hash, filename_stem=stem))
        guide = (
            f"{rater} 专用 · 独立回复质量评审 V2\n\n"
            f"1. 用电脑浏览器打开 {html_path.name}。网页自带全部材料，不需要登录或联网。\n"
            "2. 先读页面说明，然后按本人卷的顺序独立评完 96 题。每题选一个判定并写简短理由，中文或英文均可。\n"
            "3. DG 的相关摘录不是完整历史。需核验时展开完整历史，用英文关键词或日期查找原文。不要把支持者猜测当成用户确认的事实。\n"
            "4. 可分次完成。每次休息前点击“导出进度”；下次打开同一份网页，或点击“恢复进度”导入本人备份。更换浏览器/电脑需导入备份。\n"
            "5. 全部完成后点击“导出完整答卷”，确认已下载 _rated.json，再把该文件交回研究负责人。网页不会自动上传。\n"
            "6. 若网页不能使用，可复制配套 JSON 为 _rated.json，只改各题 verdict、rationale。不要改变其他字段、题序或原文。\n\n"
            "仅看自己的卷，不交流答案、不由模型代评、不寻找重复题或为一致性回改。equivalent 与 uncertain 都是允许的判断，不要求分胜负。\n"
        )
        guide_path = folder / "开始评审.txt"
        put(guide_path, guide)
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in (html_path, json_path, guide_path):
                info = zipfile.ZipInfo(path.name, (2026, 9, 8, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, pending[path])
        zip_path = OUTPUT / f"paper1_{rater.lower()}_v2.zip"
        zip_hash = put(zip_path, buf.getvalue())
        metadata[rater] = {"path": rel(json_path), "sha256": json_hash, "presentations": 96,
                           "html_path": rel(html_path), "html_sha256": html_hash,
                           "zip_path": rel(zip_path), "zip_sha256": zip_hash,
                           "guide_path": rel(guide_path), "guide_sha256": sha256_bytes(pending[guide_path])}
        sheets[rater] = sheet
    a = {i["presentation_id"]: i for i in sheets["RATER_A"]["items"]}
    b = {i["presentation_id"]: i for i in sheets["RATER_B"]["items"]}
    if {pid: {k: v for k, v in i.items() if k != "item_number"} for pid, i in a.items()} != {pid: {k: v for k, v in i.items() if k != "item_number"} for pid, i in b.items()}:
        raise RuntimeError("two raters do not see identical presentations")

    identity = read_json(AUTH / "paper1_gemini_pairwise_teacher_identity_20260904_v1.json")
    identity.update({"protocol": "paper1-gemini-pairwise-teacher-identity-v2", "date": DATE,
                     "status": "ACTIVE_REFERENCE_V2_IDENTITY_FROZEN_CALLS_NOT_AUTHORIZED",
                     "supersedes": "paper1_gemini_pairwise_teacher_identity_20260904_v1.json",
                     "reference_policy_authority": NAMES["amendment"]})
    identity["prompt_identity"] = {**pairwise_teacher_identity_payload(), "implementation": "project/src/metacom_pm/paper1/evaluation/pairwise_teacher.py"}
    identity["parser"]["duplicate_keys"] = "fail_closed_even_if_duplicate_values_match"
    identity["parser"]["source_sha256"] = sha256_file(PROJECT / "src/metacom_pm/paper1/evaluation/pairwise_teacher.py")
    g = identity["generation"]
    generation_config = {k: copy.deepcopy(g[k]) for k in ("temperature", "maxOutputTokens", "responseMimeType", "responseJsonSchema", "seed")}
    generation_config["thinkingConfig"] = copy.deepcopy(g["thinking_config"])
    private_requests, tracked_requests = [], []
    import tiktoken
    encoding = tiktoken.get_encoding("o200k_base")
    for presentation in presentations:
        pid = presentation["presentation_id"]
        item = a[pid]
        prompt = build_pairwise_teacher_prompt(task=item["task"], task_input=item["task_input"], response_a=item["response_A"], response_b=item["response_B"], reference_material=item["reference_material"])
        body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}], "generationConfig": copy.deepcopy(generation_config)}
        row = {"presentation_id": pid, "task": item["task"], "request_model": identity["model"]["request_model"],
               "prompt_sha256": sha256_text(prompt), "body_sha256": sha256_text(canonical_json(body)),
               "reference_sha256": sha256_text(item["reference_material"]) if item["reference_material"] is not None else None,
               "offline_input_tokens_o200k_base": len(encoding.encode(prompt)),
               "maximum_output_tokens": g["maxOutputTokens"]}
        tracked_requests.append(row)
        private_requests.append({**row, "body": body})
    private_path = OUTPUT / "coordinator_only" / "gemini_requests_v2.jsonl"
    private_hash = put(private_path, "".join(canonical_json(r) + "\n" for r in private_requests))
    identity["exact_request_manifest"] = {"path": rel(private_path), "sha256": private_hash, "presentations": 96, "git_tracking_forbidden": True, "human_and_teacher_reference_identical": True}
    total_tokens = sum(r["offline_input_tokens_o200k_base"] for r in tracked_requests)
    price = identity["pricing_snapshot"]
    estimate = (Decimal(total_tokens) * Decimal(str(price["standard_input_usd_per_million_tokens"])) + Decimal(96 * g["maxOutputTokens"]) * Decimal(str(price["standard_output_usd_per_million_tokens"]))) / Decimal(1000000)
    budget = {"status": "OFFLINE_ESTIMATE_ONLY_PROVIDER_TOKEN_COUNT_AND_RESERVATION_REQUIRED_BEFORE_PAID_EXECUTION",
              "pricing_snapshot_date": price["accessed_date"], "tokenizer": "o200k_base_not_Gemini_tokenizer",
              "offline_input_tokens": total_tokens, "maximum_output_tokens_one_attempt_each": 96 * g["maxOutputTokens"],
              "estimated_one_attempt_each_usd": str(estimate), "qualification_hard_cap_usd": "0.10",
              "guaranteed_worst_case_cost": False, "retries_in_estimate": False, "provider_token_count_calls": 0,
              "paid_execution_authorized": False}
    identity["offline_reference_v2_budget_preflight"] = budget
    identity_hash = put(AUTH / NAMES["identity"], identity)
    changed = Counter()
    for rater, sheet in sheets.items():
        for old, new in zip(originals[rater]["items"], sheet["items"], strict=True):
            if {k: v for k, v in old.items() if k != "reference_material"} != {k: v for k, v in new.items() if k not in {"reference_material", "reference_id"}}:
                raise RuntimeError("V2 changed a frozen question, response, rating or order")
            if new["reference_material"] != old["reference_material"]:
                changed[new["task"]] += 1
    if changed != {"DG": 64}:
        raise RuntimeError("unexpected reference edit surface")
    manifest = {
        "protocol": "paper1-pairwise-teacher-human-sheet-manifest-v2", "date": DATE,
        "status": "ACTIVE_V2_96_PRESENTATIONS_PER_RATER_READY_RATINGS_PENDING",
        "supersedes": old_manifest_path.name, "amendment_authority": NAMES["amendment"],
        "source_sha256": {**{k: sha256_file(v) for k, v in source_paths.items()}, "instrument": instrument_hash,
                          "old_instrument": sha256_file(old_instrument_path), "old_sheet_manifest": sha256_file(old_manifest_path),
                          "sanitized_runtime": sha256_file(runtime_path), "raw_public_history": sha256_file(raw_path)},
        "sheets": metadata, "base_semantic_pairs": 80, "reverse_presentations": 16,
        "primary_judgements_after_completion": 192,
        "blinding": old_manifest["blinding"],
        "validation": {"original_v1_files_unchanged": True, "original_responses_inputs_and_orders_preserved": True,
                       "both_raters_same_presentations_and_orientation": True, "only_DG_reference_material_changed": True,
                       "DG_reference_sessions_match_raw_source": True, "DG_candidates_source_coverage": "complete",
                       "DG_candidate_instances_checked": checked_candidates, "human_teacher_reference_byte_equal": True,
                       "new_ratings_created": 0},
        "DG_reference_protocol": REFERENCE_PROTOCOL,
        "DG_reference_lineage": [dg_audits[t] for t in sorted(dg_audits)],
        "teacher_identity_sha256": identity_hash,
        "teacher_request_manifest": identity["exact_request_manifest"],
        "teacher_request_identities": tracked_requests,
        "offline_budget_preflight": budget,
        "implementation_sha256": {rel(p): sha256_file(p) for p in (
            Path(__file__), PROJECT / "src/metacom_pm/paper1/evaluation/human_reference.py",
            PROJECT / "src/metacom_pm/paper1/evaluation/human_reference_form.html",
            PROJECT / "src/metacom_pm/paper1/evaluation/human_reference_form.js",
        )},
        "paid_api_calls": 0, "formal_outcome_calls": 0, "pm_training_runs": 0, "locks": generation["locks"],
    }
    put(AUTH / NAMES["manifest"], manifest)
    design = read_json(AUTH / "paper1_pairwise_teacher_human_reference_design_20260904_v1.json")
    design.update({"protocol": "paper1-pairwise-teacher-human-reference-design-v2", "date": DATE,
                   "status": "ACTIVE_REFERENCE_V2_SHEETS_READY_RATINGS_PENDING",
                   "supersedes": "paper1_pairwise_teacher_human_reference_design_20260904_v1.json",
                   "human_instrument_authority": NAMES["instrument"], "human_sheet_manifest_authority": NAMES["manifest"],
                   "reference_amendment_authority": NAMES["amendment"]})
    for letter in ("A", "B"):
        design["identity_and_blinding"][f"rater_{letter}_sheet_hash"] = metadata[f"RATER_{letter}"]["sha256"]
    design["disagreement"]["resolution"] = "predeclared_consensus_after_both_primary_files_sealed"
    design["disagreement"]["unresolved_consensus"] = "uncertain"
    design["disagreement"]["before_candidate_teacher_verdicts_seen"] = True
    design["disagreement"]["trigger"] = "primary disagreement, either uncertain, or any available reversal inconsistency"
    design["disagreement"]["canonical_presentation"] = "original non-reversed presentation, anonymous A/B only"
    design["reference_protocol"] = REFERENCE_PROTOCOL
    design["human_guide_authority"] = amendment["human_authority"]
    put(AUTH / NAMES["design"], design)
    plan = read_json(AUTH / "paper1_pairwise_teacher_qualification_plan_v2.json")
    plan.update({"protocol": "paper1-pairwise-teacher-qualification-v3", "date": DATE,
                 "status": "ACTIVE_REFERENCE_V2_HUMAN_SHEETS_READY_HUMAN_AND_GEMINI_VERDICTS_PENDING",
                 "supersedes": "paper1_pairwise_teacher_qualification_plan_v2.json",
                 "human_reference_design_authority": NAMES["design"], "human_instrument_authority": NAMES["instrument"],
                 "human_sheet_manifest_authority": NAMES["manifest"], "candidate_identity_authority": NAMES["identity"],
                 "reference_amendment_authority": NAMES["amendment"]})
    plan["human_reference"]["disagreement"] = design["disagreement"]["resolution"]
    plan["human_reference"]["ratings_used_directly_for_PM_training"] = False
    plan["reference_generation"]["reference_v2_new_generator_calls"] = 0
    plan["reference_generation"]["reference_v2_new_paid_calls"] = 0
    plan["human_teacher_reference_identical"] = True
    plan["teacher_verdicts_seen_before_human_reference_sealed"] = False
    plan["same_reference_prompt_tuning_to_improve_agreement"] = "forbidden; report weakness and use the existing fallback"
    put(AUTH / NAMES["plan"], plan)

    # Stage every byte first. Refuse overwrite unless explicitly rebuilding an
    # unrated preparation package; never touch the original V1 or returned files.
    if args.rebuild_unrated:
        for rater in originals:
            existing = PROJECT / metadata[rater]["path"]
            if existing.exists() and any(i["verdict"] is not None or i["rationale"] is not None for i in read_json(existing)["items"]):
                raise RuntimeError("refusing to replace a rated V2 original")
    for path, data in pending.items():
        same = path.exists() and path.read_bytes() == data
        if args.check and not same:
            raise RuntimeError(f"package reconstruction mismatch: {rel(path)}")
        if not args.check and path.exists() and not same and not args.rebuild_unrated:
            raise RuntimeError(f"existing V2 artifact differs; preserve or explicitly rebuild the unrated preparation: {rel(path)}")
    if not args.check:
        for path, data in pending.items():
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    print(json.dumps({"status": "VERIFIED" if args.check else "MATERIALIZED", "artifacts": len(pending),
                      "raters": {r: {"presentations": 96, "html": m["html_path"], "zip": m["zip_path"]} for r, m in metadata.items()},
                      "DG_scenarios": len(dg_views), "DG_candidate_instances_source_covered": checked_candidates,
                      "offline_budget_preflight": budget, "paid_api_calls": 0, "formal_outcome_calls": 0,
                      "PM_training_runs": 0}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
