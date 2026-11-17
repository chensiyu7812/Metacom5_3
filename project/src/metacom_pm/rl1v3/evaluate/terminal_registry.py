"""B6e terminal registry (``pmrl1v3-b6e-terminal-registry-v1``): evaluation side of the B6e -> B8e interface.

What it guarantees before any real G0 terminal exists:
* every candidate terminal is a REAL TerminalKey + ExecutionTrace: the trace reproduces the key, the
  key carries the plan's full identity (bank/index/renderer/step2/G0/decode), and with the formal B5
  replay identity substituted it equals the formal replay's key for the same subset - so subset and
  delivered record groups are exactly those of the integration-accepted replay;
* a candidate can be registered only after the prefix's checklist is frozen (``ChecklistLedger``);
* only ER-v3 engineering records (``is_gsc`` False, engineering_only, no GSC field) enter the table;
  a refused ER attempt (too uncertain, hard_safety uncertain, ...) keeps the terminal pending;
  hard_safety fail is already the ER floor (-1) inside ER-v3;
* the table reports completeness (reachable / registered / computed / refused / missing); a missing
  or refused terminal is never filled with 0 and a partial table is tagged ``partial`` - it cannot
  serve as an Oracle table (``train.real_instances`` refuses it);
* GSC is never built here: ER and GSC stay separate tables.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from typing import Mapping

from ..env import finite_head as E
from ..env.c0_binding import DOMAIN, TerminalIdentity, TerminalTable
from ..judge import engineering_reward_v3 as ER3

REGISTRY_PROTOCOL = "pmrl1v3-b6e-terminal-registry-v1"
GSC_FIELDS = ("gsc_lower", "gsc_upper", "final", "item_verdicts", "hard_factual", "hard_safety")


class RegistryError(ValueError):
    pass


@dataclasses.dataclass(frozen=True)
class ReplayBinding:
    """Facts of one prefix's formal B5 replay report (integration-accepted)."""
    prefix_id: str
    identity: Mapping[str, str]          # replay TerminalKey identity (bank/index/renderer/step2/g/decode)
    key_by_subset: Mapping[str, str]     # "RS+MP"/"OFF" -> replay TerminalKey sha256
    reachable: tuple[int, ...]

    @classmethod
    def from_report(cls, rep: dict) -> "ReplayBinding":
        if not rep["passed"]:
            raise RegistryError(f"{rep['prefix_id']}: replay did not pass")
        ident = {k: rep["identity"][k] for k in ("bank_version", "index_version", "renderer_id", "step2_id",
                                                 "g_id", "decode_id")}
        return cls(prefix_id=rep["prefix_id"], identity=ident, key_by_subset=dict(rep["key_by_subset"]),
                   reachable=tuple(sorted(E.mask_of(() if s == "OFF" else s.split("+")) for s in rep["key_by_subset"])))

    def replay_key_sha(self, prefix, key) -> str:
        from .. import contracts as K
        return K.TerminalKey.for_prefix(prefix, domain_id=DOMAIN, ordered_path=key.ordered_path,
                                        acquired=key.acquired, **self.identity).sha256


def subset_name(mask: int) -> str:
    return "+".join(E.heads_of(mask)) or "OFF"


class TerminalRegistry:
    def __init__(self, *, identity: TerminalIdentity, ledger, table_tag: str = "real"):
        self.identity, self.ledger, self.table_tag = identity, ledger, table_tag
        self.prefixes: dict[str, tuple] = {}
        self.rows: dict[str, dict[int, dict]] = {}

    def bind_prefix(self, prefix, binding: ReplayBinding) -> None:
        if prefix.prefix_id != binding.prefix_id or prefix.prefix_id in self.prefixes:
            raise RegistryError("prefix/binding mismatch or prefix already bound")
        self.prefixes[prefix.prefix_id] = (prefix, binding)
        self.rows[prefix.prefix_id] = {}

    def register(self, prefix_id: str, key, trace, response_sha256: str) -> dict:
        if prefix_id not in self.prefixes:
            raise RegistryError("prefix not bound to a formal replay")
        prefix, binding = self.prefixes[prefix_id]
        if key.prefix_id != prefix_id:
            raise RegistryError("key belongs to another prefix")
        try:
            trace.verify_key(key)
        except ValueError as exc:
            raise RegistryError(f"trace does not reproduce key: {exc}") from exc
        if {k: getattr(key, k) for k in binding.identity} != dataclasses.asdict(self.identity):
            raise RegistryError("key identity differs from the plan identity")
        mask = E.mask_of(tuple(a[4:] for a in key.ordered_path if a != E.STOP))
        if key.ordered_path != E.canonical_path(mask):
            raise RegistryError("only canonical-order Phase-1 keys are registered")
        if mask not in binding.reachable or binding.replay_key_sha(prefix, key) != binding.key_by_subset[subset_name(mask)]:
            raise RegistryError("subset/record groups differ from the formal B5 replay")
        if mask in self.rows[prefix_id]:
            raise RegistryError("terminal already registered (write-once)")
        row = self.ledger.register_candidate(prefix_id, key.sha256, response_sha256)   # refuses before freeze
        self.rows[prefix_id][mask] = dict(key_sha256=key.sha256, response_sha256=response_sha256,
                                          checklist_sha256=row["checklist_sha256"], status="pending", er=None)
        return self.rows[prefix_id][mask]

    def add_er(self, prefix_id: str, attempt: dict) -> None:
        if not isinstance(attempt, dict):
            raise RegistryError("only ER-v3 attempt dicts are accepted (a C0 TerminalRecord is GSC)")
        row = next((r for r in self.rows.get(prefix_id, {}).values() if r["key_sha256"] == attempt.get("key_sha256")), None)
        if row is None:
            raise RegistryError("ER attempt for an unregistered terminal")
        if row["er"] is not None:
            raise RegistryError("ER already recorded (write-once)")
        if attempt.get("status") == "refused":
            if attempt.get("protocol") != ER3.PROTOCOL:
                raise RegistryError("refusal from another ER protocol")
            row.update(status="refused", er=dict(reasons=list(attempt["reasons"])))
            return
        rec = attempt.get("record") or {}
        if attempt.get("status") != "computed" or rec.get("protocol") != ER3.PROTOCOL or rec.get("is_gsc") is not False \
                or rec.get("qualification_tier") != "engineering_only" or set(GSC_FIELDS) & set(rec):
            raise RegistryError("only ER-v3 engineering records (no GSC fields) enter the ER table")
        if rec["checklist_sha256"] != row["checklist_sha256"]:
            raise RegistryError("ER record used another checklist than the frozen one")
        row.update(status="computed", er=rec)

    def table(self, prefix_id: str) -> tuple[TerminalTable, dict]:
        _, binding = self.prefixes[prefix_id]
        rows = self.rows[prefix_id]
        st = Counter(r["status"] for r in rows.values())
        missing = [subset_name(m) for m in binding.reachable if m not in rows]
        complete = st["computed"] == len(binding.reachable)
        report = dict(protocol=REGISTRY_PROTOCOL, er_protocol=ER3.PROTOCOL, prefix_id=prefix_id,
                      reachable=len(binding.reachable), registered=len(rows), computed=st["computed"],
                      refused=st["refused"], pending=st["pending"], missing=missing, complete=complete,
                      refusal_reasons=dict(Counter(x for r in rows.values() if r["status"] == "refused"
                                                   for x in r["er"]["reasons"])),
                      safety_floor=sum(1 for r in rows.values() if r["status"] == "computed"
                                       and r["er"]["j1_safety_fail_items"]),
                      missing_or_refused_filled_with_zero=False, is_gsc=False, tag=self.table_tag)
        out = {r["key_sha256"]: ER3.to_outcome(r["er"]) for r in rows.values() if r["status"] == "computed"}
        tid = f"{REGISTRY_PROTOCOL}|{ER3.PROTOCOL}|{self.table_tag}|{prefix_id[:12]}|{'complete' if complete else 'partial'}"
        return TerminalTable(out, table_id=tid), report
