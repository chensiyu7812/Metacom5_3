"""Pre-registered evaluation protocol v2 (``pmrl1v3-eval-protocol-v2``).  v1 (``protocol.py``) is unchanged.

Same pre-fixed arms as v1.  Added before any real terminal exists:
* dependence: prefixes are not independent users.  Inference resamples
  clusters = connected components of owners that share a source family
  (B0 folds already keep such owners together); sessions and prefixes nest
  inside.  Natural-distribution estimates keep the B1 natural weights
  (owner census count / owner selected count).  Counts of prefixes,
  sessions, owners and clusters are always reported next to every estimate;
  the iid SE is kept only as a labelled comparison;
* ER refusal: rate overall, by resource subset, by need stratum and by
  reason, plus the computed-vs-attempted mix, so refusals cannot silently
  keep only easy-to-score terminals;
* ER-v2 sensitivity: every pre-registered grid point per arm and whether the
  arm ranking is stable across the grid;
* the per-GET engineering penalty is reported apart from measured tokens.
"""
from __future__ import annotations

import random
from collections import Counter, defaultdict
from typing import Mapping, Sequence

from .protocol import METRICS as METRICS_V1
from .protocol import OPTIONAL_ARMS, REQUIRED_ARMS, _mean, _na, _ok
from .protocol import arm_metrics as arm_metrics_v1

EVAL_PROTOCOL = "pmrl1v3-eval-protocol-v2"
BOOTSTRAP = dict(B=2000, seed=20261118, ci=0.95, unit="owner_family_cluster")
METRICS = METRICS_V1 + (
    "n_prefixes", "n_sessions", "n_owners", "n_clusters", "er_value_cluster_se", "er_value_cluster_ci",
    "er_value_natural_weighted_cluster_ci", "er_refusal_rate", "er_refusal_by_subset", "er_refusal_by_stratum",
    "er_refusal_by_reason", "er_computed_vs_attempted_mix", "get_penalty_mean", "reading_tokens_mean",
    "er_sensitivity")


def clusters(rows: Sequence[Mapping]) -> dict[str, str]:
    """owner -> cluster id; owners sharing any family id are one cluster (union-find)."""
    parent: dict[str, str] = {}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for r in rows:
        o = "owner:" + r["owner_id"]
        find(o)
        for f in r.get("family_ids") or ():
            a, b = find(o), find("family:" + f)
            if a != b:
                parent[a] = b
    owners = {r["owner_id"] for r in rows}
    roots = {o: find("owner:" + o) for o in owners}
    names = {root: "cluster:" + "+".join(sorted(o for o, rr in roots.items() if rr == root)) for root in set(roots.values())}
    return {o: names[roots[o]] for o in owners}


def cluster_bootstrap(rows: Sequence[Mapping], value_key: str = "er_value", weight_key: str | None = None,
                      cfg: Mapping = BOOTSTRAP) -> dict:
    """Weighted mean with a cluster bootstrap (whole clusters resampled with replacement)."""
    rows = [r for r in rows if r.get(value_key) is not None]
    if not rows:
        return dict(status="not_available", reason="no scored rows")
    if weight_key and any(r.get(weight_key) is None for r in rows):
        return dict(status="not_available", reason=f"{weight_key} missing")
    cl = clusters(rows)
    groups = defaultdict(list)
    for r in rows:
        groups[cl[r["owner_id"]]].append((float(r[value_key]), float(r[weight_key]) if weight_key else 1.0))
    keys = sorted(groups)

    def est(sample):
        num = sum(v * w for k in sample for v, w in groups[k])
        den = sum(w for k in sample for _, w in groups[k])
        return num / den
    point = est(keys)
    rng = random.Random(cfg["seed"])
    reps = sorted(est([rng.choice(keys) for _ in keys]) for _ in range(cfg["B"]))
    m = sum(reps) / len(reps)
    se = (sum((x - m) ** 2 for x in reps) / (len(reps) - 1)) ** 0.5 if len(reps) > 1 else 0.0
    a = (1 - cfg["ci"]) / 2
    lo, hi = reps[int(a * (len(reps) - 1))], reps[int((1 - a) * (len(reps) - 1))]
    return dict(status="ok", value=point, se=se, ci=[lo, hi], n_clusters=len(keys), n_owners=len(cl),
                n_sessions=len({(r["owner_id"], r["session_id"]) for r in rows}), n_prefixes=len(rows),
                B=cfg["B"], seed=cfg["seed"], unit=cfg["unit"],
                warning=None if len(keys) >= 10 else "fewer than 10 clusters: interval is unreliable")


def refusal_report(attempts: Sequence[Mapping]) -> dict:
    """``attempts``: ER-v2 ``attempt`` dicts (status computed|refused, subset, stratum, reasons)."""
    if not attempts:
        return dict(status="not_available", reason="no ER attempts")

    def rate(rows):
        n = len(rows)
        k = sum(r["status"] == "refused" for r in rows)
        return dict(n=n, refused=k, rate=k / n if n else None)

    def by(field):
        g = defaultdict(list)
        for a in attempts:
            g[str(a.get(field))].append(a)
        return {k: rate(v) for k, v in sorted(g.items())}

    def mix(rows, field):
        c = Counter(str(r.get(field)) for r in rows)
        n = sum(c.values())
        return {k: v / n for k, v in sorted(c.items())} if n else {}
    done = [a for a in attempts if a["status"] == "computed"]
    shift = {}
    for field in ("stratum", "subset"):
        all_mix, done_mix = mix(attempts, field), mix(done, field)
        shift[field] = dict(attempted=all_mix, computed=done_mix,
                            max_abs_share_shift=max((abs(all_mix.get(k, 0) - done_mix.get(k, 0))
                                                     for k in set(all_mix) | set(done_mix)), default=0.0))
    return dict(status="ok", overall=rate(attempts), by_subset=by("subset"), by_stratum=by("stratum"),
                by_reason=dict(Counter(x for a in attempts for x in a.get("reasons") or ())), mix=shift)


def arm_metrics(episodes: Sequence[Mapping], oracle_value: Mapping[str, float] | None = None,
                attempts: Sequence[Mapping] | None = None) -> dict:
    """v1 metrics plus v2 fields.  Episodes additionally carry owner_id, session_id, family_ids,
    get_penalty, reading_tokens_total and er_sensitivity (grid key -> value)."""
    out = arm_metrics_v1(episodes, oracle_value)
    for m in METRICS:
        out.setdefault(m, _na("no episodes"))
    if out["er_value_se"]["status"] == "ok":
        out["er_value_se"] = dict(out["er_value_se"], note="iid SE, comparison only; inference uses er_value_cluster_se")
    scored = [e for e in episodes if e.get("er_value") is not None]
    if episodes:
        out["n_prefixes"] = _ok(len({e["prefix_id"] for e in episodes}), len(episodes))
        out["n_sessions"] = _ok(len({(e["owner_id"], e["session_id"]) for e in episodes}), len(episodes))
        out["n_owners"] = _ok(len({e["owner_id"] for e in episodes}), len(episodes))
        out["n_clusters"] = _ok(len(set(clusters(episodes).values())), len(episodes))
    if scored:
        cb = cluster_bootstrap(scored)
        out["er_value_cluster_se"] = _ok(cb["se"], len(scored)) | dict(n_clusters=cb["n_clusters"], warning=cb["warning"])
        out["er_value_cluster_ci"] = _ok(cb["ci"], len(scored)) | dict(n_clusters=cb["n_clusters"], warning=cb["warning"])
        nw = cluster_bootstrap(scored, weight_key="natural_weight")
        out["er_value_natural_weighted_cluster_ci"] = (_ok(dict(value=nw["value"], ci=nw["ci"]), len(scored))
                                                       if nw["status"] == "ok" else _na(nw["reason"]))
        gp = [e.get("get_penalty") for e in scored]
        out["get_penalty_mean"] = (_na("get_penalty missing") if any(x is None for x in gp)
                                   else _ok(_mean(gp), len(gp)) | dict(label="engineering_constant_not_a_cost_model"))
        sens = [e.get("er_sensitivity") for e in scored]
        if all(isinstance(s, Mapping) for s in sens):
            out["er_sensitivity"] = _ok({k: _mean([s[k] for s in sens]) for k in sorted(sens[0])}, len(sens))
        else:
            out["er_sensitivity"] = _na("sensitivity grid missing on some terminals")
    rt = [e.get("reading_tokens_total") for e in episodes]
    if episodes:
        out["reading_tokens_mean"] = (_na("reading tokens missing") if any(x is None for x in rt)
                                      else _ok(_mean(rt), len(rt)) | dict(note="measured tokens; separate from get_penalty"))
    rep = refusal_report(attempts or ())
    if rep["status"] == "ok":
        out["er_refusal_rate"] = _ok(rep["overall"]["rate"], rep["overall"]["n"])
        for k in ("by_subset", "by_stratum", "by_reason"):
            out[f"er_refusal_{k}"] = _ok(rep[k], rep["overall"]["n"])
        out["er_computed_vs_attempted_mix"] = _ok(rep["mix"], rep["overall"]["n"])
    else:
        for k in ("er_refusal_rate", "er_refusal_by_subset", "er_refusal_by_stratum", "er_refusal_by_reason",
                  "er_computed_vs_attempted_mix"):
            out[k] = _na(rep["reason"])
    return out


def build_report(episodes_by_arm: Mapping[str, Sequence[Mapping]], *, attempts_by_arm: Mapping | None = None,
                 missing_arms: Mapping[str, str] | None = None, oracle_value: Mapping[str, float] | None = None,
                 evidence_tier: str = "engineering_only") -> dict:
    missing_arms, attempts_by_arm = dict(missing_arms or {}), dict(attempts_by_arm or {})
    names = {a.name for a in REQUIRED_ARMS}
    unknown = set(episodes_by_arm) - names - set(OPTIONAL_ARMS)
    if unknown:
        raise ValueError(f"arms outside the pre-registered protocol: {sorted(unknown)}")
    absent = names - set(episodes_by_arm) - set(missing_arms)
    if absent:
        raise ValueError(f"required arms neither run nor declared missing: {sorted(absent)}")
    if any(not str(r).strip() for r in missing_arms.values()):
        raise ValueError("every missing arm needs a reason")
    arms = {}
    for a in REQUIRED_ARMS:
        if a.name in episodes_by_arm:
            arms[a.name] = dict(kind=a.kind, deployable=a.deployable, note=a.note,
                                metrics=arm_metrics(episodes_by_arm[a.name], oracle_value, attempts_by_arm.get(a.name)))
        else:
            arms[a.name] = dict(kind=a.kind, deployable=a.deployable, status="missing", reason=missing_arms[a.name])
    for name in OPTIONAL_ARMS:
        if name in episodes_by_arm:
            arms[name] = dict(kind="optional", deployable=True,
                              metrics=arm_metrics(episodes_by_arm[name], oracle_value, attempts_by_arm.get(name)))
    ranked = {n: a["metrics"]["er_sensitivity"]["value"] for n, a in arms.items()
              if "metrics" in a and a["metrics"]["er_sensitivity"]["status"] == "ok" and a["deployable"]}
    grid = sorted(next(iter(ranked.values()))) if ranked else []
    ranking = {g: sorted(ranked, key=lambda n: -ranked[n][g]) for g in grid}
    primary = "u=0.5|g=0.01"
    stability = (dict(primary=ranking.get(primary), stable=len({tuple(r) for r in ranking.values()}) == 1,
                      ranking_by_grid=ranking) if ranking else dict(status="not_available", reason="no sensitivity values"))
    return dict(protocol=EVAL_PROTOCOL, evidence_tier=evidence_tier, metrics=list(METRICS), bootstrap=BOOTSTRAP,
                arms=arms, sensitivity_ranking=stability,
                note="DP_Oracle is privileged; ER values are engineering signals, not GSC; prefixes are not independent users")
