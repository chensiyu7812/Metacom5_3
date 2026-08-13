from __future__ import annotations

import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "data/pm_v1_5_contracts/paper1_clean_publication_manifest_v1.json"


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_clean_publication_is_current_content_addressed_and_zero_api() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert manifest["status"] == "CURRENT_CLEAN_PUBLICATION_ZERO_API_NO_LIVE_AUTHORITY"
    assert manifest["current_boundary"]["live_calls_authorized"] == 0
    assert manifest["current_boundary"]["judge_calls_authorized"] == 0
    assert manifest["current_boundary"]["fits_authorized"] == 0
    for row in manifest["included_files"]:
        path = ROOT / row["path"]
        assert path.is_file(), row["path"]
        assert _sha(path) == row["sha256"], row["path"]


def test_clean_publication_contains_no_failed_outputs_or_private_packets() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    included = [row["path"].lower() for row in manifest["included_files"]]
    forbidden_fragments = (
        "outputs/",
        "reports/",
        "private",
        "blind_packet",
        "human_review",
        "closeout",
        "execution_phase",
    )
    assert all(not any(fragment in path for fragment in forbidden_fragments) for path in included)


def test_handoff_preserves_claim_and_responsibility_boundaries() -> None:
    handoff = (ROOT / "docs/PAPER1_CURRENT_RESEARCH_HANDOFF_20260813_ZH.md").read_text(
        encoding="utf-8"
    )
    assert "RS_pass AND count_pass(MP,MS,ME) >= 2" in handoff
    assert "ESConv" in handoff and "EvoEmo" in handoff and "ES-MemEval" in handoff
    assert "当前不授权 generator、judge、fit 或 external call" in handoff

