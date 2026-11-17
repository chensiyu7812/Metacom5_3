"""B5: bind the FiniteHead core to the shared C0 0.2.x contracts (Phase-1 only).

* Observation is the C0 ``Observation`` (domain ``finite_head_v1``) built only
  from the visible prefix, delivered ``ReadingView``s (renumbered by actual
  acquisition order), legal-pool availability, the action mask and input
  tokens.  Record ids never enter it.
* GET calls only the injected WS-A ``read(head) -> ReadSuccess | ReadFailure``;
  a ``ReadFailure`` raises ``ReadRejected`` and leaves the state unchanged.
  With ``read_takes_tokens`` the reader is ``read(head, input_tokens_before=n)``
  (real A1b reads charge against the current input); the reply must echo ``n``
  and the state advances by the charged ``input_tokens_after - n``.
* STOP builds the full versioned ``TerminalKey`` (prefix context, bank/index,
  renderer, Step-2, G, decode, canonical subset path, per-action record
  groups) plus the ``ExecutionTrace`` with the real order, checks that the
  trace reproduces the key, then looks the key up in a versioned terminal
  table.  A missing key is ``PendingTerminal`` - never reward zero.
* Phase-2 actions (``EXPAND_MS(j)``) are not part of this domain; the core
  rejects them and C0 rejects them for ``finite_head_v1`` keys.

Contracts are imported lazily so this module can live on a branch that does
not yet carry C0.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Callable, Mapping

from . import finite_head as E

DOMAIN = "finite_head_v1"


def contracts():
    from metacom_pm.rl1v3 import contracts as K
    return K


class ReadRejected(E.IllegalAction):
    """WS-A read returned ReadFailure; no reading, no ordinal, state unchanged."""


@dataclass(frozen=True)
class TerminalIdentity:
    """Every non-path TerminalKey field that can change the reply."""
    bank_version: str
    index_version: str
    renderer_id: str
    step2_id: str
    g_id: str
    decode_id: str


class TerminalTable:
    """Versioned terminal outcomes keyed by the full ``TerminalKey.sha256``."""

    def __init__(self, rows: Mapping[str, E.TerminalOutcome], *, table_id: str):
        self.rows, self.table_id = dict(rows), table_id

    def lookup(self, key) -> E.TerminalOutcome:
        out = self.rows.get(key.sha256)
        if out is None:
            raise E.PendingTerminal(f"{self.table_id}: no terminal for {key.ordered_path}")
        return out


class C0FiniteHeadEnv(E.FiniteHeadEnv):
    def __init__(self, *, prefix, history_sessions: int, availability: Mapping[str, int],
                 read: Callable[[str], object], identity: TerminalIdentity, table: TerminalTable,
                 prefix_tokens: int, token_capacity: int | None = None,
                 unit_tokens: Mapping[str, int] | None = None, read_takes_tokens: bool = False):
        self.K = contracts()
        if not self.K.SCHEMA_VERSION.startswith("pmrl1v3-contracts-0.2"):
            raise RuntimeError("B5 binding targets C0 0.2.x")
        if prefix.identity_scope != "v3":
            raise ValueError("only V3 prefixes can own terminals")
        self.prefix, self.history_sessions = prefix, history_sessions
        self.identity, self.table, self._read = identity, table, read
        super().__init__(availability=availability, reader=self._reader,
                         terminal_lookup=self._lookup, prefix_tokens=prefix_tokens,
                         token_capacity=token_capacity, max_gets=len(E.HEADS),
                         unit_tokens=unit_tokens, visible_prefix=prefix.visible(),
                         lookup_takes_state=True, reader_takes_tokens=read_takes_tokens)

    # ------------------------------------------------------------ GET
    def _reader(self, head: str, input_tokens: int | None = None) -> E.ReadUnit:
        res = self._read(head) if input_tokens is None else self._read(
            head, input_tokens_before=input_tokens)
        if isinstance(res, self.K.ReadFailure):
            raise ReadRejected(f"GET_{head}: {res.reason}: {res.detail}")
        if not isinstance(res, self.K.ReadSuccess) or res.reading.head != head:
            raise ReadRejected(f"GET_{head}: reader returned a mismatched result")
        tokens = res.reading.tokens
        if input_tokens is not None:
            if res.input_tokens_before != input_tokens:
                raise ReadRejected(f"GET_{head}: reader charged against {res.input_tokens_before}"
                                   f" tokens, state has {input_tokens}")
            tokens = res.input_tokens_after - input_tokens
        return E.ReadUnit(head=head, reading_text=res.reading.reading_text,
                          tokens=tokens, record_ids=tuple(res.record_ids),
                          cost_s=res.elapsed_ms / 1000.0, public_view=res.reading)

    # ------------------------------------------------------- views
    def readings(self, s: E.State) -> tuple:
        return tuple(dataclasses.replace(r.public_view, ordinal=i + 1)
                     for i, r in enumerate(s.readings))

    def observe(self, s: E.State):
        K = self.K
        return K.Observation(
            domain_id=DOMAIN, history_sessions=self.history_sessions, prefix=self.visible_prefix,
            acquired=self.readings(s),
            availability=tuple(K.HeadAvailability(head=h, available=self.availability[h] > 0,
                                                  count=self.availability[h]) for h in E.HEADS),
            action_mask=self.legal_actions(s), input_tokens=s.input_tokens)

    def terminal_key(self, s: E.State):
        return self.K.TerminalKey.for_prefix(
            self.prefix, domain_id=DOMAIN,
            ordered_path=tuple(E.GET[h] for h in s.order) + (E.STOP,),
            acquired=tuple(r.record_ids for r in s.readings),
            **dataclasses.asdict(self.identity))

    def execution_trace(self, s: E.State):
        return self.K.ExecutionTrace(
            domain_id=DOMAIN, ordered_path=tuple(E.GET[h] for h in s.order) + (E.STOP,),
            acquired=tuple(r.record_ids for r in s.readings), readings=self.readings(s))

    def _lookup(self, s: E.State) -> E.TerminalOutcome:
        key = self.terminal_key(s)
        self.execution_trace(s).verify_key(key)
        out = self.table.lookup(key)
        return E.TerminalOutcome(reward=out.reward, key_sha256=key.sha256, detail=out.detail)


def subset_key(prefix, identity: TerminalIdentity, groups: Mapping[str, tuple[str, ...]],
               mask: int):
    """Canonical Phase-1 key for a subset given each head's delivered record group."""
    K = contracts()
    heads = E.heads_of(mask)
    return K.TerminalKey.for_prefix(prefix, domain_id=DOMAIN, ordered_path=E.canonical_path(mask),
                                    acquired=tuple(tuple(groups[h]) for h in heads),
                                    **dataclasses.asdict(identity))
