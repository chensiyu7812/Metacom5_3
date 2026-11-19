"""PP1 review tool: JS core <-> Python verifier parity, replay rules, blinding, package gating (CPU, Node only)."""
from __future__ import annotations

import copy
import json
import random
import shutil
import subprocess
from pathlib import Path

import pytest

from metacom_pm.rl1v3.review import pp1_sim as SIM
from metacom_pm.rl1v3.review import pp1_tool as T

CORE = Path(T.__file__).with_name("pp1_core.js")
NODE = shutil.which("node")


def node(script: str, payload) -> dict:
    assert NODE, "node is required for the review-tool core tests"
    r = subprocess.run([NODE, "-e", script, str(CORE)], input=json.dumps(payload), capture_output=True, text=True,
                       timeout=120)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


READ = "const C=require(process.argv[1]);let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{const P=JSON.parse(s);"


def _rand_obj(rng, depth=0):
    kind = rng.randrange(7 if depth < 3 else 4)
    if kind == 0:
        return rng.randrange(-10 ** 9, 10 ** 9)
    if kind == 1:
        return "".join(rng.choice("aZ 中文\n\t\"\\/é😀 \x01<>&'") for _ in range(rng.randrange(12)))
    if kind == 2:
        return rng.choice([True, False, None])
    if kind == 3:
        return ""
    if kind == 4:
        return [_rand_obj(rng, depth + 1) for _ in range(rng.randrange(4))]
    return {f"k{rng.randrange(50)}_{i}": _rand_obj(rng, depth + 1) for i in range(rng.randrange(5))}


def test_canon_and_sha_match_between_js_and_python():
    rng = random.Random(7)
    objs = [_rand_obj(rng) for _ in range(300)]
    out = node(READ + "console.log(JSON.stringify(P.map(o=>[C.canon(o),C.sha256(C.canon(o))])))});", objs)
    for o, (c, h) in zip(objs, out):
        assert c == T.canon(o)
        assert h == T.sha(T.canon(o))


def test_canon_rejects_floats_and_non_ascii_keys_on_both_sides():
    for bad in ({"a": 1.5}, {"键": 1}):
        with pytest.raises(ValueError):
            T.canon(bad)
    out = node(READ + "const r=P.map(o=>{try{C.canon(o);return 'ok'}catch(e){return 'err'}});console.log(JSON.stringify(r))});",
               [{"a": 1.5}, {"键": 1}])
    assert out == ["err", "err"]


def _sim_reviewer():
    cases = SIM.cases()
    reps, pairs, _ = SIM.replies(cases)
    p1, mk, au = T.reviewer_packages(cases, reps, pairs, assignee="R1", protocol=SIM.SIM_PROTOCOL, simulated=True,
                                     salt=SIM.SIM_SALT)
    return cases, reps, pairs, p1, mk, au


SCRIPT_LOG = READ + r"""
const pkg=P.pkg, plan=P.plan; let st=C.newState([pkg]); const ev=[]; const errs=[];
let t=Date.parse('2030-01-01T00:00:00.000Z');
function add(kind,item,data){ t+=1500; const e=C.makeEvent(st,kind,item,data,new Date(t).toISOString());
  try{ C.apply(st,e,[pkg]); ev.push(e); return true;}catch(x){ errs.push(kind+':'+x.message); return false;} }
add('session_start',null,{});
for (const step of plan) add(step[0], step[1], step[2]);
console.log(JSON.stringify({events:ev, errs, head:st.head, export:C.buildExport(st,ev,'final','2030-01-02T00:00:00.000Z')}));
});"""


def _q0_answer(ov="A"):
    a = dict(overall=ov, sub_natural="A", sub_empathy="same", sub_need="B", sub_advice="unsure", sub_autonomy="same",
             suff_A="full", suff_B="partial")
    if ov in ("A", "B"):
        a["strength"] = "2"
    return a


def test_js_log_reverifies_in_python_and_rules_agree():
    *_, p1, mk, au = _sim_reviewer()
    items = [it["key"] for it in p1["stages"][0]["items"]]
    plan = [["view", items[0], None], ["draft", items[0], {"answer": {"overall": "A"}}],
            ["submit", items[0], {"answer": {"overall": "A"}}],                      # incomplete -> refused
            ["submit", items[0], {"answer": _q0_answer()}],
            ["draft", items[0], {"answer": _q0_answer("B")}],                      # after lock -> refused
            ["stage_lock", "Q0", None]]                                            # 7 unsubmitted -> refused
    plan += [["submit", k, {"answer": _q0_answer("same")}] for k in items[1:]] + [["stage_lock", "Q0", None]]
    out = node(SCRIPT_LOG, dict(pkg=p1, plan=plan))
    assert [e.split(":")[0] for e in out["errs"]] == ["submit", "draft", "stage_lock"]
    assert "already locked" in out["errs"][1]
    v = T.verify_export(out["export"], {p1["package_sha256"]: p1})
    assert v["ok"], v["error"]
    assert v["stages"]["Q0"]["locked"] and v["head"] == out["head"]
    # part 2 only loads with the right anchor
    lock_h = out["export"]["stages"]["Q0"]["lock_event_h"]
    good, bad = mk(lock_h), mk("0" * 64)
    load = READ + r"""
const exp=P.exp; const r=C.replay(exp.packages, exp.events); let st=r.state; const out=[];
for (const p of [P.bad, P.good]) { const e=C.makeEvent(st,'package_load',null,{package_sha256:p.package_sha256},'2030-01-03T00:00:00.000Z');
  try { C.apply(st,e,[...exp.packages,P.bad,P.good]); out.push('ok'); } catch(x) { out.push(x.message); } }
console.log(JSON.stringify(out)); });"""
    res = node(load, dict(exp=out["export"], good=good, bad=bad))
    assert "anchor mismatch" in res[0] and res[1] == "ok"


def test_python_replay_refuses_what_js_refuses():
    *_, p1, _mk, _au = _sim_reviewer()
    items = [it["key"] for it in p1["stages"][0]["items"]]
    plan = [["submit", k, {"answer": _q0_answer()}] for k in items] + [["stage_lock", "Q0", None], ["view", items[0], None]]
    out = node(SCRIPT_LOG, dict(pkg=p1, plan=plan))
    assert len(out["errs"]) == 1 and "locked stage" in out["errs"][0]
    exp = out["export"]
    # forge the refused 'view' into the log with a valid hash: the Python rules must reject it too
    e = copy.deepcopy(exp)
    last = e["events"][-1]
    ev = dict(seq=last["seq"] + 1, t=last["t"], kind="view", item=items[0], data=None, prev=last["h"])
    ev["h"] = T.event_hash(last["h"], ev)
    e["events"].append(ev)
    e["head"] = ev["h"]
    r = T.verify_export(e)
    assert not r["ok"] and "view not allowed" in r["error"]


def test_blind_packages_carry_no_condition_label_or_history():
    cases, reps, pairs, p1, mk, au = _sim_reviewer()
    forbidden = [r["reply_key"] for r in reps] + [c["case_key"] for c in cases]
    assert T.blind_scan(p1, forbidden_ids=forbidden) == []
    assert all(c["history"] is None for c in p1["cases"].values())
    p2 = mk("a" * 64)
    assert T.blind_scan(p2, forbidden_ids=forbidden) == []
    assert all(c["history"] for c in p2["cases"].values())
    assert set(au["conditions"].values()) == {"OFF", "RET-MS"}
    leaked = copy.deepcopy(p1)
    next(iter(leaked["replies"].values()))["arm"] = "DP-MS"
    assert T.blind_scan(leaked)


def test_positions_are_balanced_and_mirrored():
    cases = SIM.cases()
    reps, pairs, _ = SIM.replies(cases)
    a = [T.reviewer_packages(cases, reps, pairs, assignee=r, protocol=SIM.SIM_PROTOCOL, simulated=True,
                             salt=SIM.SIM_SALT, mirror=r == "R2")[2] for r in ("R1", "R2")]
    bal = T.position_balance(a)
    assert all(v["control_in_A"] == 4 for v in bal.values())
    for p in a[0]["pairs"]:
        for ch in ("Q0", "QH"):
            assert a[0]["pairs"][p]["positions"][ch]["A"]["condition"] != a[1]["pairs"][p]["positions"][ch]["A"]["condition"]


def test_form_rules_curator_and_f():
    cs = SIM.cases()[:1]
    pkg, _ = T.curator_package(cs, assignee="C", protocol=SIM.SIM_PROTOCOL, simulated=True, salt="s")
    view = T._merged([pkg])
    it = next(iter(view["items"].values()))
    ref = view["cases"][it["ref"]["case_id"]]["history"]["sessions"][0]["turns"][0]["ref"]
    base = dict(need="S1", risk=["none"])
    errs = T.validate_answer(view, it, base, True)
    assert any("reason" in e for e in errs) and any("span" in e for e in errs)
    ok = dict(base, reason="the reply would repeat a failed idea", spans=[dict(ref=ref, role="required")])
    assert T.validate_answer(view, it, ok, True) == []
    assert T.validate_answer(view, it, dict(ok, risk=["none", "stale"]), True)          # exclusive option
    # F: yes needs severity, verbatim quote and a source (F5 may use no_source)
    _c, _r, _p, p1, mk, _a = _sim_reviewer()
    p2 = mk("b" * 64)
    v2 = T._merged([p1, p2])
    fit = next(i for k, i in v2["items"].items() if k.startswith("F:"))
    reply = v2["replies"][fit["ref"]["reply_id"]]["text"]
    no = {f"F{i}": dict(presence="no") for i in range(1, 9)}
    assert T.validate_answer(v2, fit, no, True) == []
    bad = dict(no, F5=dict(presence="yes", severity="serious", quote="not in the reply at all", no_source=True))
    assert any("verbatim" in e for e in T.validate_answer(v2, fit, bad, True))
    assert T.validate_answer(v2, fit, bad, False) == []                                 # drafts may hold it
    good = dict(no, F5=dict(presence="yes", severity="serious", quote=reply[:20], no_source=True))
    assert T.validate_answer(v2, fit, good, True) == []
    f1 = dict(no, F1=dict(presence="yes", severity="minor", quote=reply[:20], no_source=True))
    assert any("no_source not allowed" in e for e in T.validate_answer(v2, fit, f1, True))


def test_audit_packages_require_fully_locked_finals():
    *_, p1, _mk, _au = _sim_reviewer()
    exp = node(SCRIPT_LOG, dict(pkg=p1, plan=[]))["export"]
    with pytest.raises(ValueError):
        T.adjudication_package({"R1": exp, "R2": exp}, assignee="A", protocol=SIM.SIM_PROTOCOL, simulated=True, salt="s")


def test_render_html_embeds_package_safely():
    *_, p1, _mk, _au = _sim_reviewer()
    p = copy.deepcopy(p1)
    next(iter(p["replies"].values()))["text"] = "a </script><script>alert(1)</script> b"
    html = T.render_html(T.seal(p))
    assert "</script><script>alert(1)" not in html and "<\\/script>" in html
    assert html.count('id="pp1-package"') == 1
    assert "{{" not in html
