"""C0 ``SourceSession``/``PrefixSpec`` views of the B0 census input (WS-B side).

This is **not** the WS-A A1 ``source_registry``.  It exists so B1 can validate
exact evidence spans on real text before A1 is delivered.  Every session it
builds carries ``provenance_version = ADAPTER_PROVENANCE``; once A1 delivers,
``cross_check`` must report zero mismatches (turn text/roles/ranks/dates/family
lineage) before B1 switches to A1 sources.  It never builds resource records.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

from ..io import file_sha256, object_sha256
from ..prefixes import census as C

ADAPTER_PROVENANCE = "wsb-b0-census-source-adapter-v1"
ADAPTER_LICENSE = "inherited_source_terms_not_relicensed"


def contracts():
    from .. import contracts as K
    return K


@dataclass(frozen=True)
class PrefixContext:
    """A V3 prefix plus its complete legal source context (current + strictly past)."""
    prefix: object                     # contracts.PrefixSpec
    current: object                    # contracts.SourceSession (full; evidence limited to cut)
    history: tuple                     # strictly-past SourceSessions, chronological
    row: Mapping                       # the B0 census row

    @property
    def sources(self) -> tuple:
        return (self.current, *self.history)

    def session(self, session_id: str):
        for s in self.sources:
            if s.session_id == session_id:
                return s
        return None


class CensusSources:
    """Adapter over the sanitized EvoEmo runtime artifact used by B0."""

    def __init__(self, artifact: Path):
        self.artifact = Path(artifact)
        self.artifact_sha256 = file_sha256(self.artifact)
        self.users = {u.owner_id: u for u in C.load_users(self.artifact)}
        self._cache: dict = {}

    def source_session(self, owner_id: str, session_id: str):
        key = (owner_id, session_id)
        if key not in self._cache:
            K = contracts()
            user = self.users[owner_id]
            s = user.session_by_id(session_id)
            turns = tuple(K.SourceTurn(turn_index=i, role=t.role, text=t.content)
                          for i, t in enumerate(s.turns))
            self._cache[key] = K.SourceSession(
                owner_id=owner_id, session_id=session_id, chronological_rank=s.chronological_rank,
                date=s.timestamp, turns=turns, raw_sha256=self.artifact_sha256, dataset=C.DATASET,
                family_id=C.session_family(owner_id, s), license=ADAPTER_LICENSE,
                provenance_version=ADAPTER_PROVENANCE,
                source_uri=f"{self.artifact.name}#{owner_id}/{session_id}",
                transcript_sha256=object_sha256([(t.role, t.text) for t in turns]),
                source_split="unassigned")
        return self._cache[key]

    def context(self, row: Mapping) -> PrefixContext:
        """Rebuild and verify the C0 prefix for a census row (identity must equal B0)."""
        K = contracts()
        user = self.users[row["owner_id"]]
        turns = C.materialize_prefix(row, self.users)          # verifies B0 identity
        current = self.source_session(row["owner_id"], row["session_id"])
        history = tuple(self.source_session(row["owner_id"], s.session_id)
                        for s in C.strictly_past_sessions(user, row["cutoff_rank"]))
        families = sorted({f for s in (current, *history) for f in (s.family_id, *s.ancestor_family_ids)})
        prefix = K.PrefixSpec.create(
            owner_id=row["owner_id"], session_id=row["session_id"], cut_turn=row["cut_turn"],
            cutoff_rank=row["cutoff_rank"], timestamp=row["timestamp"], dataset=row["dataset"],
            turns=tuple(K.SourceTurn(turn_index=i, role=t.role, text=t.content)
                        for i, t in enumerate(turns)),
            family_id=current.family_id, ancestor_family_ids=tuple(families),
            fold=row["assignment"]["fold"])
        if prefix.prefix_id != row["prefix_id"]:
            raise ValueError("C0 prefix identity differs from B0 census row")
        prefix.verify_source_context(current, history)
        return PrefixContext(prefix=prefix, current=current, history=history, row=row)


def cross_check(adapter: CensusSources, registry: Iterable) -> list[str]:
    """Compare A1 ``SourceSession``s with this adapter; returns human-readable mismatches."""
    problems = []
    for s in registry:
        try:
            mine = adapter.source_session(s.owner_id, s.session_id)
        except KeyError:
            problems.append(f"{s.owner_id}/{s.session_id}: unknown to B0 census input")
            continue
        for field in ("chronological_rank", "date", "dataset", "family_id", "transcript_sha256"):
            if getattr(s, field) != getattr(mine, field):
                problems.append(f"{s.owner_id}/{s.session_id}: {field} {getattr(s, field)!r} != {getattr(mine, field)!r}")
        if tuple((t.role, t.text) for t in s.turns) != tuple((t.role, t.text) for t in mine.turns):
            problems.append(f"{s.owner_id}/{s.session_id}: turn text/roles differ")
    return problems


# ------------------------------------------------------------- A1 sources (formal)

CONTENT_FIELDS = ("chronological_rank", "date", "dataset", "family_id", "ancestor_family_ids",
                  "transcript_sha256", "raw_sha256", "complete")
# A1 derives excluded_for_overlap (RS-side family exclusion); the adapter never set it.  It must
# equal B0's own family rule: an EvoEmo session derived from ESConv has family "esconv:<id>".
ADAPTER_METADATA_FIELDS = ("license", "provenance_version", "source_uri", "source_split")


def a1_context(registry, row: Mapping) -> PrefixContext:
    """PrefixContext from the WS-A A1 source registry (B1's formal source after cross_check).

    The prefix is rebuilt by A1 and must equal the frozen B0 id; history is A1's
    strictly-past same-owner set (``Registry.context`` verifies it)."""
    prefix = registry.prefix(row["owner_id"], row["session_id"], row["cut_turn"])
    if prefix.prefix_id != row["prefix_id"]:
        raise ValueError("A1 prefix identity differs from B0 census row")
    current, history = registry.context(prefix)
    history = tuple(sorted(history, key=lambda s: s.chronological_rank))
    return PrefixContext(prefix=prefix, current=current, history=history, row=row)


def cross_check_full(adapter: CensusSources, registry, rows: Iterable[Mapping]) -> dict:
    """Field-by-field A1 vs B1-adapter comparison: sessions, original turn indices and all prefixes.

    ``content`` mismatches must be zero.  ``adapter_metadata`` lists fields the
    adapter labels differently by design (license/provenance/uri/split); they
    are reported, not hidden, and B1 uses the A1 values from now on."""
    content, meta, coverage = [], {f: 0 for f in ADAPTER_METADATA_FIELDS}, []
    derived = {"excluded_for_overlap": 0}
    personal = [e for e in registry.entries if e.availability_scope == "personal_history"]
    seen = set()
    for e in personal:
        a = e.source
        seen.add((a.owner_id, a.session_id))
        try:
            b = adapter.source_session(a.owner_id, a.session_id)
        except KeyError:
            coverage.append(f"{a.owner_id}/{a.session_id}: in A1, not in B0 census input")
            continue
        for f in CONTENT_FIELDS:
            if getattr(a, f) != getattr(b, f):
                content.append(f"{a.owner_id}/{a.session_id}:{f}")
        if tuple((t.turn_index, t.role, t.text, t.raw_turn_sha256) for t in a.turns) != \
                tuple((t.turn_index, t.role, t.text, t.raw_turn_sha256) for t in b.turns):
            content.append(f"{a.owner_id}/{a.session_id}:turns")
        raw = adapter.users[a.owner_id].session_by_id(a.session_id)
        if tuple(e.original_turn_indices) != tuple(t.idx for t in raw.turns):
            content.append(f"{a.owner_id}/{a.session_id}:original_turn_indices")
        if a.excluded_for_overlap != b.family_id.startswith("esconv:"):
            content.append(f"{a.owner_id}/{a.session_id}:excluded_for_overlap_vs_b0_family_rule")
        derived["excluded_for_overlap"] += a.excluded_for_overlap
        for f in ADAPTER_METADATA_FIELDS:
            meta[f] += getattr(a, f) != getattr(b, f)
    for owner, user in adapter.users.items():
        for s in user.sessions:
            if (owner, s.session_id) not in seen:
                coverage.append(f"{owner}/{s.session_id}: in B0 census input, not in A1")
    n_prefix, prefix_diff = 0, []
    for row in rows:
        n_prefix += 1
        b = adapter.context(row)
        try:
            a = a1_context(registry, row)
        except (KeyError, ValueError) as exc:
            prefix_diff.append(f"{row['prefix_id']}:a1_context:{exc}")
            continue
        for f in ("prefix_id", "runtime_sha256", "cutoff_rank", "timestamp", "family_id",
                  "ancestor_family_ids", "fold", "turns"):
            if getattr(a.prefix, f) != getattr(b.prefix, f):
                prefix_diff.append(f"{row['prefix_id']}:{f}")
        if [s.session_id for s in a.history] != [s.session_id for s in b.history]:
            prefix_diff.append(f"{row['prefix_id']}:history_sessions")
        visible = {x.source.session_id for x in registry.visible(a.prefix)}
        if visible != {s.session_id for s in b.history}:
            prefix_diff.append(f"{row['prefix_id']}:a1_visible_set")
    return dict(personal_sessions=len(personal), prefixes=n_prefix, content_mismatches=content,
                coverage_mismatches=coverage, prefix_mismatches=prefix_diff,
                adapter_metadata_differences=meta, a1_derived_flags_checked_against_b0_rule=derived,
                zero_content_difference=not (content or coverage or prefix_diff))
