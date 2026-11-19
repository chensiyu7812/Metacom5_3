#!/usr/bin/env python3
"""WS-B round 12 (V3.2.1-A): version-A protocol, PP1 blind-review tool, FC-MS design/power/budget, screening package,
renderer acceptance plan, licence evidence, admission one-pager.  CPU only: no GPU, Generator, Judge or paid call.

Steps (each writes under outputs/pm_rl1/v3/V321A_WSB/<step>/):
  tool        build the generic offline HTML tool + the real PP1 curator package (package kept OFF the public repo)
  e2e         full simulated PP1 in headless Chrome (curator -> Q0 -> anchor -> part 2 -> QH/probe/F -> adjudication
              -> F-A) + Python re-verification, tamper tests and blinding scans
  protocol    V3.2.1-A protocol object + item-by-item diff against V3.2.1 (d2fde5db) and #17 (b28cf37b)
  fcms        FC-MS questions, analysis family, power and three budget plans
  screenpack  execution package for the frozen 90-item screen (owner-blocked, stratum-blind)
  renderer    acceptance plan + checker dry run for a unified renderer candidate; entity census of RAW
  license     upstream licence evidence table
  admission   one-page admission table
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1].parent
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts/rl1v3"))

from metacom_pm.rl1v3.io import build_manifest, file_sha256, object_sha256  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OUT = V3 / "V321A_WSB"
V321 = V3 / "V321_WSB"
PRIVATE = Path(os.environ.get("PP1_PRIVATE_DIR", "/opt/tokkio-data0/tokkio_projects/pmrl1-validation/wsb-v321a-private"))
RUNS = Path(os.environ.get("PP1_RUN_DIR", "/opt/tokkio-data0/tokkio_runs/wsb_v321a"))
CHROME = os.environ.get("CHROME", shutil.which("google-chrome") or "/usr/bin/google-chrome")
NODE = os.environ.get("NODE", shutil.which("node") or "/usr/bin/node")
REVIEW = PROJECT / "src/metacom_pm/rl1v3/review"


def jdump(path: Path, obj, *, pretty=True):
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, indent=1 if pretty else None, sort_keys=True)
    path.write_text(text + "\n", encoding="utf-8")
    return path


def head_sha() -> str:
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()


def manifest(step: str, inputs: dict, outputs: list[Path], code: list[Path]):
    man = build_manifest(task=f"V321A_wsb_{step}", root=PROJECT, inputs={k: Path(v) for k, v in inputs.items()},
                         code=[Path(__file__)] + code, code_sha=head_sha(), outputs=outputs)
    jdump(OUT / step / "MANIFEST.json", man)


TOOL_CODE = [REVIEW / "pp1_core.js", REVIEW / "pp1_ui.js", REVIEW / "pp1_tool.css", REVIEW / "pp1_tool.html",
             REVIEW / "pp1_tool.py"]


# ------------------------------------------------------------------ real PP1 material (cases only; no replies yet)
def pp1_cases():
    from metacom_pm.rl1v3.asof import e1_receipt as E
    import V321_wsb_pr18_receipt as S
    raw = E.Raw(json.loads(S.ARTIFACT.read_text()))
    census = {c["prefix_id"]: c for c in map(json.loads, S.CENSUS.read_text().splitlines())}
    order = json.loads(S.SELECTION.read_text())["selected_ids"]
    qh = {r["prefix_id"]: r for r in json.loads((V321 / "pp1/QH_BACKGROUNDS.json").read_text())["rows"]}
    cases = []
    for k, pid in enumerate(order):
        c = census[pid]
        sess = raw.sessions[(c["owner_id"], c["session_id"])]
        prefix = sess["turns"][:c["cut_turn"] + 1]
        legal = raw.legal_past(c["owner_id"], c["cutoff_rank"], c["timestamp"])
        hist = [dict(date=s["date"], turns=s["turns"]) for s in legal]
        if [(s["rank"], s["date"]) for s in legal] != [(x["rank"], x["date"]) for x in qh[pid]["sessions"]]:
            raise SystemExit(f"{pid[:12]}: legal history differs from the frozen QH background")
        cases.append(dict(case_key=pid, owner_key=c["owner_id"], order_key=c["cutoff_rank"], prefix=prefix,
                          history=hist, words=qh[pid]["words"], background_sha256=qh[pid]["background_sha256"]))
    return cases


def step_tool(_):
    from metacom_pm.rl1v3.review import pp1_tool as T
    out = OUT / "pp1_tool"
    out.mkdir(parents=True, exist_ok=True)
    generic = out / "PP1_REVIEW_TOOL.html"
    generic.write_text(T.render_html(None), encoding="utf-8")
    # real curator package for the 8 PP1 prefixes: data are RAW conversations -> written OFF the public repo
    cases = pp1_cases()
    protocol = json.loads((OUT / "protocol/PROTOCOL_V321A_CANDIDATE.json").read_text()) \
        if (OUT / "protocol/PROTOCOL_V321A_CANDIDATE.json").exists() else None
    proto = dict(id="pmrl1v3-v321a-pp1", sha256=(protocol or {}).get("protocol_sha256", "pending"))
    salt_note = "real salt is generated and held by the coordinator; this curator package needs none for blinding"
    pkg, amap = T.curator_package([dict(c, history=c["history"]) for c in cases], assignee="CUR1", protocol=proto,
                                  simulated=False, salt="pp1-curator-order-v1")
    hits = T.blind_scan(pkg, forbidden_ids=[c["case_key"] for c in cases] + ["p15_conv_1", "esc371", "p13_conv_9",
                                                                             "p2_conv_6", "p8_conv_1", "p11_conv_13",
                                                                             "p5_conv_3", "esc471"], role="curator")
    PRIVATE.mkdir(parents=True, exist_ok=True)
    priv_pkg = jdump(PRIVATE / "PP1_CURATOR_CUR1.package.json", pkg, pretty=False)
    priv_html = PRIVATE / "PP1_CURATOR_CUR1.html"
    priv_html.write_text(T.render_html(pkg, title="PP1 生成前筛查"), encoding="utf-8")
    jdump(PRIVATE / "PP1_CURATOR_CUR1.audit_map.json", amap)
    reg = dict(
        kind="PP1 curator package registry (contents kept off the public repository)",
        reason="the package holds full RAW conversations; licence for public redistribution is unresolved "
               "(see license/LICENSE_EVIDENCE_ZH.md), so only hashes are committed",
        package_sha256=pkg["package_sha256"], items=len(pkg["stages"][0]["items"]),
        forms=sorted({i["form"] for i in pkg["stages"][0]["items"]}),
        words=[c["words"] for c in cases], qh_background_sha256=[c["background_sha256"] for c in cases],
        blind_scan_hits=hits, html_sha256=file_sha256(priv_html), private_dir=str(PRIVATE),
        rebuild="python scripts/rl1v3/V321A_wsb.py tool  (deterministic; same sha256)", salt_note=salt_note,
        assignment_note="assignee code CUR1 is a placeholder; the coordinator rebuilds with the real pseudonymous code")
    jdump(out / "PP1_CURATOR_PACKAGE_REGISTRY.json", reg)
    manifest("pp1_tool", {"qh_backgrounds": V321 / "pp1/QH_BACKGROUNDS.json"},
             [generic, out / "PP1_CURATOR_PACKAGE_REGISTRY.json"], TOOL_CODE)
    print(json.dumps(dict(generic=str(generic), curator_items=reg["items"], curator_sha=pkg["package_sha256"][:12],
                          blind_hits=len(hits))))


# ------------------------------------------------------------------ e2e (simulated)
EST_MIN = dict(S=8, Q0=1.5, QH=3, PROBE=0.3, F=4, ADJ=3, FA=1)


def _node(phase: str, cfg: dict, cfgpath: Path, log: Path) -> dict:
    jdump(cfgpath, cfg)
    t0 = time.time()
    r = subprocess.run([NODE, str(PROJECT / "scripts/rl1v3/V321A_pp1_e2e.mjs"), phase, str(cfgpath)],
                       capture_output=True, text=True, timeout=900)
    log.write_text(f"$ node V321A_pp1_e2e.mjs {phase}\n{r.stdout}\n{r.stderr}\nexit={r.returncode} "
                   f"seconds={time.time() - t0:.1f}\n")
    res = json.loads(Path(cfg["out"]).read_text())
    res["exit"] = r.returncode
    return res


def step_e2e(args):
    from metacom_pm.rl1v3.review import pp1_sim as SIM
    from metacom_pm.rl1v3.review import pp1_tool as T
    work = RUNS / f"e2e_{time.strftime('%Y%m%d_%H%M%S')}"
    work.mkdir(parents=True)
    out = OUT / "pp1_e2e"
    if out.exists():
        shutil.rmtree(out)
    (out / "exports").mkdir(parents=True)
    logs = out / "logs"
    logs.mkdir()
    checks = []

    def ck(name, ok, detail=None):
        checks.append(dict(name=name, ok=bool(ok), detail=detail, by="python"))

    proto = SIM.SIM_PROTOCOL
    generic = work / "PP1_REVIEW_TOOL.html"
    generic.write_text(T.render_html(None), encoding="utf-8")
    cases = SIM.cases()
    reps, pairs, resources = SIM.replies(cases)
    forbidden = [r["reply_key"] for r in reps] + [p[0] for p in pairs] + [c["case_key"] for c in cases] + \
                ["sim-owner-", "RET-MS"]

    # curator
    cur_pkg, cur_map = T.curator_package(cases + [SIM.rank0_case()], assignee="CUR1", protocol=proto, simulated=True,
                                         salt=SIM.SIM_SALT, translate=SIM.translate, translation_method="mock (test only)")
    ck("curator package passes the blind scan", not T.blind_scan(cur_pkg, forbidden_ids=forbidden, role="curator"),
       T.blind_scan(cur_pkg, forbidden_ids=forbidden, role="curator")[:3])
    cur_file = jdump(work / "curator.package.json", cur_pkg, pretty=False)
    cur_html = work / "curator.html"
    cur_html.write_text(T.render_html(cur_pkg), encoding="utf-8")

    # reviewers part 1
    revs, audits, make2 = {}, {}, {}
    for rid in ("R1", "R2"):
        p1, mk, au = T.reviewer_packages(cases, reps, pairs, assignee=rid, protocol=proto, simulated=True,
                                         salt=SIM.SIM_SALT, mirror=rid == "R2", translate=SIM.translate,
                                         translation_method="mock (test only)")
        hits = T.blind_scan(p1, forbidden_ids=forbidden)
        ck(f"{rid} part 1 passes the blind scan", not hits, hits[:3])
        ck(f"{rid} part 1 carries no history", all(c["history"] is None for c in p1["cases"].values()))
        revs[rid], audits[rid], make2[rid] = p1, au, mk
        (work / f"{rid}.html").write_text(T.render_html(p1), encoding="utf-8")
    balance = T.position_balance(list(audits.values()))
    ck("positions exactly balanced per channel (4 of 8 control replies in slot 甲)",
       all(v["control_in_A"] * 2 == v["pairs"] for v in balance.values()), balance)
    ck("second reviewer sees every pair in the mirrored order",
       all(audits["R1"]["pairs"][p]["positions"][ch]["A"]["condition"] != audits["R2"]["pairs"][p]["positions"][ch]["A"]["condition"]
           for p in audits["R1"]["pairs"] for ch in ("Q0", "QH")))

    base = dict(chrome=CHROME, generic_html=str(generic), tmpdir=str(work))
    cfg = dict(base, out=str(work / "res_curator.json"), curator=dict(
        html=str(cur_html), package_file=str(cur_file), n_items=len(cur_pkg["stages"][0]["items"]),
        profile1=str(work / "prof_cur1"), profile2=str(work / "prof_cur2"), profile3=str(work / "prof_cur3"),
        downloads=str(work / "dl_cur")))
    res = {"curator": _node("curator", cfg, work / "cfg_curator.json", logs / "node_curator.log")}
    cfiles = res["curator"].get("files", {})
    issued = {cur_pkg["package_sha256"]: cur_pkg}
    for k, f in cfiles.items():
        exp = json.loads(Path(f).read_text())
        v = T.verify_export(exp, issued)
        ck(f"curator {k} export re-verifies in Python", v["ok"], v.get("error"))
        shutil.copy(f, out / "exports" / f"curator_{k}.json")
    if "progress" in cfiles and "final" in cfiles:
        ck("curator final export extends the earlier progress export",
           T.extends(json.loads(Path(cfiles["progress"]).read_text()), json.loads(Path(cfiles["final"]).read_text())))

    rcfg = [dict(id=r, html=str(work / f"{r}.html"), profile1=str(work / f"prof_{r}_1"), profile2=str(work / f"prof_{r}_2"),
                 downloads=str(work / f"dl_{r}")) for r in ("R1", "R2")]
    cfg = dict(base, out=str(work / "res_q0.json"), reviewers=rcfg)
    res["q0"] = _node("q0", cfg, work / "cfg_q0.json", logs / "node_q0.log")
    anchors = {}
    for r in ("R1", "R2"):
        f = res["q0"].get("files", {}).get(r)
        if not f:
            ck(f"{r} Q0 stage export exists", False)
            continue
        exp = json.loads(Path(f).read_text())
        v = T.verify_export(exp, {revs[r]["package_sha256"]: revs[r]})
        ck(f"{r} Q0 stage export re-verifies in Python and Q0 is locked", v["ok"] and exp["stages"]["Q0"]["locked"],
           v.get("error"))
        anchors[r] = dict(lock_event_h=exp["stages"]["Q0"]["lock_event_h"], head=exp["head"], file=f)
        shutil.copy(f, out / "exports" / f"{r}_q0_stage.json")
        p2 = make2[r](anchors[r]["lock_event_h"])
        bad = make2[r]("0" * 64)
        hits = T.blind_scan(p2, forbidden_ids=forbidden)
        ck(f"{r} part 2 passes the blind scan", not hits, hits[:3])
        jdump(work / f"{r}.part2.json", p2, pretty=False)
        jdump(work / f"{r}.part2_bad_anchor.json", bad, pretty=False)
        revs[r + ":2"] = p2
        for rc in rcfg:
            if rc["id"] == r:
                rc.update(part2=str(work / f"{r}.part2.json"), bad_part2=str(work / f"{r}.part2_bad_anchor.json"))
    jdump(out / "ANCHORS.json", {r: {k: v for k, v in a.items() if k != "file"} for r, a in anchors.items()})

    cfg = dict(base, out=str(work / "res_rest.json"), reviewers=rcfg)
    res["rest"] = _node("rest", cfg, work / "cfg_rest.json", logs / "node_rest.log")
    finals = {}
    for r in ("R1", "R2"):
        f = res["rest"].get("files", {}).get(r)
        if not f:
            ck(f"{r} final export exists", False)
            continue
        exp = json.loads(Path(f).read_text())
        v = T.verify_export(exp, {revs[r]["package_sha256"]: revs[r], revs[r + ":2"]["package_sha256"]: revs[r + ":2"]})
        ck(f"{r} final export re-verifies in Python", v["ok"], v.get("error"))
        ck(f"{r} every stage locked", all(s["locked"] for s in exp["stages"].values()) and
           set(exp["stages"]) == {"Q0", "QH", "PROBE", "F"})
        ck(f"{r} final export extends the anchored Q0 stage export",
           T.extends(json.loads(Path(anchors[r]["file"]).read_text()), exp))
        finals[r] = exp
        shutil.copy(f, out / "exports" / f"{r}_final.json")

    # audit side: adjudication (blind) + F-A (non-blind), only from fully locked finals
    if len(finals) == 2:
        adj = T.adjudication_package(finals, assignee="ADJ1", protocol=proto, simulated=True, salt=SIM.SIM_SALT)
        hits = T.blind_scan(adj, forbidden_ids=forbidden)
        ck("adjudication package passes the blind scan", not hits, hits[:3])
        fa = T.auditor_package(finals, audits, resources, assignee="AUD1", protocol=proto, simulated=True)
        ck("auditor package is non-blind by design (carries conditions)", any("condition" in a for a in fa["audit"].values()))
        try:
            T.auditor_package({"R1": finals["R1"], "R2": json.loads(Path(anchors["R2"]["file"]).read_text())}, audits,
                              resources, assignee="AUD1", protocol=proto, simulated=True)
            ck("F-A cannot be built before every reviewer stage is locked", False)
        except ValueError as e:
            ck("F-A cannot be built before every reviewer stage is locked", True, str(e)[:120])
        (work / "ADJ1.html").write_text(T.render_html(adj), encoding="utf-8")
        (work / "AUD1.html").write_text(T.render_html(fa), encoding="utf-8")
        cfg = dict(base, out=str(work / "res_audit.json"), audit=[
            dict(id="ADJ1", stage="ADJ", html=str(work / "ADJ1.html"), n_items=len(adj["stages"][0]["items"]),
                 profile=str(work / "prof_adj"), downloads=str(work / "dl_adj")),
            dict(id="AUD1", stage="FA", html=str(work / "AUD1.html"), n_items=len(fa["stages"][0]["items"]),
                 profile=str(work / "prof_aud"), downloads=str(work / "dl_aud"))])
        res["audit"] = _node("audit", cfg, work / "cfg_audit.json", logs / "node_audit.log")
        for k, pk in (("ADJ1", adj), ("AUD1", fa)):
            f = res["audit"].get("files", {}).get(k)
            if f:
                v = T.verify_export(json.loads(Path(f).read_text()), {pk["package_sha256"]: pk})
                ck(f"{k} final export re-verifies in Python", v["ok"], v.get("error"))
                shutil.copy(f, out / "exports" / f"{k}_final.json")
            else:
                ck(f"{k} final export exists", False)
        ck("planted F5 disagreement reaches adjudication", len(adj["stages"][0]["items"]) >= 1,
           len(adj["stages"][0]["items"]))

    # tamper tests on the real exported logs
    tamper = tamper_suite(T, finals, anchors, revs) if len(finals) == 2 else []
    # blinding: captured page text of every blind page
    pages = [p for ph in ("q0", "rest", "audit") for p in res.get(ph, {}).get("pages", [])
             if not p["label"].startswith("AUD1")]
    page_hits = T.page_text_scan([p["text"] for p in pages], forbidden_ids=forbidden)
    ck("visible text of every blind page has no condition/label/score vocabulary or identifier", not page_hits,
       page_hits[:5])
    cur_pages = [p["text"] for p in res.get("curator", {}).get("pages", [])]
    cur_hits = [h for h in T.page_text_scan(cur_pages, forbidden_ids=forbidden)
                if h["match"] not in (r"\bS1\b", r"\bS2\b", r"\bS0\b")]
    ck("curator pages show no condition vocabulary or identifier (need-label options are the curator's own form)",
       not cur_hits, cur_hits[:5])
    jdump(out / "PAGE_TEXT_SAMPLES.json", [dict(label=p["label"], chars=len(p["text"]), head=p["text"][:600])
                                           for ph in res.values() for p in ph.get("pages", [])])
    metrics = T.procedure_metrics(finals, audits, EST_MIN) if len(finals) == 2 else None
    node_checks = [dict(c, by=f"browser:{ph}") for ph, r in res.items() for c in r.get("checks", [])]
    node_errors = {ph: r.get("errors") for ph, r in res.items() if r.get("errors")}
    allc = node_checks + checks + tamper
    report = dict(
        kind="PP1 review tool end-to-end acceptance with SIMULATED data (headless Chrome + Python re-verification)",
        simulated=True, chrome=subprocess.run([CHROME, "--version"], capture_output=True, text=True).stdout.strip(),
        node=subprocess.run([NODE, "--version"], capture_output=True, text=True).stdout.strip(),
        totals=dict(checks=len(allc), passed=sum(c["ok"] for c in allc), failed=sum(not c["ok"] for c in allc),
                    browser=len(node_checks), python=len(checks), tamper=len(tamper)),
        node_errors=node_errors, checks=allc, position_balance=balance, procedure_metrics_sim=metrics,
        packages=dict(curator=cur_pkg["package_sha256"], **{k: v["package_sha256"] for k, v in revs.items()}),
        work_dir=str(work),
        note="Times in procedure_metrics_sim are robot times (seconds), not human estimates; they only prove the "
             "timing pipeline works.  The F-A page is non-blind by design and is excluded from the blind-page scan.")
    jdump(out / "E2E_REPORT.json", report)
    manifest("pp1_e2e", {}, sorted(p for p in out.rglob("*") if p.is_file() and p.name != "MANIFEST.json"),
             TOOL_CODE + [REVIEW / "pp1_sim.py", PROJECT / "scripts/rl1v3/V321A_pp1_e2e.mjs"])
    print(json.dumps(report["totals"]), json.dumps(node_errors)[:400])
    failed = [c for c in allc if not c["ok"]]
    for c in failed:
        print("FAILED:", c["by"], c["name"], str(c.get("detail"))[:200])
    if failed or node_errors:
        raise SystemExit(1)


def tamper_suite(T, finals, anchors, revs) -> list[dict]:
    import copy
    out = []
    exp = finals["R1"]
    issued = {revs["R1"]["package_sha256"]: revs["R1"], revs["R1:2"]["package_sha256"]: revs["R1:2"]}

    def case(name, mutate, expect_ok=False, check=None):
        e = copy.deepcopy(exp)
        mutate(e)
        v = T.verify_export(e, issued)
        ok = (v["ok"] == expect_ok) if check is None else check(e, v)
        out.append(dict(name="tamper: " + name, ok=ok, detail=v.get("error"), by="python-tamper"))

    def first(e, kind, prefix=None):
        return next(i for i, x in enumerate(e["events"]) if x["kind"] == kind and (prefix is None or
                                                                                  (x["item"] or "").startswith(prefix)))

    def edit_answer(e):
        i = first(e, "submit", "QH:")
        e["events"][i]["data"]["answer"]["overall"] = "B" if e["events"][i]["data"]["answer"]["overall"] != "B" else "A"
    case("an edited locked answer breaks the hash chain", edit_answer)

    def drop(e):
        del e["events"][first(e, "submit", "F:")]
    case("a deleted event breaks the chain", drop)

    def reorder(e):
        i = first(e, "submit", "Q0:")
        e["events"][i], e["events"][i + 1] = e["events"][i + 1], e["events"][i]
    case("reordered events break the chain", reorder)

    def rehash_after_edit(e):
        i = first(e, "submit", "Q0:")
        e["events"][i]["data"]["answer"]["overall"] = "unsure"
        e["events"][i]["data"]["answer"].pop("strength", None)
        prev = e["events"][i]["prev"]
        for ev in e["events"][i:]:
            ev["prev"] = prev
            ev["h"] = T.event_hash(prev, ev)
            prev = ev["h"]
        e["head"] = prev
    case("a fully re-hashed rewrite verifies alone but no longer extends the coordinator's Q0 anchor",
         rehash_after_edit, check=lambda e, v: v["ok"] is False or
         not T.extends(json.loads(Path(anchors["R1"]["file"]).read_text()), e))

    def edit_after_lock(e):
        # append a well-formed draft on an item that was already submitted (re-hashed so only the rule can catch it)
        key = e["events"][first(e, "submit", "F:")]["item"]
        prev = e["events"][-1]["h"]
        ev = dict(seq=e["events"][-1]["seq"] + 1, t=e["events"][-1]["t"], kind="draft", item=key,
                  data=dict(answer={}), prev=prev)
        ev["h"] = T.event_hash(prev, ev)
        e["events"].append(ev)
        e["head"] = ev["h"]
    case("a well-formed edit of a locked item is refused by the replay rules", edit_after_lock)

    def foreign_pkg(e):
        e["packages"][0] = dict(e["packages"][0], title="edited")
    case("an edited package fails its own hash", foreign_pkg)

    def skip_stage(e):
        # submit QH before Q0 is locked: re-hash a log whose Q0 stage_lock is removed
        i = first(e, "stage_lock")
        del e["events"][i]
        prev = e["events"][i - 1]["h"]
        for k, ev in enumerate(e["events"][i:], start=i):
            ev["seq"] = k
            ev["prev"] = prev
            ev["h"] = T.event_hash(prev, ev)
            prev = ev["h"]
        e["head"] = prev
    case("removing the Q0 lock makes every later step illegal (stage order)", skip_stage)

    def unissued(e):
        p = copy.deepcopy(e["packages"][0])
        p["notes_zh"] = p["notes_zh"] + ["x"]
        e["packages"][0] = T.seal(p)
    case("a re-sealed package the coordinator never issued is rejected", unissued)

    leak = copy.deepcopy(revs["R1"])
    rid = next(iter(leak["replies"]))
    leak["replies"][rid]["condition"] = "RET-MS"
    hits = T.blind_scan(leak)
    out.append(dict(name="tamper: a condition field injected into a reviewer package is caught by the blind scan",
                    ok=bool(hits), detail=hits[:2], by="python-tamper"))
    return out


# ------------------------------------------------------------------ shared data helpers
def _frame_and_raw():
    from metacom_pm.rl1v3.asof import e1_receipt as E
    import V321_wsb_pr18_receipt as S
    import V32_wsb_rq1_qual as Q1
    raw = E.Raw(json.loads(S.ARTIFACT.read_text()))
    frame = Q1.natural_frame()
    census = {c["prefix_id"]: c for c in map(json.loads, S.CENSUS.read_text().splitlines())}
    return raw, frame, census


def _asof_words(raw, owner, cutoff, ts=None):
    return sum(len(t["text"].split()) for s in raw.legal_past(owner, cutoff, ts) for t in s["turns"])


def _power_inputs(raw, frame):
    import V321_wsb_admission as A
    group_of = A._groups()
    groups = {}
    for o, g in group_of.items():
        groups.setdefault(g, []).append(o)
    draw = json.loads((V3 / "V32_WSB_RQ1Q/coverage/SCREENING_DRAW.json").read_text())
    pop = {(x["owner_id"], x["stratum"]): x["population"] for x in draw["strata"]}
    owners = sorted(group_of)
    cue_pop = {o: pop[(o, "cue")] for o in owners}
    other_pop = {o: pop[(o, "other")] for o in owners}
    cue_words = sorted(_asof_words(raw, r["owner_id"], r["cutoff_rank"]) for r in frame
                       if r["flags"].get("explicit_reference_cue") and r["cutoff_rank"] >= 1)
    full = sorted(sum(len(t["text"].split()) for s in raw.by_owner[o] for t in s["turns"]) for o in owners)
    return dict(owner_groups=groups, cue_pop=cue_pop, other_pop=other_pop,
                words_item=cue_words[len(cue_words) // 2], words_owner_full=full[len(full) // 2])


def _facts():
    g = json.loads((V321 / "gates/GATES_V321.json").read_text())
    f = dict(g["facts"])
    import V321_wsb_admission as A
    prs = {str(n): A.gh_state(n) for n in (10, 15, 16, 17, 18, 19, 20)}
    f.update(g0e_identity=prs["10"]["state"] == "MERGED", instrument=(OUT / "pp1_e2e/E2E_REPORT.json").exists() and
             json.loads((OUT / "pp1_e2e/E2E_REPORT.json").read_text())["totals"]["failed"] == 0,
             requests_checked=prs["19"]["head"].startswith("4ac9ab3d"), executor_accepted=False,
             renderer_accepted=False, sealed_storage=False, family_frozen=False, dp_rule=False)
    return f, prs


def step_protocol(_):
    from metacom_pm.rl1v3.evaluate import protocol_v321a as P
    raw, frame, _ = _frame_and_raw()
    facts, prs = _facts()
    proto = P.build(_power_inputs(raw, frame))
    gates = P.gates_v321a(facts)
    out = OUT / "protocol"
    jdump(out / "PROTOCOL_V321A_CANDIDATE.json", proto)
    jdump(out / "DIFF_VS_V321.json", dict(base=P.BASE, rows=P.DIFF))
    jdump(OUT / "gates/GATES_V321A.json", dict(protocol=P.PROTOCOL, protocol_sha256=proto["protocol_sha256"],
                                               status=P.STATUS, prs=prs, facts=facts, gates=gates))
    manifest("protocol", {"v321_gates": V321 / "gates/GATES_V321.json"},
             [out / "PROTOCOL_V321A_CANDIDATE.json", out / "DIFF_VS_V321.json", OUT / "gates/GATES_V321A.json"],
             [PROJECT / "src/metacom_pm/rl1v3/evaluate/protocol_v321a.py"])
    print(proto["protocol_sha256"], [(g["gate"], g["state"]) for g in gates])


def step_fcms(_):
    from metacom_pm.rl1v3.evaluate import protocol_v321a as P
    proto = json.loads((OUT / "protocol/PROTOCOL_V321A_CANDIDATE.json").read_text())
    raw, frame, _ = _frame_and_raw()
    pin = _power_inputs(raw, frame)
    out = OUT / "fcms"
    grid = proto["power"]["grid"]
    plans = proto["power"]["plans"]
    check = dict(mde_17_2_icc01=round(P.mde(17, 2, icc=0.1), 3), mde_17_4_icc01=round(P.mde(17, 4, icc=0.1), 3),
                 mde_12_4=round(P.mde(12, 4, icc=0.1), 3), mde_8_4=round(P.mde(8, 4, icc=0.1), 3),
                 floor_17=dict((str(i), round(P.mde_floor(17, icc=i), 3)) for i in (0.05, 0.1, 0.2)),
                 floor_34_01=round(P.mde_floor(34, icc=0.1), 3), floor_51_01=round(P.mde_floor(51, icc=0.1), 3),
                 ni_010_reachable=[dict(icc=i, m=V321_ni(i)) for i in (0.0, 0.02, 0.05)])
    jdump(out / "FCMS_POWER_BUDGET.json", dict(protocol_sha256=proto["protocol_sha256"], questions=proto["questions"],
                                               analysis=proto["analysis"], answers=proto["answers"], grid=grid,
                                               plans=plans, key_numbers=check, scenarios=P.SCENARIOS, est=P.EST,
                                               inputs=dict(words_item_median=pin["words_item"],
                                                           words_owner_full_median=pin["words_owner_full"],
                                                           groups=len(pin["owner_groups"]))))
    manifest("fcms", {"protocol": OUT / "protocol/PROTOCOL_V321A_CANDIDATE.json"}, [out / "FCMS_POWER_BUDGET.json"],
             [PROJECT / "src/metacom_pm/rl1v3/evaluate/protocol_v321a.py"])
    print(json.dumps(check))
    for p in plans:
        for sn, sc in p["scenarios"].items():
            print(p["label"], sn, sc["k_s1"], sc["m_s1"], sc["cost"]["generator_calls"], sc["cost"]["total_hours"],
                  sc["primary_mde"], sc["downgraded"], sc["serious_upper_0_events_per_arm"])


def V321_ni(icc):
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    return V.required_per_group_for_margin(0.10, groups=17, decisive=0.5, icc=icc)


def step_screenpack(_):
    from metacom_pm.rl1v3.review import pp1_tool as T
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    raw, frame, census = _frame_and_raw()
    fr = {r["prefix_id"]: r for r in frame}
    scr = json.loads((V321 / "screen/INITIAL_SCREEN_90.json").read_text())
    import V321_wsb_admission as A
    group_of = A._groups()
    cases, rows = [], []
    for r in scr["rows"]:
        f = fr[r["prefix_id"]]
        c = census.get(r["prefix_id"])
        ts = c["timestamp"] if c else None
        sess = raw.sessions[(f["owner_id"], f["session_id"])]
        legal = raw.legal_past(f["owner_id"], f["cutoff_rank"], ts) if f["cutoff_rank"] >= 1 else []
        words = sum(len(t["text"].split()) for s in legal for t in s["turns"])
        cases.append(dict(case_key=r["prefix_id"], owner_key=f["owner_id"], order_key=(f["cutoff_rank"], f["cut_turn"]),
                          prefix=sess["turns"][:f["cut_turn"] + 1], history=[dict(date=s["date"], turns=s["turns"])
                                                                             for s in legal]))
        rows.append(dict(prefix_id=r["prefix_id"], owner_id=f["owner_id"], group=group_of[f["owner_id"]],
                         cutoff_rank=f["cutoff_rank"], cut_turn=f["cut_turn"], asof_words=words,
                         inclusion_probability=r["inclusion_probability"], stratum_hidden_from_curator=r["stratum"]))
    proto = json.loads((OUT / "protocol/PROTOCOL_V321A_CANDIDATE.json").read_text())
    pref = dict(id=proto["protocol"], sha256=proto["protocol_sha256"])
    # default: two curators, owner groups split by reading load (an owner's items never span two curators)
    load = {}
    for r in rows:
        load[r["group"]] = max(load.get(r["group"], 0), r["asof_words"])
    split = {"CUR1": [], "CUR2": []}
    for g in sorted(load, key=lambda g: -load[g]):
        tgt = min(split, key=lambda k: sum(load[x] for x in split[k]))
        split[tgt].append(g)
    reg = dict(kind="FC-MS formal screening execution package (90 items, frozen draw)", protocol=pref,
               screen_sha256=scr["screen_sha256"], items=len(rows), owners=len({r["owner_id"] for r in rows}),
               blinding=["样本层（cue/other/S7）对整理者隐藏", "看不到任何回复、检索排名或 DP 材料",
                         "同一 owner 按 (cutoff, cut) 升序，as-of：不会先看到更晚的会话"],
               assignment=dict(default="2 名整理者，按 owner 组整组分配（同组不拆）；整理者不担任这些前缀在 FC-MS 中的审阅者",
                               split={k: sorted(v) for k, v in split.items()},
                               words_by_curator={k: sum(load[g] for g in v) for k, v in split.items()}),
               packages={}, expansion=dict(rule=V.EXPANSION_RULE, deterministic="resource_effect_v321.expansion_next()",
                                           order="每次只按标签计数决定下一条；新增条目进入新的整理者包（同一 owner 同一整理者）"),
               dp_selection=proto["dp_selection"], sealed_ledger=dict(
                   format="整理者阶段文件（S 锁定）→ 协调人核验 → 标签写入审计 ledger（prefix_id, need, risk, spans, "
                          "submitted_at, curator, export head）；ledger 只在审计侧", never_shown_to=["审阅者", "Generator"]),
               cost=dict(per_item_full_read_hours=round(sum(r["asof_words"] / 250 + 3 for r in rows) / 60, 1),
                         owner_incremental_hours=round((sum(load.values()) / 250 + 4 * len(rows)) / 60, 1),
                         note="上界 = 每条都通读其 as-of 历史；下界 = 同一 owner 只增量通读一次（按时间顺序），每条再加 4 分钟"))
    PRIVATE.mkdir(parents=True, exist_ok=True)
    for cur, gs in split.items():
        cs = [c for c, r in zip(cases, rows) if r["group"] in gs]
        pkg, amap = T.curator_package(cs, assignee=cur, protocol=pref, simulated=False, salt="fcms-screen-order-v1")
        hits = T.blind_scan(pkg, forbidden_ids=[c["case_key"] for c in cs], role="curator")
        (PRIVATE / f"SCREEN90_{cur}.html").write_text(T.render_html(pkg, title="正式筛查 " + cur), encoding="utf-8")
        jdump(PRIVATE / f"SCREEN90_{cur}.package.json", pkg, pretty=False)
        jdump(PRIVATE / f"SCREEN90_{cur}.audit_map.json", amap)
        reg["packages"][cur] = dict(package_sha256=pkg["package_sha256"], items=len(cs), blind_scan_hits=len(hits),
                                    html_sha256=file_sha256(PRIVATE / f"SCREEN90_{cur}.html"),
                                    bytes=(PRIVATE / f"SCREEN90_{cur}.package.json").stat().st_size)
    out = OUT / "screen90"
    jdump(out / "SCREEN90_EXECUTION_REGISTRY.json", reg)
    jdump(out / "SCREEN90_ITEMS.json", rows)
    manifest("screen90", {"screen": V321 / "screen/INITIAL_SCREEN_90.json"},
             [out / "SCREEN90_EXECUTION_REGISTRY.json", out / "SCREEN90_ITEMS.json"], TOOL_CODE)
    print(json.dumps(dict(items=len(rows), split=reg["assignment"]["words_by_curator"], cost=reg["cost"],
                          packages={k: (v["items"], v["blind_scan_hits"], v["bytes"]) for k, v in reg["packages"].items()})))


def step_renderer(_):
    from metacom_pm.rl1v3.asof import e1_receipt as E
    from metacom_pm.rl1v3.asof import renderer_acceptance as RA
    import V321_wsb_pr18_receipt as S
    raw = E.Raw(json.loads(S.ARTIFACT.read_text()))
    census = {c["prefix_id"]: c for c in map(json.loads, S.CENSUS.read_text().splitlines())}
    g0e = json.loads(subprocess.run(["git", "show", f"{S.G0E_REF}:{S.G0E_PATH}"], cwd=REPO, capture_output=True,
                                    text=True, check=True).stdout)
    req = subprocess.run(["git", "show", f"{S.PP1_SHA}:{S.PP1_REQ}"], cwd=REPO, capture_output=True, text=True,
                         check=True).stdout
    rows = [json.loads(x) for x in req.splitlines() if x.strip()]
    prefixes = {}
    for r in rows:
        c = census[r["prefix_id"]]
        sess = raw.sessions[(c["owner_id"], c["session_id"])]
        prefixes[r["prefix_id"]] = dict(c, turns=sess["turns"][:c["cut_turn"] + 1])
    off = {r["prefix_id"]: r["model_input"]["messages"] for r in rows if r["condition"] == "OFF"}
    dry = RA.check_family(rows, prefixes, raw, g0e, g0e_off=off, old_renderer_id=None)
    cen = RA.entity_census(raw)
    out = OUT / "renderer"
    jdump(out / "RENDERER_ACCEPTANCE_PLAN.json", dict(plan=RA.PLAN, entity_census=cen,
                                                       dry_run_on_pr19=dict(head=S.PP1_SHA, **{k: v for k, v in dry.items()}),
                                                       candidate_status="WS-A 尚未提交统一 renderer 候选（#10/#18/#19 HEAD 与共享目录均无）"))
    manifest("renderer", {}, [out / "RENDERER_ACCEPTANCE_PLAN.json"],
             [PROJECT / "src/metacom_pm/rl1v3/asof/renderer_acceptance.py"])
    print(json.dumps(dict(census=cen, verdict=dry["verdict"], family=dry["family"])))


LICENSE_EVIDENCE = dict(
    checked_on="2026-11-19", method="GitHub API (gh api) for repository metadata, LICENSE and README; Zenodo record page "
                                   "read once via a web fetch (the API refused automated access); local artifact counts",
    sources=[
        dict(id="L1", source="ESConv（thu-coai/Emotional-Support-Conversation）", what="仓库 LICENSE 文件",
             evidence="Creative Commons Attribution-NonCommercial 4.0 International（CC BY-NC 4.0）全文",
             url="https://github.com/thu-coai/Emotional-Support-Conversation/blob/main/LICENSE"),
        dict(id="L2", source="ESConv", what="README 首行",
             evidence="“Copyright © 2021 CoAI Group, Tsinghua University. All rights reserved. Data and codes are for "
                      "academic research use only.”",
             url="https://github.com/thu-coai/Emotional-Support-Conversation"),
        dict(id="L3", source="ESConv（Hugging Face thu-coai/esconv）", what="数据卡 license 字段",
             evidence="cc-by-nc-4.0（只在 refs/pr/2 分支看到，主分支未核实）",
             url="https://huggingface.co/datasets/thu-coai/esconv"),
        dict(id="L4", source="ES-MemEval / EvoEmo（slptongji/ES-MemEval）", what="GitHub 仓库许可",
             evidence="仓库没有 LICENSE 文件，GitHub license 字段为 null；README 写明 EvoEmo 数据在 data/evo_emo.json",
             url="https://github.com/slptongji/ES-MemEval"),
        dict(id="L5", source="ES-MemEval v1.0.0（Zenodo 10.5281/zenodo.18338564）", what="Zenodo 记录",
             evidence="资源类型 Software；许可 CC BY 4.0；2026-01-22 发布；1 个 zip（798 kB）；记录中没有数据来源、使用条款或"
                      "伦理说明", url="https://zenodo.org/records/18338564"),
        dict(id="L6", source="ES-MemEval 论文（arXiv 2602.01885）", what="论文许可",
             evidence="论文文本标注 CC BY 4.0；这只覆盖论文，不一定覆盖数据", url="https://arxiv.org/abs/2602.01885"),
        dict(id="L7", source="本项目 sanitized artifact（ES-MemEval-Public-v1.0.0-1427）", what="来源构成（本地计数）",
             evidence="401 个会话中 85 个来自 ESConv（session id escNNN），316 个为 EvoEmo 生成会话", url=None),
        dict(id="L8", source="WS-A 来源登记（#18）", what="license 字段",
             evidence="ESConv_academic_research_only（8）；inherited_research_scope; upstream_EvoEmo_license_unresolved（261）",
             url=None),
        dict(id="L9", source="本仓库 chensiyu7812/Metacom5_3", what="可见性（gh api）",
             evidence="public。仓库中已有 data/external/ESConv.json（9.0 MB）、data/external/evo_emo.json（4.5 MB）、"
                      "sanitized artifact，以及 #20 提交的 8 份 QH 背景（RAW 派生）", url=None),
    ],
    uses=[
        dict(use="内部研究（团队内、非商业学术研究）", status="有证据支持（前提待确认）",
             basis=["L1/L2：ESConv 允许非商业学术研究使用，须署名", "L5：EvoEmo 发布记录为 CC BY 4.0；其中 ESConv 派生部分仍受 L1 约束"],
             conditions=["研究者确认本项目属于非商业学术研究", "署名 ESConv 与 ES-MemEval", "Tokkio 等商业部署用途不在此证据范围内"]),
        dict(use="人工审阅共享（把含 RAW 的任务包交给整理者、审阅者、裁决者）", status="可行，但须附条件并由研究者确认",
             basis=["L1：BY-NC 允许以非商业目的分享，须附署名与许可链接", "L2：仅限学术研究"],
             conditions=["任务包内附来源署名与许可说明", "参与者书面承诺只用于本研究、不转发、结束后删除",
                         "支付评审劳务是否影响“非商业”判断，需研究者或机构确认",
                         "内容涉及情绪困扰：给参与者事先说明与退出权；遵守所在机构的伦理与数据管理要求"]),
        dict(use="公开再分发（公开仓库、公开任务包、论文附录长段原文）", status="未确立",
             basis=["L1 允许非商业再分发，但 L2 写有“All rights reserved … academic research use only”",
                    "L4：数据仓库无 LICENSE；L5 的 CC BY 4.0 属于“软件”记录，是否覆盖数据文件未写明",
                    "CC BY 4.0 不能为 ESConv 派生部分（L7 的 85 个会话）去掉 NC 限制",
                    "EvoEmo 生成会话所用生成模型的条款未知"],
             conditions=["不要只凭“数据公开”推断可以公开再分发", "现状（L9）需要研究者决定：仓库转私有，或移除原始数据只保留哈希与获取脚本",
                         "本轮新生成的 PP1/筛查任务包已放在仓库外，只提交哈希"]),
    ],
    disclaimer="这是证据整理，不是法律意见；最终由研究者（必要时咨询机构）决定",
)


def step_license(_):
    out = OUT / "license"
    jdump(out / "LICENSE_EVIDENCE.json", LICENSE_EVIDENCE)
    manifest("license", {}, [out / "LICENSE_EVIDENCE.json"], [])
    print(len(LICENSE_EVIDENCE["sources"]), [u["status"] for u in LICENSE_EVIDENCE["uses"]])


def step_admission(_):
    g = json.loads((OUT / "gates/GATES_V321A.json").read_text())
    e2e = json.loads((OUT / "pp1_e2e/E2E_REPORT.json").read_text())
    rows = []
    for gate in g["gates"]:
        for it in gate["items"]:
            rows.append(dict(gate=gate["gate"], id=it["id"], state=it["state"], evidence=it["evidence"],
                             reason=it.get("reason"), owner=it.get("unblock_owner")))
    summ = dict(protocol_sha256=g["protocol_sha256"], prs=g["prs"], gates={x["gate"]: x["state"] for x in g["gates"]},
                counts={s: sum(r["state"] == s for r in rows) for s in ("PASS", "PENDING", "BLOCKED")},
                e2e=e2e["totals"], rows=rows)
    jdump(OUT / "admission/ADMISSION_TABLE.json", summ)
    manifest("admission", {"gates": OUT / "gates/GATES_V321A.json", "e2e": OUT / "pp1_e2e/E2E_REPORT.json"},
             [OUT / "admission/ADMISSION_TABLE.json"], [])
    print(json.dumps(dict(gates=summ["gates"], counts=summ["counts"])))


STEPS = dict(tool=step_tool, e2e=step_e2e, protocol=step_protocol, fcms=step_fcms, screenpack=step_screenpack,
             renderer=step_renderer, license=step_license, admission=step_admission)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=sorted(STEPS))
    a = ap.parse_args()
    STEPS[a.step](a)


if __name__ == "__main__":
    main()
