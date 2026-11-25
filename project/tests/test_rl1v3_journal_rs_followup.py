"""CPU checks for preserved delivery, weighted labels and frozen new dev tasks."""
import json
import os
from pathlib import Path

import pytest

from metacom_pm.rl1v3.journal.behavior_compare import labels_expanded
from metacom_pm.rl1v3.journal.rs_tasks import runtime


def test_annotation_distribution_keeps_each_utterance_total_weight_one():
    rows=[dict(annotations=[dict(main_therapist_behaviour="question")]),
          dict(annotations=[dict(main_therapist_behaviour="reflection"),dict(main_therapist_behaviour="question")])]
    indices,labels,weights=labels_expanded(rows)
    assert indices==[0,1,1]
    assert labels==["question","reflection","question"]
    assert weights==[1.0,0.5,0.5]
    assert sum(w for i,w in zip(indices,weights) if i==1)==1


def test_private_complex_conditions_never_enter_runtime():
    task=dict(task_id="opaque",turns=[dict(role="seeker",text="user text")],
              condition_private="CANARY_CONDITION",source_family_ids=["CANARY_FAMILY"],
              requirements=[dict(criterion="CANARY_GOLD")],source_evidence=["CANARY_SOURCE"])
    serialized=json.dumps(runtime(task))
    assert "CANARY" not in serialized
    assert set(runtime(task))=={"task_id","turns","timestamp"}


ROOT=os.environ.get("JOURNAL_RS_FOLLOWUP")


@pytest.mark.skipif(not ROOT,reason="actual private artifacts not supplied")
def test_actual_seven_video_cv_retains_distribution_and_fixed_encoder():
    root=Path(ROOT)/"behavior-compare-v1"
    result=json.loads((root/"RESULTS.json").read_text())
    assert result["fully_completed"] and not result["reward_qualified"]
    assert result["model_identity"]["device"]=="cpu"
    assert result["model_identity"]["files_sha256"]["model.safetensors"]=="3c9f31665447c8911517620762200d2245a2518d6e7208acc78cd9db317e21ad"
    assert result["encoding"]["unique_utterances"]==4882
    assert result["encoding"]["truncated_utterances"]==0
    assert len(result["seven_video_folds"])==7
    assert sum(f["test_unique"] for f in result["seven_video_folds"])==216
    assert all(f["family_overlap"]==0 and f["test_families"]==1 for f in result["seven_video_folds"])
    predictions=[json.loads(l) for l in (root/"predictions.private.jsonl").read_text().splitlines()]
    for method in ("tfidf_equal_utterance","bge_small_frozen_equal_utterance"):
        group=[p for p in predictions if p["method"]==method and p["fold"].startswith("multi_video")]
        assert len(group)==216
        assert len({tuple(p["key"]) for p in group})==216
        assert len({p["video_family"] for p in group})==7
        assert all(sum(p["annotation_distribution"].values())==10 for p in group)
        assert sum(len(p["annotation_distribution"])>1 for p in group)==104
    assert not result["model_selected"]


@pytest.mark.skipif(not ROOT,reason="actual private artifacts not supplied")
def test_actual_delivery_and_new_complex_task_freeze():
    root=Path(ROOT)
    audit=json.loads((root/"delivery-audit-v1/RESULTS.json").read_text())
    assert audit["preserved_requests"]==144 and audit["exact_native_token_checks"]==144
    assert audit["exact_reading_content_checks"]==144
    assert audit["F_resident_full_library_checks"]==24
    assert not audit["direct_versus_retrieval"]["direct_intended_skill_diagnostic_in_original_144"]
    assert audit["actual_selected_skills"].get("skill:permission",0)==0
    coverage=json.loads((root/"complex12-v1/COVERAGE.json").read_text())
    assert coverage["tasks"]==12 and coverage["source_video_families"]==12
    assert coverage["overlap_with_original24_and_casev2_video_families"]==0
    assert set(coverage["conditions"].values())=={2}
    tasks=[json.loads(l) for l in (root/"complex12-v1/TASKS.runtime.jsonl").read_text().splitlines()]
    evaluations=[json.loads(l) for l in (root/"complex12-v1/EVALSPEC.private.jsonl").read_text().splitlines()]
    for task,evaluation in zip(tasks,evaluations):
        assert task["task_id"]==evaluation["task_id"]
        assert set(task)=={"task_id","turns","timestamp"}
        assert all(p["exact_quote"] in task["turns"][0]["text"] for p in evaluation["source_evidence"])
        assert evaluation["constructed_supplement"] in task["turns"][0]["text"]
        assert evaluation["outcome"] is None and not evaluation["reward_qualified"]
        assert all(len(r["allowed_alternatives"])>=2 for r in evaluation["requirements"])


@pytest.mark.skipif(not ROOT,reason="actual private artifacts not supplied")
def test_actual_blind_review_and_public_aggregate_do_not_create_qualified_reward():
    root=Path(ROOT)/"smoke_review-v1"
    if not root.exists():pytest.skip("response review has not happened")
    reviews=[json.loads(l) for l in (root/"PAIRED_REVIEW.private.jsonl").read_text().splitlines()]
    summary=json.loads((root/"SUMMARY_PUBLIC.json").read_text())
    assert len(reviews)==12 and summary["qualified_rewards"]==0
    assert summary["qualified_semantic_success_rate"] is None
    assert summary["research_task_pending"]==12
    for row in reviews:
        assert row["qualified_reward"] is None
        assert row["finish_reason"]=="eos"
        for item in row["items"]:
            assert item["qualified_semantic_verdict"]=="uncertain"
            assert item["evidence_quote"]==row["response"][item["quote_start_char"]:item["quote_end_char"]]
    public=json.dumps(summary)
    assert all(row["response"] not in public for row in reviews)
    assert all(item["frozen_criterion"] not in public for row in reviews for item in row["items"])
    def inspect(value):
        if isinstance(value,dict):
            assert not {"response","visible_question","source_evidence","exact_quote","requirements","frozen_criterion"}&set(value)
            for child in value.values():inspect(child)
        elif isinstance(value,list):
            for child in value:inspect(child)
    inspect(summary)


@pytest.mark.skipif(not ROOT,reason="actual private artifacts not supplied")
def test_private_design_extraction_preserves_frozen_task_and_eval_bytes():
    root=Path(ROOT)
    replay=root/"complex12-public-code-replay"
    if not replay.exists():pytest.skip("public-code extraction replay absent")
    for name in ("TASKS.runtime.jsonl","EVALSPEC.private.jsonl","READABLE_TASKS.private.md","COVERAGE.json"):
        assert (root/"complex12-v1"/name).read_bytes()==(replay/name).read_bytes()
