"""B5 replay v2: fixture port (synthetic) + WS-A's real bank-v0 with a test-only tokenizer.

The fixture port mimics the A1b Reader contract (stateless read with the
acquired ReadingViews, set-based billing with a per-reading template overhead,
dynamic capacity mask).  The real-bank tests load WS-A's committed registry and
bank-v0; their tokenizer counts characters and is never a measurement.
"""
from __future__ import annotations

import dataclasses
import itertools
import json
from pathlib import Path

import pytest

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.env import finite_head as E
from metacom_pm.rl1v3.env.bank_replay_v2 import _rejected_read_keeps_state, replay_prefix
from metacom_pm.rl1v3.io import canonical_json, object_sha256
from metacom_pm.rl1v3.needs.spans import locate
from rl1v3_wsb_fixtures import DATASET, FAMILY, OWNER, context

ROOT = Path(__file__).resolve().parents[2]
VIEW = {"RS": "case", "MP": "assertion", "ME": "event", "MS": "raw"}
QUOTES = {"MP": ("s0", "My sister Anna moved to Berlin in March", 0),
          "ME": ("s0", "I tried the breathing exercise last week", 0),
          "MS": ("s1", "My boss refused my request to reduce overtime", 1)}
_drift = itertools.count()


def _esconv():
    turns = (K.SourceTurn(turn_index=0, role="seeker", text="I feel stressed about exams."),
             K.SourceTurn(turn_index=1, role="supporter", text="Exams can be really stressful."))
    return K.SourceSession(owner_id="external:esconv_0001", session_id="esconv_0001", chronological_rank=0,
                           date=None, turns=turns, raw_sha256="1" * 64, dataset="ESConv",
                           family_id="esconv:esconv_0001", license="fixture", provenance_version="fixture",
                           source_uri="fixture://esconv", source_split="train",
                           transcript_sha256=object_sha256([(t.role, t.text) for t in turns]))


class FixturePortV2:
    native_context_tokens, output_reserve_tokens, base_tokens = 1000, 200, 120

    def __init__(self, ctx, *, units=None, avail=None, bad=(), overhead=0, reserve=None):
        self.ctx, self.prefix, self.bad, self.overhead = ctx, ctx.prefix, set(bad), overhead
        if reserve is not None:
            self.output_reserve_tokens = reserve
        self.units = dict(units or {"RS": 100, "MP": 50, "ME": 80, "MS": 300})
        self.avail = dict(avail or {"RS": 3, "MP": 2, "ME": 2, "MS": 2})
        self.rid = {h: f"{h.lower()}-1" for h in E.HEADS}
        if "drift" in self.bad:
            self.rid["MS"] = f"ms-{next(_drift)}"
        self.es = _esconv()
        self.text = {h: self._text(h) for h in E.HEADS}
        self.recs = {self.rid[h]: self._record(h) for h in E.HEADS}
        self.identity = dict(bank_version="fixture-bank", index_version="fixture-index",
                             renderer_id=f"renderer:fixture-{self.output_reserve_tokens}", step2_id="none-fixture",
                             g_id="g-fixture-not-frozen", decode_id="greedy-fixture")

    def _text(self, head):
        if head == "RS":
            return "External example.\n" + "\n".join(f"{t.role}: {t.text}" for t in self.es.turns)
        q = QUOTES[head][1]
        return f"[{head}]\nseeker: " + ("a paraphrase only" if ("unbound" in self.bad and head == "MP") else q)

    def _record(self, head):
        common = dict(record_id=self.rid[head], bank_version="fixture-bank", head=head, view=VIEW[head],
                      event_time=None, valid_from=None, invalid_at=None, body="{}", reading_text=self.text[head],
                      index_keys=(), review_status="unverified", writer_identity="fixture",
                      original_raw_identity="0" * 64)
        if head == "RS":
            fam = FAMILY if "rs_overlap" in self.bad else self.es.family_id
            spans = tuple(K.SourceSpan(source_key=f"ESConv:{self.es.owner_id}:{self.es.session_id}:{i}",
                                       owner_id=self.es.owner_id, session_id=self.es.session_id, source_rank=0,
                                       turn_index=i, speaker=t.role, start_char=0, end_char=len(t.text),
                                       exact_quote=t.text, raw_turn_sha256=t.raw_turn_sha256)
                          for i, t in enumerate(self.es.turns))
            return K.ResourceRecord(**common, owner_id=None, source_refs=spans, reported_at=None, stage=None,
                                    source_rank=None, ready_at=None, family_id=fam, origin_dataset="ESConv",
                                    ancestor_family_ids=(fam,),
                                    source_split="dev" if "rs_not_train" in self.bad else "train")
        sid, quote, rank = QUOTES[head]
        span = locate(quote, self.ctx, sid)
        owner = OWNER
        if head == "MP" and "foreign_owner" in self.bad:
            owner = "pY"
            span = dataclasses.replace(span, owner_id="pY")
        ready = rank + (2 if (head == "MS" and "ready_late" in self.bad) else 1)   # s1 -> 2 == cutoff
        return K.ResourceRecord(**common, owner_id=owner, source_refs=(span,), origin_dataset=DATASET,
                                reported_at=K.TimePoint(session_rank=rank), stage="attempted" if head == "ME" else None,
                                source_rank=rank, ready_at=K.TimePoint(session_rank=ready), family_id=FAMILY)

    def _billed(self, acquired):          # one-time wrapper overhead, like A's <external_evidence> block
        return self.base_tokens + sum(r.tokens for r in acquired) + (self.overhead if acquired else 0)

    def availability(self):
        a = dict(self.avail)
        if "avail_lie" in self.bad:
            a["MP"] = 0
        return a

    def read(self, head, *, acquired=()):
        before = self._billed(acquired)
        fail = lambda reason: K.ReadFailure(reason=reason, detail=f"fixture {reason}",
                                            input_tokens_unchanged=before, elapsed_ms=1.0)
        if head in {r.head for r in acquired} or [r.ordinal for r in acquired] != list(range(1, len(acquired) + 1)):
            return fail("invalid_action")
        if self.avail.get(head, 0) <= 0:
            return fail("unavailable")
        if head == "ME" and "reject_legal" in self.bad:
            return fail("not_ready")
        tok = self.units[head]
        after = before + tok + (0 if acquired else self.overhead)
        if after + self.output_reserve_tokens > self.native_context_tokens:
            return fail("capacity")
        view = K.ReadingView(head=head, view=VIEW[head], ordinal=len(acquired) + 1, reading_text=self.text[head],
                             reported_at=None if head == "RS" else K.TimePoint(session_rank=QUOTES[head][2]),
                             tokens=tok + (1 if ("token_lie" in self.bad and head == "ME") else 0),
                             stage="attempted" if head == "ME" else None)
        echo = before + (1 if ("echo_lie" in self.bad and acquired) else 0)
        return K.ReadSuccess(reading=view, record_ids=(self.rid[head],), input_tokens_before=echo,
                             input_tokens_after=echo + view.tokens + (0 if acquired else self.overhead),
                             native_context_tokens=self.native_context_tokens,
                             output_reserve_tokens=self.output_reserve_tokens, elapsed_ms=2.0)

    def action_mask(self, acquired=()):
        ok = [f"GET_{h}" for h in E.HEADS if isinstance(self.read(h, acquired=acquired), K.ReadSuccess)]
        if "mask_hide" in self.bad and "GET_MP" in ok and acquired:
            ok.remove("GET_MP")
        return tuple(ok) + ("STOP",)

    def records(self, ids):
        return {i: self.recs[i] for i in ids if i in self.recs}

    def source(self, owner_id, session_id):
        if session_id == self.es.session_id:
            return self.es
        return {(s.owner_id, s.session_id): s for s in self.ctx.sources}[(owner_id, session_id)]

    def count_tokens(self, text):
        return next(self.units[h] for h in E.HEADS if self.text[h] == text)

    def replay(self, key):
        results = []
        for action, group in zip(key.ordered_path[:-1], key.acquired):
            res = self.read(action[4:], acquired=tuple(r.reading for r in results))
            if isinstance(res, K.ReadFailure):
                return res
            results.append(res)
        acq = tuple(r.record_ids for r in results)
        if "replay_drift" in self.bad and acq:
            acq = (("other-record",),) + acq[1:]
        return K.ExecutionTrace(domain_id="finite_head_v1", ordered_path=key.ordered_path, acquired=acq,
                                readings=tuple(r.reading for r in results))


def run(**kw):
    ctx = context()
    return replay_prefix(lambda: FixturePortV2(ctx, **kw))


def test_clean_port_reaches_16_with_real_identity_and_order_invariant_keys():
    rep = run()
    assert rep["passed"], rep["failures"]
    assert rep["n_reachable"] == 16 and rep["n_orders"] == 65 and rep["replay_identical"]
    assert len(set(rep["key_by_subset"].values())) == 16 and rep["unreachable_heads"] == {}
    assert rep["identity"]["g_id"] == "g-fixture-not-frozen"
    assert rep["head_probe"]["MS"]["ready_at_equals_cutoff"] == ["ms-1"]      # boundary is legal


def test_dynamic_capacity_mask_reports_real_reachable_count_and_static_disagreement():
    # one-time wrapper 60: root charges include it, so a static additive mask over-counts later reads
    # (after MS: 680 + ME 80 = 760 <= 800 fits, static says 680 + 140 = 820 does not)
    rep = run(units={"RS": 100, "MP": 50, "ME": 80, "MS": 500}, overhead=60)
    assert rep["passed"], rep["failures"]
    assert rep["n_reachable"] == 12          # all 8 without MS + MS, MS+MP, MS+ME, MS+RS
    assert {"after": "MS", "head": "ME", "static": False, "dynamic": True} in rep["static_mask_disagreements"]
    assert {m["reason"] for m in rep["masked_probes"]} == {"capacity"}


def test_empty_head_is_reported_with_reader_reason():
    rep = run(avail={"RS": 3, "MP": 0, "ME": 2, "MS": 2})
    assert rep["passed"] and rep["n_reachable"] == 8
    assert rep["unreachable_heads"] == {"MP": "unavailable:fixture unavailable"}


@pytest.mark.parametrize("bad,needle", [
    ("foreign_owner", "MP:mp-1:foreign_owner"),
    ("ready_late", "MS:ms-1:ready_after_cut"),
    ("rs_overlap", "RS:rs-1:rs_family_overlaps_prefix_lineage"),
    ("rs_not_train", "RS:rs-1:rs_not_external_train_case"),
    ("unbound", "MP:mp-1:reading_does_not_bind_quoted_span"),
    ("token_lie", "ME:reading_tokens_not_native_count"),
    ("avail_lie", "MP:availability_0_but_read_ok"),
    ("reject_legal", "ME:availability_2_but_read_not_ready"),
    ("echo_lie", "legal_GET_"),
    ("mask_hide", "masked_MP_after_"),
    ("replay_drift", "a_replay_differs"),
    ("drift", "fresh_port_replay_differs"),
])
def test_harness_catches_each_fault_class(bad, needle):
    rep = run(bad=(bad,))
    assert not rep["passed"] and any(needle in f for f in rep["failures"]), rep["failures"]


def test_reject_legal_is_reported_as_unreachable_with_reason():
    rep = run(bad=("reject_legal",))
    assert rep["unreachable_heads"] == {"ME": "not_ready:fixture not_ready"}


def test_capacity_stress_rejected_read_never_advances_state():
    ctx = context()
    rep = replay_prefix(lambda: FixturePortV2(ctx), stress_factory=lambda: FixturePortV2(ctx, reserve=650))
    st = rep["capacity_stress"]
    assert rep["passed"] and st["passed"], rep["failures"]
    assert st["rejected_read_keeps_state"]["tested"] and st["rejected_read_keeps_state"]["ok"]
    assert st["n_reachable"] < 16 and any(r.endswith(":capacity") for r in st["masked_reasons"])
    assert st["renderer_id"] != rep["identity"]["renderer_id"]


def test_unbound_identity_is_refused():
    ctx = context()

    def mk():
        p = FixturePortV2(ctx)
        p.identity = dict(p.identity, renderer_id="unbound-renderer-pre-A6")
        return p
    with pytest.raises(ValueError, match="real reader identity"):
        replay_prefix(mk)


# ------------------------------------------------------------------ real WS-A bank-v0

class CharTokenizer:          # same convention as WS-A's test-only FixtureTokenizer; never a measurement
    identity = "unit_test_only_unicode_codepoints"
    native_context_tokens = 100000

    def count(self, text):
        return len(text)

    def prompt_tokens(self, prefix, readings):
        from metacom_pm.rl1v3.render.v0 import messages
        return len(canonical_json(messages(prefix, readings)))


CFG = dict(registry_dir="project/outputs/pm_rl1/v3/A1_preparation/final/registry",
           bank_dir="project/outputs/pm_rl1/v3/A1b_preparation/measured_v1/bank",
           expected_source="sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02",
           expected_bank="bank:02d0a4b1e62fd033c02b4fdc8e76d8796b285aa058cb59201aacde2c13ce8dd9")


@pytest.fixture(scope="module")
def real():
    from metacom_pm.rl1v3.env import a1b_port as P
    bank = P.load_bank(ROOT, **CFG)
    cov = [json.loads(x) for x in (ROOT / "project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl").read_text().splitlines()]
    return P, bank, cov


def _mk(P, bank, prefix, cls=None, reserve=320):
    cls = cls or P.A1bPort
    return lambda: cls(bank, prefix, CharTokenizer(), g_id="g-test-not-frozen", decode_id="not_run",
                       output_reserve_tokens=reserve)


def test_real_bank_prefix_replays_with_reader_identity_and_boundary(real):
    P, bank, cov = real
    row = next(r for r in cov if r["rank_bucket"] == "early")
    prefix = P.prefix_for(bank.registry, row)
    rep = replay_prefix(_mk(P, bank, prefix))
    assert rep["passed"], rep["failures"]
    assert rep["identity"]["bank_version"] == bank.version and rep["identity"]["index_version"] == bank.index_version
    assert rep["identity"]["renderer_id"].startswith("renderer:")
    assert rep["n_reachable"] == 2 ** sum(v > 0 for v in rep["availability"].values())
    assert any(p.get("ready_at_equals_cutoff") for p in rep["head_probe"].values())


def test_real_bank_tampered_ready_time_and_foreign_owner_are_caught(real):
    P, bank, cov = real
    prefix = P.prefix_for(bank.registry, cov[0])

    class Tampered(P.A1bPort):
        def records(self, ids):
            out = super().records(ids)
            return {i: (dataclasses.replace(r, ready_at=K.TimePoint(session_rank=self.prefix.cutoff_rank + 1))
                        if r.head == "MS" else
                        dataclasses.replace(r, owner_id="p_other",
                                            source_refs=tuple(dataclasses.replace(s, owner_id="p_other") for s in r.source_refs))
                        if r.head == "ME" else r) for i, r in out.items()}
    rep = replay_prefix(_mk(P, bank, prefix, Tampered))
    assert not rep["passed"]
    assert any(":ready_after_cut" in f for f in rep["failures"]) and any(":foreign_owner" in f for f in rep["failures"])


def test_real_prefix_must_equal_b0_identity(real):
    P, bank, cov = real
    with pytest.raises(ValueError, match="differs from B0"):
        P.prefix_for(bank.registry, dict(cov[0], prefix_id="0" * 64))


def test_ws_a_prefix_port_satisfies_v2_and_matches_the_b_adapter(real):
    """WS-A's own v0_port.PrefixPort runs the v2 harness and gives exactly the B adapter's terminals."""
    from metacom_pm.rl1v3.bank import v0_port as AP
    P, bank, cov = real
    row = next(r for r in cov if r["rank_bucket"] == "mid")
    prefix = P.prefix_for(bank.registry, row)
    ident = dict(g_id="g-test-not-frozen", decode_id="not_run", step2_id="none-v0-read-replay", output_reserve_tokens=320)
    fa = AP.PortFactory(bank, CharTokenizer(), ident)
    rep_a = replay_prefix(lambda: fa.for_prefix(prefix))
    rep_b = replay_prefix(_mk(P, bank, prefix))
    assert rep_a["passed"], rep_a["failures"]
    for k in ("key_by_subset", "reachable", "input_tokens_by_subset", "availability", "identity"):
        assert rep_a[k] == rep_b[k], k
