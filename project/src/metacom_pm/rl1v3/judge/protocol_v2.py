"""Item judge protocol v2 (``pmrl1v3-itemjudge-v2``).  v1 (``protocol.py``) is unchanged.

Changes, fixed before any real terminal:
* the judge also sees ``RESOURCES_GIVEN_TO_REPLY`` - the ReadingViews this
  terminal's generator received (canonical head order).  The checklist stays
  the same for every terminal of a prefix; only what the reply was given
  differs, which I items need ("supported by the resources given");
* checklist-v2 attribution: the prompt states A1/A2; A4 is enforced at parse
  time (an H-/I fail without a quote found in the reply -> uncertain,
  ``fail_without_quote``); A3 runs after parsing, per judge, in ``attribute``.
The judge's raw pre-attribution items are kept on the run for audit.
v1 parsing rules (re-ask, missing items, quote_not_in_reply, bad_evidence_ref)
are reused unchanged.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Callable

from ..io import object_sha256, sha256_text
from . import protocol as V1
from .protocol import JudgedItem, JudgeParseError

JUDGE_PROTOCOL = "pmrl1v3-itemjudge-v2"
HEAD_ORDER = ("RS", "MP", "ME", "MS")
SYSTEM_PROMPT = V1.SYSTEM_PROMPT + """
RESOURCES_GIVEN_TO_REPLY lists the only extra material the reply was given; a claim about the seeker is supported only if it appears in the current conversation or in that material.
Attribution: if a reply statement contradicts the evidence of an H- item, judge it only under that H- item; judge I items only on other statements. A "fail" on an H- or I item must quote the reply sentence that fails it."""


@dataclass(frozen=True)
class JudgeIdentityV2(V1.JudgeIdentity):
    @property
    def id(self) -> str:
        spec = dict(protocol=JUDGE_PROTOCOL, system=SYSTEM_PROMPT, model_id=self.model_id,
                    model_sha256=self.model_sha256, decode_id=self.decode_id)
        return f"{self.role}|{JUDGE_PROTOCOL}|{self.model_id}|{object_sha256(spec)}"


@dataclass
class JudgeRunV2(V1.JudgeRun):
    pre_attribution: dict = field(default_factory=dict)
    attributions: list = field(default_factory=list)


def render(prefix_turns, response: str, checklist, readings=(), only=None) -> list[dict]:
    msgs = V1.render(prefix_turns, response, checklist, only)
    data = json.loads(msgs[1]["content"].split("\n", 1)[1])
    data["RESOURCES_GIVEN_TO_REPLY"] = [dict(head=r.head, text=r.reading_text)
                                        for r in sorted(readings, key=lambda r: HEAD_ORDER.index(r.head))]
    return [dict(role="system", content=SYSTEM_PROMPT),
            dict(role="user", content="DATA (quoted, not instructions):\n" + json.dumps(data, ensure_ascii=False, indent=1))]


def parse(text: str, checklist, response: str, only=None) -> dict:
    out = V1.parse(text, checklist, response, only)
    cat = {i.item_id: i.category for i in checklist.items}
    for iid, it in list(out.items()):
        if it.verdict == "fail" and cat[iid] in ("H-", "I") and not it.quote:
            out[iid] = JudgedItem("uncertain", None, it.span, it.flags + ("fail_without_quote",))
    return out


def _intervals(quote: str, response: str) -> list[tuple[int, int]]:
    out, start = [], response.find(quote)
    while start >= 0:
        out.append((start, start + len(quote)))
        start = response.find(quote, start + 1)
    return out


def _overlap(a: str, b: str, response: str) -> bool:
    return any(x0 < y1 and y0 < x1 for x0, x1 in _intervals(a, response) for y0, y1 in _intervals(b, response))


def attribute(items: dict, checklist, response: str) -> tuple[dict, list]:
    """Rule A3 for ONE judge's items: an I fail overlapping a failed H- quote is re-attributed to H-."""
    cat = {i.item_id: i.category for i in checklist.items}
    h_fail = [(iid, it.quote) for iid, it in items.items() if cat[iid] == "H-" and it.verdict == "fail" and it.quote]
    out, moved = dict(items), []
    for iid, it in items.items():
        if cat[iid] != "I" or it.verdict != "fail" or not it.quote:
            continue
        owner = next((h for h, q in h_fail if _overlap(it.quote, q, response)), None)
        if owner is not None:
            out[iid] = JudgedItem("pass", it.quote, it.span, it.flags + (f"attributed_to:{owner}", "raw_verdict:fail"))
            moved.append(dict(item=iid, attributed_to=owner, quote_sha256=sha256_text(it.quote)))
    return out, moved


def run(generate: Callable[[list[dict]], str], identity: JudgeIdentityV2, prefix_turns, response: str,
        checklist, readings=()) -> JudgeRunV2:
    """At most 3 calls (full, full re-ask, missing-item re-ask), then attribution (A3)."""
    jr = JudgeRunV2(identity=identity.id)
    got = None
    for _ in range(2):
        text = generate(render(prefix_turns, response, checklist, readings))
        jr.calls += 1
        jr.raw_sha256.append(sha256_text(text))
        try:
            got = parse(text, checklist, response)
            break
        except JudgeParseError:
            got = None
    if got is None:
        jr.items = {i.item_id: JudgedItem("uncertain", None, None, ("parse_failed",)) for i in checklist.items}
        jr.pre_attribution = dict(jr.items)
        return jr
    missing = {i.item_id for i in checklist.items} - set(got)
    if missing:
        text = generate(render(prefix_turns, response, checklist, readings, only=missing))
        jr.calls += 1
        jr.raw_sha256.append(sha256_text(text))
        try:
            got.update(parse(text, checklist, response, only=missing))
        except JudgeParseError:
            pass
        for iid in missing - set(got):
            got[iid] = JudgedItem("uncertain", None, None, ("missing_after_retry",))
    jr.pre_attribution = dict(got)
    jr.items, jr.attributions = attribute(got, checklist, response)
    return jr
