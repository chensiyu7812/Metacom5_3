from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = (
    ROOT
    / "data"
    / "pm_v1_5_contracts"
    / "paper1_p1_public_source_group_manifest_candidate_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "outputs"
    / "pm_v1_5_paper1_p1_manifest_design_20260810"
    / "report.json"
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def validate_manifest() -> dict[str, Any]:
    manifest = _read_json(MANIFEST)
    binding = manifest["method_binding"]
    authority_path = _resolve(binding["parent_authority_path"])
    contract_path = _resolve(binding["active_contract_path"])
    authority = _read_json(authority_path)
    contract = _read_json(contract_path)
    candidate_record = authority["validated_p1_design_candidate"]
    paid_path = _resolve(authority["paid_execution_guard"]["central_release_path"])
    paid = _read_json(paid_path)

    es_binding = manifest["source_bindings"]["ESConv"]
    es_path = _resolve(es_binding["path"])
    split_path = _resolve(es_binding["split_manifest_path"])
    esconv = _read_json(es_path)
    split_rows = _read_jsonl(split_path)

    evo_binding = manifest["source_bindings"]["EvoEmo_and_ES_MemEval"]
    evo_path = _resolve(evo_binding["path"])
    evoemo = _read_json(evo_path)

    split_counts: Counter[str] = Counter()
    nonoverlap_counts: Counter[str] = Counter()
    quarantine_ids: set[str] = set()
    split_join_valid = len(esconv) == len(split_rows)
    for index, row in enumerate(split_rows):
        expected_id = f"esconv_{index:04d}"
        split_join_valid = split_join_valid and (
            row.get("index") == index and row.get("dialogue_id") == expected_id
        )
        split_name = str(row.get("split"))
        split_counts[split_name] += 1
        if bool(row.get("excluded_for_evoemo_overlap")):
            quarantine_ids.add(expected_id)
        else:
            nonoverlap_counts[split_name] += 1

    owners_by_session: dict[str, set[str]] = defaultdict(set)
    user_session_counts: dict[str, int] = {}
    user_question_counts: dict[str, int] = {}
    question_keys: set[tuple[str, str, int]] = set()
    question_total = 0
    capability_counts: Counter[str] = Counter()
    for user in evoemo:
        user_id = str(user["id"])
        sessions = list(user.get("dialog_history") or [])
        user_session_counts[user_id] = len(sessions)
        for session in sessions:
            owners_by_session[str(session["id"])].add(user_id)
        per_user_questions = 0
        for group in user.get("questions") or []:
            group_id = str(group["id"])
            for question in group.get("questions") or []:
                question_total += 1
                per_user_questions += 1
                capability_counts[str(question["capability"])] += 1
                question_keys.add((user_id, group_id, int(question["idx"])))
        user_question_counts[user_id] = per_user_questions

    duplicated_sessions = {
        session_id: sorted(owners)
        for session_id, owners in owners_by_session.items()
        if len(owners) > 1
    }
    composite_session_rows = sum(user_session_counts.values())

    folds = manifest["frozen_outer_folds"]["folds"]
    user_to_fold: dict[str, int] = {}
    fold_counts_valid = True
    for row in folds:
        fold = int(row["fold"])
        users = [str(user_id) for user_id in row["held_out_users"]]
        if any(user_id in user_to_fold for user_id in users):
            fold_counts_valid = False
        for user_id in users:
            user_to_fold[user_id] = fold
        fold_counts_valid = fold_counts_valid and (
            int(row["held_out_sessions"])
            == sum(user_session_counts[user_id] for user_id in users)
            and int(row["held_out_questions"])
            == sum(user_question_counts[user_id] for user_id in users)
        )
    shared_sessions_one_fold = all(
        len({user_to_fold.get(user_id) for user_id in owners}) == 1
        for owners in owners_by_session.values()
    )

    authorization = manifest["authorization"]
    mutating_authorizations = {
        key: value
        for key, value in authorization.items()
        if key
        not in {
            "design_and_validation_only",
            "activation_rule",
        }
        and value is not False
    }

    candidate_design = manifest["candidate_construction_design"]
    asset_bindings: list[tuple[str, str]] = [
        (
            candidate_design["MS_SESSION"]["compiler_path"],
            candidate_design["MS_SESSION"]["compiler_sha256"],
        ),
        (
            candidate_design["MS_SESSION"]["ranker_path"],
            candidate_design["MS_SESSION"]["ranker_sha256"],
        ),
        (
            candidate_design["ME_REUSABLE_OUTCOME"]["compiler_path"],
            candidate_design["ME_REUSABLE_OUTCOME"]["compiler_sha256"],
        ),
        (
            candidate_design["RS_ATOMIC_MOVE"]["bank_path"],
            candidate_design["RS_ATOMIC_MOVE"]["bank_sha256"],
        ),
        (
            candidate_design["RS_ATOMIC_MOVE"]["bank_freeze_path"],
            candidate_design["RS_ATOMIC_MOVE"]["bank_freeze_sha256"],
        ),
        (
            candidate_design["RS_ATOMIC_MOVE"]["rank1_selector_path"],
            candidate_design["RS_ATOMIC_MOVE"]["rank1_selector_sha256"],
        ),
        (
            candidate_design["shared_candidate_discovery"]["path"],
            candidate_design["shared_candidate_discovery"]["sha256"],
        ),
        (
            evo_binding["chronology_loader"]["path"],
            evo_binding["chronology_loader"]["sha256"],
        ),
    ]
    assets_match = all(_sha256(_resolve(path)) == expected for path, expected in asset_bindings)
    card_path = _resolve(candidate_design["RS_ATOMIC_MOVE"]["bank_path"])
    card_count = len(_read_jsonl(card_path))

    runtime_forbidden = set(manifest["observability_boundary"]["EvoEmo_runtime_forbidden"])
    qa_evaluator_only = set(
        manifest["observability_boundary"]["ES_MemEval_evaluator_only"]
    )
    es_runtime_forbidden = set(
        manifest["observability_boundary"]["ESConv_runtime_forbidden"]
    )

    checks = {
        "candidate_status_is_not_authority": manifest["status"]
        == "P1_DESIGN_CANDIDATE_NOT_EXECUTION_AUTHORITY",
        "method_id_matches": binding["method_id"] == contract["method_id"]
        == authority["active_method"]["method_id"],
        "contract_hash_matches": _sha256(contract_path)
        == binding["active_contract_sha256"]
        == authority["active_method"]["contract_sha256"],
        "candidate_manifest_is_bound_by_current_authority": _sha256(MANIFEST)
        == candidate_record["sha256"]
        and candidate_record["path"]
        == str(MANIFEST.relative_to(ROOT)),
        "validated_parent_authority_hash_matches": binding[
            "parent_authority_sha256"
        ]
        == candidate_record["validated_under_parent_authority_sha256"],
        "current_authority_declares_amendment_compatibility": "changes only"
        in candidate_record["compatibility_after_amendment"]
        and "cannot authorize execution"
        in candidate_record["compatibility_after_amendment"],
        "design_parent_phase_was_p0": binding["parent_phase"]
        == "P0_ZERO_API_CLAIM_LABEL_VERSION_FREEZE",
        "manifest_cannot_self_authorize": authorization[
            "design_and_validation_only"
        ]
        is True
        and not mutating_authorizations,
        "paid_release_remains_false": paid.get("paid_execution_authorized")
        is False,
        "source_hashes_match": _sha256(es_path) == es_binding["sha256"]
        and _sha256(split_path) == es_binding["split_manifest_sha256"]
        and _sha256(evo_path) == evo_binding["sha256"],
        "esconv_source_shape": isinstance(esconv, list)
        and len(esconv) == es_binding["dialogues"] == 1300,
        "esconv_manifest_exact_join": split_join_valid,
        "esconv_split_counts": dict(split_counts)
        == es_binding["split_counts"],
        "esconv_quarantine_count": len(quarantine_ids)
        == es_binding["evoemo_seed_quarantine"]
        == 84,
        "esconv_nonoverlap_counts": dict(nonoverlap_counts)
        == es_binding["nonoverlap_counts"],
        "evoemo_users_are_exact": [str(user["id"]) for user in evoemo]
        == [f"p{index}" for index in range(1, 19)],
        "evoemo_session_counts": composite_session_rows
        == evo_binding["composite_owner_session_rows"]
        == 401
        and len(owners_by_session)
        == evo_binding["globally_unique_raw_session_ids"]
        == 400,
        "known_shared_session_exact": duplicated_sessions
        == manifest["canonical_identity_and_grouping"]["EvoEmo"][
            "shared_raw_session_owners"
        ]
        == {"esc1198": ["p13", "p18"]},
        "question_denominator_and_keys": question_total
        == len(question_keys)
        == evo_binding["questions"]
        == 1427,
        "question_capabilities_match": dict(capability_counts)
        == evo_binding["question_capabilities_evaluator_only"],
        "six_outer_folds_cover_users_once": len(folds) == 6
        and set(user_to_fold) == {f"p{index}" for index in range(1, 19)}
        and fold_counts_valid,
        "shared_source_users_same_fold": shared_sessions_one_fold
        and user_to_fold["p13"] == user_to_fold["p18"],
        "runtime_owner_is_not_split_group": manifest[
            "canonical_identity_and_grouping"
        ]["EvoEmo"]["runtime_owner_key"]
        != manifest["canonical_identity_and_grouping"]["EvoEmo"][
            "split_group_key"
        ],
        "evo_hindsight_fields_forbidden": {
            "summary",
            "observation",
            "event_experience",
            "social_relationship",
            "summaries",
            "subsequent_topics",
            "questions",
            "question answer",
            "question evidence",
        }.issubset(runtime_forbidden),
        "esconv_gold_and_posttreatment_forbidden": {
            "situation",
            "survey_score",
            "dialog[].annotation",
            "observed supporter response selected as target gold",
        }.issubset(es_runtime_forbidden),
        "qa_gold_physically_separate": {
            "capability",
            "answer",
            "evidence",
        }.issubset(qa_evaluator_only)
        and manifest["dataset_roles"]["ES_MemEval"][
            "response_pm_training_labels"
        ]
        is False,
        "candidate_asset_hashes_match": assets_match,
        "six_card_bank_exact": card_count
        == candidate_design["RS_ATOMIC_MOVE"]["card_count"]
        == 6,
        "memory_is_raw_exact_span_only": "literal source turn"
        in candidate_design["MS_SESSION"]["materialization"]
        and "literal within-turn action-result spans"
        in candidate_design["ME_REUSABLE_OUTCOME"]["materialization"],
        "rank2_promotion_forbidden": "never promote Rank-2"
        in candidate_design["common"]["actual_rank1"],
        "legacy_panels_not_reusable": all(
            marker in manifest["legacy_non_reuse"][key]
            for key, marker in (
                ("old_evoemo_204_state_panel", "forbidden"),
                ("old_esconv_122_state_panel", "not reusable"),
                ("old_qa_418_gold", "not reusable"),
                ("old_pm_checkpoints", "never active"),
            )
        ),
        "no_calls_labels_training_or_outcomes": manifest["api_calls"] == 0
        and manifest["responses_generated"] == 0
        and manifest["labels_created"] == 0
        and manifest["pm_trained"] is False
        and manifest["external_outcomes_read"] is False,
    }
    failed = [name for name, passed in checks.items() if not passed]
    return {
        "protocol": "pm-v1.5-paper1-p1-public-source-group-manifest-design-validation-v1",
        "status": (
            "P1_MANIFEST_DESIGN_PASS_EXECUTION_STILL_NOT_AUTHORIZED"
            if not failed
            else "P1_MANIFEST_DESIGN_FAIL_CLOSED"
        ),
        "checks": checks,
        "failed_checks": failed,
        "manifest_sha256": _sha256(MANIFEST),
        "active_contract_sha256": _sha256(contract_path),
        "current_authority_sha256": _sha256(authority_path),
        "validated_parent_authority_sha256": binding[
            "parent_authority_sha256"
        ],
        "observed_counts": {
            "esconv_split": dict(split_counts),
            "esconv_nonoverlap": dict(nonoverlap_counts),
            "esconv_quarantine": len(quarantine_ids),
            "evoemo_users": len(evoemo),
            "evoemo_composite_sessions": composite_session_rows,
            "evoemo_unique_session_ids": len(owners_by_session),
            "es_memeval_questions": question_total,
            "es_memeval_capabilities": dict(capability_counts),
            "rs_cards": card_count,
        },
        "shared_raw_session_owners": duplicated_sessions,
        "fold_assignment": {
            str(row["fold"]): row["held_out_users"] for row in folds
        },
        "mutating_authorizations": mutating_authorizations,
        "next": (
            "IMPLEMENT_AND_VALIDATE_A_SEPARATE_NO_MODEL_P1_MATERIALIZER_THEN_PROMOTE_BY_HASH"
            if not failed
            else "REPAIR_CANDIDATE_MANIFEST_ONLY_WITHOUT_EXECUTION"
        ),
        "api_calls": 0,
        "responses_generated": 0,
        "labels_created": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = validate_manifest()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))
    if report["failed_checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
