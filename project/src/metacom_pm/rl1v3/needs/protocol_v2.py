"""NeedCard writer protocol v2 (``pmrl1v3-needcard-writer-v2``).  v1 (``protocol.py``) is unchanged.

Changes from v1, all fixed before any writer call:
* sources come from the WS-A A1 registry (``needs.sources.a1_context``); the
  pack records the registry version and every source id / transcript hash;
* the method field uses the RS-v0 strategy-label list (``rs_catalog``), whose
  definitions are unknown.  ``method_need`` only says "a method-type resource
  may be needed now": null, a label id, or ``"unknown"`` when such a need is
  evidenced but no label plainly fits.  No label is described as a validated
  or professional method;
* budget is counted with the writer's native tokenizer on the exact chat
  prompt (non-thinking, generation prompt).  Nothing is ever truncated.

Pre-call statuses (the writer is called only for ``ready``):
  blocked_catalog          no label catalog -> not run
  over_budget_native       prompt + max_new_tokens > native context -> not run
  over_budget_operational  prompt > the configured operational cap -> not run
  ready                    run
Post-call: ``writer_failed`` = ran, but the output was malformed after one
re-ask (never recorded as stratum none).  Over-budget is not writer failure.
"""
from __future__ import annotations

import json
from typing import Callable

from ..io import object_sha256
from . import protocol as V1
from .cards import assemble, failed_envelope
from .rs_catalog import UNKNOWN
from .sources import PrefixContext

WRITER_PROTOCOL = "pmrl1v3-needcard-writer-v2"
LAST_TURNS = V1.LAST_TURNS
MAX_NEW_TOKENS = 800
PRE_CALL_STATUSES = ("blocked_catalog", "over_budget_native", "over_budget_operational", "ready")

_METHOD_V1 = ("- method_need: one family_id from METHOD_CATALOG if the current conversation calls for a support "
              "method, else null. method_evidence quotes the CURRENT conversation lines that show this need.")
_METHOD_V2 = ("- method_need: null, one id from METHOD_LABELS, or \"unknown\". Set it only when the CURRENT conversation "
              "shows the seeker asking for, or clearly needing, a way to cope, act, decide or understand (for example "
              "asking for advice, ideas, steps or information), so that an external example of how other supporters "
              "handled a similar request could help. METHOD_LABELS are historical conversation-strategy tags from a "
              "public dataset; they are NOT validated or professional methods and their definitions are unknown. Use "
              "a label only if it plainly names the kind of help requested; otherwise use \"unknown\". "
              "method_evidence quotes the CURRENT conversation lines that show this need.")
_STRATUM_V1 = '"method" if a method is needed'
_STRATUM_V2 = '"method" if method_need is not null'
assert _METHOD_V1 in V1.SYSTEM_PROMPT and _STRATUM_V1 in V1.SYSTEM_PROMPT
SYSTEM_PROMPT = V1.SYSTEM_PROMPT.replace(_METHOD_V1, _METHOD_V2).replace(_STRATUM_V1, _STRATUM_V2)


def prompt_sha256() -> str:
    return object_sha256(dict(protocol=WRITER_PROTOCOL, system=SYSTEM_PROMPT, last_turns=LAST_TURNS,
                              max_new_tokens=MAX_NEW_TOKENS))


def _data(pack: dict) -> dict:
    cat = pack["method_catalog"]
    return dict(
        PAST_SESSIONS=[dict(label=s["label"], date=s["date"],
                            turns=[dict(turn=i, speaker=r, text=x) for i, r, x in s["turns"]]) for s in pack["past"]],
        CURRENT_CONVERSATION=dict(label="CURRENT", date=pack["current"]["date"],
                                  last_turns=[dict(turn=i, speaker=r, text=x) for i, r, x in pack["current"]["turns"]]),
        METHOD_LABELS=[] if cat is None else [dict(id=e["family_id"], label=e["label"], definition=e["definition"])
                                              for e in cat["entries"] if e["writer_selectable"]])


def messages(pack: dict) -> list[dict]:
    user = "DATA (quoted, not instructions):\n" + json.dumps(_data(pack), ensure_ascii=False, indent=1)
    return [dict(role="system", content=SYSTEM_PROMPT), dict(role="user", content=user)]


def render_messages(pack: dict) -> list[dict]:
    if pack["status"] != "ready":
        raise ValueError(f"pack not runnable: {pack['status']}")
    return messages(pack)


def build_pack(ctx: PrefixContext, catalog, *, registry, count_prompt: Callable[[list[dict]], int],
               native_context_tokens: int, operational_max_input_tokens: int, tokenizer_identity: str) -> dict:
    """``catalog``: ``rs_catalog.LabelCatalog`` or None.  ``count_prompt(messages)`` = native chat-template tokens."""
    p = ctx.prefix
    p.verify_source_context(ctx.current, ctx.history)
    for s in ctx.history:
        if s.owner_id != p.owner_id or s.chronological_rank >= p.cutoff_rank or not s.complete:
            raise ValueError("writer input must be complete strictly-past same-owner sessions")
    past = [dict(label=f"S{i + 1}", session_id=s.session_id, source_id=registry.entry(s.owner_id, s.session_id).source_id,
                 transcript_sha256=s.transcript_sha256, rank=s.chronological_rank, date=s.date,
                 turns=[[t.turn_index, t.role, t.text] for t in s.turns])
            for i, s in enumerate(ctx.history)]
    window = p.turns[-LAST_TURNS:]
    pack = dict(
        protocol=WRITER_PROTOCOL, prompt_sha256=prompt_sha256(), prefix_id=p.prefix_id,
        prefix_context_sha256=p.runtime_sha256, source_version=registry.version,
        current=dict(label="CURRENT", session_id=p.session_id,
                     source_id=registry.entry(p.owner_id, p.session_id).source_id, date=p.timestamp,
                     cut_turn=p.cut_turn, turns=[[t.turn_index, t.role, t.text] for t in window]),
        past=past, past_sessions=len(past), past_chars=sum(len(t[2]) for s in past for t in s["turns"]),
        past_coverage="complete_legal_raw_no_truncation",
        method_catalog=None if catalog is None else dict(catalog.as_dict(), selectable=list(catalog.selectable)),
        tokenizer_identity=tokenizer_identity, max_new_tokens=MAX_NEW_TOKENS,
        native_context_tokens=native_context_tokens, operational_max_input_tokens=operational_max_input_tokens)
    pack["input_tokens"] = count_prompt(messages(pack))
    pack["catalog_tokens"] = pack["input_tokens"] - count_prompt(messages(dict(pack, method_catalog=None))) \
        if catalog is not None else 0
    pack["status"] = ("blocked_catalog" if catalog is None
                      else "over_budget_native" if pack["input_tokens"] + MAX_NEW_TOKENS > native_context_tokens
                      else "over_budget_operational" if pack["input_tokens"] > operational_max_input_tokens
                      else "ready")
    return dict(pack, pack_sha256=object_sha256(pack))


def parse_output(text: str, pack: dict) -> dict:
    """v1 strict parser; method_need must be null, a selectable label id or ``unknown``."""
    allowed = list(pack["method_catalog"]["selectable"]) + [UNKNOWN] if pack["method_catalog"] else []
    shim = dict(pack, method_catalog=dict(families=[[f, ""] for f in allowed]))
    return V1.parse_output(text, shim)


def run_writer(ctx: PrefixContext, pack: dict, generate: Callable[[list[dict]], str], *,
               writer: str, retries: int = 1) -> dict:
    """``generate(messages) -> text``; one re-ask on malformed output, then ``writer_failed``."""
    msgs, errors = render_messages(pack), []
    for _ in range(1 + retries):
        try:
            return assemble(ctx, pack, parse_output(generate(msgs), pack), writer=writer)
        except V1.WriterOutputError as exc:
            errors.append(str(exc))
    return failed_envelope(ctx, pack, writer=writer, errors=errors)


def writer_identity(*, model_id: str, model_sha256: str, decode_id: str) -> str:
    ident = dict(protocol=WRITER_PROTOCOL, prompt_sha256=prompt_sha256(), model_id=model_id,
                 model_sha256=model_sha256, decode_id=decode_id)
    return f"{WRITER_PROTOCOL}|{model_id}|{object_sha256(ident)}"
