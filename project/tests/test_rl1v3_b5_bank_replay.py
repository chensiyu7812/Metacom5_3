"""B5 real-bank replay harness, exercised on a hand-written fixture port (NOT bank-v0)."""
from __future__ import annotations

import itertools

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.bank_replay import replay_prefix
from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv, ReadRejected, TerminalIdentity, TerminalTable
from metacom_pm.rl1v3.needs.spans import locate
from rl1v3_wsb_fixtures import DATASET, FAMILY, OWNER, context

IDENT = TerminalIdentity("fixture-bank", "fixture-index", "render-unbound", "step2-unbound", "g0-unbound", "greedy")
VIEW = {"RS": "method", "MP": "assertion", "ME": "event", "MS": "raw"}
_drift = itertools.count()


class FixturePort:
    bank_version, index_version = "fixture-bank", "fixture-index"
    native_context_tokens, output_reserve_tokens = 1000, 200

    def __init__(self, ctx, *, units=None, avail=None, bad=()):
        self.ctx, self.bad = ctx, set(bad)
        self.units = dict(units or {"RS": 100, "MP": 50, "ME": 80, "MS": 300})
        self.avail = dict(avail or {"RS": 3, "MP": 2, "ME": 2, "MS": 2})
        self.rid = {h: f"{h.lower()}-1" for h in E.HEADS}
        if "drift" in self.bad:
            self.rid["MS"] = f"ms-{next(_drift)}"
        self.recs = {self.rid[h]: self._record(h) for h in E.HEADS}

    def _record(self, head):
        common = dict(record_id=self.rid[head], bank_version=self.bank_version, head=head, view=VIEW[head],
                      event_time=None, valid_from=None, invalid_at=None, body="{}", reading_text=f"{head} unit",
                      index_keys=(), review_status="unverified", writer_identity="fixture", origin_dataset=DATASET,
                      original_raw_identity="0" * 64)
        if head == "RS":
            fam = FAMILY if "rs_overlap" in self.bad else "esconv:esconv_0001"
            return K.ResourceRecord(**common, owner_id=None, source_refs=(), reported_at=None, stage=None,
                                    source_rank=None, ready_at=None, family_id=fam)
        sid, quote, rank = {"MP": ("s0", "My sister Anna moved to Berlin in March", 0),
                            "ME": ("s0", "I tried the breathing exercise last week", 0),
                            "MS": ("s1", "My boss refused my request to reduce overtime", 1)}[head]
        span = locate(quote, self.ctx, sid)
        owner = OWNER
        if head == "ME" and "future" in self.bad:
            rank = 2
            span = K.SourceSpan(**{**{f: getattr(span, f) for f in span.__dataclass_fields__},
                                   "session_id": "s2", "source_rank": 2, "turn_index": 4,
                                   "source_key": f"{DATASET}:{OWNER}:s2:4"})
        if head == "MP" and "foreign_owner" in self.bad:
            owner = "pY"
            span = K.SourceSpan(**{**{f: getattr(span, f) for f in span.__dataclass_fields__}, "owner_id": "pY"})
        t = K.TimePoint(session_rank=rank)
        return K.ResourceRecord(**common, owner_id=owner, source_refs=(span,), reported_at=t,
                                stage="attempted" if head == "ME" else None, source_rank=rank, ready_at=t,
                                family_id=FAMILY)

    def availability(self, prefix):
        return dict(self.avail)

    def unit_tokens(self, prefix):
        u = {h: self.units[h] for h in E.HEADS if self.avail.get(h, 0) > 0}
        if "mask_mismatch" in self.bad:
            u["MP"] = 40
        return u

    def prefix_tokens(self, prefix):
        return 120

    def read(self, prefix, head, *, input_tokens_before):
        fail = lambda reason: K.ReadFailure(reason=reason, detail=f"fixture {reason}",
                                            input_tokens_unchanged=input_tokens_before, elapsed_ms=1.0)
        if self.avail.get(head, 0) <= 0:
            return fail("empty")
        if head == "ME" and "reject_legal" in self.bad:
            return fail("not_ready")
        u = self.units[head]
        if input_tokens_before + u + self.output_reserve_tokens > self.native_context_tokens:
            return fail("capacity")
        view = K.ReadingView(head=head, view=VIEW[head], ordinal=1, reading_text=f"{head} unit",
                             reported_at=None if head == "RS" else K.TimePoint(session_rank=0), tokens=u,
                             stage="attempted" if head == "ME" else None)
        return K.ReadSuccess(reading=view, record_ids=(self.rid[head],), input_tokens_before=input_tokens_before,
                             input_tokens_after=input_tokens_before + u, native_context_tokens=self.native_context_tokens,
                             output_reserve_tokens=self.output_reserve_tokens, elapsed_ms=2.0)

    def records(self, ids):
        return {i: self.recs[i] for i in ids if i in self.recs}


def run(**kw):
    ctx = context()
    return replay_prefix(ctx, lambda: FixturePort(ctx, **kw), IDENT)


def test_clean_port_reaches_all_16_terminals_with_order_invariant_keys():
    rep = run()
    assert rep["passed"], rep["failures"]
    assert rep["n_reachable"] == 16 and rep["n_orders"] == 65 and rep["replay_identical"]
    assert len(set(rep["key_by_subset"].values())) == 16 and rep["unreachable_heads"] == {}


def test_capacity_limits_are_reported_not_bypassed():
    rep = run(units={"RS": 100, "MP": 50, "ME": 80, "MS": 600})
    assert rep["passed"], rep["failures"]
    # capacity 800, prefix 120: with MS (600) only MP (50) or ME (80) still fit; all 8 non-MS subsets fit
    ms = [p for p in rep["reachable"] if "GET_MS" in p]
    assert sorted(ms) == sorted([("GET_MS", "STOP"), ("GET_MP", "GET_MS", "STOP"), ("GET_ME", "GET_MS", "STOP")])
    assert rep["n_reachable"] == 11 and rep["unreachable_heads"] == {}
    assert rep["capacity_probes"] and all(p["reader_rejects_capacity"] for p in rep["capacity_probes"])


def test_empty_head_reduces_reachable_terminals():
    rep = run(avail={"RS": 3, "MP": 0, "ME": 2, "MS": 2})
    assert rep["passed"] and rep["n_reachable"] == 8
    assert rep["unreachable_heads"] == {"MP": "empty_pool"}


@pytest.mark.parametrize("bad,needle", [
    ("foreign_owner", "MP:mp-1:foreign_owner"),
    ("future", "ME:me-1:reported_at_not_strictly_past"),
    ("future", "ME:me-1:illegal_span"),
    ("rs_overlap", "RS:rs-1:rs_family_overlaps_prefix_lineage"),
    ("mask_mismatch", "MP:mask_unit_tokens_40_vs_charged_50"),
    ("drift", "fresh_port_replay_differs"),
    ("reject_legal", "legal_GET_ME_rejected"),
])
def test_harness_catches_provenance_capacity_and_replay_faults(bad, needle):
    rep = run(bad=(bad,))
    assert not rep["passed"] and any(needle in f for f in rep["failures"]), rep["failures"]


def test_token_aware_reader_must_echo_state_and_failure_leaves_state():
    ctx = context()
    port = FixturePort(ctx)
    lie = lambda h, input_tokens_before: port.read(ctx.prefix, h, input_tokens_before=input_tokens_before + 1)
    env = C0FiniteHeadEnv(prefix=ctx.prefix, history_sessions=2, availability=port.availability(None), read=lie,
                          identity=IDENT, table=TerminalTable({}, table_id="t"), prefix_tokens=120,
                          token_capacity=800, unit_tokens=port.unit_tokens(None), read_takes_tokens=True)
    s = env.reset()
    with pytest.raises(ReadRejected, match="charged against"):
        env.step(s, "GET_MP")
    assert s.order == () and s.input_tokens == 120
    ok = C0FiniteHeadEnv(prefix=ctx.prefix, history_sessions=2, availability=port.availability(None),
                         read=lambda h, input_tokens_before: port.read(ctx.prefix, h, input_tokens_before=input_tokens_before),
                         identity=IDENT, table=TerminalTable({}, table_id="t"), prefix_tokens=120,
                         token_capacity=800, unit_tokens=port.unit_tokens(None), read_takes_tokens=True)
    s2 = ok.step(ok.step(ok.reset(), "GET_MP")[0], "GET_ME")[0]
    assert s2.input_tokens == 120 + 50 + 80
    with pytest.raises(E.PendingTerminal):
        ok.step(s2, "STOP")
