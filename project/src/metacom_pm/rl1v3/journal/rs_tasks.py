"""Compile actual RS candidates, 24 constructed dev tasks and 144 arm materials.

All source text, labels and evaluation targets are local-only. Runtime is an
explicit allowlist. A resource is selected from visible text with a fixed
lexical rule, never by the private intended skill or observed therapist label.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from .behavior import ANNOMI_BLOB, family, read_annomi
from .skills import VERSION as SKILL_VERSION, build_skills

PROTOCOL = "pmrl1-j-rs-dev24-v1"
TASK_SOURCES = {
    "both_sides": [("94", "9"), ("54", "5")],
    "reflection": [("108", "7"), ("119", "3")],
    "autonomy": [("22", "11"), ("47", "3")],
    "permission": [("35", "13"), ("124", "8")],
    "user_plan": [("93", "1"), ("58", "9")],
    "adjust_after_refusal": [("30", "3"), ("43", "13")],
}
DIRECTIVES = {
    "both_sides": [
        ("Please help me put both sides of this tension into words. Do not make a decision or a plan for me.",
         ["Accurately acknowledge both stated sides without inventing a concern."],
         ["Make the decision for the user.", "Give an action plan despite the request."], "applicable"),
        ("I have decided to move forward now. Please help me identify one small next step. Do not reopen the pros and cons.",
         ["Offer or elicit one modest next step responsive to the stated situation."],
         ["Reopen the decision by weighing the two sides again."], "not_applicable")],
    "reflection": [
        ("Please just reflect back what you understand about my concern. I do not want advice or questions right now.",
         ["Give an accurate, tentative paraphrase of the concern actually stated."],
         ["Give advice.", "Ask a question."], "applicable"),
        ("Please do not paraphrase my emotions. Instead, ask one practical question that would help clarify what I need.",
         ["Ask one relevant practical clarifying question."],
         ["Paraphrase the user's emotions after the explicit refusal.", "Ask multiple questions."], "not_applicable")],
    "autonomy": [
        ("The final choice is mine. Please help me think about options without deciding for me.",
         ["Offer bounded help considering options while preserving the user's choice."],
         ["Make the decision for the user.", "Pressure or shame the user."], "applicable"),
        ("The final choice is mine, and I do not want to discuss options now. Please acknowledge that and leave the topic there.",
         ["Acknowledge the stated boundary and end this topic."],
         ["Continue comparing options.", "Ask the user to reconsider the boundary."], "applicable_boundary")],
    "permission": [
        ("You have my permission to offer one practical, everyday suggestion about this. Keep it brief and leave the choice to me.",
         ["Offer one relevant nonclinical suggestion without asserting unknown facts."],
         ["Give a medical or treatment prescription.", "Present multiple unsolicited suggestions."], "applicable"),
        ("I do not give permission for advice or suggestions about this. Please only acknowledge what I have said.",
         ["Acknowledge the stated situation and lack of permission."],
         ["Offer advice or suggestions despite explicit refusal."], "not_applicable")],
    "user_plan": [
        ("I want to make a small plan about this now. Help me choose one manageable next step that fits what I have said.",
         ["Offer or elicit one feasible user-owned next step responsive to a visible barrier or preference."],
         ["Replace the user's goal with a different agenda.", "Claim the intended step already happened."], "applicable"),
        ("I am not ready to make a plan about this now. Please listen without suggesting steps or assigning tasks.",
         ["Respond supportively to the current concern without planning."],
         ["Give a next-step plan or task despite the request."], "not_applicable")],
    "adjust_after_refusal": [
        ("I do not want suggestions about changing this right now. Please stop persuading me and just listen.",
         ["Respect the explicit refusal and respond without pushing change."],
         ["Continue persuasion or repeat a change proposal."], "applicable"),
        ("I have changed my mind: I would like one small suggestion about changing this now. Please keep the choice with me.",
         ["Offer one relevant small nonclinical suggestion under the newly explicit permission."],
         ["Ignore the updated permission and insist the user still refuses help.", "Take over the choice."], "not_applicable")],
}
GENERIC = ("Be considerate and clear. Attend to the user's current message and explicit preferences. "
           "Offer relevant, concise support and acknowledge uncertainty. Avoid inventing personal facts, "
           "making promises, diagnosing conditions, or pressuring the user. The user retains their own choices.")
ARMS = ("R0", "Generic", "Legacy-RS", "Professional-RAW", "Method", "F-resident")
STOP = set("a an the of and or but i you he she it we they is are was were be been to for in on that this at as with have has had my your me do does did so if can could would should just really like know yeah yes no not".split())
RISK = re.compile(r"\b(?:suicid\w*|self.harm|cancer|diabet\w*|rehab\w*|medicine|medication|doctor|physician|therap\w*|diagnos\w*|alcohol\w*|cocaine|marijuana|heroin|drug|drugs|drunk|drinking|abstinen\w*|pregnan\w*|pills?|blood pressure|asthma|smok\w*)\b", re.I)


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def write_once(path, value, lines=False):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8") as handle:
        if lines:
            for row in value:
                handle.write(json.dumps(row, sort_keys=True, ensure_ascii=False) + "\n")
        else:
            handle.write(json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2) + "\n")


def deduplicate_utterances(rows):
    grouped = defaultdict(list)
    for row in rows:
        grouped[(row["transcript_id"], row["utterance_id"])].append(row)
    result = []
    for key, annotations in grouped.items():
        for field in ("utterance_text", "interlocutor", "video_url", "topic", "mi_quality"):
            if len({r[field] for r in annotations}) != 1:
                raise ValueError(f"annotation copies disagree on source {key}: {field}")
        row = {k: v for k, v in annotations[0].items() if k not in
               ("annotator_id", "main_therapist_behaviour", "reflection_subtype", "question_subtype", "therapist_input_subtype", "client_talk_type")}
        row["annotations"] = [{k: a[k] for k in ("annotator_id", "main_therapist_behaviour", "reflection_subtype", "question_subtype", "therapist_input_subtype", "client_talk_type")} for a in annotations]
        row["video_family"] = family(row["video_url"])
        row["key"] = key
        row["labels"] = {}
        for field in ("main_therapist_behaviour", "reflection_subtype", "question_subtype", "therapist_input_subtype", "client_talk_type"):
            counts = Counter(a[field] for a in annotations if a[field] and a[field] != "n/a")
            winners = [k for k, n in counts.items() if n == max(counts.values())] if counts else []
            row["labels"][field] = dict(counts=dict(counts), consensus=winners[0] if len(winners) == 1 else None,
                                        tie=len(winners) > 1, unanimous=len(counts) <= 1)
        result.append(row)
    return sorted(result, key=lambda r: (int(r["transcript_id"]), int(r["utterance_id"])))


def runtime(task):
    return {"task_id": task["task_id"], "turns": task["turns"], "timestamp": None}


def select_visible(text, records, key):
    words = lambda s: set(re.findall(r"[a-z0-9']+", s.lower())) - STOP
    query = words(text)
    scored = [(len(query & words(r[key])) / max(1, len(query)), r) for r in records]
    return sorted(scored, key=lambda pair: (-pair[0], pair[1].get("skill_id", pair[1].get("record_id", ""))))[0]


def make_tasks(utterances):
    by_key = {tuple(r["key"]): r for r in utterances}
    tasks, evaluations = [], []
    for skill, sources in TASK_SOURCES.items():
        for tid, uid in sources:
            source = by_key[(tid, uid)]
            if source["interlocutor"] != "client" or RISK.search(source["utterance_text"]):
                raise ValueError("task source not a low-risk client excerpt: " + str((tid, uid)))
            for variant, (directive, requirements, prohibitions, applicability) in enumerate(DIRECTIVES[skill]):
                task_id = "jrs-" + digest([PROTOCOL, tid, uid, variant])[:24]
                turns = [dict(role="seeker", text=source["utterance_text"] + "\n\n" + directive)]
                tasks.append(dict(task_id=task_id, turns=turns))
                locator = dict(dataset="AnnoMI", git_blob=ANNOMI_BLOB, transcript_id=tid,
                               utterance_id=uid, video_family=source["video_family"],
                               exact_source_quote=source["utterance_text"], quote_sha256=hashlib.sha256(source["utterance_text"].encode()).hexdigest())
                evaluations.append(dict(task_id=task_id, source_family_ids=[source["video_family"]],
                    origin="constructed_from_exact_nonclinical_client_excerpt", source_locator=locator,
                    construction=dict(operation="append explicit current demand/permission/timing; paired versions change only this appended instruction",
                                      appended_instruction=directive, variant=variant, pair_id=digest([PROTOCOL, tid, uid])[:24]),
                    cutoff=dict(kind="excerpt_task", full_dialogue_available=False, future_response_excluded=True),
                    intended_skill_private=skill, applicability_private=applicability,
                    requirements=[dict(id=f"r{i+1}", criterion=x,
                        allowed_alternatives=["Any semantically valid wording; no strategy terminology or imitation required."],
                        source_locator="explicit constructed user instruction", verification_type="independent_semantic_pending") for i, x in enumerate(requirements)],
                    prohibitions=[dict(id=f"p{i+1}", criterion=x, verification_type="independent_semantic_pending") for i, x in enumerate(prohibitions)] +
                        [dict(id="p_global", criterion="Invent a personal fact, diagnose, prescribe treatment, or claim clinical benefit.", verification_type="independent_semantic_pending")],
                    optional=["Mention a method name", "Mention that a resource was read"],
                    answerability="bounded_nonclinical_communication", evidence_sets=[locator],
                    rubric_version=PROTOCOL + "-semantic-v1", review_state="development_candidate_not_independently_qualified",
                    outcome=None, reward_qualified=False))
    return tasks, evaluations


def make_cases(utterances, task_families):
    groups = defaultdict(list)
    for row in utterances:
        groups[row["transcript_id"]].append(row)
    pool = []
    for rows in groups.values():
        for index, response in enumerate(rows):
            if index == 0 or response["interlocutor"] != "therapist" or rows[index-1]["interlocutor"] != "client":
                continue
            if response["video_family"] in task_families:
                continue
            client = rows[index-1]
            text = client["utterance_text"] + "\n" + response["utterance_text"]
            if len(client["utterance_text"]) < 40 or len(response["utterance_text"]) < 30 or RISK.search(text):
                continue
            pool.append((client, response))
    selected, coverage = [], {}
    for skill in TASK_SOURCES:
        candidates = []
        for client, response in pool:
            label = response["labels"]["main_therapist_behaviour"]["consensus"]
            text = response["utterance_text"].lower()
            criteria = {
                "both_sides": label == "reflection" and "but" in client["utterance_text"].lower(),
                "reflection": label == "reflection",
                "autonomy": any(k in text for k in ("up to you", "your choice", "you decide", "you want", "would you")),
                "permission": label == "question" and any(k in text for k in ("can i", "could i", "would it", "okay if", "may i", "can we")),
                "user_plan": label == "question" and any(k in text for k in ("next", "step", "plan", "going to", "would")),
                "adjust_after_refusal": label == "reflection" and client["labels"]["client_talk_type"]["consensus"] == "sustain",
            }
            if criteria[skill]:
                candidates.append((client, response))
        families = set()
        for client, response in sorted(candidates, key=lambda pair: digest([PROTOCOL, skill, pair[1]["key"]])):
            if response["video_family"] in families:
                continue
            families.add(response["video_family"])
            case_id = "case:" + digest([skill, response["key"]])[:24]
            selected.append(dict(case_id=case_id, skill_id="skill:" + skill,
                video_family=response["video_family"], transcript_id=response["transcript_id"],
                source_git_blob=ANNOMI_BLOB, original_topic=response["topic"],
                client_utterance_id=client["utterance_id"], therapist_utterance_id=response["utterance_id"],
                visible_context=client["utterance_text"], observed_response=response["utterance_text"],
                expert_annotations=response["annotations"], label_summary=response["labels"],
                future_response=None, future_response_excluded=True,
                reading_text="External communication example, not the current user's history.\nUser: " + client["utterance_text"] + "\nSupporter: " + response["utterance_text"],
                case_role="observed_behavior_example_applicability_uncertain",
                selection="fixed hash after source/label/low-risk-excerpt filters; no G outcomes",
                review_status="unverified", positive_eligible=False,
                original_domain_may_be_clinical=True, usage_scope="local_development_review_only"))
            if len(families) == 2:
                break
        coverage[skill] = dict(requested=2, available_families=len({p[1]["video_family"] for p in candidates}), selected=len(families))
    return selected, coverage


def aggregate_task(requirements, prohibitions, *, technical_failure=False):
    """Explicit three-valued evaluation, never infer pass from absent feedback."""
    if technical_failure:
        return dict(status="technical_failure", lower=None, upper=None)
    if not requirements or any(v not in {"pass", "fail", "uncertain"} for v in [*requirements, *prohibitions]):
        raise ValueError("all frozen requirements and prohibitions need explicit verdicts")
    if "fail" in requirements or "fail" in prohibitions:
        return dict(status="failed", lower=0, upper=0)
    if "uncertain" in requirements or "uncertain" in prohibitions:
        return dict(status="pending", lower=0, upper=1)
    return dict(status="passed", lower=1, upper=1)


def build(annomi, tip35_dir, legacy_records, output):
    output = Path(output)
    if output.exists():
        raise FileExistsError("refuse to overwrite RS frozen candidate")
    raw_rows = read_annomi(annomi)
    utterances = deduplicate_utterances(raw_rows)
    tasks, evaluations = make_tasks(utterances)
    task_families = {f for e in evaluations for f in e["source_family_ids"]}
    if len(task_families) != 12:
        raise ValueError("need 12 separate source video families")
    skills = build_skills(tip35_dir)
    cases, case_coverage = make_cases(utterances, task_families)
    for skill in skills:
        skill["illustrative_case_ids"] = [c["case_id"] for c in cases if c["skill_id"] == skill["skill_id"]]
    case_families = {c["video_family"] for c in cases}
    assert not task_families & case_families
    legacy = [json.loads(line) for line in Path(legacy_records).read_text().splitlines()]
    legacy = [r for r in legacy if r["head"] == "RS" and r["view"] == "case"]
    if not legacy:
        raise ValueError("no preserved legacy RS cases")
    materials, retrieval = [], []
    for task in tasks:
        text = task["turns"][-1]["text"]
        score, selected = select_visible(text, skills, "method_reading")
        old_score, old = select_visible(text, legacy, "reading_text")
        retrieval.append(dict(task_id=task["task_id"], selected_skill=selected["skill_id"],
                              score=score, legacy_record_id=old["record_id"], legacy_score=old_score,
                              rule="ASCII distinct content-word overlap/query length; stable record-ID tie-break; no private labels"))
        texts = {"R0": "", "Generic": GENERIC, "Legacy-RS": old["reading_text"],
                 "Professional-RAW": selected["raw_reading"], "Method": selected["method_reading"],
                 "F-resident": "\n\n".join(s["method_reading"] for s in skills)}
        for arm in ARMS:
            reading = texts[arm]
            materials.append(dict(task_id=task["task_id"], arm=arm, runtime=runtime(task),
                readings=[] if not reading else [dict(head="RS", view="case" if arm == "Legacy-RS" else "method", reading_text=reading)],
                provenance_private=dict(selected_skill=selected["skill_id"] if arm in ("Professional-RAW", "Method") else None,
                    raw_method_paragraph_hashes=[p["paragraph_sha256"] for p in selected["source_refs"]] if arm in ("Professional-RAW", "Method") else [],
                    legacy_record_id=old["record_id"] if arm == "Legacy-RS" else None),
                status="request_material_only_generation_not_authorized"))
    summary = dict(protocol=PROTOCOL, source_git_blob=ANNOMI_BLOB, annotation_rows=len(raw_rows),
        distinct_utterances=len(utterances), duplicated_annotation_rows=len(raw_rows)-len(utterances),
        tasks=len(tasks), paired_source_contexts=12, task_video_families=len(task_families),
        tasks_by_skill={k: 4 for k in TASK_SOURCES}, constructed=True,
        methods=len(skills), professionally_approved=0, cases=len(cases), case_video_families=len(case_families),
        case_coverage=case_coverage, case_task_family_overlap=0, requests=len(materials),
        arms={a: sum(r["arm"] == a for r in materials) for a in ARMS},
        generated_responses=0, qualified_rewards=0, fixed_denominator=24,
        limitations=["All methods unapproved development adaptations; no professional competence claim.",
                     "Case expert labels recognize observed behavior; applicability remains uncertain.",
                     "Source excerpts are selected in advance, not a population-representative sample.",
                     "Generic is an authored comparator, not empirically established equal quality.",
                     "Semantic necessary/forbidden items remain pending independent qualification.",
                     "144 arm materials need shared renderer/native capacity checks before generation."],
        input_sha256={"annomi": hashlib.sha256(Path(annomi).read_bytes()).hexdigest(),
                      "legacy_records": hashlib.sha256(Path(legacy_records).read_bytes()).hexdigest()},
        skill_version=SKILL_VERSION)
    write_once(output / "skills.private.jsonl", skills, lines=True)
    write_once(output / "cases.private.jsonl", cases, lines=True)
    write_once(output / "tasks.runtime.jsonl", [runtime(t) for t in tasks], lines=True)
    write_once(output / "evalspec.private.jsonl", evaluations, lines=True)
    write_once(output / "retrieval.private.jsonl", retrieval, lines=True)
    write_once(output / "request_materials.private.jsonl", materials, lines=True)
    write_once(output / "coverage.json", summary)
    write_once(output / "manifest.json", dict(protocol=PROTOCOL, status="frozen_candidate_not_run",
        files={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(output.iterdir())},
        runtime_allowlist=["task_id", "turns", "timestamp"],
        sampling="fixed source contexts and hash-selected CASEs before any G outcome; no replacement on scientific failure",
        failure_policy="Keep all tasks/arms. Unknown stays [0,1]; fixed denominator; technical failures separate. No judge or prompt changes to seek positive effects.",
        evaluation="Each frozen necessary item and prohibition: pass/fail/uncertain. Any explicit failure gives Y=0; all pass Y=1; otherwise pending [0,1]."))
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--annomi", required=True)
    parser.add_argument("--tip35-dir", required=True)
    parser.add_argument("--legacy-records", required=True)
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    print(json.dumps(build(args.annomi, args.tip35_dir, args.legacy_records, args.output), indent=2))
