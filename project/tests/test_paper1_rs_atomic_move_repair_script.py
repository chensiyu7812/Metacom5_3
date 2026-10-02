from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/17_repair_rs_atomic_move_failed_cards.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("rs_atomic_move_repair_script", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def repair_module():
    return _load_module()


def _row(card_id: str, *, failed: bool, accepted_units: list | None = None, manifest: str = "src-manifest") -> dict:
    return {
        "run_manifest_sha256": manifest,
        "source_card_id": card_id,
        "accepted_units": accepted_units or [],
        "call_failure_phase": "extractor" if failed else None,
    }


def test_detect_failed_card_ids_only_flags_call_failure_phase_rows(repair_module):
    rows = [
        _row("a", failed=False, accepted_units=[{"x": 1}]),
        _row("b", failed=True),
        _row("c", failed=False),
    ]
    assert repair_module.detect_failed_card_ids(rows) == {"b"}


def test_detect_failed_card_ids_empty_when_nothing_failed(repair_module):
    rows = [_row("a", failed=False), _row("b", failed=False)]
    assert repair_module.detect_failed_card_ids(rows) == set()


def test_check_catalog_not_drifted_passes_when_counts_match(repair_module):
    repair_module.check_catalog_not_drifted(live_catalog_size=10, source_rows_count=10)


def test_check_catalog_not_drifted_raises_on_mismatch(repair_module):
    with pytest.raises(RuntimeError, match="catalog drifted"):
        repair_module.check_catalog_not_drifted(live_catalog_size=11, source_rows_count=10)


def test_merge_repaired_rows_preserves_untouched_rows_byte_for_byte(repair_module):
    source_rows = [
        _row("a", failed=False, accepted_units=[{"x": 1}], manifest="src-manifest"),
        _row("b", failed=True, manifest="src-manifest"),
    ]
    repaired = {
        "b": _row("b", failed=False, accepted_units=[{"y": 2}], manifest="repair-manifest"),
    }
    merged, still_failed, accepted_total = repair_module.merge_repaired_rows(source_rows, repaired)

    assert merged[0] == source_rows[0]
    assert merged[0]["run_manifest_sha256"] == "src-manifest"
    assert merged[1]["run_manifest_sha256"] == "repair-manifest"
    assert still_failed == []
    assert accepted_total == 2


def test_merge_repaired_rows_keeps_a_card_in_still_failed_if_the_repair_attempt_also_failed(repair_module):
    source_rows = [_row("a", failed=True, manifest="src-manifest")]
    repaired = {"a": _row("a", failed=True, manifest="repair-manifest")}
    merged, still_failed, accepted_total = repair_module.merge_repaired_rows(source_rows, repaired)

    assert still_failed == ["a"]
    assert merged[0]["run_manifest_sha256"] == "repair-manifest"
    assert accepted_total == 0


def test_merge_repaired_rows_output_order_matches_source_order(repair_module):
    source_rows = [_row("a", failed=False), _row("b", failed=True), _row("c", failed=False)]
    repaired = {"b": _row("b", failed=False, accepted_units=[{"z": 1}], manifest="repair-manifest")}
    merged, _still_failed, _accepted_total = repair_module.merge_repaired_rows(source_rows, repaired)

    assert [row["source_card_id"] for row in merged] == ["a", "b", "c"]


def test_build_repair_report_discloses_mixed_identity_and_counts(repair_module):
    report = repair_module.build_repair_report(
        source_results_path=Path("/tmp/source.jsonl"),
        source_results_sha256="a" * 64,
        source_report_path=Path("/tmp/report.json"),
        source_report_complete=True,
        source_run_manifest_sha256="src-manifest",
        repair_run_manifest_sha256="repair-manifest",
        cards_attempted_for_repair=20,
        cards_still_failed=["b", "c"],
        merged_results_path=Path("/tmp/merged.jsonl"),
        merged_results_sha256="b" * 64,
        merged_rows=100,
        accepted_units_total_after_repair=15061,
    )

    assert report["cards_attempted_for_repair"] == 20
    assert report["cards_repaired_successfully"] == 18
    assert report["cards_still_failed"] == ["b", "c"]
    assert report["outcome_calls"] == 0
    assert report["outcome_lock"] == "LOCKED_PRE_ZERO_OUTCOME_FREEZE"
    assert "mixes rows from two run identities" in report["note"]
