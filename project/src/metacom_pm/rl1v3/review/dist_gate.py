"""Distribution gate for review packages (WS-B).

Called by the coordinator (CUR1) right before building any FC-MS review package.  It runs WS-A's DP v2
`check_reviewer` for every (prefix, channel, reviewer) actually being packaged, and adds B's rules that DP v2 does not
model:

* the F adjudicator must not be (an alias of) the primary or the 15% second DP selector of that prefix, nor one of its
  reviewers, nor the non-blind coordinator;
* reviewers are R1/R2 only; the coordinator never reviews.

The DP module is passed in (it lives in WS-A's tree), so this file imports nothing from it.
"""
from __future__ import annotations


class GateRefused(Exception):
    pass


def check_distribution(D, plan, bundle, receipts, roles, packaging, *, second_receipts=None, adjudicator=None,
                       coordinator="CUR1", reviewers_allowed=("R1", "R2")):
    """packaging: [(prefix_id, channel, reviewer)].  Returns a small summary; raises GateRefused on any conflict."""
    people = roles["people"]
    done = []
    for pid, ch, rv in packaging:
        if rv not in reviewers_allowed:
            raise GateRefused(f"{rv} is not a reviewer code")
        if people.get(rv) == people.get(coordinator):
            raise GateRefused("the non-blind coordinator cannot review")
        try:
            D.check_reviewer(plan, bundle, receipts, roles, pid, rv, ch)
        except Exception as e:                       # A's AdmissionError and friends
            raise GateRefused(f"DP v2 check_reviewer refused {rv}/{ch} on {pid[:12]}: {e}") from e
        done.append((pid, ch, rv))
    adjudicable = None
    if adjudicator is not None:
        me = people.get(adjudicator)
        if not me:
            raise GateRefused("adjudicator has no person identity")
        if me == people.get(coordinator):
            raise GateRefused("the non-blind coordinator cannot adjudicate")
        adjudicable, blocked = [], []
        for pid in sorted({p for p, _c, _r in packaging}):
            sel = {receipts[pid]["selector"]}
            if second_receipts and pid in second_receipts:
                sel.add(second_receipts[pid]["selector"])
            revs = {r for chs in roles["assignments"][pid]["reviewers"].values() for r in chs}
            if me in {people.get(s) for s in sel | revs}:
                blocked.append(pid)
            else:
                adjudicable.append(pid)
        adjudicable = dict(allowed=adjudicable, blocked=blocked,
                           rule="裁决者不得是该前缀的主选择者、15% 第二选择者或审阅者；被挡住的分歧记为“未裁决”，保留两名审阅者原始标签")
    return dict(checked=len(done), adjudication=adjudicable, authorized=False)
