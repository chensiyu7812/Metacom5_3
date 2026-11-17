"""Pre-registered real-resource evaluation protocol v1 (arms + metric report).

Arms are fixed before any real terminal exists.  The report refuses to be a
single number: every metric below is always present, either with a value or
with ``status = not_available`` and the reason (e.g. GSC while J2 is pending,
latency while B4 is not delivered).  A required arm that was not run must be
listed in ``missing_arms`` with a reason; it is never silently dropped.

Notes fixed in advance:
* DP_Oracle is a privileged per-prefix upper bound over the same terminal
  table, never a deployable policy.
* Fixed_best is chosen on TRAIN folds only, then applied to test folds.
* PPO_scratch is a full arm: the synthetic preflight showed it was not worse
  than BC-initialised PPO, so BC initialisation is not assumed to help.
* Results are reported per fold-test, by derived stratum, and re-weighted to
  the natural census distribution (B1 natural weights) - never only on the
  oversampled training mix.
"""
from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Mapping, Sequence

EVAL_PROTOCOL = "pmrl1v3-eval-protocol-v1"
HEADS = ("RS", "MP", "ME", "MS")


@dataclass(frozen=True)
class Arm:
    name: str
    kind: str                       # fixed | train_selected | learned | privileged
    subset: tuple[str, ...] | None = None
    deployable: bool = True
    note: str = ""


REQUIRED_ARMS = (
    Arm("OFF", "fixed", (), note="context only; no resource read"),
    Arm("ME_only", "fixed", ("ME",)),
    Arm("Fixed_best", "train_selected", note="best fixed subset on train folds only"),
    Arm("ALL", "fixed", HEADS, note="every legal head (mask-respecting)"),
    Arm("OneShot", "learned"),
    Arm("Seq_BC", "learned"),
    Arm("PPO_BC_init", "learned"),
    Arm("PPO_scratch", "learned"),
    Arm("PPO_NoText", "learned", note="no read-text features"),
    Arm("DP_Oracle", "privileged", deployable=False, note="per-prefix DP over the table; upper bound only"),
)
OPTIONAL_ARMS = ("Rule", "Random_matched", "LLM_gate", "F_resident", "BC_union")

METRICS = (
    "n_episodes", "pending_rate", "er_value_mean", "er_value_se", "er_value_natural_weighted",
    "regret_vs_oracle_mean", "j1_lower_mean", "j1_upper_mean", "gsc_lower_mean", "gsc_upper_mean",
    "hard_factual_fail_rate", "hard_safety_fail_rate", "j1_factual_fail_rate", "j1_safety_fail_rate",
    "misuse_rate", "omission_rate", "unneeded_read_rate", "mean_gets", "get_rate_by_head",
    "input_tokens_mean", "input_tokens_p95", "latency_pred_mean", "latency_measured_p50",
    "latency_measured_p95", "by_stratum_er_value")


def _na(reason: str) -> dict:
    return dict(value=None, status="not_available", reason=reason)


def _ok(value, n) -> dict:
    return dict(value=value, status="ok", n=n)


def _mean(xs):
    return sum(xs) / len(xs)


def _pct(xs, q):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, max(0, math.ceil(q * len(xs)) - 1))]


def arm_metrics(episodes: Sequence[Mapping], oracle_value: Mapping[str, float] | None = None) -> dict:
    """``episodes``: one dict per (prefix, arm) with keys
    prefix_id, subset, er_value (None = pending), j1_lower, j1_upper, gsc_lower, gsc_upper,
    hard_factual, hard_safety, j1_factual_fail, j1_safety_fail, misuse (bool|None),
    required_heads, optional_heads, input_tokens, latency_pred, latency_measured,
    natural_weight, stratum."""
    n = len(episodes)
    out = {m: _na("no episodes") for m in METRICS}
    out["n_episodes"] = _ok(n, n)
    if not n:
        return out
    scored = [e for e in episodes if e.get("er_value") is not None]
    out["pending_rate"] = _ok(1 - len(scored) / n, n)
    if scored:
        v = [e["er_value"] for e in scored]
        out["er_value_mean"] = _ok(_mean(v), len(v))
        sd = math.sqrt(sum((x - _mean(v)) ** 2 for x in v) / (len(v) - 1)) if len(v) > 1 else 0.0
        out["er_value_se"] = _ok(sd / math.sqrt(len(v)), len(v))
        w = [e.get("natural_weight") for e in scored]
        out["er_value_natural_weighted"] = (_na("natural weights missing") if any(x is None for x in w)
                                            else _ok(sum(a * b for a, b in zip(v, w)) / sum(w), len(v)))
        if oracle_value is not None:
            r = [oracle_value[e["prefix_id"]] - e["er_value"] for e in scored if e["prefix_id"] in oracle_value]
            out["regret_vs_oracle_mean"] = _ok(_mean(r), len(r)) if r else _na("no oracle rows")
        else:
            out["regret_vs_oracle_mean"] = _na("oracle table not supplied")
        for k in ("j1_lower", "j1_upper"):
            out[k + "_mean"] = _ok(_mean([e[k] for e in scored]), len(scored))
        strata = defaultdict(list)
        for e in scored:
            strata[e.get("stratum") or "unlabelled"].append(e["er_value"])
        out["by_stratum_er_value"] = _ok({s: dict(mean=_mean(x), n=len(x)) for s, x in sorted(strata.items())}, len(scored))
    else:
        out["er_value_mean"] = _na("every terminal pending")
    for k in ("gsc_lower", "gsc_upper"):
        vals = [e.get(k) for e in episodes]
        out[k + "_mean"] = (_na(f"GSC pending on {sum(x is None for x in vals)}/{n} terminals (J2/human missing)")
                            if any(x is None for x in vals) else _ok(_mean(vals), n))
    for k, src in (("hard_factual_fail_rate", "hard_factual"), ("hard_safety_fail_rate", "hard_safety")):
        vals = [e.get(src) for e in episodes]
        out[k] = (_na(f"{src} undecided on {sum(x is None for x in vals)}/{n} terminals")
                  if any(x is None for x in vals) else _ok(sum(x == "fail" for x in vals) / n, n))
    for k, src in (("j1_factual_fail_rate", "j1_factual_fail"), ("j1_safety_fail_rate", "j1_safety_fail")):
        vals = [e.get(src) for e in episodes]
        out[k] = (_na("J1 not run on every terminal") if any(x is None for x in vals)
                  else _ok(sum(bool(x) for x in vals) / n, n))
    mis = [e.get("misuse") for e in episodes]
    out["misuse_rate"] = (_na("misuse undecided on some terminals") if any(x is None for x in mis)
                          else _ok(sum(mis) / n, n))
    if all(e.get("required_heads") is not None for e in episodes):
        omit = [bool(set(e["required_heads"]) - set(e["subset"])) for e in episodes]
        out["omission_rate"] = _ok(sum(omit) / n, n)
        reads = [(h, h in set(e["required_heads"]) | set(e.get("optional_heads") or ())) for e in episodes for h in e["subset"]]
        out["unneeded_read_rate"] = (_ok(sum(not need for _, need in reads) / len(reads), len(reads))
                                     if reads else _ok(0.0, 0))
    else:
        out["omission_rate"] = out["unneeded_read_rate"] = _na("NeedCard head needs missing")
    out["mean_gets"] = _ok(_mean([len(e["subset"]) for e in episodes]), n)
    out["get_rate_by_head"] = _ok({h: sum(h in e["subset"] for e in episodes) / n for h in HEADS}, n)
    tok = [e.get("input_tokens") for e in episodes]
    if any(t is None for t in tok):
        out["input_tokens_mean"] = out["input_tokens_p95"] = _na("token count missing")
    else:
        out["input_tokens_mean"], out["input_tokens_p95"] = _ok(_mean(tok), n), _ok(_pct(tok, .95), n)
    lp = [e.get("latency_pred") for e in episodes]
    out["latency_pred_mean"] = _na("B4 latency model not delivered") if any(x is None for x in lp) else _ok(_mean(lp), n)
    lm = [e.get("latency_measured") for e in episodes]
    if any(x is None for x in lm):
        out["latency_measured_p50"] = out["latency_measured_p95"] = _na("latency not measured")
    else:
        out["latency_measured_p50"], out["latency_measured_p95"] = _ok(_pct(lm, .5), n), _ok(_pct(lm, .95), n)
    return out


def build_report(episodes_by_arm: Mapping[str, Sequence[Mapping]], *,
                 missing_arms: Mapping[str, str] | None = None,
                 oracle_value: Mapping[str, float] | None = None, evidence_tier: str = "engineering_only") -> dict:
    missing_arms = dict(missing_arms or {})
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
                                metrics=arm_metrics(episodes_by_arm[a.name], oracle_value))
        else:
            arms[a.name] = dict(kind=a.kind, deployable=a.deployable, status="missing", reason=missing_arms[a.name])
    for name in OPTIONAL_ARMS:
        if name in episodes_by_arm:
            arms[name] = dict(kind="optional", deployable=True, metrics=arm_metrics(episodes_by_arm[name], oracle_value))
    return dict(protocol=EVAL_PROTOCOL, evidence_tier=evidence_tier, metrics=list(METRICS), arms=arms,
                note="DP_Oracle is privileged; ER-v1 values are engineering signals, not GSC")
