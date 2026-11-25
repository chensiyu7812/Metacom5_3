"""Engineering checks; the synthetic rows below are test fixtures, not research data."""
import json
from pathlib import Path
import os

import pytest

from metacom_pm.rl1v3.journal.rs_tasks import aggregate_task, deduplicate_utterances, runtime


def annotation(annotator, behavior, text="A fixed test utterance"):
    return dict(transcript_id="1", utterance_id="2", utterance_text=text,
                interlocutor="therapist", video_url="https://www.youtube.com/watch?v=test",
                topic="test_fixture", mi_quality="high", annotator_id=annotator,
                main_therapist_behaviour=behavior, reflection_subtype="n/a",
                question_subtype="n/a", therapist_input_subtype="n/a", client_talk_type="n/a")


def test_duplicate_annotations_preserve_disagreement_and_ties():
    unique = deduplicate_utterances([annotation("a", "question"), annotation("b", "reflection")])
    assert len(unique) == 1
    assert len(unique[0]["annotations"]) == 2
    label = unique[0]["labels"]["main_therapist_behaviour"]
    assert label["consensus"] is None
    assert label["tie"] and not label["unanimous"]
    assert label["counts"] == {"question": 1, "reflection": 1}


def test_duplicate_source_text_conflict_fails_closed():
    with pytest.raises(ValueError, match="disagree on source"):
        deduplicate_utterances([annotation("a", "question"), annotation("b", "question", "changed")])


def test_runtime_allowlist_drops_private_canaries():
    task = dict(task_id="opaque", turns=[dict(role="seeker", text="visible")],
                gold="GOLD_CANARY", intended_skill_private="SKILL_CANARY",
                source_family_ids=["FAMILY_CANARY"], outcome=1)
    encoded = json.dumps(runtime(task))
    assert all(canary not in encoded for canary in ("GOLD_CANARY", "SKILL_CANARY", "FAMILY_CANARY"))
    assert set(runtime(task)) == {"task_id", "turns", "timestamp"}


def test_pending_and_technical_failures_are_not_negative_rewards():
    assert aggregate_task(["uncertain"], ["pass"]) == dict(status="pending", lower=0, upper=1)
    assert aggregate_task(["pass"], ["uncertain"]) == dict(status="pending", lower=0, upper=1)
    assert aggregate_task(["uncertain", "fail"], ["pass"]) == dict(status="failed", lower=0, upper=0)
    assert aggregate_task(["pass"], ["pass"]) == dict(status="passed", lower=1, upper=1)
    assert aggregate_task([], [], technical_failure=True) == dict(status="technical_failure", lower=None, upper=None)
    with pytest.raises(ValueError):
        aggregate_task([], [])


@pytest.mark.skipif(not os.environ.get("JOURNAL_RS_OUTPUT"), reason="private actual-data output not supplied")
def test_actual_materials_have_complete_coverage_and_matched_raw_method_sources():
    root = Path(os.environ["JOURNAL_RS_OUTPUT"])
    rows = [json.loads(line) for line in (root / "request_materials.private.jsonl").read_text().splitlines()]
    cases = [json.loads(line) for line in (root / "cases.private.jsonl").read_text().splitlines()]
    evaluations = [json.loads(line) for line in (root / "evalspec.private.jsonl").read_text().splitlines()]
    assert len(rows) == 144 and len(evaluations) == 24
    tasks = {r["task_id"] for r in rows}
    assert len(tasks) == 24
    for task in tasks:
        arms = {r["arm"]: r for r in rows if r["task_id"] == task}
        assert len(arms) == 6
        assert arms["R0"]["readings"] == []
        assert arms["Method"]["provenance_private"]["raw_method_paragraph_hashes"] == arms["Professional-RAW"]["provenance_private"]["raw_method_paragraph_hashes"]
        assert len({json.dumps(r["runtime"], sort_keys=True) for r in arms.values()}) == 1
        for row in arms.values():
            assert set(row["runtime"]) == {"task_id", "turns", "timestamp"}
    task_families = {f for e in evaluations for f in e["source_family_ids"]}
    assert len(task_families) == 12
    assert not task_families & {c["video_family"] for c in cases}
    assert all(e["outcome"] is None and not e["reward_qualified"] for e in evaluations)
