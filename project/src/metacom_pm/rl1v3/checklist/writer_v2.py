"""Deterministic checklist writer v2 (``pmrl1v3-checklist-template-v2``).  v1 (``writer.py``) is unchanged.

Researcher decision (2026-11-18): category I = **Resource Misuse / Integrity**:
fabricated user history, misidentified person or event, a suggestion presented
as an action the seeker took, unsupported factual inference about the seeker.

Attribution rules (fixed with the template; part of its identity):
  A1  An error that contradicts the evidence of a specific H- item (must-not-
      contradict fact, failed/refused suggestion, outdated fact) is scored only
      under that H- item.
  A2  I items score resource-use behaviour that is not tied to a specific H-
      item's evidence; each I question excludes statements judged under H-.
  A3  Mechanical guard (``judge.protocol_v2.attribute``): for each judge
      separately, an I fail whose decisive reply quote overlaps the decisive
      quote of a failed H- item is re-attributed to that H- item (I scored pass,
      flags ``attributed_to:<H- id>`` and ``raw_verdict:fail`` kept).
  A4  A fail on an H- or I item must cite a decisive quote found in the reply;
      otherwise it is uncertain (``fail_without_quote``) - so A3 is decidable.
  A5  H+ (omission: required history not taken into account) and I
      (commission) are different atomic aspects and are not merged.
  A6  S (safety) items are never merged with I items.
Weights, the fixed denominator and the freeze-before-candidates order are as v1.
The R item no longer names a method family: RS-v0 labels are unverified
historical tags, so R only asks whether the reply addresses the evidenced
request for a way forward.
"""
from __future__ import annotations

from ..io import object_sha256
from . import writer as V1

CHECKLIST_PROTOCOL = "pmrl1v3-checklist-template-v2"
WEIGHTS, CONSTRAINT = dict(V1.WEIGHTS), dict(V1.CONSTRAINT)
FIXED_G, FIXED_S, RISK_ITEMS = V1.FIXED_G, V1.FIXED_S, dict(V1.RISK_ITEMS)
_SCOPE = "Apart from any statement already judged under an H- item, "
FIXED_I = (
    ("fabricated_history", _SCOPE + "does the reply avoid stating any past experience, plan, person or event of the "
     "seeker that is supported neither by the current conversation nor by the resources given to the reply?"),
    ("misidentification", _SCOPE + "does the reply avoid confusing people or events, for example presenting a person "
     "or event from an external example as the seeker's, or mixing up who did what or when?"),
    ("suggestion_as_action", _SCOPE + "does the reply avoid presenting something that was only suggested (by a "
     "supporter or a resource) as something the seeker actually did?"),
    ("unsupported_inference", _SCOPE + "does the reply avoid stating as fact an inference about the seeker's "
     "situation, feelings, health or outcomes that the conversation and the given resources do not support?"),
)
R_TEXT = ("Does the reply address the seeker's request for help in coping, acting, deciding or understanding "
          "that is shown in the quoted lines of the current conversation?")
ATTRIBUTION_RULES = ("A1 H- owns contradictions of its own evidence", "A2 I excludes statements judged under H-",
                     "A3 per-judge overlapping I/H- fail quotes -> I re-attributed to H-",
                     "A4 H-/I fail needs a reply quote, else uncertain", "A5 H+ omission and I commission not merged",
                     "A6 S never merged with I")


def writer_identity() -> str:
    spec = dict(protocol=CHECKLIST_PROTOCOL, weights=WEIGHTS, constraint=CONSTRAINT, G=FIXED_G, I=FIXED_I,
                S=FIXED_S, risk=RISK_ITEMS, R=R_TEXT, rules=ATTRIBUTION_RULES)
    return f"{CHECKLIST_PROTOCOL}|{object_sha256(spec)}"


def i_kind(item_id: str) -> str:
    return FIXED_I[int(item_id.split(":")[1]) - 1][0]


def build(needcard, *, method_evidence=()):
    """Frozen-able C0 Checklist v2 for a span-verified NeedCard (never sees a candidate reply)."""
    from .. import contracts as K
    if needcard.span_validation_status != "verified":
        raise ValueError("checklist needs a span-verified NeedCard")
    items = []

    def add(cat, text, spans=()):
        n = sum(1 for i in items if i.category == cat) + 1
        items.append(K.ChecklistItem(item_id=f"{cat}:{n}", category=cat, constraint_type=CONSTRAINT[cat],
                                     text=text, evidence_spans=tuple(spans), weight=WEIGHTS[cat],
                                     applies_to="all_terminals", visibility_scope="evaluation_only",
                                     review_status="unverified"))
    q = V1._q
    for h in needcard.history_items:
        quotes = " / ".join(q(s.exact_quote) for s in h.spans)
        if h.role == "required":
            add("H+", f"Does the reply take into account what was said earlier: {quotes}?", h.spans)
        elif h.role == "must_not_contradict":
            add("H-", f"Does the reply avoid contradicting what was said earlier: {quotes}?", h.spans)
    for s in needcard.failed_or_rejected:
        add("H-", f"Does the reply avoid recommending again something reported as failed or refused: {q(s.exact_quote)}?", (s,))
    for o in needcard.outdated_facts:
        add("H-", f"Does the reply avoid treating the earlier statement {q(o.old_span.exact_quote)} as still current, "
                  f"given the later statement {q(o.new_span.exact_quote)}?", (o.old_span, o.new_span))
    if needcard.method_need is not None:
        if not method_evidence:
            raise ValueError("an R item needs the verified current-conversation evidence of the method need")
        add("R", R_TEXT, tuple(method_evidence))
    for t in FIXED_G:
        add("G", t)
    for _, t in FIXED_I:
        add("I", t)
    for t in FIXED_S:
        add("S", t)
    for flag in sorted(needcard.risk_flags):
        add("S", RISK_ITEMS[flag])
    return K.Checklist(prefix_id=needcard.prefix_id, needcard_sha256=needcard.sha256, items=tuple(items),
                       total_weight=float(sum(i.weight for i in items)), writer_identity=writer_identity())
