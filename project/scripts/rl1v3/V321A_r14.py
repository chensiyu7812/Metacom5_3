#!/usr/bin/env python3
"""WS-B round 14: final decision signing candidate, executable human-screening kit, receiving and reporting.
CPU only; never produces S labels (labels come only from human curators).

Steps (committed outputs under outputs/pm_rl1/v3/V321A_WSB_R14/; RAW-bearing packages and sealed labels stay in the
private directory off the public repository):
  kit       final packages (PP1 8, CUR1 40, CUR2 50, pre-fixed 15% overlap), pre-fixed DP-overlap order, practice
            packages (simulated), staff registry templates          [--codes C1,C2 --pp1-code P to substitute codes]
  receive   verify one returned curator export against the issued registry; write a receipt; seal its labels
  report    aggregate verified receipts: counts, groups with S1, multi-session S1, unclear, time, overlap agreement
  decision  researcher decision -- final signing candidate (versioned separately; nothing frozen is modified)
  gates     gate table for this round
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts/rl1v3"))

import V321A_wsb as W  # noqa: E402
import V321A_r13 as R13  # noqa: E402
from metacom_pm.rl1v3.io import file_sha256, object_sha256  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OUT = V3 / "V321A_WSB_R14"
PRIV = Path(__import__("os").environ.get("R14_PRIV", str(W.PRIVATE / "r14")))
OVERLAP_SALT = "pmrl1v3-v321a-screen-overlap-v1"
DP_OVERLAP_SALT = "pmrl1v3-v321a-dp-overlap-v1"
OVERLAP_SHARE = 0.15


def jdump(p, o):
    return W.jdump(Path(p), o)


def overlap_items(items: list[dict], slot: str) -> list[str]:
    from metacom_pm.rl1v3.review import screen_report as SR
    return SR.prefixed_overlap(items, slot, salt=OVERLAP_SALT, share=OVERLAP_SHARE)


def dp_overlap_order(items: list[dict]) -> list[str]:
    from metacom_pm.rl1v3.review import screen_report as SR
    return SR.fixed_order([r["prefix_id"] for r in items], salt=DP_OVERLAP_SALT)


def _screen_items():
    items = json.loads((V3 / "V321A_WSB/screen90/SCREEN90_ITEMS.json").read_text())
    split = json.loads((V3 / "V321A_WSB/screen90/SCREEN90_EXECUTION_REGISTRY.json").read_text())["assignment"]["split"]
    slot_of = {g: s for s, gs in split.items() for g in gs}
    for r in items:
        r["slot"] = slot_of[r["group"]]
    return items


def _cases(pids, raw, frame, census):
    fr = {r["prefix_id"]: r for r in frame}
    out = []
    for pid in pids:
        f = fr[pid]
        c = census.get(pid)
        sess = raw.sessions[(f["owner_id"], f["session_id"])]
        legal = raw.legal_past(f["owner_id"], f["cutoff_rank"], c["timestamp"] if c else None) if f["cutoff_rank"] >= 1 else []
        out.append(dict(case_key=pid, owner_key=f["owner_id"], order_key=(f["cutoff_rank"], f["cut_turn"]),
                        prefix=sess["turns"][:f["cut_turn"] + 1],
                        history=[dict(date=s["date"], turns=s["turns"]) for s in legal]))
    return out


# ------------------------------------------------------------------ kit
def step_kit(a):
    from metacom_pm.rl1v3.review import pp1_sim as SIM
    from metacom_pm.rl1v3.review import pp1_tool as T
    codes = (a.codes or "CUR1,CUR2").split(",")
    pp1_code = a.pp1_code or "CURP"
    placeholder = not a.codes
    code_of = dict(CUR1=codes[0], CUR2=codes[1])
    proto = json.loads((V3 / "V321A_WSB/protocol/PROTOCOL_V321A_CANDIDATE.json").read_text())
    pref = dict(id=proto["protocol"], sha256=proto["protocol_sha256"])
    PRIV.mkdir(parents=True, exist_ok=True)
    R13.PRIVATE = PRIV                                    # write packages into this round's private directory
    reg = dict(kind="final human-screening kit (form S-v2); RAW-bearing packages stay off the public repository",
               form_version=T.FORMS["S"]["version"], placeholder_codes=placeholder, protocol=pref,
               distribution_rule="研究者确定人员并确认受限研究共享范围之后，才把占位代码换成真实匿名代码并分发",
               labels_rule="正式 S1/S2/S0 标签只能由人工整理者给出；任何模型不得生成或预填标签",
               packages={}, private_dir=str(PRIV))
    # PP1: 8 prefixes
    cases = W.pp1_cases()
    pkg, amap = T.curator_package(cases, assignee=pp1_code, protocol=pref, simulated=False, salt="pp1-curator-order-v1")
    R13._write_pkg(T, pkg, amap, f"PP1_CURATOR_{pp1_code}", "PP1 生成前筛查", reg, [c["case_key"] for c in cases])
    reg["packages"][f"PP1_CURATOR_{pp1_code}"].update(kind="PP1", slot="PP1")
    # formal 90 (40/50) + pre-fixed 15% overlap packages
    raw, frame, census = W._frame_and_raw()
    items = _screen_items()
    ovl = {s: overlap_items(items, s) for s in ("CUR1", "CUR2")}
    for slot in ("CUR1", "CUR2"):
        pids = [r["prefix_id"] for r in items if r["slot"] == slot]
        pkg, amap = T.curator_package(_cases(pids, raw, frame, census), assignee=code_of[slot], protocol=pref,
                                      simulated=False, salt="fcms-screen-order-v1")
        name = f"SCREEN90_{code_of[slot]}"
        R13._write_pkg(T, pkg, amap, name, "正式筛查 " + code_of[slot], reg, pids, slot=slot)
        reg["packages"][name].update(kind="primary")
        other = "CUR2" if slot == "CUR1" else "CUR1"
        oc = _cases(ovl[other], raw, frame, census)
        pkg, amap = T.curator_package(oc, assignee=code_of[slot] + "-OVL", protocol=pref, simulated=False,
                                      salt="fcms-screen-overlap-order-v1")
        name = f"SCREEN90_OVERLAP_{code_of[slot]}"
        R13._write_pkg(T, pkg, amap, name, "正式筛查（独立重叠） " + code_of[slot], reg, ovl[other], slot=slot)
        reg["packages"][name].update(kind="overlap", covers_slot=other)
    reg["overlap"] = dict(salt_sha256=hashlib.sha256(OVERLAP_SALT.encode()).hexdigest(), share=OVERLAP_SHARE,
                          rule="每名整理者的有历史条目中，按登记的 salt 哈希顺序取前 15%（向上取整），交给另一名整理者独立盲标；"
                               "不看主要标签；结果只用于报告一致性与分歧，不改写主要标签",
                          items={s: v for s, v in ovl.items()}, n={s: len(v) for s, v in ovl.items()},
                          order_sha256=object_sha256(ovl))
    dpo = dp_overlap_order(items)
    reg["dp_overlap"] = dict(salt_sha256=hashlib.sha256(DP_OVERLAP_SALT.encode()).hexdigest(), share=OVERLAP_SHARE,
                             order_sha256=object_sha256(dpo),
                             rule="顺序现在固定：S 标签冻结后，取该顺序中前 15%（向上取整）的 S1/S2 前缀做双人独立 DP 选材；"
                                  "第二人的选择不改变已冻结的主要选择")
    jdump(PRIV / "DP_OVERLAP_ORDER.json", dpo)
    # practice packages (SIMULATED; no RAW) -- committed for training
    prac = OUT / "kit/practice"
    prac.mkdir(parents=True, exist_ok=True)
    cpkg, _ = T.curator_package(SIM.cases()[:3] + [SIM.rank0_case()], assignee="T-CUR", protocol=SIM.SIM_PROTOCOL,
                                simulated=True, salt=SIM.SIM_SALT)
    (prac / "PRACTICE_CURATOR.html").write_text(T.render_html(cpkg, title="练习：生成前筛查（模拟）"), encoding="utf-8")
    reps, pairs, _ = SIM.replies(SIM.cases()[:2])
    p1, mk, _au = T.reviewer_packages(SIM.cases()[:2], reps, pairs, assignee="T-REV", protocol=SIM.SIM_PROTOCOL,
                                      simulated=True, salt=SIM.SIM_SALT)
    (prac / "PRACTICE_REVIEWER_PART1.html").write_text(T.render_html(p1, title="练习：评审第一部分（模拟）"), encoding="utf-8")
    reg["practice"] = {f.name: file_sha256(f) for f in sorted(prac.glob("*.html"))}
    jdump(OUT / "kit/KIT_REGISTRY.json", reg)
    jdump(PRIV / "KIT_REGISTRY.json", reg)
    print(json.dumps({k: (v["items"], v["package_sha256"][:12], v["blind_scan_hits"]) for k, v in reg["packages"].items()}),
          json.dumps(reg["overlap"]["n"]))


# ------------------------------------------------------------------ receive / report
def _issued():
    reg = json.loads((PRIV / "KIT_REGISTRY.json").read_text())
    pk = {}
    for name, v in reg["packages"].items():
        p = PRIV / f"{name}.package.json"
        pk[v["package_sha256"]] = (name, json.loads(p.read_text()), json.loads((PRIV / f"{name}.audit_map.json").read_text()))
    return reg, pk


def step_receive(a):
    from metacom_pm.rl1v3.review import pp1_tool as T
    reg, pk = _issued()
    exp = json.loads(Path(a.export).read_text())
    base = exp.get("base_package_sha256")
    if base not in pk:
        raise SystemExit("REFUSED: export does not belong to any issued package")
    name, pkg, amap = pk[base]
    v = T.verify_export(exp, {pkg["package_sha256"]: pkg})
    if not v["ok"]:
        raise SystemExit(f"REFUSED: {v['error']}")
    locked = all(s["locked"] for s in exp["stages"].values())
    rec = dict(package=name, package_sha256=base, assignee=exp["assignee"], head=exp["head"], n_events=len(exp["events"]),
               export_sha256=hashlib.sha256(Path(a.export).read_bytes()).hexdigest(), stage_locked=locked,
               stages=exp["stages"], kind=exp.get("kind"))
    d = PRIV / "received"
    d.mkdir(parents=True, exist_ok=True)
    jdump(d / f"{name}_{exp['head'][:8]}.receipt.json", rec)
    (d / f"{name}_{exp['head'][:8]}.export.json").write_bytes(Path(a.export).read_bytes())
    print(json.dumps(dict(package=name, head=exp["head"][:16], locked=locked,
                          submitted=sum(s["submitted"] for s in exp["stages"].values()))))


def step_report(_):
    from metacom_pm.rl1v3.review import screen_report as SR
    import V321_wsb_admission as A
    reg, pk = _issued()
    group_of = A._groups()
    latest = {}
    for rp in sorted((PRIV / "received").glob("*.receipt.json")):
        r = json.loads(rp.read_text())
        if r["stage_locked"]:
            latest[r["package"]] = rp.with_name(rp.name.replace(".receipt.json", ".export.json"))
    out = dict(received_locked=sorted(latest))
    by_kind = {"PP1": {}, "primary": {}, "overlap": {}}
    for name, p in latest.items():
        by_kind[reg["packages"][name]["kind"]][name] = p
    reports = {}
    for kind, d in by_kind.items():
        if not d:
            continue
        exps = {n: json.loads(p.read_text()) for n, p in d.items()}
        maps = {n: next(m for s, (nn, _pk, m) in pk.items() if nn == n) for n in d}
        issued = {s: v[1] for s, v in pk.items()}
        reports[kind] = SR.screen_report(exps, maps, group_of, issued)
    if "primary" in reports and "overlap" in reports:
        out["overlap_agreement"] = SR.overlap_agreement(reports["primary"]["rows"], reports["overlap"]["rows"])
    jdump(PRIV / "SCREEN_REPORT_FULL.json", dict(out, reports=reports))
    public = dict(out, reports={k: {kk: vv for kk, vv in r.items() if kk not in ("rows", "s1_per_group")}
                                for k, r in reports.items()},
                  note="只含汇总计数与耗时；逐条标签保存在仓库外的密封 ledger")
    if not __import__("os").environ.get("R14_NO_PUBLIC"):
        jdump(OUT / "screen_report/SCREEN_REPORT_SUMMARY.json", public)
    print(json.dumps({k: (r["counts"], r["groups_with_s1"], r["time"]) for k, r in reports.items()}, ensure_ascii=False))


# ------------------------------------------------------------------ decision (final signing candidate)
def step_decision(_):
    proto = json.loads((V3 / "V321A_WSB/protocol/PROTOCOL_V321A_CANDIDATE.json").read_text())
    r13 = json.loads((V3 / "V321A_WSB_R13/decision/RESEARCHER_DECISION_RECEIPT_CANDIDATE.json").read_text())
    e23 = json.loads((V3 / "V321A_WSB_R13/e6_receipt/E6_RECEIPT_PR23.json").read_text())
    body = dict(
        id="pmrl1v3-v321a-researcher-decision-2", status="FINAL_CANDIDATE_FOR_RESEARCHER_SIGNATURE",
        supersedes_candidate=dict(id="R13 candidate", receipt_sha256=r13["receipt_sha256"]),
        protocol=dict(id=proto["protocol"], sha256=proto["protocol_sha256"], modified=False),
        research=[
            "PM Step-1 负责资源获取（GET_MS/MP/ME/RS 与 STOP）",
            "Step-2 继续 no-plan（pmrl1v3-g0e-no-plan-1）",
            "Generator 隐式判断是否使用、是否提及资源；未提及历史不算错误",
            "QH 为主要长期支持指标；Q0 为即时质量保护；F 为事实与安全约束；三者不合成总分",
            "FC-MS-1 唯一主比较：S1 中 DP-MS vs OFF（QH）",
            "次要机制比较：RET-MS vs OFF、DP-MS vs RET-MS（主检验 superior 后 Holm）",
            "暂不采用 −0.10 非劣界；不显著只写 inconclusive",
            "人工 DP-MS 为主要诊断条件；Rule-DP 只作辅助诊断，不生成",
            "FC-MS 采用 line-quote-1 renderer（renderer-fcms:e675b435…），正式 DP 请求产生后复验",
            "PP1 使用旧 renderer（renderer:e04b6de4…），结果不并入 FC-MS",
            "预算暂定中等方案；90 条真实 S 标签产生后、任何 FC-MS 生成结果出现前最终冻结",
        ],
        identities=dict(renderer_fcms="renderer-fcms:e675b43535843b6d0a9f0410d14294249572290c60325a11f8081678c61880dc",
                        renderer_pp1="renderer:e04b6de4d78624db4379c25537b9e6f8571b00b4c4edee681c7b5b3e31bb3d27",
                        executor=dict(pr=23, head=e23["object"]["head"], code=e23["object"]["code_head"],
                                      bindings=e23["object"]["executor_bindings"]),
                        plans=dict(A0="43f175c56d6a3e12078ed26744fd4c09f92ab67b7eb34b0a3e28d0ef40815cb2",
                                   PP1="bc51f93157648229f751b586be013af8d2ce42071dd95c03171f522f95d96380"),
                        g0e_research_identity=dict(source="#10", head="73fdb12f29b6970a268eeda704d73e1bd35b1c3e",
                                                   status="拟固定；随本回执签署即登记为研究级身份（不等于 merge）")),
        engineering=dict(E6=dict(status="SIGNED", scope="CPU 故障注入", object="#23 " + e23["object"]["head"],
                                 history="#21 46349ccf 不签收（43/47，4 项缺陷）已由 #23 修复；原记录保留"),
                         not_authorization="E6 签收与本回执都不是 A0、PP1 或任何 GPU 的运行授权"),
        data=dict(decided=["研究属于非商业学术用途", "GitHub 仓库继续公开", "论文与项目文档正确说明并引用数据来源",
                           "当前不发送许可确认邮件", "当前不执行仓库私有化、数据删除或 Git 历史改写"],
                  uncertainty=["EvoEmo 数据文件本身没有明确的许可声明（Zenodo 记录为软件 CC BY 4.0）",
                               "ESConv 为 CC BY-NC 4.0，README 写明仅限学术研究；EvoEmo 中 85 个会话来自 ESConv",
                               "未从作者获得新的明确许可；如出现明确的新限制再另行报告"],
                  annotator_sharing="任务包的受限研究共享范围待研究者确认（人员、承诺、用后删除）"),
        frozen_untouched=["P2 v1 2b6057c8", "#17 b28cf37b", "V3.2.1 d2fde5db", "V3.2.1-A 27df254f"])
    body["receipt_sha256"] = object_sha256(body)
    jdump(OUT / "decision/RESEARCHER_DECISION_V321A_FINAL_CANDIDATE.json", body)
    print(body["receipt_sha256"])


# ------------------------------------------------------------------ gates
def step_gates(_):
    from metacom_pm.rl1v3.evaluate import protocol_v321a as P
    facts, prs = W._facts()
    e23 = json.loads((V3 / "V321A_WSB_R13/e6_receipt/E6_RECEIPT_PR23.json").read_text())
    facts.update(executor_accepted=e23["verdict"] == "SIGNED", license_scope=True)
    gates = P.gates_v321a(facts)
    for g in gates:
        for it in g["items"]:
            if it["id"] == "E6":
                it["evidence"] = (f"SIGNED：#23 HEAD {e23['object']['head'][:8]}（A0 binding {e23['object']['executor_bindings']['A0'][:8]}、"
                                  f"PP1 binding {e23['object']['executor_bindings']['PP1'][:8]}）；CPU 故障注入 49/49 + 3.12 进程路径 20/20；"
                                  "#21 46349ccf 不签收的记录保留")
            if it["id"] == "M4":
                it["evidence"] = "研究者决定：非商业学术用途；仓库继续公开；文档引用来源；上游许可的不确定性照常登记（不是新许可）"
            if it["id"] == "E1":
                it["reason"] = "研究者拟固定 #10 73fdb12f；随研究决定回执签署登记"
            if it["id"] in ("C1", "C9", "P5"):
                it["reason"] = "研究决定最终签署候选待研究者签署（R14 decision/）"
            if it["id"] in ("C6", "C7"):
                it["reason"] = "line-quote-1 已选定；待签署并在正式 DP 请求上复验"
            if it["id"] == "C10":
                it["reason"] = "人工 DP-MS 为主；A 工具需补齐覆盖/时效/阶段字段、选择者≠审阅者、选择早于生成"
            if it["id"] in ("P3", "C2"):
                it["reason"] = "任务包已备（仓库外）；待研究者指定人员、确认受限共享范围并分配匿名代码"
    rows = [dict(gate=g["gate"], id=i["id"], state=i["state"], evidence=i.get("evidence"), reason=i.get("reason"),
                 owner=i.get("unblock_owner")) for g in gates for i in g["items"]]
    out = dict(prs=prs, gates={g["gate"]: g["state"] for g in gates},
               counts={s: sum(r["state"] == s for r in rows) for s in ("PASS", "PENDING", "BLOCKED")}, rows=rows)
    jdump(OUT / "gates/GATES_R14.json", out)
    print(json.dumps(dict(gates=out["gates"], counts=out["counts"]), ensure_ascii=False))


def step_selftest(_):
    """Receiving/reporting flow on SIMULATED material only (temp registry); never touches real packages or labels."""
    import copy
    import subprocess
    import tempfile
    from metacom_pm.rl1v3.review import pp1_sim as SIM
    from metacom_pm.rl1v3.review import pp1_tool as T
    global PRIV
    real_priv = PRIV
    tmp = Path(tempfile.mkdtemp(prefix="r14_selftest_"))
    PRIV = tmp
    try:
        pkg, amap = T.curator_package(SIM.cases() + [SIM.rank0_case()], assignee="CUR1", protocol=SIM.SIM_PROTOCOL,
                                      simulated=True, salt=SIM.SIM_SALT, translate=SIM.translate,
                                      translation_method="mock (test only)")
        jdump(tmp / "SIM.package.json", pkg)
        jdump(tmp / "SIM.audit_map.json", amap)
        jdump(tmp / "KIT_REGISTRY.json", dict(packages={"SIM": dict(package_sha256=pkg["package_sha256"], kind="primary",
                                                                     items=9)}))
        e2e = V3 / "V321A_WSB_R13/pp1_e2e/exports"
        good = e2e / "curator_final.json"
        checks = []

        def run(path):
            r = subprocess.run([sys.executable, __file__, "receive", "--export", str(path)], capture_output=True, text=True,
                               env=dict(__import__("os").environ, R14_PRIV=str(tmp)))
            return r.returncode, (r.stdout + r.stderr).strip().splitlines()[-1:]
        rc, msg = run(good)
        checks.append(dict(name="a verified, locked curator export is received", ok=rc == 0, detail=msg))
        bad = copy.deepcopy(json.loads(good.read_text()))
        i = next(k for k, e in enumerate(bad["events"]) if e["kind"] == "submit")
        bad["events"][i]["data"]["answer"]["need"] = "S0" if bad["events"][i]["data"]["answer"].get("need") != "S0" else "S2"
        jdump(tmp / "tampered.json", bad)
        rc, msg = run(tmp / "tampered.json")
        checks.append(dict(name="an edited export is refused", ok=rc != 0 and "REFUSED" in " ".join(msg), detail=msg))
        rc, msg = run(e2e / "R1_final.json")
        checks.append(dict(name="an export of a package that was not issued is refused", ok=rc != 0 and "REFUSED" in " ".join(msg),
                           detail=msg))
        r = subprocess.run([sys.executable, __file__, "report"], capture_output=True, text=True,
                           env=dict(__import__("os").environ, R14_PRIV=str(tmp), R14_NO_PUBLIC="1"))
        full = json.loads((tmp / "SCREEN_REPORT_FULL.json").read_text()) if (tmp / "SCREEN_REPORT_FULL.json").exists() else {}
        rep = full.get("reports", {}).get("primary", {})
        checks.append(dict(name="the report counts the received labels and time", ok=r.returncode == 0 and rep.get("items") == 9,
                           detail=dict(counts=rep.get("counts"), time=rep.get("time"))))
        out = dict(simulated=True, note="只用模拟材料验证收件与报告流程；不涉及任何真实任务包或标签", checks=checks,
                   passed=sum(c["ok"] for c in checks), total=len(checks))
        PRIV = real_priv
        jdump(OUT / "kit/RECEIVE_SELFTEST.json", out)
        print(json.dumps(dict(passed=out["passed"], total=out["total"])))
    finally:
        PRIV = real_priv


STEPS = dict(kit=step_kit, receive=step_receive, report=step_report, decision=step_decision, gates=step_gates,
             selftest=step_selftest)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=sorted(STEPS))
    ap.add_argument("--codes")
    ap.add_argument("--pp1-code")
    ap.add_argument("--export")
    a = ap.parse_args()
    STEPS[a.step](a)
