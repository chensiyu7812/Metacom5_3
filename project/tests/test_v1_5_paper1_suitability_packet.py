from __future__ import annotations

from pathlib import Path
import subprocess
import sys

from metacom_pm.v1_5_paper1_suitability_packet import select_qualification_rows


ROOT = Path(__file__).resolve().parents[1]


def _row(component: str, group: str, index: int, *, mode: str | None = None) -> dict:
    return {
        "component": component,
        "candidate_present": True,
        "dataset": "ESConv" if component == "RS" else "EvoEmo",
        "state_id": f"{component}::{group}::{index}",
        "split_group_key": group,
        "selection_score": index / 100,
        "top1_top2_margin": index / 1000,
        "retrieval_observations": {
            "selection_mode": mode,
            "move_id": f"move_{index % 6}",
        },
    }


def test_selection_is_unique_balanced_and_deterministic() -> None:
    rows = []
    for component, groups in (("ME", 15), ("MP", 17), ("MS", 17)):
        for group_index in range(groups):
            for item_index in range(4):
                rows.append(
                    _row(
                        component,
                        f"{component}_g{group_index}",
                        item_index + group_index * 10,
                    )
                )
    for mode in ("transparent_priority", "lexical_fallback"):
        for group_index in range(30):
            rows.append(
                _row(
                    "RS",
                    f"RS_{mode}_g{group_index}",
                    group_index,
                    mode=mode,
                )
            )
    selected = select_qualification_rows(rows)
    selected_again = select_qualification_rows(list(reversed(rows)))
    keys = [(row["state_id"], stratum) for row, stratum in selected]
    assert len(keys) == len(set(state_id for state_id, _ in keys)) == 132
    assert keys == [(row["state_id"], stratum) for row, stratum in selected_again]
    counts = {}
    for row, _ in selected:
        counts[row["component"]] = counts.get(row["component"], 0) + 1
    assert counts == {"ME": 28, "MP": 34, "MS": 34, "RS": 36}


def test_completed_p2a_packet_materializer_fails_closed() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/v1_5/183l_materialize_paper1_p2a_suitability_packet_v1_5.py"),
            "--phase-manifest",
            str(
                ROOT
                / "data/pm_v1_5_contracts/paper1_p2a_suitability_packet_materialization_phase_v1.json"
            ),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "P2A packet materialization is not active" in result.stderr
