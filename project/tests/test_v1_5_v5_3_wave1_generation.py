from __future__ import annotations

from collections import Counter
import json
from pathlib import Path

from metacom_pm.v1_5_v5_3_wave1_generation import (
    candidate_requirements,
    chunk_ranges,
    preference_assignments,
)


ROOT = Path(__file__).resolve().parents[1]


def test_chunk_ranges_are_exact_and_contiguous() -> None:
    assert chunk_ranges(13) == ((1, 5), (6, 9), (10, 13))
    assert chunk_ranges(15) == ((1, 5), (6, 10), (11, 15))


def test_candidate_requirements_have_exact_per_user_contract() -> None:
    rows = candidate_requirements("u", ["t0", "t1", "t2", "t3"], 13)
    subtypes = Counter(row["subtype"] for row in rows)
    tiers = Counter(row.get("me_tier") for row in rows)
    assert subtypes == {
        "MS_SESSION": 8,
        "ME_REUSABLE_OUTCOME": 10,
        "ME_UNRESOLVED_EVENT": 5,
        "ME_CONTEXT_EVENT": 4,
    }
    assert tiers["executable_core"] == 8
    assert tiers["natural_coverage_challenge"] == 2
    assert len({row["candidate_id"] for row in rows}) == 27
    assert all(1 <= row["session_index"] <= 13 for row in rows)


def test_wave1_preferences_preserve_final_quota_reachability() -> None:
    assignments = json.loads(
        (
            ROOT
            / "data/pm_v1_5_contracts/v5_3_wave1_sentinel_assignments_v1.json"
        ).read_text(encoding="utf-8")
    )["rows"]
    existing = (
        ROOT
        / "data/pm_v1_5_v5_3_formal_longitudinal_catalog_intake_v1/canonical_users"
    )
    result = preference_assignments(assignments, existing)
    assert set(result) == {row["user_id"] for row in assignments}
    assert all(len(value) == 3 and len(set(value)) == 3 for value in result.values())

    counts = {"chatgpt_pro": Counter(), "claude": Counter()}
    user_counts = Counter()
    for path in existing.glob("*.json"):
        row = json.loads(path.read_text(encoding="utf-8"))
        counts[row["content_author"]].update(
            item["preference_type"] for item in row["response_preference_history"]
        )
        user_counts[row["content_author"]] += 1
    for row in assignments:
        counts[row["content_author"]].update(result[row["user_id"]])
        user_counts[row["content_author"]] += 1
    for author in counts:
        remaining_users = 40 - user_counts[author]
        assert all(0 <= 20 - count <= remaining_users for count in counts[author].values())


def test_wave1a_and_wave1b_are_an_exact_partition_of_frozen_wave1() -> None:
    def ids(name: str) -> list[str]:
        return [
            row["user_id"]
            for row in json.loads((ROOT / "data/pm_v1_5_contracts" / name).read_text(encoding="utf-8"))["rows"]
        ]

    full = ids("v5_3_wave1_sentinel_assignments_v1.json")
    canary = ids("v5_3_wave1a_canary_assignments_v1.json")
    scale = ids("v5_3_wave1b_scale_assignments_v1.json")
    assert canary == ["p2r_formal_gpt_u010", "p2r_formal_claude_u005"]
    assert len(scale) == 11
    assert len(set(canary + scale)) == 13
    assert set(canary + scale) == set(full)
