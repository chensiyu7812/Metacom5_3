"""R15: Chinese-first display layer, ChatGPT hand-off checks, per-person packages (synthetic material only)."""
import copy
import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts/rl1v3"))

from metacom_pm.rl1v3.review import pp1_sim as SIM  # noqa: E402
from metacom_pm.rl1v3.review import pp1_tool as T  # noqa: E402
import V321A_r15 as R  # noqa: E402

TEXTS = ["Hi", "I'm doing ok. How about you?", "yes.i have sleeping problem", "Mr. Smith said no. I left!",
         "Line one\nLine two.\n\nAfter a gap...", "   leading space. Then more.  ", "...", "Wow!!! Really?? ok",
         "It costs $20 (or 30). Fine.", "emoji 😀 here. 再见", "", "   "]


@pytest.mark.parametrize("t", TEXTS)
def test_segments_lossless_and_contentful(t):
    seg = T.segments(t)
    assert "".join(seg) == (t if t.strip() else "")
    if t.strip():
        assert seg and all(s.strip() for s in seg)
        assert len(seg) == 1 or all(any(c.isalnum() for c in s) for s in seg)


def test_segments_split_and_abbreviation():
    assert len(T.segments("I'm doing ok. How about you?")) == 2
    assert len(T.segments("Mr. Smith came. He left.")) == 2
    assert T.join_zh(["A.\n", "B."], ["甲。", "乙。"]) == "甲。\n乙。"


def test_line_checks():
    assert R.check_line("I have 2 dogs.", "我有两只狗。")[0] == ["digits_changed:2"]
    assert R.check_line("I have 2 dogs.", "我有 2 只狗。（译注：口语）")[0] == ["translator_note"]
    assert "copied_english" in R.check_line("Thank you so much.", "Thank you so much.")[0]
    assert R.check_line("I do not know.", "我知道。")[1] == ["negation_check"]
    assert R.check_line("ok", "ok") == ([], [])
    assert R.check_line("Hello there.", "")[0] == ["empty"]


def test_parse_returned_overrides_and_strips_speaker(tmp_path):
    a, b = tmp_path / "B01.zh.txt", tmp_path / "B01.fix1.zh.txt"
    a.write_text("[0001] 求助者｜你好\n[0002] 错的\nnoise line\n", encoding="utf-8")
    b.write_text("[0002] 对的\n", encoding="utf-8")
    assert R.parse_returned([a, b]) == {"0001": "你好", "0002": "对的"}
    rows = [dict(id="0001", text="Hello"), dict(id="0002", text="Right."), dict(id="0003", text="Missing one.")]
    rep = R.check_batch("B01", rows, R.parse_returned([a, b]))
    assert not rep["ok"] and {h["code"] for h in rep["hard"]} == {"missing"}


def _zh_curator():
    cs = R._sim_with_zh(SIM.cases()[:3] + [SIM.rank0_case()])
    zh, _ = T.curator_package(cs, assignee="X", protocol=SIM.SIM_PROTOCOL, simulated=True, salt=SIM.SIM_SALT,
                              translation_method="t", translator_role="t")
    en, _ = T.curator_package(SIM.cases()[:3] + [SIM.rank0_case()], assignee="X", protocol=SIM.SIM_PROTOCOL,
                              simulated=True, salt=SIM.SIM_SALT)
    return zh, en


def test_translation_layer_keeps_english_identity_and_blinding():
    zh, en = _zh_curator()
    assert R._same_source(zh, en) and zh["package_sha256"] != en["package_sha256"]
    assert zh["translation"]["provided"] and zh["translation"]["units"] > 0
    assert not T.blind_scan(zh, forbidden_ids=["sim-case-1", "sim-owner-1"], role="curator")
    c = next(iter(zh["cases"].values()))
    assert T.case_check(c) == T.case_check(next(v for v in en["cases"].values() if v["label"] == c["label"]))
    bad = copy.deepcopy(R._sim_with_zh(SIM.cases()[:1]))
    bad[0]["prefix"][0]["zh_seg"] = bad[0]["prefix"][0]["zh_seg"] + ["多出来的一句"]
    with pytest.raises(ValueError):
        T.curator_package(bad, assignee="X", protocol=SIM.SIM_PROTOCOL, simulated=True, salt=SIM.SIM_SALT)


def test_case_check_same_in_page_and_python():
    zh, _ = _zh_curator()
    c = next(iter(zh["cases"].values()))
    core = (ROOT / "src/metacom_pm/rl1v3/review/pp1_core.js").read_text(encoding="utf-8")
    js = core + """
const C = module.exports;
function enOnly(o){ if(Array.isArray(o)) return o.map(enOnly); if(o && typeof o==='object'){ const r={};
  Object.keys(o).forEach(k=>{ if(k!=='zh'&&k!=='zh_seg'&&k!=='seg') r[k]=enOnly(o[k]); }); return r;} return o; }
const c = JSON.parse(require('fs').readFileSync(0,'utf8'));
process.stdout.write(C.sha256(C.canon(enOnly({prefix: c.prefix===undefined?null:c.prefix, history: c.history===undefined?null:c.history}))).slice(0,12));
"""
    node = shutil.which("node")
    assert node, "node is required (the core JS tests use it too)"
    out = subprocess.run([node, "-e", js], input=json.dumps(c), capture_output=True, text=True, check=True).stdout
    assert out == T.case_check(c)


def test_reply_batch_is_neutral_and_reviewers_identical_and_mirrored():
    cs = SIM.cases()[:3]
    reps, pairs, _ = SIM.replies(cs)
    text, rows = R.reply_batch(reps, salt="unit-test-salt")
    for x in [r["reply_key"] for r in reps] + [c["case_key"] for c in cs] + ["OFF", "RET", "pair", "sim-case"]:
        assert x not in text
    per = {}
    for r in reps:
        for j, z in enumerate(R.sim_zh(r["text"])):
            per[(r["reply_key"], j)] = z
    got = {r["id"]: per[(r["reply_key"], r["seg"])] for r in rows}
    tm = R.reply_translation(rows, got)
    out = R.build_reviewers(R._sim_with_zh(cs), reps, pairs, salt="unit-test-salt", history_tm=None, reply_tm=tm,
                            protocol=SIM.SIM_PROTOCOL, simulated=True)
    p1 = out["R1"][0]
    assert all(v.get("zh_seg") for v in p1["replies"].values())
    assert all(c["history"] is None for c in p1["cases"].values())
    forbidden = [r["reply_key"] for r in reps] + [p[0] for p in pairs] + [c["case_key"] for c in cs] + ["RET-MS"]
    assert not T.blind_scan(p1, forbidden_ids=forbidden)
    with pytest.raises(ValueError):
        R.reply_translation(rows, dict(list(got.items())[1:]))


def test_page_check_passes_clean_page_and_refuses_logic_change(tmp_path):
    zh, en = _zh_curator()
    f = tmp_path / "ok.html"
    f.write_text(T.render_html(zh), encoding="utf-8")
    r = R.check_html(f, issued={en["package_sha256"]: en}, forbidden=["sim-case-1"])
    assert r["ok"], [c for c in r["checks"] if not c["ok"]]
    g = tmp_path / "bad.html"
    g.write_text(T.render_html(zh).replace("'use strict';", "'use strict'; var tampered = 1;", 1), encoding="utf-8")
    assert not R.check_html(g, issued={en["package_sha256"]: en}, forbidden=[])["ok"]
    h = tmp_path / "en.html"
    h.write_text(T.render_html(en), encoding="utf-8")
    assert not R.check_html(h, issued={en["package_sha256"]: en}, forbidden=[])["ok"]   # untranslated page


def test_dist_gate_rules_without_dp_module():
    from metacom_pm.rl1v3.review import dist_gate as G

    class FakeD:
        @staticmethod
        def check_reviewer(plan, bundle, receipts, roles, pid, rv, ch):
            if rv not in roles["assignments"][pid]["reviewers"][ch]:
                raise RuntimeError("not assigned")
    roles = dict(people={"R1": "p-r1", "R2": "p-r2", "CUR1": "p-c1", "CUR2": "p-c2"},
                 assignments={"a": dict(selector="CUR1", reviewers={c: ["R1", "R2"] for c in ("Q0", "QH", "F")}),
                              "b": dict(selector="CUR2", reviewers={c: ["R1", "R2"] for c in ("Q0", "QH", "F")})})
    rec = {"a": dict(selector="CUR1"), "b": dict(selector="CUR2")}
    pk = [(p, c, r) for p in "ab" for c in ("Q0", "QH", "F") for r in ("R1", "R2")]
    out = G.check_distribution(FakeD, {}, {}, rec, roles, pk, adjudicator="CUR2", second_receipts={"a": dict(selector="CUR2")})
    assert out["adjudication"]["allowed"] == [] and set(out["adjudication"]["blocked"]) == {"a", "b"}
    out = G.check_distribution(FakeD, {}, {}, rec, roles, pk, adjudicator="CUR2")
    assert out["adjudication"]["allowed"] == ["a"]
    with pytest.raises(G.GateRefused):
        G.check_distribution(FakeD, {}, {}, rec, roles, pk + [("a", "QH", "CUR1")])
    with pytest.raises(G.GateRefused):
        G.check_distribution(FakeD, {}, {}, rec, roles, pk, adjudicator="CUR1")


def test_sim_translation_covers_all_practice_text():
    cs = SIM.cases() + [SIM.rank0_case()]
    reps, _p, _r = SIM.replies(SIM.cases())
    for t in [t["text"] for c in cs for t in c["prefix"] + [x for s in c["history"] for x in s["turns"]]] + \
             [r["text"] for r in reps]:
        assert len(R.sim_zh(t)) == len(T.segments(t))
