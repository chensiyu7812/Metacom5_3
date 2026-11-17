"""B1 sampling frames.  The B0 natural census is never modified here.

* ``natural_eval_pool``: label-free, per-owner hash order (B0 ``sample_key``),
  at most ``SESSION_CAP`` prefixes per session, nested tiers S c M c L.  Weights
  ``owner_census_n / owner_selected_n`` restore the natural cut distribution.
* ``coverage_sample``: label-free fixed set for B5 real replay and the NeedCard
  pilot: per fold one early / mid / late history-depth prefix + one more, at
  most one per session.  Fold 6 (historical test owners) is replay-only.
* ``train_stratified``: needs verified NeedCard envelopes (pending A1b + writer
  run).  Target 50% history/both, 20% method, 30% none per owner, adjacent-
  stratum fill recorded per row, inverse-oversampling natural weights.
* Every row inherits B0 fold/assignment and the B0 exposure registry; no row is
  ever an "unexposed independent test" (public benchmark source, V3.1 §6.1).
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from ..prefixes import census as C

SAMPLER_VERSION = "pmrl1v3-b1-sampler-v1"
PER_OWNER = {"S": 16, "M": 27, "L": 54}        # 288 / 486 / 972 over 18 owners
SESSION_CAP = 2
TRAIN_TARGETS = {"history_or_both": 0.5, "method": 0.2, "none": 0.3}
FILL_ORDER = {"history_or_both": ("method", "none"), "method": ("history_or_both", "none"),
              "none": ("method", "history_or_both")}
GROUP_OF = {"history": "history_or_both", "both": "history_or_both", "method": "method", "none": "none"}
RANK_BUCKETS = (("early", 1, 3), ("mid", 4, 9), ("late", 10, 10 ** 6))
AUDIT_SALT = "pmrl1v3|audit|"


def rank_bucket(rank: int) -> str:
    return next(name for name, lo, hi in RANK_BUCKETS if lo <= rank <= hi)


def load_exposure(path: Path) -> dict:
    prefix, owner = {}, {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        r = json.loads(line)
        if r["record"] == "prefix":
            prefix[r["prefix_id"]] = sorted(r["categories"])
        elif r["record"] == "owner":
            owner[r["owner_id"]] = bool(r.get("public_benchmark_source"))
    return dict(prefix=prefix, owner_public=owner)


def _base(row: Mapping, exposure: Mapping) -> dict:
    a = row["assignment"]
    return dict(sampler=SAMPLER_VERSION, b0_protocol=C.CENSUS_PROTOCOL, prefix_id=row["prefix_id"],
                owner_id=row["owner_id"], session_id=row["session_id"], cut_turn=row["cut_turn"],
                cutoff_rank=row["cutoff_rank"], fold=a["fold"], g1_role_candidate=a["g1_role_candidate"],
                historical_rl1_split=a["historical_rl1_split"],
                legacy_exposure=exposure["prefix"].get(row["prefix_id"], []),
                owner_public_benchmark_source=exposure["owner_public"].get(row["owner_id"], True),
                independent_unexposed_test=False)


def _by_owner(rows: Iterable[Mapping]) -> dict[str, list]:
    out = defaultdict(list)
    for r in rows:
        out[r["owner_id"]].append(r)
    for v in out.values():
        v.sort(key=lambda r: r["sampling"]["sample_key"])
    return out


def natural_eval_pool(rows: Sequence[Mapping], exposure: Mapping,
                      per_owner: Mapping[str, int] = PER_OWNER) -> list[dict]:
    tiers = sorted(per_owner, key=per_owner.get)
    cap_k = max(per_owner.values())
    out = []
    for owner, rs in sorted(_by_owner(rows).items(), key=lambda kv: C._owner_sort(kv[0])):
        per_session, chosen = Counter(), []
        for r in rs:
            if len(chosen) == cap_k:
                break
            if per_session[r["session_id"]] < SESSION_CAP:
                per_session[r["session_id"]] += 1
                chosen.append(r)
        n = len(rs)
        for rank, r in enumerate(chosen):
            member = [t for t in tiers if rank < per_owner[t]]
            k = {t: min(per_owner[t], len(chosen)) for t in member}
            out.append(dict(_base(r, exposure), pool="natural_eval", owner_rank=rank, tiers=member,
                            selection_reason=f"owner_hash_order_rank_{rank}_session_cap_{SESSION_CAP}",
                            owner_census_n=n, owner_selected_n=k,
                            natural_weight={t: n / k[t] for t in member},
                            weight_method="owner_census_n/owner_selected_n (cut-proportional)"))
    return out


def pool_summary(pool: Sequence[Mapping], per_owner: Mapping[str, int] = PER_OWNER) -> dict:
    """Per-tier totals and owners that cannot reach the per-owner target under the session cap."""
    out = {}
    for t, k in sorted(per_owner.items(), key=lambda kv: kv[1]):
        n = Counter(r["owner_id"] for r in pool if t in r["tiers"])
        out[t] = dict(per_owner_target=k, nominal_total=k * len(n), actual_total=sum(n.values()),
                      short_owners={o: c for o, c in sorted(n.items(), key=lambda kv: C._owner_sort(kv[0])) if c < k})
    return out


def coverage_sample(rows: Sequence[Mapping], exposure: Mapping, folds: Mapping) -> list[dict]:
    by_owner = _by_owner(rows)
    used_sessions, out = set(), []
    for fold in range(1, C.N_FOLDS + 1):
        owners = sorted((o for o, f in folds["fold_of_owner"].items() if f == fold), key=C._owner_sort)
        for slot, bucket in enumerate(("early", "mid", "late", "any")):
            order = owners[slot % len(owners):] + owners[:slot % len(owners)]
            pick = None
            for owner in order:
                for r in by_owner[owner]:
                    if r["session_id"] in used_sessions:
                        continue
                    if bucket != "any" and rank_bucket(r["cutoff_rank"]) != bucket:
                        continue
                    pick = (owner, r)
                    break
                if pick:
                    break
            if pick is None:
                continue
            owner, r = pick
            used_sessions.add(r["session_id"])
            out.append(dict(_base(r, exposure), pool="coverage_v1", rank_bucket=rank_bucket(r["cutoff_rank"]),
                            n_prefix_turns=r["visible"]["n_prefix_turns"],
                            selection_reason=f"coverage:fold{fold}:slot{slot}:{bucket}:"
                                             f"{'preferred' if owner == order[0] else 'next_owner'}",
                            uses=dict(b5_real_replay=True, needcard_pilot=fold != C.FIXED_HELDOUT_FOLD,
                                      b6e_candidate=fold != C.FIXED_HELDOUT_FOLD)))
    return out


def _quota(k: int, targets: Mapping[str, float]) -> dict[str, int]:
    raw = {g: k * w for g, w in targets.items()}
    q = {g: int(v) for g, v in raw.items()}
    for g in sorted(raw, key=lambda g: (q[g] - raw[g], g))[:k - sum(q.values())]:
        q[g] += 1
    return q


def train_stratified(envelopes: Sequence[Mapping], rows: Sequence[Mapping], exposure: Mapping, *,
                     per_owner: int, train_folds: Sequence[int],
                     targets: Mapping[str, float] = TRAIN_TARGETS) -> list[dict]:
    """Requires derived strata from verified envelopes; ``writer_failed`` cards are excluded."""
    row_of = {r["prefix_id"]: r for r in rows}
    cards = [e for e in envelopes if e["status"] == "ok" and e["fold"] in set(train_folds)]
    out = []
    for owner, es in sorted(_by_owner([dict(row_of[e["prefix_id"]], _env=e) for e in cards]).items(),
                            key=lambda kv: C._owner_sort(kv[0])):
        pools = defaultdict(list)
        for r in es:
            pools[GROUP_OF[r["_env"]["derived_stratum"]]].append(r)
        quota, per_session, chosen = _quota(per_owner, targets), Counter(), defaultdict(list)

        def take(group, src, n, reason):
            for r in pools[src]:
                if n <= 0:
                    break
                if per_session[r["session_id"]] >= SESSION_CAP or any(r is x for x, _ in chosen[group]):
                    continue
                if any(r is x for g in chosen for x, _ in chosen[g]):
                    continue
                per_session[r["session_id"]] += 1
                chosen[group].append((r, reason))
                n -= 1
            return n

        short = {g: take(g, g, quota[g], f"quota:{g}") for g in targets}
        for g, n in short.items():
            for src in FILL_ORDER[g]:
                n = take(g, src, n, f"fill:{g}_short_from:{src}")
        sample_n = Counter(GROUP_OF[r["_env"]["derived_stratum"]] for g in chosen for r, _ in chosen[g])
        total_s, total_p = sum(sample_n.values()), len(es)
        for g in targets:
            for r, reason in chosen[g]:
                actual = GROUP_OF[r["_env"]["derived_stratum"]]
                w = (len(pools[actual]) / total_p) / (sample_n[actual] / total_s)
                out.append(dict(_base(r, exposure), pool="train_stratified", quota_group=g,
                                derived_stratum=r["_env"]["derived_stratum"],
                                needcard_sha256=r["_env"]["needcard_sha256"],
                                writer_identity=r["_env"]["writer_identity"], selection_reason=reason,
                                natural_weight=w, owner_pool_n=total_p,
                                owner_pool_strata=dict(sorted({k: len(v) for k, v in pools.items()}.items())),
                                quota=quota))
    return out


def audit_sample(envelopes: Sequence[Mapping], n: int = 40) -> list[str]:
    """B1 acceptance: Codex checks history evidence of ``n`` cards (history-bearing first)."""
    ok = [e for e in envelopes if e["status"] == "ok"]
    key = lambda e: hashlib.sha256((AUDIT_SALT + e["prefix_id"]).encode()).hexdigest()
    hist = sorted((e for e in ok if e["needcard"].history_items or e["needcard"].failed_or_rejected), key=key)
    rest = sorted((e for e in ok if e not in hist), key=key)
    return [e["prefix_id"] for e in (hist + rest)[:n]]
