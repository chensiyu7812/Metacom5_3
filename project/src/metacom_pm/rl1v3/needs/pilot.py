"""NeedCard writer v2 pilot runner core (``pmrl1v3-b1-needcard-pilot-v1``).  Model-free.

The GPU script (``scripts/rl1v3/B1_needcard_pilot_run.py``) supplies ``generate``;
everything that decides what is called, how often, when to stop and what is
written lives here so it can be exercised on CPU with a fixture generator.

Fixed rules (part of the run plan identity):
* inputs are the accepted ready packs, in plan order; a pack whose sha256
  differs from the plan is never sent;
* per prefix: one call + at most one verbatim re-ask (writer v2 rule); a call
  whose output is malformed, hits max_new_tokens or times out is a failed
  attempt; two failed attempts -> ``writer_failed`` (never stratum none);
* hard caps: first calls <= 20, re-asks <= 20, total <= 40;
* stop conditions S1-S5 (``STOP_CONDITIONS``); a stop never triggers a retry,
  a prompt change or a larger run;
* every call is appended to ``calls.jsonl`` (fsync) before the next one;
  envelopes and summary are write-once.  Outputs are evaluation-side only.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Callable

from ..io import canonical_json, object_sha256, sha256_text, write_json_once, write_jsonl_once
from . import protocol as V1
from . import protocol_v2 as W
from .cards import assemble, failed_envelope

PILOT_PROTOCOL = "pmrl1v3-b1-needcard-pilot-v1"
LIMITS = dict(first_calls=20, reasks=20, total_calls=40, per_call_seconds=600, wall_seconds=7200,
              early_stop_after_prefixes=5, early_stop_writer_failed=3)
STOP_CONDITIONS = (
    "S1 precondition failed (identity, pack sha, clean tree, authorization, GPU gate) -> model never loaded",
    "S2 call caps reached (first 20 / re-ask 20 / total 40) -> stop",
    "S3 exception during generation (OOM, CUDA, runtime) -> stop at once, no retry, no batch change",
    "S4 after the first 5 prefixes >= 3 writer_failed -> stop (systematic format problem; no prompt edit, no rerun)",
    "S5 wall clock > 7200 s -> stop before the next call; one call > 600 s -> that attempt fails (timeout)",
)
OK_FINISH = "stop"


class PilotStopped(RuntimeError):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def plan_sha256(plan: dict) -> str:
    return object_sha256({k: v for k, v in plan.items() if k not in ("plan_sha256", "written_by_code_head")})


def check_authorization(auth: dict, plan: dict, *, gpu_uuid: str) -> None:
    """S1: a researcher authorization bound to THIS plan (sha), caps and card; never written by WS-B."""
    need = dict(scope=plan["task_id"], plan_sha256=plan["plan_sha256"], gpu_uuid=gpu_uuid, paid_api_calls=0)
    bad = [k for k, v in need.items() if auth.get(k) != v]
    if not auth.get("authorized_by") or str(auth.get("authorized_by")).lower().startswith(("ws-b", "wsb", "codex")):
        bad.append("authorized_by")
    if not isinstance(auth.get("max_calls"), int) or not 0 < auth["max_calls"] <= LIMITS["total_calls"]:
        bad.append("max_calls")
    if not auth.get("granted_at"):
        bad.append("granted_at")
    if bad:
        raise PilotStopped("S1:authorization:" + ",".join(sorted(bad)))


def check_inputs(plan: dict, packs: dict) -> None:
    """S1: the packs rebuilt now must be byte-identical (sha) to the planned ready packs."""
    rows = {r["prefix_id"]: r for r in plan["inputs"]}
    bad = [p for p in rows if p not in packs or packs[p]["pack_sha256"] != rows[p]["pack_sha256"]
           or packs[p]["status"] != "ready"]
    if bad or set(packs) != set(rows):
        raise PilotStopped(f"S1:inputs:{sorted(bad) or 'prefix_set'}")


def _append(path: Path, row: dict) -> None:
    with path.open("a", encoding="utf-8") as f:
        f.write(canonical_json(row) + "\n")
        f.flush()
        os.fsync(f.fileno())


def run_pilot(plan: dict, contexts: dict, packs: dict, generate: Callable[[list, dict], dict], *, writer: str,
              out: Path, max_calls: int, clock: Callable[[], float] = time.monotonic) -> dict:
    """``generate(messages, pack) -> dict(text, output_tokens, finish_reason, input_tokens, seconds, peak_bytes)``."""
    check_inputs(plan, packs)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    calls_log = out / "calls.jsonl"
    if calls_log.exists():
        raise PilotStopped("S1:output_exists")         # write-once run directory
    cap = min(max_calls, LIMITS["total_calls"])
    n = dict(first=0, reask=0, total=0)
    envelopes, stop, t0 = [], None, clock()
    for k, row in enumerate(plan["inputs"]):
        pid = row["prefix_id"]
        ctx, pack = contexts[pid], packs[pid]
        msgs, errors, env = W.render_messages(pack), [], None
        for attempt in (1, 2):
            kind = "first" if attempt == 1 else "reask"
            if n["total"] >= cap or n[kind] >= LIMITS["first_calls" if kind == "first" else "reasks"]:
                stop = "S2:call_cap"
                break
            if clock() - t0 > LIMITS["wall_seconds"]:
                stop = "S5:wall_clock"
                break
            n[kind] += 1
            n["total"] += 1
            rec = dict(call=n["total"], prefix_id=pid, attempt=attempt, pack_sha256=pack["pack_sha256"],
                       messages_sha256=object_sha256(msgs), writer=writer)
            try:
                g = generate(msgs, pack)
            except Exception as exc:                     # S3: stop everything, keep the record
                _append(calls_log, dict(rec, status="exception", error=f"{type(exc).__name__}: {exc}"[:500]))
                stop = f"S3:exception:{type(exc).__name__}"
                break
            if g["input_tokens"] != pack["input_tokens"]:
                _append(calls_log, dict(rec, status="input_token_mismatch", **{k2: g[k2] for k2 in ("input_tokens",)}))
                stop = "S1:input_token_mismatch"
                break
            rec.update(output_sha256=sha256_text(g["text"]), output_text=g["text"], output_tokens=g["output_tokens"],
                       input_tokens=g["input_tokens"], finish_reason=g["finish_reason"], seconds=g["seconds"],
                       peak_bytes=g.get("peak_bytes"))
            if g["finish_reason"] != OK_FINISH:
                errors.append(f"finish_reason:{g['finish_reason']}")
                _append(calls_log, dict(rec, status="failed_attempt", error=errors[-1]))
                continue
            try:
                env = assemble(ctx, pack, W.parse_output(g["text"], pack), writer=writer)
                _append(calls_log, dict(rec, status="ok"))
                break
            except V1.WriterOutputError as exc:
                errors.append(str(exc))
                _append(calls_log, dict(rec, status="failed_attempt", error=str(exc)[:500]))
        if env is None and stop is None:
            env = failed_envelope(ctx, pack, writer=writer, errors=errors)
        if env is not None:
            envelopes.append(dict(env, pilot_protocol=PILOT_PROTOCOL, plan_sha256=plan["plan_sha256"]))
        if stop:
            break
        failed = sum(e["status"] == "writer_failed" for e in envelopes)
        if k + 1 == LIMITS["early_stop_after_prefixes"] and failed >= LIMITS["early_stop_writer_failed"]:
            stop = "S4:early_systematic_failure"
            break
    write_jsonl_once(out / "envelopes.jsonl", envelopes)
    calls = [json.loads(x) for x in calls_log.read_text().splitlines()] if calls_log.exists() else []
    summary = dict(
        protocol=PILOT_PROTOCOL, plan_sha256=plan["plan_sha256"], writer=writer, stop_reason=stop or "completed",
        prefixes_planned=len(plan["inputs"]), prefixes_done=len(envelopes),
        envelopes={s: sum(e["status"] == s for e in envelopes) for s in ("ok", "writer_failed")},
        calls=n, call_cap=cap, wall_seconds=round(clock() - t0, 1),
        output_tokens_total=sum(c.get("output_tokens") or 0 for c in calls),
        input_tokens_total=sum(c.get("input_tokens") or 0 for c in calls),
        finish_reasons={r: sum(c.get("finish_reason") == r for c in calls) for r in sorted({c.get("finish_reason") for c in calls} - {None})},
        peak_bytes_max=max((c.get("peak_bytes") or 0 for c in calls), default=0),
        needcards_enter_pm_or_g_observation=False, evidence_tier="engineering_only")
    write_json_once(out / "summary.json", summary)
    return summary
