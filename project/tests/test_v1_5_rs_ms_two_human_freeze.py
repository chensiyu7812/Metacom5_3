import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
BUNDLE = ROOT / "outputs/pm_v1_5_paper1_v3_rs_ms_dual_human_bundle_20260811"
SCRIPT = ROOT / "scripts/v1_5/251l_freeze_and_audit_paper1_v3_rs_ms_human_reviews_v1_5.py"
FAMILIES = [
    "WRONG_OWNER_OR_SPEAKER_IDENTITY",
    "PAST_UPGRADED_TO_CURRENT_OR_UNVERIFIED_PRESENT",
    "UNSUPPORTED_PERSONAL_FACT_OR_CAUSE",
    "FIRST_PERSON_SOURCE_COPY_OR_ROLE_REVERSAL",
    "INTERNAL_RESOURCE_OR_SCAFFOLD_EXPOSURE",
    "EXPLICIT_BOUNDARY_VIOLATION_OR_EXCESSIVE_DIRECTIVENESS",
]


def rows(name: str):
    return [json.loads(x) for x in (BUNDLE / name).read_text(encoding="utf-8").splitlines() if x]


def review(reviewer: str) -> dict:
    answers = {}
    for item in rows("quality_current_context_only_blind_v2.jsonl"):
        answers[item["blind_item_id"]] = {
            "label": "EQUIVALENT",
            "quote_A": item["response_A"][:20],
            "quote_B": item["response_B"][:20],
            "contrast_reason": "No material net direction.",
        }
    for item in rows("risk_absolute_blind.jsonl"):
        answers[item["blind_item_id"]] = {
            **{f"{family}_severity": "0" for family in FAMILIES},
            **{f"{family}_evidence": "" for family in FAMILIES},
            "risk_notes": "",
        }
    for item in rows("function_source_aware_blind.jsonl"):
        answers[item["blind_item_id"]] = {
            "label": "NOT_USED_FINAL",
            "source_evidence_quote": "",
            "response_evidence_quote": "",
            "boundary_event_quote": "",
            "rationale": "No independently attributable source contribution.",
        }
    return {
        "protocol": "pm-v1.5-paper1-v3-rs-ms-dual-human-bundle-v1-annotations-v1",
        "reviewer": reviewer,
        "exported_at": "2026-08-11T00:00:00Z",
        "answers": answers,
    }


def test_two_complete_reviews_freeze_and_audit_without_api(tmp_path: Path):
    a, b, out = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "out"
    a.write_text(json.dumps(review("HUMAN_A")), encoding="utf-8")
    b.write_text(json.dumps(review("HUMAN_B")), encoding="utf-8")
    subprocess.run([sys.executable, str(SCRIPT), "--human-a", str(a), "--human-b", str(b), "--output-dir", str(out)], cwd=ROOT, check=True, capture_output=True, text=True)
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["status"] == "TWO_HUMAN_RAW_REVIEWS_FROZEN_DISAGREEMENT_ADJUDICATION_PENDING"
    assert report["agreement"] == {
        "quality_exact": 16, "quality_n": 16,
        "risk_six_family_cells_exact": 192, "risk_six_family_cells_n": 192,
        "risk_items_all_six_exact": 32, "risk_items_n": 32,
        "function_exact": 16, "function_n": 16,
    }
    assert report["disagreement_items"] == 0
    assert report["api_calls"] == 0


def test_incomplete_review_fails_closed(tmp_path: Path):
    a_data, b_data = review("HUMAN_A"), review("HUMAN_B")
    a_data["answers"].pop(next(iter(a_data["answers"])))
    a, b, out = tmp_path / "a.json", tmp_path / "b.json", tmp_path / "out"
    a.write_text(json.dumps(a_data), encoding="utf-8")
    b.write_text(json.dumps(b_data), encoding="utf-8")
    proc = subprocess.run([sys.executable, str(SCRIPT), "--human-a", str(a), "--human-b", str(b), "--output-dir", str(out)], cwd=ROOT, capture_output=True, text=True)
    assert proc.returncode != 0
    assert not out.exists()
