import hashlib
import json

import pytest

from metacom_pm.paper1.evaluation import rq1


def _write_synthetic_official_inputs(tmp_path, monkeypatch):
    sources = ["ESconv"] * 158 + ["ExTES"] * 70 + ["MHP"] * 73 + ["Psych"] * 25 + ["EPITOME"] * 5
    cards = [
        {
            "base": f"Role card {index}",
            "source": source,
            "language": "english",
            "id": index,
        }
        for index, source in enumerate(sources)
    ]
    cards_path = tmp_path / "card_high_en.json"
    cards_path.write_text(json.dumps(cards, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(rq1, "EXPECTED_CARDS_SHA256", hashlib.sha256(cards_path.read_bytes()).hexdigest())

    manifest_path = tmp_path / "overlap.jsonl"
    rows = []
    for index, card in enumerate(cards):
        is_overlap = card["source"] == "ESconv"
        rows.append(
            {
                "official_file_index": index,
                "card_key": f"english::{card['source']}::{index}",
                "source": card["source"],
                "role_card_sha256": hashlib.sha256(card["base"].encode()).hexdigest(),
                "analysis_slice": (
                    "esconv_source_overlap" if is_overlap else "primary_non_esconv_transfer"
                ),
            }
        )
    manifest_path.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    return cards_path, manifest_path


def test_rq1_loader_binds_official_cards_to_frozen_slices(tmp_path, monkeypatch):
    cards_path, manifest_path = _write_synthetic_official_inputs(tmp_path, monkeypatch)
    cards = rq1.load_rq1_cards(
        official_cards_path=cards_path,
        overlap_manifest_path=manifest_path,
    )
    assert len(cards) == 331
    assert sum(card.analysis_slice == "primary_non_esconv_transfer" for card in cards) == 173
    assert sum(card.analysis_slice == "esconv_source_overlap" for card in cards) == 158


def test_rq1_run_cells_are_complete_and_paired(tmp_path, monkeypatch):
    cards_path, manifest_path = _write_synthetic_official_inputs(tmp_path, monkeypatch)
    cards = rq1.load_rq1_cards(
        official_cards_path=cards_path,
        overlap_manifest_path=manifest_path,
    )
    cells = rq1.build_rq1_run_cells(cards, seeds=(3, 11))
    assert len(cells) == 331 * 2 * 4
    first_cluster = [cell for cell in cells if cell.comparison_cluster_id == "english::ESconv::0::seed-3"]
    assert len(first_cluster) == 4
    assert len({cell.arm for cell in first_cluster}) == 4


def test_rq1_loader_fails_closed_on_manifest_drift(tmp_path, monkeypatch):
    cards_path, manifest_path = _write_synthetic_official_inputs(tmp_path, monkeypatch)
    rows = manifest_path.read_text().splitlines()
    first = json.loads(rows[0])
    first["analysis_slice"] = "primary_non_esconv_transfer"
    rows[0] = json.dumps(first)
    manifest_path.write_text("\n".join(rows) + "\n")
    with pytest.raises(ValueError, match="analysis_slice"):
        rq1.load_rq1_cards(
            official_cards_path=cards_path,
            overlap_manifest_path=manifest_path,
        )
