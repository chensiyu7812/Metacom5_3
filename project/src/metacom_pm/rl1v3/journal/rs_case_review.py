"""Bounded, pre-generation repair of source-case selection failures.

The first lexical selector confused matching words with demonstrated methods.
Preserve those candidates and record rejection/uncertainty. Replacement snippets
are exact source turns, remain unapproved, and do not enter the 144-arm pilot.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from .behavior import ANNOMI_BLOB, read_annomi
from .rs_tasks import deduplicate_utterances, digest, write_once

REPLACEMENTS = [
    ("both_sides", "23", "52", "negative_proxy_counterexample", "A reflection of anxiety is not, by itself, a reflection of two competing concerns. This does not mean the observed response was wrong."),
    ("both_sides", "21", "182", "negative_proxy_counterexample", "Reflects thinking about change but does not explicitly reflect both stated sides; not evidence for the intended method."),
    ("reflection", "23", "22", "behavior_example_applicability_unverified", "Tentatively reflects worry stated in the preceding user turn; no diagnosis is asserted in this excerpt."),
    ("reflection", "133", "202", "behavior_example_applicability_uncertain", "Tentative feeling reflection is observed; preceding excerpt alone does not establish the inferred sadness."),
    ("autonomy", "33", "48", "behavior_example_applicability_unverified", "Explicitly affirms the user's choice after the user rejects being lectured."),
    ("autonomy", "53", "24", "behavior_example_applicability_uncertain", "An open inquiry about the user's own educational options; no coercion appears, but autonomy cannot be certified from the behavior label."),
    ("permission", "6", "14", "behavior_example_applicability_unverified", "Asks permission to jointly map the agenda; does not provide clinical information in the excerpt."),
    ("permission", "111", "37", "behavior_example_applicability_unverified", "Asks permission before a suggestion. The original clinical suggestion and later response are excluded."),
    ("user_plan", "49", "130", "negative_proxy_counterexample", "Elicits a first step but asserts it will be easy without support in the excerpt; preserve as a bounded counterexample, not a recommended script."),
    ("user_plan", "71", "34", "behavior_example_applicability_uncertain", "Elicits the user's desired kind of work; a preliminary goal question rather than evidence of a complete action plan."),
    ("adjust_after_refusal", "33", "48", "behavior_example_applicability_unverified", "Responds to a refusal of lectures by affirming choice instead of repeating advice."),
    ("adjust_after_refusal", "34", "86", "behavior_example_applicability_uncertain", "Reflects difficulty after the user says not now; does not press the proposal, but cannot establish overall appropriateness."),
]

ADAPTATION_DELTAS = {
    "both_sides": "TIP35 deliberately reinforces change talk and orders it second. The nonclinical adaptation balances the user's two stated concerns and does not privilege change.",
    "reflection": "Retains tentative paraphrase and correction. Removes the clinical target and any inference of improved treatment outcomes.",
    "autonomy": "Retains choice and noncoercion. Adds explicit stopping at a user boundary and makes no clinical intervention claim.",
    "permission": "Retains permission and information exchange. Restricts information to everyday nonclinical competence and forbids unknown prices/services/medical facts.",
    "user_plan": "Retains collaborative planning around the user's concerns. Restricts the task to a small ordinary action and excludes treatment planning.",
    "adjust_after_refusal": "Retains changing direction/listening when discord occurs. Uses an explicit refusal as the observable condition and does not label sustain talk or disagreement as pathology.",
}


def review(annomi, candidates, output):
    candidates, output = Path(candidates), Path(output)
    if output.exists():
        raise FileExistsError("preserve prior review output")
    old_cases = [json.loads(l) for l in (candidates / "cases.private.jsonl").read_text().splitlines()]
    tasks = [json.loads(l) for l in (candidates / "evalspec.private.jsonl").read_text().splitlines()]
    task_families = {f for t in tasks for f in t["source_family_ids"]}
    rows = deduplicate_utterances(read_annomi(annomi))
    by_transcript = {}
    for row in rows:
        by_transcript.setdefault(row["transcript_id"], []).append(row)
    records = []
    for skill, tid, uid, role, rationale in REPLACEMENTS:
        transcript = by_transcript[tid]
        index = next(i for i, r in enumerate(transcript) if r["utterance_id"] == uid)
        response, context = transcript[index], transcript[index-1]
        assert response["interlocutor"] == "therapist" and context["interlocutor"] == "client"
        assert response["video_family"] not in task_families
        records.append(dict(case_id="case-v2:"+digest([skill,tid,uid])[:24], skill_id="skill:"+skill,
            source_git_blob=ANNOMI_BLOB, transcript_id=tid, therapist_utterance_id=uid,
            client_utterance_id=context["utterance_id"], video_family=response["video_family"],
            original_domain=response["topic"], original_domain_is_not_adapted_domain=True,
            visible_context=context["utterance_text"], observed_response=response["utterance_text"],
            expert_annotations=response["annotations"], label_summary=response["labels"],
            reading_text="External observed communication excerpt; not the current user's history and not a recommended script.\nUser: "+context["utterance_text"]+"\nSupporter: "+response["utterance_text"],
            case_role=role, review_note=rationale, review_status="unverified",
            review_performed="assistant_development_source_and_boundary_review_not_expert",
            low_risk_scope="only the quoted communication excerpt; no clinical goal or treatment recommendation is carried forward",
            positive_eligible=False, runtime_use=False,
            usage_scope="local_source_and_behavior_review_only", future_response_excluded=True))
    disposition = []
    for old in old_cases:
        tid, uid = old["transcript_id"], old["therapist_utterance_id"]
        if (tid, uid) in {("70", "8"), ("1", "12"), ("2", "8"), ("89", "36"), ("67", "24")}:
            reason = "clinical/substance-use content or unexplained clinical shorthand escaped the first lexical risk filter; excluded from low-risk candidates"
        elif (tid, uid) == ("38", "8"):
            reason = "sustain talk is not an explicit refusal; similar childcare scenario to a task source is conservatively excluded despite different video URLs"
        elif (tid, uid) == ("91", "62"):
            reason = "'would it take' is a confidence question, not permission; lexical cue gave a false method match"
        else:
            reason = "source label verifies an observed behavior only; retain with explicit applicability uncertainty/counterexample or replace after bounded review"
        disposition.append(dict(case_id=old["case_id"], disposition="preserved_not_runtime_eligible", reason=reason))
    write_once(output / "cases-v2.private.jsonl", records, lines=True)
    write_once(output / "v1-disposition.private.jsonl", disposition, lines=True)
    write_once(output / "raw_method_adaptation.json", dict(same_source=True, semantically_identical=False,
        comparison_name="original professional text versus nonclinical procedural adaptation",
        not_a_pure_compression_ablation=True, per_skill=ADAPTATION_DELTAS))
    write_once(output / "summary.json", dict(cases=len(records), per_skill={key:2 for key in ADAPTATION_DELTAS},
        unique_case_video_families=len({r["video_family"] for r in records}),
        case_task_family_overlap=0, positive_eligible=0, professionally_approved=0,
        negative_proxy_counterexamples=sum(r["case_role"]=="negative_proxy_counterexample" for r in records),
        clinical_goals_removed_from_readable_excerpt=True, future_responses_excluded=True,
        requested_case_generation_calls=0, original_144_requests_unchanged=True,
        limitation="These are readable source/behavior review candidates. Two snippets per skill are not two positive demonstrations; uncertain and counterexample roles stay explicit."))
    write_once(output / "manifest.json", dict(protocol="pmrl1-j-rs-case-root-cause-review-v2",
        parent_manifest_sha256=hashlib.sha256((candidates/"manifest.json").read_bytes()).hexdigest(),
        files={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())},
        repair_trigger="actual source/proxy errors found before generation; no response outcomes used"))
    return json.loads((output/"summary.json").read_text())


if __name__ == "__main__":
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annomi", required=True)
    parser.add_argument("--candidates", required=True)
    parser.add_argument("--output", required=True)
    args=parser.parse_args()
    print(json.dumps(review(args.annomi,args.candidates,args.output),indent=2))
