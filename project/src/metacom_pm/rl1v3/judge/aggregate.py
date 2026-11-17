"""Combine J1/J2/human results into C0 ``ItemVerdict``s and ``TerminalRecord``s.

Status channels are kept apart (never merged into one number):
  not run (judge absent) | pending (J2 or final missing) | uncertain |
  factual error (hard_factual fail) | safety problem (hard_safety fail).
``final`` is set only when both judges ran (agreement, else ``uncertain``) or a
human adjudicated; a single judge leaves the item pending, so C0
``gsc_interval`` returns ``(None, None)`` - pending is never scored as 0.
"""
from __future__ import annotations

from typing import Mapping

from ..io import sha256_text
from .protocol import JudgeRun


def item_verdicts(checklist, j1: JudgeRun | None, j2: JudgeRun | None,
                  human: Mapping[str, object] | None = None) -> tuple:
    from .. import contracts as K
    human = dict(human or {})
    if set(human) - {i.item_id for i in checklist.items}:
        raise ValueError("adjudication for an item outside the frozen checklist")
    out = []
    for item in checklist.items:
        a = j1.items[item.item_id] if j1 else None
        b = j2.items[item.item_id] if j2 else None
        adj = human.get(item.item_id)
        if adj is not None:
            final = adj.verdict
        elif a is not None and b is not None:
            final = a.verdict if a.verdict == b.verdict else "uncertain"
        else:
            final = None
        out.append(K.ItemVerdict(
            item_id=item.item_id, J1=a.verdict if a else None, J2=b.verdict if b else None, final=final,
            J1_quote=a.quote if a else None, J1_source_span=a.span if a else None,
            J2_quote=b.quote if b else None, J2_source_span=b.span if b else None,
            human_adjudication=adj))
    return tuple(out)


def hard_status(checklist, verdicts, constraint: str, *, field: str = "final") -> str | None:
    """fail if any item fails; None if any item has no decision; uncertain/pass otherwise."""
    by = {v.item_id: getattr(v, field) for v in verdicts}
    vals = [by[i.item_id] for i in checklist.items if i.constraint_type == constraint]
    if not vals:
        return "pass"
    if "fail" in vals:
        return "fail"
    if any(v is None for v in vals):
        return None
    return "uncertain" if "uncertain" in vals else "pass"


def status_summary(checklist, verdicts, j1: JudgeRun | None = None, j2: JudgeRun | None = None) -> dict:
    W = sum(i.weight for i in checklist.items)
    by = {v.item_id: v for v in verdicts}

    def weight(pred):
        return sum(i.weight for i in checklist.items if pred(i, by[i.item_id])) / W

    flags = lambda jr: sorted({f for x in (jr.items.values() if jr else ()) for f in x.flags})
    return dict(
        J1_run=j1 is not None, J2_run=j2 is not None,
        pending_items=sum(v.pending for v in verdicts),
        final_uncertain_weight=weight(lambda i, v: v.final == "uncertain"),
        J1_uncertain_weight=weight(lambda i, v: v.J1 == "uncertain"),
        J1_parse_fallback_items=sum(1 for x in (j1.items.values() if j1 else ()) if
                                    {"parse_failed", "missing_after_retry"} & set(x.flags)),
        factual_fail_items_final=sum(1 for i in checklist.items if i.constraint_type == "hard_factual" and by[i.item_id].final == "fail"),
        factual_fail_items_J1=sum(1 for i in checklist.items if i.constraint_type == "hard_factual" and by[i.item_id].J1 == "fail"),
        safety_fail_items_final=sum(1 for i in checklist.items if i.constraint_type == "hard_safety" and by[i.item_id].final == "fail"),
        safety_fail_items_J1=sum(1 for i in checklist.items if i.constraint_type == "hard_safety" and by[i.item_id].J1 == "fail"),
        human_adjudicated=sum(v.human_adjudication is not None for v in verdicts),
        hard_factual=hard_status(checklist, verdicts, "hard_factual"),
        hard_safety=hard_status(checklist, verdicts, "hard_safety"),
        J1_flags=flags(j1), J2_flags=flags(j2))


def terminal_record(*, key, trace, checklist, feedback_id: str, request_sha256: str, response: str,
                    verdicts, evidence_validation: str = "pending", misuse_flags=(),
                    soft_quality_pairwise=(), latency_pred=None, latency_measured=None,
                    qualification_tier: str = "engineering_only"):
    """GSC and hard constraints come only from final verdicts; C0 re-validates everything."""
    from .. import contracts as K
    lo, hi = K.gsc_interval(checklist, verdicts)
    return K.TerminalRecord(
        key=key, execution=trace, checklist=checklist, checklist_sha256=checklist.sha256,
        feedback_id=feedback_id, evidence_validation=evidence_validation, request_sha256=request_sha256,
        response=response, response_sha256=sha256_text(response), item_verdicts=tuple(verdicts),
        gsc_lower=lo, gsc_upper=hi, hard_factual=hard_status(checklist, verdicts, "hard_factual"),
        hard_safety=hard_status(checklist, verdicts, "hard_safety"),
        soft_quality_pairwise=tuple(soft_quality_pairwise), qualification_tier=qualification_tier,
        misuse_flags=tuple(misuse_flags), latency_pred=latency_pred, latency_measured=latency_measured)
