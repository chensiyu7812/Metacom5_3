from __future__ import annotations

from pathlib import Path
from typing import Any, Sequence
import json
import time

import numpy as np
from sklearn.feature_extraction.text import HashingVectorizer

from .api import Endpoint, OpenAICompatibleClient, request_log
from .artifacts import create_artifact_attestation, require_artifact_attestation
from .contracts import (
    CostRecord,
    DialogueTurn,
    MemoryItem,
    MemorySource,
    RuntimeState,
    SourceCatalog,
    StrategyCard,
    StrategyMode,
    parse_action_id,
)
from .io import (
    append_jsonl,
    canonical_json,
    ensure_run_manifest,
    iter_jsonl,
    load_done_keys,
    read_json,
    sha256_file,
    sha256_text,
    stable_hex,
    utc_now,
    write_json,
)
from .policies import FixedPolicy, LearnedPMPolicy, RuleConfig, StrongRulePolicy
from .prompts import OFFICIAL_ESMEM_SYSTEM, SELECTIVE_ESMEM_SYSTEM, generation_messages
from .retrieval import MemoryRetriever, StrategyRetriever, context_query
from .text import estimate_tokens, lexical_score, normalize_space
from .training import PMModel


NEUTRAL_INITIAL_GREETING = "Hi, I'm here with you. What would you like to talk about today?"
_NEUTRAL_TRACK_PROBES = (
    "I'm listening. What feels most important to share right now?",
    "What has that experience been like for you?",
    "What part of it has been weighing on you most?",
    "How has this been affecting you lately?",
    "What do you wish felt different at this point?",
    "What kind of support would feel most useful right now?",
)


def load_evoemo(path: str | Path) -> list[dict[str, Any]]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, list) or len(data) != 18:
        raise ValueError("expected EvoEmo list with exactly 18 users")
    total_sessions = sum(len(x.get("dialog_history") or []) for x in data)
    total_topics = sum(len(x.get("subsequent_topics") or []) for x in data)
    if total_sessions != 401 or total_topics != 34:
        raise ValueError(
            f"unexpected EvoEmo statistics: sessions={total_sessions}, topics={total_topics}"
        )
    return data


def _opaque_memory_id(user_id: str, source: str, key: str) -> str:
    return f"mem_{stable_hex('evo', user_id, source, key, n=20)}"


def build_evo_memory(user: dict[str, Any]) -> tuple[list[MemoryItem], list[dict[str, Any]]]:
    """Build deployable memory only from profile and past dialogue history.

    Event timelines, observation annotations, related-session labels, QA
    evidence, reference answers and future topics are evaluator-only and never
    enter the policy/generator view.
    """
    user_id = str(user["id"])
    items: list[MemoryItem] = []
    basic = user.get("basic_info") or {}
    # Preserve profile fields as separate memory units.  A single concatenated
    # profile made external MP-count=1 while training MP contained many units,
    # creating an avoidable representation/domain shortcut.
    for key, value in basic.items():
        if value in (None, ""):
            continue
        items.append(MemoryItem(
            memory_id=_opaque_memory_id(user_id, "MP", str(key)),
            source=MemorySource.MP,
            created_session=0,
            text=f"{str(key).replace('_', ' ').title()}: {value}",
        ))

    session_docs: list[dict[str, Any]] = []
    sessions = user.get("dialog_history") or []
    for index, session in enumerate(sessions, 1):
        timestamp = str(session.get("timestamp") or "")
        session_id = str(session.get("id") or f"session_{index}")
        summary = normalize_space(session.get("summary") or "")
        if summary:
            items.append(MemoryItem(
                memory_id=_opaque_memory_id(user_id, "MS", session_id),
                source=MemorySource.MS,
                created_session=index,
                timestamp=timestamp or None,
                text=summary,
            ))
        seeker_turns = [
            normalize_space(turn.get("content") or "")
            for turn in (session.get("dialogue") or [])
            if turn.get("role") == "seeker" and normalize_space(turn.get("content") or "")
        ]
        if seeker_turns:
            items.append(MemoryItem(
                memory_id=_opaque_memory_id(user_id, "ME", session_id),
                source=MemorySource.ME,
                created_session=index,
                timestamp=timestamp or None,
                text=" ".join(seeker_turns),
            ))
        dialogue_text = "\n".join(
            f"{turn.get('role')}: {normalize_space(turn.get('content') or '')}"
            for turn in (session.get("dialogue") or [])
        )
        session_docs.append({
            "session_id": session_id,
            "session_index": index,
            "timestamp": timestamp,
            "summary": summary,
            "text": dialogue_text,
        })
    return items, session_docs


def evaluator_context(user: dict[str, Any], topic: dict[str, Any]) -> dict[str, Any]:
    """Ground truth available only to post-hoc evaluators.

    The evaluator sees enough authorized history to verify facts and temporal
    updates, but no policy name, action, selected evidence or model score.
    """
    session_by_id = {
        str(row.get("id")): row for row in (user.get("dialog_history") or [])
    }
    timeline = [
        {
            "session_id": str(row.get("id")),
            "timestamp": row.get("timestamp"),
            "summary": row.get("summary"),
        }
        for row in (user.get("dialog_history") or [])
    ]
    related_sessions = []
    for session_id in topic.get("related_sessions") or []:
        session = session_by_id.get(str(session_id))
        if not session:
            continue
        related_sessions.append({
            "session_id": str(session.get("id")),
            "timestamp": session.get("timestamp"),
            "summary": session.get("summary"),
            "dialogue": session.get("dialogue") or [],
            "observations": session.get("observation") or [],
        })
    return {
        "user_profile": user.get("basic_info") or {},
        "past_session_timeline": timeline,
        "detailed_related_sessions": related_sessions,
        "current_topic": {
            "topic": topic.get("topic"),
            "psychological_condition": topic.get("psychological_condition"),
            "physical_condition": topic.get("physical_condition"),
            "more_details": topic.get("more_details"),
        },
        "evaluator_only": True,
    }


def _catalog(items: Sequence[MemoryItem], source: MemorySource, session_index: int) -> SourceCatalog:
    selected = [x for x in items if x.source is source]
    hashvec = HashingVectorizer(
        n_features=64,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
    )
    if selected:
        fp = hashvec.transform(["\n".join(x.text for x in selected)]).toarray()[0]
        ages = [session_index - x.created_session for x in selected]
    else:
        fp = np.zeros(64)
        ages = []
    return SourceCatalog(
        available=bool(selected),
        count=len(selected),
        min_age_sessions=min(ages) if ages else None,
        max_age_sessions=max(ages) if ages else None,
        estimated_tokens=sum(estimate_tokens(x.text) for x in selected),
        catalog_fingerprint=[round(float(x), 8) for x in fp],
    )


def make_evo_runtime_state(
    user: dict[str, Any],
    topic: dict[str, Any],
    conversation: list[dict[str, str]],
    current_user_text: str,
    items: list[MemoryItem],
    turn_index: int,
    condition: str,
    *,
    track_id: str | None = None,
    fixed_open_loop: bool = False,
) -> RuntimeState:
    session_index = max((x.created_session for x in items), default=0) + 1
    # The literal condition label is excluded.  The runtime state ID still
    # includes the actually observed dialogue history, so after turn 1 it may
    # legitimately differ across policies because prior supporter responses
    # are part of the treatment trajectory.  A separate exogenous state ID
    # below identifies the common fixed seeker input for paired analyses.
    transcript_hash = sha256_text(canonical_json(conversation))
    state_id = f"state_{stable_hex('evo-state', user['id'], topic['idx'], track_id or '', turn_index, transcript_hash, current_user_text, n=20)}"
    card_id = f"card_{stable_hex(state_id, n=20)}"
    exogenous_history = [
        normalize_space(row.get("content") or "")
        for row in conversation if row.get("role") == "seeker"
    ]
    exogenous_state_id = f"state_{stable_hex('evo-exogenous-state', user['id'], topic['idx'], track_id or '', turn_index, exogenous_history, current_user_text, n=20)}"
    inventory = {source: _catalog(items, source, session_index) for source in MemorySource}
    available = {src for src, cat in inventory.items() if cat.available}
    from .contracts import ACTION_MEMORY_MAP, canonical_action_id
    allowed = sorted(
        canonical_action_id(sources, strategy)
        for sources in ACTION_MEMORY_MAP.values()
        if sources <= available
        for strategy in StrategyMode
    )
    prior = list(conversation)
    if (
        prior
        and prior[-1].get("role") == "seeker"
        and normalize_space(prior[-1].get("content") or "")
        == normalize_space(current_user_text)
    ):
        prior = prior[:-1]
    history = [
        DialogueTurn(
            role="user" if row["role"] == "seeker" else "assistant",
            content=row["content"],
        )
        for row in prior[-8:]
    ]
    return RuntimeState(
        state_id=state_id,
        card_id=card_id,
        user_id=str(user["id"]),
        split="evoemo_test",
        semantic_family="evoemo_dialogue_generation",
        current_user_text=current_user_text,
        current_session_history=history,
        current_session_summary="",
        session_index=session_index,
        inventory=inventory,
        allowed_actions=allowed,
        provenance={
            "topic_index": int(topic["idx"]),
            "turn_index": int(turn_index),
            "track_id": track_id,
            "condition_label_not_present_in_pm_state": True,
            "runtime_state_includes_prior_treatment_history": not fixed_open_loop,
            "fixed_open_loop_context": fixed_open_loop,
            "fixed_context_sha256": (
                transcript_hash if fixed_open_loop else None
            ),
            "exogenous_state_id": exogenous_state_id,
        },
    )


def seeker_system_prompt(user: dict[str, Any], topic: dict[str, Any]) -> str:
    private = evaluator_context(user, topic)
    return f"""Role-play the emotional-support seeker. Stay faithful to the
private profile and topic. Do not mention that this is a benchmark, do not
reveal the entire hidden card at once, and do not discuss retrieval, policies,
or experimental conditions. Respond naturally to the supporter's latest
message in at most 60 tokens. Do not become artificially agreeable merely
because the supporter suggests something.

Private scenario:
{json.dumps(private, ensure_ascii=False, indent=2)}
"""


def _seeker_next(
    client: OpenAICompatibleClient,
    endpoint: Endpoint,
    system_prompt: str,
    conversation: list[dict[str, str]],
    *,
    seed: int,
    raw_log_path: Path,
    record_ids: dict[str, Any],
) -> str:
    if not conversation or conversation[-1].get("role") != "supporter":
        raise ValueError("seeker generation requires a transcript ending in a supporter turn")
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    # For the seeker model, supporter utterances are user messages and seeker
    # utterances are assistant messages. Every transcript row is included once.
    for row in conversation:
        messages.append({
            "role": "assistant" if row["role"] == "seeker" else "user",
            "content": row["content"],
        })
    result, _ = client.chat(
        messages,
        temperature=0.2,
        max_tokens=60,
        seed=seed,
        response_schema=None,
        retries=3,
    )
    append_jsonl(raw_log_path, request_log(
        stage="evoemo_seeker",
        endpoint=endpoint,
        messages=messages,
        result=result,
        parsed=None,
        error=None,
        prompt_hash=sha256_text(canonical_json(messages)),
        record_ids=record_ids,
    ))
    return normalize_space(result.text)


def _session_rag(query: str, session_docs: list[dict[str, Any]], top_k: int = 4) -> list[MemoryItem]:
    ranked = sorted(
        session_docs,
        key=lambda row: (
            lexical_score(query, row["summary"] + "\n" + row["text"]),
            row["session_index"],
        ),
        reverse=True,
    )[:top_k]
    return [
        MemoryItem(
            memory_id=_opaque_memory_id("session-rag", "ME", row["session_id"]),
            source=MemorySource.ME,
            created_session=row["session_index"],
            timestamp=row["timestamp"] or None,
            text=row["text"],
        )
        for row in ranked
    ]


def _track_key(user_id: str, topic_index: int, seed: int, simulator_id: str) -> tuple[str, int, int, str]:
    return str(user_id), int(topic_index), int(seed), str(simulator_id)


def build_fixed_seeker_tracks(
    evoemo_path: str | Path,
    out_dir: str | Path,
    *,
    seeker_endpoint: Endpoint,
    simulator_id: str,
    max_turns: int = 10,
    seeds: Sequence[int] = (101,),
    max_scenarios: int | None = None,
    overwrite: bool = False,
    study_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    """Generate policy-independent seeker tracks for causal fixed-input tests.

    The track is elicited by a deterministic, generic supporter scaffold. It is
    then replayed unchanged to every policy. This removes the divergent-world
    confound; interactive simulations remain a separate secondary analysis.
    """
    users = load_evoemo(evoemo_path)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    tracks_path = out_dir / "fixed_seeker_tracks.jsonl"
    raw_path = out_dir / "raw_seeker_calls.jsonl"
    summary_path = out_dir / "summary.json"
    manifest_path = out_dir / "run_manifest.json"
    attestation_path = out_dir / "artifact_attestation.json"
    if overwrite:
        for path in (tracks_path, raw_path, summary_path, manifest_path, attestation_path):
            if path.exists():
                path.unlink()
    ensure_run_manifest(manifest_path, {
        "stage": "evoemo_fixed_seeker_tracks",
        "evoemo_sha256": sha256_file(evoemo_path),
        "seeker_model": seeker_endpoint.model,
        "seeker_family": seeker_endpoint.family,
        "seeker_base_url": seeker_endpoint.base_url,
        "simulator_id": simulator_id,
        "max_turns": int(max_turns),
        "seeds": [int(x) for x in seeds],
        "max_scenarios": max_scenarios,
        "scaffold_sha256": sha256_text(canonical_json([NEUTRAL_INITIAL_GREETING, *_NEUTRAL_TRACK_PROBES])),
        "study_freeze_sha256": study_freeze_sha256,
    })
    done = load_done_keys(tracks_path, ("user_id", "topic_index", "seed", "simulator_id"))
    client = OpenAICompatibleClient(seeker_endpoint)
    failures: list[dict[str, Any]] = []
    scenarios: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for user in users:
        for topic in user.get("subsequent_topics") or []:
            scenarios.append((user, topic))
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]
    try:
        for user, topic in scenarios:
            for seed in seeds:
                key = _track_key(str(user["id"]), int(topic["idx"]), int(seed), simulator_id)
                if key in done:
                    continue
                conversation = [{"role": "supporter", "content": NEUTRAL_INITIAL_GREETING}]
                seeker_turns: list[str] = []
                try:
                    for turn_index in range(1, max_turns + 1):
                        message = _seeker_next(
                            client,
                            seeker_endpoint,
                            seeker_system_prompt(user, topic),
                            conversation,
                            seed=int(seed) + turn_index,
                            raw_log_path=raw_path,
                            record_ids={
                                "user_id": str(user["id"]),
                                "topic_index": int(topic["idx"]),
                                "seed": int(seed),
                                "simulator_id": simulator_id,
                                "turn_index": turn_index,
                                "track_generation": True,
                            },
                        )
                        seeker_turns.append(message)
                        conversation.append({"role": "seeker", "content": message})
                        if turn_index < max_turns:
                            probe = _NEUTRAL_TRACK_PROBES[(turn_index - 1) % len(_NEUTRAL_TRACK_PROBES)]
                            conversation.append({"role": "supporter", "content": probe})
                    track_id = f"track_{stable_hex(user['id'], topic['idx'], seed, simulator_id, canonical_json(seeker_turns), n=20)}"
                    append_jsonl(tracks_path, {
                        "track_id": track_id,
                        "user_id": str(user["id"]),
                        "topic_index": int(topic["idx"]),
                        "seed": int(seed),
                        "simulator_id": simulator_id,
                        "seeker_model": seeker_endpoint.model,
                        "seeker_family": seeker_endpoint.family,
                        "initial_greeting": NEUTRAL_INITIAL_GREETING,
                        "seeker_turns": seeker_turns,
                        "elicitation_scaffold": "deterministic_generic_open_loop",
                        "causal_use": "replayed unchanged to all policies",
                    })
                except Exception as exc:
                    failures.append({
                        "user_id": str(user["id"]),
                        "topic_index": int(topic["idx"]),
                        "seed": int(seed),
                        "simulator_id": simulator_id,
                        "error": f"{type(exc).__name__}: {exc}",
                    })
    finally:
        client.close()
    expected = len(scenarios) * len(seeds)
    completed = len(load_done_keys(tracks_path, ("user_id", "topic_index", "seed", "simulator_id")))
    summary = {
        "status": "COMPLETE" if completed == expected and not failures else "INCOMPLETE",
        "simulator_id": simulator_id,
        "seeker_model": seeker_endpoint.model,
        "seeker_family": seeker_endpoint.family,
        "expected_tracks": expected,
        "completed_tracks": completed,
        "max_turns": max_turns,
        "failures": failures,
        "interpretation": "fixed-input causal track; later seeker turns do not react to evaluated policy replies",
    }
    write_json(summary_path, summary)
    if summary["status"] != "COMPLETE":
        raise RuntimeError(f"fixed seeker track generation incomplete: {len(failures)} failures")
    create_artifact_attestation(
        attestation_path,
        stage="evoemo_fixed_seeker_tracks",
        inputs={"evoemo": evoemo_path, "run_manifest": manifest_path},
        outputs={
            "tracks": (tracks_path, True),
            "raw_calls": (raw_path, True),
            "summary": (summary_path, False),
        },
        parameters={
            "simulator_id": simulator_id,
            "max_turns": max_turns,
            "seeds": [int(x) for x in seeds],
        },
        expected={"tracks": expected, "turns_per_track": max_turns},
        study_freeze_sha256=study_freeze_sha256,
    )
    return summary


def _fixed_context_before_turn(
    track: dict[str, Any], turn_index: int
) -> list[dict[str, str]]:
    """Return the policy-independent context used for a one-step comparison.

    Evaluated supporter replies are deliberately absent.  Each turn is a
    separate fixed-context decision point elicited by the neutral scaffold.
    This is a causal one-step stress test, not a simulated closed-loop dialogue.
    """
    turns = [normalize_space(x) for x in (track.get("seeker_turns") or [])]
    if turn_index < 1 or turn_index > len(turns):
        raise ValueError(f"turn_index {turn_index} outside fixed track")
    greeting = normalize_space(
        track.get("initial_greeting") or NEUTRAL_INITIAL_GREETING
    )
    if greeting != NEUTRAL_INITIAL_GREETING:
        raise ValueError("fixed track initial greeting is not the frozen neutral greeting")
    context: list[dict[str, str]] = [
        {"role": "supporter", "content": NEUTRAL_INITIAL_GREETING}
    ]
    for prior_index in range(turn_index - 1):
        context.append({"role": "seeker", "content": turns[prior_index]})
        context.append({
            "role": "supporter",
            "content": _NEUTRAL_TRACK_PROBES[
                prior_index % len(_NEUTRAL_TRACK_PROBES)
            ],
        })
    return context


def _load_fixed_tracks(path: str | Path) -> dict[tuple[str, int, int, str], dict[str, Any]]:
    tracks: dict[tuple[str, int, int, str], dict[str, Any]] = {}
    for row in iter_jsonl(path):
        key = _track_key(row["user_id"], row["topic_index"], row["seed"], row["simulator_id"])
        if key in tracks:
            raise ValueError(f"duplicate fixed track key: {key}")
        tracks[key] = row
    return tracks


def _policy_from_selection(model: PMModel, selection: dict[str, Any]) -> LearnedPMPolicy:
    pm = selection["pm"]
    return LearnedPMPolicy(
        model,
        epsilon=float(pm["epsilon"]),
        tau_misuse=float(pm["tau_misuse"]),
        tau_omission=float(pm["tau_omission"]),
        tau_strategy=float(pm["tau_strategy"]),
        allow_constraint_fallback=bool(pm.get("confirmatory_allow_constraint_fallback", False)),
    )


def _external_ood_preflight(
    model: PMModel,
    users: Sequence[dict[str, Any]],
) -> dict[str, Any]:
    reports: list[dict[str, Any]] = []
    for user in users:
        items, _ = build_evo_memory(user)
        for topic in user.get("subsequent_topics") or []:
            state = make_evo_runtime_state(
                user,
                topic,
                [{"role": "supporter", "content": NEUTRAL_INITIAL_GREETING}],
                "I want to talk about what has been happening.",
                items,
                1,
                "ood_preflight",
                track_id="ood_preflight",
            )
            rows = [(state, action) for action in state.allowed_actions]
            report = model.feature_builder.ood_report(rows)
            reports.append({
                "user_id": str(user["id"]),
                "topic_index": int(topic["idx"]),
                **report,
            })
    severe = [
        row for row in reports
        if row.get("severe_scalar_ood") or row.get("severe_catalog_ood")
    ]
    return {
        "ok": not severe,
        "n_scenarios": len(reports),
        "n_severe": len(severe),
        "severe_examples": severe[:5],
        "required_action": (
            "retrain_on_matched_longitudinal_development_data_or_use_preregistered_ood_baseline"
            if severe else "none"
        ),
    }


def run_evoemo_dialogues(
    evoemo_path: str | Path,
    strategy_bank_path: str | Path,
    checkpoint_path: str | Path,
    selection_path: str | Path,
    out_dir: str | Path,
    *,
    generator_endpoint: Endpoint,
    seeker_endpoint: Endpoint | None,
    simulator_id: str,
    protocol: str = "selective",
    interaction_mode: str = "fixed",
    fixed_tracks_path: str | Path | None = None,
    fixed_tracks_attestation_path: str | Path | None = None,
    conditions: Sequence[str] = (
        "no_memory_r0",
        "no_memory_rs",
        "session_rag_rs",
        "full_history_rs",
        "all_structured_rs",
        "best_fixed",
        "strong_rule",
        "pm",
    ),
    max_turns: int = 10,
    seeds: Sequence[int] = (101,),
    max_scenarios: int | None = None,
    overwrite: bool = False,
    study_freeze_sha256: str | None = None,
) -> dict[str, Any]:
    if protocol not in {"official", "selective"}:
        raise ValueError("protocol must be official or selective")
    if interaction_mode not in {"fixed", "interactive"}:
        raise ValueError("interaction_mode must be fixed or interactive")
    if interaction_mode == "fixed" and fixed_tracks_path is None:
        raise ValueError("fixed_tracks_path is required for fixed-input evaluation")
    fixed_tracks_verification = None
    if interaction_mode == "fixed":
        fixed_tracks_attestation_path = Path(
            fixed_tracks_attestation_path
            or Path(fixed_tracks_path).parent / "artifact_attestation.json"
        )
        fixed_tracks_verification = require_artifact_attestation(
            fixed_tracks_attestation_path,
            required_stage="evoemo_fixed_seeker_tracks",
            required_output_paths={"tracks": fixed_tracks_path},
        )
    if interaction_mode == "interactive" and seeker_endpoint is None:
        raise ValueError("seeker_endpoint is required for interactive evaluation")

    users = load_evoemo(evoemo_path)
    strategy_cards = [StrategyCard.model_validate(row) for row in iter_jsonl(strategy_bank_path)]
    if not strategy_cards:
        raise ValueError("strategy bank is empty")
    strategy_retriever = StrategyRetriever(strategy_cards, top_k=3)
    memory_retriever = MemoryRetriever()
    model = PMModel.load(checkpoint_path)
    selection = read_json(selection_path)
    pm_policy = _policy_from_selection(model, selection)
    best_fixed = FixedPolicy(selection["best_fixed_action"])
    strong_rule = StrongRulePolicy(RuleConfig(**selection["strong_rule"]["config"]), strategy_retriever)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    dialogue_path = out_dir / "dialogues.jsonl"
    turn_path = out_dir / "turns.jsonl"
    raw_path = out_dir / "raw_api_calls.jsonl"
    summary_path = out_dir / "generation_summary.json"
    ood_path = out_dir / "external_ood_preflight.json"
    manifest_path = out_dir / "run_manifest.json"
    attestation_path = out_dir / "artifact_attestation.json"
    if overwrite:
        for path in (dialogue_path, turn_path, raw_path, summary_path, ood_path, manifest_path, attestation_path):
            if path.exists():
                path.unlink()

    tracks = _load_fixed_tracks(fixed_tracks_path) if fixed_tracks_path else {}
    ensure_run_manifest(manifest_path, {
        "stage": "evoemo_generation",
        "evoemo_sha256": sha256_file(evoemo_path),
        "strategy_bank_sha256": sha256_file(strategy_bank_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "selection_sha256": sha256_file(selection_path),
        "fixed_tracks_sha256": sha256_file(fixed_tracks_path) if fixed_tracks_path else None,
        "fixed_tracks_attestation_sha256": (
            fixed_tracks_verification["attestation_sha256"]
            if fixed_tracks_verification else None
        ),
        "generator_model": generator_endpoint.model,
        "generator_family": generator_endpoint.family,
        "generator_base_url": generator_endpoint.base_url,
        "seeker_model": seeker_endpoint.model if seeker_endpoint else None,
        "seeker_family": seeker_endpoint.family if seeker_endpoint else None,
        "seeker_base_url": seeker_endpoint.base_url if seeker_endpoint else None,
        "simulator_id": simulator_id,
        "protocol": protocol,
        "interaction_mode": interaction_mode,
        "fixed_track_design": (
            "policy_independent_open_loop_one_step_v2"
            if interaction_mode == "fixed" else None
        ),
        "conditions": list(conditions),
        "max_turns": int(max_turns),
        "seeds": [int(x) for x in seeds],
        "max_scenarios": max_scenarios,
        "study_freeze_sha256": study_freeze_sha256,
    })

    if "pm" in conditions:
        ood = _external_ood_preflight(model, users)
        write_json(ood_path, ood)
        if not ood["ok"]:
            raise RuntimeError(
                "EvoEmo PM evaluation blocked before API calls by severe feature-domain shift. "
                "Create a matched longitudinal development split and retrain, or run only a "
                "preregistered non-PM OOD baseline. Details: " + str(ood)
            )
    else:
        write_json(ood_path, {"ok": True, "not_applicable": True, "reason": "pm condition not requested"})

    scenarios: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for user in users:
        for topic in user.get("subsequent_topics") or []:
            scenarios.append((user, topic))
    if max_scenarios is not None:
        scenarios = scenarios[:max_scenarios]

    done_fields = ("user_id", "topic_index", "condition", "seed", "simulator_id", "interaction_mode")
    done = load_done_keys(dialogue_path, done_fields)
    generator = OpenAICompatibleClient(generator_endpoint)
    seeker = OpenAICompatibleClient(seeker_endpoint) if seeker_endpoint is not None and interaction_mode == "interactive" else None
    failures: list[dict[str, Any]] = []
    try:
        for user, topic in scenarios:
            items, session_docs = build_evo_memory(user)
            private_prompt = seeker_system_prompt(user, topic)
            for seed in seeds:
                fixed_track = None
                if interaction_mode == "fixed":
                    track_key = _track_key(str(user["id"]), int(topic["idx"]), int(seed), simulator_id)
                    fixed_track = tracks.get(track_key)
                    if fixed_track is None:
                        raise RuntimeError(f"missing fixed seeker track: {track_key}")
                    if len(fixed_track.get("seeker_turns") or []) != max_turns:
                        raise RuntimeError(
                            f"fixed track turn count mismatch for {track_key}: "
                            f"expected {max_turns}, got {len(fixed_track.get('seeker_turns') or [])}"
                        )
                for condition in conditions:
                    key = (
                        str(user["id"]), int(topic["idx"]), condition, int(seed),
                        simulator_id, interaction_mode,
                    )
                    if key in done:
                        continue
                    conversation: list[dict[str, str]] = [
                        {"role": "supporter", "content": NEUTRAL_INITIAL_GREETING}
                    ]
                    turn_records: list[dict[str, Any]] = []
                    evaluation_cases: list[dict[str, Any]] = []
                    track_id = (
                        str(fixed_track["track_id"])
                        if fixed_track is not None
                        else f"interactive_{stable_hex(user['id'], topic['idx'], condition, seed, simulator_id, n=20)}"
                    )
                    try:
                        for turn_index in range(1, max_turns + 1):
                            if fixed_track is not None:
                                seeker_message = normalize_space(
                                    fixed_track["seeker_turns"][turn_index - 1]
                                )
                                state_conversation = _fixed_context_before_turn(
                                    fixed_track, turn_index
                                )
                            else:
                                assert seeker is not None and seeker_endpoint is not None
                                seeker_message = _seeker_next(
                                    seeker,
                                    seeker_endpoint,
                                    private_prompt,
                                    conversation,
                                    seed=int(seed) + turn_index,
                                    raw_log_path=raw_path,
                                    record_ids={
                                        "user_id": str(user["id"]),
                                        "topic_index": int(topic["idx"]),
                                        "condition": condition,
                                        "seed": int(seed),
                                        "simulator_id": simulator_id,
                                        "turn_index": turn_index,
                                        "interaction_mode": interaction_mode,
                                    },
                                )
                                state_conversation = list(conversation)

                            state_start = time.perf_counter()
                            state = make_evo_runtime_state(
                                user,
                                topic,
                                state_conversation,
                                seeker_message,
                                items,
                                turn_index,
                                condition,
                                track_id=track_id,
                                fixed_open_loop=fixed_track is not None,
                            )
                            pre_evidence_ms = (time.perf_counter() - state_start) * 1000.0
                            query = context_query(
                                state.current_user_text,
                                [x.model_dump(mode="json") for x in state.current_session_history],
                                state.current_session_summary,
                            )

                            pm_ood_report = None
                            pm_decision_report = None
                            pm_ms = 0.0
                            retrieval_start = time.perf_counter()
                            catalog_reads = 0
                            if condition == "no_memory_r0":
                                action_id = "M0+R0"
                                memory_view, strategy_view = [], []
                            elif condition == "no_memory_rs":
                                action_id = "M0+RS"
                                memory_view, strategy_view = [], strategy_retriever.retrieve(query)
                            elif condition == "session_rag_rs":
                                action_id = "SESSION_RAG+RS"
                                memory_view = _session_rag(query, session_docs, top_k=4)
                                strategy_view = strategy_retriever.retrieve(query)
                            elif condition == "full_history_rs":
                                action_id = "FULL_HISTORY+RS"
                                memory_view = _session_rag(query, session_docs, top_k=len(session_docs))
                                strategy_view = strategy_retriever.retrieve(query)
                            elif condition == "all_structured_rs":
                                action_id = "ALL_STRUCTURED+RS"
                                memory_view = list(items)
                                strategy_view = strategy_retriever.retrieve(query)
                            elif condition in {"best_fixed", "strong_rule", "pm"}:
                                if condition == "best_fixed":
                                    action_id = best_fixed.choose(state)
                                elif condition == "strong_rule":
                                    catalog_reads = len(state.inventory)
                                    action_id = strong_rule.choose(state)
                                else:
                                    catalog_reads = len(state.inventory)
                                    pm_start = time.perf_counter()
                                    action_id = pm_policy.choose(state)
                                    pm_ms = (time.perf_counter() - pm_start) * 1000.0
                                    pm_ood_report = model.last_ood_report
                                    pm_decision_report = pm_policy.last_decision_report
                                sources, strategy = parse_action_id(action_id)
                                memory_view = memory_retriever.retrieve(query, items, sources)
                                strategy_view = strategy_retriever.retrieve(query) if strategy is StrategyMode.RS else []
                            else:
                                raise ValueError(f"unknown condition: {condition}")
                            retrieval_ms = (time.perf_counter() - retrieval_start) * 1000.0

                            system = OFFICIAL_ESMEM_SYSTEM if protocol == "official" else SELECTIVE_ESMEM_SYSTEM
                            messages = generation_messages(state, memory_view, strategy_view, system_prompt=system)
                            result, _ = generator.chat(
                                messages,
                                temperature=0.0,
                                max_tokens=(60 if protocol == "official" else 100),
                                seed=int(seed) + turn_index,
                                response_schema=None,
                                retries=3,
                            )
                            append_jsonl(raw_path, request_log(
                                stage="evoemo_supporter",
                                endpoint=generator_endpoint,
                                messages=messages,
                                result=result,
                                parsed=None,
                                error=None,
                                prompt_hash=sha256_text(canonical_json(messages)),
                                record_ids={
                                    "user_id": str(user["id"]),
                                    "topic_index": int(topic["idx"]),
                                    "condition": condition,
                                    "seed": int(seed),
                                    "simulator_id": simulator_id,
                                    "turn_index": turn_index,
                                    "interaction_mode": interaction_mode,
                                    "track_id": track_id,
                                },
                            ))
                            supporter_message = normalize_space(result.text)
                            if fixed_track is not None:
                                # Display-only stitched sequence. It is never fed
                                # into a later PM/generator decision or scored as
                                # an interactive dialogue.
                                conversation.extend([
                                    {"role": "seeker", "content": seeker_message},
                                    {"role": "supporter", "content": supporter_message},
                                ])
                                evaluation_cases.append({
                                    "turn_index": turn_index,
                                    "context_before_turn": state_conversation,
                                    "current_seeker_message": seeker_message,
                                    "supporter_response": supporter_message,
                                    "context_sha256": sha256_text(
                                        canonical_json(state_conversation)
                                    ),
                                })
                            else:
                                conversation.extend([
                                    {"role": "seeker", "content": seeker_message},
                                    {"role": "supporter", "content": supporter_message},
                                ])
                            sources_count = len({x.source for x in memory_view})
                            retrieval_calls = sources_count + (1 if strategy_view else 0)
                            memory_tokens = sum(estimate_tokens(x.text) for x in memory_view)
                            strategy_tokens = sum(
                                estimate_tokens(x.guidance_text + x.example_response)
                                for x in strategy_view
                            )
                            base_tokens = estimate_tokens(
                                system
                                + state.current_user_text
                                + state.current_session_summary
                                + "\n".join(x.content for x in state.current_session_history)
                            )
                            cost = CostRecord(
                                pm_input_tokens_est=estimate_tokens(query) + sum(
                                    len(cat.catalog_fingerprint) for cat in state.inventory.values()
                                ),
                                catalog_reads=catalog_reads,
                                pre_evidence_compute_ms=pre_evidence_ms,
                                pm_inference_ms=pm_ms,
                                retrieval_latency_ms=retrieval_ms,
                                generation_latency_ms=result.latency_ms,
                                retrieval_calls=retrieval_calls,
                                reranker_calls=0,
                                memory_tokens=memory_tokens,
                                strategy_tokens=strategy_tokens,
                                base_prompt_tokens=base_tokens,
                                total_input_tokens=(
                                    result.usage["prompt_tokens"]
                                    or base_tokens + memory_tokens + strategy_tokens
                                ),
                                output_tokens=(
                                    result.usage["completion_tokens"]
                                    or estimate_tokens(supporter_message)
                                ),
                                latency_ms=pre_evidence_ms + pm_ms + retrieval_ms + result.latency_ms,
                                api_cost_usd=None,
                            )
                            turn_record = {
                                "user_id": str(user["id"]),
                                "topic_index": int(topic["idx"]),
                                "condition": condition,
                                "protocol": protocol,
                                "interaction_mode": interaction_mode,
                                "trajectory_comparability": (
                                    "causal_fixed_context_one_step"
                                    if interaction_mode == "fixed"
                                    else "associational_divergent_trajectory"
                                ),
                                "simulator_id": simulator_id,
                                "track_id": track_id,
                                "seed": int(seed),
                                "turn_index": turn_index,
                                "state_id": state.state_id,
                                "exogenous_state_id": state.provenance["exogenous_state_id"],
                                "card_id": state.card_id,
                                "context_before_turn": state_conversation,
                                "context_sha256": sha256_text(
                                    canonical_json(state_conversation)
                                ),
                                "seeker_message": seeker_message,
                                "supporter_message": supporter_message,
                                "action_id": action_id,
                                "selected_memory": [x.model_dump(mode="json") for x in memory_view],
                                "selected_strategy": [x.model_dump(mode="json") for x in strategy_view],
                                "cost": cost.model_dump(mode="json"),
                                "input_tokens": cost.total_input_tokens,
                                "output_tokens": cost.output_tokens,
                                "latency_ms": cost.latency_ms,
                                "pm_ood_report": pm_ood_report,
                                "pm_decision_report": pm_decision_report,
                            }
                            append_jsonl(turn_path, turn_record)
                            turn_records.append(turn_record)

                        append_jsonl(dialogue_path, {
                            "user_id": str(user["id"]),
                            "topic_index": int(topic["idx"]),
                            "condition": condition,
                            "protocol": protocol,
                            "interaction_mode": interaction_mode,
                            "trajectory_comparability": (
                                "causal_fixed_context_one_step"
                                if interaction_mode == "fixed"
                                else "associational_divergent_trajectory"
                            ),
                            "simulator_id": simulator_id,
                            "track_id": track_id,
                            "seed": int(seed),
                            "initial_greeting": NEUTRAL_INITIAL_GREETING,
                            "dialogue": conversation,
                            "dialogue_semantics": (
                                "display_only_stitched_open_loop_cases"
                                if interaction_mode == "fixed"
                                else "actual_interactive_trajectory"
                            ),
                            "evaluation_cases": evaluation_cases,
                            "turns": turn_records,
                        })
                    except Exception as exc:
                        failures.append({
                            "user_id": str(user["id"]),
                            "topic_index": int(topic["idx"]),
                            "condition": condition,
                            "seed": int(seed),
                            "simulator_id": simulator_id,
                            "interaction_mode": interaction_mode,
                            "error": f"{type(exc).__name__}: {exc}",
                        })
    finally:
        generator.close()
        if seeker is not None:
            seeker.close()

    expected = len(scenarios) * len(conditions) * len(seeds)
    completed_keys = load_done_keys(dialogue_path, done_fields)
    completed = len(completed_keys)
    malformed = []
    for row in iter_jsonl(dialogue_path):
        if len(row.get("turns") or []) != max_turns:
            malformed.append({
                "user_id": row.get("user_id"),
                "topic_index": row.get("topic_index"),
                "condition": row.get("condition"),
                "seed": row.get("seed"),
                "n_turns": len(row.get("turns") or []),
            })
        if not row.get("dialogue") or row["dialogue"][0] != {
            "role": "supporter", "content": NEUTRAL_INITIAL_GREETING
        }:
            malformed.append({
                "key": [row.get(x) for x in done_fields],
                "error": "missing neutral initial greeting",
            })
        if row.get("interaction_mode") == "fixed":
            cases = row.get("evaluation_cases") or []
            if len(cases) != max_turns:
                malformed.append({
                    "key": [row.get(x) for x in done_fields],
                    "error": "fixed track lacks one evaluation case per turn",
                })
            for turn in row.get("turns") or []:
                context = turn.get("context_before_turn") or []
                if not context or context[0] != {
                    "role": "supporter", "content": NEUTRAL_INITIAL_GREETING
                }:
                    malformed.append({
                        "key": [row.get(x) for x in done_fields],
                        "turn": turn.get("turn_index"),
                        "error": "bad fixed context",
                    })

    if interaction_mode == "fixed":
        # Every condition must see the exact same full context and seeker turn
        # at a comparison point. This catches accidental treatment-history
        # feedback or condition leakage before any judging begins.
        state_groups: dict[tuple[Any, ...], set[tuple[Any, ...]]] = {}
        for row in iter_jsonl(dialogue_path):
            for turn in row.get("turns") or []:
                group_key = (
                    row.get("user_id"), row.get("topic_index"), row.get("seed"),
                    row.get("simulator_id"), turn.get("turn_index"),
                )
                signature = (
                    turn.get("state_id"), turn.get("exogenous_state_id"),
                    turn.get("context_sha256"), turn.get("seeker_message"),
                )
                state_groups.setdefault(group_key, set()).add(signature)
        for key, signatures in state_groups.items():
            if len(signatures) != 1:
                malformed.append({
                    "key": key,
                    "error": "fixed-context state differs across conditions",
                    "n_signatures": len(signatures),
                })
    status = "COMPLETE" if completed == expected and not failures and not malformed else "INCOMPLETE"
    summary = {
        "status": status,
        "protocol": protocol,
        "interaction_mode": interaction_mode,
        "trajectory_interpretation": (
            "causal one-step policy comparison on identical full contexts; "
            "evaluated replies are not fed into later turns"
            if interaction_mode == "fixed"
            else "secondary associational simulation; policy worlds diverge"
        ),
        "simulator_id": simulator_id,
        "conditions": list(conditions),
        "seeds": [int(x) for x in seeds],
        "max_turns": max_turns,
        "scenarios_attempted": len(scenarios),
        "expected_dialogues": expected,
        "completed_dialogues": completed,
        "malformed": malformed,
        "failures": failures,
        "evoemo_sha256": sha256_file(evoemo_path),
        "strategy_bank_sha256": sha256_file(strategy_bank_path),
        "checkpoint_sha256": sha256_file(checkpoint_path),
        "selection_sha256": sha256_file(selection_path),
        "fixed_tracks_sha256": sha256_file(fixed_tracks_path) if fixed_tracks_path else None,
        "fixed_tracks_attestation_verification": fixed_tracks_verification,
        "generated_at": utc_now(),
    }
    write_json(summary_path, summary)
    if status != "COMPLETE":
        raise RuntimeError(
            f"EvoEmo generation incomplete: failures={len(failures)}, "
            f"malformed={len(malformed)}, completed={completed}/{expected}"
        )
    create_artifact_attestation(
        attestation_path,
        stage="evoemo_generation",
        inputs={
            "evoemo": evoemo_path,
            "strategy_bank": strategy_bank_path,
            "checkpoint": checkpoint_path,
            "selection": selection_path,
            "run_manifest": manifest_path,
            **({"fixed_tracks": fixed_tracks_path} if fixed_tracks_path else {}),
            **({"fixed_tracks_attestation": fixed_tracks_attestation_path} if fixed_tracks_verification else {}),
        },
        outputs={
            "dialogues": (dialogue_path, True),
            "turns": (turn_path, True),
            "raw_calls": (raw_path, True),
            "summary": (summary_path, False),
            "ood_preflight": (ood_path, False),
        },
        parameters={
            "protocol": protocol,
            "interaction_mode": interaction_mode,
            "fixed_track_design": (
                "policy_independent_open_loop_one_step_v2"
                if interaction_mode == "fixed" else None
            ),
            "simulator_id": simulator_id,
            "conditions": list(conditions),
            "max_turns": max_turns,
            "seeds": [int(x) for x in seeds],
        },
        expected={
            "dialogues": expected,
            "turns": expected * max_turns,
        },
        study_freeze_sha256=study_freeze_sha256,
    )
    return summary
