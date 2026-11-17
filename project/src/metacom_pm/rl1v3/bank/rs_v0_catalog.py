"""Unverified ESConv strategy labels for engineering NeedCard inputs, not A4.

Only original supporter annotations in already-admitted train cases establish
categories. Legacy strategy/treatment IDs are lineage, never new methods or
instructions. Source-family IDs and writer category IDs are separate fields.
"""
from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

from ..io import canonical_json, object_sha256, write_json_once
from ..sources.source_registry import PinnedInputs, span

PROTOCOL = "pmrl1v3-rs-v0-strategy-catalog-1"
SCHEMA_VERSION = "rs-v0-catalog-1"
SCOPE = "engineering_needcard_input_only"
LABELS = {
    "Question": "question",
    "Restatement or Paraphrasing": "restatement_or_paraphrasing",
    "Reflection of feelings": "reflection_of_feelings",
    "Self-disclosure": "self_disclosure",
    "Affirmation and Reassurance": "affirmation_and_reassurance",
    "Providing Suggestions": "providing_suggestions",
    "Information": "information",
    "Others": "others",
}


def classify(label):
    """Unseen/missing annotation is unknown, never guessed from utterance text."""
    return LABELS.get(label, "unknown")


@dataclass(frozen=True)
class Catalog:
    data: dict

    @property
    def catalog_id(self):return self.data["catalog_id"]

    @property
    def sha256(self):return object_sha256(self.data)

    @property
    def entries(self):return tuple(self.data["entries"])

    @property
    def selectable(self):return tuple(e["family_id"] for e in self.entries if e["writer_selectable"])

    @property
    def bank_version(self):return self.data["bank_version"]

    def as_dict(self):
        """B v2 protocol-compatible public label catalog; no case text or IDs."""
        return dict(protocol=PROTOCOL, catalog_id=self.catalog_id, sha256=self.sha256,
                    bank_version=self.bank_version, quality="unverified", status=SCOPE,
                    unknown_value="unknown", entries=[{k:e[k] for k in (
                        "family_id", "label", "n_cases", "n_strategy_turns", "definition",
                        "definition_source", "writer_selectable", "note")} for e in self.entries])

    def for_needcard_writer(self):
        """Existing B v1 input adapter. No writer/model call or method validation."""
        from ..needs.protocol import MethodCatalog
        return MethodCatalog(catalog_id=self.catalog_id, families=tuple(
            (e["family_id"], f'ESConv annotation label: {e["label"]}; unverified; definition unknown; '
             'engineering category only, not a validated method or professional advice.')
            for e in self.entries if e["writer_selectable"]))


def build(root, bank):
    """Build the small catalog only; source registry and bank remain immutable."""
    pinned = PinnedInputs(root)
    raw = pinned.read("raw_esconv")
    evidence, cases = [], []
    strategy_ids, treatment_ids = set(), set()
    for record in sorted((r for r in bank.records if r.head == "RS"), key=lambda r:r.record_id):
        source_ids = bank.source_ids[record.record_id]
        if len(source_ids) != 1:
            raise ValueError("RS-v0 requires exactly one original case source")
        entry = bank.registry.by_id[source_ids[0]]
        source = entry.source
        if source.source_split != "train" or source.excluded_for_overlap or source.family_id in bank.registry.excluded_families:
            raise ValueError("RS-v0 excluded source family/split")
        if source.dataset != "ESConv" or record.view != "case" or record.related_claim_ids:
            raise ValueError("RS-v0 must use original ESConv cases without propagated relations")
        ordinal = int(source.session_id.removeprefix("esconv_"))
        dialogue = raw[ordinal]["dialog"]
        if source.raw_sha256 != pinned.used[pinned.config["raw_esconv"]] or len(dialogue) != len(source.turns):
            raise ValueError("original annotation source identity mismatch")
        body = json.loads(record.body)
        sids, tids = sorted(body["strategy_ids"]), sorted(body["treatment_ids"])
        strategy_ids.update(sids); treatment_ids.update(tids)
        case_evidence = []
        for i, turn in enumerate(dialogue):
            st = source.turns[i]
            if turn["content"] != st.text or turn["speaker"] != st.role:
                raise ValueError("original annotation turn differs from registry")
            if st.role != "supporter":continue
            label = turn.get("annotation", {}).get("strategy")
            category = classify(label)
            ref = json.loads(canonical_json(span(source, i)))
            row = dict(record_id=record.record_id, source_id=entry.source_id,
                       source_family=source.family_id, session_id=source.session_id,
                       original_turn_index=entry.original_turn_indices[i], original_label=label,
                       category_id=category, source_span=ref)
            row["evidence_id"] = "rs-tag:"+object_sha256(row)
            evidence.append(row); case_evidence.append(row["evidence_id"])
        cases.append(dict(record_id=record.record_id, source_id=entry.source_id,
                          source_family=source.family_id, evidence_ids=case_evidence,
                          legacy_strategy_ids=sids, legacy_treatment_ids=tids))
    groups = sorted({r["category_id"] for r in evidence})
    entries = []
    for category in groups:
        rows = [r for r in evidence if r["category_id"] == category]
        label = next((label for label, cid in LABELS.items() if cid == category), "unknown")
        entries.append(dict(family_id=category, label=label, definition="unknown", definition_source=None,
                            writer_selectable=category not in ("unknown", "others"), quality="unverified",
                            note="historical source annotation only; not a validated method or advice",
                            n_cases=len({r["record_id"] for r in rows}), n_strategy_turns=len(rows),
                            case_ids=sorted({r["record_id"] for r in rows}),
                            source_families=sorted({r["source_family"] for r in rows}),
                            evidence_ids=[r["evidence_id"] for r in rows]))
    payload = dict(protocol=PROTOCOL, schema_version=SCHEMA_VERSION, quality="unverified", scope=SCOPE,
                   is_a4_method_catalog=False, source_version=bank.registry.version,
                   bank_version=bank.version, index_version=bank.index_version, inputs=pinned.used,
                   entries=entries, cases=cases, evidence=evidence,
                   counts=dict(cases=len(cases), annotated_supporter_turns=len(evidence),
                               label_counts=dict(Counter(r["category_id"] for r in evidence)),
                               selectable_categories=sum(e["writer_selectable"] for e in entries),
                               unknown=sum(r["category_id"] == "unknown" for r in evidence),
                               linked_legacy_strategy_ids=len(strategy_ids),
                               linked_legacy_treatment_ids=len(treatment_ids)),
                   limitations=["unverified annotation categories, definitions unknown",
                                "legacy strategies/treatments are overlapping lineage layers, not independent methods",
                                "no clinical, causal, efficacy or recall-quality validation",
                                "previously exposed development data; not independent evaluation evidence"])
    return Catalog(dict(payload, catalog_id=PROTOCOL+":"+object_sha256(payload)))


def save(catalog, path):
    write_json_once(Path(path), catalog.data)


def load(path, *, root, bank):
    data = json.loads(Path(path).read_text())
    payload = {k:v for k,v in data.items() if k != "catalog_id"}
    if data.get("catalog_id") != PROTOCOL+":"+object_sha256(payload):
        raise ValueError("RS-v0 catalog content identity mismatch")
    # Verification includes annotations, source spans, train/family gates and all
    # legacy mappings; a re-signed forged span/category cannot bypass provenance.
    expected = build(root, bank)
    if canonical_json(expected.data) != canonical_json(data):
        raise ValueError("RS-v0 catalog differs from pinned original annotations")
    return expected
