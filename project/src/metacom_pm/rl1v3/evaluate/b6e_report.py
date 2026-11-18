"""Pre-registered B6e engineering-run report (``pmrl1v3-b6e-run-report-v1``).  Written before any real run.

Inputs are the run's own records (no model is called here):
  generations  one row per G0 terminal call: key_sha256, prefix_id, subset, finish_reason, input_tokens,
               output_tokens, seconds, peak_bytes, n_gets
  j1_runs      one row per J1 run: key_sha256, calls, item flags (from ``protocol_v3``), ledger summary
  attempts     ER-v3 ``attempt`` dicts (computed / refused, subset, stratum, record or reasons)
  tables       ``TerminalRegistry.table`` reports per prefix (reachable / computed / refused / missing)
Every rate keeps its denominator; nothing missing is imputed; ER is never reported as GSC.
"""
from __future__ import annotations

from collections import Counter
from statistics import mean
from typing import Mapping, Sequence

from ..judge.engineering_reward_v2 import SENSITIVITY_GRID
from .protocol_v2 import refusal_report

REPORT_PROTOCOL = "pmrl1v3-b6e-run-report-v1"
PARSE_FLAGS = ("parse_failed", "missing_after_retry")
CONFLICT_FLAGS = ("overlap_ambiguous", "ledger_row_conflict", "fail_without_valid_error")
CONTROLS = {"OFF": "OFF", "ME_only": "ME"}


def _rate(k, n):
    return dict(n=n, k=k, rate=(k / n) if n else None)


def _sum(xs):
    xs = [x for x in xs if x is not None]
    return dict(n=len(xs), total=sum(xs), mean=mean(xs) if xs else None, max=max(xs) if xs else None)


def build(*, generations: Sequence[Mapping], j1_runs: Sequence[Mapping], attempts: Sequence[Mapping],
          tables: Sequence[Mapping], strata: Mapping[str, str] | None = None) -> dict:
    gen_n = len(generations)
    fin = Counter(g["finish_reason"] for g in generations)
    full_parse = [r for r in j1_runs if not any(f in PARSE_FLAGS for it in r["item_flags"].values() for f in it)]
    conflicted = [r for r in j1_runs if any(f.startswith(CONFLICT_FLAGS) for it in r["item_flags"].values() for f in it)
                  or r["ledger"].get("invalid") or r["ledger"].get("ambiguous")]
    computed = [a for a in attempts if a["status"] == "computed"]
    safety = [a for a in computed if a["record"]["j1_safety_fail_items"]]
    reachable = sum(t["reachable"] for t in tables)
    pending = reachable - len(computed)
    where = {g["key_sha256"]: (g["prefix_id"], g["subset"]) for g in generations}
    by_prefix_subset = {where[a["key_sha256"]] for a in computed if a["key_sha256"] in where}
    controls = {name: dict(prefixes=len(tables),
                           computed=sum((t["prefix_id"], sub) in by_prefix_subset for t in tables))
                for name, sub in CONTROLS.items()}
    grid = {f"u={u}|g={g}": None for u in SENSITIVITY_GRID["uncertain_value"] for g in SENSITIVITY_GRID["get_penalty"]}
    for k in grid:
        vals = [a["record"]["sensitivity"][k] for a in computed]
        grid[k] = dict(n=len(vals), mean=mean(vals) if vals else None)
    return dict(
        protocol=REPORT_PROTOCOL, evidence_tier="engineering_only", is_gsc=False,
        generation=dict(calls=gen_n, normal=_rate(fin["stop"], gen_n), truncated=_rate(fin["length"], gen_n),
                        other_finish={k: v for k, v in fin.items() if k not in ("stop", "length")}),
        j1=dict(runs=len(j1_runs), full_parse=_rate(len(full_parse), len(j1_runs)),
                atomic_conflict=_rate(len(conflicted), len(j1_runs)), calls=_sum([r["calls"] for r in j1_runs])),
        er=dict(reachable_terminals=reachable, computed=_rate(len(computed), reachable),
                refused=_rate(sum(a["status"] == "refused" for a in attempts), reachable),
                pending_or_missing=_rate(pending, reachable), safety_fail=_rate(len(safety), reachable),
                pending_counted_as_zero=False),
        refusal=refusal_report(attempts),
        controls=controls,
        sensitivity_12=grid,
        tables=dict(prefixes=len(tables), complete=sum(bool(t["complete"]) for t in tables),
                    dp_oracle_eligible=[t["prefix_id"] for t in tables if t["complete"]],
                    ppo_eligible_without_zero_fill=[t["prefix_id"] for t in tables if t["complete"]]),
        cost=dict(input_tokens=_sum([g["input_tokens"] for g in generations]),
                  output_tokens=_sum([g["output_tokens"] for g in generations]),
                  gets=_sum([g["n_gets"] for g in generations]), seconds=_sum([g["seconds"] for g in generations]),
                  peak_bytes=_sum([g.get("peak_bytes") for g in generations])),
        strata=dict(Counter((strata or {}).values())),
        claims_not_allowed=["natural-distribution estimates", "generalisation or PPO superiority from the same 8 prefixes",
                            "research-qualified reward or natural support benefit"])
