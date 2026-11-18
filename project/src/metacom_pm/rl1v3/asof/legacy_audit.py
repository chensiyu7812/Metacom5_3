"""Independent WS-B as-of audit of the frozen bank-v0 (``pmrl1v3-wsb-asof-legacy-audit-v1``).  CPU, read-only.

Three questions, answered separately:
1. Compiler input frontier: did the legacy multi-view compiler see only strictly-past material?  Each
   compiled session row carries ``prior_profile_sha256``; we recompute it from accepted units of
   strictly earlier sessions only (the compiler's own ``_current_profile`` rule).  Reproducing all of
   them shows the per-session units were written as-of; it says nothing about unit semantics.
2. Pool membership: bank-v0 keeps, per (owner, profile slot), only the units with the maximal rank
   over the WHOLE trajectory.  A chronological writer keeps the latest unit among sessions before
   the cutoff.  The two differ exactly where a slot's global latest lies at/after the cutoff; that
   is a prefix-extension violation (appending later sessions changes an earlier pool).
3. Delivered unit: with the same lexical-v0 rule, would the as-of MP pool deliver another Top-1?
   ``same``, ``differs`` or ``tie_dependent`` (top score tied with an as-of-only unit whose record id
   does not exist yet).  This is a B-side counterfactual, not A's as-of writer and not a new bank.
ME units are kept whole by bank-v0 (no projection); MS is complete RAW; RS is the preinstalled
ESConv snapshot.  Their as-of legality reduces to the registry rules (strict past, ready, owner,
family), which the B5 replay already enforces; repaired records stay flagged for semantic review.
"""
from __future__ import annotations

import json
from collections import defaultdict

from ..io import object_sha256

PROTOCOL = "pmrl1v3-wsb-asof-legacy-audit-v1"
MP_HEADER = "Historical self-report; present validity unverified.\n"


def legacy_id(record) -> str:
    """bank-v0 legacy id (``mp::``/``me::``/``ms::``); RS cases carry none -> ``""``."""
    return json.loads(record.body).get("legacy_id", "")


def compiler_frontier(rows, registry) -> dict:
    """Recompute every session's prior-profile hash from strictly-past accepted units only."""
    from metacom_pm.paper1.multi_view_memory.contracts import PriorCurrentProfileSlot
    from metacom_pm.paper1.multi_view_memory.grounding import canonical_json, sha256_text
    rank = {(e.source.owner_id, e.source.session_id): e.source.chronological_rank
            for e in registry.entries if e.availability_scope == "personal_history"}
    units = defaultdict(list)
    for r in rows:
        units[r["owner_id"]].extend(r["accepted_units"])
    bad, unit_mismatch = [], 0
    for r in rows:
        cr = rank[(r["owner_id"], r["session_id"])]
        unit_mismatch += sum(u["source_session_rank"] != cr or u["source_session_id"] != r["session_id"]
                             for u in r["accepted_units"])
        latest = {}
        for u in sorted((u for u in units[r["owner_id"]] if "profile_slot_key" in u and u["source_session_rank"] < cr),
                        key=lambda u: (u["source_session_rank"], u["memory_id"])):
            latest[u["profile_slot_key"]] = u
        table = [PriorCurrentProfileSlot(memory_id=u["memory_id"], profile_field_type=u["profile_field_type"],
                                         profile_slot_key=u["profile_slot_key"], normalized_value=u["normalized_value"],
                                         source_session_rank=u["source_session_rank"]).model_dump(mode="json")
                 for _, u in sorted(latest.items())]
        if sha256_text(canonical_json(table)) != r["prior_profile_sha256"]:
            bad.append(dict(owner_id=r["owner_id"], session_id=r["session_id"], rank=cr))
    return dict(sessions=len(rows), reproduced=len(rows) - len(bad), mismatches=bad,
                units=sum(len(r["accepted_units"]) for r in rows), unit_session_or_rank_mismatch=unit_mismatch,
                compiler_versions=sorted({r["compiler_version"] for r in rows}),
                meaning="per-session compiler inputs were strictly past (prior profile reproduced); "
                        "unit semantics remain unverified")


class MPPools:
    """bank-v0 MP pool vs the chronological latest-before-cutoff pool, from the same compiled units."""

    def __init__(self, rows, bank):
        self.units = {u["memory_id"]: u for r in rows for u in r["accepted_units"] if "profile_slot_key" in u}
        self.by_slot = defaultdict(list)
        for u in self.units.values():
            self.by_slot[(u["owner_id"], u["profile_slot_key"])].append(u)
        self.record_of = {}           # memory_id -> bank record (MP or repaired ME)
        for r in bank.records:
            lid = legacy_id(r)
            if lid.startswith("mp::"):
                self.record_of[lid[4:]] = r
        self.mp_in_bank = {m for m, r in self.record_of.items() if r.head == "MP"}
        self.moved_to_me = {m for m, r in self.record_of.items() if r.head != "MP"}
        # sanity: every bank MP is a global-latest unit of its slot
        for m in self.mp_in_bank:
            u = self.units[m]
            top = max(x["source_session_rank"] for x in self.by_slot[(u["owner_id"], u["profile_slot_key"])])
            if u["source_session_rank"] != top:
                raise ValueError(f"bank MP {m} is not the global latest of its slot")

    def legacy(self, owner: str, cutoff: int) -> frozenset:
        return frozenset(m for m in self.mp_in_bank if self.units[m]["owner_id"] == owner
                         and self.units[m]["source_session_rank"] < cutoff)

    def asof(self, owner: str, cutoff: int) -> frozenset:
        """Latest-before-cutoff per slot.  Units re-headed to ME by an evidenced repair do not compete
        for the MP slot (they were re-classified as events, not profile updates)."""
        return asof_pool(self.by_slot, self.moved_to_me, owner, cutoff)

    def legacy_at_horizon(self, owner: str, cutoff: int, horizon: int) -> frozenset:
        """bank-v0's rule (repaired units included in the latest computation, as in ``bank_v0.build``)
        applied to a bank built from sessions < horizon (prefix-extension test)."""
        out = set()
        for (o, _), us in self.by_slot.items():
            if o != owner:
                continue
            seen = [u for u in us if u["source_session_rank"] < horizon]
            if not seen:
                continue
            top = max(u["source_session_rank"] for u in seen)
            out |= {u["memory_id"] for u in seen if u["source_session_rank"] == top and top < cutoff}
        return frozenset(out - self.moved_to_me)


def asof_pool(by_slot, moved_to_me, owner: str, cutoff: int) -> frozenset:
    """The chronological writer rule on any unit collection (also a truncated history)."""
    out = set()
    for (o, _), us in by_slot.items():
        if o != owner:
            continue
        seen = [u for u in us if u["source_session_rank"] < cutoff and u["memory_id"] not in moved_to_me]
        if not seen:
            continue
        top = max(u["source_session_rank"] for u in seen)
        out |= {u["memory_id"] for u in seen if u["source_session_rank"] == top}
    return frozenset(out)


def slots_of(rows) -> dict:
    by_slot = defaultdict(list)
    for r in rows:
        for u in r["accepted_units"]:
            if "profile_slot_key" in u:
                by_slot[(u["owner_id"], u["profile_slot_key"])].append(u)
    return by_slot


def census_diff(pools: MPPools, census_rows) -> dict:
    rows, n_diff, extra_total, missing_total = [], 0, 0, 0
    per_owner = defaultdict(lambda: [0, 0])
    for c in census_rows:
        leg, aso = pools.legacy(c["owner_id"], c["cutoff_rank"]), pools.asof(c["owner_id"], c["cutoff_rank"])
        missing, extra = aso - leg, leg - aso
        per_owner[c["owner_id"]][0] += 1
        if missing or extra:
            n_diff += 1
            per_owner[c["owner_id"]][1] += 1
        extra_total += len(extra)
        missing_total += len(missing)
        rows.append(dict(prefix_id=c["prefix_id"], owner_id=c["owner_id"], cutoff_rank=c["cutoff_rank"],
                         legacy=len(leg), asof=len(aso), asof_only=len(missing), legacy_only=len(extra)))
    return dict(prefixes=len(rows), prefixes_with_mp_pool_difference=n_diff,
                legacy_only_units_total=extra_total, asof_only_units_total=missing_total,
                per_owner={o: dict(prefixes=a, differing=b) for o, (a, b) in sorted(per_owner.items())},
                rows=rows)


def _mp_text(registry, unit) -> tuple[str, int]:
    from ..sources import source_registry as S
    e = registry.entry(unit["owner_id"], unit["source_session_id"])
    refs = [S.span(e.source, e.original_turn_indices.index(s["turn_index"]), s["start_char"], s["end_char"])
            for s in unit["supporting_spans"]]
    return MP_HEADER + "\n".join(f"{r.speaker}: {r.exact_quote}" for r in refs), e.source.chronological_rank


def counterfactual_top1(pools: MPPools, bank, prefix) -> dict:
    """Lexical-v0 Top-1 over bank-v0's legal MP pool vs over the as-of pool (same scorer, same query)."""
    from ..retrieve.v0 import search, words
    legal = search(bank, "MP", prefix)
    q = words("\n".join(t.text for t in prefix.turns[-3:]))
    score = lambda text: len(q & words(text)) / max(1, len(q))
    leg_top = None
    if legal.ranked:
        r0 = bank.by_id[legal.ranked[0].record_id]
        leg_top = dict(memory_id=legacy_id(r0)[4:], score=legal.ranked[0].score, rank=r0.source_rank,
                       record_id=r0.record_id)
    aso = pools.asof(prefix.owner_id, prefix.cutoff_rank)
    leg = pools.legacy(prefix.owner_id, prefix.cutoff_rank)
    cands = []
    for m in aso:
        if m in pools.record_of:
            r = pools.record_of[m]
            cands.append((score(r.reading_text), r.source_rank, r.record_id, m, False))
        else:
            text, rk = _mp_text(bank.registry, pools.units[m])
            cands.append((score(text), rk, None, m, True))
    cands.sort(key=lambda x: (-x[0], -x[1], x[2] or ""))
    out = dict(legacy_pool=len(leg), asof_pool=len(aso), asof_only=len(aso - leg), legacy_only=len(leg - aso),
               legacy_top1=leg_top, asof_top1=None, top1="no_candidate" if not cands and not leg_top else None)
    if cands:
        s0, rk0, rid0, m0, new0 = cands[0]
        ties = [c for c in cands if c[0] == s0 and c[1] == rk0]
        out["asof_top1"] = dict(memory_id=m0, score=s0, rank=rk0, asof_only=new0)
        if leg_top is None:
            out["top1"] = "legacy_has_no_candidate"
        elif len(ties) > 1 and any(c[4] for c in ties):
            out["top1"] = "tie_dependent"
        else:
            out["top1"] = "same" if m0 == leg_top["memory_id"] else "differs"
    elif leg_top:
        out["top1"] = "asof_has_no_candidate"
    out["sha256"] = object_sha256(out)
    return out
