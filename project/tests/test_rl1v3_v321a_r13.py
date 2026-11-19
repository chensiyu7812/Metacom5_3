"""Round 13: screening label report, post-screening re-plan, RAW inventory fingerprints (CPU only)."""
from __future__ import annotations

import json
import subprocess

import pytest

from metacom_pm.rl1v3.evaluate import fcms_replan as R
from metacom_pm.rl1v3.governance import inventory as I
from metacom_pm.rl1v3.review import pp1_sim as SIM
from metacom_pm.rl1v3.review import pp1_tool as T
from metacom_pm.rl1v3.review import screen_report as SR


def _log(pkg, steps):
    """Build a valid curator log in Python (independent of the JS core)."""
    events, prev, t = [], "genesis:" + pkg["package_sha256"], 0

    def add(kind, item=None, data=None, dt=1000):
        nonlocal prev, t
        t += dt
        ev = dict(seq=len(events), t=f"2030-01-01T00:{t // 60000:02d}:{(t // 1000) % 60:02d}.{t % 1000:03d}Z", kind=kind,
                  item=item, data=data, prev=prev)
        ev["h"] = T.event_hash(prev, ev)
        prev = ev["h"]
        events.append(ev)
    add("session_start", data={})
    for key, ans, opened in steps:
        add("view", key)
        if opened:
            add("ui", key, {"name": "history_open"})
        add("leave", key, dt=120000)
        add("submit", key, {"answer": ans})
    add("stage_lock", "S")
    v = T.replay([pkg], events)
    assert v["ok"], v["error"]
    stages = {"S": dict(items=len(steps), submitted=len(steps), locked=True)}
    return dict(schema=T.EXPORT_SCHEMA, packages=[pkg], events=events, head=prev,
                base_package_sha256=pkg["package_sha256"], stages=stages)


def _curator():
    cases = SIM.cases()[:5] + [SIM.rank0_case()]
    return T.curator_package(cases, assignee="C1", protocol=SIM.SIM_PROTOCOL, simulated=True, salt="s")


def test_screen_report_counts_and_time():
    pkg, amap = _curator()
    exp = _log(pkg, _steps(pkg))
    group_of = {f"sim-owner-{i}": ("g12" if i in (1, 2) else f"g{i}") for i in range(1, 10)}
    rep = SR.screen_report({"C1": exp}, {"C1": amap}, group_of, issued={pkg["package_sha256"]: pkg})
    assert rep["counts"] == dict(S1=2, S2=1, S0=1, unclear=1, S7=1)
    assert rep["s1_sessions_needed"] == {"one": 1, "multiple": 1} and rep["s1_multi_session_share"] == 0.5
    assert rep["unclear_share"] == 0.2 and rep["s1_without_required_span"] == 0
    assert rep["time"]["total_hours"] == pytest.approx(6 * 2 / 60, abs=0.01)
    assert rep["history_use"]["opened_share"] == 0.4


def _steps(pkg):
    view = T._merged([pkg])
    plan = ["S1", "S1", "S2", "S0", "unclear"]
    out = []
    for it in pkg["stages"][0]["items"]:
        if it["form"] == "S7":
            out.append((it["key"], dict(s7_confirm="none"), False))
            continue
        need = plan.pop(0)
        a = dict(need=need, risk=["none"])
        if need == "S1":
            ref = view["cases"][it["case_id"]]["history"]["sessions"][0]["turns"][0]["ref"]
            a.update(reason="it would repeat a failed idea", sessions_needed="multiple" if "S1" in plan else "one",
                     spans=[dict(ref=ref, role="required")])
        out.append((it["key"], a, need == "S1"))
    return out


def test_screen_report_refuses_unverified_or_unlocked():
    pkg, amap = _curator()
    exp = _log(pkg, _steps(pkg))
    bad = json.loads(json.dumps(exp))
    bad["events"][3]["data"] = {"name": "x"}
    with pytest.raises(ValueError):
        SR.screen_report({"C1": bad}, {"C1": amap}, {})
    open_ = json.loads(json.dumps(exp))
    open_["stages"]["S"]["locked"] = False
    with pytest.raises(ValueError):
        SR.screen_report({"C1": open_}, {"C1": amap}, {})


def _labels(n_groups, s1_per_group, other=2):
    rows = []
    for g in range(n_groups):
        for i in range(s1_per_group):
            rows.append(dict(prefix_id=f"p{g}s1{i}", owner_id=f"o{g}", group=f"g{g}", need="S1"))
        for j, need in enumerate(["S2", "S0", "unclear", "S7"][:other + 2]):
            rows.append(dict(prefix_id=f"p{g}x{j}", owner_id=f"o{g}", group=f"g{g}", need=need))
    return rows


def test_replan_medium_and_downgrade():
    r = R.replan(_labels(17, 3), plan="medium")
    assert r["k_s1"] == 17 and r["s1_prefixes"] == 34 and r["guard_prefixes"] == 34 and not r["downgraded"]
    assert r["generator_calls"] == 3 * 68
    assert min(x["mde"] for x in r["mde_grid"]) < 0.4
    small = R.replan(_labels(6, 2), plan="medium")
    assert small["downgraded"] and "descriptive" in small["primary_mode"]
    with pytest.raises(ValueError):
        R.replan([dict(prefix_id="a", owner_id="o", group="g", need="S1", reply_score=1)])


def test_fingerprints_and_scan_on_a_tiny_repo(tmp_path):
    art = dict(users=[dict(owner_id="p1", sessions=[
        dict(session_id="p1_conv_1", turns=[dict(content="I have been worried about my sister's wedding plans lately, honestly.")]),
        dict(session_id="esc12", turns=[dict(content="My job interview went badly and I keep replaying every single question.")])])])
    esc = [dict(dialog=[dict(content="The neighbours play loud music every night and I cannot sleep at all anymore.")])]
    fps = I.fingerprints(art, esc, n_evo=5, n_esc_in_evo=5, n_esc=5)
    kinds = {k for k, _ in fps.values()}
    assert kinds == {"evoemo_generated", "esconv_in_evoemo", "esconv_only"}
    assert any("&#x27;" in x for x in fps)
    repo = tmp_path / "r"
    repo.mkdir()
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True)
    (repo / "a.json").write_text(json.dumps({"t": list(fps)}))
    (repo / "b.txt").write_text("nothing here")
    subprocess.run(["git", "add", "."], cwd=repo, check=True)
    subprocess.run(["git", "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-qm", "x"], cwd=repo, check=True)
    hits, stats = I.scan(repo, ["main"], fps, min_hits=1)
    assert stats["unique_blobs"] == 2
    assert set(hits) == {"a.json"}
    assert "fingerprint" not in json.dumps(hits) and "wedding" not in json.dumps(hits)   # no RAW text in the output
