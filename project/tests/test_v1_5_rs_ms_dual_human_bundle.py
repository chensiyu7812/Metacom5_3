import importlib.util
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts/v1_5/249l_materialize_paper1_v3_rs_ms_dual_human_bundle_v1_5.py"
SPEC = importlib.util.spec_from_file_location("rs_ms_human_bundle", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_quality_v2_hides_source_and_balances_position():
    public, private = MODULE.quality_v2()
    assert len(public) == len(private) == 16
    assert sum(row["MS_ON_presented_as"] == "A" for row in private) == 8
    assert sum(row["MS_ON_presented_as"] == "B" for row in private) == 8
    text = MODULE.canonical_json(public).lower()
    assert "strictly_past" not in text
    assert "ms+rs" not in text
    assert all("verified_strictly_past_source_for_factual_check_only" not in row for row in public)


def test_human_ui_contains_all_constructs_without_network_dependency():
    public, _private = MODULE.quality_v2()
    risk = MODULE.rows(MODULE.RISK)
    function = MODULE.rows(MODULE.FUNCTION)
    page = MODULE.review_html(reviewer="HUMAN_A", quality=public, risk=risk, function=function)
    assert "DATA.quality.map(quality)" in page
    assert "DATA.risk.map(risk)" in page
    assert "DATA.function.map(func)" in page
    assert page.count('"blind_item_id"') == 64
    assert "exportNow" in page
    assert "http://" not in page and "https://" not in page
