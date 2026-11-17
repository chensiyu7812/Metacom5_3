"""A-owned, stateless read port over the preserved A1/A1b snapshots.

``make_port_factory(census_sources)`` supports the original B5 factory shape.
``factory.for_prefix(prefix)`` exposes the equivalent prefix-bound port for
B5 v2. Both require actual acquired ReadingViews; a token total cannot stand
in for read history. No source/bank rebuild, weights, model or network call.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from time import perf_counter
import json

from .. import contracts as K
from ..retrieve.v0 import Reader, search
from ..sources import source_registry as S
from . import bank_v0 as B

PROTOCOL = "pmrl1v3-a1b-read-port-v1"
CONFIG = "project/configs/rl1v3/bank_v0_port.json"


class _StaticReader(Reader):
    @lru_cache(maxsize=4)
    def _search(self, head):
        # A Reader owns one immutable bank snapshot and one verified prefix.
        return search(self.bank, head, self.prefix)


class PrefixPort:
    """Private executor/audit interface; only successful readings are public."""
    protocol = PROTOCOL
    supports_read_context = True

    def __init__(self, bank, prefix, tokenizer, **identity):
        bank.registry.context(prefix)
        self.bank, self.prefix, self.tokenizer = bank, prefix, tokenizer
        self.reader = _StaticReader(bank, prefix, tokenizer, **identity)
        self.bank_version, self.index_version = bank.version, bank.index_version
        self.native_context_tokens = tokenizer.native_context_tokens
        self.output_reserve_tokens = self.reader.output_reserve_tokens
        self.base_tokens = self.reader.base_tokens
        self._validated = {(): self.base_tokens}
        self._plans = {}

    @property
    def identity(self):
        return dict(self.reader.identity)

    def legal_sessions(self):
        """Strictly-past same-owner sessions, never the full current session."""
        return self.bank.registry.context(self.prefix)[1]

    def availability(self):
        return {h: len(self.reader._search(h).ranked) for h in K.HEAD_ORDER}

    def _context(self, acquired, input_tokens_before):
        acquired = tuple(acquired)
        if any(not isinstance(v, K.ReadingView) for v in acquired):
            raise ValueError("acquired must contain C0 ReadingViews")
        stamp = tuple(v.sha256 for v in acquired)
        if stamp not in self._validated:
            before, previous = self.base_tokens, ()
            for expected in acquired:
                result = self.reader.read(expected.head, acquired=previous,
                                          input_tokens_before=before)
                if not isinstance(result, K.ReadSuccess) or result.reading != expected:
                    raise ValueError("acquired view is not a successful read of this prefix/bank")
                previous += (expected,)
                before = result.input_tokens_after
            self._validated[stamp] = before
        before = self._validated[stamp]
        if input_tokens_before is not None:
            if type(input_tokens_before) is not int or input_tokens_before < 0:
                raise ValueError("input_tokens_before must be a nonnegative integer")
            if input_tokens_before != before:
                raise ValueError("input_tokens_before does not match the acquired read ledger")
        return acquired, before, stamp

    def _plan(self, head, acquired, before, stamp):
        key = (head, stamp, before)
        if key not in self._plans:
            self._plans[key] = self.reader.measure(
                head, acquired=acquired, input_tokens_before=before,
                bank_version=self.bank_version, index_version=self.index_version)
        return self._plans[key]

    def unit_tokens(self, *, acquired=(), input_tokens_before=None):
        """Private exact delta at this state, including units exceeding capacity.

        Missing candidates are represented by availability=0. Integrity errors
        raise, rather than quietly turning into an unavailable action.
        """
        acquired, before, stamp = self._context(acquired, input_tokens_before)
        units = {}
        for head, count in self.availability().items():
            if not count or head in {v.head for v in acquired}:
                continue
            plan = self._plan(head, acquired, before, stamp)
            if isinstance(plan, K.ReadFailure):
                raise ValueError(f"cannot size {head}: {plan.reason}: {plan.detail}")
            units[head] = plan.input_tokens_after - before
        return units

    def read(self, head, *, acquired=(), input_tokens_before=None,
             bank_version=None, index_version=None):
        start = perf_counter()
        try:
            acquired, before, stamp = self._context(acquired, input_tokens_before)
        except ValueError as exc:
            unchanged = input_tokens_before if type(input_tokens_before) is int and input_tokens_before >= 0 else self.base_tokens
            return K.ReadFailure(reason="integrity", detail=str(exc),
                                 input_tokens_unchanged=unchanged,
                                 elapsed_ms=(perf_counter()-start)*1000)
        if ((bank_version is not None and bank_version != self.bank_version) or
                (index_version is not None and index_version != self.index_version)):
            return K.ReadFailure(reason="integrity", detail="version_mismatch",
                                 input_tokens_unchanged=before, elapsed_ms=(perf_counter()-start)*1000)
        plan = self._plan(head, acquired, before, stamp)
        if isinstance(plan, K.ReadFailure):
            return K.ReadFailure(reason=plan.reason, detail=plan.detail,
                                 input_tokens_unchanged=before, elapsed_ms=(perf_counter()-start)*1000)
        if plan.input_tokens_after + self.output_reserve_tokens > self.native_context_tokens:
            return K.ReadFailure(reason="capacity", detail="whole_unit_exceeds_native_context; no truncation or substitution",
                                 input_tokens_unchanged=before, elapsed_ms=(perf_counter()-start)*1000)
        view = K.ReadingView(head=plan.head, view=plan.view, ordinal=plan.ordinal,
                             reading_text=plan.reading_text, reported_at=plan.reported_at,
                             tokens=plan.tokens, stage=plan.stage, expandable=False)
        result = K.ReadSuccess(reading=view, record_ids=plan.record_ids,
                               input_tokens_before=before, input_tokens_after=plan.input_tokens_after,
                               native_context_tokens=self.native_context_tokens,
                               output_reserve_tokens=self.output_reserve_tokens,
                               elapsed_ms=(perf_counter()-start)*1000)
        self._validated[(*stamp, view.sha256)] = result.input_tokens_after
        return result

    def action_mask(self, acquired=(), *, input_tokens_before=None):
        return tuple("GET_"+h for h in K.HEAD_ORDER if isinstance(
            self.read(h, acquired=acquired, input_tokens_before=input_tokens_before), K.ReadSuccess)) + ("STOP",)

    def records(self, record_ids):
        return {rid: self.bank.by_id[rid] for rid in record_ids if rid in self.bank.by_id}

    def source(self, owner_id, session_id):
        """Private provenance lookup for audit; not a policy/writer history API."""
        return self.bank.registry.entry(owner_id, session_id).source

    def verify_records(self, record_ids):
        errors = []
        if not record_ids:
            return ["empty_record_group"]
        for rid in record_ids:
            record = self.bank.by_id.get(rid)
            if record is None:
                errors.append(f"{rid}:missing_record")
                continue
            if record.bank_version != self.bank_version:
                errors.append(f"{rid}:bank_version")
            reason = self.bank.reason(record, self.prefix)
            if reason:
                errors.append(f"{rid}:{reason}")
            if record.related_claim_ids or record.relation_index_version:
                errors.append(f"{rid}:unverified_relation_propagation")
            for span in record.source_refs:
                try:
                    source = self.source(span.owner_id, span.session_id)
                    span.verify(source)
                    if record.head != "RS":
                        K.verify_legal_span(span, self.prefix, source)
                except (KeyError, ValueError) as exc:
                    errors.append(f"{rid}:illegal_source_span:{exc}")
        return errors

    def count_tokens(self, text):
        return self.tokenizer.count(text)

    def token_account(self, acquired=()):
        acquired, billed, _ = self._context(acquired, None)
        return dict(native_prompt_tokens=self.tokenizer.prompt_tokens(self.prefix, acquired),
                    billed_input_tokens=billed, delivered_reading_tokens=sum(v.tokens for v in acquired),
                    native_context_tokens=self.native_context_tokens,
                    output_reserve_tokens=self.output_reserve_tokens,
                    billing_rule="max(previous_bill + native_reading_tokens, native_full_prompt)")

    def terminal_key(self, results):
        return self.reader.terminal_key(results)

    def execution_trace(self, results):
        key = self.terminal_key(results)
        trace = K.ExecutionTrace(domain_id="finite_head_v1",
            ordered_path=tuple("GET_"+r.reading.head for r in results)+("STOP",),
            acquired=tuple(r.record_ids for r in results), readings=tuple(r.reading for r in results))
        trace.verify_key(key)
        return trace

    def replay(self, key):
        return self.reader.replay(key)


class RoutingPort:
    """Original B5 factory convention, with explicit context for non-root GETs."""
    protocol = PROTOCOL
    supports_read_context = True

    def __init__(self, factory):
        self.factory, self._ports = factory, {}
        self.bank_version = factory.bank.version
        self.index_version = factory.bank.index_version
        self.native_context_tokens = factory.tokenizer.native_context_tokens
        self.output_reserve_tokens = factory.identity["output_reserve_tokens"]

    def for_prefix(self, prefix):
        self.factory.bank.registry.context(prefix)
        if prefix.sha256 not in self._ports:
            self._ports[prefix.sha256] = self.factory.for_prefix(prefix)
        return self._ports[prefix.sha256]

    def availability(self, prefix):return self.for_prefix(prefix).availability()
    def prefix_tokens(self, prefix):return self.for_prefix(prefix).base_tokens
    def terminal_identity(self, prefix):return self.for_prefix(prefix).identity
    def legal_sessions(self, prefix):return self.for_prefix(prefix).legal_sessions()
    def unit_tokens(self, prefix, **kwargs):return self.for_prefix(prefix).unit_tokens(**kwargs)
    def read(self, prefix, head, **kwargs):return self.for_prefix(prefix).read(head, **kwargs)
    def replay(self, prefix, key):return self.for_prefix(prefix).replay(key)
    def verify_records(self, prefix, record_ids):return self.for_prefix(prefix).verify_records(record_ids)
    def records(self, record_ids):return {rid:self.factory.bank.by_id[rid] for rid in record_ids if rid in self.factory.bank.by_id}


class PortFactory:
    def __init__(self, bank, tokenizer, identity):
        self.bank, self.registry, self.tokenizer = bank, bank.registry, tokenizer
        self.identity = dict(identity)

    def __call__(self, prefix=None):
        return RoutingPort(self) if prefix is None else self.for_prefix(prefix)

    def for_prefix(self, prefix):
        return PrefixPort(self.bank, prefix, self.tokenizer, **self.identity)

    def prefix(self, row):
        prefix = self.registry.prefix(row["owner_id"], row["session_id"], row["cut_turn"])
        if prefix.prefix_id != row["prefix_id"]:
            raise ValueError("registry prefix differs from B0")
        return prefix


def load_bank(root=None, *, config=None):
    """Load and verify preserved snapshots; building is explicitly B.build()."""
    root = Path(root) if root else Path(__file__).resolve().parents[5]
    cfg = dict(config) if config is not None else json.loads((root/CONFIG).read_text())
    if cfg["protocol"] != PROTOCOL:
        raise ValueError("unsupported read port configuration")
    registry = S.load(root/cfg["registry_dir"])
    if registry.version != cfg["expected_source"]:
        raise ValueError("source version mismatch")
    bank = B.load(root/cfg["bank_dir"], registry, expected_version=cfg["expected_bank"])
    if bank.index_version != cfg["expected_index"]:
        raise ValueError("index version mismatch")
    return bank, cfg


def make_port_factory(census_sources=None, *, root=None, config=None, tokenizer=None, reader_identity=None):
    root = Path(root) if root else Path(__file__).resolve().parents[5]
    bank, cfg = load_bank(root, config=config)
    if census_sources is not None:
        for entry in bank.registry.entries:
            source = entry.source
            if entry.availability_scope != "personal_history":continue
            other = census_sources.source_session(source.owner_id, source.session_id)
            fields = ("owner_id", "session_id", "chronological_rank", "date", "dataset", "family_id", "transcript_sha256")
            if any(getattr(source, k) != getattr(other, k) for k in fields) or tuple(
                    (t.role,t.text) for t in source.turns) != tuple((t.role,t.text) for t in other.turns):
                raise ValueError("A registry/B census source mismatch")
    if tokenizer is None:
        from ..retrieve.native_tokens import NativeTokenizer
        tokenizer = NativeTokenizer(cfg["tokenizer_model"], root/cfg["asset_manifest"])
    elif reader_identity is None:
        raise ValueError("an injected tokenizer requires an explicit reader identity")
    return PortFactory(bank, tokenizer, reader_identity or cfg["reader_identity"])
