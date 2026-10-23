import csv
import importlib.util
from pathlib import Path


PROJECT = Path(__file__).resolve().parents[1]
SCRIPT = PROJECT / "scripts/paper1/32_export_human_review_sheets.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("paper1_human_review_export", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _csv_rows(path: Path):
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def test_readable_human_review_exports_remain_blank_and_blind(tmp_path):
    module = _load_script()
    module.OUTPUT = tmp_path
    assert module.main() == 0

    rs = _csv_rows(tmp_path / "paper1_rs_semantics_human_review_20260820_v1.csv")
    assert len(rs) == 64
    assert all("Strategy family [" not in row["candidate_move"] for row in rs)
    assert all(
        row[field] == ""
        for row in rs
        for field in (
            "atomicity",
            "state_appropriateness",
            "boundary_compatibility",
            "executability",
            "leakage",
            "redundancy_near_duplicate",
            "rationale",
            "reviewer_id",
        )
    )
    forbidden_rs_headers = {"rank", "family", "similarity", "provenance", "pm", "arm"}
    assert not forbidden_rs_headers.intersection({key.lower() for key in rs[0]})

    a = _csv_rows(tmp_path / "paper1_esc_evaluator_reviewer_a_20260820_v1.csv")
    b = _csv_rows(tmp_path / "paper1_esc_evaluator_reviewer_b_20260820_v1.csv")
    assert len(a) == len(b) == 24
    assert {row["blind_item_id"] for row in a} == {
        row["blind_item_id"] for row in b
    }
    assert all(
        row[field] == ""
        for rows in (a, b)
        for row in rows
        for field in (*module.ESC_DIMENSIONS, "notes", "human_completed")
    )
    assert not any("reviewer_b" in key.lower() for key in a[0])
    assert not any("reviewer_a" in key.lower() for key in b[0])

    adjudication = _csv_rows(
        tmp_path / "paper1_esc_evaluator_adjudication_20260820_v1.csv"
    )
    assert len(adjudication) == 24
    assert all(
        value == ""
        for row in adjudication
        for key, value in row.items()
        if key not in {"blind_item_id", "dialogue"}
    )


def test_reviewer_html_contains_no_true_model_or_arm_identity(tmp_path):
    module = _load_script()
    module.OUTPUT = tmp_path
    module.main()
    for label in ("a", "b"):
        text = (
            tmp_path / f"paper1_esc_evaluator_reviewer_{label}_20260820_v1.html"
        ).read_text(encoding="utf-8")
        assert "qwen3-235b" not in text.lower()
        assert "deepseek" not in text.lower()
        assert "internlm" not in text.lower()
        assert "learned_rs_pm" not in text.lower()
        assert "rs_fixed_high" not in text.lower()

