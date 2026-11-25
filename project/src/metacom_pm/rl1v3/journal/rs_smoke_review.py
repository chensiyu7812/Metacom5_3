"""Validate a previously frozen blind development review and join its run key.

This does not judge responses or create rewards. It verifies evidence spans and
summarizes assistant observations separately from unqualified semantic verdicts.
Raw replies and private task criteria never enter the public aggregate.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import statistics

from .rs_tasks import write_once


def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def read_lines(path):return [json.loads(x) for x in Path(path).read_text().splitlines()]


def unblind(review_dir, blinded, key_path, paired_path, delivery_path, retrieval_path):
    directory=Path(review_dir)
    receipt=json.loads((directory/"BLIND_FREEZE_RECEIPT.json").read_text())
    review_path=directory/"BLIND_REVIEW_FROZEN.private.jsonl"
    if sha(review_path)!=receipt["blind_review_sha256"] or sha(blinded)!=receipt["blinded_input_sha256"]:
        raise ValueError("blind review/input changed after freeze")
    reviews=read_lines(review_path)
    source={r["case_id"]:r for r in read_lines(blinded)}
    keys={r["case_id"]:r for r in read_lines(key_path) if r["domain"]=="rs"}
    actual={r["request_id"]:r for r in read_lines(paired_path) if r["domain"]=="rs"}
    delivery={r["request_id"]:r for r in read_lines(delivery_path)}
    retrieval={r["task_id"]:r for r in read_lines(retrieval_path)}
    if len(reviews)!=12 or len(keys)!=12 or len(actual)!=12:raise ValueError("fixed 12-response denominator differs")
    combined=[]
    for review in reviews:
        case=review["case_id"];key=keys[case];response=source[case];run=actual[key["request_id"]]
        if not (review["task_id"]==key["task_id"]==run["task_id"]==response["task_id"]):raise ValueError("task join differs")
        if not (review["response_sha256"]==response["response_sha256"]==run["response_sha256"]==hashlib.sha256(run["response"].encode()).hexdigest()):raise ValueError("response identity differs")
        if response["response"]!=run["response"]:raise ValueError("blinded response text differs")
        if review["technical_status"]!=run["technical_status"] or run["finish_reason"]!="eos":
            raise ValueError("frozen returned-EOS review does not match actual technical status")
        for item in review["items"]:
            if item["evidence_quote"]!=run["response"][item["quote_start_char"]:item["quote_end_char"]]:raise ValueError("review evidence absent from response")
            if item["qualified_semantic_verdict"]!="uncertain":raise ValueError("development review cannot silently qualify semantics")
        for flag in review["auxiliary_flags"]:
            if flag["quote"]!=run["response"][flag["start_char"]:flag["end_char"]]:raise ValueError("flag quote mismatch")
        if run["reward"] is not None or review["qualified_reward"] is not None:raise ValueError("unqualified reward")
        supplied=delivery[key["request_id"]]
        if run["input_tokens"]!=supplied["input_tokens"]:raise ValueError("actual input token delivery mismatch")
        combined.append(dict(**review,arm=key["arm"],request_id=key["request_id"],
            response=run["response"],input_tokens=run["input_tokens"],output_tokens=run["output_tokens"],
            generation_seconds=run["generation_seconds"],finish_reason=run["finish_reason"],
            resource_tokens=supplied["resource_tokens"],marginal_input_tokens_vs_R0=supplied["marginal_input_tokens_vs_R0"],
            selected_skill_private=retrieval[review["task_id"]]["selected_skill"] if key["arm"] in ("Method","Professional-RAW") else None,
            delivery_selection=supplied["selection"]))
    by_task=defaultdict(list)
    for row in combined:by_task[row["task_id"]].append(row)
    expected={"R0","Generic","Legacy-RS","Professional-RAW","Method","F-resident"}
    if len(by_task)!=2 or any({r["arm"] for r in rows}!=expected or len(rows)!=6 for rows in by_task.values()):
        raise ValueError("incomplete task-by-arm comparison")
    by_arm={}
    for arm in sorted(expected):
        rows=[r for r in combined if r["arm"]==arm]
        by_arm[arm]=dict(responses=len(rows),technical_eos=sum(r["finish_reason"]=="eos" for r in rows),
            development_constraint_observations=dict(Counter(i["development_observation"] for r in rows for i in r["items"])),
            apparent_request_consistency=sum(r["applicable_to_visible_request_development_observation"]=="consistent_with_current_request" for r in rows),
            formal_semantic_pending=len(rows),qualified_reward_count=0,
            auxiliary_flags=dict(Counter(f["flag"] for r in rows for f in r["auxiliary_flags"])),
            input_tokens_total=sum(r["input_tokens"] for r in rows),output_tokens_total=sum(r["output_tokens"] for r in rows),
            resource_tokens_total=sum(r["resource_tokens"] for r in rows),
            marginal_input_tokens_vs_R0_total=sum(r["marginal_input_tokens_vs_R0"] for r in rows),
            generation_seconds_total=sum(r["generation_seconds"] for r in rows),
            generation_seconds_median=statistics.median(r["generation_seconds"] for r in rows))
    summary=dict(protocol="pmrl1-j-rs-smoke-development-observations-v1",tasks=2,responses=12,arms=6,
        fixed_denominator=12,technical_eos=sum(r["finish_reason"]=="eos" for r in combined),verified_response_hashes=12,verified_item_evidence_spans=48,
        generation_input_matches_frozen_native_tokens=12,by_arm=by_arm,
        raw_question_mark_count=sum(r["explicit_question_mark_count"] for r in combined),
        clear_apparent_frozen_constraint_violations=sum(i["development_observation"]=="clear_apparent_violation" for r in combined for i in r["items"]),
        qualified_semantic_success_rate=None,qualified_rewards=0,research_task_pending=12,research_task_mean_interval=[0,1],
        interpretation="All six arms visibly followed the two simple explicit user requests in this unqualified development review; no additional task-capability gain is established by this smoke batch. Auxiliary surface/scope flags are separate from the frozen semantic criteria.",
        limits=["Two development tasks and one deterministic response per arm cannot support broad efficacy or noninferiority claims.",
                "Same assistant authored resources/tasks and reviewed responses; arm strings were masked but evaluator independence/qualification is absent.",
                "No classifier accuracy is used as support quality or task reward.",
                "Actual generation wall time is a component measure, not end-to-end client latency.",
                "No scientific-failure resampling, prompt repair, judge replacement, or new generation occurred."],
        public_aggregate_contains_raw_source_or_reply_text=False)
    write_once(directory/"PAIRED_REVIEW.private.jsonl",combined,lines=True)
    write_once(directory/"SUMMARY_PUBLIC.json",summary)
    write_once(directory/"MANIFEST.json",dict(protocol=summary["protocol"],
        blind_freeze_receipt_sha256=sha(directory/"BLIND_FREEZE_RECEIPT.json"),
        input_sha256={str(p):sha(p) for p in [blinded,key_path,paired_path,delivery_path,retrieval_path]},
        output_sha256={name:sha(directory/name) for name in ["PAIRED_REVIEW.private.jsonl","SUMMARY_PUBLIC.json"]},
        new_model_calls=0,no_response_byte_changes=True))
    return summary


if __name__=="__main__":
    import argparse
    p=argparse.ArgumentParser(description=__doc__)
    for name in ("review-dir","blinded","key","paired","delivery","retrieval"):p.add_argument("--"+name,required=True)
    a=p.parse_args();print(json.dumps(unblind(a.review_dir,a.blinded,a.key,a.paired,a.delivery,a.retrieval),indent=2))
