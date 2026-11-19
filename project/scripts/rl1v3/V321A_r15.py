#!/usr/bin/env python3
"""WS-B round 15: per-person HTML handover for human screening/review with Chinese-first display.

The verified S-v2 tool (PR #25 HEAD 490c73c1) is reused unchanged in its rules; this round only adds a display layer
(Chinese first, English original sentence by sentence, always expandable) and a translation hand-off:
ChatGPT (web, operated by a person) translates small text batches; this script checks every returned line against
the source and bakes the translation into the already-verified page.  No model is called here; no label is produced.

Steps
  packages   English source packages with the fixed codes (R1, R2, CUR1, CUR2); identity vs the R14 kit
  batches    translation batches (each source sentence once; stable source identity + SHA) for ChatGPT web
  zh         read returned *.zh.txt, check them, build the Chinese-first HTML for every fully translated package
  check      identity / blinding / translation checks of any final HTML (also one rewritten by hand or by ChatGPT)
  receive    accept one returned export (issued final packages only; cross-check independence order enforced)
  report     aggregate counts only (safe to show to R1)
  practice   simulated practice pages (R1/R2 part 1, CUR1/CUR2 screening) + a practice batch to dry-run ChatGPT
  part2      coordinator: practice part 2 for R1/R2 after their Q0 stage file
  handover   write the off-repo handover tree (per person) + SHA manifest; docs in the repo
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import shutil
import sys
from collections import defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[1].parent
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts/rl1v3"))

import V321A_wsb as W  # noqa: E402
import V321A_r14 as R14  # noqa: E402
from metacom_pm.rl1v3.io import file_sha256, object_sha256  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OUT = V3 / "V321A_WSB_R15"
PRIV = Path(os.environ.get("R15_PRIV", str(W.PRIVATE / "r15")))
HAND = Path(os.environ.get("R15_HANDOVER", str(W.PRIVATE.parent / "wsb-v321a-handover-r15")))
R14_PRIV = W.PRIVATE / "r14"
BATCH_WORDS = 3000
BASE_HEAD = "490c73c1bd0eed937edcc6f50001e6e7cce3c687"
TR_METHOD = "ChatGPT 网页版逐句翻译（人工操作）+ WS-B 逐行机检；英文原文为准"
LABEL_SALT = "pmrl1v3-r15-translation-labels-v1"

# The five curator packages, in the order the work (and therefore the translation) is needed.
#   name -> (person, R14 package it continues, assignee, title); per-person number = order of work
PACKAGES = {
    "CUR1_01_CROSS6": ("CUR1", "SCREEN90_OVERLAP_CUR1", "CUR1-OVL", "交叉复核（6 条，来自 CUR2 的组）"),
    "CUR2_01_CROSS5": ("CUR2", "SCREEN90_OVERLAP_CUR2", "CUR2-OVL", "交叉复核（5 条，来自 CUR1 的组）"),
    "CUR1_02_SCREEN40": ("CUR1", "SCREEN90_CUR1", "CUR1", "正式筛查（40 条）"),
    "CUR2_02_SCREEN50": ("CUR2", "SCREEN90_CUR2", "CUR2", "正式筛查（50 条）"),
    "CUR1_03_PP1_S8": ("CUR1", "PP1_CURATOR_CURP", "CUR1", "PP1 生成前 S 标注（8 条）"),
}
# Order chosen so that no formal item is labelled after its curator has read a later session of the same person
# (CUR1: cross 6 -> formal 40 -> PP1 8 gives 0 formal exposures; PP1 first would give 10).

def owner_slot() -> dict:
    """owner -> CUR1 / CUR2 (the curator whose formal group holds that person)."""
    raw, frame, _c = W._frame_and_raw()
    fr = {r["prefix_id"]: r for r in frame}
    out = {}
    for r in R14._screen_items():
        out[fr[r["prefix_id"]]["owner_id"]] = r["slot"]
    return out


OTHER = {"CUR1": "CUR2", "CUR2": "CUR1"}
# Translation operator of a session = the OTHER curator (never R1/R2): each curator reads the other group's people in
# full while translating, so no formal (primary) item is labelled after its curator has read a later session.


def jdump(p, o, pretty=True):
    return W.jdump(Path(p), o, pretty=pretty)


def jload(p):
    return json.loads(Path(p).read_text(encoding="utf-8"))


# ------------------------------------------------------------------ source cases (with stable source identity)
def _src_cases(kind: str, pids: list[str]):
    """Cases as R14 built them, plus the source key of every turn: (owner, session, turn index)."""
    raw, frame, census = W._frame_and_raw()
    import V321_wsb_pr18_receipt as S
    if kind == "PP1":
        cen = {c["prefix_id"]: c for c in map(json.loads, S.CENSUS.read_text().splitlines())}
        ref = {c["case_key"]: c for c in W.pp1_cases()}
        out = []
        for pid in pids:
            c = cen[pid]
            sess = raw.sessions[(c["owner_id"], c["session_id"])]
            legal = raw.legal_past(c["owner_id"], c["cutoff_rank"], c["timestamp"])
            case = dict(case_key=pid, owner_key=c["owner_id"], order_key=c["cutoff_rank"],
                        prefix=_tag(sess["turns"][:c["cut_turn"] + 1], c["owner_id"], c["session_id"]),
                        history=[dict(date=s["date"], turns=_tag(s["turns"], c["owner_id"], s["session_id"]),
                                      _rank=s["rank"]) for s in legal])
            r = ref[pid]
            assert [t["text"] for t in case["prefix"]] == [t["text"] for t in r["prefix"]]
            assert [[t["text"] for t in s["turns"]] for s in case["history"]] == \
                [[t["text"] for t in s["turns"]] for s in r["history"]]
            out.append(case)
        return out
    fr = {r["prefix_id"]: r for r in frame}
    out = []
    for pid in pids:
        f = fr[pid]
        c = census.get(pid)
        sess = raw.sessions[(f["owner_id"], f["session_id"])]
        legal = raw.legal_past(f["owner_id"], f["cutoff_rank"], c["timestamp"] if c else None) \
            if f["cutoff_rank"] >= 1 else []
        out.append(dict(case_key=pid, owner_key=f["owner_id"], order_key=(f["cutoff_rank"], f["cut_turn"]),
                        prefix=_tag(sess["turns"][:f["cut_turn"] + 1], f["owner_id"], f["session_id"]),
                        history=[dict(date=s["date"], turns=_tag(s["turns"], f["owner_id"], s["session_id"]),
                                      _rank=s["rank"]) for s in legal]))
    return out


def _tag(turns, owner, sid):
    return [dict(role=t["role"], text=t["text"], _src=(owner, sid, j)) for j, t in enumerate(turns)]


def _plain(cases, tm=None):
    """Strip source tags; attach aligned Chinese from the translation memory when given."""
    def turn(t):
        d = dict(role=t["role"], text=t["text"])
        if tm is not None:
            k = ukey(t["_src"], t["text"])
            if k in tm:
                d["zh_seg"] = tm[k]
        return d
    return [dict(case_key=c["case_key"], owner_key=c["owner_key"], order_key=c["order_key"],
                 prefix=[turn(t) for t in c["prefix"]],
                 history=[dict(date=s["date"], turns=[turn(t) for t in s["turns"]]) for s in c["history"]])
            for c in cases]


def ukey(src, text) -> str:
    owner, sid, j = src
    return f"{owner}|{sid}|{j}|{hashlib.sha256(text.encode('utf-8')).hexdigest()[:16]}"


def _protocol():
    proto = jload(V3 / "V321A_WSB/protocol/PROTOCOL_V321A_CANDIDATE.json")
    return dict(id=proto["protocol"], sha256=proto["protocol_sha256"])


def _r14_registry():
    return jload(R14_PRIV / "KIT_REGISTRY.json")


def _pids_of(r14name):
    reg = _r14_registry()
    amap = jload(R14_PRIV / f"{r14name}.audit_map.json")
    return [v["case_key"] for v in amap.values()], reg["packages"][r14name]


def _salt(r14name):
    if r14name.startswith("PP1"):
        return "pp1-curator-order-v1"
    return "fcms-screen-overlap-order-v1" if "OVERLAP" in r14name else "fcms-screen-order-v1"


def build_package(name, tm=None):
    from metacom_pm.rl1v3.review import pp1_tool as T
    person, r14name, assignee, title = PACKAGES[name]
    pids, _info = _pids_of(r14name)
    cases = _src_cases("PP1" if r14name.startswith("PP1") else "FCMS", pids)
    kw = dict(assignee=assignee, protocol=_protocol(), simulated=False, salt=_salt(r14name))
    if tm is not None:
        kw.update(translation_method=TR_METHOD, translator_role="ChatGPT 网页版；操作人为另一组整理者（CUR1 译 CUR2 组人物，CUR2 译 CUR1 组人物）")
    pkg, amap = T.curator_package(_plain(cases, tm), **kw)
    return pkg, amap, cases


# ------------------------------------------------------------------ packages
def step_packages(_):
    from metacom_pm.rl1v3.review import pp1_tool as T
    PRIV.mkdir(parents=True, exist_ok=True)
    r14 = _r14_registry()
    reg = dict(kind="R15 English source packages (fixed codes); RAW-bearing files stay off the public repository",
               form_version=T.FORMS["S"]["version"], protocol=_protocol(), base_kit=dict(pr=25, head=BASE_HEAD),
               packages={})
    for name, (person, r14name, assignee, title) in PACKAGES.items():
        pkg, amap, cases = build_package(name)
        r14pkg = jload(R14_PRIV / f"{r14name}.package.json")
        same = pkg["package_sha256"] == r14pkg["package_sha256"]
        same_but_code = (not same) and T.package_sha({**pkg, "assignee": r14pkg["assignee"]}) == r14pkg["package_sha256"]
        ids = [c["case_key"] for c in cases] + sorted({t["_src"][1] for c in cases for s in c["history"] for t in s["turns"]}
                                                     | {c["prefix"][0]["_src"][1] for c in cases})
        hits = T.blind_scan(pkg, forbidden_ids=ids, role="curator")
        jdump(PRIV / f"{name}.en.package.json", pkg, pretty=False)
        jdump(PRIV / f"{name}.audit_map.json", amap)
        items = [dict(n=i + 1, item=it["key"], case_id=it["case_id"], label=pkg["cases"][it["case_id"]]["label"],
                      group=pkg["cases"][it["case_id"]]["group"], prefix_id=amap[it["case_id"]]["case_key"],
                      owner_id=amap[it["case_id"]]["owner_key"], form=it["form"],
                      source_check=T.case_check(pkg["cases"][it["case_id"]]))
                 for i, it in enumerate(pkg["stages"][0]["items"])]
        jdump(PRIV / f"{name}.items.json", items)
        reg["packages"][name] = dict(person=person, assignee=assignee, title=title, continues_r14=r14name,
                                     r14_package_sha256=r14pkg["package_sha256"], en_package_sha256=pkg["package_sha256"],
                                     identical_to_r14=same, identical_to_r14_except_code=same_but_code,
                                     items=len(items), with_history=sum(i["form"] == "S" for i in items),
                                     blind_scan_hits=len(hits))
        print(name, pkg["package_sha256"][:12], "R14", "same" if same else ("same-but-code" if same_but_code else "DIFF"),
              len(items), "hits", len(hits))
    reg["exposure"] = exposure()
    jdump(PRIV / "R15_REGISTRY.json", reg)


def exposure():
    """Cross-package as-of exposure for a curator who works through the packages in the listed order: an item counts
    when the curator has already read a session of the same person at or after the item's cutoff."""
    seen = defaultdict(dict)       # person -> owner -> max rank read
    slot = owner_slot()
    raw, _f, _c = W._frame_and_raw()
    for owner, sl in slot.items():           # translation: each curator reads the other group's people first
        seen[OTHER[sl]][owner] = max(s_["rank"] for s_ in raw.by_owner[owner])
    out = {}
    for name, (person, r14name, *_r) in PACKAGES.items():
        pids, _ = _pids_of(r14name)
        cases = _src_cases("PP1" if r14name.startswith("PP1") else "FCMS", pids)
        n = 0
        for c in cases:
            cut = c["order_key"][0] if isinstance(c["order_key"], tuple) else c["order_key"]
            if seen[person].get(c["owner_key"], -1) >= cut:
                n += 1
        for c in cases:
            ranks = [s["_rank"] for s in c["history"]] + [(c["order_key"][0] if isinstance(c["order_key"], tuple)
                                                          else c["order_key"])]
            seen[person][c["owner_key"]] = max(seen[person].get(c["owner_key"], -1), max(ranks))
        out[name] = dict(person=person, items_with_prior_later_reading=n)
    return out


# ------------------------------------------------------------------ translation batches
def _units_by_session():
    """All translation units: one per non-empty source turn, keyed by (owner, session, turn, text SHA)."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    sess = {}                # (owner, sid) -> dict(rank, date, turns:{j: text}, first_pkg)
    for name, (person, r14name, *_r) in PACKAGES.items():
        pids, _ = _pids_of(r14name)
        for c in _src_cases("PP1" if r14name.startswith("PP1") else "FCMS", pids):
            blocks = [(c["prefix"], None, None)] + [(s["turns"], s["_rank"], s["date"]) for s in c["history"]]
            for turns, rank, date in blocks:
                for t in turns:
                    owner, sid, j = t["_src"]
                    if not T.segments(t["text"]):
                        continue
                    e = sess.setdefault((owner, sid), dict(rank=rank, date=date, turns={}, first_pkg=name, roles={}))
                    if rank is not None:
                        e["rank"], e["date"] = rank, date
                    e["turns"][j] = t["text"]
                    e["roles"][j] = t["role"]
    return sess


def step_batches(_):
    from metacom_pm.rl1v3.review import pp1_tool as T
    raw, _f, _c = W._frame_and_raw()
    sess = _units_by_session()
    for (owner, sid), e in sess.items():                 # current-session-only entries: take rank/date from RAW
        if e["rank"] is None:
            r = raw.sessions[(owner, sid)]
            e["rank"], e["date"] = r["rank"], r["date"]
    owners = sorted({o for o, _ in sess}, key=lambda o: hashlib.sha256((LABEL_SALT + o).encode()).hexdigest())
    olabel = {o: f"人物 {i + 1:02d}" for i, o in enumerate(owners)}
    batches, cur, words = [], None, 0
    order = list(PACKAGES)
    slot = owner_slot()
    keyed_sessions = sorted(sess.items(), key=lambda kv: (order.index(kv[1]["first_pkg"]), slot[kv[0][0]],
                                                          owners.index(kv[0][0]), kv[1]["rank"]))
    for (owner, sid), e in keyed_sessions:
        w = sum(len(x.split()) for x in e["turns"].values())
        if cur is None or cur["first_pkg"] != e["first_pkg"] or cur["group"] != slot[owner] or words + w > BATCH_WORDS:
            cur = dict(id=f"B{len(batches) + 1:02d}", first_pkg=e["first_pkg"], group=slot[owner],
                       operator=OTHER[slot[owner]], sessions=[])
            batches.append(cur)
            words = 0
        cur["sessions"].append((owner, sid))
        words += w
    tdir = HAND / "00_TRANSLATE" / "batches"
    if tdir.exists():
        shutil.rmtree(tdir)
    tdir.mkdir(parents=True)
    registry = dict(kind="translation batch registry (private: maps line ids to source sentences)", batches={})
    plan = []
    for b in batches:
        lines, rows, n = [], [], 0
        for owner, sid in b["sessions"]:
            e = sess[(owner, sid)]
            full = len(raw.sessions[(owner, sid)]["turns"])
            js = sorted(e["turns"])
            part = "" if len(js) == len([t for t in raw.sessions[(owner, sid)]["turns"] if T.segments(t["text"])]) \
                else f"（只含前 {js[-1] + 1} 轮）"
            lines.append(f"### {olabel[owner]} · 第 {e['rank'] + 1} 次会话 · {e['date'] or '日期未知'}{part}")
            for j in js:
                text = e["turns"][j]
                who = {"seeker": "求助者", "user": "求助者", "supporter": "支持者", "assistant": "支持者"}.get(e["roles"][j], e["roles"][j])
                for k, s in enumerate(T.segments(text)):
                    n += 1
                    lid = f"{n:04d}"
                    lines.append(f"[{lid}] {who}｜{' '.join(s.split())}")
                    rows.append(dict(id=lid, unit=ukey((owner, sid, j), text), seg=k, text=s))
            lines.append("")
        body = "\n".join(lines).rstrip() + "\n"
        head = (f"PM-RL1 翻译批次 {b['id']} · 共 {n} 行\n"
                f"请按同目录《CHATGPT_转换说明_ZH.md》逐行翻译。只输出带编号的中文行，例如：[0001] 中文译文\n"
                f"输出文件名：{b['id']}.zh.txt\n"
                f"==============================================================\n\n")
        text = head + body
        f = tdir / f"{b['operator']}_操作" / f"{b['id']}.txt"
        f.parent.mkdir(exist_ok=True)
        f.write_text(text, encoding="utf-8")
        units = sorted({r["unit"] for r in rows})
        registry["batches"][b["id"]] = dict(file_sha256=file_sha256(f), first_package=b["first_pkg"], lines=rows,
                                            units=units, operator=b["operator"], people_group=b["group"])
        plan.append(dict(batch=b["id"], operator=b["operator"], people_group=b["group"], first_package=b["first_pkg"],
                         lines=n, sessions=len(b["sessions"]),
                         units=len(units), words=sum(len(r["text"].split()) for r in rows), file_sha256=file_sha256(f)))
    need = {}
    for name, (person, r14name, *_r) in PACKAGES.items():
        pids, _ = _pids_of(r14name)
        us = set()
        for c in _src_cases("PP1" if r14name.startswith("PP1") else "FCMS", pids):
            for t in c["prefix"] + [t for s in c["history"] for t in s["turns"]]:
                if T.segments(t["text"]):
                    us.add(ukey(t["_src"], t["text"]))
        need[name] = sorted(bid for bid, v in registry["batches"].items() if us & set(v["units"]))
        registry.setdefault("package_units", {})[name] = sorted(us)
    registry["package_batches"] = need
    jdump(PRIV / "TRANSLATION_REGISTRY.json", registry, pretty=False)
    summary = dict(batches=len(plan), lines=sum(p["lines"] for p in plan), units=sum(p["units"] for p in plan),
                   words=sum(p["words"] for p in plan), words_per_batch_max=BATCH_WORDS,
                   by_first_package={k: dict(batches=sum(p["first_package"] == k for p in plan),
                                             words=sum(p["words"] for p in plan if p["first_package"] == k))
                                     for k in PACKAGES},
                   by_operator={op: dict(batches=sum(p["operator"] == op for p in plan),
                                         words=sum(p["words"] for p in plan if p["operator"] == op)) for op in ("CUR1", "CUR2")},
                   package_needs_batches=need,
                   batch_files=[{k: p[k] for k in ("batch", "operator", "lines", "words", "file_sha256")} for p in plan],
                   rule="同一来源句子只出现一次（来源身份 + 原文 SHA）；人物与会话只用中性编号；批次不含任何标签、条件或回复；"
                        "每个批次只含一个组的人物，由另一组的整理者操作 ChatGPT；R1/R2 不接触批次")
    jdump(PRIV / "TRANSLATION_PLAN.json", summary)
    jdump(OUT / "translation/TRANSLATION_PLAN.json", summary)
    print(json.dumps({k: summary[k] for k in ("batches", "lines", "units", "words")}),
          json.dumps(summary["by_operator"], ensure_ascii=False), json.dumps(summary["by_first_package"], ensure_ascii=False))


# ------------------------------------------------------------------ returned translations: parse + check
_LINE = re.compile(r"^\s*\[(\d{4})\]\s?(.*)$")
_CJK = re.compile(r"[㐀-鿿豈-﫿]")
_NOTE = re.compile(r"(译注|译者注|注：|注:|【注|（注|\(注|Translator|translator'?s note|备注)")
_NEG_EN = re.compile(r"\b(not|no|never|nothing|nobody|none|neither|nor|cannot|without|nowhere)\b|n't\b", re.I)
_NEG_ZH = re.compile(r"[不没未无别非否莫勿免甭]")
_SPK = re.compile(r"^(求助者|支持者)\s*[｜|:：]\s*")


def parse_returned(files: list[Path]) -> dict[str, str]:
    """Later files override earlier ones for the same line id (fix files: B07.fix1.zh.txt ...)."""
    out = {}
    for f in files:
        for line in f.read_text(encoding="utf-8-sig").splitlines():
            m = _LINE.match(line)
            if m:
                out[m.group(1)] = _SPK.sub("", m.group(2).strip()).strip()
    return out


def check_line(en: str, zh: str) -> tuple[list[str], list[str]]:
    hard, warn = [], []
    en1 = " ".join(en.split())
    if not zh:
        return ["empty"], warn
    letters = len(re.findall(r"[A-Za-z]", en1))
    if letters > 3 and not _CJK.search(zh):
        hard.append("no_chinese")
    if letters > 3 and zh == en1:
        hard.append("copied_english")
    if _NOTE.search(zh):
        hard.append("translator_note")
    for d in re.findall(r"\d+", en1):
        if d not in zh:
            hard.append(f"digits_changed:{d}")
    if _NEG_EN.search(en1) and not _NEG_ZH.search(zh):
        warn.append("negation_check")
    zc = len(re.sub(r"\s", "", zh))
    if letters > 12 and not (0.12 <= zc / max(1, len(en1)) <= 1.3):
        warn.append("length_ratio")
    if re.search(r"[A-Za-z]{4,}", zh) and letters > 3:
        warn.append("latin_left")
    return hard, warn


def check_batch(bid: str, rows: list[dict], got: dict[str, str]) -> dict:
    ids = [r["id"] for r in rows]
    extra = sorted(set(got) - set(ids))
    hard, warn = [], []
    for r in rows:
        zh = got.get(r["id"])
        if zh is None:
            hard.append(dict(id=r["id"], code="missing"))
            continue
        h, w = check_line(r["text"], zh)
        hard += [dict(id=r["id"], code=c) for c in h]
        warn += [dict(id=r["id"], code=c) for c in w]
    hard += [dict(id=i, code="unknown_id") for i in extra]
    return dict(batch=bid, lines=len(rows), returned=len(got), ok=not hard, hard=hard, warnings=warn)


def step_zh(a):
    from metacom_pm.rl1v3.review import pp1_tool as T
    reg = jload(PRIV / "TRANSLATION_REGISTRY.json")
    rdir = Path(a.returned) if a.returned else HAND / "00_TRANSLATE" / "returned"
    tm, reports = {}, {}
    fixdir = HAND / "00_TRANSLATE" / "fix_requests"
    fixdir.mkdir(parents=True, exist_ok=True)
    for bid, b in reg["batches"].items():
        files = sorted(rdir.glob(f"{bid}.zh.txt")) + sorted(rdir.glob(f"{bid}.part*.zh.txt")) + \
            sorted(rdir.glob(f"{bid}.fix*.zh.txt"))          # base, continuation parts, then fixes (later wins)
        if not files:
            reports[bid] = dict(batch=bid, status="not_returned")
            continue
        got = parse_returned(files)
        rep = check_batch(bid, b["lines"], got)
        rep["files"] = [dict(name=f.name, sha256=file_sha256(f)) for f in files]
        reports[bid] = rep
        fx = fixdir / f"{bid}.fix_request.txt"
        if rep["hard"]:
            bad = {h["id"]: h["code"] for h in rep["hard"] if h["code"] != "unknown_id"}
            text = {r["id"]: r["text"] for r in b["lines"]}
            fx.write_text(f"批次 {bid}：以下各行需要重译（原因见括号）。请只输出这些行，格式不变，保存为 {bid}.fix1.zh.txt"
                          f"（第二次修正用 fix2，依此类推）。\n\n" +
                          "\n".join(f"[{i}] {' '.join(text[i].split())}    （{_why(c)}）" for i, c in sorted(bad.items())) + "\n",
                          encoding="utf-8")
        elif fx.exists():
            fx.unlink()
        if rep["ok"]:
            per = defaultdict(dict)
            for r in b["lines"]:
                per[r["unit"]][r["seg"]] = got[r["id"]]
            for u, segs in per.items():
                tm[u] = [segs[k] for k in sorted(segs)]
    jdump(PRIV / "TRANSLATION_MEMORY.json", tm, pretty=False)
    # build every package whose units are all translated
    built = {}
    fin = PRIV / "final"
    fin.mkdir(parents=True, exist_ok=True)
    for name in PACKAGES:
        need = reg["package_units"][name]
        missing = [u for u in need if u not in tm]
        if missing:
            built[name] = dict(status="waiting_translation", missing_units=len(missing),
                               batches_pending=sorted(b for b in reg["package_batches"][name]
                                                      if not reports.get(b, {}).get("ok")))
            continue
        pkg, amap, cases = build_package(name, tm)
        en = jload(PRIV / f"{name}.en.package.json")
        ident = _same_source(pkg, en)
        html = T.render_html(pkg, title=PACKAGES[name][3])
        person = PACKAGES[name][0]
        dest = HAND / person / f"{name}.html"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(html, encoding="utf-8")
        jdump(fin / f"{name}.zh.package.json", pkg, pretty=False)
        chk = check_html(dest)
        built[name] = dict(status="built" if ident and chk["ok"] else "REFUSED", html=str(dest), html_sha256=file_sha256(dest),
                           zh_package_sha256=pkg["package_sha256"], en_package_sha256=en["package_sha256"],
                           same_english_source=ident, translation_mapping_sha256=pkg["translation"]["mapping_sha256"],
                           check=chk)
        if not (ident and chk["ok"]):
            dest.unlink()
    out = dict(batches={k: {kk: vv for kk, vv in v.items() if kk not in ("hard", "warnings")} |
                        dict(hard=len(v.get("hard", [])), warnings=len(v.get("warnings", [])))
                        for k, v in reports.items()},
               packages=built)
    jdump(PRIV / "ZH_BUILD.json", dict(out, detail=reports))
    jdump(HAND / "00_TRANSLATE" / "CHECK_RESULT.json", out)
    for k, v in reports.items():
        if v.get("status") != "not_returned":
            print(k, "OK" if v["ok"] else f"需要修正 {len(v['hard'])} 行", f"提示 {len(v['warnings'])}")
    for k, v in built.items():
        print(k, v["status"], v.get("html_sha256", "")[:12] or v.get("batches_pending"))


def _why(code):
    return {"missing": "缺这一行", "empty": "空行", "no_chinese": "没有中文", "copied_english": "照抄了英文",
            "translator_note": "加了译注/说明，请只给译文", "unknown_id": "编号不存在"}.get(
        code, "数字必须原样保留：" + code.split(":", 1)[1] if code.startswith("digits_changed") else code)


def _same_source(zh_pkg, en_pkg) -> bool:
    from metacom_pm.rl1v3.review import pp1_tool as T
    drop = ("package_sha256", "translation")
    a = {k: v for k, v in T.en_only(zh_pkg).items() if k not in drop}
    b = {k: v for k, v in T.en_only(en_pkg).items() if k not in drop}
    return T.canon(a) == T.canon(b)


# ------------------------------------------------------------------ check any final HTML
def extract(html: str) -> dict:
    m = re.search(r'<script type="application/json" id="pp1-package">(.*?)</script>', html, re.S)
    scripts = re.findall(r"<script>(.*?)</script>", html, re.S)
    return dict(package=json.loads(m.group(1).replace("<\\/", "</")) if m else None, scripts=scripts)


def check_html(path: Path, *, issued: dict | None = None, forbidden: list | None = None) -> dict:
    """Identity, logic, translation alignment and blinding checks; works on any HTML that claims to be a final page."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    here = PROJECT / "src/metacom_pm/rl1v3/review"
    x = extract(Path(path).read_text(encoding="utf-8"))
    res = dict(file=str(path), checks=[])

    def ck(name, ok, detail=None):
        res["checks"].append(dict(name=name, ok=bool(ok), detail=detail))
    pkg = x["package"]
    ck("embedded package present", pkg is not None)
    if pkg is None:
        res["ok"] = False
        return res
    ck("package SHA matches its content", T.package_sha(pkg) == pkg.get("package_sha256"))
    core = (here / "pp1_core.js").read_text(encoding="utf-8")
    ui = (here / "pp1_ui.js").read_text(encoding="utf-8")
    ck("verified core logic unchanged (pp1_core.js)", core in x["scripts"])
    ck("verified page logic unchanged (pp1_ui.js)", ui in x["scripts"])
    ck("no other scripts", len(x["scripts"]) == 2, len(x["scripts"]))
    ck("no network references", not re.search(r"https?://|src=|<link|@import|fetch\(|XMLHttpRequest", Path(path).read_text(
        encoding="utf-8").replace(core, "").replace(ui, "")))
    issued = issued if issued is not None else _issued_en()
    en_sha = None
    for sha_, en in issued.items():
        if _same_source(pkg, en):
            en_sha = sha_
    ck("same English source as an issued package", en_sha is not None, en_sha)
    units, bad = [], []

    def walk(o):
        if isinstance(o, dict):
            if "text" in o and isinstance(o.get("text"), str):
                units.append(o)
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk({k: pkg[k] for k in ("cases", "replies") if k in pkg})
    for u in units:
        if "zh_seg" in u:
            if "".join(u["seg"]) != u["text"] or len(u["seg"]) != len(u["zh_seg"]) or u["zh"] != T.join_zh(u["seg"], u["zh_seg"]):
                bad.append(u.get("ref"))
    need = [u for u in units if T.segments(u["text"])]
    ck("every sentence translated and aligned", not bad and all("zh_seg" in u for u in need),
       dict(misaligned=len(bad), untranslated=sum("zh_seg" not in u for u in need)))
    tb = pkg.get("translation", {})
    if pkg.get("role") == "curator":          # mapping is recorded in item order: prefix lines, then history lines
        seq = []
        for it in pkg["stages"][0]["items"]:
            c = pkg["cases"][it["case_id"]]
            seq += c["prefix"] + ([t for s in c["history"]["sessions"] for t in s["turns"]] if c.get("history") else [])
        tr = [dict(ref=u["ref"], src_sha256=T.sha(u["text"]), zh_sha256=T.sha(u["zh"])) for u in seq if u.get("zh")]
        ck("translation mapping recorded (every line: source SHA + translation SHA)",
           tb.get("mapping_sha256") == (T.sha(T.canon(tr)) if tr else None) and tb.get("units") == len(tr))
    else:
        ck("translation recorded", bool(tb.get("provided")) == any(u.get("zh") for u in units))
    hits = T.blind_scan(pkg, forbidden_ids=_forbidden_ids() if forbidden is None else forbidden,
                        role=pkg.get("role", "reviewer"))
    ck("blind scan (no ids, conditions, labels, scores)", not hits, hits[:5])
    res["ok"] = all(c["ok"] for c in res["checks"])
    res["package_sha256"] = pkg["package_sha256"]
    res["en_package_sha256"] = en_sha
    return res


def _issued_en() -> dict:
    out = {}
    for name in PACKAGES:
        p = PRIV / f"{name}.en.package.json"
        if p.exists():
            d = jload(p)
            out[d["package_sha256"]] = d
    return out


def _forbidden_ids():
    ids = set()
    for name in PACKAGES:
        p = PRIV / f"{name}.audit_map.json"
        if p.exists():
            ids |= {v["case_key"] for v in jload(p).values()}
    raw, _f, _c = W._frame_and_raw()
    ids |= {sid for (_o, sid) in raw.sessions}
    return sorted(i for i in ids if len(i) >= 6)


def step_check(a):
    r = check_html(Path(a.file))
    for c in r["checks"]:
        print(("PASS " if c["ok"] else "FAIL ") + c["name"] + ("" if c["ok"] or c["detail"] is None else f"  {c['detail']}"))
    print("RESULT:", "可以使用" if r["ok"] else "不能投入真实评审")
    if a.e2e:
        print(json.dumps(smoke(Path(a.file)), ensure_ascii=False)[:600])


def smoke(path: Path, out: Path | None = None) -> dict:
    """Headless browser: Chinese shown first, English expandable, progress export verifies, import restores."""
    import subprocess
    import tempfile
    from metacom_pm.rl1v3.review import pp1_tool as T
    out = out or Path(tempfile.mkdtemp(prefix="r15smoke_", dir=os.environ.get("TMPDIR")))
    out.mkdir(parents=True, exist_ok=True)
    cfg = dict(chrome=W.CHROME if hasattr(W, "CHROME") else _chrome(), html=str(Path(path).resolve()), out=str(out),
               tmpdir=os.environ.get("TMPDIR", "/tmp"))
    (out / "cfg.json").write_text(json.dumps(cfg), encoding="utf-8")
    p = subprocess.run(["node", str(PROJECT / "scripts/rl1v3/V321A_r15_smoke.mjs"), str(out / "cfg.json")],
                       capture_output=True, text=True, timeout=240)
    res = json.loads((out / "result.json").read_text()) if (out / "result.json").exists() else dict(checks=[], errors=[p.stderr[-800:]])
    exp = out / "dl" / "progress.json"
    if exp.exists():
        pkg = extract(Path(path).read_text(encoding="utf-8"))["package"]
        v = T.verify_export(jload(exp), {pkg["package_sha256"]: pkg})
        res["checks"].append(dict(name="Python independently verifies the exported progress file", ok=v["ok"], detail=v.get("error")))
    res["ok"] = bool(res["checks"]) and all(c["ok"] for c in res["checks"]) and not res.get("errors")
    return res


def _chrome():
    for c in ("/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
              "/opt/google/chrome/chrome"):
        if Path(c).exists():
            return c
    return shutil.which("google-chrome") or shutil.which("chromium") or "google-chrome"


# ------------------------------------------------------------------ receive / report (issued final packages only)
def _issued_final():
    zb = PRIV / "ZH_BUILD.json"
    out = {}
    if zb.exists():
        for name, v in jload(zb)["packages"].items():
            if v.get("status") == "built":
                out[v["zh_package_sha256"]] = (name, jload(PRIV / "final" / f"{name}.zh.package.json"),
                                               jload(PRIV / f"{name}.audit_map.json"))
    return out


CUSTODY = "received"


def step_receive(a):
    from metacom_pm.rl1v3.review import pp1_tool as T
    pk = _issued_final()
    exp = jload(a.export)
    base = exp.get("base_package_sha256")
    if base not in pk:
        en = _issued_en()
        raise SystemExit("REFUSED: 这是英文源文件（不分发）的导出" if base in en else "REFUSED: 不属于任何已发放的任务包")
    name, pkg, _amap = pk[base]
    v = T.verify_export(exp, {pkg["package_sha256"]: pkg})
    if not v["ok"]:
        raise SystemExit(f"REFUSED: {v['error']}")
    d = PRIV / CUSTODY
    d.mkdir(parents=True, exist_ok=True)
    locked = all(s["locked"] for s in exp["stages"].values())
    # independence: CUR1 keeps the returned files, so CUR1's own cross-check must be locked before CUR2's labels arrive
    if name == "CUR2_02_SCREEN50" and not any(json.loads(p.read_text())["stage_locked"] for p in d.glob("CUR1_01_CROSS6_*.receipt.json")):
        raise SystemExit("REFUSED: 请先收 CUR1 的交叉复核（6 条，已锁定）导出，再收 CUR2 的 50 条导出（CUR1 保管收件，不能先看到 CUR2 的标签）")
    rec = dict(package=name, package_sha256=base, assignee=exp["assignee"], head=exp["head"], n_events=len(exp["events"]),
               export_sha256=hashlib.sha256(Path(a.export).read_bytes()).hexdigest(), stage_locked=locked,
               submitted=sum(s["submitted"] for s in exp["stages"].values()), kind=exp.get("kind"))
    jdump(d / f"{name}_{exp['head'][:8]}.receipt.json", rec)
    (d / f"{name}_{exp['head'][:8]}.export.json").write_bytes(Path(a.export).read_bytes())
    print(json.dumps(dict(package=name, locked=locked, submitted=rec["submitted"], receipt=rec["export_sha256"][:16]),
                     ensure_ascii=False))


def step_report(_):
    """Aggregate counts only (no per-item labels): safe to pass to R1."""
    from metacom_pm.rl1v3.review import screen_report as SR
    import V321_wsb_admission as A
    pk = _issued_final()
    group_of = A._groups()
    latest = {}
    for rp in sorted((PRIV / CUSTODY).glob("*.receipt.json")):
        r = jload(rp)
        if r["stage_locked"]:
            latest[r["package"]] = rp.with_name(rp.name.replace(".receipt.json", ".export.json"))
    kind = {"CUR1_03_PP1_S8": "PP1", "CUR1_02_SCREEN40": "primary", "CUR2_02_SCREEN50": "primary",
            "CUR1_01_CROSS6": "overlap", "CUR2_01_CROSS5": "overlap"}
    issued = {s: v[1] for s, v in pk.items()}
    reports = {}
    for kd in ("PP1", "primary", "overlap"):
        d = {n: p for n, p in latest.items() if kind[n] == kd}
        if d:
            exps = {n: jload(p) for n, p in d.items()}
            maps = {n: next(m for s, (nn, _pk, m) in pk.items() if nn == n) for n in d}
            reports[kd] = SR.screen_report(exps, maps, group_of, issued)
    out = dict(received_locked=sorted(latest))
    if "primary" in reports and "overlap" in reports:
        out["overlap_agreement"] = SR.overlap_agreement(reports["primary"]["rows"], reports["overlap"]["rows"])
    jdump(PRIV / "SCREEN_REPORT_FULL.json", dict(out, reports=reports))
    safe = dict(out, reports={k: {kk: vv for kk, vv in r.items() if kk not in ("rows", "s1_per_group")}
                              for k, r in reports.items()}, note="只含汇总计数与耗时；逐条标签只在 CUR1 保管目录")
    jdump(HAND / "CUR1" / "COORDINATOR" / "SCREEN_REPORT_SUMMARY.json", safe)
    print(json.dumps({k: (r["counts"], r["groups_with_s1"]) for k, r in reports.items()}, ensure_ascii=False))


# ------------------------------------------------------------------ practice (simulated, no RAW)
def sim_zh(text: str) -> list[str]:
    """Hand-written Chinese for the synthetic practice sentences (aligned to pp1_tool.segments)."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    from metacom_pm.rl1v3.review import pp1_sim as SIM
    zt = {"starting a new job at a bakery": "在面包店开始一份新工作", "my manager seems strict": "我的经理好像很严格",
          "I tried waking up earlier but it did not help": "我试过早点起床，但没有用",
          "moving to a new city": "搬到一个新城市", "I still know nobody here": "我在这里还一个人都不认识",
          "joining a running club felt awkward last time": "上次加入跑步俱乐部时觉得很尴尬",
          "my sister's wedding planning": "我姐姐的婚礼筹备", "everyone keeps asking me to help": "大家一直找我帮忙",
          "I said no to organising the music": "我拒绝了安排音乐的事",
          "preparing for a driving test": "准备驾照考试", "I failed the parking part once": "我有一次倒车入库没过",
          "practising at night made me more nervous": "晚上练习让我更紧张",
          "caring for an old dog": "照顾一只老狗", "the vet visits are expensive": "看兽医很贵",
          "a payment plan was rejected by the clinic": "诊所拒绝了分期付款",
          "learning to cook for myself": "学着自己做饭", "I keep burning the rice": "我总是把米饭煮糊",
          "the cooking class was too fast for me": "烹饪课对我来说太快了",
          "a long exam season": "漫长的考试季", "my friends study much faster": "我的朋友们学得快得多",
          "a study group made me feel worse": "学习小组让我感觉更糟",
          "repairing a friendship": "修复一段友谊", "we argued about a trip": "我们为一次旅行吵了架",
          "my first apology message got no answer": "我第一次发的道歉消息没有回音"}
    pats = [
        (r"^Simulated session (\d+): I want to talk about (.+)\.$", lambda m: f"模拟第 {m[1]} 次会话：我想聊聊{zt[m[2]]}。"),
        (r"^Simulated supporter: thank you for sharing about (.+)\.$", lambda m: f"模拟支持者：谢谢你分享{zt[m[1]]}的事。"),
        (r"^How are you feeling\?$", lambda m: "你现在感觉怎么样？"),
        (r"^Simulated: honestly (.+)\.$", lambda m: f"模拟：说实话，{zt[m[1]]}。"),
        (r"^Simulated supporter: that sounds hard\.$", lambda m: "模拟支持者：听起来很不容易。"),
        (r"^What have you tried so far\?$", lambda m: "到目前为止你试过什么办法？"),
        (r"^Simulated: (.+)\.$", lambda m: f"模拟：{zt[m[1]]}。"),
        (r"^Simulated today: things around (.+) came back this week\.$", lambda m: f"模拟今天：这周，和{zt[m[1]]}有关的事又冒出来了。"),
        (r"^Simulated supporter: I am here\.$", lambda m: "模拟支持者：我在这里。"),
        (r"^What happened\?$", lambda m: "发生了什么？"),
        (r"^Simulated today: (.+) again and I do not know what to do\.$", lambda m: f"模拟今天：又是{zt[m[1]]}，我不知道该怎么办。"),
        (r"^Simulated first talk: I just want someone to listen today\.$", lambda m: "模拟第一次谈话：今天我只是想有人听我说说。"),
        (r"^Simulated reply: it makes sense that (.+) feels heavy\.$", lambda m: f"模拟回复：{zt[m[1]]}让人觉得沉重，这很正常。"),
        (r"^Would it help to talk through one small step you could take this week\?$",
         lambda m: "一起聊聊这周你可以迈出的一小步，会有帮助吗？"),
        (r"^Simulated reply: you mentioned before that (.+), so let us not repeat that\.$",
         lambda m: f"模拟回复：你之前提到{zt[m[1]]}，所以我们别再重复那样做。"),
        (r"^It makes sense that (.+) feels heavy\.$", lambda m: f"{zt[m[1]]}让人觉得沉重，这很正常。"),
        (r"^What would feel manageable right now\?$", lambda m: "现在什么事情让你觉得可以应付？"),
    ]
    out = []
    for s in T.segments(text):
        s1 = s.strip()
        for pat, fn in pats:
            m = re.match(pat, s1)
            if m:
                out.append(fn(m))
                break
        else:
            raise KeyError(s1)
    _ = SIM
    return out


def _sim_with_zh(cases):
    def turn(t):
        return dict(t, zh_seg=sim_zh(t["text"]))
    return [dict(c, prefix=[turn(t) for t in c["prefix"]],
                 history=[dict(s, turns=[turn(t) for t in s["turns"]]) for s in c["history"]]) for c in cases]


PRAC_METHOD = "练习材料：模拟句子的中文由 WS-B 手写（不是真实翻译流程）"


def practice_reviewer(who: str):
    from metacom_pm.rl1v3.review import pp1_tool as T
    from metacom_pm.rl1v3.review import pp1_sim as SIM
    cs = SIM.cases()[:3]
    reps, pairs, _ = SIM.replies(cs)
    reps = [dict(r, zh_seg=sim_zh(r["text"])) for r in reps]
    return T.reviewer_packages(_sim_with_zh(cs), reps, pairs, assignee=f"练习-{who}", protocol=SIM.SIM_PROTOCOL,
                               simulated=True, salt=SIM.SIM_SALT, mirror=(who == "R2"), translation_method=PRAC_METHOD,
                               translator_role="WS-B（练习）")


def step_practice(_):
    from metacom_pm.rl1v3.review import pp1_tool as T
    from metacom_pm.rl1v3.review import pp1_sim as SIM
    prac = OUT / "practice"
    prac.mkdir(parents=True, exist_ok=True)
    files = {}
    for who in ("CUR1", "CUR2"):
        cpkg, _ = T.curator_package(_sim_with_zh(SIM.cases()[:3]) + [SIM.rank0_case()], assignee=f"练习-{who}",
                                    protocol=SIM.SIM_PROTOCOL, simulated=True, salt=SIM.SIM_SALT,
                                    translation_method=PRAC_METHOD, translator_role="WS-B（练习）")
        f = prac / f"PRACTICE_{who}_SCREENING.html"
        f.write_text(T.render_html(cpkg, title=f"练习：生成前筛查（模拟）· {who}"), encoding="utf-8")
        files[f.name] = dict(sha256=file_sha256(f), package_sha256=cpkg["package_sha256"])
    for who in ("R1", "R2"):
        p1, _mk, au = practice_reviewer(who)
        f = prac / f"PRACTICE_{who}_PART1_Q0.html"
        f.write_text(T.render_html(p1, title=f"练习：评审第一部分 Q0（模拟）· {who}"), encoding="utf-8")
        files[f.name] = dict(sha256=file_sha256(f), package_sha256=p1["package_sha256"])
    a1, a2 = practice_reviewer("R1")[2], practice_reviewer("R2")[2]
    mirror = all(a1["pairs"][p]["positions"][ch]["A"]["reply_id"] == a2["pairs"][p]["positions"][ch]["B"]["reply_id"]
                 for p in a1["pairs"] for ch in ("Q0", "QH"))
    same_zh = practice_reviewer("R1")[0]["replies"] == practice_reviewer("R2")[0]["replies"]
    # practice translation batch: dry run of the ChatGPT hand-off on synthetic text only
    lines, rows, n = [], [], 0
    seen = set()
    for c in SIM.cases()[:3]:
        for t in c["prefix"] + [t for s in c["history"] for t in s["turns"]]:
            if t["text"] in seen:
                continue
            seen.add(t["text"])
            for k, s in enumerate(T.segments(t["text"])):
                n += 1
                lines.append(f"[{n:04d}] {T._speaker(t['role'])}｜{' '.join(s.split())}")
                rows.append(dict(id=f"{n:04d}", text=s, seg=k, unit=T.sha(t["text"])[:16]))
    pb = prac / "PRACTICE_B00.txt"
    pb.write_text(f"PM-RL1 翻译批次 B00（练习，模拟句子）· 共 {n} 行\n请按《CHATGPT_转换说明_ZH.md》逐行翻译。只输出带编号的中文行。\n"
                  f"输出文件名：B00.zh.txt\n==============================================================\n\n"
                  + "\n".join(lines) + "\n", encoding="utf-8")
    jdump(prac / "PRACTICE_B00.registry.json", dict(lines=rows))
    files[pb.name] = dict(sha256=file_sha256(pb))
    jdump(prac / "PRACTICE_REGISTRY.json", dict(files=files, r1_r2_mirrored=mirror, r1_r2_same_reply_translation=same_zh,
                                                note="全部为模拟材料，不含 RAW；只用于练习与 ChatGPT 流程试跑"))
    print(json.dumps(dict(files=len(files), mirrored=mirror, same_zh=same_zh)))


def step_part2(a):
    """Coordinator (CUR1): practice part 2 once R1/R2 sends the Q0 stage file."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    exp = jload(a.export)
    who = a.who
    p1, mk, _au = practice_reviewer(who)
    v = T.verify_export(exp, {p1["package_sha256"]: p1})
    if not v["ok"]:
        raise SystemExit(f"REFUSED: {v['error']}")
    lock = next((e for e in exp["events"] if e["kind"] == "stage_lock" and e.get("item") == "Q0"), None)
    if lock is None:
        raise SystemExit("REFUSED: Q0 尚未锁定")
    p2 = mk(lock["h"])
    dest = Path(a.out) if a.out else OUT / "practice" / f"PRACTICE_{who}_PART2.package.json"
    jdump(dest, p2, pretty=False)
    print(dest, p2["package_sha256"][:12])


def step_practice_dryrun(a):
    """Build the practice page from ChatGPT's returned B00.zh.txt (dry run of the real flow on synthetic text)."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    from metacom_pm.rl1v3.review import pp1_sim as SIM
    reg = jload(OUT / "practice/PRACTICE_B00.registry.json")
    got = parse_returned([Path(a.returned)])
    rep = check_batch("B00", reg["lines"], got)
    print(json.dumps({k: rep[k] for k in ("lines", "returned", "ok")}), [h for h in rep["hard"]][:8])
    if not rep["ok"]:
        raise SystemExit("翻译未通过检查：请按上面列出的编号让 ChatGPT 重译")
    per = defaultdict(dict)
    for r in reg["lines"]:
        per[r["unit"]][r["seg"]] = got[r["id"]]
    tm = {u: [s[k] for k in sorted(s)] for u, s in per.items()}

    def turn(t):
        return dict(t, zh_seg=tm[T.sha(t["text"])[:16]])
    cs = [dict(c, prefix=[turn(t) for t in c["prefix"]], history=[dict(s, turns=[turn(t) for t in s["turns"]])
                                                                  for s in c["history"]]) for c in SIM.cases()[:3]]
    pkg, _ = T.curator_package(cs, assignee="练习-试跑", protocol=SIM.SIM_PROTOCOL, simulated=True, salt=SIM.SIM_SALT,
                               translation_method="ChatGPT 网页版（试跑）", translator_role="试跑")
    dest = Path(a.out) if a.out else HAND / "00_TRANSLATE" / "PRACTICE_DRYRUN.html"
    dest.write_text(T.render_html(pkg, title="试跑：ChatGPT 译文（模拟）"), encoding="utf-8")
    print(dest, file_sha256(dest)[:12])


# ------------------------------------------------------------------ after PP1 generation (coordinator CUR1; CUR2 translates)
def reply_batch(replies: list[dict], *, salt: str, batch_id: str = "Y01"):
    """Translation batch for generated replies: neutral numbers in a salted order; no case, pair, position or condition.
    Returns (text, rows); rows map line ids back to reply keys (coordinator only)."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    order = sorted(replies, key=lambda r: T.keyed(salt, "reply-translation-order", r["reply_key"]))
    lines, rows, n = [], [], 0
    for k, r in enumerate(order, start=1):
        lines.append(f"### 回复 {k:02d}")
        for j, sg in enumerate(T.segments(r["text"])):
            n += 1
            lines.append(f"[{n:04d}] {' '.join(sg.split())}")
            rows.append(dict(id=f"{n:04d}", reply_key=r["reply_key"], seg=j, text=sg))
        lines.append("")
    head = (f"PM-RL1 翻译批次 {batch_id}（候选回复）· 共 {n} 行\n请按《CHATGPT_转换说明_ZH.md》逐行翻译。"
            f"只输出带编号的中文行。不要比较、评价或排序这些回复。\n输出文件名：{batch_id}.zh.txt\n"
            "==============================================================\n\n")
    return head + "\n".join(lines).rstrip() + "\n", rows


def reply_translation(rows: list[dict], got: dict) -> dict:
    rep = check_batch("Y", rows, got)
    if not rep["ok"]:
        raise ValueError(f"reply translation not accepted: {rep['hard'][:5]}")
    per = defaultdict(dict)
    for r in rows:
        per[r["reply_key"]][r["seg"]] = got[r["id"]]
    return {k: [v[i] for i in sorted(v)] for k, v in per.items()}


def build_reviewers(cases_src, replies, pairs, *, salt, history_tm, reply_tm, protocol, simulated):
    """R1 / R2 part 1 with the SAME Chinese for every line; R2 sees the mirrored positions.  Returns
    {R1: (part1, make_part2, audit), R2: ...} -- part 2 is sealed only after that reviewer's Q0 anchor."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    cases = _plain(cases_src, history_tm) if history_tm is not None else cases_src
    reps = [dict(r, zh_seg=reply_tm[r["reply_key"]]) for r in replies]
    out = {}
    for who in ("R1", "R2"):
        out[who] = T.reviewer_packages(cases, reps, pairs, assignee=who, protocol=protocol, simulated=simulated, salt=salt,
                                       mirror=(who == "R2"), translation_method=TR_METHOD,
                                       translator_role="ChatGPT 网页版；回复由 CUR2 操作，历史由另一组整理者操作")
    a1, a2 = out["R1"][0], out["R2"][0]
    same_text = a1["replies"] == a2["replies"] and \
        {k: c["prefix"] for k, c in a1["cases"].items()} == {k: c["prefix"] for k, c in a2["cases"].items()}
    if not same_text:                     # (item labels / order differ by design; text and translation must not)
        raise ValueError("R1 and R2 would not see identical text and translation")
    for pk in out["R1"][2]["pairs"]:
        for ch in ("Q0", "QH"):
            p1, p2 = out["R1"][2]["pairs"][pk]["positions"][ch], out["R2"][2]["pairs"][pk]["positions"][ch]
            if p1["A"]["reply_id"] != p2["B"]["reply_id"]:
                raise ValueError("R2 positions are not the mirror of R1")
    return out


def _pp1_inputs(a):
    """REPLIES.jsonl rows {reply_key, case_key, condition, text} + PAIRS.json [[pair_key, case_key, x, y]] (from WS-A's
    validated PP1 outputs), the coordinator's secret salt file, and the PP1 cases with their history translation."""
    replies = [json.loads(x) for x in Path(a.replies).read_text(encoding="utf-8").splitlines() if x.strip()]
    pairs = [tuple(x) for x in jload(a.pairs)]
    salt = Path(a.salt_file).read_text(encoding="utf-8").strip()
    if len(salt) < 16:
        raise SystemExit("REFUSED: salt file too short (CUR1 creates it once and keeps it)")
    pids, _ = _pids_of("PP1_CURATOR_CURP")
    if {r["case_key"] for r in replies} - set(pids) or {p[1] for p in pairs} - set(pids):
        raise SystemExit("REFUSED: replies/pairs do not belong to the 8 PP1 prefixes")
    return replies, pairs, salt, _src_cases("PP1", pids)


def step_replybatch(a):
    """CUR1: write the reply translation batch for CUR2 (no case/pair/position/condition in it)."""
    replies, _pairs, salt, _cases = _pp1_inputs(a)
    text, rows = reply_batch(replies, salt=salt)
    d = HAND / "00_TRANSLATE" / "batches" / "CUR2_操作"
    d.mkdir(parents=True, exist_ok=True)
    (d / "Y01.txt").write_text(text, encoding="utf-8")
    co = HAND / "CUR1" / "COORDINATOR_只限CUR1"
    jdump(co / "Y01.registry.json", dict(lines=rows))
    print(d / "Y01.txt", len(rows), "lines")


def step_reviewers(a):
    """CUR1: build R1/R2 part 1 (Chinese first, identical translation, mirrored positions) after Y01 is returned."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    replies, pairs, salt, cases = _pp1_inputs(a)
    co = HAND / "CUR1" / "COORDINATOR_只限CUR1"
    rows = jload(co / "Y01.registry.json")["lines"]
    rdir = Path(a.returned) if a.returned else HAND / "00_TRANSLATE" / "returned"
    files = sorted(rdir.glob("Y01.zh.txt")) + sorted(rdir.glob("Y01.part*.zh.txt")) + sorted(rdir.glob("Y01.fix*.zh.txt"))
    rtm = reply_translation(rows, parse_returned(files))
    tm = jload(PRIV / "TRANSLATION_MEMORY.json")
    out = build_reviewers(cases, replies, pairs, salt=salt, history_tm=tm, reply_tm=rtm, protocol=_protocol(),
                          simulated=False)
    forbidden = _forbidden_ids() + [r["reply_key"] for r in replies] + [p[0] for p in pairs]
    for who, (p1, _mk, audit) in out.items():
        hits = T.blind_scan(p1, forbidden_ids=forbidden)
        if hits:
            raise SystemExit(f"REFUSED: {who} part 1 fails the blind scan: {hits[:3]}")
        f = HAND / who / f"{who}_PP1_第一部分_Q0.html"
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(T.render_html(p1, title=f"PP1 评审 第一部分 Q0 · {who}"), encoding="utf-8")
        chk = check_html(f, issued={}, forbidden=forbidden)
        bad = [c["name"] for c in chk["checks"] if not c["ok"] and not c["name"].startswith("same English source")]
        if bad:
            f.unlink()
            raise SystemExit(f"REFUSED: {who} page check failed: {bad}")
        jdump(co / f"PP1_{who}_part1.package.json", p1, pretty=False)
        jdump(co / f"PP1_{who}_AUDIT_NOT_FOR_REVIEWERS.json", audit)
        print(who, f, p1["package_sha256"][:12])


def step_part2real(a):
    """CUR1: after R1/R2 sends the locked Q0 stage file, register the anchor and write that reviewer's part 2."""
    from metacom_pm.rl1v3.review import pp1_tool as T
    replies, pairs, salt, cases = _pp1_inputs(a)
    co = HAND / "CUR1" / "COORDINATOR_只限CUR1"
    p1 = jload(co / f"PP1_{a.who}_part1.package.json")
    exp = jload(a.export)
    v = T.verify_export(exp, {p1["package_sha256"]: p1})
    if not v["ok"]:
        raise SystemExit(f"REFUSED: {v['error']}")
    lock = next((e for e in exp["events"] if e["kind"] == "stage_lock" and e.get("item") == "Q0"), None)
    if lock is None:
        raise SystemExit("REFUSED: Q0 尚未锁定")
    rows = jload(co / "Y01.registry.json")["lines"]
    rdir = HAND / "00_TRANSLATE" / "returned"
    files = sorted(rdir.glob("Y01.zh.txt")) + sorted(rdir.glob("Y01.part*.zh.txt")) + sorted(rdir.glob("Y01.fix*.zh.txt"))
    out = build_reviewers(cases, replies, pairs, salt=salt, history_tm=jload(PRIV / "TRANSLATION_MEMORY.json"),
                          reply_tm=reply_translation(rows, parse_returned(files)), protocol=_protocol(), simulated=False)
    p1b, mk, _au = out[a.who]
    if p1b["package_sha256"] != p1["package_sha256"]:
        raise SystemExit("REFUSED: part 1 cannot be rebuilt identically (inputs changed)")
    p2 = mk(lock["h"])
    anchors = co / "Q0_ANCHORS.json"
    reg = jload(anchors) if anchors.exists() else {}
    if a.who in reg and reg[a.who]["lock_event_h"] != lock["h"]:
        raise SystemExit("REFUSED: a different Q0 anchor is already registered for this reviewer")
    reg[a.who] = dict(lock_event_h=lock["h"], export_sha256=hashlib.sha256(Path(a.export).read_bytes()).hexdigest(),
                      part2_sha256=p2["package_sha256"])
    jdump(anchors, reg)
    f = HAND / a.who / f"{a.who}_PP1_第二部分_QH_F.json"
    jdump(f, p2, pretty=False)
    print(a.who, f, p2["package_sha256"][:12])


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("step", choices=["packages", "batches", "zh", "check", "receive", "report", "practice", "part2",
                                     "dryrun", "handover", "status", "selftest", "replybatch", "reviewers",
                                     "part2real"])
    ap.add_argument("--returned")
    ap.add_argument("--file")
    ap.add_argument("--e2e", action="store_true")
    ap.add_argument("--export")
    ap.add_argument("--who", choices=["R1", "R2"])
    ap.add_argument("--out")
    ap.add_argument("--no-browser", action="store_true")
    ap.add_argument("--replies")
    ap.add_argument("--pairs")
    ap.add_argument("--salt-file")
    ap.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    fn = {"packages": step_packages, "batches": step_batches, "zh": step_zh, "check": step_check,
          "receive": step_receive, "report": step_report, "practice": step_practice, "part2": step_part2,
          "dryrun": step_practice_dryrun, "selftest": step_selftest, "replybatch": step_replybatch,
          "reviewers": step_reviewers, "part2real": step_part2real}.get(a.step)
    if fn is None:
        import V321A_r15_docs as D
        fn = {"handover": D.step_handover, "status": D.step_status}[a.step]
    fn(a)



# ------------------------------------------------------------------ selftest (test-only translation; nothing distributed)
def mock_line(en: str) -> str:
    digits = " ".join(re.findall(r"\d+", en))
    return "【测试译文·非真实】" + (digits or "")


def step_selftest(a):
    """Whole hand-off on the REAL English packages with a fake translation, in a throw-away directory:
    batches -> returned files -> line checks -> Chinese HTML build -> page checks -> tamper refusals -> browser smoke
    -> receive order rule.  The fake pages are deleted at the end; nothing goes to the handover tree."""
    import copy
    import subprocess
    from metacom_pm.rl1v3.review import pp1_tool as T
    root = Path(os.environ.get("TMPDIR", "/tmp")) / "r15_selftest_TEST_ONLY"
    if root.exists():
        shutil.rmtree(root)
    priv, hand = root / "priv", root / "hand"
    shutil.copytree(PRIV, priv, ignore=shutil.ignore_patterns("final", "received", "ZH_BUILD.json",
                                                             "TRANSLATION_MEMORY.json", "SCREEN_REPORT_FULL.json"))
    env = dict(os.environ, R15_PRIV=str(priv), R15_HANDOVER=str(hand))
    checks = []

    def ck(name, ok, detail=None):
        checks.append(dict(name=name, ok=bool(ok), detail=detail))

    def run(*args):
        r = subprocess.run([sys.executable, __file__, *args], capture_output=True, text=True, env=env, timeout=900)
        return r.returncode, (r.stdout + r.stderr).strip().splitlines()
    rc, _ = run("batches")
    reg = jload(priv / "TRANSLATION_REGISTRY.json")
    ck("batches rebuild identically (same file SHA as the handover copy)",
       rc == 0 and all(v["file_sha256"] == jload(PRIV / "TRANSLATION_REGISTRY.json")["batches"][k]["file_sha256"]
                       for k, v in reg["batches"].items()))
    ret = hand / "00_TRANSLATE" / "returned"
    ret.mkdir(parents=True)
    digit_batch = next(k for k, v in sorted(reg["batches"].items()) if any(re.search(r"\d", r["text"]) for r in v["lines"][8:]))
    first = digit_batch
    for bid, b in reg["batches"].items():
        rows = {r["id"]: f"[{r['id']}] {mock_line(r['text'])}" for r in b["lines"]}
        if bid == first:                     # plant faults: one missing line, one changed number, one note, one copy
            ids = [r["id"] for r in b["lines"]]
            del rows[ids[0]]
            dr = next(r for r in b["lines"][8:] if re.search(r"\d", r["text"]))
            rows[dr["id"]] = f"[{dr['id']}] 【测试译文·非真实】数字被改"
            rows[ids[3]] += "（译注：语气）"
            cp = next(r for r in b["lines"][4:8] if len(re.findall(r"[A-Za-z]", r["text"])) > 3)
            rows[cp["id"]] = f"[{cp['id']}] {' '.join(cp['text'].split())}"
        lines = list(rows.values())
        (ret / f"{bid}.zh.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    rc, out = run("zh")
    zb = jload(priv / "ZH_BUILD.json")
    det = zb["detail"][first]
    codes = {h["code"].split(":")[0] for h in det["hard"]}
    ck("line checks catch a missing line, a changed number, a translator note and copied English",
       {"missing", "digits_changed", "translator_note"} <= codes and ({"copied_english", "no_chinese"} & codes), sorted(codes))
    ck("a fix request listing only the bad lines is written",
       (hand / "00_TRANSLATE/fix_requests" / f"{first}.fix_request.txt").exists())
    blocked = [n for n, v in zb["packages"].items() if v["status"] == "waiting_translation"]
    ck("packages needing the faulty batch are not built", bool(blocked) and all(
        first in zb["packages"][n]["batches_pending"] for n in blocked), blocked)
    # fix: rewrite the bad lines only
    fx = [f"[{r['id']}] {mock_line(r['text'])}" for r in reg["batches"][first]["lines"]
          if r["id"] in {h["id"] for h in det["hard"]}]
    (ret / f"{first}.fix1.zh.txt").write_text("\n".join(fx) + "\n", encoding="utf-8")
    rc, out = run("zh")
    zb = jload(priv / "ZH_BUILD.json")
    built = {n: v for n, v in zb["packages"].items() if v["status"] == "built"}
    ck("after the fix file every package is built and passes the page checks", len(built) == len(PACKAGES),
       {n: v["status"] for n, v in zb["packages"].items()})
    ck("Chinese pages keep exactly the English source of the issued packages",
       all(v["same_english_source"] and v["en_package_sha256"] == jload(PRIV / f"{n}.en.package.json")["package_sha256"]
           for n, v in built.items()))
    # the same source sentence gets the same Chinese everywhere (one translation per source identity)
    tm = jload(priv / "TRANSLATION_MEMORY.json")
    ck("one translation per source sentence (translation memory size = unique units)",
       len(tm) == len({u for b in reg["batches"].values() for u in b["units"]}), len(tm))
    # page-level tamper refusals on one built page
    name = "CUR1_01_CROSS6"
    html = Path(built[name]["html"]).read_text(encoding="utf-8")
    tdir = root / "tamper"
    tdir.mkdir()
    pkg = extract(html)["package"]

    def page_with(p, ui_extra="", extra=""):
        h = T.render_html(p, title="tamper")
        if ui_extra:
            h = h.replace("'use strict';", "'use strict';" + ui_extra, 1)
        return h.replace("</body>", extra + "</body>")
    cases = {}
    p1 = copy.deepcopy(pkg)
    cid = next(iter(p1["cases"]))
    u = next(t for t in p1["cases"][cid]["prefix"] if t.get("zh_seg"))
    u["zh_seg"][0] = "被改动的译文"
    cases["edited translation without resealing"] = page_with(p1)
    p2 = copy.deepcopy(pkg)
    u = next(t for t in p2["cases"][cid]["prefix"] if t.get("zh_seg"))
    u["text"] = u["text"] + " (edited)"
    u["seg"][-1] = u["seg"][-1] + " (edited)"
    cases["English source edited and resealed"] = page_with(T.seal(p2))
    p3 = copy.deepcopy(pkg)
    u = next(t for t in p3["cases"][cid]["prefix"] if t.get("zh_seg") and len(t["zh_seg"]) > 1)
    u["zh_seg"] = u["zh_seg"][:-1]
    cases["sentence alignment broken and resealed"] = page_with(T.seal(p3))
    cases["page logic modified"] = page_with(pkg, ui_extra=" var _x = 1;")
    cases["external script added"] = page_with(pkg, extra='<script src="https://example.org/x.js"></script>')
    p6 = copy.deepcopy(pkg)
    p6["cases"][cid]["label"] = p6["cases"][cid]["label"] + "（OFF）"
    cases["blinding term inserted and resealed"] = page_with(T.seal(p6))
    for label, h in cases.items():
        f = tdir / (re.sub(r"\W+", "_", label) + ".html")
        f.write_text(h, encoding="utf-8")
        r = check_html(f, issued={jload(priv / f"{name}.en.package.json")["package_sha256"]:
                                  jload(priv / f"{name}.en.package.json")})
        ck(f"page check refuses: {label}", not r["ok"], [c["name"] for c in r["checks"] if not c["ok"]])
    if not a.no_browser:
        sm = smoke(Path(built[name]["html"]), out=root / "smoke")
        for c in sm["checks"]:
            ck("browser: " + c["name"], c["ok"], c["detail"])
        ck("browser: no errors", not sm.get("errors"), sm.get("errors"))
    # receive order rule (CUR1 keeps the returned files): uses the simulated curator export of the zh E2E run
    e2e = OUT / "pp1_e2e_zh/exports/curator_final.json"
    if e2e.exists():
        exp = jload(e2e)
        spkg = next(p for p in exp["packages"] if not p.get("requires"))
        fin = priv / "final"
        sav = jload(priv / "ZH_BUILD.json")

        def as_name(n):
            jdump(fin / f"{n}.zh.package.json", spkg, pretty=False)
            jdump(priv / f"{n}.audit_map.json", {})
            jdump(priv / "ZH_BUILD.json", dict(packages={n: dict(status="built", zh_package_sha256=spkg["package_sha256"])}))
        as_name("CUR2_02_SCREEN50")
        rc, msg = run("receive", "--export", str(e2e))
        ck("receive refuses CUR2's 50 before CUR1's own cross-check is in", rc != 0 and "交叉复核" in " ".join(msg), msg[-1:])
        as_name("CUR1_01_CROSS6")
        rc, msg = run("receive", "--export", str(e2e))
        ck("receive accepts CUR1's locked cross-check", rc == 0, msg[-1:])
        as_name("CUR2_02_SCREEN50")
        rc, msg = run("receive", "--export", str(e2e))
        ck("then CUR2's 50 is accepted", rc == 0, msg[-1:])
        bad = copy.deepcopy(exp)
        i = next(k for k, e in enumerate(bad["events"]) if e["kind"] == "submit")
        bad["events"][i]["data"]["answer"]["need"] = "S0" if bad["events"][i]["data"]["answer"].get("need") != "S0" else "S2"
        jdump(root / "tampered.json", bad)
        rc, msg = run("receive", "--export", str(root / "tampered.json"))
        ck("receive refuses an edited export", rc != 0 and "REFUSED" in " ".join(msg), msg[-1:])
        jdump(priv / "ZH_BUILD.json", sav)
    # PP1 after generation (fake replies for the 8 real PP1 prefixes; test only)
    pids, _ = _pids_of("PP1_CURATOR_CURP")
    reps, prs = [], []
    for i, pid in enumerate(pids):
        a_, b_ = f"t{i}:x", f"t{i}:y"
        reps += [dict(reply_key=a_, case_key=pid, condition="OFF", text=f"Fake reply {i} one. It is only a test."),
                 dict(reply_key=b_, case_key=pid, condition="RET-MS", text=f"Fake reply {i} two. Still a test only.")]
        prs.append([f"pair{i}", pid, a_, b_])
    (root / "REPLIES.jsonl").write_text("".join(json.dumps(r) + "\n" for r in reps), encoding="utf-8")
    jdump(root / "PAIRS.json", prs)
    (root / "salt.txt").write_text("TEST-ONLY-SALT-0123456789", encoding="utf-8")
    kw = ["--replies", str(root / "REPLIES.jsonl"), "--pairs", str(root / "PAIRS.json"), "--salt-file", str(root / "salt.txt")]
    rc, msg = run("replybatch", *kw)
    y = hand / "00_TRANSLATE/batches/CUR2_操作/Y01.txt"
    ytxt = y.read_text(encoding="utf-8") if y.exists() else ""
    ck("PP1 reply batch: written for CUR2, no case/pair/condition/key in it",
       rc == 0 and ytxt and not any(x in ytxt for x in ["OFF", "RET", "pair", "t0:x"] + pids), msg[-1:])
    yrows = jload(hand / "CUR1/COORDINATOR_只限CUR1/Y01.registry.json")["lines"]
    (ret / "Y01.zh.txt").write_text("".join(f"[{r['id']}] {mock_line(r['text'])}\n" for r in yrows), encoding="utf-8")
    rc, msg = run("reviewers", *kw)
    ck("PP1 R1/R2 part 1 built (Chinese first, identical translation, mirrored, blind scan, page checks)",
       rc == 0 and (hand / "R1/R1_PP1_第一部分_Q0.html").exists() and (hand / "R2/R2_PP1_第一部分_Q0.html").exists(),
       msg[-2:])
    res = dict(test_only=True, note="真实英文任务包 + 假译文（【测试译文·非真实】）；页面在测试结束后删除，不进入交接目录",
               checks=checks, passed=sum(c["ok"] for c in checks), total=len(checks))
    jdump(OUT / "selftest/R15_SELFTEST.json", res)
    if not a.keep:
        shutil.rmtree(root)
    print(json.dumps({k: res[k] for k in ("passed", "total")}))
    for c in checks:
        if not c["ok"]:
            print("FAIL", c["name"], c["detail"])

if __name__ == "__main__":
    main()
