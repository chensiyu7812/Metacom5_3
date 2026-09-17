"""Versioned, blinded human reference and lossless offline rating forms.

This module never calls a provider, constructs effect labels, or ranks responses.
DG history is projected from the sanitized runtime source, independent of arms.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.contracts import TaskType
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Target
from metacom_pm.paper1.evaluation.pairwise_teacher import VERDICTS


PROTOCOL = "paper1-pairwise-teacher-human-sheet-v2"
REFERENCE_PROTOCOL = "paper1-DG-complete-strict-past-human-teacher-reference-v2"
EXCERPT_HEADER = "TASK-RELATED HISTORICAL EXCERPT (not exhaustive):"
HISTORY_HEADER = "COMPLETE PRIOR HISTORY (chronological; consult to verify memory claims):"


def render_session(timestamp: str, turns: list[dict[str, str]]) -> str:
    return f"Prior session [{timestamp}]:\n" + "\n".join(
        f"{turn['role']}: {turn['content']}" for turn in turns
    )


def reference_from_view(view: dict[str, Any]) -> str:
    history = "\n\n".join(
        render_session(session["timestamp"], session["turns"])
        for session in view["sessions"]
    )
    return f"{EXCERPT_HEADER}\n{view['excerpt']}\n\n{HISTORY_HEADER}\n{history}"


def build_dg_reference(
    *, user: MemorySourceUser, target: Target, excerpt: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    if user.owner_id != target.owner_id or target.task_type is not TaskType.DIALOGUE_GENERATION:
        raise ValueError("DG reference owner/task mismatch")
    if not isinstance(excerpt, str) or not excerpt.strip():
        raise ValueError("DG excerpt is missing")
    sessions = sorted(user.sessions, key=lambda s: s.chronological_rank)
    if [s.chronological_rank for s in sessions] != list(range(len(sessions))):
        raise ValueError("DG reference source has duplicate or missing session ranks")
    if not 0 < target.cutoff_rank <= len(sessions):
        raise ValueError("DG reference cutoff is outside the source history")
    past = [s for s in sessions if s.chronological_rank < target.cutoff_rank]
    if len({s.session_id for s in past}) != len(past):
        raise ValueError("DG reference has duplicate session identities")
    if any(a.date > b.date for a, b in zip(past, past[1:])):
        raise ValueError("DG reference chronological ranks disagree with dates")
    view = {
        "excerpt": excerpt,
        "sessions": [
            {
                "timestamp": s.timestamp,
                "turns": [{"role": t.role, "content": t.content} for t in s.turns],
            }
            for s in past
        ],
    }
    if any(t["role"] not in {"seeker", "supporter"} for s in view["sessions"] for t in s["turns"]):
        raise ValueError("unexpected role in DG source history")
    allowed_excerpt_sessions = {
        render_session(s["timestamp"], s["turns"]) for s in view["sessions"]
    }
    pieces = excerpt.split("\n\nPrior session [")
    excerpt_sessions = [pieces[0], *("Prior session [" + p for p in pieces[1:])]
    if any(s not in allowed_excerpt_sessions for s in excerpt_sessions):
        raise ValueError("DG excerpt contains text outside the exact strict-past source sessions")
    rendered = reference_from_view(view)
    # Only this separate coordinator record contains target/source identities.
    audit = {
        "target_id": target.target_id,
        "owner_id": user.owner_id,
        "cutoff_rank": target.cutoff_rank,
        "source_session_ids": [s.session_id for s in past],
        "source_session_ranks": [s.chronological_rank for s in past],
        "session_count": len(past),
        "reference_sha256": sha256_text(rendered),
        "reference_view_sha256": sha256_text(canonical_json(view)),
    }
    return view, audit


def upgrade_human_sheet(
    original: dict[str, Any],
    *,
    instrument: dict[str, Any],
    presentation_targets: dict[str, str],
    dg_views: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if any(i["verdict"] is not None or i["rationale"] is not None for i in original["items"]):
        raise ValueError("cannot upgrade a rated original; preserve it separately")
    sheet = copy.deepcopy(original)
    sheet["protocol"] = PROTOCOL
    sheet["instrument"] = copy.deepcopy(instrument)
    sheet["status"] = "READY_FOR_INDEPENDENT_RATING"
    catalog = {}
    for item in sheet["items"]:
        if item["task"] != "DG":
            continue
        view = dg_views[presentation_targets[item["presentation_id"]]]
        ref = reference_from_view(view)
        ref_id = "history_" + sha256_text(ref)[:24]
        catalog[ref_id] = copy.deepcopy(view)
        item["reference_id"] = ref_id
        item["reference_material"] = ref
    sheet["reference_catalog"] = dict(sorted(catalog.items()))
    validate_reference_catalog(sheet)
    return sheet


def validate_reference_catalog(sheet: dict[str, Any]) -> None:
    used = set()
    for item in sheet["items"]:
        if item["task"] == "DG":
            ref_id = item["reference_id"]
            expected = reference_from_view(sheet["reference_catalog"][ref_id])
            if item["reference_material"] != expected or ref_id != "history_" + sha256_text(expected)[:24]:
                raise ValueError("human display and teacher reference differ")
            used.add(ref_id)
        elif "reference_id" in item:
            raise ValueError("non-DG item acquired a history reference")
    if used != set(sheet["reference_catalog"]):
        raise ValueError("unreferenced history would expose extraneous evidence")


def _without_ratings(sheet: dict[str, Any]) -> dict[str, Any]:
    value = copy.deepcopy(sheet)
    for item in value["items"]:
        # Require both keys; omission is not a legitimate blank answer.
        item["verdict"]
        item["rationale"]
        item["verdict"] = item["rationale"] = None
    return value


def validate_rated_sheet(
    original: dict[str, Any], rated: dict[str, Any], *, require_complete: bool = True
) -> dict[str, int]:
    try:
        if canonical_json(_without_ratings(original)) != canonical_json(_without_ratings(rated)):
            raise ValueError("rater, version, item order, instructions, evidence or responses changed")
        completed = 0
        for item in rated["items"]:
            verdict, rationale = item["verdict"], item["rationale"]
            if verdict is not None and (not isinstance(verdict, str) or verdict not in VERDICTS):
                raise ValueError("verdict outside the four-class set")
            if rationale is not None and not isinstance(rationale, str):
                raise ValueError("rationale must be text or null")
            completed += verdict in VERDICTS and isinstance(rationale, str) and bool(rationale.strip())
        if require_complete and completed != len(original["items"]):
            raise ValueError("complete submission requires a verdict and rationale for every item")
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError("malformed human rating sheet") from exc
    return {"presentations": len(rated["items"]), "completed": completed}


def read_rating_json(path: Path) -> dict[str, Any]:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key in human rating file")
            result[key] = value
        return result

    value = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique)
    if not isinstance(value, dict):
        raise ValueError("human rating file must be one JSON object")
    return value


def render_rating_html(sheet: dict[str, Any], *, sheet_sha256: str, filename_stem: str) -> str:
    validate_reference_catalog(sheet)
    template = Path(__file__).with_name("human_reference_form.html").read_text(encoding="utf-8")
    script = Path(__file__).with_name("human_reference_form.js").read_text(encoding="utf-8")
    payload = json.dumps(
        {"sheet": sheet, "sheet_sha256": sheet_sha256, "filename_stem": filename_stem},
        ensure_ascii=False,
    )
    # Raw public dialogue is data, never HTML or JavaScript source.
    payload = payload.replace("&", "\\u0026").replace("<", "\\u003c").replace(">", "\\u003e")
    payload = payload.replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    return template.replace("__FORM_SCRIPT__", script).replace("__FORM_PAYLOAD__", payload)


__all__ = [
    "PROTOCOL", "REFERENCE_PROTOCOL", "build_dg_reference", "reference_from_view",
    "upgrade_human_sheet", "validate_reference_catalog", "validate_rated_sheet",
    "read_rating_json", "render_rating_html",
]
