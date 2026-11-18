#!/usr/bin/env python
"""WS-B V3.2.1 admission preparation (CPU only; no Generator, GPU, writer, Judge, training or paid API).

  receipt    three-axis WS-B receipt for PR #18 (needs pr18_receipt/MECHANICAL_CHECK.json + TOKENIZE_CHECK.json)
  screen     90-item initial screen from the frozen 162 draw + expansion rule
  pp1        QH backgrounds (complete as-of RAW) for the 8 PP1 prefixes + PP1 protocol
  stats      17-group precision / NI / serious-error tables
  protocol   V3.2.1 protocol candidate (frozen sha), embedding review spec v2, stats, screen, PP1
  gates      G-ENG / PP1 / FC-MS / FC-MP / FC-ME / FC-RS / G-RWD
  testsdiff  per-test-id comparison of whole-tests-dir junit runs (base vs head)

Outputs: outputs/pm_rl1/v3/V321_WSB/<step>/
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))
sys.path.insert(0, str(PROJECT / "scripts/rl1v3"))

from metacom_pm.rl1v3.io import build_manifest, file_sha256, object_sha256, write_json_once  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OUT = V3 / "V321_WSB"
RQ1Q = V3 / "V32_WSB_RQ1Q"
ELIG = V3 / "V32_WSB_P0P2/p2/ELIGIBILITY_54.json"
DRAW = RQ1Q / "coverage/SCREENING_DRAW.json"
CENSUS_SUMMARY = V3 / "B0/census_summary.json"
RECEIPT_DIR = OUT / "pr18_receipt"


def gh_state(n: int) -> dict:
    r = subprocess.run(["gh", "api", f"repos/chensiyu7812/Metacom5_3/pulls/{n}", "--jq",
                        "{state: .state, draft: .draft, merged_at: .merged_at, head: .head.sha, base: .base.ref}"],
                       cwd=REPO, capture_output=True, text=True)
    if r.returncode != 0:
        raise SystemExit(f"gh api failed for PR #{n}: {r.stderr.strip()[:200]}")
    d = json.loads(r.stdout)
    return dict(d, state="MERGED" if d["merged_at"] else d["state"].upper())


def manifest(step: str, inputs: dict, outputs: list[Path]):
    code = [Path(__file__), PROJECT / "src/metacom_pm/rl1v3/evaluate/resource_effect_v321.py",
            PROJECT / "src/metacom_pm/rl1v3/asof/e1_receipt.py", PROJECT / "scripts/rl1v3/V321_wsb_pr18_receipt.py"]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    man = build_manifest(task=f"V321_wsb_{step}", root=PROJECT, inputs=inputs, code=code, code_sha=head,
                         outputs=outputs)
    write_json_once(OUT / step / "MANIFEST.json", man)


# ------------------------------------------------------------------ receipt
R1_R5 = [
    dict(id="R1", confirmed=True, where="asof/binding.py frontier_for -> FrontierEntry.source_id",
         finding="binding identity depends on registry source_id whose hash covers the whole-file raw_sha256",
         disposition="accept; adopt the session-local source_sha256 of A's spec as the frontier identity in a "
                     "binding v2 (old bindings kept as audit map); needs A/B sign-off before use",
         blocks=["G-RWD"], not_blocking=["G-ENG", "PP1", "FC-MS"]),
    dict(id="R2", confirmed=True, where="env/research_v32.py BoundEpisode.__init__",
         finding="constructor checks six env identity fields and prefix id/context only; AB.validate is not called",
         disposition="accept; constructor must call the full validation and bind the actual snapshot/port",
         blocks=["G-RWD"], not_blocking=["G-ENG", "PP1", "FC-MS"]),
    dict(id="R3", confirmed=True, where="env/research_v32.py try_step(STOP)",
         finding="STOP returns the unchanged state (done stays False), so a later GET succeeds",
         disposition="accept; STOP must set done and later GETs return typed after_stop; real STOP->GET test",
         blocks=["G-RWD"], not_blocking=["G-ENG", "PP1", "FC-MS"]),
    dict(id="R4", confirmed=True, where="env/research_v32.py ReplayCache.put/get",
         finding="stored value carries added metadata so an identical retry raises; get returns the internal dict "
                 "and the stored copy is shallow (caller aliases can mutate it)",
         disposition="accept; idempotent identical put, deep-frozen copies on put and get",
         blocks=["G-RWD"], not_blocking=["G-ENG", "PP1", "FC-MS"]),
    dict(id="R5", confirmed=True, where="asof/wsa_adapter.py HEAD map",
         finding="RELATION records raise KeyError; the 8 PR #18 bundles contain only MS_RAW/MP/ME so this receipt "
                 "is unaffected",
         disposition="accept; carry RELATION/UPDATE with target, known/ready and validity; unapproved relations "
                     "never change the fact projection (exchange format, not C0)",
         blocks=["G-RWD", "any future correction-chain receipt"], not_blocking=["G-ENG", "PP1", "FC-MS"]),
]


def step_receipt(_):
    from metacom_pm.rl1v3.asof import e1_receipt as E
    import V321_wsb_pr18_receipt as S
    mech = json.loads((RECEIPT_DIR / "MECHANICAL_CHECK.json").read_text())
    tok = json.loads((RECEIPT_DIR / "TOKENIZE_CHECK.json").read_text())
    sem = S.bundle_jsonl("cpu_v3/SEMANTIC_CANDIDATES.jsonl")
    disp = S.bundle_jsonl("SEMANTIC_REVIEW_DISPOSITIONS.jsonl")
    snap_ids = set()
    for b in S.bundle_jsonl("cpu_v3/BINDINGS.jsonl"):
        s = S.bundle_json("cpu_v3/" + b["snapshot_past"])
        snap_ids |= {v["record"]["record_id"] for v in s["views"] if v["record"]["kind"] != "MS_RAW"}
    sem_ids = {x["record"]["record_id"] for x in sem}
    counts = dict(candidates=len(sem), kinds=dict(Counter(x["record"]["kind"] for x in sem)),
                  dispositions=dict(Counter(x["candidate_disposition"] for x in disp)),
                  human_status=dict(Counter(x["human_status"] for x in disp)),
                  runtime=dict(Counter(x["runtime_disposition"] for x in disp)),
                  approved=sum(bool(x["approved"]) for x in disp),
                  ids_equal_snapshot_semantic_records=sem_ids == snap_ids == {x["record_id"] for x in disp})
    mech_pass = (mech["prefixes_passed"] == 8 and not mech["hash_vectors"]["problems"]
                 and mech["projection"]["passed"] == mech["projection"]["previewed"] == 63
                 and mech["b_sidecar_adapter"].get("passed") is True
                 and not mech["dual_horizon_readings"]["differ"] and not mech["isolation"]["case_family_owner_overlap"]
                 and tok["any_variant_matches"] == tok["previews"] == 63)
    notes = [
        dict(id="N1", kind="presentation", text="MS-RAW / MP / ME / CASE 证据块经 html.escape（' → &#x27;，\" → &quot;），"
             "对话本身不转义；G0e renderer（PR #10 request_packet.py / v0.py）同样转义。不是泄露；是需明确决定的展示属性",
             affects=["FC-MS", "FC-MP", "FC-ME", "FC-RS", "PP1（RET-MS 同样转义）"]),
        dict(id="N2", kind="single-factor", text="PR #18 E1 renderer（renderer-e1-direct:323c2054…，前言 'Optional historical "
             "evidence…'）与 PR #10 G0e renderer（前言 'Notes — quoted external data…'）不同；若 DP-MS 用 E1、RET-MS 用旧输入，"
             "则比较同时改变选材与呈现两个因素", affects=["FC-MS"]),
        dict(id="N3", kind="framing", text="RS 证据块沿用 'Optional historical evidence' 前言与历史证据措辞；"
             "RS 不是个人历史，属于呈现语义问题，交 RS 适用性审核", affects=["FC-RS"]),
        dict(id="N4", kind="family", text="A 的 family closure 是 as-of 的（当前及更早会话 + owner），p13 截至 rank 12 "
             "不含 esconv_1198；B 的聚类仍按全轨迹合并 p13+p18（更严格）", affects=["统计聚类（不变）"]),
        dict(id="N5", kind="treatment-visible", text="证据标签 type=\"MS-RAW-direct\" 等臂名对 G 可见（审阅者不可见）；"
             "属于处理的一部分，须在同一实验族内保持固定", affects=["FC-*"]),
    ]
    receipt = dict(
        protocol=E.PROTOCOL, reviewer="WS-B", pr=18, head=S.PR18_SHA, base=S.PR18_BASE,
        independence="B 自写 canonical 编码、从公开 sanitized artifact 直接解析 RAW、用 B0 census 与 B6e 选择、"
                     "用 PR #10 G0e.json；未导入或执行任何 A 代码；A 的 589 项测试与参考 checker 未作为证据",
        axes=dict(
            mechanical=dict(verdict="PASS_WITH_NOTES" if mech_pass else "FAIL", scope="来源 / 时点 / owner / family / "
                            "hash / 双 horizon / Generator 可见投影", details=dict(
                                hash_vectors=f"{mech['hash_vectors']['n']}/{mech['hash_vectors']['n']}",
                                own_encoder_equals_stdlib=mech["own_encoder_equals_stdlib_on_snapshots"],
                                prefixes=f"{mech['prefixes_passed']}/8",
                                snapshots_two_horizons="16/16 reproduced; past file == future file; own materialisation "
                                                       "from each ledger == snapshot (X5a)",
                                b_sidecar_adapter=dict(passed=mech["b_sidecar_adapter"].get("passed"),
                                                       cutoffs=mech["b_sidecar_adapter"].get("cutoffs_passed")),
                                projection=f"{mech['projection']['passed']}/{mech['projection']['previewed']} previews; "
                                           f"tokens {mech['projection']['token_range']}",
                                retokenisation=f"{tok['any_variant_matches']}/{tok['previews']} input_ids reproduced "
                                               f"(transformers {tok['transformers']}, tokenizer files = G0e.json)",
                                dual_horizon_readings=f"{mech['dual_horizon_readings']['pairs']} pairs identical",
                                isolation=mech["isolation"]), notes=notes),
            human_semantic=dict(verdict="NOT_SIGNED_BY_B", reason="B 不做也不代签人工语义、当前适用与许可",
                                a_reported_counts_mechanically_consistent=counts,
                                pending=["64 条 MP/ME 候选人工审核（0 批准）", "8 条 SUM 不可用", "EvoEmo 上游许可",
                                         "2 张 METHOD 与 CASE 的许可、适用、关联"]),
            research_qualification=dict(verdict="NOT_QUALIFIED_YET",
                                        reason="机械通过不推出研究资格；正式 DP 选材、评价协议与 G 正确使用均待定",
                                        usable_now_for=["PP1 的 QH 背景来源（全部合法 RAW）",
                                                        "FC-MS 的 DP-MS 候选（8 个前缀；正式样本需同规则导出）"],
                                        not_usable_for=["任何效果结论", "MP/ME/RS 正式比较", "奖励"])),
        r1_r5=R1_R5,
        gate_effect="G-ENG E3：PR #18 的 63 个预览通过；PP1 的 16 个旧请求包仍需导出后用同一检查器核验。"
                    "FC-MS M2：8 个前缀 PASS，正式样本前缀待导出。FC-MP/ME/RS：语义/许可 BLOCKED 不变",
    )
    pp1 = OUT / "pp1_requests_preliminary"
    if (pp1 / "PP1_REQUESTS_CHECK.json").exists():
        a = json.loads((pp1 / "PP1_REQUESTS_CHECK.json").read_text())
        t = json.loads((pp1 / "PP1_TOKENIZE_CHECK.json").read_text())
        receipt["pp1_requests_preliminary"] = dict(
            ws_a_commit=a["ws_a_commit"], file_sha256=a["file_sha256_git"], passed=f"{a['passed']}/{a['requests']}",
            retokenised=f"{t['matched']}/{t['requests']}", renderer_ids=a["renderer_ids"], conditions=a["conditions"],
            html_escaped_ret_ms=a["html_escaped"], ret_ms_sources=a["ret_ms_sources"],
            status="PRELIMINARY: WS-A 尚未就该提交开 PR；在其 Draft 固定 HEAD 上复跑后才作为正式回执")
    write_json_once(RECEIPT_DIR / "WSB_RECEIPT_PR18.json", receipt)
    print(json.dumps(dict(mechanical=receipt["axes"]["mechanical"]["verdict"], counts=counts), ensure_ascii=False))


# ------------------------------------------------------------------ screen / stats / pp1 / protocol / gates
def _groups():
    from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
    cs = json.loads(CENSUS_SUMMARY.read_text())
    fam = [sorted({h["owner_id"] for h in x["holders"]}) for x in cs["shared_families"]]
    g = Q.owner_groups([f"p{i}" for i in range(1, 19)], fam)
    return {o: name for name, os in g.items() for o in os}


def step_screen(_):
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    draw = json.loads(DRAW.read_text())
    s = V.initial_screen(draw)
    gof = _groups()
    dry = V.expansion_next(draw, {r["prefix_id"] for r in s["rows"]}, {}, gof)
    out = OUT / "screen"
    write_json_once(out / "INITIAL_SCREEN_90.json", dict(s, expansion_rule=V.EXPANSION_RULE,
                    labels_collected=0, owner_groups=len(set(gof.values())),
                    expansion_dry_run_with_no_labels=dict(groups_in_deficit=len(dry["deficit"]),
                                                          next_items=len([x for x in dry["next"] if x["prefix_id"]]))))
    manifest("screen", {"draw": DRAW, "census_summary": CENSUS_SUMMARY}, [out / "INITIAL_SCREEN_90.json"])
    print(json.dumps(dict(n=len(s["rows"]), counts=s["counts"], owners=s["owners"], sha=s["screen_sha256"])))


def step_stats(_):
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    out = OUT / "stats"
    st = V.stats_v321(17)
    write_json_once(out / "STATS_V321.json", st)
    manifest("stats", {}, [out / "STATS_V321.json"])
    print(json.dumps(dict(anchor=st["anchor"], anchor_m4=st["anchor_m4"], ni=st["ni_required_pairs_per_group"],
                          se=st["serious_error"]["replies_needed_upper_below_0_05"],
                          harm=st["serious_error"]["paired_harm_detectable_arm_only_errors"])))


def step_pp1(_):
    from metacom_pm.rl1v3.asof import e1_receipt as E
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    import V321_wsb_pr18_receipt as S
    raw = E.Raw(json.loads(S.ARTIFACT.read_text()))
    handoff = {r["prefix_id"]: r for r in S.bundle_json("cpu_v3/QH_SOURCE_HANDOFF.json")["rows"]}
    elig = json.loads(ELIG.read_text())["rows"]
    calls = V.pp1_calls(elig)
    out = OUT / "pp1"
    bgs, index = {}, []
    for b in S.bundle_jsonl("cpu_v3/BINDINGS.jsonl"):
        pre = S.bundle_json("cpu_v3/" + b["prefix_path"])
        legal = raw.legal_past(pre["owner_id"], pre["cutoff_rank"], pre["timestamp"])
        snap = S.bundle_json("cpu_v3/" + b["snapshot_past"])
        raw_by_session = {r["session_id"]: r["record_id"] for r in snap["ledger_prefix"] if r["kind"] == "MS_RAW"}
        same = [raw_by_session.get(s["session_id"]) for s in legal] == handoff[b["prefix_id"]]["raw_record_ids"]
        sessions = [dict(rank=s["rank"], date=s["date"], turns=[dict(role=t["role"], text=t["text"])
                                                                   for t in s["turns"]]) for s in legal]
        bg = dict(prefix_id=b["prefix_id"], kind="QH background: complete as-of RAW, arm-independent",
                  index=[dict(rank=s["rank"], date=s["date"], turns=len(s["turns"])) for s in sessions],
                  sessions=sessions, words=sum(len(t["text"].split()) for s in sessions for t in s["turns"]),
                  equals_pr18_qh_source_handoff=same)
        bg["background_sha256"] = object_sha256({k: v for k, v in bg.items() if k != "equals_pr18_qh_source_handoff"})
        bgs[b["prefix_id"]] = bg
        index.append(dict(prefix_id=b["prefix_id"], owner_id=pre["owner_id"], sessions=len(sessions), words=bg["words"],
                          background_sha256=bg["background_sha256"], equals_pr18_qh_source_handoff=same))
    if {c["prefix_id"] for c in calls} != set(bgs):
        raise SystemExit("PP1 ELIGIBLE prefixes differ from the PR #18 bound prefixes")
    write_json_once(out / "QH_BACKGROUNDS.json", dict(rule="all legal past sessions (rank < cutoff, date <= prefix "
                    "timestamp) from the public sanitized artifact; no excerpt, role or ranking; identical for OFF and "
                    "RET-MS; frozen before any generation", rows=list(bgs.values())))
    spec = V.pp1_protocol(elig, qh_backgrounds=dict(file="QH_BACKGROUNDS.json", index=index,
                                                    sha256=object_sha256(index)), words=[x["words"] for x in index])
    write_json_once(out / "PP1_PROTOCOL.json", V.freeze(dict(pp1=spec)))
    manifest("pp1", {"eligibility": ELIG}, [out / "QH_BACKGROUNDS.json", out / "PP1_PROTOCOL.json"])
    print(json.dumps(dict(calls=len(calls), backgrounds=len(bgs), all_equal=all(x["equals_pr18_qh_source_handoff"]
                     for x in index), words=[x["words"] for x in index], cost=spec["cost"]), ensure_ascii=False))


def step_protocol(_):
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    screen = json.loads((OUT / "screen/INITIAL_SCREEN_90.json").read_text())
    pp1 = json.loads((OUT / "pp1/PP1_PROTOCOL.json").read_text())
    spec = dict(revisions=V.REVISIONS, review=V.review_spec_v2(), audit_ledger=V.AUDIT_LEDGER_RULE,
                stats=V.stats_v321(17), primary=dict(
                    channel="QH net preference vs OFF, equal weight over 17 owner groups, exact sign-flip + owner-group "
                            "bootstrap CI", guard="Q0 net preference vs OFF (non-inferiority margin: discussion candidate)",
                    constraint="F serious-error rate per arm with exact upper bound; harm test vs OFF",
                    margins_status="candidates for researcher decision, not gates", strata=["S1", "S2", "S0", "S7"]),
                screen=dict(file="screen/INITIAL_SCREEN_90.json", sha256=screen["screen_sha256"],
                            expansion_rule=V.EXPANSION_RULE),
                pp1=dict(file="pp1/PP1_PROTOCOL.json", sha256=pp1["protocol_sha256"]),
                missing=dict(uncertain="bounded (all-loss / all-win), never imputed", technical_failure="pending, "
                             "reported per arm, never zero", rater_missing="pair excluded from the point estimate and "
                             "covered by the bounds"))
    f = V.freeze(spec)
    write_json_once(OUT / "protocol/PROTOCOL_V321_CANDIDATE.json", f)
    manifest("protocol", {"screen": OUT / "screen/INITIAL_SCREEN_90.json", "pp1": OUT / "pp1/PP1_PROTOCOL.json"},
             [OUT / "protocol/PROTOCOL_V321_CANDIDATE.json"])
    print(f["protocol_sha256"])


def step_gates(_):
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    rec = json.loads((RECEIPT_DIR / "WSB_RECEIPT_PR18.json").read_text())
    prs = {str(n): gh_state(n) for n in (10, 15, 16, 17, 18)}
    pp1_dir = OUT / "pp1_requests_preliminary"
    pp1_req_pass = False
    if (pp1_dir / "PP1_REQUESTS_CHECK.json").exists() and (pp1_dir / "PP1_TOKENIZE_CHECK.json").exists():
        a = json.loads((pp1_dir / "PP1_REQUESTS_CHECK.json").read_text())
        t = json.loads((pp1_dir / "PP1_TOKENIZE_CHECK.json").read_text())
        pp1_req_pass = a["passed"] == a["requests"] == 16 and t["matched"] == t["requests"] == 16
    facts = dict(
        g0e_identity=prs["10"].get("state") == "MERGED", a0_measured=False,
        requests_checked=False, requests_pending=pp1_req_pass,
        requests_reason=("PP1 的 16 个请求包在 WS-A WIP 提交 4ac9ab3d 上初步通过 B 检查（16/16，重分词 16/16）；"
                         "须在 A 的 Draft PR 固定 HEAD 上用同一检查器复跑") if pp1_req_pass else
                        "PP1 的 16 个 G0e 请求包尚未导出或未经 B 检查",
        output_policy=True, gpu_auth=False,
        pp1_qh_backgrounds=(OUT / "pp1/QH_BACKGROUNDS.json").exists(), pp1_screen_labels=False, raters=False,
        pp1_protocol_approved=False, instrument=False,
        formal_protocol=False, screen_labels=False, formal_qh=False, pp1_done=False, single_renderer=False,
        dp_ms_formal=False, ret_ms_asof=False, license_scope=False,
        mp_semantic=False, me_semantic=False, rs_reviewed=False,
        fc_results=False, j1_validated=False, decode_cap=False, r1_r5_fixed=False)
    gates = V.gates_v321(facts)
    out = OUT / "gates"
    write_json_once(out / "GATES_V321.json", dict(protocol=V.PROTOCOL, status=V.STATUS, prs=prs, facts=facts,
                    pr18_mechanical=rec["axes"]["mechanical"]["verdict"], gates=gates))
    manifest("gates", {"receipt": RECEIPT_DIR / "WSB_RECEIPT_PR18.json"}, [out / "GATES_V321.json"])
    for g in gates:
        print(g["gate"], g["state"], [(i["id"], i["state"]) for i in g["items"]])


def step_admission(_):
    """Cost numbers for the admission report: PP1 (from its protocol), the 90 screen, FC-MS scenarios."""
    from metacom_pm.rl1v3.asof import e1_receipt as E
    from metacom_pm.rl1v3.evaluate import resource_effect_v321 as V
    import V321_wsb_pr18_receipt as S
    raw = E.Raw(json.loads(S.ARTIFACT.read_text()))
    census = {c["prefix_id"]: c for c in map(json.loads, S.CENSUS.read_text().splitlines())}
    screen = json.loads((OUT / "screen/INITIAL_SCREEN_90.json").read_text())
    words = []
    for r in screen["rows"]:
        if r["stratum"] == "S7_rank0":                    # rank-0 cuts: no personal history (not in B0 census)
            words.append(0)
            continue
        c = census[r["prefix_id"]]
        words.append(sum(len(t["text"].split()) for s in raw.legal_past(c["owner_id"], c["cutoff_rank"], c["timestamp"])
                         for t in s["turns"]))
    pp1 = json.loads((OUT / "pp1/PP1_PROTOCOL.json").read_text())["pp1"]
    with_hist = sorted(w for w in words if w)
    med = with_hist[len(with_hist) // 2]
    res = dict(pp1_cost=pp1["cost"], screen90=V.screen_cost(words), screen162_upper=V.screen_cost(words + words[:72]),
               fc_ms=[V.fc_ms_cost(n, med) for n in (34, 51, 68)],
               note="FC-MS rows: 17 groups x m = 2 / 3 / 4 prefixes, 3 arms (OFF, DP-MS, RET-MS), all 3 pairs; "
                    "history read once per person per prefix at 250 wpm (upper bound); screen162_upper "
                    "approximates the remaining 72 by the first 72 items' history lengths")
    write_json_once(OUT / "admission/ADMISSION_NUMBERS.json", res)
    manifest("admission", {"screen": OUT / "screen/INITIAL_SCREEN_90.json", "pp1": OUT / "pp1/PP1_PROTOCOL.json"},
             [OUT / "admission/ADMISSION_NUMBERS.json"])
    print(json.dumps(dict(pp1=res["pp1_cost"]["human_minutes"], gpu=res["pp1_cost"]["gpu_seconds"],
                          screen90=res["screen90"], screen162=res["screen162_upper"], fc_ms=res["fc_ms"]),
                     ensure_ascii=False))


def _junit(p: Path) -> dict:
    res = {}
    for tc in ET.parse(p).getroot().iter("testcase"):
        tid = f"{tc.get('classname')}::{tc.get('name')}"
        kind = "passed"
        for ch in tc:
            if ch.tag in ("failure", "error"):
                kind = "failed"
            elif ch.tag == "skipped":
                kind = "skipped"
        res[tid] = kind
    return res


def step_testsdiff(a):
    runs = {}
    for spec in a.runs:
        label, path = spec.split("=", 1)
        runs[label] = _junit(Path(path))
    labels = list(runs)
    base, head = labels[0], labels[1]
    fb = {t for t, k in runs[base].items() if k == "failed"}
    fh = {t for t, k in runs[head].items() if k == "failed"}
    only_head = sorted(t for t in runs[head] if t not in runs[base])
    res = dict(runs={k: dict(Counter(v.values())) for k, v in runs.items()},
               failed_both=sorted(fb & fh), failed_only_base=sorted(fb - fh), failed_only_head=sorted(fh - fb),
               tests_only_in_head=len(only_head), tests_only_in_head_failed=sorted(t for t in only_head
                                                                                    if runs[head][t] == "failed"),
               tests_only_in_base=len([t for t in runs[base] if t not in runs[head]]),
               status_changes=sorted(dict(test=t, base=runs[base][t], head=runs[head][t]) for t in runs[base]
                                     if t in runs[head] and runs[base][t] != runs[head][t]),
               failing_files=dict(Counter(t.split("::")[0] for t in fh)))
    for extra in labels[2:]:
        fe = {t for t, k in runs[extra].items() if k == "failed"}
        res[f"vs_{extra}"] = dict(failed=len(fe), same_failed_set_as_head=fe == fh,
                                  only_extra=sorted(fe - fh), only_head=sorted(fh - fe))
    out = OUT / "testsdiff"
    write_json_once(out / "ALLTESTS_DIFF.json", res)
    print(json.dumps({k: (v if not isinstance(v, list) else len(v)) for k, v in res.items()
                      if k not in ("failing_files",)}, indent=1, default=str))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("receipt", "screen", "stats", "pp1", "protocol", "gates", "admission",
                                     "testsdiff"))
    ap.add_argument("--runs", nargs="*", default=[], help="label=junit.xml (base first, head second)")
    a = ap.parse_args()
    dict(receipt=step_receipt, screen=step_screen, stats=step_stats, pp1=step_pp1, protocol=step_protocol,
         gates=step_gates, admission=step_admission, testsdiff=step_testsdiff)[a.step](a)
