"""User-latency measurement interface and log schema (``pmrl1v3-latency-log-v1``).  CPU; no measurement yet.

Online user experience and offline research cost are different ledgers and can never be summed:

  ONLINE  (per user request; what the user waits for)
    request_end -> first VALID visible text      (TTFV; a hidden Step-2 plan / invalid JSON is not visible)
    request_end -> complete reply text           (TTC)
    Tokkio: user speech end -> first valid audio  (TTFA)
    components: queue, PM decision, per-GET filter/retrieval/read, render/tokenise, prefill, decode,
                hidden Step-2, validation/rewrite, fallback, TTS/A2F
  OFFLINE (research only; never part of the user latency)
    NeedCard writer, checklist build, J1/J2 judging, human review, index build, training, batch precompute

Each online event row carries cold/warm, cache hit/miss, retry and fallback flags.  Reports give
p50/p95 per condition with failure, timeout, retry and fallback rates; percentiles are measured on
end-to-end samples, never obtained by adding per-GET percentiles.
"""
from __future__ import annotations

import math

from ..io import object_sha256

PROTOCOL = "pmrl1v3-latency-log-v1"
ONLINE_EVENTS = ("request_end", "pm_start", "pm_decision", "get_start", "get_end", "render_end", "queue_start",
                 "queue_end", "prefill_start", "first_token", "first_visible_valid_text", "complete_text",
                 "fallback_start", "tts_first_audio", "user_speech_end")
ONLINE_FLAGS = ("cold_start", "cache_hit", "retry", "fallback", "timeout", "failed", "hidden_plan_tokens")
OFFLINE_KINDS = ("needcard_writer", "checklist", "judge_j1", "judge_j2", "human_review", "index_build",
                 "training", "batch_precompute")
REQUIRED = ("request_id", "condition", "binding_sha256", "g_id", "decode_id", "hardware_id", "events_ms", "flags")


class LedgerMix(ValueError):
    pass


def validate_online(row: dict) -> list[str]:
    p = [f"missing:{k}" for k in REQUIRED if k not in row]
    if p:
        return p
    ev = row["events_ms"]
    unknown = set(ev) - set(ONLINE_EVENTS)
    if unknown:
        p.append(f"unknown_events:{sorted(unknown)}")
    if row.get("kind") in OFFLINE_KINDS or any(k in row for k in ("judge_ms", "writer_ms", "needcard_ms")):
        p.append("offline_cost_in_online_row")
    start = ev.get("request_end", ev.get("user_speech_end"))
    if start is None:
        p.append("no_start_event")
    for a, b in (("request_end", "first_visible_valid_text"), ("first_visible_valid_text", "complete_text"),
                 ("prefill_start", "first_token"), ("get_start", "get_end"), ("queue_start", "queue_end")):
        if a in ev and b in ev and ev[b] < ev[a]:
            p.append(f"order:{a}>{b}")
    if "first_token" in ev and "first_visible_valid_text" in ev and ev["first_visible_valid_text"] < ev["first_token"]:
        p.append("visible_before_first_token")
    fl = row["flags"]
    if not fl.get("failed") and not fl.get("timeout") and "complete_text" not in ev:
        p.append("no_complete_text_without_failure_flag")
    return p


def derive(row: dict) -> dict:
    ev, fl = row["events_ms"], row["flags"]
    s = ev.get("request_end")
    out = dict(request_id=row["request_id"], condition=row["condition"],
               ttfv_ms=None if s is None or "first_visible_valid_text" not in ev else ev["first_visible_valid_text"] - s,
               ttc_ms=None if s is None or "complete_text" not in ev else ev["complete_text"] - s,
               ttfa_ms=None if "user_speech_end" not in ev or "tts_first_audio" not in ev
               else ev["tts_first_audio"] - ev["user_speech_end"],
               ttft_ms=None if s is None or "first_token" not in ev else ev["first_token"] - s,
               **{f: bool(fl.get(f)) for f in ONLINE_FLAGS if f != "hidden_plan_tokens"})
    return out


def _pct(xs, q):
    xs = sorted(xs)
    if not xs:
        return None
    k = (len(xs) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def summarise(rows: list[dict]) -> dict:
    by = {}
    for r in rows:
        p = validate_online(r)
        if p:
            raise LedgerMix(f"{r.get('request_id')}: {p}")
        d = derive(r)
        by.setdefault((d["condition"], d["cold_start"]), []).append(d)
    out = {}
    for (cond, cold), ds in sorted(by.items()):
        ok = [d for d in ds if not d["failed"] and not d["timeout"]]
        m = dict(n=len(ds), failure_rate=sum(d["failed"] for d in ds) / len(ds),
                 timeout_rate=sum(d["timeout"] for d in ds) / len(ds),
                 retry_rate=sum(d["retry"] for d in ds) / len(ds),
                 fallback_rate=sum(d["fallback"] for d in ds) / len(ds),
                 cache_hit_rate=sum(d["cache_hit"] for d in ds) / len(ds))
        for key in ("ttfv_ms", "ttc_ms", "ttfa_ms", "ttft_ms"):
            xs = [d[key] for d in ok if d[key] is not None]
            m[key] = dict(p50=_pct(xs, .5), p95=_pct(xs, .95), n=len(xs))
        out[f"{cond}|{'cold' if cold else 'warm'}"] = m
    return dict(protocol=PROTOCOL, groups=out, note="failed/timeout rows are counted in rates and excluded from "
                                                    "percentiles; percentiles are end-to-end, never summed per GET")


def offline_row(kind: str, *, wall_s: float, gpu_s: float, identity: str) -> dict:
    if kind not in OFFLINE_KINDS:
        raise LedgerMix(f"not an offline kind: {kind}")
    return dict(ledger="offline", kind=kind, wall_s=wall_s, gpu_s=gpu_s, identity=identity, user_latency=False)


MEASUREMENT_PLAN = dict(
    status="protocol only; real A6000 / Tokkio measurement needs a separate authorisation",
    conditions=["OFF", "each single head", "MP+MS", "ME+MS", "ALL", "F-resident", "policy under test"],
    design="per condition: >= 30 warm + 10 cold requests on the same frozen prefixes and binding; interleaved "
           "order (seeded) to spread queue effects; one hardware id per report",
    report=["TTFV p50/p95", "TTC p50/p95", "TTFA p50/p95 (Tokkio staging only)", "failure / timeout / retry / "
            "fallback rates", "component medians (queue, PM, retrieval, render, prefill, decode, hidden plan)"],
    excluded=list(OFFLINE_KINDS),
    proxy_rule="token counts are diagnostics only; a condition with fewer tokens but higher TTFV is not faster",
)


def manifest() -> dict:
    spec = dict(protocol=PROTOCOL, online_events=ONLINE_EVENTS, flags=ONLINE_FLAGS, offline=OFFLINE_KINDS,
                required=REQUIRED, plan=MEASUREMENT_PLAN)
    return dict(spec, sha256=object_sha256(spec))
