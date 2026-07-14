from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal, Sequence

import numpy as np
from pydantic import Field, model_validator
from sklearn.feature_extraction.text import HashingVectorizer

from .api import Endpoint, make_client
from .contracts import (
    ACTION_MEMORY_MAP,
    DialogueTurn,
    MemoryBackendRecord,
    MemoryItem,
    MemorySource,
    RuntimeState,
    SourceCatalog,
    StrategyMode,
    canonical_action_id,
)
from .io import append_jsonl, canonical_json, sha256_text, write_json
from .pm_v2_contracts import (
    ObservableSourceSummary,
    PMV2Split,
    PMV2State,
    ResourceNeedRegime,
    SplitManifest,
    StrictModel,
)


SPACE_RE = re.compile(r"\s+")


def normalize_text(text: str) -> str:
    return SPACE_RE.sub(" ", text.strip().lower())


class GeneratedMemory(StrictModel):
    memory_id: str
    source: MemorySource
    text: str = Field(min_length=1)
    created_session: int = Field(ge=0)
    stale: bool = False
    conflicts_with_current_state: bool = False
    private_sensitivity: Literal["ordinary", "sensitive"] = "ordinary"


class GeneratedStateCase(StrictModel):
    case_id: str
    semantic_family: str = Field(min_length=1)
    surface_form_id: str = Field(min_length=1)
    regime: ResourceNeedRegime
    current_user_text: str = Field(min_length=1)
    recent_dialogue: list[DialogueTurn]
    session_summary: str
    session_index: int = Field(ge=1)
    profile_memories: list[GeneratedMemory]
    summary_memories: list[GeneratedMemory]
    event_memories: list[GeneratedMemory]
    strategy_catalog_count: int = Field(default=20, ge=0)
    strategy_estimated_tokens: int = Field(default=240, ge=0)
    authorized_user_context: str = Field(min_length=1)
    coverage_rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def source_consistency(self):
        expected = {
            "profile_memories": MemorySource.MP,
            "summary_memories": MemorySource.MS,
            "event_memories": MemorySource.ME,
        }
        for field_name, source in expected.items():
            if any(item.source is not source for item in getattr(self, field_name)):
                raise ValueError(f"{field_name} contains a wrong source")
        return self


class GeneratedUserBundle(StrictModel):
    user_id: str
    profile_summary: str = Field(min_length=1)
    stable_preferences: list[str]
    boundaries: list[str]
    cases: list[GeneratedStateCase] = Field(min_length=4)
    generator_seed_id: str
    provenance: dict[str, Any] = Field(default_factory=dict)


REGIME_INSTRUCTIONS: dict[ResourceNeedRegime, str] = {
    ResourceNeedRegime.CONTEXT_ONLY: (
        "The current turn must be fully understandable from recent dialogue. Long-term "
        "memory and strategy cards should add little value or make the reply less natural."
    ),
    ResourceNeedRegime.PROFILE_NEEDED: (
        "A stable preference, boundary, or personal constraint from profile memory is "
        "material to a good response. Other memories should be distractors."
    ),
    ResourceNeedRegime.SUMMARY_NEEDED: (
        "A cross-session pattern summarized in MS is material, while isolated events are "
        "insufficient or misleading."
    ),
    ResourceNeedRegime.EVENT_NEEDED: (
        "A concrete past event in ME is material to understanding the current turn. "
        "Generic summaries and strategy cards should not be necessary."
    ),
    ResourceNeedRegime.MULTI_SOURCE_NEEDED: (
        "A good reply needs complementary information from at least two memory sources."
    ),
    ResourceNeedRegime.MEMORY_HARMFUL: (
        "Available memories must include stale, weakly related, or conflicting material. "
        "The safest response should avoid long-term memory."
    ),
    ResourceNeedRegime.STRATEGY_HELPFUL: (
        "The current state benefits from structured emotional-support guidance, while "
        "memory alone is not enough."
    ),
    ResourceNeedRegime.STRATEGY_HARMFUL: (
        "Strategy cards would make the reply premature, formulaic, or overly directive. "
        "A natural context-grounded response should keep strategy retrieval off."
    ),
    ResourceNeedRegime.AMBIGUOUS: (
        "Several low-cost actions should be genuinely competitive; do not create an "
        "obvious high-resource winner."
    ),
}


def generation_messages(
    *,
    seed_dialogue: str,
    user_id: str,
    semantic_families: Sequence[str],
    regimes: Sequence[ResourceNeedRegime],
) -> list[dict[str, str]]:
    regime_text = "\n".join(
        f"- {regime.value}: {REGIME_INSTRUCTIONS[regime]}" for regime in regimes
    )
    system = """You create privacy-safe synthetic longitudinal emotional-support users for
training a pre-retrieval resource policy. Generate natural, diverse English. Do not copy
names or events from known benchmarks. Avoid clinical diagnosis, self-harm, acute crisis,
or treatment instructions. The output is development data, not a conversation answer."""
    user = f"""SEED DIALOGUE (style and topic inspiration only; do not copy phrases)
{seed_dialogue}

CREATE USER ID: {user_id}
SEMANTIC FAMILIES: {', '.join(semantic_families)}

Create one case for every requested regime below. Each case must contain a current turn,
recent dialogue, session summary, authorized longitudinal context, and MP/MS/ME memory
items. Include relevant and irrelevant items so source selection is non-trivial. Use at
least two distinct surface forms per semantic family across the bundle. Do not state the
best action or include action codes in user-facing text.

REGIMES
{regime_text}

CRITICAL BALANCE RULES
1. At least one case must make M0+R0 preferable.
2. At least one case must make R0 preferable with memory on.
3. At least one case must make RS helpful.
4. Event memory must not be universally best.
5. Full memory must not be universally best.
6. Do not reuse the same current-user sentence structure.
7. Memories must include timestamps through created_session and explicit stale/conflict flags.
Return strict JSON matching GeneratedUserBundle."""
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def generate_user_bundle(
    *,
    endpoint: Endpoint,
    seed_dialogue: str,
    user_id: str,
    semantic_families: Sequence[str],
    regimes: Sequence[ResourceNeedRegime],
    seed: int,
) -> GeneratedUserBundle:
    client = make_client(endpoint)
    try:
        messages = generation_messages(
            seed_dialogue=seed_dialogue,
            user_id=user_id,
            semantic_families=semantic_families,
            regimes=regimes,
        )
        call, bundle = client.chat(
            messages,
            temperature=0.8,
            max_tokens=6000,
            seed=seed,
            response_schema=GeneratedUserBundle,
            retries=4,
        )
        assert bundle is not None
        bundle.user_id = user_id
        bundle.generator_seed_id = sha256_text(seed_dialogue)[:16]
        bundle.provenance.update(
            {
                "generator_model": endpoint.model,
                "generator_family": endpoint.family,
                "request_hash": call.request_hash,
                "messages_hash": sha256_text(canonical_json(messages)),
            }
        )
        return bundle
    finally:
        client.close()


def _catalog_summary(
    *,
    source: MemorySource,
    memories: Sequence[GeneratedMemory],
    query_text: str,
    session_index: int,
    n_features: int = 64,
) -> ObservableSourceSummary:
    if not memories:
        return ObservableSourceSummary(available=False, count=0, estimated_tokens=0)
    vectorizer = HashingVectorizer(
        n_features=n_features,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
    )
    q = vectorizer.transform([query_text]).toarray()[0]
    matrix = vectorizer.transform([memory.text for memory in memories]).toarray()
    similarities = matrix @ q
    ages = [max(0, session_index - memory.created_session) for memory in memories]
    estimated_tokens = sum(max(1, len(memory.text.split())) for memory in memories)
    catalog = matrix.mean(axis=0)
    return ObservableSourceSummary(
        available=True,
        count=len(memories),
        min_age_sessions=min(ages),
        median_age_sessions=float(np.median(ages)),
        max_age_sessions=max(ages),
        estimated_tokens=estimated_tokens,
        query_similarity_mean=float(np.mean(similarities)),
        query_similarity_max=float(np.max(similarities)),
        query_similarity_p90=float(np.quantile(similarities, 0.90)),
        stale_fraction=float(np.mean([memory.stale for memory in memories])),
        conflict_fraction=float(
            np.mean([memory.conflicts_with_current_state for memory in memories])
        ),
        catalog_embedding=[float(value) for value in catalog],
    )


def case_to_state(
    *,
    user_id: str,
    case: GeneratedStateCase,
    split: PMV2Split,
    bundle_provenance: dict[str, Any] | None = None,
) -> PMV2State:
    query = "\n".join(
        [case.current_user_text, case.session_summary]
        + [turn.content for turn in case.recent_dialogue]
    )
    memories = {
        MemorySource.MP: case.profile_memories,
        MemorySource.MS: case.summary_memories,
        MemorySource.ME: case.event_memories,
    }
    inventory = {
        source: _catalog_summary(
            source=source,
            memories=items,
            query_text=query,
            session_index=case.session_index,
        )
        for source, items in memories.items()
    }
    available = {source for source, summary in inventory.items() if summary.available}
    allowed_actions = sorted(
        {
            canonical_action_id(sources, strategy)
            for sources in ACTION_MEMORY_MAP.values()
            if sources <= available
            for strategy in StrategyMode
        }
    )
    state_id = "state_" + sha256_text(f"{user_id}|{case.case_id}|{case.surface_form_id}")[:24]
    card_id = "card_" + sha256_text(f"{state_id}|{case.regime.value}")[:24]
    return PMV2State(
        state_id=state_id,
        card_id=card_id,
        user_id=user_id,
        split=split,
        semantic_family=case.semantic_family,
        surface_form_id=case.surface_form_id,
        current_user_text=case.current_user_text,
        current_session_history=case.recent_dialogue,
        current_session_summary=case.session_summary,
        session_index=case.session_index,
        inventory=inventory,
        strategy_catalog_count=case.strategy_catalog_count,
        strategy_estimated_tokens=case.strategy_estimated_tokens,
        allowed_actions=allowed_actions,
        provenance={
            **(bundle_provenance or {}),
            "regime": case.regime.value,
            "authorized_user_context": case.authorized_user_context,
            "coverage_rationale": case.coverage_rationale,
            "memory_items": {
                source.value: [item.model_dump(mode="json") for item in items]
                for source, items in memories.items()
            },
        },
    )


def validate_bundle(bundle: GeneratedUserBundle) -> dict[str, Any]:
    regimes = Counter(case.regime.value for case in bundle.cases)
    current_texts = [normalize_text(case.current_user_text) for case in bundle.cases]
    if len(current_texts) != len(set(current_texts)):
        raise ValueError(f"bundle {bundle.user_id} repeats normalized current-user text")
    required = {
        ResourceNeedRegime.CONTEXT_ONLY.value,
        ResourceNeedRegime.EVENT_NEEDED.value,
        ResourceNeedRegime.STRATEGY_HELPFUL.value,
        ResourceNeedRegime.STRATEGY_HARMFUL.value,
    }
    missing = required - set(regimes)
    if missing:
        raise ValueError(f"bundle {bundle.user_id} missing required regimes: {sorted(missing)}")
    for case in bundle.cases:
        if not case.profile_memories and not case.summary_memories and not case.event_memories:
            raise ValueError(f"case {case.case_id} has no inventory variation")
    return {
        "user_id": bundle.user_id,
        "case_count": len(bundle.cases),
        "regime_distribution": dict(regimes),
        "semantic_families": sorted({case.semantic_family for case in bundle.cases}),
    }


def validate_split_manifests(split_states: dict[PMV2Split, Sequence[PMV2State]]) -> SplitManifest:
    train = split_states.get(PMV2Split.TRAIN, [])
    calibration = split_states.get(PMV2Split.CALIBRATION, [])
    test = split_states.get(PMV2Split.INTERNAL_TEST, [])
    user_sets = [{state.user_id for state in rows} for rows in (train, calibration, test)]
    family_sets = [{state.semantic_family for state in rows} for rows in (train, calibration, test)]
    text_sets = [{normalize_text(state.current_user_text) for state in rows} for rows in (train, calibration, test)]
    user_overlap = sum(len(user_sets[i] & user_sets[j]) for i in range(3) for j in range(i + 1, 3))
    family_overlap = sum(
        len(family_sets[i] & family_sets[j]) for i in range(3) for j in range(i + 1, 3)
    )
    text_overlap = sum(len(text_sets[i] & text_sets[j]) for i in range(3) for j in range(i + 1, 3))
    return SplitManifest(
        train_users=sorted(user_sets[0]),
        calibration_users=sorted(user_sets[1]),
        internal_test_users=sorted(user_sets[2]),
        train_semantic_families=sorted(family_sets[0]),
        calibration_semantic_families=sorted(family_sets[1]),
        internal_test_semantic_families=sorted(family_sets[2]),
        normalized_text_overlap=text_overlap,
        user_overlap=user_overlap,
        semantic_family_overlap=family_overlap,
    )


def state_to_v1_runtime(state: PMV2State) -> RuntimeState:
    inventory = {}
    for source, summary in state.inventory.items():
        fp = list(summary.catalog_embedding)
        if len(fp) < 64:
            fp = fp + [0.0] * (64 - len(fp))
        elif len(fp) > 64:
            fp = fp[:64]
        inventory[source] = SourceCatalog(
            available=summary.available,
            count=summary.count,
            min_age_sessions=summary.min_age_sessions,
            max_age_sessions=summary.max_age_sessions,
            estimated_tokens=summary.estimated_tokens,
            catalog_fingerprint=fp,
        )
    split_map = {
        PMV2Split.TRAIN: "train",
        PMV2Split.CALIBRATION: "validation",
        PMV2Split.INTERNAL_TEST: "development",
        PMV2Split.EXTERNAL_TEST: "evoemo_test",
    }
    return RuntimeState(
        state_id=state.state_id,
        card_id=state.card_id,
        user_id=state.user_id,
        split=split_map[state.split],
        semantic_family=state.semantic_family,
        current_user_text=state.current_user_text,
        current_session_history=state.current_session_history,
        current_session_summary=state.current_session_summary,
        session_index=state.session_index,
        inventory=inventory,
        allowed_actions=state.allowed_actions,
        provenance={**state.provenance, "pm_v2_state_id": state.state_id},
    )


def state_to_memory_backend(state: PMV2State) -> MemoryBackendRecord:
    raw = state.provenance.get("memory_items") or {}
    items: list[MemoryItem] = []
    for source in MemorySource:
        for index, row in enumerate(raw.get(source.value, [])):
            memory_id = "mem_" + sha256_text(
                f"{state.card_id}|{source.value}|{index}|{row.get('text','')}"
            )[:24]
            items.append(
                MemoryItem(
                    memory_id=memory_id,
                    source=source,
                    created_session=int(row.get("created_session", 0)),
                    text=str(row["text"]),
                )
            )
    return MemoryBackendRecord(card_id=state.card_id, items=items)


def write_development_dataset(
    *,
    bundles: Sequence[GeneratedUserBundle],
    split_by_user: dict[str, PMV2Split],
    out_dir: str | Path,
) -> dict[str, Any]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    states_by_split: dict[PMV2Split, list[PMV2State]] = {
        split: [] for split in (PMV2Split.TRAIN, PMV2Split.CALIBRATION, PMV2Split.INTERNAL_TEST)
    }
    bundle_reports = []
    for bundle in bundles:
        bundle_reports.append(validate_bundle(bundle))
        try:
            split = split_by_user[bundle.user_id]
        except KeyError as exc:
            raise ValueError(f"no split assigned for user {bundle.user_id}") from exc
        for case in bundle.cases:
            states_by_split[split].append(
                case_to_state(
                    user_id=bundle.user_id,
                    case=case,
                    split=split,
                    bundle_provenance=bundle.provenance,
                )
            )
    manifest = validate_split_manifests(states_by_split)
    all_states = [state for rows in states_by_split.values() for state in rows]
    state_path = out_dir / "pm_v2_states.jsonl"
    runtime_path = out_dir / "runtime_states.jsonl"
    backend_path = out_dir / "memory_backend.jsonl"
    for path in (state_path, runtime_path, backend_path):
        path.write_text("", encoding="utf-8")
    for state in all_states:
        append_jsonl(state_path, state.model_dump(mode="json"))
        append_jsonl(runtime_path, state_to_v1_runtime(state).model_dump(mode="json"))
        append_jsonl(backend_path, state_to_memory_backend(state).model_dump(mode="json"))
    bundle_path = out_dir / "pm_v2_bundles.jsonl"
    bundle_path.write_text("", encoding="utf-8")
    for bundle in bundles:
        append_jsonl(bundle_path, bundle.model_dump(mode="json"))
    report = {
        "status": "COMPLETE",
        "n_users": len(bundles),
        "n_states": len(all_states),
        "split_counts": {
            split.value: len(rows) for split, rows in states_by_split.items()
        },
        "split_manifest": manifest.model_dump(mode="json"),
        "bundle_reports": bundle_reports,
        "states_path": str(state_path),
        "runtime_path": str(runtime_path),
        "memory_backend_path": str(backend_path),
        "bundles_path": str(bundle_path),
    }
    write_json(out_dir / "pm_v2_data_report.json", report)
    return report


def load_states(path: str | Path) -> list[PMV2State]:
    states: list[PMV2State] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                states.append(PMV2State.model_validate(json.loads(line)))
    return states


def load_bundles(path: str | Path) -> list[GeneratedUserBundle]:
    bundles: list[GeneratedUserBundle] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        for line in handle:
            if line.strip():
                bundles.append(GeneratedUserBundle.model_validate(json.loads(line)))
    return bundles


def runtime_to_pmv2_state(
    state: RuntimeState,
    *,
    split: PMV2Split = PMV2Split.EXTERNAL_TEST,
    strategy_catalog_count: int = 0,
    strategy_estimated_tokens: int = 240,
) -> PMV2State:
    query = "\n".join(
        [state.current_user_text, state.current_session_summary]
        + [turn.content for turn in state.current_session_history]
    )
    hashvec = HashingVectorizer(
        n_features=64,
        alternate_sign=False,
        norm="l2",
        lowercase=True,
        ngram_range=(1, 2),
    )
    q = hashvec.transform([query]).toarray()[0]
    inventory: dict[MemorySource, ObservableSourceSummary] = {}
    for source, cat in state.inventory.items():
        fp = np.asarray(cat.catalog_fingerprint, dtype=float)
        similarity = 0.0
        if fp.size and np.linalg.norm(fp) > 0 and np.linalg.norm(q) > 0:
            similarity = float(fp @ q / (np.linalg.norm(fp) * np.linalg.norm(q)))
        inventory[source] = ObservableSourceSummary(
            available=cat.available,
            count=cat.count,
            min_age_sessions=cat.min_age_sessions,
            median_age_sessions=(
                float(cat.min_age_sessions + cat.max_age_sessions) / 2.0
                if cat.min_age_sessions is not None and cat.max_age_sessions is not None
                else None
            ),
            max_age_sessions=cat.max_age_sessions,
            estimated_tokens=cat.estimated_tokens,
            query_similarity_mean=similarity,
            query_similarity_max=similarity,
            query_similarity_p90=similarity,
            stale_fraction=float(state.provenance.get(f"{source.value}_stale_fraction", 0.0)),
            conflict_fraction=float(
                state.provenance.get(f"{source.value}_conflict_fraction", 0.0)
            ),
            catalog_embedding=[float(value) for value in fp],
        )
    return PMV2State(
        state_id=state.state_id,
        card_id=state.card_id,
        user_id=state.user_id,
        split=split,
        semantic_family=state.semantic_family,
        surface_form_id=str(state.provenance.get("surface_form_id", state.state_id)),
        current_user_text=state.current_user_text,
        current_session_history=state.current_session_history,
        current_session_summary=state.current_session_summary,
        session_index=state.session_index,
        inventory=inventory,
        strategy_catalog_count=strategy_catalog_count,
        strategy_estimated_tokens=strategy_estimated_tokens,
        allowed_actions=state.allowed_actions,
        provenance={**state.provenance, "adapted_from_runtime_state": True},
    )
