"""J1/J2 aggregation v3 (``pmrl1v3-judge-aggregation-v3``): rule L7.  ``aggregate.py`` is unchanged.

C0 ``ItemVerdict`` forces ``final = uncertain`` whenever J1 and J2 disagree and
no human has adjudicated.  For an ownership disagreement inside H-/I (J1 fails
item X and passes Y, J2 fails Y and passes X) that makes C0 ``gsc_interval``
count the error under both items in the lower bound and under neither in the
upper bound, although both judges found an error.  Whether it is one error with
two candidate owners or two errors each judge missed once cannot be decided
mechanically, so v3 does not score it: the disputed items need a C0
``HumanAdjudication`` before the terminal is admitted to a GSC table; until
then ``gsc_interval`` returns ``(None, None)`` (pending, never 0).  Other
disagreements keep the v1 rule (uncertain).
"""
from __future__ import annotations

from . import aggregate as AG

AGGREGATION_PROTOCOL = "pmrl1v3-judge-aggregation-v3"
INTEGRITY = ("H-", "I")


def attribution_disputes(checklist, j1, j2) -> list[dict]:
    if j1 is None or j2 is None:
        return []
    ids = [i.item_id for i in checklist.items if i.category in INTEGRITY]
    a = [i for i in ids if j1.items[i].verdict == "fail" and j2.items[i].verdict == "pass"]
    b = [i for i in ids if j2.items[i].verdict == "fail" and j1.items[i].verdict == "pass"]
    if not (a and b):
        return []
    ledgers = {r: sorted(getattr(j, "ledger", ()), key=lambda e: e["id"]) for r, j in (("J1", j1), ("J2", j2))}
    return [dict(rule="L7", items=sorted(a + b), j1_only_fail=a, j2_only_fail=b,
                 ledgers={r: [dict(id=e["id"], kind=e["kind"], owner=e.get("owner"), quotes=e["quotes"])
                              for e in led if e.get("invalid") is None] for r, led in ledgers.items()})]


def item_verdicts(checklist, j1, j2, human=None) -> tuple:
    """C0 ItemVerdicts exactly as v1 (C0 is frozen); disputes are handled by ``gsc_admission``."""
    return AG.item_verdicts(checklist, j1, j2, human)


def gsc_admission(checklist, verdicts, disputes) -> dict:
    by = {v.item_id: v for v in verdicts}
    open_ = sorted({i for d in disputes for i in d["items"] if by[i].human_adjudication is None})
    if open_:
        return dict(status="pending_adjudication", unresolved_items=open_, protocol=AGGREGATION_PROTOCOL)
    if any(v.pending for v in verdicts):
        return dict(status="pending", unresolved_items=[], protocol=AGGREGATION_PROTOCOL)
    return dict(status="admissible", unresolved_items=[], protocol=AGGREGATION_PROTOCOL)


def gsc_interval(checklist, verdicts, disputes):
    from .. import contracts as K
    if gsc_admission(checklist, verdicts, disputes)["status"] != "admissible":
        return None, None
    return K.gsc_interval(checklist, verdicts)
