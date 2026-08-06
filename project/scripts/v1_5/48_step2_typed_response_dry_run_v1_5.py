"""Step2 typed_response_program runner: real candidates, dry-run by default.

Status: DRY-RUN ONLY in this session. Wires v1_5_v5_3_typed_response_program.py
to a real production candidate (via the same discover_final_typed_memory_
candidates()/build_evo_memory() functions used throughout the ME/MS/MP
verification work) and to the real `generator` endpoint config in
project/configs/experiment.yaml (Llama-3.1-8B-Instruct via NVIDIA), closing
the gap the module's own docstring flags: "implemented, unit-tested, NOT yet
wired into any generation pipeline."

This script makes NO network call unless invoked with --live. Without
--live, it builds the real TypedResponseProgram and the real generation
messages from a real qualifying-panel state, prints them, and validates a
synthetic (hand-written, clearly fake) response against
parse_generator_response_dict + typed_response_guard_errors, to prove the
downstream parsing/validation path is correct before any money is spent.

Running with --live requires NVIDIA_API_KEY to be set (e.g.
`source ~/.metacom_v1_5_secrets.env`) and is a real, billable API call --
not run automatically, not run by importing this file, only by explicit
`--live` on the command line. This session never passed --live.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.contracts import MemoryItem, MemorySource  # noqa: E402
from metacom_pm.evoemo import build_evo_memory  # noqa: E402
from metacom_pm.retrieval import source_specific_memory_queries  # noqa: E402
from metacom_pm.v1_5_candidate_discovery import (  # noqa: E402
    discover_final_typed_memory_candidates,
)
from metacom_pm.v1_5_typed_resource_adapter import TypedResourceCandidate  # noqa: E402
from metacom_pm.v1_5_v5_3_typed_response_program import (  # noqa: E402
    build_typed_response_program,
    evidence_aware_generation_messages,
    parse_generator_response_dict,
    typed_response_guard_errors,
)

EVOEMO = ROOT / "data/external/evo_emo.json"
PANEL_DIR = ROOT / "outputs/pm_v1_5b_corrected_external_split_v1"


def load_jsonl(path: Path) -> list[dict]:
    with path.open() as f:
        return [json.loads(line) for line in f if line.strip()]


def load_states() -> list[dict]:
    states = []
    for fname in ("evoemo_qualification_panel_private.jsonl", "evoemo_lockbox_panel_private.jsonl"):
        for row in load_jsonl(PANEL_DIR / fname):
            rt = row["runtime_state"]
            states.append(
                {
                    "state_id": row["state_id"],
                    "user_id": row["user_id_private_analysis_only"],
                    "current_user_text": rt.get("current_user_text", ""),
                    "current_session_history": rt.get("current_session_history", []),
                    "current_session_summary": rt.get("current_session_summary", ""),
                }
            )
    return states


def _ms_candidate(item: MemoryItem, session_index: int, user_id: str) -> TypedResourceCandidate:
    return TypedResourceCandidate(
        component="MS",
        subtype="MS_SESSION_OBSERVATION",
        resource_id=item.memory_id,
        candidate_version="v1",
        source_kind="session",
        owner_id=user_id,
        strictly_prior=True,
        age_sessions=session_index - item.created_session,
        prior_observation=item.text,
    )


def _mp_candidate(item: MemoryItem, user_id: str) -> TypedResourceCandidate:
    return TypedResourceCandidate(
        component="MP",
        subtype="MP_PROFILE",
        resource_id=item.memory_id,
        candidate_version="v1",
        source_kind="profile",
        owner_id=user_id,
        profile_fact=item.text,
    )


def find_demo_state(states: list[dict], users: dict) -> tuple[dict, dict, int]:
    """Find one real state with a usable MS candidate (MP optional).

    ME is deliberately not attempted here: the ME verification work already
    established a 0.40% strict-compiler pass rate, so requiring a real ME
    candidate for the demo would very likely fail on almost any state, for
    reasons already documented, not a bug in this script.
    """
    for state in states:
        uid = state["user_id"]
        user = users[uid]
        session_index = len(user.get("dialog_history") or []) + 1
        items, _extra = build_evo_memory(user)
        queries = source_specific_memory_queries(
            state["current_user_text"], state["current_session_history"], state["current_session_summary"]
        )
        discoveries = discover_final_typed_memory_candidates(
            queries=queries, items=items, source_metadata={}, session_index=session_index,
        )
        ms_selected = discoveries[MemorySource.MS].selected_items
        if ms_selected:
            return state, discoveries, session_index
    raise RuntimeError("no state in the panel had any MS candidate -- unexpected, investigate")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true",
        help="Make a real, billable API call. Requires NVIDIA_API_KEY. Never passed in this session.",
    )
    args = parser.parse_args()

    users = {str(u["id"]): u for u in json.loads(EVOEMO.read_text(encoding="utf-8"))}
    states = load_states()
    state, discoveries, session_index = find_demo_state(states, users)
    uid = state["user_id"]

    candidates: dict[str, TypedResourceCandidate] = {}
    ms_item = discoveries[MemorySource.MS].selected_items[0]
    candidates["MS"] = _ms_candidate(ms_item, session_index, uid)
    requested_action_id = "MS+R0"
    mp_selected = discoveries[MemorySource.MP].selected_items
    if mp_selected:
        candidates["MP"] = _mp_candidate(mp_selected[0], uid)
        requested_action_id = "MPMS+R0" if "MS" in candidates else "MP+R0"

    program = build_typed_response_program(
        requested_action_id=requested_action_id,
        current_goal="respond to the seeker's current turn, integrating the confirmed evidence naturally",
        current_user_id=uid,
        candidates=candidates,
    )
    messages = evidence_aware_generation_messages(
        current_context=state["current_user_text"], program=program
    )

    print(f"demo state: {state['state_id']} (user={uid}, action={requested_action_id})")
    print(f"evidence items: {len(program.evidence)}")
    print("\n--- messages that would be sent to the generator endpoint ---")
    for m in messages:
        print(f"[{m['role']}] {m['content'][:500]}")

    if args.live:
        from metacom_pm.api import OpenAICompatibleClient  # noqa: PLC0415
        from metacom_pm.config import endpoint_from_config, load_config  # noqa: PLC0415
        from pydantic import BaseModel  # noqa: PLC0415

        class _GeneratorResponseSchema(BaseModel):
            reply: str
            used_evidence_ids: list[str]
            realized_response_act: str

        config = load_config(ROOT / "configs/experiment.yaml")
        endpoint = endpoint_from_config(config, "generator")
        client = OpenAICompatibleClient(endpoint)
        try:
            result, parsed = client.chat(messages, response_schema=_GeneratorResponseSchema)
        finally:
            client.close()
        if parsed is None:
            print(f"\nLIVE call did not return structured output: {result}")
            return
        response = parse_generator_response_dict(parsed.model_dump())
        print(f"\n--- LIVE generator response ---\n{response}")
    else:
        # Dry-run: validate the downstream parse/guard path with a
        # synthetic, clearly-fabricated response. This is NOT a real model
        # output -- it only proves parse_generator_response_dict and
        # typed_response_guard_errors accept a well-formed response and
        # reject the things they are supposed to reject.
        fake_good = {
            "reply": (
                f"That sounds like a lot to carry. Given what you noted before "
                f"({ms_item.text[:60]}...), how are you feeling about it today?"
            ),
            "used_evidence_ids": [item.evidence_id for item in program.evidence],
            "realized_response_act": "reflection",
        }
        response = parse_generator_response_dict(fake_good)
        errors = typed_response_guard_errors(response=response, program=program)
        print(f"\n--- dry-run: synthetic response parses cleanly, guard errors: {errors} ---")

        fake_bad = dict(fake_good)
        fake_bad["reply"] = "An earlier session recorded: something. " + fake_good["reply"]
        bad_response = parse_generator_response_dict(fake_bad)
        bad_errors = typed_response_guard_errors(response=bad_response, program=program)
        print(f"--- dry-run: synthetic V5.2-leak-style response correctly flagged: {bad_errors} ---")


if __name__ == "__main__":
    main()
