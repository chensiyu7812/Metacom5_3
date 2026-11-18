"""Static output-size diagnostic for judge v3 (``{errors, items}``).  No judge is run.

Builds the answers a v3 judge would have to emit for a given checklist shape and reply and
returns their native token counts, so the J1 output budget can be compared with the minimum
the frozen format needs.  Pure functions; the token counter is passed in.
"""
from __future__ import annotations

import json

ROW_FIELDS = ("id", "verdict", "quote", "evidence", "errors")
ERROR_FIELDS = ("id", "kind", "quotes", "evidence")
REQUIRED_FOR_FAIL = {"H-": "errors: >= 1 valid ledger id (else uncertain)",
                     "I": "errors: >= 1 valid ledger id (else uncertain)",
                     "H+": "none beyond the row fields", "R": "none beyond the row fields",
                     "G": "none beyond the row fields", "S": "none beyond the row fields"}
SCENARIOS = ("minimal", "quote_every_item", "all_integrity_fail", "worst")


def item_ids(counts: dict) -> list[tuple[str, str]]:
    """``counts``: category -> number of items, in checklist order H+/H-/R/G/I/S."""
    return [(f"{c}:{n}", c) for c in ("H+", "H-", "R", "G", "I", "S") for n in range(1, counts.get(c, 0) + 1)]


def answer(items: list[tuple[str, str]], sentences: list[str], scenario: str, *, n_evidence: int = 0,
           pretty: bool = False) -> str:
    """The JSON text a v3 judge returns for ``scenario`` (see ``SCENARIOS``)."""
    longest = max(sentences, key=len)
    errors, rows = [], []
    ev = f"E{max(n_evidence, 1)}" if n_evidence else ""
    for k, (iid, cat) in enumerate(items):
        quote = "" if scenario == "minimal" else longest if scenario == "worst" else sentences[k % len(sentences)]
        fail = scenario in ("all_integrity_fail", "worst") and cat in ("H-", "I")
        errs = []
        if fail:
            xid = f"X{len(errors) + 1}"
            span = longest if scenario == "worst" else sentences[k % len(sentences)]
            quotes = [span, sentences[(k + 1) % len(sentences)]] if scenario == "worst" else [span]
            errors.append(dict(id=xid, kind="history_conflict" if cat == "H-" else "fabricated_history",
                               quotes=quotes, evidence=ev if cat == "H-" else ""))
            errs = [xid]
        rows.append(dict(id=iid, verdict="fail" if fail else "pass", quote=quote,
                         evidence=ev if (scenario != "minimal" and cat in ("H+", "H-", "R")) else "", errors=errs))
    out = dict(errors=errors, items=rows)
    return json.dumps(out, ensure_ascii=False, indent=1) if pretty else json.dumps(out, ensure_ascii=False,
                                                                                    separators=(",", ":"))


def table(count_tokens, shapes: dict, replies: dict, *, budgets=(800,)) -> list[dict]:
    """Token count per (checklist shape, reply, scenario, compact/pretty) and whether each budget fits."""
    out = []
    for shape, counts in shapes.items():
        items = item_ids(counts)
        for rname, sentences in replies.items():
            for sc in SCENARIOS:
                for pretty in (False, True):
                    n = count_tokens(answer(items, sentences, sc, n_evidence=sum(counts.get(c, 0) for c in ("H+", "H-", "R")) * 2,
                                            pretty=pretty)) + 1          # + end-of-turn token
                    out.append(dict(shape=shape, items=len(items), reply=rname, scenario=sc,
                                    format="pretty" if pretty else "compact", output_tokens=n,
                                    fits={str(b): n <= b for b in budgets}))
    return out
