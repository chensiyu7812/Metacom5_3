"""B29.1: MP source ontology decision surface.

Diagnostic only. Compares two candidate *source ontologies* for the MP
(Profile Memory) head:

- **A -- conversation-derived** (the current, already-primary approach in
  ``memory/mp.py``): a profile fact only counts if the seeker is shown to
  have literally said it, in-session, matched by a small precision-first
  regex set.
- **B -- persistent-profile-store (proposed, NOT adopted)**: EvoEmo's
  per-owner ``basic_info`` block (name/age/gender/job/education/
  nationality/location), read here for the first time in this lane, purely
  to make the comparison possible.

This module never wires ontology B into ``memory/mp.py``, ``candidates/``,
or ``features/zero_outcome_census.py``, and never changes what the primary
MP compiler extracts (still 3 unique candidates / 3 owners / 214 edges --
verified directly against the sanitized artifact and census in this
module's own tests, not asserted from memory). ``_load_raw_basic_info_only``
is the ONLY reader of ``basic_info`` anywhere in this lane, and reads
nothing else from the raw file (no ``dialog_history``/``questions``/
``summaries``/``subsequent_topics``) -- it exists purely to compute this
diagnostic comparison and must never be imported by anything in the
runtime candidate/feature surface.

Ontology B is reported with two structural findings that argue against
adopting it as primary without further researcher decision:

1. **No strict-past availability time is provable.** ``basic_info`` is one
   flat dict per owner with no session id, timestamp, or version -- there
   is no mechanical way to determine when (or whether) a given fact became
   true relative to any target's cutoff, unlike ontology A's session-
   grounded ``chronological_rank``/``observed_at``.
2. **Source-side-privileged / gold-adjacent risk.** ``memory/mp.py``'s own
   docstring already established that ``basic_info`` never appears in the
   dialogue text verbatim (checked against the full corpus) -- it is
   dataset-author persona metadata, not something the seeker is shown
   saying, the same class of leak as the historical ESConv ``situation``-
   field incident this project has already found and fixed twice. B28R's
   official-harness audit further confirmed that ``basic_info``'s non-
   ``name`` fields are simulator/evaluator-only in the official ES-MemEval
   harness (never shown to the tested supporter at all) -- using them as an
   MP feature would inject a field source-side-privileged relative to what
   the officially-tested system itself ever sees.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.features.zero_outcome_census import build_census, summarize_census
from metacom_pm.paper1.memory.mp import extract_profile_disclosures

RAW_BASIC_INFO_FIELDS: tuple[str, ...] = (
    "name",
    "age",
    "gender",
    "job",
    "education",
    "nationality",
    "location",
)

ONTOLOGY_A_CONVERSATION_DERIVED = "A_conversation_derived"
ONTOLOGY_B_PERSISTENT_PROFILE_STORE_PROPOSED = "B_persistent_profile_store_proposed"

STATUS_PRIMARY_MP_CURRENT = "PRIMARY_MP_CURRENT"
STATUS_PROPOSED_NOT_ADOPTED = "PROPOSED_NOT_ADOPTED"


def _load_raw_basic_info_only(evo_path: Path) -> dict[str, dict[str, Any]]:
    """The ONLY reader of ``basic_info`` in this lane.

    Reads exactly ``id`` and ``basic_info`` per raw user record -- never
    ``dialog_history``/``questions``/``summaries``/``subsequent_topics``/
    ``event_experience``/``social_relationship``. Diagnostic/proposal-only:
    the result of this function must never reach ``candidates/`` or
    ``features/zero_outcome_census.py``.
    """

    raw = json.loads(evo_path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("ES-MemEval/EvoEmo source must be a JSON array of user records")
    return {
        user["id"]: {field: user["basic_info"][field] for field in RAW_BASIC_INFO_FIELDS} for user in raw
    }


@dataclass(frozen=True)
class MpSourceOntologyRow:
    ontology: str
    status: str
    unique_candidate_count: int
    owners_with_candidates: int
    owners_total: int
    target_edges: int | None
    target_coverage_fraction: float | None
    coverage_semantics_note: str
    source_provenance: str
    strict_past_availability_time_provable: bool
    strict_past_note: str
    future_gold_source_privileged_risk: str
    stable_fields: tuple[str, ...]
    fields_missing_versioning_or_effective_time: tuple[str, ...]

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-mp-source-ontology-row-v1",
            "ontology": self.ontology,
            "status": self.status,
            "unique_candidate_count": self.unique_candidate_count,
            "owners_with_candidates": self.owners_with_candidates,
            "owners_total": self.owners_total,
            "target_edges": self.target_edges,
            "target_coverage_fraction": self.target_coverage_fraction,
            "coverage_semantics_note": self.coverage_semantics_note,
            "source_provenance": self.source_provenance,
            "strict_past_availability_time_provable": self.strict_past_availability_time_provable,
            "strict_past_note": self.strict_past_note,
            "future_gold_source_privileged_risk": self.future_gold_source_privileged_risk,
            "stable_fields": list(self.stable_fields),
            "fields_missing_versioning_or_effective_time": list(self.fields_missing_versioning_or_effective_time),
        }


def _ontology_a_row(users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...]) -> MpSourceOntologyRow:
    unique_ids: set[str] = set()
    owners_with: set[str] = set()
    for user in users:
        disclosures = extract_profile_disclosures(user)
        if disclosures:
            owners_with.add(user.owner_id)
        for d in disclosures:
            unique_ids.add(f"{d.owner_id}:{d.session_id}:{d.turn.idx}")

    census_rows = build_census(users, targets)
    summary = summarize_census(census_rows)
    mp_summary = summary["per_head"]["MP"]

    return MpSourceOntologyRow(
        ontology=ONTOLOGY_A_CONVERSATION_DERIVED,
        status=STATUS_PRIMARY_MP_CURRENT,
        unique_candidate_count=len(unique_ids),
        owners_with_candidates=len(owners_with),
        owners_total=len(users),
        target_edges=mp_summary["target_candidate_edges"],
        target_coverage_fraction=mp_summary["coverage_fraction"],
        coverage_semantics_note=(
            "Real, non-vacuous strict-past coverage: a target is only "
            "'covered' if a qualifying self-disclosure exists in a session "
            "strictly before that target's cutoff_rank."
        ),
        source_provenance=(
            "Seeker turn text itself (memory/mp.py's is_profile_disclosure "
            "regex set), traceable to an exact session_id/turn.idx."
        ),
        strict_past_availability_time_provable=True,
        strict_past_note=(
            "Every candidate carries session_chronological_rank/observed_at "
            "from the session it was said in -- the same strict-past gate "
            "already used by candidates/compilers.py."
        ),
        future_gold_source_privileged_risk=(
            "LOW: content is exactly what the seeker is shown saying, "
            "in-session -- not a dataset-author annotation, and not a field "
            "the official harness ever hides from any consumer differently "
            "than raw dialogue text itself."
        ),
        stable_fields=(),
        fields_missing_versioning_or_effective_time=(),
    )


def _ontology_b_row(
    users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...], evo_path: Path
) -> MpSourceOntologyRow:
    raw_basic_info = _load_raw_basic_info_only(evo_path)
    owners_total = len(users)
    owners_with = {owner_id for owner_id, fields in raw_basic_info.items() if fields}
    unique_fact_count = sum(len(fields) for fields in raw_basic_info.values())

    targets_by_owner: dict[str, int] = {}
    for t in targets:
        targets_by_owner[t.owner_id] = targets_by_owner.get(t.owner_id, 0) + 1
    # Hypothetical edges IF ontology B were adopted with every field treated
    # as unconditionally available from the owner's very first target
    # onward (the only assumption possible, since there is no session/date
    # binding to gate on) -- one edge per (target, field).
    hypothetical_edges = sum(
        targets_by_owner.get(owner_id, 0) * len(RAW_BASIC_INFO_FIELDS) for owner_id in raw_basic_info
    )

    return MpSourceOntologyRow(
        ontology=ONTOLOGY_B_PERSISTENT_PROFILE_STORE_PROPOSED,
        status=STATUS_PROPOSED_NOT_ADOPTED,
        unique_candidate_count=unique_fact_count,
        owners_with_candidates=len(owners_with),
        owners_total=owners_total,
        target_edges=hypothetical_edges,
        target_coverage_fraction=1.0,
        coverage_semantics_note=(
            "VACUOUS/TRIVIAL coverage, not a real temporal claim: because "
            "basic_info carries no session/timestamp/version, there is no "
            "mechanical way to gate it by strict-past cutoff at all -- "
            "adopting it means every field is 'available' for every target "
            "unconditionally, which is exactly why "
            "strict_past_availability_time_provable is False below. This "
            "1.0 must never be compared against ontology A's real "
            "coverage_fraction as if they measured the same thing."
        ),
        source_provenance=(
            "EvoEmo per-owner basic_info block (dataset-author persona "
            "metadata) -- read here only by "
            "mp_source_ontology_audit._load_raw_basic_info_only, the sole "
            "reader of this field in the entire lane."
        ),
        strict_past_availability_time_provable=False,
        strict_past_note=(
            "basic_info is one flat dict per owner with no session id, "
            "timestamp, or version field at all -- there is no mechanical "
            "way to determine when, or whether, a given fact became true "
            "relative to any target's cutoff_rank."
        ),
        future_gold_source_privileged_risk=(
            "HIGH: memory/mp.py's own docstring already established that "
            "basic_info never appears verbatim in seeker dialogue text "
            "(checked against the full corpus) -- it is dataset-author "
            "persona metadata, the same leak class as the historical "
            "ESConv 'situation'-field incident this project already fixed "
            "once. B28R's official-harness audit further confirmed that "
            "basic_info's non-name fields are simulator/evaluator-only in "
            "the official ES-MemEval harness -- never shown to the tested "
            "supporter at all -- so using them as an MP feature would be "
            "source-side-privileged relative to what the officially-tested "
            "system itself ever sees. Absent any effective-time field, this "
            "project also cannot rule out a given fact only becoming true "
            "at some point in the seeker's (unobserved) timeline, which is "
            "an unprovable-but-real future-information risk relative to an "
            "early target's cutoff."
        ),
        stable_fields=("name", "gender", "nationality"),
        fields_missing_versioning_or_effective_time=RAW_BASIC_INFO_FIELDS,
    )


def build_mp_source_ontology_rows(
    users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...], evo_path: Path
) -> tuple[MpSourceOntologyRow, MpSourceOntologyRow]:
    return (_ontology_a_row(users, targets), _ontology_b_row(users, targets, evo_path))


def build_mp_source_ontology_report(
    users: tuple[MemorySourceUser, ...], targets: tuple[Target, ...], evo_path: Path
) -> dict[str, Any]:
    rows = build_mp_source_ontology_rows(users, targets, evo_path)
    return {
        "protocol": "pm-paper1-mp-source-ontology-report-v1",
        "status": "B29_1_DIAGNOSTIC_ONLY_ONTOLOGY_B_NOT_ADOPTED",
        "outcome_calls": 0,
        "note": (
            "Ontology B (persistent-profile-store, basic_info) is proposed "
            "here for comparison only -- it is never wired into "
            "memory/mp.py, candidates/, or features/zero_outcome_census.py. "
            "Ontology A's numbers (3 unique / 3 owners / 214 edges) are the "
            "actual, unchanged primary MP -- recomputed directly in this "
            "report, not hardcoded from memory."
        ),
        "stable_fields_caveat": (
            "'stable_fields' for ontology B (name/gender/nationality) is a "
            "domain-knowledge HYPOTHESIS about which fields are less likely "
            "to change over a support-seeking timeframe, not something "
            "verified from the data -- basic_info carries no dates to "
            "verify stability against at all. job/education/location are "
            "plausibly time-varying by the same domain-knowledge reasoning, "
            "also unverified."
        ),
        "ontologies": [r.to_manifest_row() for r in rows],
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def write_mp_source_ontology_manifest(report: dict[str, Any], out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "es_memeval_public_mp_source_ontology_audit_v1.json"
    path.write_text(_canonical(report) + "\n", encoding="utf-8")
    return path
