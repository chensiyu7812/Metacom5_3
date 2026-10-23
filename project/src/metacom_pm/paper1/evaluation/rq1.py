"""Outcome-blind ESC-Eval RQ1 input and paired-cell construction."""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from pydantic import Field

from ..contracts import ExperimentArm, StrictContract

EXPECTED_ESC_EVAL_COMMIT = "9ad46e7b5e247e824dae4633910eaa82be668beb"
EXPECTED_CARDS_SHA256 = "2c63cf0f65cbe159b38837e0da368667201d34e42c6e5ea1bedbcf35cb7ab4e8"
EXPECTED_SOURCE_COUNTS = {"ESconv": 158, "ExTES": 70, "MHP": 73, "Psych": 25, "EPITOME": 5}
RQ1_ARMS = (
    ExperimentArm.R0,
    ExperimentArm.RS_FIXED_HIGH,
    ExperimentArm.RS_MATCHED_RANDOM,
    ExperimentArm.LEARNED_RS_PM,
)


def _sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _sha256_text(value: str) -> str:
    return _sha256_bytes(value.encode("utf-8"))


class RQ1InputCard(StrictContract):
    official_file_index: int = Field(ge=0)
    target_id: str = Field(min_length=1)
    source: str = Field(min_length=1)
    analysis_slice: str
    role_card_text: str = Field(min_length=1)
    role_card_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class RQ1RunCell(StrictContract):
    target_id: str
    official_file_index: int = Field(ge=0)
    analysis_slice: str
    arm: ExperimentArm
    seed: int = Field(ge=0)
    comparison_cluster_id: str


def _read_overlap_manifest(path: Path) -> list[dict[str, Any]]:
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    if len(rows) != 331:
        raise ValueError("RQ1 overlap manifest must contain exactly 331 cards")
    return rows


def load_rq1_cards(
    *,
    official_cards_path: str | Path,
    overlap_manifest_path: str | Path,
) -> tuple[RQ1InputCard, ...]:
    """Bind public role cards to the frozen text-free slice manifest."""

    cards_path = Path(official_cards_path)
    raw = cards_path.read_bytes()
    if _sha256_bytes(raw) != EXPECTED_CARDS_SHA256:
        raise ValueError("ESC-Eval official English card artifact SHA256 mismatch")
    official = json.loads(raw)
    manifest = _read_overlap_manifest(Path(overlap_manifest_path))
    if not isinstance(official, list) or len(official) != 331:
        raise ValueError("ESC-Eval official English input must contain 331 cards")
    source_counts = Counter(str(row.get("source")) for row in official)
    if dict(source_counts) != EXPECTED_SOURCE_COUNTS:
        raise ValueError(f"ESC-Eval source counts drifted: {dict(source_counts)}")

    bound: list[RQ1InputCard] = []
    for index, (card, identity) in enumerate(zip(official, manifest, strict=True)):
        source = str(card.get("source"))
        role_text = str(card.get("base") or "").strip()
        target_id = f"{card.get('language')}::{source}::{card.get('id')}"
        expected_slice = (
            "esconv_source_overlap" if source == "ESconv" else "primary_non_esconv_transfer"
        )
        checks = {
            "official_file_index": index,
            "card_key": target_id,
            "source": source,
            "role_card_sha256": _sha256_text(role_text),
            "analysis_slice": expected_slice,
        }
        for key, expected in checks.items():
            if identity.get(key) != expected:
                raise ValueError(f"ESC-Eval card/manifest mismatch at {index}: {key}")
        bound.append(
            RQ1InputCard(
                official_file_index=index,
                target_id=target_id,
                source=source,
                analysis_slice=expected_slice,
                role_card_text=role_text,
                role_card_sha256=checks["role_card_sha256"],
            )
        )
    return tuple(bound)


def build_rq1_run_cells(
    cards: Sequence[RQ1InputCard],
    *,
    seeds: Sequence[int],
) -> tuple[RQ1RunCell, ...]:
    """Create complete paired arm cells; does not invoke generation/scoring."""

    if len(cards) != 331 or len({card.target_id for card in cards}) != 331:
        raise ValueError("RQ1 run construction requires 331 unique official cards")
    normalized_seeds = tuple(seeds)
    if not normalized_seeds or len(set(normalized_seeds)) != len(normalized_seeds):
        raise ValueError("RQ1 seeds must be non-empty and unique")
    if any(seed < 0 for seed in normalized_seeds):
        raise ValueError("RQ1 seeds must be non-negative")

    return tuple(
        RQ1RunCell(
            target_id=card.target_id,
            official_file_index=card.official_file_index,
            analysis_slice=card.analysis_slice,
            arm=arm,
            seed=seed,
            comparison_cluster_id=f"{card.target_id}::seed-{seed}",
        )
        for card in sorted(cards, key=lambda item: item.official_file_index)
        for seed in normalized_seeds
        for arm in RQ1_ARMS
    )
