"""Deterministic checklist writer v3 (``pmrl1v3-checklist-template-v3``).  v1/v2 are unchanged.

Why v3 (``outputs/pm_rl1/v3/B2/ATTRIBUTION_V3_ZH.md``; executable counterexamples in
``tests/test_rl1v3_b2_attribution_counterexamples.py``): v2 decided "same atomic
error" from character overlap of two decisive quotes (A3) and told every I item to
skip whole *statements* already judged under H- (A2).  Both are statement-level,
not error-level: two different errors in one sentence were merged (one lost) and
one error quoted in two places was counted twice.

v3 keeps every item, category (H+/H-/R/G/I/S), constraint type, weight and the
fixed total weight of v2.  Only two things change:
* the four I questions lose the statement-level scope prefix;
* the attribution rules become the atomic-error ledger rules L1-L8 below,
  applied by ``judge.protocol_v3`` (per judge) and ``judge.aggregate_v3``
  (J1/J2).  Text overlap alone never merges two errors.

  L1  One atomic error = one ledger entry (judge-declared id) = one false or
      unsupported proposition; ``quotes`` lists every exact, shortest reply
      span that states it (the same error said twice -> one entry, two quotes).
  L2  Owner from kind + evidence, never from text: ``history_conflict`` -> the
      H- item holding the cited evidence id (none -> invalid entry); an I kind
      citing an H- item's evidence -> that H- item (researcher rule: H- owns
      contradictions of specific history); any other I kind -> its I item.
  L3  An error counts once, under its owner; another item's fail citing it is
      re-attributed (pass, ``attributed_to:<owner>``, ``raw_verdict:fail``).
  L4  Different entries whose quotes are disjoint are different errors and
      all count, also inside one sentence.
  L5  Different entries with different owners whose quotes overlap (identical,
      nested or partial) are neither merged nor certainly double counted: the
      higher-precedence owner fails (H- items in checklist order, then I:1-I:4)
      and the lower one is ``uncertain`` (``overlap_ambiguous``) unless it owns
      another unambiguous error.  J1 lower bound = two errors, upper = one.
  L6  Rows must agree with the ledger: an H-/I fail needs a valid owned or
      cited error (else uncertain, ``fail_without_valid_error``); an item that
      owns a valid error but is answered pass/uncertain is uncertain
      (``ledger_row_conflict``).
  L7  J1/J2: if each judge fails some H-/I item that the other passes, the
      ownership is disputed; those items need human adjudication before the
      terminal can enter a GSC table (C0 would otherwise score the error twice
      in the lower bound and not at all in the upper bound).
  L8  H+ (omission) and S (safety) are never merged with I (v2 A5/A6).
"""
from __future__ import annotations

from ..io import object_sha256
from . import writer as V1
from . import writer_v2 as V2

CHECKLIST_PROTOCOL = "pmrl1v3-checklist-template-v3"
WEIGHTS, CONSTRAINT = dict(V2.WEIGHTS), dict(V2.CONSTRAINT)
FIXED_G, FIXED_S, RISK_ITEMS, R_TEXT = V2.FIXED_G, V2.FIXED_S, dict(V2.RISK_ITEMS), V2.R_TEXT
FIXED_I = tuple((kind, text[len(V2._SCOPE)].upper() + text[len(V2._SCOPE) + 1:]) for kind, text in V2.FIXED_I)
I_KINDS = tuple(k for k, _ in FIXED_I)
ATTRIBUTION_RULES = (
    "L1 one ledger entry per atomic error; quotes = every shortest reply span stating it",
    "L2 owner from kind+evidence: history_conflict or I kind citing H- evidence -> that H- item; else its I item",
    "L3 an error counts once under its owner; other items citing it are re-attributed",
    "L4 entries with disjoint quotes are distinct errors, also within one sentence",
    "L5 overlapping quotes with different owners: higher precedence fails, lower uncertain (never merged)",
    "L6 H-/I fail needs a valid error; owned error with pass/uncertain row -> uncertain",
    "L7 J1/J2 ownership swap within H-/I -> human adjudication before GSC",
    "L8 H+ omission and S safety never merged with I",
)


def writer_identity() -> str:
    spec = dict(protocol=CHECKLIST_PROTOCOL, weights=WEIGHTS, constraint=CONSTRAINT, G=FIXED_G, I=FIXED_I,
                S=FIXED_S, risk=RISK_ITEMS, R=R_TEXT, rules=ATTRIBUTION_RULES)
    return f"{CHECKLIST_PROTOCOL}|{object_sha256(spec)}"


def i_kind(item_id: str) -> str:
    return FIXED_I[int(item_id.split(":")[1]) - 1][0]


def i_item(kind: str) -> str:
    return f"I:{I_KINDS.index(kind) + 1}"


def build(needcard, *, method_evidence=()):
    """Frozen-able C0 Checklist v3 for a span-verified NeedCard (never sees a candidate reply).

    Item order, categories, weights and evidence are those of v2 (``writer_v2.build``)."""
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
