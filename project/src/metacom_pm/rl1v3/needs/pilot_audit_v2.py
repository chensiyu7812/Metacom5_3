"""Development audit of the pilot NeedCards, protocol v2 (``pmrl1v3-b1-needcard-pilot-audit-v2``).  v1 is kept.

The six preregistered checks and the derivation rule are exactly those of v1 (``pilot_audit.CHECKS``);
v2 only (a) uses the labels of the researcher's 2026-11-18 instruction, (b) separates pre-call
blocked packs, (c) keeps per-card evidence, error types and per-check reviewer notes, and (d) adds
the B6e gate:
  valid            all checks yes / not_applicable
  evidence_error   any "no" on evidence / state / method / RS-label checks        (v1 evidence_error)
  stratum_error    otherwise any "no" on required-vs-optional checks             (v1 tier_error)
  uncertain        otherwise any cannot_judge                                     (v1 cannot_judge)
  writer_failed    the writer ran and produced no valid card
  pre_call_blocked the pack was not ready; the writer was never called
Gates (both must hold, thresholds are not relaxed): evidence-error rate <= 10% over cards that exist,
and every B6e-v3 selected prefix has a valid card; otherwise B6e is paused.  Only valid cards may get a
checklist v3, frozen before any candidate reply.  RS-v0 ``method_need`` is never GET_RS gold.
"""
from __future__ import annotations

from ..io import object_sha256
from . import pilot_audit as V1

AUDIT_PROTOCOL = "pmrl1v3-b1-needcard-pilot-audit-v2"
CHECKS, ANSWERS = V1.CHECKS, V1.ANSWERS
EVIDENCE_CHECKS, TIER_CHECKS = V1.EVIDENCE_CHECKS, V1.TIER_CHECKS
VERDICTS = ("valid", "evidence_error", "stratum_error", "uncertain", "writer_failed", "pre_call_blocked")
V1_LABEL = {"valid": "valid", "evidence_error": "evidence_error", "tier_error": "stratum_error",
            "cannot_judge": "uncertain", "writer_failed": "writer_failed"}
EVIDENCE_ERROR_GATE = V1.EVIDENCE_ERROR_GATE
NO_CARD = ("writer_failed", "pre_call_blocked")


def prepare(envelopes) -> list[dict]:
    rows = []
    blocked = [e for e in envelopes if e["status"] == "pre_call_blocked"]
    for r, e in zip(V1.prepare([e for e in envelopes if e["status"] != "pre_call_blocked"]),
                    [e for e in envelopes if e["status"] != "pre_call_blocked"]):
        rows.append(dict(r, protocol=AUDIT_PROTOCOL, notes={k: None for k in CHECKS}))
    for e in blocked:
        rows.append(dict(protocol=AUDIT_PROTOCOL, prefix_id=e["prefix_id"], status="pre_call_blocked",
                         needcard_sha256=None, facts=dict(blocked_status=e.get("blocked_status")),
                         answers={k: "not_applicable" for k in CHECKS}, notes={k: None for k in CHECKS},
                         fix_reason=None, reviewer=None))
    return rows


def verdict(row: dict) -> str:
    if row["status"] == "pre_call_blocked":
        return "pre_call_blocked"
    return V1_LABEL[V1.verdict(row)]


def report(rows, *, b6e_prefixes) -> dict:
    out = []
    for r in rows:
        v = verdict(r)
        if v not in ("valid",) + NO_CARD and not r.get("fix_reason"):
            raise ValueError(f"{r['prefix_id']}: a {v} card needs a fix reason")
        if r["status"] == "ok" and not r.get("reviewer"):
            raise ValueError(f"{r['prefix_id']}: reviewer missing")
        out.append(dict(prefix_id=r["prefix_id"], needcard_sha256=r["needcard_sha256"], verdict=v,
                        error_types=sorted(k for k, a in r["answers"].items() if a == "no"),
                        answers=r["answers"], notes=r.get("notes"), facts=r.get("facts"),
                        fix_reason=r.get("fix_reason"), reviewer=r.get("reviewer")))
    cards = [x for x in out if x["verdict"] not in NO_CARD]
    counts = {v: sum(x["verdict"] == v for x in out) for v in VERDICTS}
    rate = counts["evidence_error"] / len(cards) if cards else None
    valid = {x["prefix_id"] for x in out if x["verdict"] == "valid"}
    b6e_missing = sorted(p for p in b6e_prefixes if p not in valid)
    gate_rate = rate is not None and rate <= EVIDENCE_ERROR_GATE
    rep = dict(protocol=AUDIT_PROTOCOL, checks_identical_to=V1.AUDIT_PROTOCOL, cards=len(out), counts=counts,
               per_check={k: {a: sum(x["answers"][k] == a for x in cards) for a in ANSWERS} for k in CHECKS},
               evidence_error_rate=rate, evidence_error_gate=EVIDENCE_ERROR_GATE, gate_passed=gate_rate,
               b6e_prefixes=sorted(b6e_prefixes), b6e_prefixes_without_valid_card=b6e_missing,
               b6e_gate_passed=gate_rate and not b6e_missing, b6e_paused=not (gate_rate and not b6e_missing),
               checklist_eligible=sorted(valid),
               fix_reasons={x["prefix_id"]: x["fix_reason"] for x in out if x["fix_reason"]},
               rs_method_need_is_gold_for_get_rs=False,
               scope="small-scale generation feasibility only; formal B1 still needs its sampling and the 40-card audit",
               rows=out, evidence_tier="engineering_only")
    return dict(rep, sha256=object_sha256(rep))


def freeze_checklists(rep: dict, envelopes, ledger, build) -> dict:
    """Same rule as v1: evidence-error gate passed, valid cards only, before any candidate."""
    return V1.freeze_checklists(rep, envelopes, ledger, build)
