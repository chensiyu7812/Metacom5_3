"""Assemble verified C0 NeedCards and the WS-B evaluation-side envelope.

* Every writer quote is resolved with ``spans.locate`` (exact, legal, unique).
  Items whose evidence does not resolve are dropped and logged (V3.1 §6.1).
* The card's ``stratum`` is **derived from retained evidence**, not copied from
  the writer: history = some ``required``/``must_not_contradict`` item, a
  failed/rejected suggestion or an outdated fact; method = a catalog family
  plus at least one verified CURRENT-conversation evidence span.  The writer's
  claim is kept for audit and disagreements are flagged.
* Finer head needs (RS/MP/ME/MS) live only in the envelope and follow the four
  heads' purposes: method->RS, profile_fact->MP, event->ME, session_detail->MS,
  failed/rejected suggestions->ME (attempt/outcome stage), outdated facts->MP
  (state update).  ``relevant_optional`` items give *optional* heads only.
* A writer that fails to produce a parseable card yields ``writer_failed`` -
  never ``stratum = none``.
"""
from __future__ import annotations

from typing import Callable

from ..io import object_sha256, sha256_text
from .protocol import (RESOURCE_KINDS, WRITER_PROTOCOL, WriterOutputError, parse_output,
                       prompt_sha256, render_messages)
from .sources import PrefixContext
from .spans import SpanRejected, locate

ENVELOPE_SCHEMA = "pmrl1v3-b1-needcard-envelope-v1"
HISTORY_NEED_ROLES = ("required", "must_not_contradict")
HEADS = ("RS", "MP", "ME", "MS")


def writer_identity(*, model_id: str, model_sha256: str, decode_id: str) -> str:
    ident = dict(protocol=WRITER_PROTOCOL, prompt_sha256=prompt_sha256(), model_id=model_id,
                 model_sha256=model_sha256, decode_id=decode_id)
    return f"{WRITER_PROTOCOL}|{model_id}|{object_sha256(ident)}"


def derive_stratum(history_items, failed, outdated, method_need) -> str:
    history = bool(failed or outdated or any(h.role in HISTORY_NEED_ROLES for h in history_items))
    method = method_need is not None
    return "both" if history and method else "history" if history else "method" if method else "none"


def assemble(ctx: PrefixContext, pack: dict, parsed: dict, *, writer: str) -> dict:
    from .. import contracts as K
    drops, items, kinds, seen = [], [], [], set()

    def drop(kind, quote, reason, **extra):
        drops.append(dict(kind=kind, quote_sha256=sha256_text(quote), reason=reason, **extra))

    for it in parsed["history_items"]:
        try:
            span = locate(it["quote"], ctx, it["session_id"], speaker=it["speaker"])
        except SpanRejected as exc:
            drop("history_item", it["quote"], exc.reason, role=it["role"], session=it["session"])
            continue
        ident = (span.sha256, it["role"])
        if ident in seen:
            drop("history_item", it["quote"], "duplicate", role=it["role"], session=it["session"])
            continue
        seen.add(ident)
        items.append(K.HistoryItem(record_id=None, spans=(span,), role=it["role"],
                                   source_role=span.speaker, source_rank=span.source_rank))
        kinds.append(it["resource_kind"])
    failed = []
    for it in parsed["failed_or_rejected"]:
        try:
            span = locate(it["quote"], ctx, it["session_id"], speaker=it["speaker"])
        except SpanRejected as exc:
            drop("failed_or_rejected", it["quote"], exc.reason, session=it["session"])
            continue
        if span.sha256 in {s.sha256 for s in failed}:
            drop("failed_or_rejected", it["quote"], "duplicate", session=it["session"])
            continue
        failed.append(span)
    outdated = []
    for it in parsed["outdated_facts"]:
        try:
            old = locate(it["old_quote"], ctx, it["old_session_id"])
            new = locate(it["new_quote"], ctx, it["new_session_id"])
            outdated.append(K.OutdatedFact(old_span=old, new_span=new))
        except SpanRejected as exc:
            drop("outdated_fact", it["old_quote"] + "\x00" + it["new_quote"], exc.reason)
        except ValueError:
            drop("outdated_fact", it["old_quote"] + "\x00" + it["new_quote"], "correction_not_later")
    method_spans = []
    for it in parsed["method_evidence"]:
        try:
            method_spans.append(locate(it["quote"], ctx, ctx.prefix.session_id))
        except SpanRejected as exc:
            drop("method_evidence", it["quote"], exc.reason)
    method_need = parsed["method_need"]
    if method_need is not None and not method_spans:
        drops.append(dict(kind="method_need", quote_sha256=None, reason="method_without_verified_evidence"))
        method_need = None
    if method_need is None:
        method_spans = []
    stratum = derive_stratum(items, failed, outdated, method_need)
    card = K.NeedCard(prefix_id=ctx.prefix.prefix_id, stratum=stratum, history_items=tuple(items),
                      failed_or_rejected=tuple(failed), outdated_facts=tuple(outdated),
                      method_need=method_need, risk_flags=tuple(parsed["risk_flags"]),
                      writer_identity=writer, input_sha256=pack["pack_sha256"],
                      span_validation_status="verified")
    card.verify_evidence(ctx.prefix, ctx.sources)
    required, optional = set(), set()
    for h, kind in zip(items, kinds):
        (required if h.role in HISTORY_NEED_ROLES else optional).add(RESOURCE_KINDS[kind])
    if failed:
        required.add("ME")
    if outdated:
        required.add("MP")
    if method_need is not None:
        required.add("RS")
    optional -= required
    n_proposed = sum(len(parsed[k]) for k in ("history_items", "failed_or_rejected",
                                              "outdated_facts", "method_evidence"))
    return dict(
        schema=ENVELOPE_SCHEMA, status="ok", prefix_id=ctx.prefix.prefix_id,
        owner_id=ctx.prefix.owner_id, session_id=ctx.prefix.session_id,
        fold=ctx.row["assignment"]["fold"], needcard=card, needcard_sha256=card.sha256,
        writer_identity=writer, pack_sha256=pack["pack_sha256"], raw_output_sha256=parsed["raw_sha256"],
        writer_claimed_stratum=parsed["stratum"], derived_stratum=stratum,
        stratum_conflict=parsed["stratum"] != stratum,
        head_needs=dict(required=[h for h in HEADS if h in required],
                        optional=[h for h in HEADS if h in optional]),
        method_evidence=tuple(method_spans), drops=drops, n_proposed=n_proposed,
        n_dropped=len(drops), visibility_scope="evaluation_only",
        review_status="unverified", evidence_tier="engineering_only")


def failed_envelope(ctx: PrefixContext, pack: dict, *, writer: str, errors: list[str]) -> dict:
    return dict(schema=ENVELOPE_SCHEMA, status="writer_failed", prefix_id=ctx.prefix.prefix_id,
                owner_id=ctx.prefix.owner_id, session_id=ctx.prefix.session_id,
                fold=ctx.row["assignment"]["fold"], needcard=None, needcard_sha256=None,
                writer_identity=writer, pack_sha256=pack["pack_sha256"], derived_stratum=None,
                errors=errors, visibility_scope="evaluation_only", evidence_tier="engineering_only")


def run_writer(ctx: PrefixContext, pack: dict, generate: Callable[[list[dict]], str], *,
               writer: str, retries: int = 1) -> dict:
    """``generate(messages) -> text``; one re-ask on a malformed card, then ``writer_failed``."""
    messages, errors = render_messages(pack), []
    for _ in range(1 + retries):
        try:
            return assemble(ctx, pack, parse_output(generate(messages), pack), writer=writer)
        except WriterOutputError as exc:
            errors.append(str(exc))
    return failed_envelope(ctx, pack, writer=writer, errors=errors)
