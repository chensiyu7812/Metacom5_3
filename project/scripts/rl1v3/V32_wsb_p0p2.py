"""WS-B V3.2 P0-P2 CPU preparation (no GPU, no model inference, no judge, no writer, no paid call).

Steps (each writes once under outputs/pm_rl1/v3/V32_WSB_P0P2/<step>/):
  asof        compiler input frontier, bank-v0 MP pool vs chronological as-of pool on all 4,119
              prefixes, counterfactual Top-1 on the 8 B6e-v3 prefixes, legacy bindings, exchange-format
              negative/positive controls on every cutoff of the 8 B6e owners, optional WS-A exchange check
  visibility  PM-observation whitelist scan over every reachable acquisition order of the 8 prefixes
              (Gemma tokenizer only, CPU) + G-request payload scan of the PR #13 fixture requests
  p2          54-input eligibility matrix and the frozen P2 resource-value protocol (nothing generated)
  reward      J1 capacity v2 (Qwen tokenizer only): output worst cases and input sizes for the 8 prefixes;
              reward-qualification manifest
  env         baselines manifest + fixture evaluation of the fixed arms on the synthetic task
  latency     latency log schema manifest
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from itertools import permutations
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.io import build_manifest, file_sha256, object_sha256, write_json_once  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OUT = V3 / "V32_WSB_P0P2"
SESSION_RESULTS = PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl"
CENSUS = V3 / "B0/prefix_census.jsonl"
SELECTION = V3 / "B6e_plan/v3/SELECTION.json"
REPLAY = V3 / "WSB_S3/integration_acceptance_320a33d1/B5/replay_reports.jsonl"
PR13_JOBS = "project/outputs/pm_rl1/v3/resource_architecture_review_20261118/cpu/PROPOSED_JOBS.json"
PR13_REQ = "project/tests/fixtures/rl1v3_resource_review/request_inputs.json"
WSA_REF = "b63635f3621f3a5d252099efcd58ae2d1958dce2"     # pmrl1-v3/ws-a-asof-cpu-20261118 (pinned)
WSA_DIR = "project/outputs/pm_rl1/v3/asof_cpu_20261118/cpu_v3"


def git(*a, cwd=REPO):
    return subprocess.run(["git", *a], cwd=cwd, capture_output=True, text=True).stdout.strip()


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines()]


def pr13_file(path: str) -> tuple[dict, str]:
    ref = git("rev-parse", "origin/pmrl1-v3/ws-a-resource-architecture-review")
    text = subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO, capture_output=True, text=True, check=True).stdout
    return json.loads(text), ref


def wsa_files(sub: str) -> list[tuple[str, str]]:
    names = subprocess.run(["git", "ls-tree", "--name-only", f"{WSA_REF}:{WSA_DIR}/{sub}"], cwd=REPO,
                           capture_output=True, text=True, check=True).stdout.split()
    return [(n, subprocess.run(["git", "show", f"{WSA_REF}:{WSA_DIR}/{sub}/{n}"], cwd=REPO, capture_output=True,
                               text=True, check=True).stdout) for n in names]


def wsa_file(name: str) -> str:
    return subprocess.run(["git", "show", f"{WSA_REF}:{WSA_DIR}/{name}"], cwd=REPO, capture_output=True, text=True,
                          check=True).stdout


def load_bank():
    from metacom_pm.rl1v3.bank import v0_port as AP
    bank, cfg = AP.load_bank(REPO)
    return bank, cfg


def selected_prefixes(registry):
    sel = json.loads(SELECTION.read_text())
    census = {c["prefix_id"]: c for c in jl(CENSUS)}
    return [(registry.prefix(census[p]["owner_id"], census[p]["session_id"], census[p]["cut_turn"]), census[p])
            for p in sel["selected_ids"]], sel


# ------------------------------------------------------------------------------------ asof
def step_asof(args):
    from metacom_pm.rl1v3.asof import binding as AB, check as CK, legacy_audit as LA, visibility as VIS
    out = OUT / "asof"
    bank, cfg = load_bank()
    reg = bank.registry
    rows = jl(SESSION_RESULTS)
    frontier = LA.compiler_frontier(rows, reg)
    pools = LA.MPPools(rows, bank)
    census = jl(CENSUS)
    diff = LA.census_diff(pools, census)
    write_json_once(out / "MP_POOL_CENSUS_DIFF.json", {k: v for k, v in diff.items() if k != "rows"})
    (out / "MP_POOL_CENSUS_DIFF_ROWS.jsonl").write_text("".join(json.dumps(r) + "\n" for r in diff["rows"]))
    sel_prefixes, sel = selected_prefixes(reg)
    cf, bindings = [], []
    rep = {r["prefix_id"]: r for r in jl(REPLAY)}
    vis_sha = VIS.whitelist_manifest()["sha256"]
    for prefix, c in sel_prefixes:
        legal = {LA.legacy_id(r)[4:] for r in bank.candidates("MP", prefix)}
        if legal != set(pools.legacy(prefix.owner_id, prefix.cutoff_rank)):
            raise SystemExit("legacy MP pool reconstruction differs from bank.candidates")
        x = LA.counterfactual_top1(pools, bank, prefix)
        cf.append(dict(prefix_id=prefix.prefix_id, owner_id=prefix.owner_id, cutoff_rank=prefix.cutoff_rank, **x))
        snap = object_sha256(sorted((r.head, r.record_id) for h in ("RS", "MP", "ME", "MS")
                                    for r in bank.candidates(h, prefix)))
        b = AB.legacy_bank_v0_binding(reg, prefix, identity=rep[prefix.prefix_id]["identity"], snapshot_sha256=snap,
                                      external_snapshot=f"{reg.version}|esconv-train-preinstalled",
                                      visibility_policy=vis_sha)
        probs = AB.validate(b, reg, prefix)
        bindings.append(dict(prefix_id=prefix.prefix_id, binding_sha256=b.sha256, tier=b.tier, tier_reason=b.tier_reason,
                             writer_kind=b.writer_kind, frontier_sessions=len(b.source_frontier),
                             frontier_sha256=b.frontier_sha256, snapshot_sha256=snap, validate_problems=probs,
                             identity={k: getattr(b, k) for k in AB.IDENTITY_FIELDS}))
    write_json_once(out / "B6E_MP_COUNTERFACTUAL.json", dict(protocol=LA.PROTOCOL, rows=cf,
                    top1=dict(Counter(r["top1"] for r in cf))))
    write_json_once(out / "B6E_LEGACY_BINDINGS.json", dict(protocol=AB.PROTOCOL, rows=bindings,
                    c0_migration_proposal=AB.C0_MIGRATION_PROPOSAL))
    owners = sorted({p.owner_id for p, _ in sel_prefixes})
    first = {}
    for c in census:
        if c["owner_id"] in owners:
            k = (c["owner_id"], c["session_id"])
            if k not in first or c["cut_turn"] < first[k]["cut_turn"]:
                first[k] = c
    cut_prefixes = [reg.prefix(c["owner_id"], c["session_id"], c["cut_turn"])
                    for c in sorted(first.values(), key=lambda c: (c["owner_id"], c["cutoff_rank"]))]
    controls = {}
    for kind in ("legacy_bank_v0", "reference_chronological"):
        ex = CK.build_exchange(kind, pools, bank, cut_prefixes)
        res = CK.run(ex, reg)
        controls[kind] = dict({k: v for k, v in res.items() if k != "rows"},
                              per_cutoff_problem_kinds=dict(Counter(p.split(":")[0] for r in res["rows"] for p in r["problems"])),
                              prefix_extension_problem_kinds=dict(Counter(p.split(":")[0] for p in res["prefix_extension_problems"])),
                              exchange_sha256=object_sha256(ex))
    from metacom_pm.rl1v3.asof import wsa_adapter as WA
    snaps = [json.loads(t) for _, t in wsa_files("snapshots")]
    a_check = WA.check_sidecar(snaps, reg, census)
    a_check.update(wsa_ref=WSA_REF, files=len(snaps), files_sha256=object_sha256([t for _, t in wsa_files("snapshots")]))
    write_json_once(out / "WSA_SIDECAR_INDEPENDENT_CHECK.json", a_check)
    a_check = {k: v for k, v in a_check.items() if k != "rows"}
    if args.a_exchange:
        ex = json.loads(Path(args.a_exchange).read_text())
        a_check["exchange_file"] = dict(CK.run(ex, reg), exchange_file_sha256=file_sha256(args.a_exchange))
    rule = ("pre-registered control set: the 8 B6e-v3 owners, every session that has a legal prefix, its smallest "
            "cut_turn; horizons = cutoff and full trajectory")
    write_json_once(out / "EXCHANGE_CONTROLS.json", dict(protocol=CK.PROTOCOL, owners=owners, cutoffs=len(cut_prefixes),
                    selection_rule=rule, controls=controls, wsa_exchange_check=a_check))
    summary = dict(protocol=LA.PROTOCOL, compiler_frontier={k: v for k, v in frontier.items() if k != "mismatches"},
                   compiler_frontier_mismatches=frontier["mismatches"],
                   mp_pool={k: diff[k] for k in ("prefixes", "prefixes_with_mp_pool_difference",
                                                  "legacy_only_units_total", "asof_only_units_total")},
                   b6e_counterfactual=dict(Counter(r["top1"] for r in cf)),
                   controls={k: dict(passed=v["passed"], cutoffs=v["cutoffs"], cutoffs_passed=v["cutoffs_passed"],
                                     prefix_extension=v["prefix_extension_problem_kinds"]) for k, v in controls.items()},
                   wsa_sidecar=dict(ref=WSA_REF, snapshots=a_check["snapshots"], owners=a_check["owners"],
                                    cutoffs_passed=a_check["cutoffs_passed"], x5a=a_check["x5a"],
                                    prefix_extension_problems=len(a_check["prefix_extension_problems"]),
                                    passed=a_check["passed"]),
                   bank_version=bank.version, source_version=reg.version, evidence_tier="engineering_only",
                   gpu_used=False, model_calls=0)
    write_json_once(out / "ASOF_SUMMARY.json", summary)
    man = build_manifest(task="V32_wsb_asof", root=PROJECT,
                         inputs={"session_results": SESSION_RESULTS, "census": CENSUS, "selection": SELECTION,
                                 "replay": REPLAY},
                         outputs=sorted(out.glob("*.json")) + [out / "MP_POOL_CENSUS_DIFF_ROWS.jsonl"],
                         code=[Path(__file__)] + sorted((PROJECT / "src/metacom_pm/rl1v3/asof").glob("*.py")),
                         code_sha=git("rev-parse", "HEAD"))
    write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False))
    print(json.dumps(summary, indent=1)[:3000])


# ------------------------------------------------------------------------------ visibility
def _orders(heads):
    for k in range(len(heads) + 1):
        yield from permutations(heads, k)


def step_visibility(args):
    from metacom_pm.rl1v3.asof import binding as AB, visibility as VIS
    from metacom_pm.rl1v3.bank import v0_port as AP
    from metacom_pm.rl1v3.env import finite_head as E, research_v32 as RV
    from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv, TerminalIdentity, TerminalTable
    out = OUT / "visibility"
    fa = AP.make_port_factory(root=REPO)
    reg, bank = fa.bank.registry, fa.bank
    sel_prefixes, _ = selected_prefixes(reg)
    rep = {r["prefix_id"]: r for r in jl(REPLAY)}
    rows, n_obs, n_orders, invalid = [], 0, 0, Counter()
    private = set()
    for r in bank.records:
        private.add(r.record_id)
    for e in reg.entries:
        private |= {e.source_id, e.source.session_id, e.source.family_id}
    private |= {bank.version, bank.index_version, reg.version}
    for prefix, c in sel_prefixes:
        port = fa.for_prefix(prefix)
        ident = TerminalIdentity(**{k: rep[prefix.prefix_id]["identity"][k] for k in
                                    ("bank_version", "index_version", "renderer_id", "step2_id", "g_id", "decode_id")})
        env = C0FiniteHeadEnv(prefix=port.prefix, history_sessions=prefix.cutoff_rank, availability=dict(port.availability()),
                              read=lambda h, acquired, p=port: p.read(h, acquired=acquired), identity=ident,
                              table=TerminalTable({}, table_id="keys-only"), prefix_tokens=port.base_tokens,
                              read_takes_acquired=True, dynamic_mask=port.action_mask)
        snap = object_sha256(sorted((r.head, r.record_id) for h in E.HEADS for r in bank.candidates(h, prefix)))
        b = AB.legacy_bank_v0_binding(reg, prefix, identity=rep[prefix.prefix_id]["identity"], snapshot_sha256=snap,
                                      external_snapshot=f"{reg.version}|esconv-train-preinstalled",
                                      visibility_policy=VIS.whitelist_manifest()["sha256"])
        ep = RV.BoundEpisode(env, b)
        cur = reg.entry(prefix.owner_id, prefix.session_id).source
        future = [t.text for t in cur.turns[prefix.cut_turn + 1:]]
        for e in reg.entries:
            s = e.source
            if s.owner_id == prefix.owner_id and s.chronological_rank > prefix.cutoff_rank:
                future += [t.text for t in s.turns]
        legal = [t.text for t in prefix.turns]
        for s in reg.context(prefix)[1]:
            legal += [t.text for t in s.turns]
        avail = [h for h in E.HEADS if env.availability[h] > 0]
        tok = sorted(private | {prefix.prefix_id})
        ok_obs = bad = 0
        orders = 0
        for order in _orders(avail):
            s = ep.reset()
            fine = True
            for h in order:
                s2, info = ep.try_step(s, E.GET[h])
                if isinstance(info, RV.Invalid):
                    invalid[info.reason] += 1
                    fine = False
                    break
                s = s2
            if not fine:
                continue
            orders += 1
            for notext in (False, True):
                try:
                    ep.observe(s, notext=notext, private_tokens=tok, future_texts=future, legal_texts=legal)
                    ok_obs += 1
                except RV.ObservationLeak as exc:
                    bad += 1
                    rows.append(dict(prefix_id=prefix.prefix_id, order=list(order), leak=exc.args[0]))
        # unavailable head GET is a typed failure, state unchanged
        for h in E.HEADS:
            if env.availability[h] == 0:
                s0 = ep.reset()
                s1, info = ep.try_step(s0, E.GET[h])
                invalid[f"probe:{info.reason}"] += 1
                assert s1 == s0
        n_obs += ok_obs + bad
        n_orders += orders
        rows.append(dict(prefix_id=prefix.prefix_id, orders=orders, observations=ok_obs + bad, leaks=bad,
                         future_texts=len(future), unavailable=[h for h in E.HEADS if env.availability[h] == 0]))
    req, ref = pr13_file(PR13_REQ)
    g_rows = []
    for case in req["cases"]:
        payload = {k: case["row"][k] for k in ("messages", "input_ids", "decode")}
        rp = VIS.scan(payload, VIS.GENERATOR_REQUEST, private_tokens=sorted(private | {case["row"]["prefix_id"]}))
        g_rows.append(dict(request_id=case["row"]["request_id"][:16], subset=case["row"]["subset"], **rp))
    res = dict(protocol=VIS.PROTOCOL, whitelist_sha256=VIS.whitelist_manifest()["sha256"], prefixes=len(sel_prefixes),
               orders=n_orders, observations=n_obs, leaks=sum(r.get("leaks", 0) for r in rows if "leaks" in r),
               invalid_attempts=dict(invalid), per_prefix=[r for r in rows if "orders" in r],
               leak_rows=[r for r in rows if "leak" in r], generator_payload_scan=g_rows, pr13_ref=ref,
               generator_payload_scope="2 PR #13 fixture requests only; the 120 G0e requests need PR #10 merged "
                                       "(B6e_g0e_binding_addendum)", evidence_tier="engineering_only")
    write_json_once(out / "VISIBILITY_SCAN.json", res)
    write_json_once(out / "WHITELISTS.json", VIS.whitelist_manifest())
    man = build_manifest(task="V32_wsb_visibility", root=PROJECT, inputs={"selection": SELECTION, "replay": REPLAY},
                         outputs=[out / "VISIBILITY_SCAN.json", out / "WHITELISTS.json"],
                         code=[Path(__file__), PROJECT / "src/metacom_pm/rl1v3/asof/visibility.py",
                               PROJECT / "src/metacom_pm/rl1v3/env/research_v32.py"], code_sha=git("rev-parse", "HEAD"))
    write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False, tokenizer_only=True))
    print(json.dumps({k: v for k, v in res.items() if k not in ("per_prefix", "leak_rows")}, indent=1))


# ------------------------------------------------------------------------------------- p2
def step_p2(args):
    from metacom_pm.rl1v3.asof import legacy_audit as LA
    from metacom_pm.rl1v3.evaluate import resource_value_v32 as RV
    from metacom_pm.rl1v3.retrieve.v0 import search
    out = OUT / "p2"
    bank, cfg = load_bank()
    reg = bank.registry
    pools = LA.MPPools(jl(SESSION_RESULTS), bank)
    jobs_doc, ref = pr13_file(PR13_JOBS)
    jobs = jobs_doc["jobs"]
    if len(jobs) != 54 or jobs_doc["by_layer"] != {"D": 39, "E": 15}:
        raise SystemExit("PR #13 job list changed")
    sel_prefixes, _ = selected_prefixes(reg)
    rep = {r["prefix_id"]: r for r in jl(REPLAY)}
    facts, cues_by = {}, {}
    for prefix, c in sel_prefixes:
        cues_by[prefix.prefix_id] = c["visible"]["surface_cues"]
        cf = LA.counterfactual_top1(pools, bank, prefix)
        f = {}
        for h in RV.HEADS:
            res = search(bank, h, prefix)
            if not res.ranked:
                asof = "mp_unreachable_legacy_reachable_asof" if h == "MP" and cf["asof_pool"] else "no_candidate"
                f[h] = dict(legal_candidates=0, top1=dict(score=None), asof=dict(status=asof, legacy_pool=0,
                            asof_pool=cf["asof_pool"] if h == "MP" else 0), cues={}, sessions_ago=None)
                continue
            r = bank.by_id[res.ranked[0].record_id]
            src = r.source_refs[0]
            sessions_ago = None if h == "RS" else prefix.cutoff_rank - r.source_rank
            ent = reg.entry(src.owner_id, src.session_id)
            days = None
            if h != "RS" and ent.source.date and prefix.timestamp:
                from datetime import date
                days = (date.fromisoformat(prefix.timestamp) - date.fromisoformat(ent.source.date)).days
            if h == "RS":
                asof = "external_snapshot"
            elif h == "MP":
                asof = dict(same="mp_same", differs="mp_differs", tie_dependent="mp_tie_dependent").get(cf["top1"], cf["top1"])
            else:
                asof = "registry_rules"
            slot_versions = 0
            if h == "MP":
                u = pools.units[LA.legacy_id(r)[4:]]
                slot_versions = sum(x["source_session_rank"] < prefix.cutoff_rank
                                    for x in pools.by_slot[(u["owner_id"], u["profile_slot_key"])])
            f[h] = dict(legal_candidates=len(res.ranked), review_status=r.review_status, view=r.view, stage=r.stage,
                        sessions_ago=sessions_ago, days_ago=days, slot_versions_before_cutoff=slot_versions,
                        top1=dict(record_id=r.record_id, score=res.ranked[0].score, source_session_id=src.session_id,
                                  source_rank=r.source_rank, chars=len(r.reading_text)),
                        asof=dict(status=asof, legacy_pool=cf["legacy_pool"] if h == "MP" else len(res.ranked),
                                  asof_pool=cf["asof_pool"] if h == "MP" else len(res.ranked)),
                        cues=RV.text_cues(r.reading_text))
        facts[prefix.prefix_id] = f
    assessed = []
    for j in jobs:
        a = RV.assess_job(j, facts[j["prefix_id"]], cues_by[j["prefix_id"]])
        assessed.append(dict(plan_job_id=j["plan_job_id"], prefix_id=j["prefix_id"], owner_id=j["owner_id"],
                             layer=j["layer"], subset=j["subset"], terminal_key_sha256=j["terminal_key_sha256"],
                             existing_request_id=j["existing_request_id"], generation_calls_executed=0, **a))
    reachable = {p: sorted(rep[p]["key_by_subset"]) for p in facts}
    for u in jobs_doc["unreachable"]:
        a = RV.assess_job(dict(subset=u["subset"], prefix_id=u["prefix_id"]), facts[u["prefix_id"]], {})
        assessed.append(dict(plan_job_id=None, prefix_id=u["prefix_id"], owner_id=None, layer="D" if "+" not in u["subset"] else "E",
                             subset=u["subset"], terminal_key_sha256=None, existing_request_id=None,
                             generation_calls_executed=0, pr13_status=u["status"], **a))
    rank = {"BLOCKED": 0, "LEGACY_DIAGNOSTIC": 1, "ELIGIBLE": 2}
    a_rows = {r["plan_job_id"]: r for r in (json.loads(x) for x in wsa_file("INPUT_54_ELIGIBILITY.jsonl").splitlines())}
    disagree = []
    for a in assessed:
        ar = a_rows.get(a["plan_job_id"])
        a["b_mechanical_eligibility"] = a.pop("eligibility")
        a["wsa_writer_eligibility"] = ar["status"] if ar else None
        a["wsa_snapshot_sha"] = ar["snapshot_sha"] if ar else None
        joint = a["b_mechanical_eligibility"] if ar is None else min(a["b_mechanical_eligibility"], ar["status"], key=rank.get)
        a["joint_eligibility"] = joint
        if ar and ar["status"] != a["b_mechanical_eligibility"]:
            disagree.append(dict(plan_job_id=a["plan_job_id"], prefix_id=a["prefix_id"][:12], subset=a["subset"],
                                 b=a["b_mechanical_eligibility"], a=ar["status"], joint=joint))
    counts = Counter(a["joint_eligibility"] for a in assessed if a["plan_job_id"])
    b_counts = Counter(a["b_mechanical_eligibility"] for a in assessed if a["plan_job_id"])
    a_counts = Counter(r["status"] for r in a_rows.values())
    spec = dict(
        scope="exposed development inputs only; NOT executed; quality/result fields stay null",
        source=dict(pr13_ref=ref, jobs_sha256=object_sha256(jobs), proposed=54, unreachable_listed=len(jobs_doc["unreachable"])),
        eligibility_rule=dict(ELIGIBLE="all read heads as-of consistent (RS external snapshot, ME/MS registry rules, MP "
                                       "Top-1 identical under the chronological pool); still pending WS-A's formal binding",
                              LEGACY_DIAGNOSTIC="some read head's delivered unit depends on bank-v0's full-history "
                                                "projection (MP Top-1 differs or is tie-dependent)",
                              BLOCKED="unreachable in bank-v0 (never filled with zero; a new as-of input would be a new "
                                      "identity outside the 54)"),
        counts=dict(joint=dict(counts), b_mechanical=dict(b_counts), wsa_writer=dict(a_counts)),
        joint_rule="joint = the more conservative of B's time-legality label and WS-A's writer/semantic label "
                   "(ELIGIBLE > LEGACY_DIAGNOSTIC > BLOCKED); disagreements listed, none silently resolved",
        wsa_ref=WSA_REF, disagreements=disagree,
        situations=RV.coverage(assessed, memory_empty_inputs=sum(
            all(facts[a["prefix_id"]][h]["legal_candidates"] == 0 for h in ("MP", "ME", "MS")) for a in assessed)),
        supplementary_needed=dict(
            rule="only for situations NOT covered; a separate, pre-registered challenge set with its own identity, "
                 "never replacing any of the 54; selection before any generation, by researcher approval",
            S7_candidate_rule="for each B6e owner, the rank-0 session prefix with the smallest B0 sample_key "
                              "(no legal personal history; RS only)"),
        families=RV.family_design(jobs, reachable), review_form=RV.review_form(), errors=RV.ERRORS,
        positives=RV.POSITIVES, analysis=RV.analysis_plan(), cues=RV.CUES,
        thresholds=dict(stale_sessions=RV.STALE_SESSIONS, low_overlap=RV.LOW_OVERLAP),
    )
    frozen = RV.freeze(spec)
    pairs = RV.assign_positions(RV.review_pairs(jobs), frozen["protocol_sha256"])
    write_json_once(out / "ELIGIBILITY_54.json", dict(protocol=RV.PROTOCOL, rows=assessed, counts=spec["counts"],
                    disagreements=disagree, head_facts=facts, wsa_ref=WSA_REF, evidence_tier="engineering_only"))
    write_json_once(out / "P2_PROTOCOL_FROZEN.json", frozen)
    write_json_once(out / "BLIND_REVIEW_PAIRS.json", dict(protocol=RV.PROTOCOL, protocol_sha256=frozen["protocol_sha256"],
                    pairs=pairs, n=len(pairs), executed=0))
    man = build_manifest(task="V32_wsb_p2", root=PROJECT, inputs={"selection": SELECTION, "replay": REPLAY,
                         "session_results": SESSION_RESULTS, "census": CENSUS},
                         outputs=[out / "ELIGIBILITY_54.json", out / "P2_PROTOCOL_FROZEN.json", out / "BLIND_REVIEW_PAIRS.json"],
                         code=[Path(__file__), PROJECT / "src/metacom_pm/rl1v3/evaluate/resource_value_v32.py",
                               PROJECT / "src/metacom_pm/rl1v3/asof/legacy_audit.py"], code_sha=git("rev-parse", "HEAD"))
    write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False, generation_calls=0))
    print(json.dumps(dict(counts=spec["counts"], disagreements=len(disagree), protocol_sha256=frozen["protocol_sha256"], pairs=len(pairs),
                          situations={k: v["candidate_inputs"] for k, v in frozen["situations"].items()}), indent=1))


# --------------------------------------------------------------------------------- reward
def step_reward(args):
    import yaml
    from metacom_pm.rl1v3.bank import v0_port as AP
    from metacom_pm.rl1v3.judge import capacity_v3 as C, protocol_v3 as JP3, reward_qualification_v1 as RQ
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    from metacom_pm.rl1v3.retrieve.v0 import search
    sys.path.insert(0, str(PROJECT / "tests"))
    import rl1v3_reward_review_cases as RC  # fixture checklist (synthetic prefix), no model
    out = OUT / "reward"
    pre = yaml.safe_load((PROJECT / "configs/rl1v3/B1_needcard_v2.yaml").read_text())
    tok = NativeTokenizer(pre["writer_model"]["path"], PROJECT / pre["asset_manifest"])
    count = lambda t: len(tok.tokenizer.encode(t, add_special_tokens=False))
    chat = lambda msgs: len(tok.tokenizer.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                                                             enable_thinking=False))
    words = ("it sounds like the last few weeks at work have left you exhausted and you are not sure how to get "
             "through tonight without feeling overwhelmed again so maybe we can look at one small step").split()
    sent = lambda n, k: " ".join(words[(k * 7 + i) % len(words)] for i in range(n)).capitalize() + "."
    replies = {"typical_6x18w": [sent(18, k) for k in range(6)], "max_8x30w": [sent(30, k) for k in range(8)],
               "one_320tok_sentence": [" ".join(words[i % len(words)] for i in range(240)).capitalize() + "."]}
    reply_tokens = {k: count(" ".join(v)) for k, v in replies.items()}
    grid = []
    for n_h in (0, 2, 4, 8, 13, 20, 26):
        counts = {"H+": n_h // 2, "H-": n_h - n_h // 2, "R": 1, "G": 3, "I": 4, "S": 1 + (5 if n_h >= 20 else 0)}
        items = C.item_ids(counts)
        for rname, ss in replies.items():
            for sc in C.SCENARIOS:
                for pretty in (False, True):
                    n = count(C.answer(items, ss, sc, n_evidence=2 * (counts["H+"] + counts["H-"] + 1), pretty=pretty)) + 1
                    grid.append(dict(h_items=n_h, items=len(items), reply=rname, scenario=sc,
                                     format="pretty" if pretty else "compact", output_tokens=n,
                                     budget=RQ.decode_budget(n, input_tokens=0)))
    worst = {}
    for g in grid:
        if g["scenario"] == "worst" and g["format"] == "pretty":
            worst.setdefault(g["items"], {})[g["reply"]] = g["output_tokens"]
    # input side on the 8 B6e prefixes, ALL readings, fixture checklist (13 items) + per-extra-item cost
    fa = AP.make_port_factory(root=REPO)
    reg, bank = fa.bank.registry, fa.bank
    sel_prefixes, _ = selected_prefixes(reg)
    cl, _ = RC.card("full")
    long_reply = replies["one_320tok_sentence"][0]
    inp = []
    for prefix, c in sel_prefixes:
        readings = []
        for h in ("RS", "MP", "ME", "MS"):
            res = search(bank, h, prefix)
            if res.ranked:
                readings.append(bank.by_id[res.ranked[0].record_id])
        n13 = chat(JP3.render(prefix.turns, long_reply, cl, readings))
        n0 = chat(JP3.render(prefix.turns, long_reply, cl, ()))
        inp.append(dict(prefix_id=prefix.prefix_id, readings=[r.head for r in readings], input_tokens_all_13items=n13,
                        input_tokens_off_13items=n0))
    per_item = max(count(json.dumps(dict(id=i.item_id, category=i.category, text=i.text,
                                         evidence=[s.exact_quote for s in i.evidence_spans]), indent=1))
                   for i in cl.items) + 8
    worst40 = worst[max(worst)]["one_320tok_sentence"]
    for r in inp:
        r["input_tokens_all_40items_est"] = r["input_tokens_all_13items"] + 27 * per_item
        r["budget_40items_worst"] = RQ.decode_budget(worst40, input_tokens=r["input_tokens_all_40items_est"])
    res = dict(protocol="pmrl1v3-j1v3-capacity-diagnostic-v2", judge_calls=0, measured=False,
               frozen_j1=dict(protocol=JP3.JUDGE_PROTOCOL, max_new_tokens=800, status="frozen; capacity risk open"),
               reply_tokens=reply_tokens, grid=grid, worst_pretty_by_items=worst,
               fits_800=sorted({g["items"] for g in grid if g["output_tokens"] > 800}),
               input_side=inp, per_extra_item_input_tokens=per_item, decode_candidate=RQ.DECODE_CANDIDATE,
               blocked_shapes=sorted({(g["items"], g["reply"]) for g in grid if g["budget"]["blocked"]}),
               evidence_tier="engineering_only (static tokenizer counts, no judge run)")
    write_json_once(out / "J1_CAPACITY_V2.json", res)
    write_json_once(out / "REWARD_QUALIFICATION_MANIFEST.json", RQ.manifest())
    pilot = (OUT / "logs/needcard_pilot_v2_check.log").read_text()
    write_json_once(out / "NEEDCARD_PILOT_V2_CHECK.json", dict(
        plan_sha256="b1d3225b4e9b9442c2d2e7c1730ea7645e2168bd5987a2d9138fa77adca1598f",
        check_log_sha256=object_sha256(pilot), check_passed='"problems": []' in pilot and "exit=0" in pilot,
        weights_verified='"weights_verified": true' in pilot,
        writer_calls=0, run_dir_exists=(V3 / "B1/needcard_pilot_v2").exists(), authorization="none",
        gates_unchanged=["max_first_calls 20", "max_retry_calls 0", "S1-S5", "6-check audit", "evidence error <= 10%",
                         "every B6e-v3 prefix has a valid card"]))
    man = build_manifest(task="V32_wsb_reward", root=PROJECT, inputs={"selection": SELECTION},
                         outputs=sorted(out.glob("*.json")),
                         code=[Path(__file__), PROJECT / "src/metacom_pm/rl1v3/judge/reward_qualification_v1.py",
                               PROJECT / "src/metacom_pm/rl1v3/judge/capacity_v3.py"], code_sha=git("rev-parse", "HEAD"))
    write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False, tokenizer_only=True))
    print(json.dumps(dict(worst_pretty=worst, over_800=res["fits_800"], input=inp, blocked=res["blocked_shapes"]), indent=1)[:4000])


# ------------------------------------------------------------------------------ env / latency
def step_env(args):
    from metacom_pm.rl1v3.env import programmatic as PG
    from metacom_pm.rl1v3.evaluate import baselines_v32 as BL
    out = OUT / "env"
    train = PG.generate(300, 2001, (0, 1, 2), "train")
    test = PG.generate(300, 2002, (0, 1, 2), "test")

    def table(inst):
        feas = PG.feasible_subsets(inst)
        return {m: float(inst.rewards[m]) for m in feas}

    tr = [table(i) for i in train]
    te = [dict(table=table(i), cues=dict(advice_request=i.cue == "cue_method",
                                         back_reference=i.cue in ("cue_event", "cue_profile")),
               history_sessions=1) for i in test]                     # cue = the visible (paraphrased) prefix cue
    res = BL.evaluate_fixed_arms(te, tr, k_random=1, seed=7)
    res["note"] = ("synthetic programmatic task (B8e-preflight family); fixture rewards; shows the arms run and "
                   "the fairness contract; NOT evidence about support quality or PPO")
    write_json_once(out / "BASELINES_FIXTURE.json", res)
    write_json_once(out / "BASELINES_MANIFEST.json", BL.manifest())
    man = build_manifest(task="V32_wsb_env", root=PROJECT, inputs={}, outputs=sorted(out.glob("*.json")),
                         code=[Path(__file__), PROJECT / "src/metacom_pm/rl1v3/evaluate/baselines_v32.py",
                               PROJECT / "src/metacom_pm/rl1v3/env/research_v32.py"], code_sha=git("rev-parse", "HEAD"))
    write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False))
    print(json.dumps(res, indent=1))


def step_latency(args):
    from metacom_pm.rl1v3.evaluate import latency_v1 as L
    out = OUT / "latency"
    write_json_once(out / "LATENCY_SCHEMA.json", L.manifest())
    man = build_manifest(task="V32_wsb_latency", root=PROJECT, inputs={}, outputs=[out / "LATENCY_SCHEMA.json"],
                         code=[Path(__file__), PROJECT / "src/metacom_pm/rl1v3/evaluate/latency_v1.py"],
                         code_sha=git("rev-parse", "HEAD"))
    write_json_once(out / "manifest.json", dict(man, measurements=0, gpu_used=False))
    print(L.manifest()["sha256"])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("asof", "visibility", "p2", "reward", "env", "latency"))
    ap.add_argument("--a-exchange", default=None, help="WS-A as-of exchange JSON (pmrl1v3-asof-exchange-v0.1)")
    args = ap.parse_args()
    dict(asof=step_asof, visibility=step_visibility, p2=step_p2, reward=step_reward, env=step_env,
         latency=step_latency)[args.step](args)


if __name__ == "__main__":
    main()
