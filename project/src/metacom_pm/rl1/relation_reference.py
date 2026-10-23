"""Bounded reference-information diagnostic; no model/credential access on import.

This adapts the existing paired.run engine, strict scorer, outer wrapper and
ledger. It neither changes training caches nor manufactures reference labels.
"""
from copy import deepcopy
from decimal import Decimal
import hashlib
import json
from pathlib import Path

from .schema import digest
from .evidence import evidence_turns
from .judge_indexed import response_units

VERSION = "pmrl1-relation-reference-v1-20261021"
INTERFACE = "partial-relation-reference-v1-20261021"
POLICY = dict(semantic_error="record_continue", reviewer_ambiguity="record_continue",
              model_unknown="missing_continue", technical_failure="stop_stage",
              identity_source_or_service_failure="stop_stage", unknown_usage="stop_stage",
              insufficient_liability_budget="stop_stage", retries=0, reward_eligible=False)
USE_CONTRACT = (
    "This is partial reference information for this reply, not a new source or a score target. "
    "Researcher-confirmed interpretations, exact source quotations and analyst-proposed "
    "relationships are distinguished explicitly. Do not treat analyst drafts as independent "
    "gold. Check the full original reply and all legal sources, including claims omitted "
    "from this partial table. You may correct or reject a reference with an explanation "
    "in the existing public reason fields. Cite only original legal source IDs. Preserve "
    "documented alternative readings. Absence of support is not proof of nonoccurrence; "
    "a source relationship alone does not determine severity or quality. Use the unchanged "
    "scoring rubric and final schema; do not add output fields."
)
CLAIM_FIELDS = {"claim_id", "response_unit_id", "response_quote", "claim_type", "claim",
                "subject", "action", "action_stage", "time", "relation", "source_checks",
                "researcher_confirmed_parts", "analyst_interpretation", "limitations"}
SOURCE_FIELDS = {"source_id", "quote", "source_type", "speaker", "evidence_scope",
                 "scope_status"}
REFERENCE_FIELDS = {"interface_version", "reply_text_sha256", "evidence_identity", "claims",
                    "coverage", "independent_gold", "verification_scope"}


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read(path):
    # Frozen preparation JSON also rejects duplicate keys.
    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise ValueError("duplicate JSON key")
            out[key] = value
        return out
    return json.loads(Path(path).read_text(), object_pairs_hook=unique)


def save_new(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("x") as f:
        f.write(value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)+"\n")
    path.chmod(0o600)


def validate_reference(item, ref, paired):
    if set(ref) != REFERENCE_FIELDS or ref["interface_version"] != INTERFACE:
        raise ValueError("reference fields/version mismatch")
    if (ref["reply_text_sha256"] != hashlib.sha256(item["reply"].encode()).hexdigest()
            or ref["evidence_identity"] != digest(item["evidence"]) or ref["independent_gold"] is not False):
        raise ValueError("reference binding or gold status mismatch")
    turns = evidence_turns(item["evidence"])
    projected = []
    for c in ref["claims"]:
        if set(c) != CLAIM_FIELDS:
            raise ValueError("reference claim allowlist; no scores or preferences")
        if not all(isinstance(c[k], str) and c[k] for k in ("claim", "action", "analyst_interpretation", "limitations")):
            raise ValueError("explicit claim, action and provenance limitations required")
        if not isinstance(c["researcher_confirmed_parts"], list):
            raise ValueError("researcher statements must be explicit partial interpretations")
        evidence = []
        for e in c["source_checks"]:
            if set(e) != SOURCE_FIELDS or e["source_id"] not in turns:
                raise ValueError("source field/ID allowlist")
            t = turns[e["source_id"]]
            if e["quote"] not in t["text"] or not e["quote"] or e["speaker"] != t["role"]:
                raise ValueError("source quote/speaker mismatch")
            if e["source_type"] != ("current" if e["source_id"].startswith("C:") else "legal_history"):
                raise ValueError("source type mismatch")
            if e["scope_status"] != "analyst_proposed_relation_not_independent_gold":
                raise ValueError("cannot self-certify a semantic relationship")
            evidence.append({k:e[k] for k in ("source_id", "quote")})
        projected.append({k:c[k] for k in ("claim_id", "response_unit_id", "response_quote", "claim_type",
                                           "subject", "time", "action_stage", "relation")} |
                         dict(evidence=evidence, reason=c["analyst_interpretation"]))
    uncertain = any(c["relation"] == "uncertain" for c in projected)
    # Reuse old relation-table schema and exact quote/response-unit checks.
    paired.validate_extract(dict(status="uncertain" if uncertain else "checked", claims=projected,
        coverage=ref["coverage"], uncertainty_reasons=["Reference explicitly retains ambiguity"] if uncertain else []), item)


def make_payload(item, ref, arm, prompt, paired):
    if arm not in ("A", "B"):
        raise ValueError("unknown arm")
    messages, schema = paired.payload(item, "joint")
    messages[0]["content"] = prompt
    if arm == "B":
        validate_reference(item, ref, paired)
        # The frozen transport permits system+user only. Reuse that interface:
        # append explicitly delimited reference DATA to the system message,
        # keep the complete original user/evidence bytes unchanged. This is a
        # versioned B input intervention, NOT a claim of identical full prompts.
        messages[0]["content"] += "\n\nPARTIAL_RELATION_REFERENCE_V1_DATA\n" + json.dumps(dict(
            reference_use_contract=USE_CONTRACT, relation_reference=ref), ensure_ascii=False)
    return dict(messages=messages, schema=schema)


def validate_payload(item, ref, arm, prompt, data, paired):
    if data != make_payload(item, ref, arm, prompt, paired):
        raise ValueError("full outbound message/schema mismatch")
    # Validate ALL messages, extending the old runner's second-message check.
    if len(data["messages"]) != 2:
        raise ValueError("extra outbound message")
    if arm == "B":
        extra = json.loads(data["messages"][0]["content"].split("\n\nPARTIAL_RELATION_REFERENCE_V1_DATA\n",1)[1])
        if set(extra) != {"reference_use_contract", "relation_reference"}:
            raise ValueError("reference outbound allowlist")
    return paired.input_guard(data["messages"])


def schedule(items, order, repeats):
    rows = []
    for index, (key, repetition) in enumerate([(k, 1) for k in order] + [(k, 2) for k in repeats]):
        original_index = order.index(key)
        arms = ("A", "B") if original_index % 2 == 0 else ("B", "A")
        if repetition == 2:
            arms = arms[::-1]
        for arm in arms:
            logical = dict(study=VERSION, item=key, arm=arm, repetition=repetition)
            rows.append(dict(position=len(rows)+1, slot_id=digest(logical),
                logical_slot=logical, item_key=key+"__"+arm, material_id=key, arm=arm,
                repetition=repetition, component="joint", reply_identity=digest(items[key]["reply"]),
                evidence_identity=digest(items[key]["evidence"])))
    return rows


def check_stop(protocol, starts, results):
    for slot in protocol["schedule"]:
        sid = slot["slot_id"]
        if sid not in starts:
            continue
        row = results.get(sid)
        if row is None:
            return "started request unresolved; no retry", 0, {}
        if row.get("hard_stop"):
            return row["hard_stop"], 0, {}
        if not row["financial"]["settlement_confirmed"]:
            return "usage/responsibility unknown; reservation retained", 0, {}
        if not row["technical_valid"]:
            return "technical or integrity failure; no retry", 0, {}
        # Model unknown and semantic outcomes are measured results in this
        # diagnostic. Neither can authorize training or erase an old STOP.
    return None, 0, {}


def require_approval(protocol, approval, reference_review):
    expected = protocol["approval_required"]
    if (approval.get("status") != "APPROVED" or approval.get("protocol_identity") != protocol["identity"]
            or any(approval.get(k) != v for k,v in expected.items())
            or not approval.get("researcher_authorization_record")):
        raise ValueError("explicit new execution/outbound/budget approval required")
    if (reference_review.get("status") != "RESEARCHER_REVIEW_COMPLETED"
            or reference_review.get("reference_bundle_sha256") != protocol["reference_bundle_sha256"]
            or reference_review.get("independent_second_rater") is not False
            or reference_review.get("decisions") != {k:"accepted_for_bounded_diagnostic"
                                                     for k in protocol["reference_review_groups"]}
            or not reference_review.get("actual_researcher_record")):
        raise ValueError("bounded reference review pending; never fabricate acceptance")
    if approval.get("reference_review_identity") != digest(reference_review):
        raise ValueError("approval/reference-review mismatch")


def summarize(protocol, root, baseline, paired):
    starts, results = paired.replay(root, protocol)
    stop = read(Path(root)/"STOP.json") if (Path(root)/"STOP.json").exists() else None
    slots = []
    for slot in protocol["schedule"]:
        r = results.get(slot["slot_id"])
        state = ("model_unknown" if r and r["technical_valid"] and r["evaluation"].get("model_unknown")
                 else "completed" if r and r["technical_valid"] else "failed" if r
                 else "started_unresolved" if slot["slot_id"] in starts else "not_dispatched")
        review_path=Path(root)/"reviews"/(slot["slot_id"]+".json")
        review=None
        if review_path.exists():
            if r is None:raise ValueError("orphan semantic review")
            review=read(review_path)
            item=read(protocol["input_file"])[slot["material_id"]]
            validate_review(review, slot, r, Path(root)/(slot["slot_id"]+".result.json"), item, protocol)
        slots.append(dict(**slot, state=state, result=r, semantic_review=review,
            not_dispatched_reason=(stop["reason"] if stop else "not authorized or not yet dispatched") if state=="not_dispatched" else None))
    comparisons = []
    for pair in protocol["resource_pairs"]:
        for arm in ("A", "B"):
            off_draws = sorted({s["repetition"] for s in slots if s["material_id"] == pair["off"]})
            for draw in off_draws:
                off = next(s for s in slots if s["material_id"]==pair["off"] and s["arm"]==arm and s["repetition"]==draw)
                on = next(s for s in slots if s["material_id"]==pair["on"] and s["arm"]==arm and s["repetition"]==1)
                comparable = off["state"]==on["state"]=="completed"
                delta = (on["result"]["evaluation"]["U"]-off["result"]["evaluation"]["U"]) if comparable else None
                comparisons.append(dict(pair_id=pair["id"], arm=arm, off_draw=draw, on_draw=1,
                    off_slot=off["slot_id"], on_slot=on["slot_id"], shared_on=draw>1,
                    comparable=comparable, delta_U=delta,
                    net_reward=delta-pair["resource_tokens"]/40960 if comparable else None,
                    direction_correctness=None, independent_pair_count=1,
                    missing_reason=None if comparable else "missing/failed/model-unknown endpoint"))
    usage=[r["usage"] for r in results.values() if isinstance(r.get("usage"),dict)]
    reviewed=[s for s in slots if s["semantic_review"]]
    counts=dict(reviewed_results=len(reviewed), unreviewed_results=len(results)-len(reviewed),
        confirmed_error_records=sum(any(f["kind"] in ("confirmed_checking_error","new_false_accusation","new_omission")
            for f in s["semantic_review"]["findings"]) for s in reviewed),
        reviewer_ambiguity_records=sum(any(f["kind"]=="reviewer_ambiguity" for f in s["semantic_review"]["findings"]) for s in reviewed),
        reference_uptake={k:sum(s["semantic_review"]["reference_uptake"]==k for s in reviewed)
            for k in ("not_applicable_A","accurate","misread","ignored","rejected_with_source_reason","unclear")},
        not_accuracy=True, independent_human_reviews=0)
    return dict(study=VERSION, planned=len(slots), started=len(starts), cumulative=baseline+len(starts),
        slots=slots, resource_comparisons=comparisons, stop=stop,
        distinct_replies=protocol["statistics"]["distinct_replies"], statistics=protocol["statistics"],
        technical_delivered=sum(r["technical_valid"] for r in results.values()),
        model_unknown=sum(r["evaluation"].get("model_unknown") is True for r in results.values()),
        numerical_scored=sum(s["state"]=="completed" for s in slots),
        semantic_counts=counts if reviewed else None, semantic_status="requires_bound_source_review_not_imputed",
        prompt_tokens=sum(u.get("prompt_tokens") or 0 for u in usage),
        output_tokens_including_thinking=sum(u.get("completion_tokens") or 0 for u in usage),
        elapsed_seconds=sum(r["elapsed_seconds"] for r in results.values()),
        accounted_usd=str(sum((Decimal(r["financial"]["accounted_upper_usd"] or "0") for r in results.values()),Decimal(0))),
        result_liability_usd=str(sum((Decimal(r["financial"]["unsettled_reservation_usd"]) for r in results.values()),Decimal(0))
                                +Decimal(".786432")*(len(starts)-len(results))),
        authoritative_liability_source="shared ledger including any reserved-before-start orphan",
        reward_eligible=False, natural_updates=0)


def validate_review(review, slot, result, result_path, item, protocol):
    """Bind postrun analyst findings to exact final/source bytes, never gold."""
    if (review.get("status")!="ANALYST_REVIEW" or review.get("independent_human_reference") is not False
            or review.get("slot_id")!=slot["slot_id"] or review.get("result_sha256")!=sha(result_path)
            or review.get("reference_bundle_sha256")!=protocol["reference_bundle_sha256"]):
        raise ValueError("semantic review identity/independence mismatch")
    uptake=review.get("reference_uptake")
    if uptake not in (("not_applicable_A",) if slot["arm"]=="A" else ("accurate","misread","ignored","rejected_with_source_reason","unclear")):
        raise ValueError("reference uptake needs an arm-appropriate explicit finding")
    if review.get("target_relationship") not in ("correct","incorrect","ambiguous","unclear") or review.get("score_basis") not in ("supported","incorrect","unresolved","not_evaluable"):
        raise ValueError("separate relationship and scoring findings required")
    def strings(v):
        if isinstance(v,str):return [v]
        if isinstance(v,dict):return [s for vv in v.values() for s in strings(vv)]
        if isinstance(v,list):return [s for vv in v for s in strings(vv)]
        return []
    final_strings=strings(result["evaluation"].get("value"))
    quotes=review.get("public_final_quotes")
    if not isinstance(quotes,list) or not quotes or any(not q or not any(q in t for t in final_strings) for q in quotes):
        raise ValueError("review must quote the completed public final, never thinking")
    turns=evidence_turns(item["evidence"])
    if not isinstance(review.get("findings"),list):raise ValueError("explicit findings list required")
    for f in review["findings"]:
        if (f.get("kind") not in ("confirmed_checking_error","new_false_accusation","new_omission","reviewer_ambiguity")
                or not f.get("claim") or not f.get("criterion") or not f.get("reason") or not f.get("source_checks")):
            raise ValueError("source/criterion proof required; adjacent q is not an error")
        for e in f["source_checks"]:
            if e.get("source_id") not in turns or not e.get("quote") or e["quote"] not in turns[e["source_id"]]["text"]:
                raise ValueError("review source quotation invalid")


def runtime(protocol, payloads, items, refs, prompt, paired, authorize):
    def payload(item, component, first=None):
        if component != "joint" or first is not None:
            raise ValueError("single joint score per arm; no automatic extraction")
        data = payloads[item["material_id"]+"__"+item["arm"]]
        validate_payload(item, refs[item["material_id"]], item["arm"], prompt, data, paired)
        rt["joint_prompt_unchanged"] = item["arm"] == "A"
        return deepcopy(data["messages"]), deepcopy(data["schema"])
    rt = dict(max_calls=protocol["limits"]["max_calls"], cap=protocol["limits"]["cumulative_cap"],
        study=VERSION, version=VERSION, approve=authorize, payload=payload,
        streaks=check_stop, summarize=lambda p,r,b:summarize(p,r,b,paired), review=None,
        semantic_revisions_applied=2, joint_prompt_unchanged=True)
    return rt
