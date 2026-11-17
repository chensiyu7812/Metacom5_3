"""RS-v0 strategy-label catalog for the NeedCard writer, derived mechanically from WS-A bank-v0.

What WS-A bank-v0 actually provides for RS: 875 complete ESConv train dialogues
(``view = case``), each body listing the legacy ``strategy_ids`` (rows of the
pinned ``strategy_cards_v1_5``) and ``treatment_ids``.  It is NOT a method
catalog (WS-A says so explicitly) and no label has an expert-reviewed
definition.  This module therefore only lists the historical ESConv strategy
labels that occur in admitted cases, with counts, and records every
definition as ``unknown``.  It invents no description, method card or
validity claim.  ``Others`` is a residual label with no content and is not
offered to the writer.  The writer may answer ``unknown`` when a method-type
need is evidenced but no label fits.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass

from ..io import object_sha256

CATALOG_PROTOCOL = "pmrl1v3-rs-v0-strategy-labels-v1"
UNKNOWN = "unknown"
RESIDUAL_LABELS = ("Others",)
STATUS = ("derived_by_wsb_from_bank_v0_rs_cases; not a WS-A MethodCatalog delivery; "
          "historical ESConv strategy tags; definitions unknown; not expert-reviewed")
GUIDANCE_TEMPLATE = ("Use the emotional-support strategy '{}' when it fits the visible dialogue. Adapt it naturally; "
                     "do not copy private facts or assume information that the user has not disclosed.")


def family_id(label: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", label.casefold()).strip("_")


@dataclass(frozen=True)
class LabelCatalog:
    catalog_id: str
    bank_version: str
    entries: tuple            # dicts: family_id, label, n_cases, n_strategy_turns, definition, writer_selectable

    @property
    def selectable(self) -> tuple[str, ...]:
        return tuple(e["family_id"] for e in self.entries if e["writer_selectable"])

    @property
    def sha256(self) -> str:
        return object_sha256(dict(catalog_id=self.catalog_id, bank_version=self.bank_version, entries=self.entries))

    def as_dict(self) -> dict:
        return dict(protocol=CATALOG_PROTOCOL, catalog_id=self.catalog_id, sha256=self.sha256,
                    bank_version=self.bank_version, status=STATUS, unknown_value=UNKNOWN,
                    entries=list(self.entries))


def derive(bank, strategy_rows) -> tuple[LabelCatalog, dict]:
    """``strategy_rows``: the pinned strategy_cards_v1_5 rows (hash-checked by the caller)."""
    by_id = {r["strategy_id"]: r for r in strategy_rows}
    cases, turns, missing, generic = Counter(), Counter(), 0, True
    rs = [r for r in bank.records if r.head == "RS"]
    for rec in rs:
        body = json.loads(rec.body)
        labels = set()
        for sid in body.get("strategy_ids", ()):
            row = by_id.get(sid)
            if row is None:
                missing += 1
                continue
            labels.add(row["strategy_label"])
            turns[row["strategy_label"]] += 1
            generic &= row["guidance_text"] == GUIDANCE_TEMPLATE.format(row["strategy_label"])
        for lab in labels:
            cases[lab] += 1
    entries = tuple(dict(family_id=family_id(lab), label=lab, n_cases=cases[lab], n_strategy_turns=turns[lab],
                         definition=UNKNOWN, definition_source=None,
                         writer_selectable=lab not in RESIDUAL_LABELS,
                         note="residual label without content" if lab in RESIDUAL_LABELS else
                              "historical conversation-strategy tag; not a validated method")
                    for lab in sorted(cases, key=lambda x: (-cases[x], x)))
    cat = LabelCatalog(catalog_id=f"{CATALOG_PROTOCOL}|{bank.version}", bank_version=bank.version, entries=entries)
    audit = dict(rs_cases=len(rs), rs_cases_without_strategy=sum(1 for r in rs if not json.loads(r.body).get("strategy_ids")),
                 strategy_ids_not_in_cards=missing, guidance_text_is_generic_template=generic,
                 labels=len(entries), selectable=len(cat.selectable))
    return cat, audit
