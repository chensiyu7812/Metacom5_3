"""Screening label report (audit side): what the curators actually labelled and how long it took.

Input = verified curator final exports + the audit maps written when the packages were built (case id -> prefix id,
owner).  Output = the numbers the researcher asked for: S1/S2/S0/S7 counts, owner groups with any S1, whether an S1
needs several sessions combined, unclear shares, real reading/labelling time, and history-panel use.  Labels are read
as submitted; nothing here can change a label.
"""
from __future__ import annotations

from collections import Counter, defaultdict

from metacom_pm.rl1v3.review import pp1_tool as T


def _q(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(q * len(xs)))] if xs else None


def screen_report(exports: dict[str, dict], audit_maps: dict[str, dict], group_of: dict[str, str],
                  issued: dict[str, dict] | None = None) -> dict:
    rows, timing, curators = [], [], {}
    for cur, exp in sorted(exports.items()):
        v = T.verify_export(exp, issued)
        if not v["ok"]:
            raise ValueError(f"{cur}: export does not verify: {v['error']}")
        if not all(s["locked"] for s in exp["stages"].values()):
            raise ValueError(f"{cur}: screening stage not locked")
        amap = audit_maps[cur]
        mins = []
        for key, st in v["items"].items():
            if not key.startswith("S:") or st.get("status") != "locked":
                continue
            cid = key[2:]
            a = st["answer"]
            form = v["view"]["items"][key]["form"]
            ui = v["ui"].get(key, {})
            m = st.get("view_ms", 0) / 60000
            mins.append(m)
            rows.append(dict(curator=cur, case_id=cid, prefix_id=amap[cid]["case_key"], owner_id=amap[cid]["owner_key"],
                             group=group_of.get(amap[cid]["owner_key"], amap[cid]["owner_key"]),
                             need="S7" if form == "S7" else a.get("need"), s7_anomaly=a.get("s7_confirm") == "anomaly",
                             sessions_needed=a.get("sessions_needed"), risk=a.get("risk", []),
                             spans=Counter(x["role"] for x in a.get("spans", [])), minutes=round(m, 2),
                             history_opened=bool(ui.get("history_open")), history_searched=bool(ui.get("history_search"))))
        curators[cur] = dict(items=len(mins), hours=round(sum(mins) / 60, 2), median_min=_q(mins, 0.5),
                             p90_min=_q(mins, 0.9), head=exp["head"])
        timing += mins
    need = Counter(r["need"] for r in rows)
    s1 = [r for r in rows if r["need"] == "S1"]
    per_group = defaultdict(Counter)
    for r in rows:
        per_group[r["group"]][r["need"]] += 1
    hist = [r for r in rows if r["need"] != "S7"]
    return dict(
        items=len(rows), counts={k: need.get(k, 0) for k in ("S1", "S2", "S0", "unclear", "S7")},
        unclear_share=round(need.get("unclear", 0) / max(1, len(hist)), 3),
        s7_anomalies=sum(r["s7_anomaly"] for r in rows),
        groups_total=len(per_group), groups_with_s1=sum(1 for g in per_group.values() if g["S1"] > 0),
        s1_per_group=dict(sorted((g, c["S1"]) for g, c in per_group.items())),
        s1_sessions_needed=dict(Counter(r["sessions_needed"] for r in s1)),
        s1_multi_session_share=round(sum(r["sessions_needed"] == "multiple" for r in s1) / max(1, len(s1)), 3),
        s1_without_required_span=sum(r["spans"].get("required", 0) == 0 for r in s1),
        time=dict(total_hours=round(sum(timing) / 60, 2), median_min=_q(timing, 0.5), p90_min=_q(timing, 0.9)),
        history_use=dict(opened_share=round(sum(r["history_opened"] for r in hist) / max(1, len(hist)), 3),
                         searched_share=round(sum(r["history_searched"] for r in hist) / max(1, len(hist)), 3)),
        curators=curators, rows=rows,
        note="标签按提交原样统计；本报告不改变任何标签，也不读取任何回复或模型结果")
