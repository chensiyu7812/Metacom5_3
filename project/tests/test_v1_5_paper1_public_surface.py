from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys

from metacom_pm.v1_5_paper1_public_surface import (
    build_esconv_states,
    build_evo_states_and_candidates,
    build_qa_surfaces,
    validate_surfaces,
    write_structural_surface,
)


ROOT = Path(__file__).resolve().parents[1]


def _users() -> list[dict]:
    return [
        {
            "id": "p13",
            "basic_info": {
                "name": "Hidden Name",
                "job": "teacher",
                "location": "Osaka",
            },
            "dialog_history": [
                {
                    "id": "esc1198",
                    "timestamp": "2024-01-01",
                    "dialogue": [
                        {
                            "idx": 1,
                            "role": "seeker",
                            "content": "I tried journaling and it helped me feel calmer.",
                        },
                        {"idx": 2, "role": "supporter", "content": "I hear you."},
                    ],
                },
                {
                    "id": "p13_conv_2",
                    "timestamp": "2024-01-02",
                    "dialogue": [
                        {
                            "idx": 1,
                            "role": "seeker",
                            "content": "Work feels difficult again today.",
                        }
                    ],
                },
            ],
            "questions": [
                {
                    "id": "timeline",
                    "questions": [
                        {
                            "idx": 1,
                            "question": "What helped before?",
                            "capability": "temporal reasoning",
                            "answer": "Journaling helped.",
                            "evidence": ["esc1198:1"],
                        }
                    ],
                }
            ],
        },
        {
            "id": "p18",
            "basic_info": {
                "name": "Other Hidden Name",
                "job": "designer",
                "location": "Tokyo",
            },
            "dialog_history": [
                {
                    "id": "esc1198",
                    "timestamp": "2024-01-03",
                    "dialogue": [
                        {
                            "idx": 1,
                            "role": "seeker",
                            "content": "I need to think through this carefully.",
                        }
                    ],
                }
            ],
            "questions": [
                {
                    "id": "abstention",
                    "questions": [
                        {
                            "idx": 1,
                            "question": "What is not known?",
                            "capability": "abstention",
                            "answer": "The source does not say.",
                            "evidence": [],
                        }
                    ],
                }
            ],
        },
    ]


def test_esconv_surface_uses_only_visible_dialogue_and_excludes_quarantine() -> None:
    dialogues = [
        {
            "situation": "forbidden",
            "survey_score": {"x": 5},
            "dialog": [
                {"speaker": "seeker", "content": "I feel stuck.", "annotation": {}},
                {
                    "speaker": "supporter",
                    "content": "What feels hardest?",
                    "annotation": {"strategy": "Question"},
                },
                {"speaker": "seeker", "content": "Choosing.", "annotation": {}},
                {
                    "speaker": "supporter",
                    "content": "That makes sense.",
                    "annotation": {"strategy": "Affirmation"},
                },
            ],
        },
        {"dialog": [{"speaker": "seeker", "content": "Quarantined"}]},
    ]
    splits = [
        {
            "index": 0,
            "dialogue_id": "esconv_0000",
            "split": "train",
            "excluded_for_evoemo_overlap": False,
        },
        {
            "index": 1,
            "dialogue_id": "esconv_0001",
            "split": "test",
            "excluded_for_evoemo_overlap": True,
        },
    ]
    states = build_esconv_states(dialogues, splits)

    assert len(states) == 2
    assert {row["dialogue_id"] for row in states} == {"esconv_0000"}
    assert states[0]["visible_dialogue"] == [
        {"raw_turn_index": 0, "speaker": "seeker", "content": "I feel stuck."}
    ]
    serialized = json.dumps(states)
    assert "forbidden" not in serialized
    assert "annotation" not in serialized
    assert "Affirmation" not in serialized


def test_evo_surface_binds_shared_split_but_keeps_owner_catalogs_separate() -> None:
    users = _users()
    states, candidates, groups = build_evo_states_and_candidates(
        users, {"p13": 1, "p18": 1}
    )

    assert len(states) == 3
    assert len(groups) == 1
    assert groups[0]["runtime_owners"] == ["p13", "p18"]
    assert groups[0]["split_group_key"] == "evo_component::p13__p18"
    assert {row["runtime_owner_key"] for row in candidates} == {
        "evo::p13",
        "evo::p18",
    }
    assert all("Hidden Name" not in row["literal_text"] for row in candidates)
    p13_second = next(
        row for row in states if row["source_session_id"] == "p13_conv_2"
    )
    assert p13_second["candidate_source_counts"]["MS"] == 1
    assert p13_second["candidate_source_counts"]["ME"] == 1
    assert all(
        row["runtime_owner_key"] == "evo::p13"
        for row in candidates
        if row["component"] == "ME"
    )


def test_qa_visible_and_evaluator_gold_are_physically_separable() -> None:
    visible, evaluator = build_qa_surfaces(
        _users(), {"p13": 1, "p18": 1}
    )

    assert len(visible) == len(evaluator) == 2
    assert {row["question_id"] for row in visible} == {
        row["question_id"] for row in evaluator
    }
    assert all(
        not ({"answer", "evidence", "capability", "wrapper_user_id"} & set(row))
        for row in visible
    )
    assert all("answer" in row and "evidence" in row for row in evaluator)


def test_structural_surface_validation_and_writes_are_unlabeled(tmp_path: Path) -> None:
    users = _users()
    evo_states, candidates, groups = build_evo_states_and_candidates(
        users, {"p13": 1, "p18": 1}
    )
    qa_visible, qa_evaluator = build_qa_surfaces(
        users, {"p13": 1, "p18": 1}
    )
    esconv_states = build_esconv_states(
        [
            {
                "dialog": [
                    {"speaker": "seeker", "content": "Please help."},
                    {"speaker": "supporter", "content": "Okay."},
                ]
            }
        ],
        [
            {
                "index": 0,
                "dialogue_id": "esconv_0000",
                "split": "train",
                "excluded_for_evoemo_overlap": False,
            }
        ],
    )
    validation = validate_surfaces(
        esconv_states=esconv_states,
        evo_states=evo_states,
        candidates=candidates,
        qa_visible=qa_visible,
        qa_evaluator=qa_evaluator,
    )
    assert validation["failed_checks"] == []

    report = write_structural_surface(
        output_dir=tmp_path / "public",
        private_output_dir=tmp_path / "private",
        esconv_states=esconv_states,
        evo_states=evo_states,
        candidates=candidates,
        groups=groups,
        qa_visible=qa_visible,
        qa_evaluator=qa_evaluator,
        source_index={"protocol": "fixture", "api_calls": 0},
    )
    assert report["status"] == (
        "P1_STRUCTURAL_SURFACE_PASS_ACTUAL_RANK1_NOT_YET_MATERIALIZED"
    )
    assert report["actual_rank1_materialized"] is False
    assert report["labels_created"] == 0
    assert (tmp_path / "public" / "qa_generator_visible.jsonl").is_file()
    assert (tmp_path / "private" / "qa_evaluator_only.jsonl").is_file()


def test_completed_structural_cli_fails_closed_before_reading_public_sources() -> None:
    script = (
        ROOT
        / "scripts"
        / "v1_5"
        / "175l_materialize_paper1_p1_public_structural_surface_v1_5.py"
    )
    completed = subprocess.run(
        [sys.executable, str(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )

    assert completed.returncode != 0
    assert "P1 structural materialization is not active" in completed.stderr
