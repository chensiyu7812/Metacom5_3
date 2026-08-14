#!/usr/bin/env python3
"""Materialize the 64-case V5.3 Step2 semantic qualification plan (zero API)."""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.evoemo import load_evoemo  # noqa: E402
from metacom_pm.io import write_json, write_jsonl  # noqa: E402
from metacom_pm.v1_5_v5_3_external_leakage_audit import (  # noqa: E402
    compare_text_surface_overlap,
    external_overlap_surfaces,
    normalized_tokens,
)
from metacom_pm.v1_5_v5_3_step2_semantic_qualification import (  # noqa: E402
    build_semantic_qualification_plan,
    semantic_qualification_surface_rows,
)


EVOEMO = ROOT / "data/external/evo_emo.json"
ESCONV = ROOT / "data/external/ESConv.json"
FORMAL_USERS = (
    ROOT
    / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users"
)


def _iter_strings(value: Any, path: tuple[str, ...] = ()) -> Iterable[tuple[tuple[str, ...], str]]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield from _iter_strings(item, (*path, str(key)))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            yield from _iter_strings(item, (*path, str(index)))
    elif isinstance(value, str) and value.strip():
        yield path, value


def _external_surfaces() -> list[dict[str, str]]:
    evoemo = external_overlap_surfaces(load_evoemo(EVOEMO))
    esconv_raw = json.loads(ESCONV.read_text(encoding="utf-8"))
    esconv = [
        {
            "surface_id": "esconv:" + ":".join(path),
            "category": "external_esconv_text",
            "text": value,
        }
        for path, value in _iter_strings(esconv_raw)
        if len(normalized_tokens(value)) >= 3
    ]
    return [*evoemo, *esconv]


def _formal_surfaces() -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for path in sorted(FORMAL_USERS.glob("*.json")):
        value = json.loads(path.read_text(encoding="utf-8"))
        for field_path, text in _iter_strings(value):
            if len(normalized_tokens(text)) >= 3:
                rows.append(
                    {
                        "surface_id": f"formal:{path.stem}:{':'.join(field_path)}",
                        "category": "formal_intake_text",
                        "text": text,
                    }
                )
    return rows


def main() -> None:
    out = ROOT / "outputs/pm_v1_5_v5_3_step2_semantic_qualification_plan_v1"
    plan = build_semantic_qualification_plan()
    internal = semantic_qualification_surface_rows()
    external_overlap = compare_text_surface_overlap(
        internal_surfaces=internal,
        external_surfaces=_external_surfaces(),
        ngram_size=8,
    )
    formal_overlap = compare_text_surface_overlap(
        internal_surfaces=internal,
        external_surfaces=_formal_surfaces(),
        ngram_size=8,
    )
    blocked = any(
        report[metric]
        for report in (external_overlap, formal_overlap)
        for metric in ("exact_collision_count", "normalized_ngram_collision_count")
    )
    integrity = {
        "protocol": "pm-v1.5-v5.3-step2-semantic-qualification-integrity-v1",
        "status": "BLOCKED_CONTENT_OVERLAP" if blocked else "PASS_CONTENT_DISJOINT",
        "qualification_semantic_surfaces": len(internal),
        "external_sources": ["ESConv", "EvoEmo", "ES-MemEval QA surfaces embedded in EvoEmo"],
        "formal_intake_users": len(list(FORMAL_USERS.glob("*.json"))),
        "external_overlap": external_overlap,
        "formal_intake_overlap": formal_overlap,
        "generated_response_or_outcome_read": False,
        "api_calls": 0,
    }
    write_json(out / "plan_manifest.json", plan.model_dump(mode="json", exclude={"cases"}))
    write_jsonl(out / "cases.jsonl", [case.model_dump(mode="json") for case in plan.cases])
    write_json(out / "content_disjoint_audit.json", integrity)
    if blocked:
        raise RuntimeError("Step2 semantic qualification content overlaps formal/external surfaces")
    print(json.dumps({**plan.model_dump(mode="json", exclude={"cases"}), "integrity": integrity}, indent=2))


if __name__ == "__main__":
    main()
