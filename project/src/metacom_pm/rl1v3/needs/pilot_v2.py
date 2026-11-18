"""NeedCard pilot runner core v2 (``pmrl1v3-b1-needcard-pilot-v2``): no verbatim greedy re-ask.

Researcher recommendation (2026-11-18): the first round uses the fixed 20 development prefixes,
at most 20 first calls and NO re-ask of the identical prompt (greedy decoding would reproduce the
same output).  v1 (``pilot.py``, plan ``9a43a79b...``, 40 calls) is kept unchanged and still valid.

Per prefix exactly one call; a malformed output, a max_new_tokens stop or a timeout makes the
card ``writer_failed`` at once.  A planned pack that is not ``ready`` becomes ``pre_call_blocked``
without a call.  Every call record carries: input identity (pack / messages sha, input tokens),
the actual output, finish reason, output tokens, seconds, peak memory, error and whether it ended
the card as writer_failed.  Stop conditions as v1 (S1-S5) with caps 20 / 0 / 20.  The measured
seconds and peak memory may be handed to A0 labelled as the NeedCard WRITER workload (Qwen3.5-9B,
<= 800 output tokens) - never as J1 judge throughput.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Callable

from ..io import object_sha256, sha256_text, write_json_once, write_jsonl_once
from . import protocol as V1W
from . import protocol_v2 as W
from .cards import assemble, failed_envelope
from .pilot import OK_FINISH, PilotStopped, _append, plan_sha256  # noqa: F401  (re-exported for the runner)

PILOT_PROTOCOL = "pmrl1v3-b1-needcard-pilot-v2"
LIMITS = dict(max_first_calls=20, max_retry_calls=0, total_calls=20, per_call_seconds=600, wall_seconds=7200,
              early_stop_after_prefixes=5, early_stop_writer_failed=3)
STOP_CONDITIONS = (
    "S1 precondition failed (identity, pack sha, clean tree, authorization, GPU gate, weight keys) -> model never loaded",
    "S2 call cap reached (first calls 20, retries 0, total 20) -> stop",
    "S3 exception during generation (OOM, CUDA, runtime) -> stop at once, no retry, no batch change",
    "S4 after the first 5 prefixes >= 3 writer_failed -> stop (systematic format problem; no prompt edit, no rerun)",
    "S5 wall clock > 7200 s -> stop before the next call; one call > 600 s -> that card is writer_failed (timeout)",
)
WORKLOAD_LABEL = "NeedCard writer workload (Qwen3.5-9B, greedy, non-thinking, <=800 output tokens); NOT J1 judge throughput"


def check_authorization(auth: dict, plan: dict, *, gpu_uuid: str) -> None:
    need = dict(scope=plan["task_id"], plan_sha256=plan["plan_sha256"], gpu_uuid=gpu_uuid, paid_api_calls=0,
                max_retry_calls=0)
    bad = [k for k, v in need.items() if auth.get(k) != v]
    if not auth.get("authorized_by") or str(auth.get("authorized_by")).lower().startswith(("ws-b", "wsb", "codex")):
        bad.append("authorized_by")
    if not isinstance(auth.get("max_first_calls"), int) or not 0 < auth["max_first_calls"] <= LIMITS["max_first_calls"]:
        bad.append("max_first_calls")
    if not auth.get("granted_at"):
        bad.append("granted_at")
    if bad:
        raise PilotStopped("S1:authorization:" + ",".join(sorted(bad)))


def check_inputs(plan: dict, packs: dict) -> None:
    rows = {r["prefix_id"]: r for r in plan["inputs"]}
    bad = [p for p in rows if p not in packs or packs[p]["pack_sha256"] != rows[p]["pack_sha256"]
           or packs[p]["status"] != rows[p]["status"]]
    if bad or set(packs) != set(rows):
        raise PilotStopped(f"S1:inputs:{sorted(bad) or 'prefix_set'}")


def blocked_envelope(ctx, pack: dict, *, writer: str) -> dict:
    return dict(schema="pmrl1v3-b1-needcard-envelope-v1", status="pre_call_blocked", prefix_id=ctx.prefix.prefix_id,
                owner_id=ctx.prefix.owner_id, session_id=ctx.prefix.session_id, fold=ctx.row["assignment"]["fold"],
                needcard=None, needcard_sha256=None, writer_identity=writer, pack_sha256=pack["pack_sha256"],
                derived_stratum=None, blocked_status=pack["status"], visibility_scope="evaluation_only",
                evidence_tier="engineering_only")


def run_pilot(plan: dict, contexts: dict, packs: dict, generate: Callable[[list, dict], dict], *, writer: str,
              out: Path, max_first_calls: int, clock: Callable[[], float] = time.monotonic) -> dict:
    check_inputs(plan, packs)
    out = Path(out)
    out.mkdir(parents=True, exist_ok=True)
    log = out / "calls.jsonl"
    if log.exists():
        raise PilotStopped("S1:output_exists")
    cap = min(max_first_calls, LIMITS["max_first_calls"], LIMITS["total_calls"])
    n, envelopes, stop, t0 = 0, [], None, clock()
    for k, row in enumerate(plan["inputs"]):
        pid = row["prefix_id"]
        ctx, pack = contexts[pid], packs[pid]
        if pack["status"] != "ready":
            envelopes.append(dict(blocked_envelope(ctx, pack, writer=writer), pilot_protocol=PILOT_PROTOCOL,
                                  plan_sha256=plan["plan_sha256"]))
            continue
        if n >= cap:
            stop = "S2:call_cap"
            break
        if clock() - t0 > LIMITS["wall_seconds"]:
            stop = "S5:wall_clock"
            break
        msgs = W.render_messages(pack)
        n += 1
        rec = dict(call=n, prefix_id=pid, attempt=1, pack_sha256=pack["pack_sha256"], messages_sha256=object_sha256(msgs),
                   planned_input_tokens=pack["input_tokens"], writer=writer)
        try:
            g = generate(msgs, pack)
        except Exception as exc:
            _append(log, dict(rec, status="exception", error=f"{type(exc).__name__}: {exc}"[:500], writer_failed=None))
            stop = f"S3:exception:{type(exc).__name__}"
            break
        if g["input_tokens"] != pack["input_tokens"]:
            _append(log, dict(rec, status="input_token_mismatch", input_tokens=g["input_tokens"], writer_failed=None))
            stop = "S1:input_token_mismatch"
            break
        rec.update(input_tokens=g["input_tokens"], output_text=g["text"], output_sha256=sha256_text(g["text"]),
                   output_tokens=g["output_tokens"], finish_reason=g["finish_reason"], seconds=g["seconds"],
                   peak_bytes=g.get("peak_bytes"))
        env, error = None, None
        if g["finish_reason"] != OK_FINISH:
            error = f"finish_reason:{g['finish_reason']}"
        else:
            try:
                env = assemble(ctx, pack, W.parse_output(g["text"], pack), writer=writer)
            except V1W.WriterOutputError as exc:
                error = str(exc)
        if env is None:
            env = failed_envelope(ctx, pack, writer=writer, errors=[error])
        _append(log, dict(rec, status="ok" if env["status"] == "ok" else "failed", error=(error or None) and error[:500],
                          writer_failed=env["status"] == "writer_failed"))
        envelopes.append(dict(env, pilot_protocol=PILOT_PROTOCOL, plan_sha256=plan["plan_sha256"]))
        failed = sum(e["status"] == "writer_failed" for e in envelopes)
        if k + 1 == LIMITS["early_stop_after_prefixes"] and failed >= LIMITS["early_stop_writer_failed"]:
            stop = "S4:early_systematic_failure"
            break
    write_jsonl_once(out / "envelopes.jsonl", envelopes)
    calls = [json.loads(x) for x in log.read_text().splitlines()] if log.exists() else []
    timed = [c for c in calls if c.get("seconds") is not None]
    summary = dict(
        protocol=PILOT_PROTOCOL, plan_sha256=plan["plan_sha256"], writer=writer, stop_reason=stop or "completed",
        prefixes_planned=len(plan["inputs"]), prefixes_done=len(envelopes),
        envelopes={s: sum(e["status"] == s for e in envelopes) for s in ("ok", "writer_failed", "pre_call_blocked")},
        calls=dict(first=n, retry=0, total=n), call_cap=cap, wall_seconds=round(clock() - t0, 1),
        finish_reasons={r: sum(c.get("finish_reason") == r for c in calls) for r in sorted({c.get("finish_reason") for c in calls} - {None})},
        a0_handoff=dict(label=WORKLOAD_LABEL, calls=len(timed),
                        seconds=[c["seconds"] for c in timed], input_tokens=[c["input_tokens"] for c in timed],
                        output_tokens=[c["output_tokens"] for c in timed],
                        peak_bytes_max=max((c.get("peak_bytes") or 0 for c in timed), default=0)),
        needcards_enter_pm_or_g_observation=False, evidence_tier="engineering_only")
    write_json_once(out / "summary.json", summary)
    return summary
