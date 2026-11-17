"""B5 real bank replay harness (``pmrl1v3-b5-bank-replay-v1``).

Runs one prefix through the C0-bound FiniteHead environment against a bank
port (WS-A A1b ``bank_v0.load`` + ``retrieve.search/read`` behind a thin shim)
and checks, without ever bypassing the action mask:

1. per-head GET from the root: ReadSuccess/ReadFailure, availability agreement;
2. provenance of every delivered record: bank version, head, owner, strict-past
   time (``verify_legal_span`` on every source span, ready/report rank),
   family closure (personal heads inside, RS outside the prefix lineage),
   token charge vs. the private mask size and native capacity;
3. full versioned TerminalKey per reachable subset;
4. every legal GET order of a subset gives ONE key, while ExecutionTraces differ;
5. a head masked for capacity really is rejected by the reader (probe only;
   the environment is never stepped through a masked action);
6. a missing terminal is PendingTerminal, never reward 0;
7. a fresh port replays identical record ids, reading hashes, tokens and keys.
The real number of reachable terminals is reported (it may be < 16).
"""
from __future__ import annotations

from typing import Callable, Mapping, Protocol

from ..io import object_sha256, sha256_text
from . import finite_head as E
from .c0_binding import C0FiniteHeadEnv, ReadRejected, TerminalIdentity, TerminalTable

REPLAY_PROTOCOL = "pmrl1v3-b5-bank-replay-v1"


class BankPort(Protocol):
    bank_version: str
    index_version: str
    native_context_tokens: int
    output_reserve_tokens: int

    def availability(self, prefix) -> Mapping[str, int]: ...
    def unit_tokens(self, prefix) -> Mapping[str, int]: ...
    def prefix_tokens(self, prefix) -> int: ...
    def read(self, prefix, head: str, *, input_tokens_before: int): ...
    def records(self, record_ids) -> Mapping[str, object]: ...


def _check_records(ctx, port, head, res) -> list[str]:
    from .. import contracts as K
    prefix, out = ctx.prefix, []
    recs = port.records(res.record_ids)
    sources = {(s.owner_id, s.session_id): s for s in ctx.sources}
    for rid in res.record_ids:
        rec = recs.get(rid)
        if rec is None:
            out.append(f"{head}:{rid}:record_missing")
            continue
        if rec.bank_version != port.bank_version:
            out.append(f"{head}:{rid}:bank_version")
        if rec.head != head:
            out.append(f"{head}:{rid}:head")
        if head == "RS":
            if rec.owner_id is not None:
                out.append(f"{head}:{rid}:rs_has_owner")
            if {rec.family_id, *rec.ancestor_family_ids} & set(prefix.ancestor_family_ids):
                out.append(f"{head}:{rid}:rs_family_overlaps_prefix_lineage")
            continue
        if rec.owner_id != prefix.owner_id:
            out.append(f"{head}:{rid}:foreign_owner")
        if rec.family_id not in prefix.ancestor_family_ids:
            out.append(f"{head}:{rid}:family_outside_closure")
        for t, label in ((rec.reported_at, "reported_at"), (rec.ready_at, "ready_at")):
            if t is not None and t.session_rank is not None and t.session_rank >= prefix.cutoff_rank:
                out.append(f"{head}:{rid}:{label}_not_strictly_past")
            if t is not None and t.date and prefix.timestamp and t.date > prefix.timestamp:
                out.append(f"{head}:{rid}:{label}_future_date")
        for span in rec.source_refs:
            src = sources.get((span.owner_id, span.session_id))
            try:
                if src is None:
                    raise ValueError("source not in legal context")
                K.verify_legal_span(span, prefix, src)
            except ValueError as exc:
                out.append(f"{head}:{rid}:illegal_span:{exc}")
    return out


def _probe(ctx, port) -> tuple[dict, list[str]]:
    avail, units = dict(port.availability(ctx.prefix)), dict(port.unit_tokens(ctx.prefix))
    p_tok = port.prefix_tokens(ctx.prefix)
    from .. import contracts as K
    probe, fails = {}, []
    for h in E.HEADS:
        if avail.get(h, 0) <= 0:
            probe[h] = dict(status="empty_pool")
            continue
        res = port.read(ctx.prefix, h, input_tokens_before=p_tok)
        if isinstance(res, K.ReadFailure):
            probe[h] = dict(status="rejected", reason=res.reason)
            if res.reason == "empty":
                fails.append(f"{h}:availability_says_nonempty_but_read_empty")
            continue
        charged = res.input_tokens_after - res.input_tokens_before
        probe[h] = dict(status="ok", record_ids=list(res.record_ids), charged_tokens=charged,
                        reading_tokens=res.reading.tokens, reading_sha256=sha256_text(res.reading.reading_text),
                        view=res.reading.view)
        if res.input_tokens_before != p_tok:
            fails.append(f"{h}:input_tokens_before_mismatch")
        if units.get(h) != charged:
            fails.append(f"{h}:mask_unit_tokens_{units.get(h)}_vs_charged_{charged}")
        fails += _check_records(ctx, port, h, res)
    return probe, fails


def _enumerate(ctx, port, identity: TerminalIdentity, table: TerminalTable) -> dict:
    from .. import contracts as K
    avail, units = dict(port.availability(ctx.prefix)), dict(port.unit_tokens(ctx.prefix))
    cap = port.native_context_tokens - port.output_reserve_tokens
    env = C0FiniteHeadEnv(
        prefix=ctx.prefix, history_sessions=len(ctx.history), availability=avail,
        read=lambda h, input_tokens_before: port.read(ctx.prefix, h, input_tokens_before=input_tokens_before),
        identity=identity, table=table, prefix_tokens=port.prefix_tokens(ctx.prefix),
        token_capacity=cap, unit_tokens=units, read_takes_tokens=True)
    keys, traces, readings, outcomes, fails, probes = {}, {}, {}, {}, [], []

    def visit(s):
        legal = env.legal_actions(s)
        key = env.terminal_key(s)
        trace = env.execution_trace(s)
        trace.verify_key(key)
        keys.setdefault(s.mask, set()).add(key.sha256)
        traces.setdefault(s.mask, set()).add(trace.sha256)
        readings.setdefault(s.mask, set()).add(object_sha256(sorted(
            (r.head, list(r.record_ids), sha256_text(r.reading_text), r.tokens) for r in s.readings)))
        try:
            _, reward, done, info = env.step(s, E.STOP)
            outcomes.setdefault(s.mask, set()).add(("reward", reward))
        except E.PendingTerminal:
            outcomes.setdefault(s.mask, set()).add(("pending", None))
        for h in E.HEADS:
            if h in s.order or avail.get(h, 0) <= 0:
                continue
            if E.GET[h] in legal:
                try:
                    visit(env.step(s, E.GET[h])[0])
                except ReadRejected as exc:
                    fails.append(f"legal_GET_{h}_rejected_after_{''.join(s.order) or 'root'}:{exc}")
            elif len(s.order) < env.max_gets:
                res = port.read(ctx.prefix, h, input_tokens_before=s.input_tokens)   # probe; never stepped
                ok = isinstance(res, K.ReadFailure) and res.reason == "capacity"
                probes.append(dict(after="".join(s.order) or "root", head=h, reader_rejects_capacity=ok))
                if not ok:
                    fails.append(f"mask_disagrees_with_reader:{h}_after_{''.join(s.order) or 'root'}")

    visit(env.reset())
    for m, ks in keys.items():
        if len(ks) != 1:
            fails.append(f"order_changed_key:{E.canonical_path(m)}")
        n_orders = len(traces[m])
        if n_orders != _n_orders(m):
            fails.append(f"trace_count_{n_orders}_vs_orders_{_n_orders(m)}:{E.canonical_path(m)}")
    return dict(keys={m: next(iter(v)) for m, v in keys.items()}, traces=traces, readings=readings,
                outcomes=outcomes, fails=fails, capacity_probes=probes, capacity=cap)


def _n_orders(mask: int) -> int:
    import math
    return math.factorial(bin(mask).count("1"))


def replay_prefix(ctx, port_factory: Callable[[], BankPort], identity: TerminalIdentity) -> dict:
    port = port_factory()
    probe, fails = _probe(ctx, port)
    empty = TerminalTable({}, table_id="replay-empty")
    first = _enumerate(ctx, port, identity, empty)
    fails += first["fails"]
    if any(kind != "pending" for m in first["outcomes"] for kind, _ in first["outcomes"][m]):
        fails.append("empty_table_gave_a_reward")
    off_key = first["keys"].get(0)
    one = TerminalTable({off_key: E.TerminalOutcome(reward=0.123, key_sha256=off_key)}, table_id="replay-off-only")
    second = _enumerate(ctx, port_factory(), identity, one)
    for m, outs in second["outcomes"].items():
        expect = {("reward", 0.123)} if m == 0 else {("pending", None)}
        if outs != expect:
            fails.append(f"pending_semantics:{E.canonical_path(m)}:{sorted(outs, key=str)}")
    same = (first["keys"] == second["keys"] and first["traces"] == second["traces"]
            and first["readings"] == second["readings"])
    if not same:
        fails.append("fresh_port_replay_differs")
    reach = sorted(first["keys"])
    unreachable = {}
    for h in E.HEADS:
        if not any(m & E.BIT[h] for m in reach):
            p = probe.get(h, {})
            unreachable[h] = p.get("reason") or p.get("status") or "masked"
            if p.get("status") == "ok":
                unreachable[h] = "capacity_masked_from_root"
    return dict(
        protocol=REPLAY_PROTOCOL, prefix_id=ctx.prefix.prefix_id, owner_id=ctx.prefix.owner_id,
        fold=ctx.row["assignment"]["fold"], bank_version=port.bank_version, index_version=port.index_version,
        identity=identity.__dict__, availability=dict(port.availability(ctx.prefix)),
        unit_tokens=dict(port.unit_tokens(ctx.prefix)), prefix_tokens=port.prefix_tokens(ctx.prefix),
        capacity=first["capacity"], head_probe=probe,
        reachable=[E.canonical_path(m) for m in reach], n_reachable=len(reach),
        n_orders=sum(len(first["traces"][m]) for m in reach), unreachable_heads=unreachable,
        key_by_subset={"+".join(E.heads_of(m)) or "OFF": first["keys"][m] for m in reach},
        capacity_probes=first["capacity_probes"], replay_identical=same, failures=sorted(set(fails)),
        passed=not fails)
