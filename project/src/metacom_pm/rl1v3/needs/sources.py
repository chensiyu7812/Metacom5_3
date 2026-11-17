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
