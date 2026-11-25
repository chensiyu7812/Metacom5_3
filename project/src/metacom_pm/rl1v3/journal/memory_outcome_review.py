"""Verify a private, arm-blind development review; never assign formal reward.

Semantic judgments are authored outside this module after reading outputs and
sources. Exact quotes and source delivery are mechanically checked here. These
checks do not qualify the reviewer or turn word overlap into entailment.
"""
from __future__ import annotations

import hashlib
import html
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

PROTOCOL = "pmrl1-j-memory-blind-development-review-v1"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def rows(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line]


def write_once(path, value):
    with Path(path).open("x") as stream:
        stream.write(json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True) + "\n")


def exact_supplied_sessions(resources, sources):
    """Recover full source identity from the visible reports, without arm labels."""
    text = html.unescape("\n".join(resources))
    pattern = (r"Completed historical session; reported (\d{4}-\d{2}-\d{2}):\n"
               r"SOURCE_EXACT[^\n]*\n(.*?)(?=\n\nCompleted historical session; reported |</resource>)")
    sessions = []
    for match in re.finditer(pattern, text, re.S):
        date, body = match.groups()
        matches = []
        for (owner, sid), source in sources.items():
            rendered = "\n".join(f"{t['role']}: {t['content']}" for t in source["dialogue"])
            if source["timestamp"] == date and rendered == body.strip():
                matches.append((owner, sid))
        if len(matches) != 1:
            raise ValueError("supplied report cannot be uniquely bound to raw source")
        owner, sid = matches[0]
        sessions.append(dict(owner_id=owner, session_id=sid, reported_at=date))
    if text.count("Completed historical session; reported ") != len(sessions):
        raise ValueError("unparsed source report")
    return sessions


def validate_review(blind, audit, manual, raw):
    sources = {(u["id"], s["id"]): s for u in raw for s in u["dialog_history"]}
    cases = {r["case_id"]: r for r in blind}
    if len(cases) != len(blind) or set(cases) != set(manual["cases"]):
        raise ValueError("blind cases missing, duplicated, or added")
    audits = {r["task_id"]: r for r in audit}
    compiled = []
    for case_id, case in cases.items():
        decision = manual["cases"][case_id]
        if "arm" in decision or "arm" in case:
            raise ValueError("arm label forbidden in blind stage")
        if decision["formal_status"] != "uncertain" or decision["reward"] is not None:
            raise ValueError("unqualified semantic review cannot produce formal reward")
        response = case["response"]
        if hashlib.sha256(response.encode()).hexdigest() != case["response_sha256"]:
            raise ValueError("response digest mismatch")
        task = audits[case["task_id"]]
        if task["question"] != case["visible_question"]:
            raise ValueError("original question changed")
        sessions = exact_supplied_sessions(case["supplied_resources"], sources)
        if any(s["owner_id"] != task["owner_id"] for s in sessions):
            raise ValueError("wrong-owner source")
        delivered = {s["session_id"] for s in sessions}
        cutoff = task["explicit_time"]["upper"]
        future = [s["session_id"] for s in sessions if cutoff and s["reported_at"] > cutoff]
        legal = delivered - set(future)
        required = {a["atom_id"]: a for a in task["atoms"] if a.get("required", True)}
        judgments = {a["atom_id"]: a for a in decision["atoms"]}
        if len(judgments) != len(decision["atoms"]) or set(judgments) != set(required):
            raise ValueError("frozen necessary atom set changed")
        bound_atoms = []
        for atom_id, atom in required.items():
            judgment = judgments[atom_id]
            if judgment["observed"] not in {"complete", "underspecified", "missing", "abstained"}:
                raise ValueError("unknown development judgment")
            for quote in judgment["output_quotes"]:
                if not quote or quote not in response:
                    raise ValueError("atom output quote is not exact")
            groups = atom["sufficient_source_groups"]
            supply = lambda ids: bool(groups) and any(all(ref.rsplit(":", 1)[0] in ids for ref in g) for g in groups)
            bound_atoms.append(dict(**judgment, necessary=True, source_evidence=atom["source_evidence"],
                                    supplied_reviewed_support=supply(delivered), strict_supplied_reviewed_support=supply(legal)))
        claims = []
        for claim in decision["claims"]:
            if not claim["output_quote"] or claim["output_quote"] not in response:
                raise ValueError("claim output quote is not exact")
            evidence = []
            for ref in claim["source_refs"]:
                sid, idx = ref.rsplit(":", 1)
                source = sources[(task["owner_id"], sid)]
                turns = [t for t in source["dialogue"] if str(t["idx"]) == idx]
                if len(turns) != 1 or sid not in delivered:
                    raise ValueError("claim source absent from supplied input")
                turn = turns[0]
                evidence.append(dict(source_ref=ref, speaker=turn["role"], exact_quote=turn["content"],
                                     reported_at=source["timestamp"], strict_legal=sid in legal))
            claims.append(dict(**claim, evidence=evidence))
        compiled.append(dict(protocol=PROTOCOL, case_id=case_id, task_id=case["task_id"],
                             response=response, response_sha256=case["response_sha256"],
                             question=case["visible_question"], gold=task["gold"],
                             explicit_time=task["explicit_time"], supplied_sessions=sessions,
                             strict_future_sessions=future, **{k: v for k, v in decision.items() if k not in {"atoms", "claims"}},
                             atoms=bound_atoms, claims=claims,
                             completed_necessary_atoms=sum(a["observed"] == "complete" for a in bound_atoms),
                             necessary_atoms=len(bound_atoms),
                             legal_supported_completed_atoms=sum(a["observed"] == "complete" and a["strict_supplied_reviewed_support"] for a in bound_atoms)))
    return compiled


def freeze(blind_path, audit_path, manual_path, raw_path, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    audits = rows(audit_path)
    if any(r["source_sha256"] != sha(raw_path) for r in audits):
        raise ValueError("raw source does not match frozen audit")
    data = validate_review(rows(blind_path), audits, json.loads(Path(manual_path).read_text()), json.loads(Path(raw_path).read_text()))
    write_once(output / "BLIND_REVIEW_PRIVATE.json", data)
    inputs = {str(Path(p).resolve()): sha(p) for p in (blind_path, audit_path, manual_path, raw_path, __file__)}
    receipt = dict(protocol=PROTOCOL, frozen_at_utc=datetime.now(timezone.utc).isoformat(),
                   stage="blind_before_key_access", arm_key_accessed=False, reviewer="same-model assistant as evidence audit; not independent human; not qualified official scorer",
                   inputs_sha256=inputs, review_sha256=sha(output / "BLIND_REVIEW_PRIVATE.json"), cases=len(data),
                   formal_status="uncertain", reward=None)
    write_once(output / "BLIND_FREEZE_MANIFEST.json", receipt)
    return receipt


def join_key(output, key_path):
    """Only call after inspecting the blind-freeze receipt; preserve blind bytes."""
    output = Path(output)
    receipt = json.loads((output / "BLIND_FREEZE_MANIFEST.json").read_text())
    if receipt["stage"] != "blind_before_key_access" or sha(output / "BLIND_REVIEW_PRIVATE.json") != receipt["review_sha256"]:
        raise ValueError("blind freeze missing or changed")
    for name, digest in receipt["inputs_sha256"].items():
        if sha(name) != digest:
            raise ValueError("frozen input changed")
    keys = {r["case_id"]: r for r in rows(key_path)}
    reviewed = json.loads((output / "BLIND_REVIEW_PRIVATE.json").read_text())
    if not {r["case_id"] for r in reviewed} <= keys.keys():
        raise ValueError("key missing reviewed case")
    joined = []
    for r in reviewed:
        key = keys[r["case_id"]]
        if key.get("task_id", r["task_id"]) != r["task_id"]:
            raise ValueError("key task mismatch")
        joined.append(dict(**r, arm=key["arm"]))
    pairs = [(r["task_id"], r["arm"]) for r in joined]
    if len(set(pairs)) != len(pairs):
        raise ValueError("duplicate task arm")
    arm_sets = [{r["arm"] for r in joined if r["task_id"] == t} for t in {r["task_id"] for r in joined}]
    if any(len(arms) != 4 or arms != arm_sets[0] for arms in arm_sets):
        raise ValueError("incomplete four-arm task comparison")
    write_once(output / "JOINED_REVIEW_PRIVATE.json", joined)
    public = []
    for r in sorted(joined, key=lambda r: (r["task_id"], r["arm"])):
        public.append({k: r[k] for k in ("case_id", "task_id", "arm", "completed_necessary_atoms", "necessary_atoms", "legal_supported_completed_atoms", "official_gold_development", "strict_answer_development", "strict_pipeline_development", "failure_attribution", "formal_status", "reward")})
    aggregate = dict(protocol=PROTOCOL, source_review_qualification=receipt["reviewer"], cases=len(public), tasks=len({r["task_id"] for r in public}),
                     atom_completions=sum(r["completed_necessary_atoms"] for r in public), necessary_atom_presentations=sum(r["necessary_atoms"] for r in public),
                     legal_supported_atom_completions=sum(r["legal_supported_completed_atoms"] for r in public),
                     official_gold_development_counts=dict(Counter(r["official_gold_development"] for r in public)),
                     strict_answer_development_counts=dict(Counter(r["strict_answer_development"] for r in public)),
                     strict_input_future_source_cases=sum(bool(r["strict_future_sessions"]) for r in joined),
                     response_future_claim_cases=sum(r["late_date_assertion_observed"] for r in joined),
                     formal_status="uncertain", reward=None, table=public,
                     interpretation="Descriptive source-bound development observations only; two preselected tasks, one owner, no efficacy estimate or formal semantic reward.")
    write_once(output / "PUBLIC_AGGREGATE.json", aggregate)
    write_once(output / "JOIN_MANIFEST.json", dict(blind_manifest_sha256=sha(output / "BLIND_FREEZE_MANIFEST.json"), key_sha256=sha(key_path),
                                                  joined_sha256=sha(output / "JOINED_REVIEW_PRIVATE.json"), aggregate_sha256=sha(output / "PUBLIC_AGGREGATE.json"),
                                                  joined_at_utc=datetime.now(timezone.utc).isoformat()))
    return aggregate
