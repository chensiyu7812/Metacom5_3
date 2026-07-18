from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from metacom_pm.artifacts import create_artifact_attestation
from metacom_pm.evoemo import evoemo_chronology_audit, normalize_evoemo_chronology
from metacom_pm.io import iter_jsonl, read_json, sha256_file, write_json
from metacom_pm.paid_run_release import (
    PAID_RUN_RELEASE_PROTOCOL,
    require_paid_run_release,
)
from metacom_pm.pm_v1_5_algorithm_selection import (
    _select_one_standard_error_candidate,
)
from metacom_pm.v1_5_actual_corpus_review import (
    ACTUAL_CORPUS_REVIEW_PROTOCOL,
    ACTUAL_CORPUS_REVIEW_STAGE,
    _surface_fallback_report,
    require_actual_corpus_semantic_review_pass,
)
from metacom_pm.v1_5_automated_semantic_review import (
    V1_5_REVIEW_STRATEGY_CARD_IDS,
)


ROOT = Path(__file__).resolve().parents[1]


def test_every_v1_5_paid_entrypoint_calls_the_central_release_gate() -> None:
    candidates = [
        *sorted((ROOT / "scripts" / "v1_5").glob("*.py")),
        *sorted((ROOT / "scripts").glob("v1_5_*.py")),
    ]
    paid_entrypoints = []
    for path in candidates:
        source = path.read_text(encoding="utf-8")
        if 'add_argument("--run"' in source:
            paid_entrypoints.append(path)
            assert "require_paid_run_release" in source, path
    assert paid_entrypoints


def test_central_paid_release_is_fail_closed_and_identity_bound(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "configs" / "pm_v1_5.yaml"
    config_path.parent.mkdir(parents=True)
    manifest_path = tmp_path / "outputs" / "paid_release.json"
    blocked = {
        "release_revision": "pm-v1.5_1",
        "execution_release": {
            "protocol": PAID_RUN_RELEASE_PROTOCOL,
            "status": "PAID_RUN_BLOCKED",
            "release_revision": "pm-v1.5_1",
            "approval_manifest": "outputs/paid_release.json",
        },
    }
    write_json(config_path, blocked)
    assert require_paid_run_release(
        blocked,
        config_path=config_path,
        stage="development_data_generation",
        run=False,
        run_identity=None,
    )["status"] == "DRY_RUN_ALLOWED"
    with pytest.raises(RuntimeError, match="centrally blocked"):
        require_paid_run_release(
            blocked,
            config_path=config_path,
            stage="development_data_generation",
            run=True,
            run_identity="fresh-cost-hash",
        )

    released = {
        **blocked,
        "execution_release": {
            **blocked["execution_release"],
            "status": "PAID_RUN_RELEASED",
        },
    }
    write_json(config_path, released)
    manifest_path.parent.mkdir(parents=True)
    write_json(
        manifest_path,
        {
            "protocol": PAID_RUN_RELEASE_PROTOCOL,
            "status": "APPROVED",
            "release_revision": "pm-v1.5_1",
            "config_sha256": sha256_file(config_path),
            "stage_approvals": {
                "development_data_generation": "fresh-cost-hash"
            },
        },
    )
    assert require_paid_run_release(
        released,
        config_path=config_path,
        stage="development_data_generation",
        run=True,
        run_identity="fresh-cost-hash",
    )["status"] == "PAID_RUN_RELEASED"
    with pytest.raises(RuntimeError, match="stale"):
        require_paid_run_release(
            released,
            config_path=config_path,
            stage="development_data_generation",
            run=True,
            run_identity="different-hash",
        )


def test_source_disjoint_strategy_bank_keeps_all_strategy_families() -> None:
    selected_path = (
        ROOT / "data" / "strategy" / "pm_v1_5_selected_seed_sources.jsonl"
    )
    bank_path = ROOT / "data" / "strategy" / "strategy_cards_v1_5.jsonl"
    audit = read_json(
        ROOT / "data" / "strategy" / "strategy_bank_audit_v1_5.json"
    )
    selected = [str(row["dialogue_id"]) for row in iter_jsonl(selected_path)]
    cards = [dict(row) for row in iter_jsonl(bank_path)]
    source_ids = {str(row["source_dialogue_id"]) for row in cards}
    families = {str(row["strategy_label"]) for row in cards}

    assert len(selected) == len(set(selected)) == 52
    assert set(selected).isdisjoint(source_ids)
    assert len(cards) == 11_590
    assert len(source_ids) == 823
    assert len(families) == 8
    exclusion = audit["development_seed_exclusion"]
    assert exclusion["excluded_source_ids"] == sorted(selected)
    assert exclusion["bank_source_intersection"] == []
    assert audit["strategy_family_card_counts"]
    assert all(int(count) > 0 for count in audit["strategy_family_card_counts"].values())

    by_id = {str(row["strategy_id"]): row for row in cards}
    review_cards = [by_id[value] for value in V1_5_REVIEW_STRATEGY_CARD_IDS.values()]
    assert len(review_cards) == len(V1_5_REVIEW_STRATEGY_CARD_IDS) == 11
    assert len({row["source_dialogue_id"] for row in review_cards}) == 11
    assert {row["source_dialogue_id"] for row in review_cards}.isdisjoint(selected)
    role_labels = {
        "gentle_question": "Question",
        "open_restatement": "Restatement or Paraphrasing",
        "stress_reflection": "Reflection of feelings",
        "exam_reflection": "Reflection of feelings",
        "one_problem_suggestion": "Providing Suggestions",
        "social_connection_suggestion": "Providing Suggestions",
        "low_pressure_connection": "Providing Suggestions",
        "intrusive_long_plan": "Providing Suggestions",
        "video_call_self_disclosure": "Self-disclosure",
        "support_affirmation": "Affirmation and Reassurance",
        "job_information": "Information",
    }
    assert {
        role: by_id[card_id]["strategy_label"]
        for role, card_id in V1_5_REVIEW_STRATEGY_CARD_IDS.items()
    } == role_labels


def test_evoemo_chronology_is_timestamp_normalized_and_refs_fail_closed() -> None:
    raw = [
        {
            "id": "u1",
            "dialog_history": [
                {"id": "later", "timestamp": "2024-02-01"},
                {"id": "earlier", "timestamp": "2024-01-01"},
            ],
            "subsequent_topics": [
                {"idx": 0, "related_sessions": ["earlier", "later"]}
            ],
        }
    ]
    normalized, report = normalize_evoemo_chronology(raw)
    assert [row["id"] for row in normalized[0]["dialog_history"]] == [
        "earlier",
        "later",
    ]
    assert report["status"] == "PASS_WITH_FROZEN_TIMESTAMP_NORMALIZATION"
    assert report["reordered_user_count"] == 1

    raw[0]["subsequent_topics"][0]["related_sessions"] = ["missing"]
    with pytest.raises(RuntimeError, match="reference missing"):
        normalize_evoemo_chronology(raw)

    corpus = evoemo_chronology_audit(ROOT / "data" / "external" / "evo_emo.json")
    assert corpus["users"] == 18
    assert corpus["sessions"] == 401
    assert corpus["topics"] == 34
    assert corpus["reordered_user_count"] == 6
    assert corpus["related_session_references_checked"] == 149


def test_actual_corpus_fallback_gate_is_split_specific_and_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bundles = [
        SimpleNamespace(
            user_id="train_user",
            cases=[object(), object()],
            provenance={"surface_selection": {"fallback_cases": ["one"]}},
        ),
        SimpleNamespace(
            user_id="internal_user",
            cases=[object()],
            provenance={"surface_selection": {"fallback_cases": []}},
        ),
    ]
    monkeypatch.setattr(
        "metacom_pm.v1_5_actual_corpus_review.load_bundles", lambda _: bundles
    )
    split_by_user = {
        "train_user": "train",
        "internal_user": "internal_test",
    }
    passed = _surface_fallback_report(
        bundles_path="unused.jsonl",
        split_by_user=split_by_user,
        maximum_fallback_rate_by_split={
            "train": 0.5,
            "calibration": 0.0,
            "internal_test": 0.0,
        },
    )
    assert passed["status"] == "PASS"
    failed = _surface_fallback_report(
        bundles_path="unused.jsonl",
        split_by_user=split_by_user,
        maximum_fallback_rate_by_split={
            "train": 0.49,
            "calibration": 0.0,
            "internal_test": 0.0,
        },
    )
    assert failed["status"] == "FAIL"


def test_actual_468_gate_is_attested_and_binds_state_corpus(
    tmp_path: Path,
) -> None:
    states = tmp_path / "states.jsonl"
    states.write_text('{"state_id":"s1"}\n', encoding="utf-8")
    report_path = tmp_path / "gate_report.json"
    write_json(
        report_path,
        {
            "protocol": ACTUAL_CORPUS_REVIEW_PROTOCOL,
            "status": "PASS",
            "n_real_cases": 468,
            "corpus_audit": {
                "fallback_gate": {"status": "PASS"},
                "input_hashes": {"states": sha256_file(states)},
            },
        },
    )
    attestation = tmp_path / "attestation.json"
    create_artifact_attestation(
        attestation,
        stage=ACTUAL_CORPUS_REVIEW_STAGE,
        inputs={"states": states},
        outputs={"gate_report": (report_path, False)},
        parameters={},
    )
    assert require_actual_corpus_semantic_review_pass(
        report_path, attestation, expected_states_path=states
    )["status"] == "PASS"
    states.write_text('{"state_id":"changed"}\n', encoding="utf-8")
    with pytest.raises(RuntimeError, match="hash mismatch|did not PASS"):
        require_actual_corpus_semantic_review_pass(
            report_path, attestation, expected_states_path=states
        )


def test_one_standard_error_rule_prefers_simpler_near_best_candidate() -> None:
    common = {
        "mean_quality": 0.8,
        "mean_risk": 0.1,
        "mean_observed_input_tokens": 100.0,
        "action_distribution_instability": 0.1,
    }
    raw_best = {
        **common,
        "algorithm": "complex",
        "priority": 0,
        "simplicity_rank": 2,
        "mean_realized_utility": 0.80,
        "mean_realized_utility_standard_error": 0.05,
    }
    simpler = {
        **common,
        "algorithm": "simple",
        "priority": 1,
        "simplicity_rank": 0,
        "mean_realized_utility": 0.77,
        "mean_realized_utility_standard_error": 0.01,
    }
    below_band = {
        **common,
        "algorithm": "too_weak",
        "priority": 2,
        "simplicity_rank": 0,
        "mean_realized_utility": 0.74,
        "mean_realized_utility_standard_error": 0.01,
    }
    best, selected, floor, candidates = _select_one_standard_error_candidate(
        [raw_best, simpler, below_band]
    )
    assert best["algorithm"] == "complex"
    assert floor == pytest.approx(0.75)
    assert {row["algorithm"] for row in candidates} == {"complex", "simple"}
    assert selected["algorithm"] == "simple"
