"""WS-B V3.2 RQ1 resource-effect qualification, CPU only (no GPU, model, writer, judge or paid call).

Steps (each writes once under outputs/pm_rl1/v3/V32_WSB_RQ1Q/<step>/):
  samples    54-input identity boundary + re-check of joint eligibility (16/24/14, ELIGIBLE = 8 OFF + 8 MS);
             exposure registry v2 (recorded, not exclusionary) for owners, the 54 prefixes and the new draw
  coverage   S0-S7 natural-frame candidate counts (4,119 rank>=1 cuts + rank-0 cuts) from the visible prefix and
             strictly-past RAW / compiled units only; pre-registered human screening draw for the supplementary set
  stats      precision / minimal-detectable-effect table and a fixture check of the pair / cluster rules
  protocol   candidate protocol (Q0/QH/F spec, QH packet rule, strata, statistics, exposure rule) hashed;
             the frozen P2 v1 file is verified unchanged
  gates      E1 executability matrix and Gate 1-2 PASS/BLOCKED/PENDING list from observed facts
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.io import build_manifest, file_sha256, object_sha256, write_json_once  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OUT = V3 / "V32_WSB_RQ1Q"
P0P2 = V3 / "V32_WSB_P0P2"
SOURCE = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
SESSION_RESULTS = PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl"
CENSUS = V3 / "B0/prefix_census.jsonl"
CENSUS_SUMMARY = V3 / "B0/census_summary.json"
EXPOSURE_B0 = V3 / "B0/exposure_registry.jsonl"
SELECTION = V3 / "B6e_plan/v3/SELECTION.json"
ELIG54 = P0P2 / "p2/ELIGIBILITY_54.json"
P2_FROZEN = P0P2 / "p2/P2_PROTOCOL_FROZEN.json"
P2_FROZEN_SHA = "2b6057c8dde4b443c08fd3ff281cb6c22c3ebd1f4d1a02eab8ac948a7bd4c81f"
NEEDCARD_PLAN = V3 / "B1/needcard_pilot_v2_plan/RUN_PLAN.json"
B1_COVERAGE = V3 / "B1/coverage_sample_v1.jsonl"
WSA_SIDECAR_OWNERS = ("p1", "p15", "p18")          # PR #15 b63635f3
STALE_SESSIONS = 5
A0_MEASURED = False                                 # no A0 GPU run exists (needs researcher authorisation)
DRAW_SALT = "pmrl1v3-v32-rq1q-screen-draw-v1"
CODE = [Path(__file__), PROJECT / "src/metacom_pm/rl1v3/evaluate/resource_effect_v32q.py"]


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines() if x.strip()]


def code_sha():
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()


def manifest(step, inputs, outputs):
    m = build_manifest(task=f"V32_wsb_rq1_qual:{step}", root=PROJECT, inputs=inputs, outputs=outputs,
                       code=[c for c in CODE], code_sha=code_sha())
    write_json_once(OUT / step / "manifest.json", m)


def owner_sort(o):
    return int(o[1:])


# ------------------------------------------------------------------------------- samples
def step_samples(args):
    from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
    out = OUT / "samples"
    e = json.loads(ELIG54.read_text())
    rows = [r for r in e["rows"] if r["plan_job_id"]]
    if len(rows) != 54:
        raise SystemExit(f"expected 54 listed inputs, got {len(rows)}")
    joint = Counter(r["joint_eligibility"] for r in rows)
    eligible = Counter(r["subset"] for r in rows if r["joint_eligibility"] == "ELIGIBLE")
    ident = object_sha256(sorted((r["plan_job_id"], r["prefix_id"], r["subset"], r["terminal_key_sha256"]) for r in rows))
    sel = json.loads(SELECTION.read_text())["selected_ids"]
    census = {c["prefix_id"]: c for c in jl(CENSUS)}
    reg = jl(EXPOSURE_B0)
    owner_rec = {r["owner_id"]: r for r in reg if r["record"] == "owner"}
    pre_rec = {r["prefix_id"]: r for r in reg if r["record"] == "prefix"}
    ses_rec = {(r["owner_id"], r["session_id"]): r for r in reg if r["record"] == "session"}
    needcard = json.loads(NEEDCARD_PLAN.read_text())["inputs"]
    b1cov = jl(B1_COVERAGE)
    b6e_owners = sorted({census[p]["owner_id"] for p in sel}, key=owner_sort)

    def cats(rec):
        return sorted({c for c in (rec or {}).get("categories", [])}) if rec else []
    owners = []
    for o in sorted(owner_rec, key=owner_sort):
        r = owner_rec[o]
        legacy = r["legacy_prefixes_by_category"]
        kinds = ["inspection"]
        if legacy.get("human_review") or legacy.get("judge_or_feedback") or legacy.get("training") or \
                r["run_dirs_by_category"].get("generation_or_probe"):
            kinds.append("outcome_other_contrast")
        v3 = []
        if o in b6e_owners:
            v3.append("B6e-v3 development prefix (old 54 inputs; design only, 0 generations)")
        if o in WSA_SIDECAR_OWNERS:
            v3.append("WS-A as-of sidecar PR #15 (engineering inspection)")
        n_nc = sum(1 for x in needcard if x["owner_id"] == o)
        if n_nc:
            v3.append(f"NeedCard pilot v2 plan: {n_nc} prefixes selected (0 writer calls)")
        if o in b6e_owners or n_nc:
            kinds.append("design")
        owners.append(dict(owner_id=o, fold=r["fold"], historical_rl1_split=r["historical_rl1_split"],
                           legacy_prefixes_by_category=legacy,
                           legacy_generation_or_probe_runs=len(r["run_dirs_by_category"].get("generation_or_probe", [])),
                           legacy_human_review_runs=len(r["run_dirs_by_category"].get("human_review", [])),
                           v3_exposure=v3, exposure_kinds=sorted(set(kinds)),
                           automatic_exclusion=False))
    inputs54 = []
    for p in sel:
        c = census[p]
        srec = ses_rec.get((c["owner_id"], c["session_id"]))
        inputs54.append(dict(prefix_id=p, owner_id=c["owner_id"], session_id=c["session_id"],
                             prefix_level_legacy_exposure=cats(pre_rec.get(p)),
                             session_level_legacy_exposure=cats(srec),
                             outcome_same_contrast=False,
                             outcome_same_contrast_basis="no generation or rating of these prefixes exists in V3 "
                                                         "(B6e 120 endpoints pending, 0 G calls); prefix not in "
                                                         "the 172 legacy prefix records" if p not in pre_rec else
                                                         "prefix appears in legacy records - check",
                             sensitivity_flag_session_human_review="human_review" in cats(srec)))
    boundary = dict(
        old54=dict(protocol="PR #13 PROPOSED_JOBS (54 = 39 D + 15 E) on the 8 B6e-v3 prefixes",
                   identity_sha256=ident, n=len(rows), joint=dict(joint),
                   eligible_by_subset=dict(eligible),
                   eligible_is_8_off_8_ms=dict(eligible) == {"OFF": 8, "MS": 8},
                   unlisted_blocked=[dict(prefix_id=r["prefix_id"], subset=r["subset"]) for r in e["rows"]
                                     if not r["plan_job_id"]],
                   rule="never swapped, renamed or re-hashed; usable for resource-increment comparison once source, "
                        "semantic and experimental eligibility pass (researcher 2026-11-18)"),
        supplementary=dict(protocol="pmrl1v3-v32-resource-effect-qual-v1-candidate supplementary set",
                           identity="screen draw sha256 (coverage/SCREENING_DRAW.json) + promotion rule; separate "
                                    "namespace, never merged into the 54 identity",
                           excludes_prefixes=sorted(sel)),
        challenge=dict(rule="constructed items (if ever approved) get a third namespace and are never pooled with "
                            "natural items"),
    )
    write_json_once(out / "SAMPLE_BOUNDARY.json", boundary)
    write_json_once(out / "EXPOSURE_REGISTRY_V2.json", dict(
        rule=Q.EXPOSURE_RULE, kinds=Q.EXPOSURE_KINDS,
        owners=owners, inputs54_prefixes=inputs54,
        b1_coverage_sample=dict(n=len(b1cov), owners=dict(Counter(x["owner_id"] for x in b1cov))),
        summary=dict(owners=len(owners), owners_outcome_other_contrast=sum("outcome_other_contrast" in o["exposure_kinds"]
                                                                            for o in owners),
                     inputs54_outcome_same_contrast=sum(x["outcome_same_contrast"] for x in inputs54),
                     inputs54_session_human_review=sum(x["sensitivity_flag_session_human_review"] for x in inputs54),
                     automatic_exclusions=0)))
    manifest("samples", dict(elig54=ELIG54, selection=SELECTION, census=CENSUS, exposure_b0=EXPOSURE_B0,
                             needcard_plan=NEEDCARD_PLAN, b1_coverage=B1_COVERAGE),
             [out / "SAMPLE_BOUNDARY.json", out / "EXPOSURE_REGISTRY_V2.json"])
    print(json.dumps(dict(joint=dict(joint), eligible=dict(eligible), identity=ident[:12],
                          prefix_exposed=sum(bool(x["prefix_level_legacy_exposure"]) for x in inputs54),
                          session_hr=sum(x["sensitivity_flag_session_human_review"] for x in inputs54))))


# ------------------------------------------------------------------------------ coverage
def natural_frame():
    from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
    from metacom_pm.rl1v3.prefixes import census as C
    users = C.load_users(SOURCE)
    units = [u for r in jl(SESSION_RESULTS) for u in r["accepted_units"]]
    mp = defaultdict(list)
    me = defaultdict(list)
    for u in units:
        if "profile_slot_key" in u:
            mp[u["owner_id"]].append(u)
        elif "event_experience_type" in u:
            me[u["owner_id"]].append(u)
    census = {(c["owner_id"], c["session_id"], c["cut_turn"]): c for c in jl(CENSUS)}
    frame = []
    for user in users:
        sessions = sorted(user.sessions, key=lambda s: s.chronological_rank)
        cues = [Q.session_cues(s) for s in sessions]
        for s in sessions:
            r = s.chronological_rank
            slot_vals = defaultdict(set)
            for u in mp[user.owner_id]:
                if u["source_session_rank"] < r:
                    slot_vals[u["profile_slot_key"]].add(u["normalized_value"])
            changed = sum(1 for v in slot_vals.values() if len(v) > 1)
            old_ongoing = sum(1 for u in me[user.owner_id] if u["temporal_status"] == "ongoing_stage"
                              and u["source_session_rank"] <= r - STALE_SESSIONS)
            for cut in C.legal_cut_positions(s):
                c = census.get((user.owner_id, s.session_id, cut))
                if r >= 1 and c is None:
                    raise SystemExit("census row missing")
                if c is not None:
                    pid, surface = c["prefix_id"], c["visible"]["surface_cues"]
                else:
                    turns = C.prefix_turns(s, cut)
                    pid = C.prefix_id_for(user.owner_id, s.session_id, cut, C.digest(C.turn_payload(turns)))
                    surface = C.visible_features(user, s, cut)["surface_cues"]
                flags = Q.prefix_candidates(cutoff_rank=r, past_cues=cues[:r], surface=surface,
                                            mp_changed_slots=changed, me_old_ongoing=old_ongoing)
                frame.append(dict(prefix_id=pid, owner_id=user.owner_id, session_id=s.session_id, cutoff_rank=r,
                                  cut_turn=cut, in_b0_census=c is not None, flags=flags))
    return frame


def step_coverage(args):
    from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
    out = OUT / "coverage"
    frame = natural_frame()
    owners = sorted({r["owner_id"] for r in frame}, key=owner_sort)
    if sum(r["in_b0_census"] for r in frame) != 4119:
        raise SystemExit("frame does not contain the 4,119 B0 cuts")
    mat = Q.coverage_matrix(frame, owners)
    sel = set(json.loads(SELECTION.read_text())["selected_ids"])
    draw = Q.screening_draw(frame, salt=DRAW_SALT, exclude=sel)
    situ = {}
    for k, (status, note) in Q.SITUATION_STATUS.items():
        keys = [x for x in mat if x.split("_")[0] == k or (k == "S1" and x == "explicit_reference_cue")]
        situ[k] = dict(description=Q.SITUATIONS[k], status=status, note=note,
                       mechanical_candidates={x: {kk: mat[x][kk] for kk in ("prefixes", "owners_with_any", "min_per_owner")}
                                              for x in keys})
    eligible54 = dict(S1="pending human; 8 MS inputs are candidates", S2="pending human", S0="pending human",
                      S3="pre-screen 21 inputs", S4="pre-screen 22 inputs", S5="pre-screen 9 inputs",
                      S6="pre-screen 36 inputs", S7="0 (all 8 prefixes have history)")
    gaps = [
        "S1/S2/S0: no natural count without the human screen; prior exposed evidence (2026-11-05 train screen) "
        "found a specific information gap in 10/96 prefixes - strict S1 is likely rare",
        "S2: no mechanical proxy; only the screen can separate relevant-optional from not-relevant",
        "S4/S6: cues are present in almost every with-history prefix - non-discriminative",
        "S5: lexical candidates only; ME stage is 'unknown' in bank-v0 and A's ledger has no rejected stage yet",
        "S7: 202 natural rank-0 cuts exist (18 owners) but none is in the old 54",
    ]
    write_json_once(out / "COVERAGE.json", dict(
        frame=mat["_frame"], frame_note="4,119 B0 cuts (rank>=1) + rank-0 cuts, same legal-cut rule",
        matrix={k: v for k, v in mat.items() if k != "_frame"}, situations=situ, old54_prescreen=eligible54,
        gaps=gaps, selection_independent_of_replies=True,
        inputs_used=["visible prefix", "strictly-past RAW sessions", "compiled MP/ME units with source rank < cutoff"]))
    write_json_once(out / "SCREENING_DRAW.json", dict(draw, promotion_rule=Q.PROMOTION_RULE,
                                                      screen_labels=dict(need=list(Q.NEED_LABELS),
                                                                         hazard=list(Q.HAZARD_FLAGS)),
                                                      labels_collected=0))
    manifest("coverage", dict(source=SOURCE, session_results=SESSION_RESULTS, census=CENSUS, selection=SELECTION),
             [out / "COVERAGE.json", out / "SCREENING_DRAW.json"])
    print(json.dumps(dict(frame=mat["_frame"], **{k: (v["prefixes"], v["owners_with_any"], v["min_per_owner"])
                                                  for k, v in mat.items() if k != "_frame"},
                          drawn=len(draw["drawn"]), by_stratum=dict(Counter(d["stratum"] for d in draw["drawn"])))))


# ---------------------------------------------------------------------------------- stats
def step_stats(args):
    from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
    out = OUT / "stats"
    summary = json.loads(CENSUS_SUMMARY.read_text())
    owners = [f"p{i}" for i in range(1, 19)]
    fams = [[h["owner_id"] for h in f["holders"]] for f in summary["shared_families"]]
    groups = Q.owner_groups(owners, fams)
    table = Q.precision_table()
    need = {f"groups{g}_d{d}_icc{r}_hw{t}": Q.required_per_group(groups=g, target_half_width=t, decisive=d, icc=r)
            for g in (8, 17) for d in (0.3, 0.5) for r in (0.1, 0.3) for t in (0.15, 0.20)}
    # fixture: the rules on a labelled toy set (not data)
    fx = [("p1", ["A_better", "tie"], "A"), ("p1", ["tie", "tie"], "B"), ("p2", ["B_better", "A_better"], "A"),
          ("p13", ["uncertain", "uncertain"], "A"), ("p18", ["A_better", "uncertain"], "B"), ("p3", ["B_better", "B_better"], "B")]
    gof = {o: g for g, os in groups.items() for o in os}
    pairs = [dict(owner_id=o, **Q.pair_outcome(lab, pos)) for o, lab, pos in fx]
    est = Q.cluster_estimate(pairs, gof)
    fixture = dict(pairs=pairs, estimate=est, bounds=Q.uncertainty_bounds(pairs, gof),
                   sign_flip_p=Q.sign_flip_p(list(est["group_means"].values())), note="toy labels, not data")
    write_json_once(out / "STATS_PLAN.json", dict(plan=Q.stats_plan(), owner_groups=groups, n_groups=len(groups),
                                                  precision_table=table, required_per_group=need, fixture=fixture,
                                                  prior_reference=dict(
                                                      legacy_exposed="2026-11-05 history-necessity: C vs OFF 4 win / "
                                                                     "5 tie / 1 loss on 10 screened train prefixes "
                                                                     "(decisive 0.5); 2026-11-04/05 24 pairs 17 tie "
                                                                     "(decisive ~0.3)",
                                                      use="only to bracket d in the precision table; not pooled")))
    manifest("stats", dict(census_summary=CENSUS_SUMMARY), [out / "STATS_PLAN.json"])
    print(json.dumps(dict(groups=len(groups), merged=[g for g in groups if "+" in g], need=need)))


# ------------------------------------------------------------------------------- protocol
def step_protocol(args):
    from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
    out = OUT / "protocol"
    v1 = json.loads(P2_FROZEN.read_text())
    body = {k: v for k, v in v1.items() if k != "protocol_sha256"}
    if v1.get("protocol_sha256") != P2_FROZEN_SHA or object_sha256(body) != P2_FROZEN_SHA:
        raise SystemExit("frozen P2 v1 changed")
    spec = dict(situations=Q.SITUATIONS, need_labels=list(Q.NEED_LABELS), hazard_flags=list(Q.HAZARD_FLAGS),
                needcard_role_map=Q.NEEDCARD_ROLE_MAP, review=Q.review_spec(), qh_packet_rule=Q.QH_PACKET_RULE,
                f_serious_default=list(Q.F_SERIOUS_DEFAULT), statistics=Q.stats_plan(),
                promotion_rule=Q.PROMOTION_RULE, exposure_rule=Q.EXPOSURE_RULE, exposure_kinds=Q.EXPOSURE_KINDS,
                frozen_v1=dict(path=str(P2_FROZEN.relative_to(PROJECT)), protocol_sha256=P2_FROZEN_SHA,
                               file_sha256=file_sha256(P2_FROZEN), changed=False,
                               withdrawn_in_candidate="task_Q reviewer context = union of readings of all conditions"))
    frozen = Q.freeze(spec)
    write_json_once(out / "PROTOCOL_CANDIDATE.json", frozen)
    manifest("protocol", dict(p2_v1=P2_FROZEN), [out / "PROTOCOL_CANDIDATE.json"])
    print(frozen["protocol_sha256"])


# ---------------------------------------------------------------------------------- gates
def pr_state(n):
    r = subprocess.run(["gh", "pr", "view", str(n), "--json", "state,commits"], cwd=REPO, capture_output=True,
                       text=True)
    if r.returncode != 0:
        return dict(state="unknown", head=None)
    d = json.loads(r.stdout)
    return dict(state=d["state"], head=d["commits"][-1]["oid"])


def step_gates(args):
    from metacom_pm.rl1v3.evaluate import resource_effect_v32q as Q
    out = OUT / "gates"
    b = json.loads((OUT / "samples/SAMPLE_BOUNDARY.json").read_text())["old54"]
    pr10, pr15 = pr_state(10), pr_state(15)
    facts = dict(
        # G0 research identity needs PR #10 merged AND A0 real load/decode measured (not done: no GPU authorisation)
        g0_identity=pr10["state"] == "MERGED" and A0_MEASURED,
        raters_scheduled=False, primary_metric_approved=False, screen_labels=False, qh_packets=False,
        wsa_8owner_evidence=False,
        eligible_16_is_8off_8ms=b["eligible_is_8_off_8_ms"], identity_54_unchanged=b["n"] == 54,
        materials={"DP-MP": False, "DP-ME": False, "DP-MS": False, "RS-METHOD": False, "bounded_renderer": False,
                   "RET-MS-asof": False},
    )
    obs = dict(pr10=pr10, pr15=pr15, pr15_owners=list(WSA_SIDECAR_OWNERS),
               materials_basis="ELIGIBILITY_54: MP/ME LEGACY/BLOCKED (A sidecar MP/ME/SUM quarantine); MS ELIGIBLE "
                               "is bank-v0 lexical-v0 top-1 full RAW = a retrieval arm, not direct provision; no "
                               "reviewed METHOD card exists; bounded renderer not delivered")
    write_json_once(out / "E1_EXECUTABILITY.json", dict(observed=obs, facts=facts, rows=Q.executability(facts)))
    write_json_once(out / "GATES.json", dict(observed=obs, **Q.gate_list(facts)))
    manifest("gates", dict(sample_boundary=OUT / "samples/SAMPLE_BOUNDARY.json"),
             [out / "E1_EXECUTABILITY.json", out / "GATES.json"])
    g = json.loads((out / "GATES.json").read_text())
    print(json.dumps(dict(gate1=g["gate1"]["state"], gate2=g["gate2"]["state"], pr10=pr10["state"], pr15=pr15["head"][:8])))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("samples", "coverage", "stats", "protocol", "gates"))
    args = ap.parse_args()
    dict(samples=step_samples, coverage=step_coverage, stats=step_stats, protocol=step_protocol,
         gates=step_gates)[args.step](args)


if __name__ == "__main__":
    main()
