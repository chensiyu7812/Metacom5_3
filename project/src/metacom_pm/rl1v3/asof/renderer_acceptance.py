"""WS-B independent acceptance checks for a unified renderer candidate (FC-MS gate C7).

Runs on request rows in the #19 shape (model_input.messages / input_ids, renderer_id, g_id, decode_id, step2_id,
condition, prefix_id).  B does not import A's renderer; every check re-derives what the Generator sees from RAW.

RA1 entities       payload vs RAW: verbatim / html-escaped / mismatch; entity count in G-visible evidence text
RA2 boundary       exactly one evidence block per resource arm; payload cannot contain a delimiter
RA3 single factor  arm minus its inserted block == OFF of the same prefix; framing (everything but the payload)
                   identical across all resource arms of the family (DP and RET may differ only in the chosen session)
RA4 native tokens  input_ids recomputed with the G0e tokenizer (separate step, tokenizer files only)
RA5 identity       one renderer_id per family; g_id / decode / step2 unchanged; a behaviour change => new renderer_id
RA6 leakage        future / other-owner / metadata scan (same rules as the #18/#19 receipts)
RA7 OFF reuse      OFF requests byte-identical to the G0e OFF requests (PP1 OFF stays valid)
"""
from __future__ import annotations

import html
import re
from collections import Counter, defaultdict

from metacom_pm.rl1v3.asof import e1_receipt as E

ENTITY = re.compile(r"&(?:#x?[0-9a-fA-F]+|quot|amp|lt|gt|apos);")
DELIMS = ("<resource", "</resource", "<Notes", "</Notes", "<ExternalEvidence", "</ExternalEvidence")
BLOCK = re.compile(r"(<resource\b[^>]*>|<ExternalEvidence\b[^>]*>)(.*?)(</resource>|</ExternalEvidence>)", re.S)


def entity_census(raw: E.Raw) -> dict:
    """How many RAW turns a given escaping policy would alter (what G would see differently)."""
    n = esc_full = esc_min = 0
    chars = Counter()
    delim_hits = 0
    for ss in raw.by_owner.values():
        for s in ss:
            for t in s["turns"]:
                x = t["text"]
                n += 1
                for c in "'\"&<>":
                    chars[c] += c in x
                esc_full += html.escape(x, quote=True) != x
                esc_min += html.escape(x, quote=False) != x
                delim_hits += any(d.lower() in x.lower() for d in DELIMS)
    return dict(turns=n, turns_with_char=dict(chars), altered_by_html_escape_quote_true=esc_full,
                altered_by_minimal_escape_amp_lt_gt=esc_min, altered_by_verbatim=0,
                turns_containing_a_delimiter=delim_hits,
                share_altered_full=round(esc_full / n, 3), share_altered_minimal=round(esc_min / n, 4))


def _split(row):
    m = row["model_input"]["messages"]
    return m


def check_family(rows: list[dict], prefixes: dict, raw: E.Raw, g0e: dict, *, g0e_off: dict | None = None,
                 old_renderer_id: str | None = None) -> dict:
    """rows: every request of one experimental family (all arms, all prefixes)."""
    by_prefix = defaultdict(dict)
    for r in rows:
        by_prefix[r["prefix_id"]][r["condition"]] = r
    per_row, framings, renderer_ids = [], defaultdict(set), set()
    idents = Counter()
    for pid, arms in sorted(by_prefix.items()):
        pre = prefixes[pid]
        off = arms.get("OFF")
        off_m = off["model_input"]["messages"] if off else None
        for cond, r in sorted(arms.items()):
            prob, note = [], {}
            m = r["model_input"]["messages"]
            renderer_ids.add(r["renderer_id"])
            idents[(r["g_id"], r["decode_id"], r["step2_id"])] += 1
            conv_len = len(pre["turns"])
            inserted = m[1:len(m) - conv_len]
            if cond == "OFF":
                if inserted:
                    prob.append("RA3_off_has_block")
                if g0e_off is not None and pid in g0e_off and m != g0e_off[pid]:
                    prob.append("RA7_off_differs_from_G0e_off")
            else:
                if len(inserted) != 1:
                    prob.append("RA2_not_one_inserted_message")
                else:
                    blocks = BLOCK.findall(inserted[0]["content"])
                    if len(blocks) != 1:
                        prob.append(f"RA2_blocks:{len(blocks)}")
                    else:
                        open_tag, payload, close_tag = blocks[0]
                        if any(d.lower() in payload.lower() for d in DELIMS):
                            prob.append("RA2_delimiter_inside_payload")
                        src = E.identify_raw_session(payload, raw, pre["owner_id"])
                        if src is None:
                            prob.append("RA1_payload_not_a_verbatim_owner_session")
                        else:
                            sess = raw.sessions[(pre["owner_id"], src["session_id"])]
                            verbatim = all(f"{t['role']}: {t['text']}" in payload for t in sess["turns"] if t["text"])
                            ent = len(ENTITY.findall(payload))
                            note.update(source_session=src["session_id"], source_rank=src["rank"],
                                        payload_mode="verbatim" if verbatim else "html_escaped", entities=ent)
                            if not src["rank"] < pre["cutoff_rank"]:
                                prob.append("RA6_source_not_strictly_past")
                        frame = inserted[0]["content"].replace(payload, "<PAYLOAD>")
                        frame = re.sub(r"\[MS; reported [0-9-]+\]", "[MS; reported <DATE>]", frame)
                        framings[cond].add(frame)
                if off_m is not None and [x for x in m if x not in inserted] != off_m:
                    prob.append("RA3_not_single_factor_vs_OFF")
            q = E.check_pp1_request(r, pre, raw, g0e, off_m if cond != "OFF" else None)
            leak = [p for p in q.get("problems", []) if p.startswith(("Q5", "Q6", "Q7", "Q8"))]
            prob += [f"RA6:{p}" for p in leak]
            per_row.append(dict(prefix_id=pid[:12], condition=cond, renderer_id=r["renderer_id"], problems=prob, **note))
    all_frames = set().union(*framings.values()) if framings else set()
    fam = dict(
        rows=len(rows), prefixes=len(by_prefix), conditions=sorted({r["condition"] for r in rows}),
        renderer_ids=sorted(renderer_ids), one_renderer=len(renderer_ids) == 1,
        identity_triples=len(idents), same_g_decode_step2=len(idents) == 1,
        framing_variants=len(all_frames), same_framing_across_arms=len(all_frames) <= 1,
        payload_modes=dict(Counter(x.get("payload_mode") for x in per_row if x.get("payload_mode"))),
        entities_total=sum(x.get("entities", 0) for x in per_row),
        renderer_changed_vs_old=(old_renderer_id is not None and renderer_ids != {old_renderer_id}),
        rows_with_problems=sum(bool(x["problems"]) for x in per_row))
    verdict = dict(
        RA1="DECISION_NEEDED" if fam["payload_modes"].get("html_escaped") else "PASS",
        RA2="PASS" if not any(p.startswith("RA2") for x in per_row for p in x["problems"]) else "FAIL",
        RA3="PASS" if fam["same_framing_across_arms"] and not any(p.startswith("RA3") for x in per_row for p in x["problems"])
        else "FAIL",
        RA4="SEPARATE_STEP", RA5="PASS" if fam["one_renderer"] and fam["same_g_decode_step2"] else "FAIL",
        RA6="PASS" if not any(p.startswith("RA6") for x in per_row for p in x["problems"]) else "FAIL",
        RA7="PASS" if not any(p.startswith("RA7") for x in per_row for p in x["problems"]) else "FAIL")
    return dict(family=fam, verdict=verdict, rows=per_row)


PLAN = [
    dict(id="RA1", check="HTML 实体", how="逐个资源块把载荷与 RAW 会话逐轮比对：verbatim / html_escaped / mismatch；统计 G 可见实体数",
         pass_if="研究者决定的转义策略被一致执行（推荐：verbatim + 边界检查；最少也只转义 & < >）",
         why="当前 html.escape 改变了 56% 的 RAW 轮次（撇号变 &#x27;），这是 G 实际看到的文本"),
    dict(id="RA2", check="来源边界", how="每个资源臂恰好一个证据块；载荷中不得出现任何分隔符（<resource、</Notes、<ExternalEvidence 等）",
         pass_if="0 例；若 RAW 中出现分隔符，候选必须有确定的中和规则并登记",
         why="去掉转义后，需要另一种方式保证资料不能伪造块边界"),
    dict(id="RA3", check="单因素", how="资源臂去掉插入块后与同前缀 OFF 字节相同；DP 与 RET 的框架（前言、标签、属性）完全相同，"
         "只允许载荷（选中的会话）不同", pass_if="全部相同",
         why="E1 renderer 的 type=\"MS-RAW-direct\" 若只出现在 DP，会成为第二个因素"),
    dict(id="RA4", check="原生 token", how="用 G0e 的 tokenizer 文件（不加载权重）对全部请求重新套 chat template 并分词，逐 token 比对",
         pass_if="100% 一致；输入 + 320 ≤ 16,384", why="请求身份最终以 input_ids 为准"),
    dict(id="RA5", check="请求身份", how="同一实验族只有一个 renderer_id；g_id / decode / step2 不变；渲染行为变化必须产生新的 "
         "renderer_id 与新的请求 id，不迁移旧结果", pass_if="满足", why="防止新旧请求混用"),
    dict(id="RA6", check="泄露", how="8-gram 未来文本 / 其他 owner / 元数据（哈希、记录 id、会话 id、字段名、条件名）扫描",
         pass_if="0", why="与 #18/#19 回执同一规则"),
    dict(id="RA7", check="OFF 复用", how="OFF 请求与 G0e OFF 字节相同", pass_if="相同则 PP1 的 OFF 结论框架不受 renderer 变更影响",
         why="OFF 不含资源块，统一 renderer 不应改变它"),
]
