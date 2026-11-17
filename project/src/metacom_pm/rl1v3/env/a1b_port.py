"""Thin B-side adapter: WS-A A1b ``retrieve.Reader`` -> ``BankPortV2`` (B5 replay v2).

No retrieval, ranking, filtering or token logic lives here; every decision is
the WS-A Reader's.  The adapter only forwards the state's actual acquired
ReadingViews, the bank/index versions (so a version drift fails closed) and
exposes the records/sources the B-side provenance checks need.  The prefix is
always rebuilt from the A1 source registry and must equal the frozen B0 id.
"""
from __future__ import annotations

from pathlib import Path

ADAPTER = "wsb-a1b-bankport-v2"


class A1bPort:
    def __init__(self, bank, prefix, tokenizer, *, g_id: str, decode_id: str,
                 step2_id: str = "none-v0-read-replay", output_reserve_tokens: int = 320):
        from ..retrieve import Reader
        self.bank, self.prefix, self.tokenizer = bank, prefix, tokenizer
        self.reader = Reader(bank, prefix, tokenizer, g_id=g_id, decode_id=decode_id,
                             step2_id=step2_id, output_reserve_tokens=output_reserve_tokens)
        self.native_context_tokens = tokenizer.native_context_tokens
        self.output_reserve_tokens = output_reserve_tokens
        self.base_tokens = self.reader.base_tokens

    @property
    def identity(self) -> dict:
        return dict(self.reader.identity)

    def availability(self):
        return self.reader.availability()

    def read(self, head, *, acquired=()):
        return self.reader.read(head, acquired=tuple(acquired), bank_version=self.bank.version,
                                index_version=self.bank.index_version)

    def action_mask(self, acquired=()):
        return self.reader.action_mask(tuple(acquired))

    def records(self, record_ids):
        return {i: self.bank.by_id[i] for i in record_ids if i in self.bank.by_id}

    def source(self, owner_id, session_id):
        return self.bank.registry.entry(owner_id, session_id).source

    def count_tokens(self, text):
        return self.tokenizer.count(text)

    def replay(self, key):
        return self.reader.replay(key)


def load_bank(root: Path, *, registry_dir: str, bank_dir: str, expected_source: str, expected_bank: str):
    """Load the pinned A1 registry and A1b bank; versions must match the config."""
    from ..bank import bank_v0
    from ..sources import source_registry
    registry = source_registry.load(Path(root) / registry_dir)
    if registry.version != expected_source:
        raise ValueError(f"source registry {registry.version} != expected {expected_source}")
    return bank_v0.load(Path(root) / bank_dir, registry, expected_version=expected_bank)


def prefix_for(registry, row: dict):
    """A1 prefix for a B0/B1 row; identity must equal the frozen B0 prefix id."""
    p = registry.prefix(row["owner_id"], row["session_id"], row["cut_turn"])
    if p.prefix_id != row["prefix_id"]:
        raise ValueError(f"A1 prefix id differs from B0 for {row['prefix_id']}")
    return p
