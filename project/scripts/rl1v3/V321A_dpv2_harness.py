#!/usr/bin/env python3
"""WS-B independent acceptance of WS-A's human DP v2 (PR #26), CPU only, simulated material only.

Runs A's code from a detached checkout (--wt) and never uses A's own tests or helpers as the oracle: every fixture,
expectation and fault below is B's.  No real selection, no formal sample, no generation.

  python V321A_dpv2_harness.py --wt /opt/.../wt26 --out DIR [--head SHA] [--no-browser]
  python V321A_dpv2_harness.py --raw-check BUNDLE.json --out DIR      (runs with B's own src: RAW correspondence)
"""
from __future__ import annotations

import argparse
import base64
import copy
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve()
B_PROJECT = HERE.parents[2]
RESULTS = []


def ck(sid, name, ok, detail=None, kind="check"):
    RESULTS.append(dict(id=sid, name=name, ok=bool(ok), detail=detail, kind=kind))
    print(("PASS " if ok else "FAIL ") + sid + " " + name + ("" if ok or detail is None else f"  {str(detail)[:200]}"))


def refused(fn, *a, **k):
    try:
        fn(*a, **k)
    except Exception as e:          # AdmissionError, KeyError, ValueError ...: any refusal counts, record its text
        return True, f"{type(e).__name__}: {e}"
    return False, "accepted"


# ------------------------------------------------------------------ B's synthetic fixtures (not A's)
def H(x):
    import hashlib
    return hashlib.sha256(x.encode()).hexdigest()


def fixtures(D, V1, manifest_frozen="2031-01-01T01:00:00+00:00"):
    """Three synthetic prefixes of two synthetic people; pools hold every strictly-past synthetic session."""
    from metacom_pm.rl1v3.io import object_sha256 as osha
    people = {"ownA": 4, "ownB": 3}
    pools, labels, spec = [], [], []
    for owner, n in people.items():
        sessions = []
        for r in range(n):
            refs = [dict(owner_id=owner, session_id=f"{owner}-s{r}", turn_index=k, speaker=sp,
                         exact_quote=f"SIMULATED {owner} session {r} line {k}.") for k, sp in enumerate(("seeker", "supporter"))]
            sessions.append(dict(record_id=f"rec-{owner}-{r}", owner_id=owner, session_id=f"{owner}-s{r}",
                                 family_id=f"fam-{owner}", reported_at=dict(session_rank=r, date=f"2030-0{r + 1}-01"),
                                 known_at=dict(session_rank=r), ready_at=dict(session_rank=r),
                                 text="\n".join(x["speaker"] + ": " + x["exact_quote"] for x in refs), source_refs=refs))
        for cut in ([n] if owner == "ownB" else [n - 1, n]):
            pid = H(f"B-SYNTH|{owner}|{cut}")
            pools.append(dict(owner_id=owner, prefix_id=pid, snapshot_sha=H(f"snap|{pid}"),
                              candidates=[c for c in sessions if c["reported_at"]["session_rank"] < cut],
                              prefix=dict(owner_id=owner, prefix_id=pid, session_id=f"{owner}-cur{cut}", cutoff_rank=cut,
                                          timestamp=f"2030-0{cut + 1}-15", family_id=f"fam-{owner}", ancestor_family_ids=[],
                                          turns=[dict(role="seeker", text=f"SIMULATED current need of {owner} at {cut}.")])))
            labels.append(dict(prefix_id=pid, owner_id=owner, group="G-" + owner, need="S1"))
            spec.append(dict(prefix_id=pid, owner_id=owner, session_id=f"{owner}-cur{cut}", cut_turn=0))
    screening = dict(simulated=False, verified_by="WS-B harness (synthetic, not human)",
                     verification_evidence="B harness synthetic envelope", frozen_at="2031-01-01T00:00:00+00:00",
                     labels=labels, labels_sha256=osha(labels))
    manifest = dict(researcher_confirmed=True, signed_by="SYNTHETIC", evidence="SYNTHETIC", prefixes=spec,
                    prefixes_sha256=osha(spec), frozen_at=manifest_frozen, screening_receipt_sha256=osha(screening))
    bundle = D.wrap_bundle(V1.wrap_pools(pools, osha(manifest), formal=True))
    pids = [p["prefix_id"] for p in pools]
    sel = {pids[0]: "CUR1", pids[1]: "CUR1", pids[2]: "CUR2"}
    roles = dict(sample_identity=bundle["sample_identity"], signed_by="CUR1 (coordinator; synthetic)", evidence="SYNTHETIC",
                 frozen_at="2031-01-01T02:00:00+00:00",
                 people={"R1": "person-researcher", "R2": "person-r2", "CUR1": "person-cur1", "CUR2": "person-cur2"},
                 assignments={p: dict(selector=sel[p], reviewers={ch: ["R1", "R2"] for ch in ("Q0", "QH", "F")}) for p in pids})
    ret = dict(bundle_sha256=bundle["bundle_sha256"],
               rows={e["pool"]["prefix_id"]: dict(pool_sha256=e["pool_sha256"],
                                                  selected_record_id=e["pool"]["candidates"][-1]["record_id"])
                     for e in bundle["rows"]})
    baseline = dict(identity=dict(renderer_id="b-old", g_id="b-g", decode_id="b-decode", step2_id="b-no-plan"),
                    spec=dict(system_prompt="B synthetic system prompt.", decode=dict(max_new_tokens=320)))
    return bundle, roles, ret, baseline, manifest, screening


def draft(D, bundle, i, **kw):
    e = bundle["rows"][i]
    d = dict(protocol=D.PROTOCOL, bundle_sha256=bundle["bundle_sha256"], prefix_id=e["pool"]["prefix_id"],
             pool_sha256=e["pool_sha256"], selector=kw.pop("selector", "CUR1"), current_need="SIMULATED need",
             rationale="SIMULATED reason", declared_at="2031-01-01T03:00:00+00:00", outcomes_not_seen=True,
             rankings_not_seen=True, decision="selected", selected_record_id=e["pool"]["candidates"][0]["record_id"],
             single_session_coverage="full", missing_need="", staleness_issue=False, staleness_detail="",
             stage_issue=False, stage_detail="")
    d.update(kw)
    return d


class Counter:
    def ids(self, messages):
        return [len(m["content"]) for m in messages]


def run_api(wt: Path, out: Path):
    sys.path.insert(0, str(wt / "project/src"))
    from metacom_pm.rl1v3.compile import dp_selection as V1, dp_selection_v2 as D
    from metacom_pm.rl1v3.io import object_sha256 as osha
    tmp = Path(tempfile.mkdtemp(prefix="dpv2_", dir=os.environ.get("TMPDIR")))
    T1, T2, T3, T4 = ("2031-01-01T03:01:00+00:00", "2031-01-01T03:02:00+00:00", "2031-01-01T03:03:00+00:00",
                      "2031-01-01T04:00:00+00:00")

    # ---------------- A: real v1 bundle of #21 (8 PP1 prefixes, 87 sessions) wrapped as v2
    v1 = json.loads((wt / "project/outputs/pm_rl1/v3/runprep_fcms_20261119/cpu_v2/DP_SELECTOR_BUNDLE_8.json").read_text())
    v2 = D.wrap_bundle(v1)
    ok, why = refused(D.validate_bundle, v2)
    ck("A1", "v2 wrap of #21's 8-prefix bundle validates; pools byte-identical to v1; binds v1 SHA",
       not ok and [r["pool_sha256"] for r in v2["rows"]] == [r["pool_sha256"] for r in v1["rows"]]
       and v2["legacy_bundle_sha256"] == v1["bundle_sha256"] and v2["protocol"] == D.PROTOCOL, why if ok else None)
    (out / "v2_bundle_8.json").write_text(json.dumps(v2))
    ck("A2", "v2 bundle holds 87 candidate sessions over 8 prefixes",
       sum(len(r["pool"]["candidates"]) for r in v2["rows"]) == 87 and len(v2["rows"]) == 8)
    html = D.selection_html(v2)
    emb = json.loads(base64.b64decode(re.search(r'atob\("([A-Za-z0-9+/=]+)"\)', html).group(1)).decode())
    keys = set()

    def walk(o):
        if isinstance(o, dict):
            for k, v in o.items():
                keys.add(k)
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)
    walk(emb)
    bad = sorted(k for k in keys if re.search(r"rank|score|retriev|lexical|ret_|outcome|result|reward|judge", k, re.I)
                 and k not in ("session_rank", "cutoff_rank", "source_rank"))
    chrono = all(x["source_rank"] == c["reported_at"]["session_rank"] for r in emb["rows"] for c in r["pool"]["candidates"]
                 for x in c["source_refs"])
    ck("A3", "selector page embeds only the whitelisted pool view (no ranking/score/retrieval/result keys; "
             "source_rank is the session's time order, equal to reported_at.session_rank)",
       not bad and chrono and emb == json.loads(json.dumps(v2)), dict(bad=bad, source_rank_is_time_order=chrono))
    bundle, roles, ret, base, manifest, screening = fixtures(D, V1)

    def rehash(b):
        body = {k: v for k, v in b.items() if k not in {"bundle_sha256", "engineering_ready", "research_qualified", "authorized"}}
        for r in body["rows"]:
            r["pool_sha256"] = osha(r["pool"])
        return dict(body, bundle_sha256=osha(body), engineering_ready=True, research_qualified=False, authorized=False)
    b = copy.deepcopy(bundle)
    fut = copy.deepcopy(b["rows"][0]["pool"]["candidates"][0])
    fut.update(record_id="rec-future", session_id="ownA-future", reported_at=dict(session_rank=9, date="2030-09-01"),
               known_at=dict(session_rank=9), ready_at=dict(session_rank=9))
    for x in fut["source_refs"]:
        x["session_id"] = "ownA-future"
    b["rows"][0]["pool"]["candidates"].append(fut)
    ok, why = refused(D.validate_bundle, rehash(b))
    ck("A4", "rehashed bundle with a future session is refused (as-of rechecked)", ok, why)
    b = copy.deepcopy(bundle)
    b["rows"][0]["pool"]["candidates"][0]["text"] += " (edited)"
    ok, why = refused(D.validate_bundle, rehash(b))
    ck("A5", "rehashed bundle with edited session text is refused (RAW span coverage)", ok, why)
    b = copy.deepcopy(bundle)
    b["rows"][0]["pool"]["candidates"] = b["rows"][0]["pool"]["candidates"][1:]
    ok, why = refused(D.validate_bundle, rehash(b))
    ck("A6", "OBSERVATION: a rehashed bundle that silently drops one legal past session is NOT refused "
             "(completeness is not rechecked against the snapshot)", not ok, why, kind="observation")
    ok, why = refused(D.freeze_choice, v1, draft(D, v1, 0), roles, tmp / "x", now=T1)
    ck("A7", "a v1 bundle cannot be used to freeze a v2 choice", ok and "v2 bundle required" in why, why)

    # ---------------- B: semantic fields
    def fz(i, sub, **kw):
        return refused(D.freeze_choice, bundle, draft(D, bundle, i, **kw), roles, tmp / sub, now=T1)
    ok, why = fz(0, "b1")
    ck("B1", "selected + full coverage + empty missing_need is accepted", not ok, why)
    for sid, name, kw in [
            ("B2", "full coverage with a missing need is refused", dict(missing_need="still missing X")),
            ("B3", "partial coverage without missing_need is refused", dict(single_session_coverage="partial")),
            ("B4", "staleness_issue as the string 'true' is refused (explicit boolean)", dict(staleness_issue="true")),
            ("B5", "staleness_issue=true without detail is refused", dict(staleness_issue=True)),
            ("B6", "stage_issue=true without detail is refused", dict(stage_issue=True)),
            ("B7", "rankings_not_seen=false is refused", dict(rankings_not_seen=False)),
            ("B8", "outcomes_not_seen=false is refused", dict(outcomes_not_seen=False)),
            ("B9", "missing_need=None is refused", dict(missing_need=None)),
            ("B10", "unknown coverage value is refused", dict(single_session_coverage="most")),
            ("B11", "a source outside the lawful pool is refused", dict(selected_record_id="rec-ownB-0"))]:
        ok, why = fz(0, sid.lower(), **kw)
        ck(sid, name, ok, why)
    ok, why = fz(0, "b12", single_session_coverage="none", missing_need="nothing in it covers the need")
    ck("B12", "OBSERVATION: decision=selected with coverage=none is accepted (a chosen session that covers nothing)",
       not ok, why, kind="observation")

    # ---------------- C: none / uncertain
    for sid, name, kw in [
            ("C1", "none_suitable carrying a source is refused", dict(decision="none_suitable", single_session_coverage="none",
                                                                     missing_need="x")),
            ("C2", "none_suitable with coverage=partial is refused", dict(decision="none_suitable", selected_record_id=None,
                                                                          single_session_coverage="partial", missing_need="x")),
            ("C3", "none_suitable without saying what is missing is refused", dict(decision="none_suitable", selected_record_id=None,
                                                                                    single_session_coverage="none"))]:
        ok, why = fz(1, sid.lower(), **kw)
        ck(sid, name, ok, why)

    # ---------------- full path with one uncertain prefix; 4-person roles
    rd = tmp / "receipts"
    recs = {}
    recs[bundle["rows"][0]["pool"]["prefix_id"]] = D.freeze_choice(bundle, draft(D, bundle, 0), roles, rd, now=T1)
    recs[bundle["rows"][1]["pool"]["prefix_id"]] = D.freeze_choice(
        bundle, draft(D, bundle, 1, decision="uncertain", selected_record_id=None, single_session_coverage="none",
                      missing_need="cannot tell whether the plan was carried out"), roles, rd, now=T2)
    recs[bundle["rows"][2]["pool"]["prefix_id"]] = D.freeze_choice(
        bundle, draft(D, bundle, 2, selector="CUR2", single_session_coverage="partial", missing_need="later outcome",
                      stage_issue=True, stage_detail="intended, not done"), roles, rd, now=T3)
    ck("F3", "the fixed 4-person registry (CUR1/CUR2 select; R1/R2 review Q0/QH/F) freezes every prefix", len(recs) == 3)
    rows = D.export_candidates(bundle, recs, roles, ret, base, Counter())
    unc = next(r for r in rows if r["arm"] == "DP-MS" and r["prefix_id"] == bundle["rows"][1]["pool"]["prefix_id"])
    ck("C4", "uncertain stays a pending DP-MS row (no input, status 'uncertain'); not turned into OFF or RET",
       unc["model_input"] is None and unc["material_status"] == "uncertain" and unc["source_sha256"] is None)
    plan = D.bind_plan(bundle, recs, roles, rows, manifest, screening, now=T4)
    ck("C5", "the plan lists the uncertain DP-MS request as material_pending and never as runnable",
       unc["request_id"] in plan["material_pending"] and plan["authorized"] is False and plan["runtime_callable"] is False)
    bad = copy.deepcopy(rows)
    r = next(x for x in bad if x["request_id"] == unc["request_id"])
    rr = next(x for x in bad if x["arm"] == "RET-MS" and x["prefix_id"] == r["prefix_id"])
    for k in ("model_input", "source_sha256", "messages_sha256", "input_ids_sha256", "input_tokens"):
        r[k] = copy.deepcopy(rr[k])
    r["request_id"] = D.request_id(r)
    ok, why = refused(D.bind_plan, bundle, recs, roles, bad, manifest, screening, now=T4)
    ck("C6", "substituting the RET source into the uncertain DP-MS row is refused", ok, why)

    # ---------------- D: real screening provenance and plan binding
    def sample(mut):
        m, s = copy.deepcopy(manifest), copy.deepcopy(screening)
        mut(m, s)
        return refused(D.validate_sample, m, s)
    ok, why = sample(lambda m, s: None)
    ck("D0", "B's synthetic screening envelope (4 label fields) passes A's validate_sample", not ok, why)

    def resha(m, s):
        s["labels_sha256"] = osha(s["labels"])
        m["screening_receipt_sha256"] = osha(s)
    for sid, name, mut in [
            ("D1", "simulated screening is refused", lambda m, s: (s.update(simulated=True), resha(m, s))),
            ("D2", "a label row with an extra field (score) is refused",
             lambda m, s: (s["labels"][0].update(score=0.9), resha(m, s))),
            ("D3", "a label hash that does not match is refused", lambda m, s: s.update(labels_sha256="0" * 64)),
            ("D4", "a formal prefix labelled S7/unclear is refused",
             lambda m, s: (s["labels"][0].update(need="unclear"), resha(m, s))),
            ("D5", "a manifest bound to another screening receipt is refused",
             lambda m, s: m.update(screening_receipt_sha256="0" * 64)),
            ("D6", "a sample frozen before its screening is refused",
             lambda m, s: (s.update(frozen_at="2031-01-02T00:00:00+00:00"), resha(m, s))),
            ("D7", "an unconfirmed sample is refused", lambda m, s: m.update(researcher_confirmed=False))]:
        ok, why = sample(mut)
        ck(sid, name, ok, why)
    ok, why = sample(lambda m, s: (s.update(verified_by="anyone", verification_evidence="any text"), resha(m, s)))
    ck("D8", "OBSERVATION: verified_by / verification_evidence are free text -- any non-empty string passes "
             "(human provenance is attested, not checked against B's receipt)", not ok, why, kind="observation")
    p2 = copy.deepcopy(plan)
    p2["ordered_request_ids"] = p2["ordered_request_ids"][::-1]
    p2["plan_sha256"] = osha({k: v for k, v in p2.items() if k != "plan_sha256"})
    ok, why = refused(D.check_start, p2, bundle, recs, roles, rows, manifest, screening, now="2031-01-02T00:00:00+00:00")
    ck("D9", "a resealed plan with reordered requests is refused at check_start", ok, why)

    # ---------------- E: time order
    ok, why = refused(D.check_start, plan, bundle, recs, roles, rows, manifest, screening, now=plan["frozen_at"])
    ck("E1", "START at exactly the plan freeze time is refused (strictly later required)", ok, why)
    res = D.check_start(plan, bundle, recs, roles, rows, manifest, screening, now="2031-01-02T00:00:00+00:00")
    ck("E2", "START after the plan passes and states generation_started=false, authorized=false",
       res["generation_started"] is False and res["authorized"] is False)
    ok, why = refused(D.check_start, plan, bundle, recs, roles, rows, manifest, screening, now="2031-01-01T03:30:00+00:00")
    ck("E3", "START before the plan freeze is refused", ok, why)
    ok, why = refused(D.bind_plan, bundle, recs, roles, rows, manifest, screening, now="2031-01-01T03:02:30+00:00")
    ck("E4", "a plan frozen before one selection was frozen is refused", ok, why)
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0), dict(roles, frozen_at="2031-01-01T05:00:00+00:00"),
                      tmp / "e5", now=T1)
    ck("E5", "a selection frozen before the role registry is refused", ok, why)
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0, declared_at="2031-01-01T06:00:00+00:00"), roles,
                      tmp / "e6", now=T1)
    ck("E6", "a declaration time after the freeze is refused", ok, why)
    bE, rolesE, retE, baseE, mE, sE = fixtures(D, V1, manifest_frozen="2031-01-01T03:01:30+00:00")
    recE = {e["pool"]["prefix_id"]: D.freeze_choice(bE, draft(D, bE, i, selector=rolesE["assignments"][e["pool"]["prefix_id"]]
                                                               ["selector"]), rolesE, tmp / "e7", now=t)
            for i, (e, t) in enumerate(zip(bE["rows"], (T1, T2, T3)))}
    rowsE = D.export_candidates(bE, recE, rolesE, retE, baseE, Counter())
    ok, why = refused(D.bind_plan, bE, recE, rolesE, rowsE, mE, sE, now=T4)
    ck("E7", "a selection frozen before the sample freeze is refused", ok and "sample/plan order" in why, why)
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0), roles, tmp / "e8", now="2030-01-01T00:00:00+00:00")
    ck("E8", "OBSERVATION: freeze time is the machine clock (or a caller-supplied value); a back-dated freeze is only "
             "caught by the relative order checks", ok, why, kind="observation")
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0), roles, rd, now=T1)
    ck("E9", "a second freeze of the same prefix into the same receipt directory is refused (write-once)", ok, why)

    # ---------------- F: roles
    r2 = copy.deepcopy(roles)
    p0 = bundle["rows"][0]["pool"]["prefix_id"]
    r2["assignments"][p0]["reviewers"]["QH"] = ["R1", "CUR1"]
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0), r2, tmp / "f1", now=T1)
    ck("F1", "the selector as a QH reviewer of the same prefix is refused", ok, why)
    r3 = copy.deepcopy(roles)
    r3["people"]["CUR1-B"] = "person-cur1"
    r3["assignments"][p0]["reviewers"]["F"] = ["R1", "CUR1-B"]
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0), r3, tmp / "f2", now=T1)
    ck("F2", "an alias of the selector (same person) as F reviewer is refused", ok, why)
    r4 = copy.deepcopy(roles)
    r4["assignments"][p0]["reviewers"]["Q0"] = ["R9"]
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0), r4, tmp / "f4", now=T1)
    ck("F4", "a reviewer code without a person identity is refused", ok, why)
    ok, why = refused(D.freeze_choice, bundle, draft(D, bundle, 0, selector="CUR2"), roles, tmp / "f5", now=T1)
    ck("F5", "a selector not assigned to the prefix is refused", ok, why)
    # 15% double selection: the second selector freezes into its own directory under its own registry
    roles2 = copy.deepcopy(roles)
    roles2["assignments"][p0]["selector"] = "CUR2"
    second = D.freeze_choice(bundle, draft(D, bundle, 0, selector="CUR2", selected_record_id=bundle["rows"][0]["pool"]
                                           ["candidates"][-1]["record_id"]), roles2, tmp / "second", now=T1)
    rows_again = D.export_candidates(bundle, recs, roles, ret, base, Counter())
    ck("F6", "15% second selection works with a separate registry + separate directory; the frozen primary set and "
             "its requests are unchanged", second["selector"] == "CUR2" and
       [r["request_id"] for r in rows_again] == [r["request_id"] for r in rows], kind="check")
    ok, why = refused(D.export_candidates, bundle, dict(recs, **{p0: second}), roles, ret, base, Counter())
    ck("F7", "a second-selector receipt cannot replace the primary one in the plan (role registry differs)", ok, why)
    ck("F8", "OBSERVATION: the second selection is not a first-class role in v2 (no 'second_selector' field, no link "
             "between the two registries); it depends on a coordinator convention", True, None, kind="observation")
    ok, why = refused(D.check_reviewer, plan, bundle, recs, roles, p0, "R1", "QH")
    ck("F9", "check_reviewer passes R1 for QH of a prefix selected by CUR1", not ok, why)
    ok, why = refused(D.check_reviewer, plan, bundle, recs, roles, p0, "CUR1", "QH")
    ck("F10", "check_reviewer refuses the selector as reviewer", ok, why)
    ck("F11", "OBSERVATION: the F-adjudicator role is not modelled; CUR2 adjudicating a prefix that CUR2 selected "
              "(primary or 15% second) has to be refused by the adjudication-package builder (B enforces it)", True,
       None, kind="observation")
    # ---------------- H: B's distribution entry calls A's check_reviewer (+ adjudicator rule)
    import importlib.util
    spec = importlib.util.spec_from_file_location("dist_gate", B_PROJECT / "src/metacom_pm/rl1v3/review/dist_gate.py")
    G = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(G)
    pk = [(e["pool"]["prefix_id"], ch, r) for e in bundle["rows"] for ch in ("Q0", "QH", "F") for r in ("R1", "R2")]
    ok, why = refused(G.check_distribution, D, plan, bundle, recs, roles, pk)
    ck("H1", "B's distribution gate runs A's check_reviewer on all 18 (prefix, channel, reviewer) of the 4-person plan",
       not ok, why)
    bad = list(pk)
    bad[0] = (bad[0][0], bad[0][1], "CUR1")
    ok, why = refused(G.check_distribution, D, plan, bundle, recs, roles, bad)
    ck("H2", "the gate refuses packaging a curator as reviewer", ok, why)
    ok, why = refused(G.check_distribution, D, plan, bundle, recs, roles, pk, adjudicator="CUR2",
                      second_receipts={p0: second})
    gate = None if ok else G.check_distribution(D, plan, bundle, recs, roles, pk, adjudicator="CUR2",
                                                second_receipts={p0: second})
    ck("H3", "adjudicator CUR2 is blocked on prefixes CUR2 selected (primary or 15% second) and allowed elsewhere",
       gate is not None and set(gate["adjudication"]["blocked"]) == {p0, bundle["rows"][2]["pool"]["prefix_id"]}
       and gate["adjudication"]["allowed"] == [bundle["rows"][1]["pool"]["prefix_id"]], gate and gate["adjudication"])
    ok, why = refused(G.check_distribution, D, plan, bundle, recs, roles, pk, adjudicator="CUR1")
    ck("H4", "the non-blind coordinator CUR1 cannot adjudicate", ok, why)
    (out / "synthetic_bundle.json").write_text(json.dumps(bundle))
    (out / "synthetic_roles.json").write_text(json.dumps(roles))
    return bundle, roles, D


# ------------------------------------------------------------------ browser check of dp_selector_v2.html
def run_browser(wt: Path, out: Path, bundle, roles, D):
    html = D.selection_html(bundle)
    page = out / "SELECTOR_SYNTHETIC.html"
    page.write_text(html, encoding="utf-8")
    src = (B_PROJECT / "scripts/rl1v3/V321A_r15_smoke.mjs").read_text(encoding="utf-8")
    client = src[src.index("// ---------------------------------------------------------------- minimal CDP client"):
                 src.index("async function main()")]
    client = client.replace('''!!document.querySelector(".top, #fatal, .main")''', "true")
    js = """import { spawn } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
const cfg = JSON.parse(fs.readFileSync(process.argv[2], 'utf8'));
const res = { checks: [], errors: [] };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const LAUNCHED = [];
const check = (id, name, ok, detail) => res.checks.push({ id, name, ok: !!ok, detail: detail === undefined ? null : detail });
""" + client + """
async function main() {
  const b = await Browser.launch(cfg.out + '/prof');
  await b.downloadsTo(cfg.out + '/dl');
  const p = await b.open('file://' + cfg.html);
  await p.waitFor("document.getElementById('prefix').options.length > 0");
  await p.select('#decision', 'selected');
  const pre = await p.eval("document.getElementById('source').value");
  check('G1', 'FINDING: with "选择一份完整会话" the first (earliest) session is already selected before the person picks one',
        !!pre, pre);
  const hasPlaceholder = await p.eval("[...document.getElementById('source').options].some(o => o.value === '')");
  check('G2', 'FINDING: the source list has no empty "请选择" option', !hasPlaceholder);
  await p.select('#decision', 'none_suitable');
  const cov = await p.eval("[document.getElementById('coverage').value, document.getElementById('coverage').disabled]");
  check('G3', 'none_suitable sets coverage=none and locks it', cov[0] === 'none' && cov[1] === true, cov);
  await p.select('#decision', 'selected');
  await p.type('#selector', 'CUR1'); await p.type('#need', 'SIMULATED need'); await p.type('#rationale', 'SIMULATED reason');
  await p.select('#coverage', 'full'); await p.select('#staleness', 'false'); await p.select('#stage', 'false');
  await p.click('#download');
  const msg1 = await p.text('#status');
  check('G4', 'download is blocked until both blind statements are ticked', msg1.includes('需要先确认'), msg1);
  await p.click('#rankBlind'); await p.click('#blind');
  await p.type('#missing', 'still missing something');
  await p.click('#download');
  const msg2 = await p.text('#status');
  check('G5', 'full coverage with a missing need is blocked in the page', msg2.includes('不一致'), msg2);
  await p.type('#missing', '');
  await p.select('#source', await p.eval("document.getElementById('source').options[1].value"));
  const before = fs.readdirSync(cfg.out + '/dl');
  await p.click('#download');
  let f = null;
  for (let i = 0; i < 100 && !f; i++) { const n = fs.readdirSync(cfg.out + '/dl').filter((x) => !before.includes(x) && x.endsWith('.json')); if (n.length) f = n[0]; await sleep(50); }
  check('G6', 'a complete choice downloads a draft file', !!f, f);
  const zh = await p.eval("document.body.innerText.length");
  const text = await p.eval("document.body.innerText");
  check('G7', 'OBSERVATION: the selector page shows the history only in English (no Chinese display layer)',
        !/[\\u4e00-\\u9fff]/.test(await p.eval("document.getElementById('history').innerText + document.getElementById('current').innerText")), zh);
  res.forbidden = /\\bRET\\b|DP-MS|RET-MS|lexical|\\bscore/i.test(text);
  res.draft = f ? path.join(cfg.out, 'dl', f) : null;
  await b.close();
}
main().catch((e) => res.errors.push(String(e && e.stack || e))).finally(() => {
  LAUNCHED.forEach((x) => { try { x.kill('SIGKILL'); } catch (e) {} });
  fs.writeFileSync(cfg.out + '/browser.json', JSON.stringify(res, null, 1)); process.exit(0); });
"""
    (out / "sel.mjs").write_text(js, encoding="utf-8")
    chrome = os.environ.get("CHROME", "/usr/bin/google-chrome")
    (out / "sel.json").write_text(json.dumps(dict(chrome=chrome, html=str(page), out=str(out),
                                                  tmpdir=os.environ.get("TMPDIR", "/tmp"))))
    subprocess.run(["node", str(out / "sel.mjs"), str(out / "sel.json")], timeout=180)
    r = json.loads((out / "browser.json").read_text())
    for c in r["checks"]:
        kind = "finding" if c["name"].startswith("FINDING") else "observation" if c["name"].startswith("OBSERVATION") else "check"
        ck(c["id"], c["name"], c["ok"], c["detail"], kind=kind)
    ck("G8", "no condition / score / retrieval wording in the selector page text", not r.get("forbidden"))
    ck("G9", "browser run without errors", not r["errors"], r["errors"][:1])
    if r.get("draft"):
        d = json.loads(Path(r["draft"]).read_text())
        rec = D.freeze_choice(bundle, d, roles, out / "browser_receipts", now="2099-01-01T00:00:00+00:00")
        ck("G10", "the downloaded draft freezes through A's freeze_choice with the 4-person registry",
           rec["selector"] == "CUR1" and rec["decision"] == "selected")


# ------------------------------------------------------------------ RAW correspondence (B's own src)
def raw_check(bundle_path: Path, out: Path):
    sys.path.insert(0, str(B_PROJECT / "src"))
    sys.path.insert(0, str(B_PROJECT / "scripts/rl1v3"))
    from metacom_pm.rl1v3.asof import e1_receipt as E
    import V321_wsb_pr18_receipt as S
    raw = E.Raw(json.loads(S.ARTIFACT.read_text()))
    census = {c["prefix_id"]: c for c in map(json.loads, S.CENSUS.read_text().splitlines())}
    bundle = json.loads(bundle_path.read_text())
    rows = []
    for row in bundle["rows"]:
        pool = row["pool"]
        c = census[pool["prefix_id"]]
        legal = raw.legal_past(c["owner_id"], c["cutoff_rank"], c["timestamp"])
        cand = pool["candidates"]
        lines = {s["session_id"]: [f"{t['role']}: {t['text']}" for t in s["turns"] if t["text"]] for s in legal}
        rows.append(dict(prefix=pool["prefix_id"][:12], owner=c["owner_id"], legal=len(legal), candidates=len(cand),
                         same_set=sorted(x["session_id"] for x in cand) == sorted(lines),
                         texts_equal=sum(x["text"].split("\n") == lines.get(x["session_id"]) for x in cand),
                         chronological=[x["reported_at"]["session_rank"] for x in cand] ==
                         sorted(x["reported_at"]["session_rank"] for x in cand),
                         strictly_past=all(x["reported_at"]["session_rank"] < c["cutoff_rank"] for x in cand),
                         prefix_matches_census=pool["prefix"]["cutoff_rank"] == c["cutoff_rank"] and
                         pool["owner_id"] == c["owner_id"]))
    res = dict(rows=rows, total=sum(r["candidates"] for r in rows),
               ok=all(r["same_set"] and r["texts_equal"] == r["candidates"] and r["chronological"] and r["strictly_past"]
                      and r["prefix_matches_census"] for r in rows))
    (out / "raw_check.json").write_text(json.dumps(res, indent=1))
    print(json.dumps(dict(total=res["total"], ok=res["ok"])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wt")
    ap.add_argument("--out", required=True)
    ap.add_argument("--head")
    ap.add_argument("--raw-check")
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.raw_check:
        return raw_check(Path(a.raw_check), out)
    wt = Path(a.wt)
    head = subprocess.run(["git", "-C", str(wt), "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if a.head and head != a.head:
        raise SystemExit(f"checkout is at {head}, expected {a.head}")
    dirty = subprocess.run(["git", "-C", str(wt), "status", "--porcelain"], capture_output=True, text=True).stdout.strip()
    bundle, roles, D = run_api(wt, out)
    r = subprocess.run([sys.executable, str(HERE), "--raw-check", str(out / "v2_bundle_8.json"), "--out", str(out)],
                       capture_output=True, text=True, env=dict(os.environ))
    raw = json.loads((out / "raw_check.json").read_text()) if (out / "raw_check.json").exists() else dict(ok=False)
    ck("A8", "every v2 pool equals the prefix's complete strictly-past RAW sessions (B's own RAW reader): "
             f"{raw.get('total')} sessions, texts identical, chronological", raw.get("ok"), r.stderr[-300:] or None)
    if not a.no_browser:
        run_browser(wt, out, bundle, roles, D)
    res = dict(object=dict(pr=26, head=head, clean_checkout=not dirty), harness=str(HERE.relative_to(B_PROJECT.parent)),
               results=RESULTS, checks_passed=sum(x["ok"] for x in RESULTS if x["kind"] == "check"),
               checks_total=sum(x["kind"] == "check" for x in RESULTS),
               findings=[x for x in RESULTS if x["kind"] == "finding"],
               observations=[x for x in RESULTS if x["kind"] == "observation"])
    (out / "DPV2_HARNESS_RESULT.json").write_text(json.dumps(res, indent=1, ensure_ascii=False))
    print(json.dumps({k: res[k] for k in ("checks_passed", "checks_total")}), len(res["findings"]), len(res["observations"]))


if __name__ == "__main__":
    main()
