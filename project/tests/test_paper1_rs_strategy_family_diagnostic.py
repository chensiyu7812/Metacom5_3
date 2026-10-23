import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def test_strategy_family_diagnostic_is_evaluator_only_and_not_pm_gold():
    root = ROOT / "data/paper1_evaluator_only_rs"
    summary = json.loads(
        (root / "esconv_rs_strategy_family_match_summary_v1.json").read_text(
            encoding="utf-8"
        )
    )
    rows_path = root / "esconv_rs_strategy_family_match_evaluator_only_v1.jsonl"
    assert summary["scope"] == {
        "authority_allowed_use": "retriever_strategy_family_sanity_diagnostic_only",
        "evaluator_only": True,
        "PM_feature": False,
        "RS_ON_OFF_gold": False,
        "candidate_applicability_gold": False,
        "Generator_outcome": False,
        "Paper1_capability_metric": False,
        "winner_selected": False,
        "pass_fail_gate": False,
        "formal_outcome_calls": 0,
    }
    assert summary["counts"]["states"] == 11883
    assert summary["counts"]["states_by_effect_split"] == {
        "train": 9923,
        "validation": 1960,
    }
    assert summary["provenance"]["evaluator_rows_sha256"] == _sha256(rows_path)
    assert set(summary["methods"]) == {"lexical_jaccard", "bge_small", "bge_m3"}
    for method in summary["methods"].values():
        assert 0.0 <= method["strategy_family_match_at_1"] <= 1.0
        assert method["strategy_family_match_at_1"] <= method[
            "strategy_family_match_at_3"
        ] <= 1.0
        assert set(method["by_effect_state_split"]) == {"train", "validation"}
        assert 0.0 <= method["macro_strategy_family_match_at_1"] <= 1.0
        assert method["macro_strategy_family_match_at_1"] <= method[
            "macro_strategy_family_match_at_3"
        ] <= 1.0


def test_evaluator_only_rows_have_no_raw_text_or_runtime_feature_payload():
    path = (
        ROOT
        / "data/paper1_evaluator_only_rs/esconv_rs_strategy_family_match_evaluator_only_v1.jsonl"
    )
    rows = path.read_text(encoding="utf-8").splitlines()
    assert len(rows) == 11883
    forbidden = {
        "query_text",
        "current_user_text",
        "visible_dialogue_text",
        "model_features",
        "on_off_label",
        "outcome",
    }
    for line in rows:
        row = json.loads(line)
        assert row["evaluator_only"] is True
        assert row["source_split"] in {"train", "validation"}
        assert not forbidden & set(row)
        assert len(row["method_diagnostics"]) == 3
