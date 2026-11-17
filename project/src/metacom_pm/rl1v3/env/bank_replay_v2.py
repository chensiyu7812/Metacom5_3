"""B5 real bank replay harness v2 (``pmrl1v3-b5-bank-replay-v2``).

v1 (``bank_replay.py``) is kept unchanged for its history and tests.  v2 closes
the five cross-line gaps the integration owner recorded against A1b
(``WSB_S1_C0_FROZEN_SYNC_20261117``):

1. the port reads with the state's *actual acquired ReadingViews* (A1b
   ``Reader.read(head, acquired=...)`` is stateless), never a token total;
2. GET legality is the reader's dynamic full chat-template capacity mask,
   intersected with the static rules; the old static unit-token mask is only
   reported as a diagnostic, and a rejected read never advances the state
   (checked on real records under a capacity-stress port);
3. completed-session boundary: personal ``ready_at.session_rank <= cutoff`` is
   legal (``>`` rejected), while ``reported_at`` / source rank stay strictly
   before the cut and dates never after the prefix;
4. the TerminalKey identity is the real ``Reader.identity`` (bank, index,
   renderer incl. tokenizer, Step-2, G, decode) - no ``unbound-*`` values;
5. RS cases are only checked as external train-split cases; they are not a
   method catalog.

Per prefix it checks: root GET per head vs availability; provenance of every
delivered record (owner, strict-past time, family closure, every source span
legal, reading text binds the quoted spans, native token count, capacity);
one key per reachable subset with k! distinct traces; WS-A ``replay(key)``
reproduces each canonical trace; missing terminal = PendingTerminal; a fresh
port gives identical ids, text hashes, tokens and keys.  The real reachable
count is reported (may be < 16); the action mask is never bypassed.
"""
from __future__ import annotations

import math
from typing import Callable, Mapping, Protocol

from ..io import object_sha256, sha256_text
from . import finite_head as E
from .c0_binding import C0FiniteHeadEnv, ReadRejected, TerminalIdentity, TerminalTable

REPLAY_PROTOCOL = "pmrl1v3-b5-bank-replay-v2"


class BankPortV2(Protocol):
    """One port per prefix (wraps a WS-A ``retrieve.Reader``)."""
    prefix: object
    identity: Mapping[str, str]             # Reader.identity: the six TerminalIdentity fields
    native_context_tokens: int
    output_reserve_tokens: int
    base_tokens: int

    def availability(self) -> Mapping[str, int]: ...
    def read(self, head: str, *, acquired: tuple): ...
    def action_mask(self, acquired: tuple) -> tuple[str, ...]: ...
    def records(self, record_ids) -> Mapping[str, object]: ...
    def source(self, owner_id: str, session_id: str): ...
    def count_tokens(self, text: str) -> int: ...
    def replay(self, key): ...


def check_records(prefix, port, head, res) -> list[str]:
    """Provenance of every record a successful read delivered (independent of A's filters)."""
    from .. import contracts as K
    out = []
    recs = port.records(res.record_ids)
    text = res.reading.reading_text
    for rid in res.record_ids:
        rec = recs.get(rid)
        tag = f"{head}:{rid}"
        if rec is None:
            out.append(f"{tag}:record_missing")
            continue
        if rec.bank_version != port.identity["bank_version"]:
            out.append(f"{tag}:bank_version")
        if rec.head != head or rec.view != res.reading.view:
            out.append(f"{tag}:head_or_view")
        if not rec.source_refs:
            out.append(f"{tag}:no_source_refs")
        for span in rec.source_refs:
            if span.exact_quote and span.exact_quote not in text:
                out.append(f"{tag}:reading_does_not_bind_quoted_span")
                break
        if head == "RS":
            if rec.owner_id is not None:
                out.append(f"{tag}:rs_has_owner")
            if rec.origin_dataset != "ESConv" or rec.source_split != "train":
                out.append(f"{tag}:rs_not_external_train_case")
            if {rec.family_id, *rec.ancestor_family_ids} & set(prefix.ancestor_family_ids):
                out.append(f"{tag}:rs_family_overlaps_prefix_lineage")
            for span in rec.source_refs:
                try:
                    src = port.source(span.owner_id, span.session_id)
                    if src.dataset != "ESConv":
                        raise ValueError("RS span outside ESConv")
                    span.verify(src)
                except (KeyError, ValueError) as exc:
                    out.append(f"{tag}:rs_span:{exc}")
            continue
        if rec.owner_id != prefix.owner_id:
            out.append(f"{tag}:foreign_owner")
        if rec.family_id not in prefix.ancestor_family_ids:
            out.append(f"{tag}:family_outside_closure")
        if rec.source_rank is None or rec.source_rank >= prefix.cutoff_rank:
            out.append(f"{tag}:source_rank_not_strictly_past")
        rep, rdy = rec.reported_at, rec.ready_at
        if rep is None or rep.session_rank is None or rep.session_rank >= prefix.cutoff_rank:
            out.append(f"{tag}:reported_at_not_strictly_past")
        if rdy is None or rdy.session_rank is None or rdy.session_rank > prefix.cutoff_rank:
            out.append(f"{tag}:ready_after_cut")         # == cutoff: completed-session boundary, legal
        for t, label in ((rep, "reported_at"), (rdy, "ready_at")):
            if t is not None and t.date and prefix.timestamp and t.date > prefix.timestamp:
                out.append(f"{tag}:{label}_future_date")
        for span in rec.source_refs:
            try:
                K.verify_legal_span(span, prefix, port.source(span.owner_id, span.session_id))
            except (KeyError, ValueError) as exc:
                out.append(f"{tag}:illegal_span:{exc}")
    if res.reading.tokens != port.count_tokens(text):
        out.append(f"{head}:reading_tokens_not_native_count")
    if res.input_tokens_after + res.output_reserve_tokens > res.native_context_tokens:
        out.append(f"{head}:exceeds_native_capacity")
    return out


def _probe(port) -> tuple[dict, list[str]]:
    from .. import contracts as K
    avail = dict(port.availability())
    probe, fails = {}, []
    for h in E.HEADS:
        res = port.read(h, acquired=())
        if isinstance(res, K.ReadFailure):
            probe[h] = dict(status="rejected", reason=res.reason, detail=res.detail, availability=avail.get(h, 0))
            if res.input_tokens_unchanged != port.base_tokens:
                fails.append(f"{h}:failed_read_changed_tokens")
            if avail.get(h, 0) > 0 and res.reason != "capacity":    # legal candidates exist: only capacity may refuse
                fails.append(f"{h}:availability_{avail.get(h)}_but_read_{res.reason}")
            continue
        if avail.get(h, 0) <= 0:
            fails.append(f"{h}:availability_0_but_read_ok")
        probe[h] = dict(status="ok", availability=avail.get(h, 0), record_ids=list(res.record_ids),
                        reading_tokens=res.reading.tokens,
                        charged_tokens=res.input_tokens_after - res.input_tokens_before,
                        reading_sha256=sha256_text(res.reading.reading_text), view=res.reading.view,
                        ready_at_equals_cutoff=sorted(
                            rid for rid, r in port.records(res.record_ids).items()
                            if r.ready_at is not None and r.ready_at.session_rank == port.prefix.cutoff_rank))
        if res.input_tokens_before != port.base_tokens:
            fails.append(f"{h}:input_tokens_before_{res.input_tokens_before}_vs_base_{port.base_tokens}")
        fails += check_records(port.prefix, port, h, res)
    return probe, fails


def _identity(port) -> TerminalIdentity:
    ident = TerminalIdentity(**{k: port.identity[k] for k in TerminalIdentity.__dataclass_fields__})
    if any(str(v).startswith("unbound") for v in ident.__dict__.values()):
        raise ValueError("v2 replay requires the real reader identity, not unbound placeholders")
    return ident


def _env(port, table, *, dynamic=True):
    return C0FiniteHeadEnv(
        prefix=port.prefix, history_sessions=port.prefix.cutoff_rank, availability=dict(port.availability()),
        read=lambda h, acquired: port.read(h, acquired=acquired), identity=_identity(port), table=table,
        prefix_tokens=port.base_tokens, read_takes_acquired=True,
        dynamic_mask=port.action_mask if dynamic else None)


def _enumerate(port, table, *, static_units: Mapping[str, int] | None = None) -> dict:
    from .. import contracts as K
    env = _env(port, table)
    cap = port.native_context_tokens - port.output_reserve_tokens
    keys, traces, readings, outcomes, fails, masked, static_diff = {}, {}, {}, {}, [], [], []
    totals = {}
    canonical = {}

    def visit(s):
        legal = env.legal_actions(s)
        acquired = env.readings(s)
        reader_mask = set(port.action_mask(acquired))
        if set(legal) != reader_mask:
            fails.append(f"env_mask_differs_from_reader_after_{''.join(s.order) or 'root'}")
        key, trace = env.terminal_key(s), env.execution_trace(s)
        trace.verify_key(key)
        keys.setdefault(s.mask, set()).add(key.sha256)
        traces.setdefault(s.mask, set()).add(trace.sha256)
        readings.setdefault(s.mask, set()).add(object_sha256(sorted(
            (r.head, list(r.record_ids), sha256_text(r.reading_text), r.public_view.tokens) for r in s.readings)))
        totals.setdefault(s.mask, set()).add(s.input_tokens)
        if s.order == tuple(h for h in E.HEADS if h in s.order):
            canonical[s.mask] = (key, s)
        try:
            env.step(s, E.STOP)
            outcomes.setdefault(s.mask, set()).add("reward")
        except E.PendingTerminal:
            outcomes.setdefault(s.mask, set()).add("pending")
        for h in E.HEADS:
            if h in s.order:
                continue
            if static_units is not None and h in static_units and env.availability[h] > 0:
                static_ok = s.input_tokens + static_units[h] <= cap
                if static_ok != (E.GET[h] in legal):
                    static_diff.append(dict(after="".join(s.order) or "root", head=h,
                                            static=static_ok, dynamic=E.GET[h] in legal))
            if E.GET[h] in legal:
                try:
                    nxt = env.step(s, E.GET[h])[0]
                except ReadRejected as exc:
                    fails.append(f"legal_GET_{h}_rejected_after_{''.join(s.order) or 'root'}:{exc}")
                    continue
                if nxt.readings[-1].public_view.ordinal != len(nxt.order):
                    fails.append(f"ordinal_after_{''.join(nxt.order)}")
                visit(nxt)
            else:
                res = port.read(h, acquired=acquired)      # probe only; the env is never stepped
                reason = res.reason if isinstance(res, K.ReadFailure) else "read_ok_but_masked"
                masked.append(dict(after="".join(s.order) or "root", head=h, reason=reason))
                if not isinstance(res, K.ReadFailure):
                    fails.append(f"masked_{h}_after_{''.join(s.order) or 'root'}_but_reader_succeeds")
                elif res.input_tokens_unchanged != s.input_tokens:
                    fails.append(f"failed_{h}_after_{''.join(s.order) or 'root'}_reports_other_tokens")

    visit(env.reset())
    for m, ks in keys.items():
        if len(ks) != 1:
            fails.append(f"order_changed_key:{E.canonical_path(m)}")
        if len(traces[m]) != math.factorial(bin(m).count("1")):
            fails.append(f"trace_count_{len(traces[m])}:{E.canonical_path(m)}")
        if len(readings[m]) != 1:
            fails.append(f"order_changed_reading_content:{E.canonical_path(m)}")
        if len(totals[m]) != 1:      # per-unit charges may differ by order; the subset total may not
            fails.append(f"order_changed_input_tokens:{E.canonical_path(m)}:{sorted(totals[m])}")
    for m, (key, s) in canonical.items():        # WS-A replay must reproduce the canonical trace
        res = port.replay(key)
        if isinstance(res, K.ReadFailure):
            fails.append(f"a_replay_failed:{E.canonical_path(m)}:{res.reason}")
            continue
        mine = env.execution_trace(s)
        if (res.acquired != mine.acquired or
                [(r.head, r.reading_text, r.tokens) for r in res.readings] !=
                [(r.head, r.reading_text, r.tokens) for r in mine.readings]):
            fails.append(f"a_replay_differs:{E.canonical_path(m)}")
    return dict(keys={m: next(iter(v)) for m, v in keys.items()}, traces=traces, readings=readings,
                input_tokens={m: next(iter(v)) for m, v in totals.items()},
                outcomes=outcomes, fails=fails, masked=masked, static_mask_disagreements=static_diff,
                capacity=cap)


def _rejected_read_keeps_state(port) -> dict:
    """Under a port whose capacity rejects some head, step a STATIC-mask env into
    that head: the read must be rejected, the state object unchanged and the
    next successful read still gets ordinal n+1."""
    from .. import contracts as K
    env = _env(port, TerminalTable({}, table_id="stress"), dynamic=False)
    s = env.reset()
    for _ in range(len(E.HEADS)):
        bad = [h for h in E.HEADS if h not in s.order and env.availability[h] > 0
               and isinstance(port.read(h, acquired=env.readings(s)), K.ReadFailure)]
        good = [h for h in E.HEADS if h not in s.order and env.availability[h] > 0 and h not in bad]
        if bad:
            before = (s.order, s.input_tokens, len(s.readings))
            try:
                env.step(s, E.GET[bad[0]])
                return dict(tested=True, ok=False, why="rejected read advanced")
            except ReadRejected:
                pass
            if (s.order, s.input_tokens, len(s.readings)) != before:
                return dict(tested=True, ok=False, why="state mutated")
            if good:
                nxt = env.step(s, E.GET[good[0]])[0]
                return dict(tested=True, ok=nxt.readings[-1].public_view.ordinal == len(s.order) + 1,
                            after="".join(s.order) or "root", rejected=bad[0], then=good[0])
            return dict(tested=True, ok=True, after="".join(s.order) or "root", rejected=bad[0], then=None)
        if not good:
            break
        s = env.step(s, E.GET[good[0]])[0]
    return dict(tested=False, ok=True, why="no capacity rejection under this port")


def replay_prefix(port_factory: Callable[[], BankPortV2], *, fresh_factory: Callable[[], BankPortV2] | None = None,
                  stress_factory: Callable[[], BankPortV2] | None = None, meta: Mapping | None = None) -> dict:
    port = port_factory()
    ident = _identity(port)
    probe, fails = _probe(port)
    units = {h: p["charged_tokens"] for h, p in probe.items() if p["status"] == "ok"}
    first = _enumerate(port, TerminalTable({}, table_id="replay-empty"), static_units=units)
    fails += first["fails"]
    if any(o != {"pending"} for o in first["outcomes"].values()):
        fails.append("empty_table_gave_a_reward")
    off_key = first["keys"][0]
    table = TerminalTable({off_key: E.TerminalOutcome(reward=0.123, key_sha256=off_key)}, table_id="replay-off-only")
    second = _enumerate((fresh_factory or port_factory)(), table)
    for m, outs in second["outcomes"].items():
        if outs != ({"reward"} if m == 0 else {"pending"}):
            fails.append(f"pending_semantics:{E.canonical_path(m)}:{sorted(outs)}")
    same = (first["keys"] == second["keys"] and first["traces"] == second["traces"]
            and first["readings"] == second["readings"])
    if not same:
        fails.append("fresh_port_replay_differs")
    reach = sorted(first["keys"])
    unreachable = {}
    for h in E.HEADS:
        if not any(m & E.BIT[h] for m in reach):
            p = probe[h]
            unreachable[h] = (f"{p['reason']}:{p['detail']}" if p["status"] == "rejected"
                              else "masked_from_root")
    stress = None
    if stress_factory is not None:
        sp = stress_factory()
        s_probe, s_fails = _probe(sp)
        s_enum = _enumerate(sp, TerminalTable({}, table_id="stress-empty"), static_units=units)
        keeps = _rejected_read_keeps_state(sp)
        s_fails += s_enum["fails"] + ([] if keeps["ok"] else [f"rejected_read_advanced_state:{keeps}"])
        stress = dict(capacity=s_enum["capacity"], output_reserve_tokens=sp.output_reserve_tokens,
                      renderer_id=sp.identity["renderer_id"],
                      n_reachable=len(s_enum["keys"]), reachable=["+".join(E.heads_of(m)) or "OFF" for m in sorted(s_enum["keys"])],
                      masked_reasons=sorted({f"{x['head']}:{x['reason']}" for x in s_enum["masked"]}),
                      static_mask_disagreements=s_enum["static_mask_disagreements"],
                      rejected_read_keeps_state=keeps, failures=sorted(set(s_fails)), passed=not s_fails)
        fails += [f"stress:{f}" for f in s_fails]
    return dict(
        protocol=REPLAY_PROTOCOL, prefix_id=port.prefix.prefix_id, owner_id=port.prefix.owner_id,
        session_id=port.prefix.session_id, cut_turn=port.prefix.cut_turn, cutoff_rank=port.prefix.cutoff_rank,
        fold=port.prefix.fold, **dict(meta or {}), identity=ident.__dict__, availability=dict(port.availability()),
        base_tokens=port.base_tokens, capacity=first["capacity"], head_probe=probe,
        reachable=["+".join(E.heads_of(m)) or "OFF" for m in reach], n_reachable=len(reach),
        n_orders=sum(len(first["traces"][m]) for m in reach), unreachable_heads=unreachable,
        key_by_subset={"+".join(E.heads_of(m)) or "OFF": first["keys"][m] for m in reach},
        input_tokens_by_subset={"+".join(E.heads_of(m)) or "OFF": first["input_tokens"][m] for m in reach},
        masked_probes=first["masked"], static_mask_disagreements=first["static_mask_disagreements"],
        capacity_stress=stress, replay_identical=same, failures=sorted(set(fails)), passed=not fails)
