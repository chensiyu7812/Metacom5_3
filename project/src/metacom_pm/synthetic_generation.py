from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
import random
import re

from pydantic import Field, model_validator

from .api import Endpoint, OpenAICompatibleClient, request_log
from .contracts import StrictModel
from .io import append_jsonl, canonical_json, load_done_keys, sha256_text, stable_hex, write_json


class GeneratedTurn(StrictModel):
    role: Literal["user", "assistant"]
    content: str = Field(min_length=2, max_length=600)


class GeneratedPastSession(StrictModel):
    session_index: int = Field(ge=1)
    summary: str = Field(min_length=10, max_length=700)
    seeker_disclosures: list[str] = Field(min_length=1, max_length=8)


class GeneratedDecisionState(StrictModel):
    semantic_family: str = Field(min_length=2, max_length=80)
    session_index: int = Field(ge=2)
    current_session_summary: str = Field(min_length=5, max_length=500)
    current_session_history: list[GeneratedTurn] = Field(min_length=1, max_length=6)
    current_user_text: str = Field(min_length=5, max_length=500)


class GeneratedLongitudinalUser(StrictModel):
    stable_profile_facts: list[str] = Field(min_length=3, max_length=10)
    communication_preferences: list[str] = Field(min_length=1, max_length=5)
    past_sessions: list[GeneratedPastSession] = Field(min_length=6, max_length=10)
    decision_states: list[GeneratedDecisionState] = Field(min_length=6, max_length=10)

    @model_validator(mode="after")
    def temporal_and_unique(self):
        indices = [x.session_index for x in self.past_sessions]
        if indices != sorted(indices) or len(indices) != len(set(indices)):
            raise ValueError("past session indices must be unique and increasing")
        maximum = max(indices)
        if any(x.session_index <= maximum for x in self.decision_states):
            raise ValueError("decision states must occur after all supplied past sessions")
        current = [" ".join(x.current_user_text.lower().split()) for x in self.decision_states]
        if len(current) != len(set(current)):
            raise ValueError("decision-state user messages must be unique")
        return self


SYSTEM = """Generate realistic longitudinal emotional-support user data for
research. Build a coherent user with multiple past sessions and later current
session states. The current messages must sound natural and must not reveal any
dataset, policy, retrieval, memory-source, action, or expected-answer label.
Do not write clinical diagnoses, crisis instructions, or gold decisions.
Vary wording, topics, support needs, and whether the past happens to be useful.
Return only the requested JSON schema."""

THEMES = [
    "work uncertainty and belonging", "family expectations and boundaries",
    "relationship change and self-worth", "loneliness and daily routine",
    "academic pressure and identity", "caregiving and personal needs",
    "friendship conflict and trust", "relocation and social connection",
    "creative goals and fear of judgment", "sleep disruption and workload",
    "retirement transition and purpose", "financial uncertainty and shame",
]


def _messages(user_index: int, seed: int) -> list[dict[str, str]]:
    rng = random.Random(seed + user_index)
    themes = rng.sample(THEMES, 3)
    return [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": (
            f"Create synthetic user {user_index}. Use these broad themes as inspiration: "
            + "; ".join(themes)
            + ". Produce 6-8 chronological past sessions and 6-8 later decision states. "
              "At least two later states should be understandable without past information; "
              "at least two may benefit from a specific past event; at least one should involve "
              "an updated situation where an older fact is no longer current. Express all of "
              "this only through natural history and dialogue, never through labels or instructions."
        )},
    ]


def _source_rows(user_id: str, value: GeneratedLongitudinalUser) -> list[dict[str, Any]]:
    profile_text = "; ".join(value.stable_profile_facts + value.communication_preferences)
    memory_store = {"MP": [{
        "memory_id": f"src_{stable_hex(user_id, 'profile', n=16)}",
        "session_index": 0,
        "text": profile_text,
    }], "MS": [], "ME": []}
    rolling: list[str] = []
    for session in value.past_sessions:
        rolling.append(session.summary)
        # Two rolling summary checkpoints avoid making MS identical to ME.
        if len(rolling) in {max(2, len(value.past_sessions)//2), len(value.past_sessions)}:
            memory_store["MS"].append({
                "memory_id": f"src_{stable_hex(user_id, 'summary', session.session_index, n=16)}",
                "session_index": session.session_index,
                "text": "Across sessions: " + " ".join(rolling),
            })
        memory_store["ME"].append({
            "memory_id": f"src_{stable_hex(user_id, 'event', session.session_index, n=16)}",
            "session_index": session.session_index,
            "text": " ".join(session.seeker_disclosures),
        })
    rows: list[dict[str, Any]] = []
    for index, state in enumerate(value.decision_states):
        rows.append({
            "sim_card_id": f"syn_{stable_hex(user_id, index, state.current_user_text, n=20)}",
            "user_id": user_id,
            "semantic_family": state.semantic_family,
            "session_depth": state.session_index,
            "current_user_text": state.current_user_text,
            "current_session_history": [x.model_dump(mode="json") for x in state.current_session_history],
            "current_session_summary": state.current_session_summary,
            "memory_store": memory_store,
        })
    return rows


def generate_longitudinal_source(
    out_source_path: str | Path,
    out_raw_log_path: str | Path,
    out_summary_path: str | Path,
    *,
    endpoint: Endpoint,
    n_users: int = 60,
    seed: int = 90210,
) -> dict[str, Any]:
    done = load_done_keys(out_raw_log_path, ("user_index", "success"))
    # Resume uses successful raw records to avoid regenerating users with a new result.
    successful = {int(x[0]) for x in done if x[1] is True}
    client = OpenAICompatibleClient(endpoint)
    all_rows: list[dict[str, Any]] = []
    # Existing clean rows are safe to load for resume.
    if Path(out_source_path).exists():
        from .io import iter_jsonl
        all_rows.extend(iter_jsonl(out_source_path))
    try:
        for user_index in range(n_users):
            if user_index in successful:
                continue
            messages = _messages(user_index, seed)
            try:
                result, parsed = client.chat(
                    messages,
                    temperature=0.7,
                    max_tokens=4500,
                    seed=seed + user_index,
                    response_schema=GeneratedLongitudinalUser,
                    retries=4,
                )
                assert parsed is not None
                user_id = f"synuser_{stable_hex(seed, user_index, n=16)}"
                rows = _source_rows(user_id, parsed)
                for row in rows:
                    append_jsonl(out_source_path, row)
                    all_rows.append(row)
                append_jsonl(out_raw_log_path, request_log(
                    stage="synthetic_user_generation", endpoint=endpoint,
                    messages=messages, result=result, parsed=parsed, error=None,
                    prompt_hash=sha256_text(canonical_json(messages)),
                    record_ids={"user_index": user_index, "success": True},
                ))
            except Exception as exc:
                append_jsonl(out_raw_log_path, {
                    "stage": "synthetic_user_generation",
                    "user_index": user_index,
                    "success": False,
                    "error": f"{type(exc).__name__}: {exc}",
                })
                raise
    finally:
        client.close()

    forbidden = re.compile(r"\b(?:M0|MP|MS|ME|MPE|MSE|R0|RS|policy manager|gold action|specific memory)\b", re.I)
    texts = [" ".join(str(x["current_user_text"]).lower().split()) for x in all_rows]
    cue_hits = [x["sim_card_id"] for x in all_rows if forbidden.search(x["current_user_text"])]
    summary = {
        "n_users": len({x["user_id"] for x in all_rows}),
        "n_states": len(all_rows),
        "n_unique_current_texts": len(set(texts)),
        "exact_duplicate_current_texts": len(texts) - len(set(texts)),
        "forbidden_action_cue_hits": cue_hits,
        "status": "PASS" if not cue_hits and len(texts) == len(set(texts)) else "FAIL",
        "endpoint_model": endpoint.model,
        "seed": seed,
    }
    write_json(out_summary_path, summary)
    if summary["status"] != "PASS":
        raise RuntimeError("synthetic generation audit failed")
    return summary
