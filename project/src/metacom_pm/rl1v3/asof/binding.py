"""PrefixAsOfBinding (``pmrl1v3-prefix-asof-binding-v0.1-proposal``): which resource snapshot a
terminal was produced from, and with which writer / bank / index / query / renderer / G / decode /
Step-2 identities.  WS-B proposal for the joint A<->B contract; it does NOT modify C0 0.2.0.

Why a separate binding: the C0 ``TerminalKey`` carries bank/index/renderer/G/decode/Step-2 and the
acquired record ids, but not *how the bank content available at this cutoff was produced* (writer
identity, source frontier, snapshot).  Under V3.2 the same prefix can be served by the legacy
full-history bank-v0 projection or by a chronological as-of writer; both may deliver records with
equal text yet different legitimacy.  Until a C0 migration adds an explicit field (see
``C0_MIGRATION_PROPOSAL``) every V3.2 cache/terminal lookup uses the composite key
``asof_terminal_key_sha256(c0_key_sha256, binding)``, so old and new identities can never collide.

Tiers (fail-closed):
  legacy_engineering   bank-v0 or any writer whose pool membership is not prefix-extension
                       invariant; engineering replay only, never research evidence;
  research_candidate   chronological writer, mechanical as-of checks passed, semantic review pending;
  research_qualified   research_candidate + researcher-approved semantic review + frozen identities.
Promotion never happens by renaming: a different writer/snapshot is a different binding.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field

from ..io import object_sha256

PROTOCOL = "pmrl1v3-prefix-asof-binding-v0.1-proposal"
TIERS = ("legacy_engineering", "research_candidate", "research_qualified")
WRITER_KINDS = ("legacy_full_history_projection", "chronological_asof")
PLACEHOLDERS = ("not_run", "pending", "required", "unknown", "not_frozen", "tokenizer_only", "fixture")
IDENTITY_FIELDS = ("bank_version", "index_version", "query_id", "renderer_id", "g_id", "decode_id", "step2_id")

C0_MIGRATION_PROPOSAL = dict(
    proposal="C0 0.3.0 candidate (cross-line review + integration owner; not applied)",
    add_to_TerminalKey=["asof_binding_sha256 (required; sha256 of PrefixAsOfBinding without tier)"],
    add_to_IndexManifest=["writer_identity", "source_frontier_rule"],
    unchanged=["Observation", "ReadingView", "action semantics", "finite_head_v1 domain"],
    interim="WS-B composite key asof_terminal_key_sha256(c0_key, binding); C0 0.2.0 keys stay valid "
            "for legacy_engineering only",
)


class BindingError(ValueError):
    pass


@dataclass(frozen=True)
class FrontierEntry:
    """One completed strictly-past session the writer was allowed to consume."""
    source_id: str
    session_id: str
    rank: int
    date: str | None
    transcript_sha256: str
    ready_rank: int


@dataclass(frozen=True)
class PrefixAsOfBinding:
    prefix_id: str
    owner_id: str
    session_id: str
    cut_turn: int
    cutoff_rank: int
    timestamp: str | None
    prefix_context_sha256: str
    fold: int | None
    family_closure: tuple[str, ...]
    source_frontier: tuple[FrontierEntry, ...]
    external_snapshot: str                     # RS external version (source-local; never the global registry hash)
    writer_identity: str
    writer_kind: str
    snapshot_sha256: str                       # materialised resource view available at the cutoff
    bank_version: str
    index_version: str
    query_id: str
    renderer_id: str
    g_id: str
    decode_id: str
    step2_id: str
    visibility_policy: str
    tier: str
    tier_reason: str = ""
    protocol: str = PROTOCOL
    notes: tuple[str, ...] = field(default_factory=tuple)

    @property
    def frontier_sha256(self) -> str:
        return object_sha256([dataclasses.asdict(e) for e in self.source_frontier])

    def identity(self) -> dict:
        """Everything that can change what PM/G see.  Excluded (aligned with WS-A's interface candidate
        57047c5f): tier labels, notes and the fold assignment (evaluation metadata, not content).  No
        field may be a global corpus/registry hash: appending a future session must not change a past
        binding (identity-level prefix extension)."""
        d = dataclasses.asdict(self)
        for k in ("tier", "tier_reason", "notes", "fold"):
            d.pop(k)
        d["frontier_sha256"] = self.frontier_sha256
        return d

    @property
    def sha256(self) -> str:
        return object_sha256(self.identity())


def asof_terminal_key_sha256(c0_key_sha256: str, binding: PrefixAsOfBinding) -> str:
    """Interim composite key: a C0 key is only meaningful together with its as-of binding."""
    return object_sha256(dict(protocol=PROTOCOL, c0_terminal_key=c0_key_sha256, asof_binding=binding.sha256))


def frontier_for(registry, prefix) -> tuple[FrontierEntry, ...]:
    """The exact legal personal-history frontier of a prefix (registry rules, nothing else)."""
    _, history = registry.context(prefix)
    out = []
    for s in sorted(history, key=lambda s: s.chronological_rank):
        e = registry.entry(s.owner_id, s.session_id)
        if registry.reason(e.source_id, prefix) is not None:
            continue
        out.append(FrontierEntry(source_id=e.source_id, session_id=s.session_id, rank=s.chronological_rank,
                                 date=s.date, transcript_sha256=s.transcript_sha256,
                                 ready_rank=e.ready_at.session_rank))
    return tuple(out)


def validate(binding: PrefixAsOfBinding, registry, prefix) -> list[str]:
    """Mechanical checks; returns problems (empty = pass).  Semantic review is never implied."""
    p = []
    if binding.protocol != PROTOCOL:
        p.append("protocol")
    if binding.tier not in TIERS:
        p.append("tier")
    if binding.writer_kind not in WRITER_KINDS:
        p.append("writer_kind")
    if (binding.prefix_id, binding.owner_id, binding.session_id, binding.cut_turn, binding.cutoff_rank) != (
            prefix.prefix_id, prefix.owner_id, prefix.session_id, prefix.cut_turn, prefix.cutoff_rank):
        p.append("prefix_mismatch")
    if binding.prefix_context_sha256 != prefix.runtime_sha256:
        p.append("prefix_context_mismatch")
    if tuple(binding.family_closure) != tuple(prefix.ancestor_family_ids):
        p.append("family_closure_mismatch")
    legal = frontier_for(registry, prefix)
    if tuple(binding.source_frontier) != legal:
        extra = {e.source_id for e in binding.source_frontier} - {e.source_id for e in legal}
        missing = {e.source_id for e in legal} - {e.source_id for e in binding.source_frontier}
        p.append(f"frontier_not_exact(extra={len(extra)},missing={len(missing)})")
    for e in binding.source_frontier:
        if e.rank >= prefix.cutoff_rank or e.ready_rank > prefix.cutoff_rank:
            p.append(f"frontier_future:{e.session_id}")
        if e.session_id == prefix.session_id:
            p.append("frontier_contains_current_session")
    if binding.tier != "legacy_engineering":
        if binding.writer_kind != "chronological_asof":
            p.append("research_tier_requires_chronological_writer")
        for k in IDENTITY_FIELDS + ("writer_identity", "snapshot_sha256", "visibility_policy"):
            v = (getattr(binding, k) or "").lower().replace("-", "_")
            if not v or any(x in v for x in PLACEHOLDERS):
                p.append(f"placeholder_identity:{k}")
    if binding.writer_kind == "legacy_full_history_projection" and binding.tier != "legacy_engineering":
        p.append("legacy_writer_cannot_be_research")
    return p


def legacy_bank_v0_binding(registry, prefix, *, identity: dict, snapshot_sha256: str,
                           external_snapshot: str, visibility_policy: str) -> PrefixAsOfBinding:
    """Binding that records the formal bank-v0 replay honestly as legacy engineering."""
    return PrefixAsOfBinding(
        prefix_id=prefix.prefix_id, owner_id=prefix.owner_id, session_id=prefix.session_id,
        cut_turn=prefix.cut_turn, cutoff_rank=prefix.cutoff_rank, timestamp=prefix.timestamp,
        prefix_context_sha256=prefix.runtime_sha256, fold=prefix.fold,
        family_closure=tuple(prefix.ancestor_family_ids), source_frontier=frontier_for(registry, prefix),
        external_snapshot=external_snapshot,
        writer_identity="pmrl1v3-a1b-bank-v0 (MP pool = full-history latest-rank projection)",
        writer_kind="legacy_full_history_projection", snapshot_sha256=snapshot_sha256,
        query_id="lexical-v0:last_3_visible_turns", visibility_policy=visibility_policy,
        tier="legacy_engineering",
        tier_reason="MP pool membership depends on sessions after the cutoff (PR #13; V32 asof audit)",
        **{k: identity[k] for k in ("bank_version", "index_version", "renderer_id", "g_id", "decode_id", "step2_id")})
