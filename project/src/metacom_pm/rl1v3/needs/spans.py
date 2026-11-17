"""Exact quote -> C0 ``SourceSpan`` resolution for NeedCard / checklist evidence.

Rules (V3.1 §6.1/§6.8.1, RESOURCE_SPEC I1/I2/T13):
* exact Unicode substring match only (no normalisation, no fuzzy match);
* the current session is searched only up to the inclusive ``cut_turn``;
  strictly-past sessions must be complete same-owner sessions of the prefix;
* a quote that occurs more than once (in one or several turns) is ambiguous and
  fails closed unless the caller pins the turn and it is unique there;
* every resolved span is re-checked with ``contracts.verify_legal_span``.
A rejected quote is reported with a reason; it is never silently repaired.
"""
from __future__ import annotations

from ..io import sha256_text
from .sources import PrefixContext

MIN_QUOTE_CHARS = 8
REASONS = ("too_short", "unknown_session", "not_found", "future_turn", "ambiguous",
           "speaker_mismatch", "illegal")


class SpanRejected(ValueError):
    def __init__(self, reason: str, detail: str = ""):
        assert reason in REASONS, reason
        super().__init__(f"{reason}: {detail}")
        self.reason = reason


def _occurrences(text: str, quote: str) -> list[int]:
    out, i = [], text.find(quote)
    while i >= 0:
        out.append(i)
        i = text.find(quote, i + 1)
    return out


def locate(quote: str, ctx: PrefixContext, session_id: str, *, speaker: str | None = None,
           turn_index: int | None = None):
    from .. import contracts as K
    if not isinstance(quote, str) or len(quote.strip()) < MIN_QUOTE_CHARS:
        raise SpanRejected("too_short", repr(quote)[:40])
    source = ctx.session(session_id)
    if source is None:
        raise SpanRejected("unknown_session", session_id)
    current = session_id == ctx.prefix.session_id
    last = ctx.prefix.cut_turn if current else len(source.turns) - 1
    hits = [(t.turn_index, start) for t in source.turns[:last + 1]
            for start in _occurrences(t.text, quote)]
    if turn_index is not None:
        hits = [h for h in hits if h[0] == turn_index]
    if not hits:
        if current and any(_occurrences(t.text, quote) for t in source.turns[last + 1:]):
            raise SpanRejected("future_turn", "quote only after the cut")
        raise SpanRejected("not_found", session_id)
    if speaker is not None:
        hits = [h for h in hits if source.turns[h[0]].role == speaker]
        if not hits:
            raise SpanRejected("speaker_mismatch", speaker)
    if len(hits) != 1:
        raise SpanRejected("ambiguous", f"{len(hits)} occurrences")
    ti, start = hits[0]
    turn = source.turns[ti]
    span = K.SourceSpan(
        source_key=f"{source.dataset}:{source.owner_id}:{source.session_id}:{ti}",
        owner_id=source.owner_id, session_id=source.session_id,
        source_rank=source.chronological_rank, turn_index=ti, speaker=turn.role,
        start_char=start, end_char=start + len(quote), exact_quote=quote,
        raw_turn_sha256=sha256_text(turn.text))
    try:
        K.verify_legal_span(span, ctx.prefix, source)
    except ValueError as exc:
        raise SpanRejected("illegal", str(exc)) from exc
    return span
