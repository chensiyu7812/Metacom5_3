"""R15 hand-over tree (off the public repository) + DP preparation templates + SHA manifest.

  handover   copy the per-person files into the hand-over directory, write DP templates, SHA256SUMS + manifest
  status     one-line status per package (built / waiting for which batches)
"""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

import V321A_r15 as R
from metacom_pm.rl1v3.io import file_sha256

DOCS = R.OUT / "docs"
ROOT_DOCS = ["START_HERE_ZH.md", "ROLE_ASSIGNMENTS_ZH.md", "OPS_ZH.md", "STATUS_ZH.md"]
PERSON_DOCS = {"R1": ["REVIEWER_GUIDE_ZH.md"], "R2": ["REVIEWER_GUIDE_ZH.md"],
               "CUR1": ["CURATOR_GUIDE_R15_ZH.md", "DP_PREP_ZH.md"], "CUR2": ["CURATOR_GUIDE_R15_ZH.md", "DP_PREP_ZH.md"]}
COORD_DOCS = ["PP1_AFTER_GENERATION_ZH.md"]


def _cp(src: Path, dst: Path):
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(src, dst)


def dp_templates(dest: Path):
    """A's DP v2 role-registry format, pre-filled with the fixed codes; fields that need a real person or signature are
    left EMPTY on purpose, so A's freeze refuses the template until the coordinator completes it."""
    items = R.R14._screen_items()
    order = R.jload(R.R14_PRIV / "DP_OVERLAP_ORDER.json")
    people = {"R1": "", "R2": "", "CUR1": "", "CUR2": ""}
    assign = {r["prefix_id"]: dict(selector=r["slot"], reviewers={ch: ["R1", "R2"] for ch in ("Q0", "QH", "F")})
              for r in items}
    roles = dict(protocol_note="WS-A DP v2 角色登记格式（pmrl1-dp-human-selection-2）；只在真实 S 标签冻结、正式样本确认后启用",
                 sample_identity="", signed_by="", evidence="", frozen_at="", people=people, assignments=assign,
                 fill_rule="people 填各人稳定的 person_id（同一人只能有一个）；signed_by 为 CUR1；frozen_at 为签署时间；"
                           "正式样本确定后删去不在样本内的前缀。空字段会被 A 的 freeze 拒绝。")
    R.jdump(dest / "DP_ROLES_TEMPLATE.json", roles)
    second = dict(order_sha256=R.object_sha256(order), share=0.15, order=order,
                  rule="S 标签冻结后：按此顺序取 S1/S2 前缀中的前 15%（向上取整）；第二选择者 = 另一名整理者；"
                       "第二选择用单独的角色登记（只把 selector 换成第二选择者）与单独目录冻结；不改变、不替换主选择；"
                       "第二选择者先冻结自己的选择，之后协调人才登记另一人的主选择（CUR1 保管收件）")
    R.jdump(dest / "DP_SECOND_SELECTION_ORDER.json", second)
    return dict(prefixes=len(assign), order=len(order))


def step_handover(_a):
    H = R.HAND
    H.mkdir(parents=True, exist_ok=True)
    reg = R.jload(R.PRIV / "R15_REGISTRY.json")
    for d in ROOT_DOCS:
        _cp(DOCS / d, H / d)
    _cp(DOCS / "CHATGPT_转换说明_ZH.md", H / "00_TRANSLATE" / "CHATGPT_转换说明_ZH.md")
    _cp(R.PRIV / "TRANSLATION_PLAN.json", H / "00_TRANSLATE" / "TRANSLATION_PLAN.json")
    _cp(R.OUT / "practice/PRACTICE_B00.txt", H / "00_TRANSLATE" / "试跑_模拟" / "B00.txt")
    for sub in ("returned", "fix_requests"):
        (H / "00_TRANSLATE" / sub).mkdir(parents=True, exist_ok=True)
    (H / "00_TRANSLATE" / "returned" / "把ChatGPT返回的Bxx.zh.txt放在这里.txt").write_text(
        "文件名必须是 Bxx.zh.txt（续写部分 Bxx.part2.zh.txt，修正 Bxx.fix1.zh.txt）。\n", encoding="utf-8")
    for who, docs in PERSON_DOCS.items():
        for d in docs:
            _cp(DOCS / d, H / who / d)
    for who in ("CUR1", "CUR2"):
        _cp(R.OUT / f"practice/PRACTICE_{who}_SCREENING.html", H / who / f"00_练习_{who}_筛查（模拟）.html")
    for who in ("R1", "R2"):
        _cp(R.OUT / f"practice/PRACTICE_{who}_PART1_Q0.html", H / who / f"00_练习_{who}_评审第一部分Q0（模拟）.html")
    from metacom_pm.rl1v3.review import pp1_tool as T
    for name, (person, *_rest, title) in R.PACKAGES.items():
        en = R.jload(R.PRIV / f"{name}.en.package.json")
        src = H / person / "_英文源文件_不分发" / f"{name}.en.html"
        src.parent.mkdir(parents=True, exist_ok=True)
        src.write_text(T.render_html(en, title=title + "（英文源文件，不分发）"), encoding="utf-8")
    co = H / "CUR1" / "COORDINATOR_只限CUR1"
    for name in R.PACKAGES:
        _cp(R.PRIV / f"{name}.items.json", co / "ITEM_LISTS" / f"{name}.items.json")
        _cp(R.PRIV / f"{name}.audit_map.json", co / "AUDIT_MAPS" / f"{name}.audit_map.json")
    for d in COORD_DOCS:
        _cp(DOCS / d, co / d)
    R.jdump(co / "EXPOSURE.json", reg["exposure"])
    dpn = dp_templates(co / "DP_PREP")
    (co / "receipts").mkdir(exist_ok=True)
    # manifest
    files = sorted(p for p in H.rglob("*") if p.is_file() and p.name not in ("SHA256SUMS.txt", "MANIFEST_SHA256.json"))
    rows = [dict(path=str(p.relative_to(H)), sha256=file_sha256(p), bytes=p.stat().st_size) for p in files]
    (H / "SHA256SUMS.txt").write_text("".join(f"{r['sha256']}  {r['path']}\n" for r in rows), encoding="utf-8")
    man = dict(kind="R15 hand-over (off the public repository)", root=str(H), files=len(rows),
               packages={k: {kk: v[kk] for kk in ("person", "items", "en_package_sha256", "r14_package_sha256",
                                                   "identical_to_r14", "identical_to_r14_except_code")}
                         for k, v in reg["packages"].items()},
               dp_templates=dpn, rows=rows)
    R.jdump(H / "MANIFEST_SHA256.json", man)
    # repo copy: hashes and names only (no RAW)
    pub = dict(man, root="(off-repo hand-over directory)",
               rows=[dict(path=r["path"], sha256=r["sha256"], bytes=r["bytes"]) for r in rows])
    R.jdump(R.OUT / "HANDOVER_MANIFEST.json", pub)
    print(json.dumps(dict(files=len(rows), dp=dpn)))


def step_status(_a):
    zb = R.PRIV / "ZH_BUILD.json"
    reg = R.jload(R.PRIV / "TRANSLATION_REGISTRY.json")
    built = R.jload(zb)["packages"] if zb.exists() else {}
    for name in R.PACKAGES:
        v = built.get(name, {})
        need = reg["package_batches"][name]
        print(name, v.get("status", "waiting_translation"), "needs", len(need), "batches:", ",".join(need[:6]) +
              ("…" if len(need) > 6 else ""))
