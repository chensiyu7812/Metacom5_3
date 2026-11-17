"""B1 (pre-A1b part): label-free sampling frames + real-text span validation.

No model, GPU, judge or paid call.  Does not write NeedCards (the writer needs
the RS catalog from WS-A and GPU authorisation).  B0 outputs are read-only.

Outputs (write-once) in --out:
  coverage_sample_v1.jsonl   fixed 24-prefix coverage set (B5 replay / pilot / B6e candidates)
  natural_eval_pool_v1.jsonl nested S/M/L natural evaluation pool with weights and exposure
  pool_summary.json          per-tier totals and session-cap shortfalls
  span_validation.json       census-wide C0 context + mechanical span probes
  pilot_pack_status.jsonl    NeedCard writer input-pack status per pilot prefix (hashes only)
  manifest.json
"""
from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.rl1v3.io import build_manifest, write_json_once, write_jsonl_once  # noqa: E402
from metacom_pm.rl1v3.needs import protocol as P, sampling as SM  # noqa: E402
from metacom_pm.rl1v3.needs.sources import ADAPTER_PROVENANCE, CensusSources  # noqa: E402
from metacom_pm.rl1v3.needs.spans import SpanRejected, locate  # noqa: E402


def h(text: str) -> int:
    return int(hashlib.sha256(text.encode()).hexdigest(), 16)


def outcome(fn):
    try:
        fn()
        return "resolved"
    except SpanRejected as e:
        return e.reason


def probes(ctx, src, rows_by_owner, owners):
    """Mechanical probes with known expected outcomes on real text."""
    out = {}
    pid = ctx.prefix.prefix_id
    if ctx.history:
        sess = ctx.history[h(pid) % len(ctx.history)]
        turn = max(sess.turns, key=lambda t: (len(t.text), -t.turn_index))
        q = turn.text[:60]
        out["past_quote"] = ("resolved", outcome(lambda: locate(q, ctx, sess.session_id)))
        if " " in q:
            alt = q.replace(" ", "  ", 1)
            out["whitespace_altered"] = ("not_found", outcome(lambda: locate(alt, ctx, sess.session_id)))
        other_owner = owners[(owners.index(ctx.prefix.owner_id) + 1) % len(owners)]
        o_user = src.users[other_owner]
        o_turn = max(o_user.sessions[0].turns, key=lambda t: len(t.content)).content[:60]
        if not any(o_turn in t.text for s in ctx.sources for t in s.turns):
            out["other_owner_text"] = ("not_found", outcome(lambda: locate(o_turn, ctx, sess.session_id)))
    after = ctx.current.turns[ctx.prefix.cut_turn + 1].text
    if len(after.strip()) >= 8 and not any(after in t.text for t in ctx.prefix.turns):
        out["after_cut"] = ("future_turn", outcome(lambda: locate(after, ctx, ctx.prefix.session_id)))
    future = [s for s in src.users[ctx.prefix.owner_id].sessions if s.chronological_rank > ctx.prefix.cutoff_rank]
    if future:
        fq = max(future[0].turns, key=lambda t: len(t.content)).content[:60]
        out["future_session"] = ("unknown_session", outcome(lambda: locate(fq, ctx, future[0].session_id)))
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs/rl1v3/B1.yaml"))
    ap.add_argument("--out", default=str(ROOT / "outputs/pm_rl1/v3/B1"))
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    out = Path(args.out)
    t0 = time.time()
    census = ROOT / cfg["census"]
    rows = [json.loads(x) for x in census.read_text().splitlines()]
    exposure = SM.load_exposure(ROOT / cfg["exposure"])
    folds = json.loads((ROOT / cfg["folds"]).read_text())
    src = CensusSources(ROOT / cfg["source_artifact"])

    cov = SM.coverage_sample(rows, exposure, folds)
    pool = SM.natural_eval_pool(rows, exposure)
    summary = SM.pool_summary(pool)

    owners = sorted(src.users, key=lambda o: int(o[1:]))
    contexts_ok, ctx_fail, tally, mism = 0, [], Counter(), []
    detail = {}
    cov_ids = {r["prefix_id"] for r in cov}
    for r in rows:
        try:
            ctx = src.context(r)
            contexts_ok += 1
        except Exception as exc:  # reported, never silenced
            ctx_fail.append(dict(prefix_id=r["prefix_id"], error=str(exc)[:200]))
            continue
        res = probes(ctx, src, None, owners)
        for name, (want, got) in res.items():
            tally[(name, want, got)] += 1
            if want != got:
                mism.append(dict(prefix_id=r["prefix_id"], probe=name, expected=want, got=got))
        if r["prefix_id"] in cov_ids:
            detail[r["prefix_id"]] = {k: dict(expected=w, got=g) for k, (w, g) in res.items()}
    pilot = []
    row_of = {r["prefix_id"]: r for r in rows}
    for c in cov:
        if not c["uses"]["needcard_pilot"]:
            continue
        ctx = src.context(row_of[c["prefix_id"]])
        pack = P.build_pack(ctx, None)
        pilot.append(dict(prefix_id=c["prefix_id"], owner_id=c["owner_id"], fold=c["fold"],
                          status=pack["status"], pack_sha256=pack["pack_sha256"],
                          n_past_sessions=len(pack["past"]), past_chars=pack["past_chars"],
                          window_turns=len(pack["current"]["turns"]), writer_protocol=P.WRITER_PROTOCOL,
                          prompt_sha256=P.prompt_sha256()))
    validation = dict(
        protocol="pmrl1v3-b1-span-validation-v1", source_adapter=ADAPTER_PROVENANCE,
        note="mechanical probes on real census text; not NeedCards and not semantic need labels",
        census_rows=len(rows), contexts_verified=contexts_ok, context_failures=ctx_fail,
        probe_outcomes=[dict(probe=a, expected=b, got=c, n=n) for (a, b, c), n in sorted(tally.items())],
        mismatches=mism, coverage_detail=detail, wall_seconds=round(time.time() - t0, 2))

    out.mkdir(parents=True, exist_ok=True)
    files = []
    for name, value in (("coverage_sample_v1.jsonl", cov), ("natural_eval_pool_v1.jsonl", pool),
                        ("pilot_pack_status.jsonl", pilot)):
        write_jsonl_once(out / name, value)
        files.append(out / name)
    for name, value in (("pool_summary.json", dict(sampler=SM.SAMPLER_VERSION, session_cap=SM.SESSION_CAP,
                                                   per_owner=SM.PER_OWNER, tiers=summary,
                                                   census_sessions_rank_ge_1=len({(r["owner_id"], r["session_id"]) for r in rows}),
                                                   coverage_folds={str(k): v for k, v in sorted(Counter(r["fold"] for r in cov).items())})),
                        ("span_validation.json", validation)):
        write_json_once(out / name, value)
        files.append(out / name)
    code = [ROOT / p for p in ("scripts/rl1v3/B1_frames.py", "src/metacom_pm/rl1v3/needs/sampling.py",
                               "src/metacom_pm/rl1v3/needs/sources.py", "src/metacom_pm/rl1v3/needs/spans.py",
                               "src/metacom_pm/rl1v3/needs/protocol.py", "configs/rl1v3/B1.yaml")]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    dirty = bool(subprocess.run(["git", "status", "--porcelain", "--", *map(str, code)], cwd=ROOT,
                                capture_output=True, text=True).stdout.strip())
    man = build_manifest(task="B1_frames", root=ROOT, inputs={k: ROOT / cfg[k] for k in
                         ("census", "exposure", "folds", "source_artifact")},
                         outputs=files, code=code, code_sha=head + ("-dirty" if dirty else ""))
    write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False, paid_calls=0))
    print(json.dumps(dict(contexts_verified=contexts_ok, context_failures=len(ctx_fail), mismatches=len(mism),
                          coverage=len(cov), pool=len(pool), tiers={k: v["actual_total"] for k, v in summary.items()},
                          pilot=Counter(p["status"] for p in pilot), seconds=round(time.time() - t0, 1)), default=str))


if __name__ == "__main__":
    main()
