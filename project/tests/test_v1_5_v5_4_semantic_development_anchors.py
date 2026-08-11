import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/v1_5/113l_materialize_v5_4_semantic_development_anchors_v1_5.py"


def test_anchor_script_does_not_import_formal_effect_results():
    source = SCRIPT.read_text()
    assert "formal_qf_20260809" not in source
    assert "fold_1_results.jsonl" not in source
    assert "effect_group_manifest_private.jsonl" in source


def test_anchor_materialization_is_balanced_and_development_only():
    subprocess.run([sys.executable, str(SCRIPT)], cwd=ROOT, check=True, capture_output=True, text=True)
    out = ROOT / "outputs/pm_v1_5_v5_4_semantic_development_anchors_20260809"
    report = json.loads((out / "report.json").read_text())
    rows = [json.loads(line) for line in (out / "anchors_private.jsonl").read_text().splitlines() if line.strip()]
    assert report["status"] == "COMPLETE_ZERO_API_DEVELOPMENT_ANCHORS"
    assert len(rows) == 48
    assert len({row["semantic_family_id"] for row in rows}) == 48
    assert all(row["development_only_not_fresh_confirmation"] for row in rows)
    assert all(not row["effect_or_quality_outcome_read_by_materializer"] for row in rows)
    assert report["api_calls"] == 0
