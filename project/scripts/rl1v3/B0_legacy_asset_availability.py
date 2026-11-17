#!/usr/bin/env python3
"""B0 supplement: strictly-past availability of LEGACY memory assets per census prefix.

Read-only count of the historical Paper-1 Multi-View compiler result (713 MP
profile units, 1,523 ME event units) and past-session MS-RAW per B0 prefix.
This is NOT bank v0 (WS-A A1b owns that adapter), NOT a reading through
retrieve.read, and says nothing about whether any asset improves a reply.
Usage/evaluation coverage comes from the B0 exposure registry.

    PYTHONPATH=project/src python project/scripts/rl1v3/B0_legacy_asset_availability.py
"""
from __future__ import annotations

import collections
import hashlib
import json
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.paper1.multi_view_memory import load_accepted_multi_view_units  # noqa: E402
from metacom_pm.rl1v3.prefixes import census as C  # noqa: E402

ARTIFACT = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
UNITS = PROJECT / "data/paper1_public_memory/es_memeval_public_multi_view_session_results_v1.jsonl"
B0 = PROJECT / "outputs/pm_rl1/v3/B0"
HEAD = {"AcceptedProfileViewUnit": "MP_legacy_profile", "AcceptedEventExperienceUnit": "ME_legacy_event"}


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def q(v):
    v = sorted(v)
    return dict(min=v[0], p10=v[int(.1 * (len(v) - 1))], p50=v[(len(v) - 1) // 2],
                p90=v[int(.9 * (len(v) - 1))], max=v[-1])


def main() -> int:
    users = C.load_users(ARTIFACT)
    units = load_accepted_multi_view_units(UNITS, users=users)
    by = collections.defaultdict(lambda: collections.defaultdict(list))
    for u in units:
        by[u.owner_id][HEAD[type(u).__name__]].append(u.source_session_rank)
    rows = [json.loads(l) for l in (B0 / "prefix_census.jsonl").open(encoding="utf-8")]
    counts = collections.defaultdict(list)
    for r in rows:
        for h in HEAD.values():
            counts[h].append(sum(1 for x in by[r["owner_id"]][h] if x < r["cutoff_rank"]))
        counts["MS_RAW_past_sessions"].append(r["cutoff_rank"])
    exposure = [json.loads(l) for l in (B0 / "exposure_registry.jsonl").open(encoding="utf-8")]
    pref = [e for e in exposure if e["record"] == "prefix"]
    out = dict(
        status="LEGACY_ASSET_AVAILABILITY_NOT_BANK_V0",
        evidence_tier="engineering_only",
        units_total=dict(collections.Counter(HEAD[type(u).__name__] for u in units)),
        prefixes=len(rows),
        legal_strict_past_availability={
            h: dict(prefixes_with_at_least_one=sum(1 for x in v if x > 0),
                    share=round(sum(1 for x in v if x > 0) / len(v), 4), per_prefix=q(v))
            for h, v in counts.items()},
        historical_use_lower_bound=dict(
            prefixes_in_judge_feedback_training_or_human_dirs=len(pref),
            share=round(len(pref) / len(rows), 4),
            prefixes_in_human_review_dirs=sum("human_review" in p["categories"] for p in pref),
            source="B0 exposure_registry.jsonl (legacy rl1 PrefixSpec identity match)"),
        not_measured=["reading through WS-A bank_v0/retrieve.read (A1b not delivered)",
                      "whether any legacy asset improves a reply vs OFF (needs B1/B2 + B6e)",
                      "RS drafts (11/15: 12 cases + 3 methods) — global, not owner-scoped; "
                      "none shown to improve natural support (RESOURCE_SPEC §1)"],
        inputs={str(p.relative_to(PROJECT)): sha(p) for p in
                (ARTIFACT, UNITS, B0 / "prefix_census.jsonl", B0 / "exposure_registry.jsonl")},
        code_sha256=sha(Path(__file__)),
    )
    (B0 / "legacy_asset_availability.json").write_text(
        json.dumps(out, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(out["legal_strict_past_availability"], indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
