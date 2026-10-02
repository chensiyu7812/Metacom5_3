"""Deterministic-order, append-only resumable batch compile over the RS
source-card catalog.

Simpler than ``semantic_memory/batch.py``: RS source cards are independent
of each other (no owner-scoped "strictly-past accepted units" threading like
MP/MS/ME), and ``build_strategy_source_catalog`` already returns cards in a
fixed, reproducible (dialogue-index, turn-index) order, so no separate
ordering step is needed.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal, Protocol

from metacom_pm.io import append_jsonl, canonical_json, iter_jsonl, sha256_file, sha256_text, write_json

from .contracts import AcceptedAtomicMoveUnit, SourceCardCompileInput
from .runtime import SourceCardCompileResult, source_sha256
from .source_adapter import build_source_card_compile_input
from ..rs.strategy_bank import StrategySourceCard

RunScope = Literal["smoke", "full"]


class SourceCardCompiler(Protocol):
    @property
    def compiler_version(self) -> str: ...

    @property
    def run_manifest(self) -> dict[str, object]: ...

    @property
    def run_identity_sha256(self) -> str: ...

    def compile_source_card(self, source: SourceCardCompileInput) -> SourceCardCompileResult: ...


def _full_run_manifest(
    *, compiler: SourceCardCompiler, preceding_turns: int, run_scope: RunScope
) -> dict[str, object]:
    return {
        **compiler.run_manifest,
        "preceding_turns": preceding_turns,
        "run_scope": run_scope,
    }


def _run_manifest_sha256(manifest: dict[str, object]) -> str:
    return sha256_text(canonical_json(manifest))


def run_source_card_prefix(
    *,
    cards: tuple[StrategySourceCard, ...],
    esconv_data: list[dict[str, Any]],
    compiler: SourceCardCompiler,
    maximum_cards: int,
    preceding_turns: int,
    run_scope: RunScope,
    results_path: str | Path,
    report_path: str | Path,
) -> dict[str, object]:
    """Compile a stable prefix of ``cards``; existing successful rows must be
    an exact prefix identified by ``source_card_id``, ``source_sha256``, AND
    ``run_manifest_sha256`` (binds compiler/prompt/schema/renderer/pricing/
    preceding_turns/scope identity) -- mirrors the memory compiler's
    resume-without-repayment contract, but additionally fails closed on a
    prompt/model/renderer change reusing an old results file, including for
    rows with zero accepted units (which have no accepted-unit-internal
    hash to fall back on).

    ``run_scope="smoke"`` never reports ``complete=True`` regardless of how
    much of the requested prefix finished, so a partial smoke run can never
    be mistaken for a finished formal compile. Only ``run_scope="full"``
    with every card in ``cards`` completed can report ``complete=True``."""

    if maximum_cards < 1:
        raise ValueError("maximum_cards must be positive")
    if run_scope == "full" and maximum_cards != len(cards):
        raise ValueError("run_scope='full' must select every card in the catalog")
    selected = cards[:maximum_cards]
    full_manifest = _full_run_manifest(
        compiler=compiler, preceding_turns=preceding_turns, run_scope=run_scope
    )
    manifest_sha256 = _run_manifest_sha256(full_manifest)
    path = Path(results_path)
    existing_rows = list(iter_jsonl(path)) if path.exists() else []
    if len(existing_rows) > len(selected):
        raise RuntimeError("existing RS atomic-move rows exceed selected card prefix")

    for index, row in enumerate(existing_rows):
        expected_card = selected[index]
        if row.get("source_card_id") != expected_card.card_id:
            raise RuntimeError("existing RS atomic-move rows are not the exact ordered prefix")
        if row.get("run_manifest_sha256") != manifest_sha256:
            raise RuntimeError(
                "existing RS atomic-move row was compiled under a different "
                "compiler/prompt/schema/renderer/pricing/scope identity; "
                "resume refused. Start a new results file for the new identity."
            )
        expected_source = build_source_card_compile_input(
            expected_card, esconv_data=esconv_data, preceding_turns=preceding_turns
        )
        if row.get("source_sha256") != source_sha256(expected_source):
            raise RuntimeError("existing RS atomic-move row has a source-identity mismatch")
        # A row surviving to disk is trusted data, but "trusted" must still
        # mean "schema-valid" -- re-validate every stored accepted unit
        # against the live AcceptedAtomicMoveUnit contract on every resume,
        # so a corrupted or schema-stale blob is caught here, not just
        # silently counted.
        for unit in row.get("accepted_units") or []:
            AcceptedAtomicMoveUnit.model_validate(unit)

    accepted_total = 0
    extractor_proposals_total = 0
    structurally_invalid_total = 0
    verifier_rejections_total = 0
    duplicate_semantic_content_total = 0
    call_failures_total = 0

    for row in existing_rows:
        accepted_total += len(row.get("accepted_units") or [])
        extractor_proposals_total += int(row.get("extractor_proposal_count") or 0)
        structurally_invalid_total += int(row.get("structurally_invalid_proposals") or 0)
        verifier_rejections_total += int(row.get("verifier_rejections") or 0)
        duplicate_semantic_content_total += int(row.get("duplicate_semantic_content_count") or 0)
        if row.get("call_failure_phase"):
            call_failures_total += 1

    for card in selected[len(existing_rows) :]:
        source = build_source_card_compile_input(
            card, esconv_data=esconv_data, preceding_turns=preceding_turns
        )
        result = compiler.compile_source_card(source)
        row = {
            "run_manifest_sha256": manifest_sha256,
            "source_card_id": card.card_id,
            "source_dialogue_id": card.source_dialogue_id,
            "source_turn_index": card.source_turn_index,
            "source_sha256": source_sha256(source),
            "accepted_units": [u.model_dump(mode="json") for u in result.accepted_units],
            "extractor_proposal_count": result.extractor_proposal_count,
            "structurally_invalid_proposals": result.structurally_invalid_proposals,
            "verifier_rejections": result.verifier_rejections,
            "duplicate_semantic_content_count": result.duplicate_semantic_content_count,
            "call_failure_phase": result.call_failure_phase,
        }
        append_jsonl(path, row)
        accepted_total += len(result.accepted_units)
        extractor_proposals_total += result.extractor_proposal_count
        structurally_invalid_total += result.structurally_invalid_proposals
        verifier_rejections_total += result.verifier_rejections
        duplicate_semantic_content_total += result.duplicate_semantic_content_count
        if result.call_failure_phase:
            call_failures_total += 1

    all_rows = list(iter_jsonl(path)) if path.exists() else []
    is_full_catalog_done = run_scope == "full" and len(all_rows) == len(cards)
    report: dict[str, object] = {
        "protocol": "paper1-rs-atomic-move-batch-report-v2",
        "run_scope": run_scope,
        "run_manifest_sha256": manifest_sha256,
        # The full manifest content, not just its hash -- a human reviewer
        # (or a future audit) must be able to read what this hash actually
        # represents without recomputing it from live code state.
        "run_manifest": full_manifest,
        "selected_cards": len(selected),
        "completed_cards": len(all_rows),
        "catalog_size": len(cards),
        "accepted_units": accepted_total,
        "extractor_proposals": extractor_proposals_total,
        "structurally_invalid_proposals": structurally_invalid_total,
        "verifier_rejections": verifier_rejections_total,
        "duplicate_semantic_content_count": duplicate_semantic_content_total,
        "call_failures": call_failures_total,
        # Only a run_scope="full" pass over the entire catalog may ever be
        # complete=True; a smoke run (by definition a prefix) never is,
        # regardless of whether it finished its own smaller selection.
        "complete": is_full_catalog_done,
        "results_sha256": sha256_file(path) if path.exists() else None,
        "outcome_calls": 0,
        "outcome_lock": "LOCKED_PRE_ZERO_OUTCOME_FREEZE",
    }
    write_json(report_path, report)
    return report
