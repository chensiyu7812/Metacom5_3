from collections import Counter, defaultdict

import pytest

from metacom_pm.paper1.evaluation.formal_schedule import (
    CANONICAL_DG_ARMS,
    FORMAL_MISTRAL_SCHEDULE_PROTOCOL,
    build_arm_balanced_schedule,
)


def _requests(units: int = 12):
    rows = []
    for unit in range(units):
        for arm in CANONICAL_DG_ARMS:
            rows.append(
                {
                    "request_id": f"r-{unit}-{arm}",
                    "request_sha256": f"hash-{unit}-{arm}",
                    "owner_id": f"owner-{unit % 3}",
                    "scenario_id": f"scenario-{unit}",
                    "turn_index": unit % 10,
                    "observation_id": f"observation-{unit}",
                    "judgement_kind": "usage" if unit % 2 else "score",
                    "arm": arm,
                }
            )
    return rows


def test_schedule_is_input_order_independent_and_keeps_six_arm_microblocks():
    rows = _requests()
    forward = build_arm_balanced_schedule(rows)
    reverse = build_arm_balanced_schedule(tuple(reversed(rows)))
    assert forward == reverse
    assert [row["schedule_position"] for row in forward] == list(range(len(forward)))

    blocks = defaultdict(list)
    for row in forward:
        assert row["schedule_protocol"] == FORMAL_MISTRAL_SCHEDULE_PROTOCOL
        blocks[row["matched_unit_id"]].append(row)
    for block in blocks.values():
        assert len(block) == 6
        assert {row["arm"] for row in block} == set(CANONICAL_DG_ARMS)
        positions = [row["schedule_position"] for row in block]
        assert positions == list(range(min(positions), min(positions) + 6))


def test_cyclic_rotation_balances_every_arm_across_positions():
    scheduled = build_arm_balanced_schedule(_requests(units=12))
    counts = Counter((row["arm"], row["within_unit_position"]) for row in scheduled)
    assert set(counts.values()) == {2}


def test_schedule_fails_closed_on_missing_or_duplicate_arm():
    rows = _requests(units=1)
    with pytest.raises(ValueError, match="exactly the canonical arms"):
        build_arm_balanced_schedule(rows[:-1])
    duplicate = [*rows, {**rows[0], "request_id": "new-request"}]
    with pytest.raises(ValueError, match="duplicate arm"):
        build_arm_balanced_schedule(duplicate)


def test_schedule_fails_closed_on_duplicate_request_identity():
    rows = _requests(units=1)
    with pytest.raises(ValueError, match="duplicate request_id"):
        build_arm_balanced_schedule([*rows, rows[0]])
