"""Development audit of the 20 pilot NeedCards (``pmrl1v3-b1-needcard-pilot-audit-v1``) and the
checklist-v3 freeze that may follow it.  Fixed before any card exists.

The audit is NOT "can the quote be located" (``cards.assemble`` already guarantees that): a reviewer
answers six questions per card (``CHECKS``) with yes / no / cannot_judge / not_applicable.  The card
verdict is then DERIVED by a fixed rule, never chosen freely:
  writer_failed   envelope status writer_failed (no card)
  evidence_error  any "no" on evidence / state / method / RS-label checks
  tier_error      otherwise any "no" on the required/optional checks
  cannot_judge    otherwise any cannot_judge
  valid           everything yes / not_applicable
A non-valid verdict needs a fix reason.  Only ``valid`` cards may get a checklist; a corrected card
would be a new reviewed NeedCard version (not part of this pilot).  RS-v0 ``method_need`` (and the RS
head need it implies) is never a gold label for GET_RS necessity.  The 20 pilot cards show small-scale
feasibility only; the formal B1 needs the original sampling and 40-card development audit.
"""
from __future__ import annotations

from ..io import object_sha256

AUDIT_PROTOCOL = "pmrl1v3-b1-needcard-pilot-audit-v1"
ANSWERS = ("yes", "no", "cannot_judge", "not_applicable")
CHECKS = dict(
    evidence_supports_claim="Every retained span says what its role claims (not merely locatable).",
    required_is_indispensable="Every required / must_not_contradict item is history the current reply cannot do without.",
    optional_not_mislabeled="No relevant_optional item should be required and no required item is merely optional.",
    state_not_confused="Corrections, refusals, attempts and completions are kept apart (tried-and-failed is not done, "
                       "a suggestion is not an action, a refusal is not an attempt, an outdated fact is marked as such).",
    method_need_supported="A non-null method_need is supported by the quoted CURRENT lines; null when no such request.",
    rs_label_not_validated_method="An RS-v0 label is used only as an unverified dialogue-act tag; 'unknown' when no label "
                                  "plainly fits; nothing treats it as a validated method.",
)
EVIDENCE_CHECKS = ("evidence_supports_claim", "state_not_confused", "method_need_supported", "rs_label_not_validated_method")
TIER_CHECKS = ("required_is_indispensable", "optional_not_mislabeled")
VERDICTS = ("valid", "evidence_error", "tier_error", "cannot_judge", "writer_failed")
EVIDENCE_ERROR_GATE = 0.10


def _span(s) -> dict:
    return dict(session_id=s.session_id, source_rank=s.source_rank, speaker=s.speaker, quote=s.exact_quote)


def prepare(envelopes) -> list[dict]:
    """One row per envelope: machine facts for the reviewer + blank answers."""
    rows = []
    for e in envelopes:
        row = dict(protocol=AUDIT_PROTOCOL, prefix_id=e["prefix_id"], status=e["status"],
                   needcard_sha256=e.get("needcard_sha256"), answers={k: None for k in CHECKS},
                   fix_reason=None, reviewer=None)
        if e["status"] == "ok":
            c = e["needcard"]
            row["facts"] = dict(
                derived_stratum=e["derived_stratum"], writer_claimed_stratum=e["writer_claimed_stratum"],
                stratum_conflict=e["stratum_conflict"], dropped=e["drops"], n_proposed=e["n_proposed"],
                history_items=[dict(role=h.role, spans=[_span(s) for s in h.spans]) for h in c.history_items],
                failed_or_rejected=[_span(s) for s in c.failed_or_rejected],
                outdated_facts=[dict(old=_span(o.old_span), new=_span(o.new_span)) for o in c.outdated_facts],
                method_need=c.method_need, method_evidence=[_span(s) for s in e["method_evidence"]],
                risk_flags=list(c.risk_flags), head_needs=e["head_needs"],
                rs_head_need_is_gold_for_get_rs=False)
        else:
            row["facts"] = dict(errors=e.get("errors", []))
            row["answers"] = {k: "not_applicable" for k in CHECKS}
        rows.append(row)
    return rows


def verdict(row: dict) -> str:
    if row["status"] == "writer_failed":
        return "writer_failed"
    a = row["answers"]
    if set(a) != set(CHECKS) or any(v not in ANSWERS for v in a.values()):
        raise ValueError(f"{row['prefix_id']}: every check needs one of {ANSWERS}")
    if any(a[k] == "no" for k in EVIDENCE_CHECKS):
        return "evidence_error"
    if any(a[k] == "no" for k in TIER_CHECKS):
        return "tier_error"
    if any(v == "cannot_judge" for v in a.values()):
        return "cannot_judge"
    return "valid"


def report(rows) -> dict:
    out = []
    for r in rows:
        v = verdict(r)
        if v not in ("valid", "writer_failed") and not r.get("fix_reason"):
            raise ValueError(f"{r['prefix_id']}: a {v} card needs a fix reason")
        if r["status"] == "ok" and not r.get("reviewer"):
            raise ValueError(f"{r['prefix_id']}: reviewer missing")
        out.append(dict(prefix_id=r["prefix_id"], needcard_sha256=r["needcard_sha256"], verdict=v,
                        answers=r["answers"], fix_reason=r.get("fix_reason"), reviewer=r.get("reviewer")))
    cards = [x for x in out if x["verdict"] != "writer_failed"]
    counts = {v: sum(x["verdict"] == v for x in out) for v in VERDICTS}
    rate = counts["evidence_error"] / len(cards) if cards else None
    per_check = {k: {a: sum(x["answers"][k] == a for x in cards) for a in ANSWERS} for k in CHECKS}
    rep = dict(protocol=AUDIT_PROTOCOL, cards=len(out), counts=counts, per_check=per_check,
               evidence_error_rate=rate, evidence_error_gate=EVIDENCE_ERROR_GATE,
               gate_passed=rate is not None and rate <= EVIDENCE_ERROR_GATE,
               checklist_eligible=sorted(x["prefix_id"] for x in out if x["verdict"] == "valid"),
               fix_reasons={x["prefix_id"]: x["fix_reason"] for x in out if x["fix_reason"]},
               rs_method_need_is_gold_for_get_rs=False,
               scope="small-scale generation feasibility only; formal B1 still needs its sampling and the 40-card audit",
               rows=out, evidence_tier="engineering_only")
    return dict(rep, sha256=object_sha256(rep))


def freeze_checklists(rep: dict, envelopes, ledger, build) -> dict:
    """Freeze one checklist (``build(needcard, method_evidence=...)``) per audited-valid card, before any
    candidate exists (``ChecklistLedger`` refuses otherwise).  Nothing else is frozen."""
    if not rep["gate_passed"]:
        raise ValueError("evidence error gate not passed; no checklist may be frozen")
    by = {e["prefix_id"]: e for e in envelopes}
    frozen = {}
    for pid in rep["checklist_eligible"]:
        e = by[pid]
        row = next(x for x in rep["rows"] if x["prefix_id"] == pid)
        if e["needcard_sha256"] != row["needcard_sha256"] or e["needcard"].sha256 != row["needcard_sha256"]:
            raise ValueError(f"{pid}: audited NeedCard differs from the envelope")
        cl = build(e["needcard"], method_evidence=tuple(e["method_evidence"]))
        ledger.freeze(cl, e["needcard"])
        frozen[pid] = dict(checklist_sha256=cl.sha256, writer_identity=cl.writer_identity, items=len(cl.items),
                           total_weight=cl.total_weight)
    return frozen
