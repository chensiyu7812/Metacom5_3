#!/usr/bin/env python3
"""WS-B round 13 (V3.2.1-A decisions, #21 E6, screening preparation, data governance).  CPU only.

Steps (outputs under outputs/pm_rl1/v3/V321A_WSB_R13/<step>/):
  e6          collect the fault-injection harness result (V321A_e6_harness.py) into the E6 receipt
  rdiff       old vs new renderer: token and presentation differences per request (#21 previews)
  inventory   RAW-bearing files on every remote branch (fingerprints; no RAW text written), PRs, artifacts
  dpcheck     B's independent check of A's DP selection pools (#21 DP_SELECTOR_BUNDLE_8)
  screenprep  rebuild PP1-curator and screen-90 packages with form S-v2 (--codes to substitute real curator codes)
  replan      demo of the post-screening re-plan on SIMULATED labels (real run: --labels)
  decision    researcher decision receipt candidate
  admission   gate table after this round
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1].parent
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts/rl1v3"))

import V321A_wsb as W  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, file_sha256, object_sha256  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OUT = V3 / "V321A_WSB_R13"
PR21 = W.PR21_SHA
PR21_DIR = W.PR21_DIR
E6_DIR = Path(os.environ.get("E6_DIR", "/opt/tokkio-data0/tokkio_runs/wsb_v321a/e6/final"))
PRIVATE = W.PRIVATE / "r13"


def jdump(p: Path, obj):
    return W.jdump(p, obj)


def manifest(step, inputs, outputs, code):
    man = build_manifest(task=f"V321A_r13_{step}", root=PROJECT, inputs={k: Path(v) for k, v in inputs.items()},
                         code=[Path(__file__)] + code, code_sha=W.head_sha(), outputs=outputs)
    jdump(OUT / step / "MANIFEST.json", man)


# ------------------------------------------------------------------ e6
DEFECTS = [
    dict(id="E6-D1", severity="high", scenario="E5_parent_SIGTERM",
         finding="SIGTERM to the supervisor ends it without STOP/SUMMARY; the worker runs in its own session, survives as "
                 "an orphan and finishes the in-flight call (12 s in the harness; a real generate or a model load would "
                 "keep the GPU busy until it ends). The parent-side watchdog timers die with the parent.",
         fix="convert SIGTERM/SIGHUP into an exception in the supervisor (so drive() journals STOP and close() kills the "
             "group); in the worker add PR_SET_PDEATHSIG=SIGKILL (preexec) and a watchdog thread that exits when "
             "getppid() != the admitted supervisor pid; pass a per-operation absolute deadline to the worker and enforce "
             "it there too"),
    dict(id="E6-D2", severity="medium", scenario="E6_parent_SIGKILL",
         finding="same as D1 for SIGKILL (cannot be caught): orphan worker completes the in-flight call",
         fix="worker-side PR_SET_PDEATHSIG + parent-pid watchdog + worker-side deadline (as D1)"),
    dict(id="E6-D3", severity="high", scenario="F1_reapproval_after_unresolved_start",
         finding="the no-retry claim is keyed by the approval hash; a second approval for the SAME plan (any text "
                 "change) re-runs every request although a REQUEST_START without result exists (4-call plan -> 6 "
                 "physical calls in the harness)",
         fix="key the claim by plan_sha256 (one execution per plan); or refuse when any journal of this plan has an "
             "unresolved START unless the new approval names that journal and a new plan covers only never-started "
             "request ids; never re-run validated or unresolved calls under the same plan"),
    dict(id="E6-D4", severity="low", scenario="E3_worker_exit_leaves_child",
         finding="when the worker process itself dies, close() skips killpg, so children left in its process group "
                 "survive (the real HF worker is not expected to spawn processes)",
         fix="close(): always killpg(worker pgid, SIGKILL) and reap, ignoring ProcessLookupError"),
]
OBSERVATIONS = [
    "日志语义：START = REQUEST_START（发送前 fsync 落盘，已由假 worker 在收到请求时核对）；RESULT = REQUEST_RETURNED（原样）"
    "+ REQUEST_VALIDATED；FAILED 没有逐请求事件，由 STOP（含 reason 与 pending）表示。建议增加 failed_request_id 字段。"
    "监督进程被杀时没有 STOP：读取方必须把“有 START、无 RESULT”视为未决（E6-D1/D3 的修复后由执行器强制）",
    "write_once 是 O_EXCL + fsync(文件和目录)，不是临时文件 + rename；写一半崩溃会留下不完整文件，代码有意保留作为未决证据，"
    "读取方需容忍最后一条不可解析",
    "executor_review_evidence 只检查非空；应绑定 B 的 E6 回执（URL、回执 sha、覆盖的执行器 HEAD）",
    "模型与 tokenizer：baseline 的文件列表包含 tokenizer.json、tokenizer_config.json、chat_template.jinja，加载前逐字节哈希"
    "（本 harness 用替代小文件验证了“哈希不符即 STOP、不加载”）；24 GB 实际哈希约 170 s 计入 1,200 s 总预算",
    "真实 worker 的“只加载一次”“原生 tokenizer 与请求 ids 相等”只做了代码审查（假 worker 替代了它），需在 A0 实测时由日志证明",
    "未跟踪文件不在干净检查范围内（--untracked-files=no）；PYTHONPATH 下的未跟踪 sitecustomize.py 会在 worker 启动时被导入（低）",
]


def step_e6(_):
    res = json.loads((E6_DIR / "E6_HARNESS_RESULT.json").read_text())
    d = OUT / "e6_receipt"
    jdump(d / "E6_HARNESS_RESULT.json", res)
    if (E6_DIR.parent / "final.log").exists():
        shutil.copy(E6_DIR.parent / "final.log", d / "harness_run.log")
    failed = {c["name"].split(":")[0] for c in res["checks"] if not c["ok"]}
    expected = {"E3", "E5_parent_SIGTERM", "E6_parent_SIGKILL", "F1"}
    verdict = dict(
        object=dict(pr=21, head=W.PR21_SHA, code_head="575011b43947f4aaf73d6bb31f376bf4c36405fc"),
        method="B 自写故障注入 harness（V321A_e6_harness.py）；A 的执行器只作为被测对象；不使用 A 的测试或验收函数作为 oracle；"
               "假 worker、假 nvidia-smi、临时 DATA；不加载模型、不访问 GPU",
        totals=res["totals"], failed_checks=sorted(c["name"] for c in res["checks"] if not c["ok"]),
        failed_match_expected_defects=failed <= expected | {f.split(":")[0] for f in failed},
        verdict="NOT_SIGNED" if res["totals"]["failed"] else "SIGNED",
        defects=DEFECTS, observations=OBSERVATIONS,
        consequence="E6 未签收：按研究者要求，A0 与 PP1 都不能批准；修复后 B 用同一 harness 在新的固定 HEAD 上复跑",
        retest="python scripts/rl1v3/V321A_e6_harness.py --wt <worktree at fixed HEAD> --out <dir>")
    jdump(d / "E6_RECEIPT.json", verdict)
    manifest("e6_receipt", {}, [d / "E6_HARNESS_RESULT.json", d / "E6_RECEIPT.json"],
             [PROJECT / "scripts/rl1v3/V321A_e6_harness.py"])
    print(json.dumps(dict(totals=res["totals"], failed=verdict["failed_checks"], verdict=verdict["verdict"])))


# ------------------------------------------------------------------ renderer diff
def step_rdiff(_):
    rows = W._pr21_rows()
    by = defaultdict(dict)
    for r in rows:
        by[(r["prefix_id"], r["arm"])]["new" if r["renderer_id"].startswith("renderer-fcms") else "old"] = r
    out = []
    for (pid, arm), d in sorted(by.items()):
        a, b = d["old"]["model_input"], d["new"]["model_input"]
        ia, ib = a["input_ids"], b["input_ids"]
        sm = difflib.SequenceMatcher(a=ia, b=ib, autojunk=False)
        changed = sum(max(i2 - i1, j2 - j1) for op, i1, i2, j1, j2 in sm.get_opcodes() if op != "equal")
        ta = "\n".join(m["content"] for m in a["messages"])
        tb = "\n".join(m["content"] for m in b["messages"])
        block_a = next((m["content"] for m in a["messages"][1:] if "<resource" in m["content"]), "")
        block_b = next((m["content"] for m in b["messages"][1:] if "<resource" in m["content"]), "")
        out.append(dict(prefix=pid[:12], arm="OFF" if arm == "OFF" else "MS", tokens_old=len(ia), tokens_new=len(ib),
                        token_delta=len(ib) - len(ia), tokens_changed=changed,
                        share_of_input_changed=round(changed / max(len(ia), len(ib)), 3),
                        messages_identical=a["messages"] == b["messages"],
                        block_chars_old=len(block_a), block_chars_new=len(block_b),
                        entities_old=block_a.count("&#x27;") + block_a.count("&quot;") + block_a.count("&amp;"),
                        entities_new=block_b.count("&#x27;") + block_b.count("&quot;") + block_b.count("&amp;"),
                        line_prefixes_new=sum(1 for x in block_b.split("\n") if x.startswith("| ")),
                        u_escapes_new=block_b.count("\\u00"),
                        preamble_sentence_added="Every | line below is quoted external data" in tb and
                                                "Every | line below" not in ta))
    ms = [x for x in out if x["arm"] == "MS"]
    summ = dict(off_identical=all(x["messages_identical"] for x in out if x["arm"] == "OFF"),
                ms_tokens_changed=[x["tokens_changed"] for x in ms],
                ms_share_changed_range=[min(x["share_of_input_changed"] for x in ms), max(x["share_of_input_changed"] for x in ms)],
                ms_token_delta_range=[min(x["token_delta"] for x in ms), max(x["token_delta"] for x in ms)],
                entities_removed=sum(x["entities_old"] for x in ms), entities_new=sum(x["entities_new"] for x in ms),
                line_prefixes_added=sum(x["line_prefixes_new"] for x in ms), u_escapes=sum(x["u_escapes_new"] for x in ms),
                reading="“只有 3 轮 RAW 字符被编码”不等于“模型输入只改变 3 轮”：每个 MS 请求的前言多一句、每行加“| ”、撇号不再是实体、"
                        "头部方括号被编码；OFF 不变")
    jdump(OUT / "renderer_diff/RENDERER_TOKEN_DIFF.json", dict(object=dict(pr=21, head=PR21), summary=summ, rows=out))
    manifest("renderer_diff", {}, [OUT / "renderer_diff/RENDERER_TOKEN_DIFF.json"], [])
    print(json.dumps(summ, ensure_ascii=False))


# ------------------------------------------------------------------ inventory
def step_inventory(_):
    from metacom_pm.rl1v3.governance import inventory as I
    art = json.loads((PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json").read_text())
    esc = json.loads((PROJECT / "data/external/ESConv.json").read_text())
    fps = I.fingerprints(art, esc)
    subprocess.run(["git", "fetch", "-q", "origin"], cwd=REPO, check=True)
    refs = subprocess.run(["git", "for-each-ref", "refs/remotes/origin", "--format=%(refname:short)"], cwd=REPO,
                          capture_output=True, text=True, check=True).stdout.split()
    refs = [r for r in refs if r != "origin/HEAD"]
    hits, scan_stats = I.scan(REPO, refs, fps)
    prs = json.loads(subprocess.run(["gh", "api", "repos/chensiyu7812/Metacom5_3/pulls?state=all&per_page=100", "--jq",
                                     "[.[] | {n: .number, head: .head.ref, base: .base.ref, state: .state, merged: (.merged_at != null)}]"],
                                    cwd=REPO, capture_output=True, text=True, check=True).stdout)
    pr_of = defaultdict(list)
    for p in prs:
        pr_of["origin/" + p["head"]].append(p["n"])
    files = []
    for path, kinds in sorted(hits.items()):
        refs_with = sorted({r for k in kinds.values() for r in k})
        size = None
        for r in refs_with:
            s = subprocess.run(["git", "cat-file", "-s", f"{r}:{path}"], cwd=REPO, capture_output=True, text=True)
            if s.returncode == 0:
                size = int(s.stdout)
                break
        files.append(dict(path=path, category=I.classify(path), bytes=size,
                          fingerprints={k: max(v.values()) for k, v in kinds.items()},
                          branches=len(refs_with), on_public_main_or_integration=[r for r in refs_with if r in
                                                                                  ("origin/main", "origin/pmrl1-v3/integration")],
                          prs=sorted({n for r in refs_with for n in pr_of.get(r, [])}), **I.git_history(REPO, path)))
    arts = json.loads(subprocess.run(["gh", "api", "repos/chensiyu7812/Metacom5_3/actions/artifacts?per_page=100", "--jq",
                                      "{total: .total_count, names: ([.artifacts[] | .name] | unique), "
                                      "expired: ([.artifacts[] | select(.expired)] | length)}"],
                                     cwd=REPO, capture_output=True, text=True).stdout or "{}")
    rel = subprocess.run(["gh", "api", "repos/chensiyu7812/Metacom5_3/releases", "--jq", "length"], cwd=REPO,
                         capture_output=True, text=True).stdout.strip()
    by_cat = defaultdict(lambda: dict(files=0, bytes=0))
    for f in files:
        by_cat[f["category"]]["files"] += 1
        by_cat[f["category"]]["bytes"] += f["bytes"] or 0
    out = dict(method="指纹：从 sanitized artifact 与 ESConv.json 中按 sha 排序确定性抽取 ≥50 字符的纯 ASCII 句子"
                      "（EvoEmo 生成会话 400、ESConv 派生会话 150、只在 ESConv 中的 300；另加 html 转义变体），"
                      "对每个远端分支的全部 blob 去重后逐一读取，按 8 词片段匹配（已把 &#x27; 还原为撇号）；某文件命中 ≥3 个不同指纹即记为含 RAW。"
                      "输出只含路径、计数与提交信息，不含任何原文",
               fingerprints=dict(total=len(fps), sha256=object_sha256(sorted(I._sha(x)[:16] for x in fps))),
               branches_scanned=len(refs), scan_stats=scan_stats, repo_visibility="public",
               files=files, by_category=dict(by_cat), actions_artifacts=arts, releases=rel,
               notes=["GitHub 为每个 PR 保留 refs/pull/N/head；分支删除后这些提交仍可通过 PR 访问",
                      "任何人都可以下载公开分支的源码压缩包；已存在的 fork 与克隆无法收回",
                      "CI 上传的 artifacts 只有测试结果文件（名称见 actions_artifacts），本清单未下载其内容"])
    jdump(OUT / "governance/RAW_INVENTORY.json", out)
    manifest("governance", {}, [OUT / "governance/RAW_INVENTORY.json"],
             [PROJECT / "src/metacom_pm/rl1v3/governance/inventory.py"])
    print(json.dumps(dict(files=len(files), by_category=dict(by_cat), branches=len(refs), artifacts=arts, releases=rel),
                     ensure_ascii=False))


# ------------------------------------------------------------------ dpcheck
DP_FORBIDDEN = ("rank", "score", "retriev", "lexical", "bm25", "dense", "result", "reply", "output", "judge", "RET")


def step_dpcheck(_):
    from metacom_pm.rl1v3.asof import e1_receipt as E
    import V321_wsb_pr18_receipt as S
    raw = E.Raw(json.loads(S.ARTIFACT.read_text()))
    census = {c["prefix_id"]: c for c in map(json.loads, S.CENSUS.read_text().splitlines())}
    bundle = json.loads(W._git_show(PR21, f"{PR21_DIR}/DP_SELECTOR_BUNDLE_8.json"))
    keys = set()

    def walk(o, path=""):
        if isinstance(o, dict):
            for k, v in o.items():
                keys.add(k)
                walk(v, path + "." + k)
        elif isinstance(o, list):
            for v in o:
                walk(v, path)
    walk(bundle)
    chrono = ("session_rank", "cutoff_rank", "source_rank", "chronological_rank")   # time order, not retrieval rank
    leaked = sorted(k for k in keys if any(f.lower() in k.lower() for f in DP_FORBIDDEN) and k not in chrono)
    rows = []
    for row in bundle["rows"]:
        pool = row["pool"]
        c = census[pool["prefix_id"]]
        legal = raw.legal_past(c["owner_id"], c["cutoff_rank"], c["timestamp"])
        legal_ids = [s["session_id"] for s in legal]
        cand = pool["candidates"]
        def raw_lines(sid):
            return [f"{t['role']}: {t['text']}" for t in raw.sessions[(c["owner_id"], sid)]["turns"] if t["text"]]
        texts_ok = sum(x["text"].split("\n") == raw_lines(x["session_id"]) for x in cand)
        rows.append(dict(prefix=pool["prefix_id"][:12], owner=c["owner_id"], cutoff_rank=c["cutoff_rank"],
                         candidates=len(cand), legal_sessions=len(legal),
                         same_session_set=sorted(x["session_id"] for x in cand) == sorted(legal_ids),
                         all_strictly_past=all(x["reported_at"]["session_rank"] < c["cutoff_rank"] for x in cand),
                         chronological=[x["reported_at"]["session_rank"] for x in cand] ==
                                       sorted(x["reported_at"]["session_rank"] for x in cand),
                         candidates_equal_raw_session=texts_ok))
    out = dict(object=dict(pr=21, head=PR21, file=f"{PR21_DIR}/DP_SELECTOR_BUNDLE_8.json",
                           bundle_sha256=bundle.get("bundle_sha256")),
               forbidden_key_hits=leaked, rows=rows,
               all_pools_equal_legal_sessions=all(r["same_session_set"] for r in rows),
               all_candidate_texts_equal_raw=all(r["candidates_equal_raw_session"] == r["candidates"] for r in rows),
               candidates_total=sum(r["candidates"] for r in rows),
               a_receipt_fields=["selector", "current_need", "rationale", "declared_at", "outcomes_not_seen", "decision",
                                 "selected_record_id", "source_sha256", "source_session_id", "receipt_sha256"],
               missing_vs_researcher=["结构化的“单会话覆盖”字段（full/partial/none）", "时效问题标记", "阶段问题标记",
                                      "选择者 ≠ 该前缀 Q0/QH/F 审阅者的强制检查（需在协调侧角色登记中执行）",
                                      "选择冻结时间早于任何生成 START 的绑定（需写入 FC-MS 计划并由执行器核对）"])
    jdump(OUT / "dp_alignment/DP_POOL_CHECK.json", out)
    manifest("dp_alignment", {}, [OUT / "dp_alignment/DP_POOL_CHECK.json"], [])
    print(json.dumps({k: v for k, v in out.items() if k not in ("rows",)}, ensure_ascii=False)[:900])


# ------------------------------------------------------------------ screenprep
def step_screenprep(a):
    from metacom_pm.rl1v3.review import pp1_tool as T
    codes = (a.codes or "CUR1,CUR2").split(",")
    pp1_code = a.pp1_code or "CURP"
    placeholder = not a.codes
    proto = json.loads((V3 / "V321A_WSB/protocol/PROTOCOL_V321A_CANDIDATE.json").read_text())
    pref = dict(id=proto["protocol"], sha256=proto["protocol_sha256"])
    PRIVATE.mkdir(parents=True, exist_ok=True)
    reg = dict(kind="real distribution packages (form S-v2); contents kept off the public repository",
               form_version=T.FORMS["S"]["version"], placeholder_codes=placeholder, protocol=pref, packages={},
               distribution_rule="研究者确认受限共享条件并指定人员之前，不向任何外部人员发送；代码与真实身份的对照只由研究者保管")
    cases = W.pp1_cases()
    pkg, amap = T.curator_package(cases, assignee=pp1_code, protocol=pref, simulated=False, salt="pp1-curator-order-v1")
    _write_pkg(T, pkg, amap, f"PP1_CURATOR_{pp1_code}", "PP1 生成前筛查", reg, [c["case_key"] for c in cases])
    raw, frame, census = W._frame_and_raw()
    fr = {r["prefix_id"]: r for r in frame}
    scr = json.loads((V3 / "V321_WSB/screen/INITIAL_SCREEN_90.json").read_text())
    split = json.loads((V3 / "V321A_WSB/screen90/SCREEN90_EXECUTION_REGISTRY.json").read_text())["assignment"]["split"]
    import V321_wsb_admission as A
    group_of = A._groups()
    for slot, code in zip(("CUR1", "CUR2"), codes):
        cs = []
        for r in scr["rows"]:
            f = fr[r["prefix_id"]]
            if group_of[f["owner_id"]] not in split[slot]:
                continue
            c = census.get(r["prefix_id"])
            sess = raw.sessions[(f["owner_id"], f["session_id"])]
            legal = raw.legal_past(f["owner_id"], f["cutoff_rank"], c["timestamp"] if c else None) if f["cutoff_rank"] >= 1 else []
            cs.append(dict(case_key=r["prefix_id"], owner_key=f["owner_id"], order_key=(f["cutoff_rank"], f["cut_turn"]),
                           prefix=sess["turns"][:f["cut_turn"] + 1],
                           history=[dict(date=s["date"], turns=s["turns"]) for s in legal]))
        pkg, amap = T.curator_package(cs, assignee=code, protocol=pref, simulated=False, salt="fcms-screen-order-v1")
        _write_pkg(T, pkg, amap, f"SCREEN90_{code}", "正式筛查 " + code, reg, [c["case_key"] for c in cs], slot=slot)
    jdump(OUT / "screen_prep/DISTRIBUTION_REGISTRY.json", reg)
    manifest("screen_prep", {}, [OUT / "screen_prep/DISTRIBUTION_REGISTRY.json"],
             [PROJECT / "src/metacom_pm/rl1v3/review/pp1_tool.py"])
    print(json.dumps({k: (v["items"], v["package_sha256"][:12], v["blind_scan_hits"]) for k, v in reg["packages"].items()}))


def _write_pkg(T, pkg, amap, name, title, reg, ids, slot=None):
    hits = T.blind_scan(pkg, forbidden_ids=ids, role="curator")
    html = PRIVATE / f"{name}.html"
    html.write_text(T.render_html(pkg, title=title), encoding="utf-8")
    jdump(PRIVATE / f"{name}.package.json", pkg)
    jdump(PRIVATE / f"{name}.audit_map.json", amap)
    reg["packages"][name] = dict(slot=slot, assignee=pkg["assignee"], items=len(pkg["stages"][0]["items"]),
                                 package_sha256=pkg["package_sha256"], html_sha256=file_sha256(html),
                                 blind_scan_hits=len(hits), private_path=str(html))


# ------------------------------------------------------------------ replan
def step_replan(a):
    from metacom_pm.rl1v3.evaluate import fcms_replan as R
    import V321_wsb_admission as A
    group_of = A._groups()
    items = json.loads((V3 / "V321A_WSB/screen90/SCREEN90_ITEMS.json").read_text())
    words = {r["prefix_id"]: r["asof_words"] for r in items}
    if a.labels:
        labels = json.loads(Path(a.labels).read_text())
        simulated = False
    else:
        # SIMULATED labels for a dry run only: a fixed hash decides the label, nothing else.
        labels, simulated = [], True
        for r in items:
            h = int(hashlib.sha256(("sim-label|" + r["prefix_id"]).encode()).hexdigest()[:8], 16) % 100
            need = "S7" if r["stratum_hidden_from_curator"] == "S7_rank0" else (
                "S1" if (r["stratum_hidden_from_curator"] == "cue" and h < 35) or h < 8 else
                "S2" if h < 55 else "S0" if h < 90 else "unclear")
            labels.append(dict(prefix_id=r["prefix_id"], owner_id=r["owner_id"], group=group_of[r["owner_id"]], need=need))
    res = {p: R.replan(labels, plan=p, words=words) for p in ("conservative", "medium", "extended")}
    jdump(OUT / "replan/REPLAN_DEMO.json" if simulated else OUT / "replan/REPLAN_REAL.json",
          dict(simulated=simulated, note="模拟标签，只演示流程；正式数值必须由真实 S 标签重算" if simulated else "真实标签",
               plans=res))
    print(json.dumps({p: dict(k=r["k_s1"], s1=r["s1_prefixes"], calls=r["generator_calls"], hours=r["review_hours"],
                              mode=r["primary_mode"]) for p, r in res.items()}, ensure_ascii=False))


# ------------------------------------------------------------------ decision receipt
def step_decision(_):
    proto = json.loads((V3 / "V321A_WSB/protocol/PROTOCOL_V321A_CANDIDATE.json").read_text())
    pr21 = json.loads((V3 / "V321A_WSB/pr21_renderer_receipt/RENDERER_RECEIPT_PR21.json").read_text())
    e6 = json.loads((OUT / "e6_receipt/E6_RECEIPT.json").read_text())
    body = dict(
        kind="researcher decision receipt CANDIDATE (WS-B record of the researcher's round-13 message; needs the "
             "researcher's explicit sign-off to become final)",
        status="CANDIDATE_PENDING_RESEARCHER_SIGNATURE",
        based_on=dict(protocol=proto["protocol"], protocol_sha256=proto["protocol_sha256"], pr=22, pr22_head="e46d978d"),
        adopted_in_principle=[
            dict(item="A1–A15 总体结构", reason="版本 A：资源获取由 PM Step-1 负责，Step-2 no-plan，G 隐式使用资源", scope="FC-MS-1 及后续同族比较"),
            dict(item="QH 为长期支持主指标；Q0 即时质量保护；F 事实与安全约束；三者不合成总分", reason="与研究目标一致；未提及记忆不算错误", scope="全部 FC 族"),
            dict(item="唯一主比较：S1 中 DP-MS 对 OFF 的 QH", reason="先回答资源潜在价值；单一主检验避免结果驱动换指标", scope="FC-MS-1"),
            dict(item="次要机制比较：RET−OFF、DP−RET（主检验 superior 后 Holm）", reason="区分检索质量与资源价值", scope="FC-MS-1"),
            dict(item="不采用 −0.10 非劣界", reason="17 组下 ICC ≥ 0.05 不可达；不显著只写 inconclusive", scope="FC-MS-1"),
            dict(item="PP1 只作程序试点，不并入 FC-MS", reason="旧 renderer 与新 renderer 不同；PP1 只测程序", scope="PP1"),
            dict(item="Step-2 维持 G0e no-plan；新 applicability prompt 不进入当前实验族", reason="单因素；版本化另评", scope="当前实验族"),
        ],
        selected=[
            dict(item="FC-MS renderer = #21 renderer-fcms:e675b435（line-quote-1）",
                 sha=pr21["renderer_id_recomputed"], status="候选通过，待正式 DP 样本复验",
                 caveats=["只有 3 轮 RAW 字符被编码，但每个 MS 请求约 15–20% 的 token 改变（见 renderer_diff）",
                          "行为层面的注入防护与情感支持效应未实测", "PP1 旧 renderer 的回复不得并入新 renderer 的 FC-MS"]),
            dict(item="主要 DP-MS = A 的人工选材（#21 DP 选材工具）", sha=PR21,
                 status="待补齐：单会话覆盖、时效、阶段字段；选择者≠审阅者；选择时间早于生成（见 dp_alignment）"),
            dict(item="B 的确定性规则 = Rule-DP 次要诊断基线（暂不增加模型调用）", status="只计算选材，不生成"),
            dict(item="预算暂定中等方案", status="在 90 条真实 S 标签产生后、任何 FC-MS 生成结果出现前最终冻结（fcms_replan）"),
        ],
        not_changed_by_this_receipt=dict(
            license="许可与公开仓库处理仍待研究者决定（governance/）", staff="整理者、审阅者、裁决者尚未指定",
            gpu="A0、PP1、FC-MS 生成均未授权", e6=f"E6 {e6['verdict']}（见 e6_receipt）",
            g0e_identity="研究者拟固定 #10 73fdb12f 为研究级 G0e 身份；正式冻结签收待办（不等于 merge，也不授予运行许可）"),
        frozen_evidence_untouched=["P2 v1 2b6057c8", "#17 b28cf37b", "V3.2.1 d2fde5db", "V3.2.1-A 27df254f（本回执不修改）"])
    body["receipt_sha256"] = object_sha256(body)
    jdump(OUT / "decision/RESEARCHER_DECISION_RECEIPT_CANDIDATE.json", body)
    manifest("decision", {}, [OUT / "decision/RESEARCHER_DECISION_RECEIPT_CANDIDATE.json"], [])
    print(body["receipt_sha256"])


# ------------------------------------------------------------------ admission
def step_admission(_):
    from metacom_pm.rl1v3.evaluate import protocol_v321a as P
    facts, prs = W._facts()
    gates = P.gates_v321a(facts)
    e6 = json.loads((OUT / "e6_receipt/E6_RECEIPT.json").read_text())
    for g in gates:
        for it in g["items"]:
            if it["id"] == "E6":
                it["reason"] = f"B 的 E6 回执：{e6['verdict']}（{e6['totals']['passed']}/{e6['totals']['checks']}；" \
                               f"高 2、中 1、低 1 项缺陷待 A 修复后复跑）"
            if it["id"] == "C7":
                it["reason"] = "候选通过，待正式 DP 样本复验；研究者倾向采纳"
            if it["id"] == "E1":
                it["reason"] = "研究者拟固定 #10 73fdb12f 为研究级 G0e 身份；正式冻结签收待办（不等于 merge）"
            if it["id"] in ("C1", "C9", "P5"):
                it["reason"] = "研究者原则同意版本 A；研究决定回执候选待签署（decision/）"
            if it["id"] == "C6":
                it["reason"] = "研究者倾向统一使用 #21 line-quote-1；待签署并在正式 DP 样本上复验"
            if it["id"] == "C10":
                it["reason"] = "研究者倾向：A 人工选材为主、Rule-DP 为次要基线；A 工具需补齐覆盖/时效/阶段字段与角色约束"
    rows = [dict(gate=g["gate"], id=i["id"], state=i["state"], reason=i.get("reason"), owner=i.get("unblock_owner"))
            for g in gates for i in g["items"]]
    out = dict(prs=prs, gates={g["gate"]: g["state"] for g in gates},
               counts={s: sum(r["state"] == s for r in rows) for s in ("PASS", "PENDING", "BLOCKED")}, rows=rows)
    jdump(OUT / "admission/ADMISSION_TABLE_R13.json", out)
    print(json.dumps(dict(gates=out["gates"], counts=out["counts"]), ensure_ascii=False))


STEPS = dict(e6=step_e6, rdiff=step_rdiff, inventory=step_inventory, dpcheck=step_dpcheck, screenprep=step_screenprep,
             replan=step_replan, decision=step_decision, admission=step_admission)

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=sorted(STEPS))
    ap.add_argument("--codes", help="real curator codes for the two screen-90 slots, e.g. R13C1,R13C2")
    ap.add_argument("--pp1-code")
    ap.add_argument("--labels", help="frozen label ledger JSON for the real re-plan")
    a = ap.parse_args()
    STEPS[a.step](a)
