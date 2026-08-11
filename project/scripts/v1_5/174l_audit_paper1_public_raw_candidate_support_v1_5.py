from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.evoemo import load_evoemo  # noqa: E402
from metacom_pm.v1_5_v5_2_atomic_memory import (  # noqa: E402
    compile_atomic_reusable_outcome,
    compile_atomic_session_observation,
)


MANIFEST = (
    ROOT
    / "data"
    / "pm_v1_5_contracts"
    / "paper1_p1_public_source_group_manifest_candidate_v1.json"
)
DEFAULT_OUTPUT = (
    ROOT
    / "outputs"
    / "pm_v1_5_paper1_public_raw_candidate_support_20260810"
    / "report.json"
)


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve(relative: str) -> Path:
    path = (ROOT / relative).resolve()
    path.relative_to(ROOT.resolve())
    return path


def audit_support() -> dict[str, Any]:
    manifest = _read_json(MANIFEST)
    evo_binding = manifest["source_bindings"]["EvoEmo_and_ES_MemEval"]
    es_binding = manifest["source_bindings"]["ESConv"]
    evo_path = _resolve(evo_binding["path"])
    es_path = _resolve(es_binding["path"])
    split_path = _resolve(es_binding["split_manifest_path"])
    if _sha256(evo_path) != evo_binding["sha256"]:
        raise RuntimeError("EvoEmo source hash drifted")
    if _sha256(es_path) != es_binding["sha256"]:
        raise RuntimeError("ESConv source hash drifted")
    if _sha256(split_path) != es_binding["split_manifest_sha256"]:
        raise RuntimeError("ESConv split manifest hash drifted")

    users = load_evoemo(evo_path)
    totals: Counter[str] = Counter()
    user_rows: list[dict[str, Any]] = []
    for user in users:
        user_id = str(user["id"])
        profile_items = [
            (str(key), value)
            for key, value in (user.get("basic_info") or {}).items()
            if key != "name" and str(value).strip()
        ]
        prior_ms: list[tuple[int, int, str]] = []
        prior_me: list[tuple[int, int, str]] = []
        counts: Counter[str] = Counter()
        for session_index, session in enumerate(user["dialog_history"], start=1):
            dialogue = list(session.get("dialogue") or [])
            for turn in dialogue:
                if (
                    str(turn.get("role")) != "seeker"
                    or not str(turn.get("content") or "").strip()
                ):
                    continue
                counts["seeker_turn_states"] += 1
                if profile_items:
                    counts["states_with_mp_source"] += 1
                if prior_ms:
                    counts["states_with_strict_past_ms_source"] += 1
                if prior_me:
                    counts["states_with_strict_past_me_source"] += 1
            # A session opens as memory only after every turn in it closes.
            for turn in dialogue:
                if str(turn.get("role")) != "seeker":
                    continue
                text = " ".join(str(turn.get("content") or "").split())
                turn_index = int(turn.get("idx") or 0)
                if compile_atomic_session_observation(text) is not None:
                    prior_ms.append((session_index, turn_index, text))
                if compile_atomic_reusable_outcome(text) is not None:
                    prior_me.append((session_index, turn_index, text))
        counts["mp_profile_items"] = len(profile_items)
        counts["ms_literal_items"] = len(prior_ms)
        counts["me_literal_action_result_items"] = len(prior_me)
        totals.update(counts)
        user_rows.append({"user_id": user_id, **dict(counts)})

    esconv = _read_json(es_path)
    split_rows = _read_jsonl(split_path)
    esconv_dialogues: Counter[str] = Counter()
    esconv_states: Counter[str] = Counter()
    for raw_index, (dialogue, split_row) in enumerate(
        zip(esconv, split_rows, strict=True)
    ):
        if split_row["index"] != raw_index:
            raise RuntimeError("ESConv split manifest reordered")
        if bool(split_row["excluded_for_evoemo_overlap"]):
            continue
        split = str(split_row["split"])
        esconv_dialogues[split] += 1
        turns = list(dialogue.get("dialog") or [])
        for turn_index, turn in enumerate(turns):
            if (
                turn.get("speaker") != "seeker"
                or not str(turn.get("content") or "").strip()
            ):
                continue
            later_supporter_exists = any(
                later.get("speaker") == "supporter"
                and str(later.get("content") or "").strip()
                for later in turns[turn_index + 1 :]
            )
            if later_supporter_exists:
                esconv_states[split] += 1

    users_with_me = sum(
        row["me_literal_action_result_items"] > 0 for row in user_rows
    )
    report = {
        "protocol": "pm-v1.5-paper1-public-raw-candidate-support-audit-v1",
        "status": "RAW_SUPPORT_PRESENT_ACTUAL_RANK1_AND_LEARNABILITY_NOT_YET_ESTABLISHED",
        "method_id": manifest["method_binding"]["method_id"],
        "candidate_manifest_sha256": _sha256(MANIFEST),
        "scope": "read-only counts from permitted raw source fields; no state rows, candidate text, label, response, PM prediction, or external outcome is emitted",
        "evoemo": {
            "users": len(users),
            "seeker_turn_states": totals["seeker_turn_states"],
            "mp_profile_items": totals["mp_profile_items"],
            "states_with_mp_source": totals["states_with_mp_source"],
            "ms_literal_items": totals["ms_literal_items"],
            "states_with_strict_past_ms_source": totals[
                "states_with_strict_past_ms_source"
            ],
            "me_literal_action_result_items": totals[
                "me_literal_action_result_items"
            ],
            "users_with_me_literal_item": users_with_me,
            "states_with_strict_past_me_source": totals[
                "states_with_strict_past_me_source"
            ],
            "per_user_counts": user_rows,
        },
        "esconv": {
            "nonoverlap_dialogues": dict(esconv_dialogues),
            "eligible_seeker_turn_states_with_later_supporter": dict(
                esconv_states
            ),
        },
        "head_support_interpretation": {
            "MP": "raw onboarding profile source is present for every EvoEmo state; suitability and actual Rank-1 relevance remain unmeasured",
            "MS": "strict-past literal source coverage is broad across users and states; suitability and actual Rank-1 relevance remain unmeasured",
            "ME": "natural exact action-result support exists but is sparse at 24 items across 15 users; ME may qualify or may remain an explicit limited/failed head",
            "RS": "ESConv provides a large grouped current-state surface; the frozen six-card actual Rank-1 and suitability distribution remain unmeasured"
        },
        "paper1_implication": "The raw source does not force a zero-candidate outcome for MP, MS, or RS and gives bounded ME support. This is evidence to proceed to P1, not evidence that any head has learned or passed.",
        "api_calls": 0,
        "responses_generated": 0,
        "labels_created": 0,
        "pm_trained": False,
        "external_outcomes_read": False,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    report = audit_support()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
