"""Freeze-before-candidates ledger for one experiment registry.

* ``freeze`` binds the checklist via C0 ``io.bind_checklist`` (write-once per
  prefix; a different checklist for the same prefix is refused).
* ``register_candidate`` appends (prefix, TerminalKey sha, response sha,
  checklist sha) and refuses when the prefix has no frozen checklist.
* ``freeze`` refuses when any candidate for the prefix was already registered,
  even if no checklist file exists: a checklist written after replies were seen
  is not a fixed checklist.
All terminals of a prefix therefore share one item set and denominator.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from ..io import bind_checklist, canonical_json, load_checklist


class ChecklistOrderError(RuntimeError):
    pass


class ChecklistLedger:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.checklists = self.root / "checklists"
        self.log = self.root / "candidates.jsonl"
        self.checklists.mkdir(parents=True, exist_ok=True)

    def _candidates(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text(encoding="utf-8").splitlines() if x]

    def frozen(self, prefix_id: str) -> bool:
        return (self.checklists / f"{prefix_id}.json").exists()

    def freeze(self, checklist, needcard) -> str:
        if any(c["prefix_id"] == checklist.prefix_id for c in self._candidates()):
            raise ChecklistOrderError("candidates already exist for this prefix; checklist cannot be fixed now")
        return bind_checklist(self.checklists, checklist, needcard)

    def checklist(self, prefix_id: str):
        return load_checklist(self.checklists, prefix_id)

    def register_candidate(self, prefix_id: str, key_sha256: str, response_sha256: str) -> dict:
        if not self.frozen(prefix_id):
            raise ChecklistOrderError("no frozen checklist for this prefix")
        row = dict(prefix_id=prefix_id, key_sha256=key_sha256, response_sha256=response_sha256,
                   checklist_sha256=self.checklist(prefix_id).sha256)
        with self.log.open("a", encoding="utf-8") as f:
            f.write(canonical_json(row) + "\n")
            f.flush()
            os.fsync(f.fileno())
        return row
