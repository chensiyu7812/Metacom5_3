"""B28/B28R: official ES-MemEval RQ2 runtime-visibility / baseline-contract audit.

Zero-outcome, static source-code audit -- not computed from ``evo_emo.json``
or the sanitized runtime artifact at all. This module is a hand-encoded,
mechanically-verified record of exactly what the pinned official ES-MemEval
harness (repository ``slptongji/ES-MemEval``, tag ``v1.0.0``, commit
``692624208acc077b8867698c1d6fcd998dee641a``) actually does, read directly
from that commit's source via the GitHub API before writing anything here
(every claim below cites the specific file(s)/function(s) it came from; see
``AUDITED_SOURCE_FILES`` for the exact blob sha of every file read, and
``AUDITED_SOURCE_TREES`` for the exact tree sha of directories enumerated in
full to support an *absence* claim -- an absence claim needs a complete
directory listing, not a curated set of blobs someone chose to fetch).

The public artifact this project uses is ``ES-MemEval-Public-v1.0.0-1427``
-- the pinned public release, not a row-exact reproduction of the paper's
1209-QA figure (``PAPER_QA_COUNT``/``PUBLIC_QA_COUNT`` in
``metacom_pm.paper1.data.materializer``); this module never conflates the
two.

B28R correction: the four surfaces below are NOT guaranteed pairwise
non-overlapping, and this module no longer claims they are.

- **A -- retrieval corpus**: which strict-past session/document a
  Retriever *could* index. Being indexable does NOT mean the text is
  currently in the Generator's prompt -- see
  ``CANDIDATE_VS_PROMPT_VISIBILITY_NOTE``, which now also states the
  concrete conditions (truncation, corpus size <= top-k) under which A and
  C do *not* coincide, rather than asserting unconditional coincidence.
- **B -- query-state only**: the official harness has NO PM/memory-
  selection component at all (see ``SURFACE_B_NO_PM_IN_HARNESS_NOTE``).
  This surface names only the officially-visible current query/turn text a
  future PM's decision would be built from. A future PM's actual decision
  input = surface-A-selected candidate outcome-blind descriptors + this
  surface-B query-state -- never surface C or D.
- **C -- Generator-visible prompt/context**: what actually ends up inside
  the frozen Generator's final prompt for this arm.
- **D -- not tested-supporter-visible**: everything that never reaches the
  supporter's own prompt. B28R splits this into three sub-categories that
  are themselves not mutually exclusive (a field can be both
  hidden-seeker-simulator-only AND postgeneration-evaluator-only -- see
  ``FIELD_VISIBILITY_TABLE``'s ``dialog_history[].summary``/
  ``subsequent_topics[].topic`` rows for real examples): ``hidden_seeker_
  simulator_only`` (DG's own simulator-only background), ``postgeneration_
  evaluator_only`` (actually read by a scorer/judge, strictly after
  generation), and ``unused_official_metadata`` (present in the raw schema
  but never read by any of the three audited experiment scripts at all --
  B28R correction: this project previously mislabeled these as
  "evaluator-only", which overclaims that a consumer reads them).

``FIELD_VISIBILITY_TABLE`` replaces the old flat ``EVALUATOR_ONLY_FIELDS``
set with a field-level table -- ``basic_info`` in particular is field-
split: ``basic_info.name`` reaches the tested supporter's own prompt
directly (DG's fixed greeting/system message, and QA/Summarization's
Full-History/RAG document human-turn labels), while age/gender/
nationality/location/job/education never do.

This module never runs generation, never calls a scorer, never invokes
BGE-M3 or any embedding model, and never reads ``evo_emo.json`` -- it is a
pure, hardcoded documentation-and-schema artifact, checked by tests for
internal consistency and against the pinned blob/tree identities above.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

PINNED_REPOSITORY = "slptongji/ES-MemEval"
PINNED_TAG = "v1.0.0"
PINNED_COMMIT = "692624208acc077b8867698c1d6fcd998dee641a"
PUBLIC_ARTIFACT_NAME = "ES-MemEval-Public-v1.0.0-1427"
PUBLIC_ARTIFACT_NOTE = (
    "The public artifact this project uses is the pinned "
    "ES-MemEval-Public-v1.0.0-1427 release, not a row-exact reproduction "
    "of the paper's 1209-QA figure -- see PAPER_QA_COUNT vs. "
    "PUBLIC_QA_COUNT in metacom_pm.paper1.data.materializer."
)

# path (relative to repo root) -> git blob sha at PINNED_COMMIT, fetched via
# `gh api repos/slptongji/ES-MemEval/contents/<path>?ref=<PINNED_COMMIT>`.
AUDITED_SOURCE_FILES: dict[str, str] = {
    "src/lib/shared/chat_rooms/chat_room.py": "4bab80c5d3061696aefe90c12651e097441744b1",
    "src/lib/shared/chat_rooms/chat_room_builder.py": "67599e8a00095cace875ce073f802451818bb987",
    "src/lib/qa/qa_experiment.py": "a58d29787b4500f9ba4ba2556398bee0584e9df0",
    "src/lib/qa/qa_experiment_parameters.py": "0c65ef8abb5eb4d4250a5a688aa30edd2e885a67",
    "src/exe/qa/qa_gpt4o_full.py": "763617b87d40bae269d8245ff183d03e7cb1297a",
    "src/exe/qa/qa_gpt4o_rag.py": "06b00c8184c41079460bc32d2056ca26b2b56b31",
    "src/lib/sum/sum_experiment.py": "594f140bf2a832e635c3fa338b569899f37730f9",
    "src/lib/sum/sum_experiment_parameters.py": "837dae7e9d6ff69e2d3e1b02b10ed9d62eff2505",
    "src/exe/sum/sum_gpt4o_full.py": "1a7cf4b5b1920ac379166903e4448a8d08a2733b",
    "src/exe/sum/sum_gpt4o_rag.py": "c106a0518b1d3dc34c224892d4ce8c1a6f651a2c",
    "src/lib/dg/dg_experiment.py": "13b2288a26beb378e1239744f412b6e5fbebd1df",
    "src/lib/dg/dg_experiment_parameters.py": "9c9145fbd8248390a086d571716329fa0097905f",
    "src/exe/dg/dg_gpt4o.py": "346a57b4687afbe9be9c1b56281d4fc572f639a8",
    "src/exe/dg/dg_gpt4o_full.py": "34eaf2ac9d95c0f1d8335a8a040e8f293c0655c2",
    "src/exe/dg/dg_gpt4o_rag.py": "78159947f2b4ba4003885497701dc5462df84f2d",
    "src/lib/shared/document_stores/document_store.py": "82e8469f108761f67bd3789e411a2fe31eb7800e",
    "src/lib/shared/document_stores/vector_document_store.py": "66fc315f878e40e78c2bef2315e51dfe511f3867",
    "src/lib/shared/document_stores/always_all_document_store.py": "2a32d4890a52bab1346616e085b606bdebc027f4",
    "src/lib/shared/embedding_models/embedding_provider.py": "a98510f2304afeadc415d5391db4f64a412ad6f7",
    "src/lib/shared/prompt_strategies/prompt_strategy.py": "34ba10cad03e2c9a949c36bd7825431d61a9be4f",
    "src/lib/shared/prompt_strategies/fixed_strategy.py": "9ad479828d230d6415de7415e0367d647da72762",
    "src/lib/shared/prompt_strategies/mixed_strategy.py": "caefcc7f1fafbb79cbc5fe5a2819c4df32913c3f",
    "src/lib/shared/prompt_strategies/session_wise_memory_inplace_strategy.py": "e8efc593aa4fdbb9e038448500484a5de2f6a779",
    "src/lib/shared/prompt_strategies/session_wise_memory_prepend_strategy.py": "a88a419a988912c899a369bba8c686f02accf586",
    "src/lib/shared/prompt_strategies/no_prompt_strategy.py": "2196f95a53adce81ba4e16eec49d5c43e7254a6b",
    "src/lib/shared/prompt_strategies/session_information.py": "f51eb80dcc797f9d150e68490c72d9c1d7113c6b",
    "src/lib/shared/data_provider/raw_seeker.py": "b93d5a9842f1fc9e45f14ab541c0ad7182eb5218",
    "src/lib/shared/data_provider/raw_dialog_history.py": "465fccff542ec4713c6392a34090586c692adba0",
    "src/lib/shared/data_provider/raw_dialogue.py": "789c18a95fcf1866d95c1b7de4c2fd1962bc8e7b",
    "src/lib/shared/data_provider/raw_question.py": "212affda58c8a1698626d0fdf032ba4ae2a73a8e",
    "src/lib/shared/data_provider/raw_question_group.py": "b0748a5f66fafbc1fc53e7023d94d12013744ebf",
    "src/lib/shared/data_provider/raw_subsequent_topic.py": "4103871e742c734b5319cfe94a59cf3c2cdfe27c",
    "src/lib/shared/data_provider/raw_summary.py": "6cdc4029811b0f90db7e7836678ad12c682b19ac",
    "src/lib/shared/data_provider/raw_observation.py": "145fe67f3ea20c27d876725b103974a27fe16665",
    "src/lib/shared/data_provider/raw_basic_info.py": "101383d8213f9727b796dba97b295c3c9ca19dbe",
    "src/lib/shared/data_provider/raw_event_experience.py": "d096feaf85a1adfed85e97772fd226175ef8a8da",
}

# B28R.6: directory (git tree) sha at PINNED_COMMIT for directories whose
# COMPLETE listing (not a curated selection of blobs) is the evidence for an
# absence claim -- "no officially-shipped no-memory script exists for QA/
# Summarization" needs proof that every file in these two directories was
# enumerated, not just that a few chosen files don't happen to be it.
# Fetched via `gh api repos/slptongji/ES-MemEval/contents/src/exe?ref=<PINNED_COMMIT>`.
AUDITED_SOURCE_TREES: dict[str, str] = {
    "src/exe/qa": "ca5ae553316fd9b1c88a3797c3b7701528b84041",
    "src/exe/sum": "34c7ebffb885b02f59a0c2c9b88d19d20956e827",
}

# Complete file-name listing of the two trees above at PINNED_COMMIT, as
# independent confirmation the tree sha corresponds to what this module
# claims -- none of these 24+10 names suggest a dedicated empty/no-memory
# baseline (all are model x {full, rag[_variant]} combinations).
AUDITED_SOURCE_TREE_LISTINGS: dict[str, tuple[str, ...]] = {
    "src/exe/qa": (
        "qa_gpt35turbo_full.py",
        "qa_gpt35turbo_rag.py",
        "qa_gpt4o_full.py",
        "qa_gpt4o_rag.py",
        "qa_mistral24b_full.py",
        "qa_mistral24b_full_2k.py",
        "qa_mistral24b_full_4k.py",
        "qa_mistral24b_full_8k.py",
        "qa_mistral24b_rag.py",
        "qa_mistral24b_rag_round_10.py",
        "qa_mistral24b_rag_round_15.py",
        "qa_mistral24b_rag_round_5.py",
        "qa_mistral24b_rag_session_2.py",
        "qa_mistral24b_rag_session_8.py",
        "qa_mistral24b_rag_turn_10.py",
        "qa_mistral24b_rag_turn_20.py",
        "qa_mistral24b_rag_turn_30.py",
        "qa_mistral8b_full.py",
        "qa_mistral8b_full_2k.py",
        "qa_mistral8b_full_4k.py",
        "qa_mistral8b_full_8k.py",
        "qa_mistral8b_rag.py",
        "qa_phi3_full.py",
        "qa_phi3_rag.py",
    ),
    "src/exe/sum": (
        "sum_gpt35turbo_full.py",
        "sum_gpt35turbo_rag.py",
        "sum_gpt4o_full.py",
        "sum_gpt4o_rag.py",
        "sum_mistral24b_full.py",
        "sum_mistral24b_rag.py",
        "sum_mistral8b_full.py",
        "sum_mistral8b_rag.py",
        "sum_phi3_full.py",
        "sum_phi3_rag.py",
    ),
}

SURFACE_A_RETRIEVAL_CORPUS = "A_retrieval_corpus"
SURFACE_B_QUERY_STATE_ONLY = "B_query_state_only"
SURFACE_C_GENERATOR_VISIBLE_PROMPT = "C_generator_visible_prompt_context"
SURFACE_D_NOT_SUPPORTER_VISIBLE = "D_not_tested_supporter_visible"
SURFACES = (
    SURFACE_A_RETRIEVAL_CORPUS,
    SURFACE_B_QUERY_STATE_ONLY,
    SURFACE_C_GENERATOR_VISIBLE_PROMPT,
    SURFACE_D_NOT_SUPPORTER_VISIBLE,
)

# B28R.2: surface D sub-categories -- not mutually exclusive with each other.
D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY = "hidden_seeker_simulator_only"
D_SUB_POSTGENERATION_EVALUATOR_ONLY = "postgeneration_evaluator_only"
D_SUB_POSTGENERATION_LOGGING_ONLY = "postgeneration_logging_only"
D_SUB_UNUSED_OFFICIAL_METADATA = "unused_official_metadata"
D_SUB_CATEGORIES = (
    D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY,
    D_SUB_POSTGENERATION_EVALUATOR_ONLY,
    D_SUB_POSTGENERATION_LOGGING_ONLY,
    D_SUB_UNUSED_OFFICIAL_METADATA,
)

TASK_QA = "qa"
TASK_SUMMARIZATION = "summarization"
TASK_DIALOGUE_GENERATION = "dialogue_generation"
TASKS = (TASK_QA, TASK_SUMMARIZATION, TASK_DIALOGUE_GENERATION)

ARM_NO_MEMORY = "no_memory"
ARM_FULL_HISTORY = "full_history"
ARM_OFFICIAL_RAG_TOP4 = "official_rag_top4"
ARMS = (ARM_NO_MEMORY, ARM_FULL_HISTORY, ARM_OFFICIAL_RAG_TOP4)

SURFACE_B_NO_PM_IN_HARNESS_NOTE = (
    "The official ES-MemEval harness itself has no PM/memory-selection "
    "component at all -- surface B names only the officially-visible "
    "current query/turn state (the question text for QA/Summarization; "
    "the live current-round seeker utterance for DG), the raw material a "
    "FUTURE PM would consume. A future PM's actual decision input is "
    "surface-A-selected candidate outcome-blind descriptors (this "
    "project's own eligible-candidate-pool/feature layer) PLUS this "
    "surface-B query-state -- never surface C (what the Generator "
    "happens to receive for a fixed baseline arm) or surface D."
)

CANDIDATE_VS_PROMPT_VISIBILITY_NOTE = (
    "'Candidate comes from history' (surface A) is NOT the same claim as "
    "'candidate text is currently in the Generator's prompt' (surface C) "
    "-- and the two do not reliably coincide even for Full History. For "
    "QA/Summarization Full History, surface C starts as the full surface-A "
    "corpus, but the assembled 'Question + Relevant Memory' string is then "
    "hard-truncated to context_length(16000) minus the system-prompt token "
    "count -- if that budget is exceeded, surface C becomes only a PREFIX "
    "of surface A (source-list-later sessions are cut first), not the "
    "full set; it only coincides with A when the corpus fits under budget. "
    "For QA/Summarization Official RAG Top-4, surface C is normally at "
    "most the top-4 retrieved sessions (a subset of surface A) but is "
    "STILL subject to the same tail truncation, so even that top-4 set is "
    "not guaranteed to be fully present verbatim; and when a seeker has 4 "
    "or fewer total sessions, retrieval returns everything, so C is not "
    "reliably a STRICT (proper) subset of A in every case either. For "
    "Dialogue Generation, A and C do not even share a common mechanism "
    "across arms: Full History has no retrieval-corpus concept at all "
    "(raw message replay via ChatRoomBuilder.fill_session, never "
    "AlwaysAllDocumentStore -- see the DG-specific Full History surface-A "
    "row), while Official RAG Top-4 retrieval is genuinely dynamic and can "
    "return a different top-4 every round (see OFFICIAL_RAG_CONTRACT's DG "
    "query_construction entry). This project's own eligible-candidate-pool "
    "layer (features.zero_outcome_census.build_eligible_pool) is analogous "
    "to surface A only, and must never be read as 'what the Generator "
    "currently sees' (surface C)."
)

MECHANICAL_INVALIDATION_NOTE = (
    "Consistent with AGENTS.md 'Treatment validity': semantic adoption or "
    "non-use of an injected resource is diagnostic only and never grounds "
    "for invalidating a row. Only mechanical delivery/identity/integrity "
    "failures do -- compiler/schema failure, missing or mismatched "
    "assigned resource, wrong owner, future/gold leakage, arm/seed/prompt/"
    "candidate mismatch, terminal empty generation, or an unparseable "
    "official scorer. This is a restatement of an already-adopted project "
    "policy (execution-reconciliation section 4), not a new finding "
    "derived from the ES-MemEval source -- the source code has no opinion "
    "on this project's own invalidation policy."
)

DG_RAG_DOUBLE_BEGINNING_PROMPT_NOTE = (
    "B28R.4: dg_gpt4o_rag.py's room() wires parameters.beginning_prompt "
    "into the conversation TWICE, not once. First, via "
    "FixedStrategy([beginning_prompt], None, []) as the 'before' half of "
    "MixedStrategy -- MixedStrategy.generate_prepend_prompts returns it "
    "fresh on EVERY supporter generation call (prepended alongside "
    "whatever sessions are retrieved that round). Second, via a direct "
    "room.append(parameters.beginning_prompt) into the room's persistent "
    "_history immediately after begin_session() -- this copy is returned "
    "unchanged by the room's default inplace behavior (since "
    "SessionWiseMemoryPrependStrategy.generate_inplace_prompts always "
    "returns None), so it appears once, fixed in place, as part of the "
    "growing conversation transcript itself. The very first supporter "
    "generation call therefore assembles a prompt containing "
    "beginning_prompt twice; the prepended copy keeps reappearing on every "
    "subsequent call while the _history copy stays fixed at its original "
    "position."
)


@dataclass(frozen=True)
class TaskArmSurfaceRow:
    task: str
    arm: str
    arm_officially_shipped_script: bool
    surface: str
    description: str
    source_refs: tuple[str, ...]
    d_sub_categories: tuple[str, ...] = ()

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-official-visibility-task-arm-surface-row-v2",
            "task": self.task,
            "arm": self.arm,
            "arm_officially_shipped_script": self.arm_officially_shipped_script,
            "surface": self.surface,
            "d_sub_categories": list(self.d_sub_categories),
            "description": self.description,
            "source_refs": list(self.source_refs),
        }


@dataclass(frozen=True)
class FieldVisibilityRow:
    """Field-level visibility row -- B28R.1/B28R.2/B28R.7: basic_info and
    every other surface-D-relevant field are recorded individually, not as
    one coarse per-(task, arm) blob, so a field that reaches the tested
    supporter (basic_info.name) is never lumped in with fields that never
    do (age/gender/... , social_relationship, unread evidence/theme/group).
    """

    field_path: str
    applies_to_tasks: tuple[str, ...]
    reaches_tested_supporter_prompt: bool
    reaches_tested_supporter_note: str
    d_sub_categories: tuple[str, ...]
    description: str
    source_refs: tuple[str, ...]

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-official-visibility-field-row-v1",
            "field_path": self.field_path,
            "applies_to_tasks": list(self.applies_to_tasks),
            "reaches_tested_supporter_prompt": self.reaches_tested_supporter_prompt,
            "reaches_tested_supporter_note": self.reaches_tested_supporter_note,
            "d_sub_categories": list(self.d_sub_categories),
            "description": self.description,
            "source_refs": list(self.source_refs),
        }


FIELD_VISIBILITY_TABLE: tuple[FieldVisibilityRow, ...] = (
    FieldVisibilityRow(
        field_path="basic_info.name",
        applies_to_tasks=TASKS,
        reaches_tested_supporter_prompt=True,
        reaches_tested_supporter_note=(
            "QA/Summarization (full_history/official_rag_top4 arms only): "
            "labels 'Human' turns in retrieved/replayed documents as "
            "'{name}: {text}' via ChatRoomBuilder.fill_chat_room's "
            "human_name plus SessionWiseMemoryInplaceStrategy._as_text. "
            "It is still READ (extracted into a local variable) even under "
            "a no_memory-style memory_strategy, since fill_chat_room always "
            "extracts it -- but has no effect there, since NoPromptStrategy."
            "record_session is a no-op that stores nothing. Dialogue "
            "Generation (all 3 arms): embedded directly and unconditionally "
            "in the supporter's own fixed system prompt "
            "('...talking to your seeker {name}.') and in the fixed opening "
            "greeting ('Hi {name}! How are you these days?') -- both "
            "constructed once in DgExperiment.generate_dialogue, "
            "independent of arm."
        ),
        d_sub_categories=(),
        description="Seeker's display name.",
        source_refs=(
            "src/lib/shared/chat_rooms/chat_room_builder.py:ChatRoomBuilder.fill_chat_room",
            "src/lib/shared/prompt_strategies/session_wise_memory_inplace_strategy.py:SessionWiseMemoryInplaceStrategy._as_text",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",
        ),
    ),
    FieldVisibilityRow(
        field_path="basic_info.age|gender|nationality|location|job|education",
        applies_to_tasks=(TASK_DIALOGUE_GENERATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note=(
            "Never referenced anywhere in qa_experiment.py/sum_experiment.py "
            "(only .name is read, via fill_chat_room). For DG, confirmed "
            "absent from the supporter's system prompt/beginning_prompt "
            "construction (only .name appears there)."
        ),
        d_sub_categories=(D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY, D_SUB_POSTGENERATION_EVALUATOR_ONLY),
        description=(
            "The rest of the seeker demographic block. Used in the DG "
            "seeker-simulator's own system prompt, and again in the "
            "observation scorer/usage-judge prompts (postgeneration) -- "
            "never in the tested supporter's prompt."
        ),
        source_refs=(
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_scores._score",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_usages._judge",
        ),
    ),
    FieldVisibilityRow(
        field_path="social_relationship",
        applies_to_tasks=TASKS,
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Never referenced in qa_experiment.py, sum_experiment.py, or dg_experiment.py.",
        d_sub_categories=(D_SUB_UNUSED_OFFICIAL_METADATA,),
        description=(
            "RawSeeker.social_relationship: list[str] -- schema-present, "
            "never read by any of the three audited experiment scripts. "
            "B28R correction: previously mislabeled 'evaluator-only', which "
            "overclaims that some consumer reads it."
        ),
        source_refs=("src/lib/shared/data_provider/raw_seeker.py:RawSeeker",),
    ),
    FieldVisibilityRow(
        field_path="dialog_history[].emotion",
        applies_to_tasks=TASKS,
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Never referenced anywhere in the audited harness code.",
        d_sub_categories=(D_SUB_UNUSED_OFFICIAL_METADATA,),
        description=(
            "Session-level emotion label -- schema-present, confirmed "
            "unread by ChatRoomBuilder, the seeker-simulator prompt "
            "builder, and every scorer. B28R correction: previously "
            "mislabeled 'evaluator-only'."
        ),
        source_refs=("src/lib/shared/data_provider/raw_dialog_history.py:RawDialogHistory",),
    ),
    FieldVisibilityRow(
        field_path="dialog_history[].topic",
        applies_to_tasks=TASKS,
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Never referenced anywhere in the audited harness code.",
        d_sub_categories=(D_SUB_UNUSED_OFFICIAL_METADATA,),
        description=(
            "Session-level topic label (distinct from DG's subsequent_"
            "topics[].topic scenario field) -- schema-present, unread "
            "everywhere. B28R correction: previously mislabeled "
            "'evaluator-only'."
        ),
        source_refs=("src/lib/shared/data_provider/raw_dialog_history.py:RawDialogHistory",),
    ),
    FieldVisibilityRow(
        field_path="dialog_history[].summary",
        applies_to_tasks=(TASK_DIALOGUE_GENERATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note=(
            "QA/Summarization never reference dialog_history summaries at "
            "all (only raw dialogue turns, via ChatRoomBuilder). DG's "
            "supporter never receives it either."
        ),
        d_sub_categories=(D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY, D_SUB_POSTGENERATION_EVALUATOR_ONLY),
        description=(
            "Session-level gold summary -- used in BOTH the DG "
            "seeker-simulator's system prompt ('Summaries of previous "
            "sessions') and the DG observation scorer/usage-judge prompts "
            "(identical heading) -- a real example of the two D "
            "sub-categories not being mutually exclusive for one field."
        ),
        source_refs=(
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_scores._score",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_usages._judge",
        ),
    ),
    FieldVisibilityRow(
        field_path="dialog_history[].observation",
        applies_to_tasks=(TASK_DIALOGUE_GENERATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Read only post-generation by the observation scorer/usage judge.",
        d_sub_categories=(D_SUB_POSTGENERATION_EVALUATOR_ONLY,),
        description="Per-session observation list, scored against each generated seeker turn.",
        source_refs=(
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_scores",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_usages",
        ),
    ),
    FieldVisibilityRow(
        field_path="question.answer",
        applies_to_tasks=(TASK_QA,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Read strictly post-generation.",
        d_sub_categories=(D_SUB_POSTGENERATION_EVALUATOR_ONLY,),
        description="Gold answer -- actually consumed by f1()/QaBertScore.compute()/llm_as_a_judge().",
        source_refs=("src/lib/qa/qa_experiment.py:QaExperiment._run_for_seeker",),
    ),
    FieldVisibilityRow(
        field_path="question.evidence",
        applies_to_tasks=(TASK_QA,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Never referenced anywhere in qa_experiment.py -- schema-present only.",
        d_sub_categories=(D_SUB_UNUSED_OFFICIAL_METADATA,),
        description=(
            "Evidence session-id list -- present in RawQuestion but not "
            "read by the official QA experiment script itself (this "
            "project's own splits/evidence.py is a separate, project-owned "
            "reader of the raw dataset file for fold construction, not the "
            "official harness -- B28R.7: schema presence is not the same "
            "claim as official-harness consumption)."
        ),
        source_refs=(
            "src/lib/shared/data_provider/raw_question.py:RawQuestion",
            "src/lib/qa/qa_experiment.py:QaExperiment._run_for_seeker",
        ),
    ),
    FieldVisibilityRow(
        field_path="question.capability",
        applies_to_tasks=(TASK_QA,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Logged to the results CSV only; never used to construct the prompt or influence scoring.",
        d_sub_categories=(D_SUB_POSTGENERATION_LOGGING_ONLY,),
        description="Task-difficulty/capability tag, CSV-output-only (not a scoring input).",
        source_refs=("src/lib/qa/qa_experiment.py:QaExperiment._run_for_seeker",),
    ),
    FieldVisibilityRow(
        field_path="summary.answer",
        applies_to_tasks=(TASK_SUMMARIZATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Read strictly post-generation.",
        d_sub_categories=(D_SUB_POSTGENERATION_EVALUATOR_ONLY,),
        description="Gold reference summary -- consumed by rouge_scorer.score()/llm_as_a_judge().",
        source_refs=("src/lib/sum/sum_experiment.py:SumExperiment._run_for_seeker",),
    ),
    FieldVisibilityRow(
        field_path="summary.evidence|theme|group",
        applies_to_tasks=(TASK_SUMMARIZATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Never referenced anywhere in sum_experiment.py -- schema-present only.",
        d_sub_categories=(D_SUB_UNUSED_OFFICIAL_METADATA,),
        description=(
            "Evidence session-id list, theme label, and Summary group id "
            "-- all present in RawSummary but none read by the official "
            "Summarization experiment script itself."
        ),
        source_refs=(
            "src/lib/shared/data_provider/raw_summary.py:RawSummary",
            "src/lib/sum/sum_experiment.py:SumExperiment._run_for_seeker",
        ),
    ),
    FieldVisibilityRow(
        field_path="summary.capability",
        applies_to_tasks=(TASK_SUMMARIZATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Logged to the results CSV only.",
        d_sub_categories=(D_SUB_POSTGENERATION_LOGGING_ONLY,),
        description="Task-difficulty/capability tag, CSV-output-only.",
        source_refs=("src/lib/sum/sum_experiment.py:SumExperiment._run_for_seeker",),
    ),
    FieldVisibilityRow(
        field_path="subsequent_topics[].related_sessions",
        applies_to_tasks=(TASK_DIALOGUE_GENERATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Used only as a session-id selector; the id list itself is never printed into any prompt.",
        d_sub_categories=(D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY,),
        description=(
            "Selects which dialog_history sessions populate topic.sessions, "
            "whose raw dialogue text then appears only in the "
            "seeker-simulator's own system prompt."
        ),
        source_refs=("src/lib/dg/dg_experiment.py:DgExperiment._load_topics",),
    ),
    FieldVisibilityRow(
        field_path="subsequent_topics[].topic",
        applies_to_tasks=(TASK_DIALOGUE_GENERATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note=(
            "Appears in both the seeker-simulator's system prompt and the "
            "observation scorer/usage-judge prompts -- never in the "
            "supporter's own prompt."
        ),
        d_sub_categories=(D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY, D_SUB_POSTGENERATION_EVALUATOR_ONLY),
        description=(
            "The scenario topic text -- another field where the two D "
            "sub-categories are not mutually exclusive."
        ),
        source_refs=(
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_scores._score",
            "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_usages._judge",
        ),
    ),
    FieldVisibilityRow(
        field_path="subsequent_topics[].psychological_condition|physical_condition|more_details",
        applies_to_tasks=(TASK_DIALOGUE_GENERATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note=(
            "Confirmed absent from generate_observation_scores/generate_"
            "observation_usages -- unlike .topic, these three are "
            "seeker-simulator-only."
        ),
        d_sub_categories=(D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY,),
        description="Scenario background detail fields.",
        source_refs=("src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",),
    ),
    FieldVisibilityRow(
        field_path="event_experience",
        applies_to_tasks=(TASK_DIALOGUE_GENERATION,),
        reaches_tested_supporter_prompt=False,
        reaches_tested_supporter_note="Used only in the seeker-simulator's system prompt ('Summaries of previous events').",
        d_sub_categories=(D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY,),
        description="Seeker's cross-session event history.",
        source_refs=("src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",),
    ),
)


_QA_SUM_SOURCE_REFS_COMMON = (
    "src/lib/shared/chat_rooms/chat_room_builder.py:ChatRoomBuilder.fill_chat_room",
    "src/lib/shared/chat_rooms/chat_room.py:ChatRoom.begin_session/append/end_session/drop_session/generate_without_append",
)


def _qa_sum_rows(task: str, experiment_file: str) -> tuple[TaskArmSurfaceRow, ...]:
    rows: list[TaskArmSurfaceRow] = []
    tree_path = "src/exe/qa" if task == TASK_QA else "src/exe/sum"

    rows.append(
        TaskArmSurfaceRow(
            task=task,
            arm=ARM_NO_MEMORY,
            arm_officially_shipped_script=False,
            surface=SURFACE_A_RETRIEVAL_CORPUS,
            description=(
                "No officially-shipped no-memory script exists for QA/Summarization "
                "(unlike DG's dg_gpt4o.py) -- confirmed by enumerating the COMPLETE "
                f"{tree_path} directory listing (tree sha {AUDITED_SOURCE_TREES[tree_path]}, "
                f"{len(AUDITED_SOURCE_TREE_LISTINGS[tree_path])} files, all model x "
                "{full, rag[_variant]} combinations, none a dedicated empty/no-memory "
                "baseline), not a curated selection of blobs. Constructing this arm means "
                "using the same harness with an empty/no-op memory_strategy (e.g. "
                "NoPromptStrategy), so the retrieval corpus is empty by construction."
            ),
            source_refs=(f"{experiment_file}:{'Qa' if task == TASK_QA else 'Sum'}ExperimentParameters.memory_strategy",),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=task,
            arm=ARM_FULL_HISTORY,
            arm_officially_shipped_script=True,
            surface=SURFACE_A_RETRIEVAL_CORPUS,
            description=(
                "AlwaysAllDocumentStore: every dialog_history session becomes one "
                "Document (all turns joined 'role: content' per line, Human turns "
                "labeled with basic_info.name -- see FIELD_VISIBILITY_TABLE), added "
                "via record_session when ChatRoomBuilder.fill_chat_room replays the "
                "entire history before the query. _retrieve() returns every stored "
                "Document unconditionally, regardless of query."
            ),
            source_refs=(
                "src/lib/shared/document_stores/always_all_document_store.py:AlwaysAllDocumentStore",
                "src/lib/shared/prompt_strategies/session_wise_memory_inplace_strategy.py:SessionWiseMemoryInplaceStrategy.record_session",
            ),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=task,
            arm=ARM_OFFICIAL_RAG_TOP4,
            arm_officially_shipped_script=True,
            surface=SURFACE_A_RETRIEVAL_CORPUS,
            description=(
                "VectorDocumentStore(4, 'FAISS', BAAI/bge-m3 embeddings): identical "
                "one-Document-per-session indexing as Full History (same basic_info."
                "name Human-turn labeling), but held in a FAISS vector index rather "
                "than a plain list -- see OFFICIAL_RAG_CONTRACT."
            ),
            source_refs=(
                "src/lib/shared/document_stores/vector_document_store.py:VectorDocumentStore",
                "src/lib/shared/embedding_models/embedding_provider.py:EmbeddingProvider.bge_m3",
            ),
        )
    )

    query_field_ref = "question['question']" if task == TASK_QA else "summary['question']"
    for arm, shipped in ((ARM_NO_MEMORY, False), (ARM_FULL_HISTORY, True), (ARM_OFFICIAL_RAG_TOP4, True)):
        rows.append(
            TaskArmSurfaceRow(
                task=task,
                arm=arm,
                arm_officially_shipped_script=shipped,
                surface=SURFACE_B_QUERY_STATE_ONLY,
                description=(
                    f"The officially-asked query text itself ({query_field_ref}) "
                    "and the task type -- nothing else. Each question/summary item is "
                    "answered in its own fresh room.begin_session()/drop_session() "
                    "pair, so no other question in the same seeker's group, and no "
                    "prior generated answer, is part of the query state. "
                    + SURFACE_B_NO_PM_IN_HARNESS_NOTE
                ),
                source_refs=_QA_SUM_SOURCE_REFS_COMMON + (f"{experiment_file}:_generate_answer",),
            )
        )

    rows.append(
        TaskArmSurfaceRow(
            task=task,
            arm=ARM_NO_MEMORY,
            arm_officially_shipped_script=False,
            surface=SURFACE_C_GENERATOR_VISIBLE_PROMPT,
            description=(
                "Fixed system prompt (task instructions) + a single HumanMessage "
                "'Question: {question}' (no 'Relevant Memory' section, since the "
                "memory_strategy contributes no inplace text) -- truncated to "
                "context_length(16000) minus the system-prompt token count if it "
                "somehow still exceeds that (won't, in practice, for a bare question)."
            ),
            source_refs=(f"{experiment_file}:_create_room.inplace_behavior",),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=task,
            arm=ARM_FULL_HISTORY,
            arm_officially_shipped_script=True,
            surface=SURFACE_C_GENERATOR_VISIBLE_PROMPT,
            description=(
                "Same fixed system prompt + one HumanMessage: 'Question: {question}"
                "\\nRelevant Memory:\\n' followed by every session's '[date]\\n{text}' "
                "block, unranked, in raw source-list/store-insertion order -- then "
                "hard-truncated: the whole 'Question + Relevant Memory' string is "
                "tiktoken-encoded (o200k_base) and cut to the first "
                "context_length(16000) - system_prompt_tokens tokens if it exceeds "
                "that, decoded back to text. Truncation can cut mid-document and "
                "always removes the *tail* of the assembled content, i.e. source-list-"
                "later sessions are the ones truncated away first. The official code "
                "does not explicitly sort Full History before this iteration. "
                "B28R.5: surface C therefore only coincides with surface A when the "
                "assembled corpus fits under the token budget -- when it does not, C "
                "is a PREFIX of A, not the full corpus; see "
                "CANDIDATE_VS_PROMPT_VISIBILITY_NOTE."
            ),
            source_refs=(f"{experiment_file}:_create_room.inplace_behavior",),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=task,
            arm=ARM_OFFICIAL_RAG_TOP4,
            arm_officially_shipped_script=True,
            surface=SURFACE_C_GENERATOR_VISIBLE_PROMPT,
            description=(
                "Identical inplace mechanism and the SAME tail truncation as Full "
                "History, except 'Relevant Memory' starts from only the up-to-4 "
                "sessions returned by the BGE-M3/FAISS retriever for this exact "
                "query, each formatted '{rank}. [date]\\n{text}\\n' (1-indexed by "
                "retrieval rank). B28R.5: because the same truncation still applies "
                "afterward, even this top-4 set is not guaranteed to be fully "
                "present verbatim in the final prompt; and when the seeker has <=4 "
                "total sessions, the retrieved set equals the full surface-A corpus, "
                "so C is not reliably a strict subset of A in every case."
            ),
            source_refs=(f"{experiment_file}:_create_room.inplace_behavior",),
        )
    )

    for arm, shipped in ((ARM_NO_MEMORY, False), (ARM_FULL_HISTORY, True), (ARM_OFFICIAL_RAG_TOP4, True)):
        if task == TASK_QA:
            d_desc = (
                "question['answer'] is actually read (F1/BERTScore/LLM-judge, "
                "strictly post-generation). question['capability'] is logged to the "
                "results CSV only, never a scoring input. question['evidence'] is "
                "schema-present in RawQuestion but never referenced anywhere in "
                "qa_experiment.py -- unused_official_metadata, not a consumed "
                "evaluator field. See FIELD_VISIBILITY_TABLE for the exact per-field "
                "breakdown and d_sub_categories."
            )
            sub_cats = (
                D_SUB_POSTGENERATION_EVALUATOR_ONLY,
                D_SUB_POSTGENERATION_LOGGING_ONLY,
                D_SUB_UNUSED_OFFICIAL_METADATA,
            )
        else:
            d_desc = (
                "summary['answer'] is actually read (ROUGE-1/2/L + event-based "
                "LLM-judge, strictly post-generation). summary['capability'] is "
                "logged to the results CSV only. summary['evidence']/summary['theme']/"
                "summary['group'] are all schema-present in RawSummary but never "
                "referenced anywhere in sum_experiment.py -- unused_official_"
                "metadata, not consumed evaluator fields. See FIELD_VISIBILITY_TABLE "
                "for the exact per-field breakdown and d_sub_categories."
            )
            sub_cats = (
                D_SUB_POSTGENERATION_EVALUATOR_ONLY,
                D_SUB_POSTGENERATION_LOGGING_ONLY,
                D_SUB_UNUSED_OFFICIAL_METADATA,
            )
        rows.append(
            TaskArmSurfaceRow(
                task=task,
                arm=arm,
                arm_officially_shipped_script=shipped,
                surface=SURFACE_D_NOT_SUPPORTER_VISIBLE,
                description=d_desc,
                d_sub_categories=sub_cats,
                source_refs=(f"{experiment_file}:_run_for_seeker",),
            )
        )

    return tuple(rows)


def _dg_rows() -> tuple[TaskArmSurfaceRow, ...]:
    rows: list[TaskArmSurfaceRow] = []

    rows.append(
        TaskArmSurfaceRow(
            task=TASK_DIALOGUE_GENERATION,
            arm=ARM_NO_MEMORY,
            arm_officially_shipped_script=True,
            surface=SURFACE_A_RETRIEVAL_CORPUS,
            description=(
                "dg_gpt4o.py's room() builds a NoPromptStrategy() room -- no "
                "document store, no dialog_history injected at all. Unlike QA/"
                "Summarization, this IS an officially-shipped script (not something "
                "this project must construct itself)."
            ),
            source_refs=("src/exe/dg/dg_gpt4o.py:room",),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=TASK_DIALOGUE_GENERATION,
            arm=ARM_FULL_HISTORY,
            arm_officially_shipped_script=True,
            surface=SURFACE_A_RETRIEVAL_CORPUS,
            description=(
                "No DocumentStore/retriever at all -- B28R.5: this is NOT an "
                "AlwaysAllDocumentStore path (that class/mechanism is specific to "
                "QA/Summarization Full History). dg_gpt4o_full.py instead replays "
                "the entire dialog_history as literal chat messages directly into "
                "the supporter room's persistent history via ChatRoomBuilder.fill_"
                "session (raw HumanMessage/AIMessage append, no PromptStrategy/"
                "DocumentStore involved), once, before the live rounds begin. There "
                "is no separate 'corpus' object distinct from the conversation "
                "itself for this arm/task."
            ),
            source_refs=(
                "src/exe/dg/dg_gpt4o_full.py:room",
                "src/lib/shared/chat_rooms/chat_room_builder.py:ChatRoomBuilder.fill_session",
            ),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=TASK_DIALOGUE_GENERATION,
            arm=ARM_OFFICIAL_RAG_TOP4,
            arm_officially_shipped_script=True,
            surface=SURFACE_A_RETRIEVAL_CORPUS,
            description=(
                "VectorDocumentStore(4, 'FAISS', BAAI/bge-m3), same one-Document-"
                "per-session indexing as QA/Summarization RAG (but via "
                "SessionWiseMemoryPrependStrategy, which does NOT label turns with "
                "basic_info.name -- see FIELD_VISIBILITY_TABLE), built once via "
                "ChatRoomBuilder.fill_chat_room before the live 10-round exchange "
                "begins -- but re-*retrieved* dynamically every round (see surface C "
                "and DG_RAG_DOUBLE_BEGINNING_PROMPT_NOTE)."
            ),
            source_refs=("src/exe/dg/dg_gpt4o_rag.py:room",),
        )
    )

    for arm, shipped in ((ARM_NO_MEMORY, True), (ARM_FULL_HISTORY, True), (ARM_OFFICIAL_RAG_TOP4, True)):
        rows.append(
            TaskArmSurfaceRow(
                task=TASK_DIALOGUE_GENERATION,
                arm=arm,
                arm_officially_shipped_script=shipped,
                surface=SURFACE_B_QUERY_STATE_ONLY,
                description=(
                    "At round t: the fixed opening greeting (turn 0, identical across "
                    "all arms), every previously-*generated* seeker/supporter "
                    "utterance from rounds 1..t-1, and the genuinely-generated CURRENT "
                    "seeker utterance for round t (appended to supporter_room "
                    "immediately before the supporter is asked to reply). Task type = "
                    "DG. related_sessions/topic/psychological_condition/physical_"
                    "condition/more_details/basic_info's non-name fields/event_"
                    "experience never reach this surface at any round -- see "
                    "DG_STRUCTURE, FIELD_VISIBILITY_TABLE, and surface D. " + SURFACE_B_NO_PM_IN_HARNESS_NOTE
                ),
                source_refs=("src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",),
            )
        )

    rows.append(
        TaskArmSurfaceRow(
            task=TASK_DIALOGUE_GENERATION,
            arm=ARM_NO_MEMORY,
            arm_officially_shipped_script=True,
            surface=SURFACE_C_GENERATOR_VISIBLE_PROMPT,
            description=(
                "[beginning_prompt(system), 'The following dialogue happens now.'"
                "(system), beginning_prompt(system) again], then the live alternating "
                "HumanMessage(seeker)/AIMessage(supporter) exchange as it is "
                "generated. B28R.3: there is no harness-level INPUT-context "
                "truncation anywhere in this path -- see DG_TOKEN_CONTRACT for the "
                "full, corrected token-budget picture (output IS capped, via "
                "max_tokens=60 on both seeker and supporter)."
            ),
            source_refs=("src/exe/dg/dg_gpt4o.py:room", "src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue"),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=TASK_DIALOGUE_GENERATION,
            arm=ARM_FULL_HISTORY,
            arm_officially_shipped_script=True,
            surface=SURFACE_C_GENERATOR_VISIBLE_PROMPT,
            description=(
                "beginning_prompt, then for every historical session in raw source-list "
                "order (the official code performs no explicit sort here): "
                "SystemMessage('happens on {date}') + that session's real "
                "turns as HumanMessage(seeker)/AIMessage(supporter) -- then "
                "SystemMessage('happens now') + beginning_prompt again, then the live "
                "exchange. Same 'no input-context truncation' finding as No Memory -- "
                "see DG_TOKEN_CONTRACT."
            ),
            source_refs=("src/exe/dg/dg_gpt4o_full.py:room",),
        )
    )
    rows.append(
        TaskArmSurfaceRow(
            task=TASK_DIALOGUE_GENERATION,
            arm=ARM_OFFICIAL_RAG_TOP4,
            arm_officially_shipped_script=True,
            surface=SURFACE_C_GENERATOR_VISIBLE_PROMPT,
            description=(
                "beginning_prompt appears TWICE (see DG_RAG_DOUBLE_BEGINNING_PROMPT_"
                "NOTE), then -- freshly, on EVERY supporter generation call, not "
                "injected once -- up to 4 sessions retrieved by similarity to the "
                "current last message in the live conversation, reconstructed as "
                "real role-tagged System/Human/AI messages (sorted by date, each "
                "preceded by a 'happens on {date}' marker), followed by 'happens "
                "now', then the in-progress live exchange. Genuinely dynamic: the "
                "retrieved set can change every round as the query (the latest "
                "message) changes. Same 'no input-context truncation' finding as the "
                "other two arms -- see DG_TOKEN_CONTRACT."
            ),
            source_refs=(
                "src/exe/dg/dg_gpt4o_rag.py:room",
                "src/lib/shared/prompt_strategies/session_wise_memory_prepend_strategy.py:SessionWiseMemoryPrependStrategy.generate_prepend_prompts",
            ),
        )
    )

    for arm, shipped in ((ARM_NO_MEMORY, True), (ARM_FULL_HISTORY, True), (ARM_OFFICIAL_RAG_TOP4, True)):
        rows.append(
            TaskArmSurfaceRow(
                task=TASK_DIALOGUE_GENERATION,
                arm=arm,
                arm_officially_shipped_script=shipped,
                surface=SURFACE_D_NOT_SUPPORTER_VISIBLE,
                description=(
                    "Everything the seeker-simulator's own system prompt and the "
                    "three DG scorers read but the supporter never does -- see "
                    "FIELD_VISIBILITY_TABLE for the exact field-by-field breakdown "
                    "(basic_info.age/gender/nationality/location/job/education, "
                    "social_relationship [unused], dialog_history[].summary "
                    "[both simulator AND evaluator], dialog_history[].observation "
                    "[evaluator], event_experience [simulator], subsequent_topics[]."
                                "related_sessions/psychological_condition/physical_condition/"
                    "more_details [simulator], subsequent_topics[].topic [both "
                    "simulator AND evaluator]). basic_info.name is the one field in "
                    "this family that DOES reach the supporter -- see the surface-A/C "
                    "rows and FIELD_VISIBILITY_TABLE, not this surface-D row."
                ),
                d_sub_categories=(
                    D_SUB_HIDDEN_SEEKER_SIMULATOR_ONLY,
                    D_SUB_POSTGENERATION_EVALUATOR_ONLY,
                    D_SUB_UNUSED_OFFICIAL_METADATA,
                ),
                source_refs=(
                    "src/lib/dg/dg_experiment.py:DgExperiment._load_topics",
                    "src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",
                    "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_scores",
                    "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_usages",
                    "src/lib/dg/dg_experiment.py:DgExperiment.generate_overall_scores",
                ),
            )
        )

    return tuple(rows)


def build_task_arm_surface_rows() -> tuple[TaskArmSurfaceRow, ...]:
    rows: list[TaskArmSurfaceRow] = []
    rows.extend(_qa_sum_rows(TASK_QA, "src/lib/qa/qa_experiment.py"))
    rows.extend(_qa_sum_rows(TASK_SUMMARIZATION, "src/lib/sum/sum_experiment.py"))
    rows.extend(_dg_rows())
    return tuple(rows)


OFFICIAL_RAG_CONTRACT: dict[str, Any] = {
    "embedding_model": "BAAI/bge-m3",
    "embedding_library": "langchain_huggingface.HuggingFaceEmbeddings",
    "vector_store_backend": "FAISS",
    "top_k": 4,
    "retrieval_granularity": "session (one Document per dialog_history session; alternate round-wise/turn-wise granularities exist in the harness only for the separate qa_retrieval_* sensitivity experiments, not the main QA/Summarization/DG tasks)",
    "query_construction": {
        TASK_QA: "the current question text itself: session_history[-1].text() where session_history == [HumanMessage(question)] for this fresh session",
        TASK_SUMMARIZATION: "identical mechanism as QA, using the current summary-prompt question text",
        TASK_DIALOGUE_GENERATION: "session_history[-1].text() of the LIVE, ONGOING supporter-room conversation at the moment of each supporter generation call -- i.e. the just-appended, genuinely-generated CURRENT seeker utterance for that round; re-evaluated fresh every round, never a static pre-generation query",
    },
    "prompt_placement": {
        TASK_QA: "inplace -- appended into the SAME HumanMessage as the question, under a 'Relevant Memory:' header, each retrieved session formatted '{rank}. [date]\\n{session_text}\\n'",
        TASK_SUMMARIZATION: "identical inplace mechanism as QA",
        TASK_DIALOGUE_GENERATION: "prepend -- retrieved sessions are reconstructed as separate role-tagged SystemMessage/HumanMessage/AIMessage turns inserted before the in-progress conversation history, freshly on every supporter generation call (never injected only once); beginning_prompt itself also appears twice -- see DG_RAG_DOUBLE_BEGINNING_PROMPT_NOTE",
    },
    "truncation_max_token_behavior": {
        TASK_QA: "hard INPUT-context token-level truncation: the assembled 'Question + Relevant Memory' string is tiktoken-encoded (o200k_base) and, if it exceeds context_length(16000) minus the fixed system-prompt's token count, cut to the first N tokens and decoded back -- always removes the tail of the assembled string (source-list/rank-later sessions truncated first); this means surface C is only a PREFIX of the intended memory content when the budget is exceeded, see CANDIDATE_VS_PROMPT_VISIBILITY_NOTE",
        TASK_SUMMARIZATION: "identical truncation mechanism as QA",
        TASK_DIALOGUE_GENERATION: "no harness-level INPUT-context truncation logic found anywhere in dg_experiment.py, dg_gpt4o_rag.py, or dg_gpt4o_full.py -- context grows unbounded across rounds/history replay for all 3 arms; see DG_TOKEN_CONTRACT for the corrected picture, including the OUTPUT max_tokens caps this task does have (seeker/supporter=60, observation scorer/usage judge=30)",
    },
    "source_refs": (
        "src/lib/shared/embedding_models/embedding_provider.py:EmbeddingProvider.bge_m3",
        "src/lib/shared/document_stores/vector_document_store.py:VectorDocumentStore",
        "src/lib/shared/prompt_strategies/session_wise_memory_inplace_strategy.py:SessionWiseMemoryInplaceStrategy",
        "src/lib/shared/prompt_strategies/session_wise_memory_prepend_strategy.py:SessionWiseMemoryPrependStrategy",
        "src/lib/qa/qa_experiment.py:QaExperiment._create_room",
        "src/exe/qa/qa_gpt4o_rag.py:memory",
        "src/exe/dg/dg_gpt4o_rag.py:room",
    ),
}

# B28R.3: replaces the removed "no truncation/max-token logic anywhere"
# claim, which conflated INPUT-context truncation (genuinely absent) with
# OUTPUT generation caps (genuinely present, and distinct per role).
DG_TOKEN_CONTRACT: dict[str, Any] = {
    "harness_level_input_context_truncation": "NONE",
    "harness_level_input_context_truncation_note": (
        "No truncation/max-token logic for the ASSEMBLED INPUT PROMPT exists "
        "anywhere in dg_experiment.py, dg_gpt4o_rag.py, or dg_gpt4o_full.py "
        "-- input context grows unbounded across the 10 rounds for all 3 "
        "arms (Full History/RAG additionally start from an already-large "
        "replayed/retrieved history)."
    ),
    "output_max_tokens": {
        "seeker": 60,
        "supporter": 60,
        "observation_scorer": 30,
        "observation_usage_judge": 30,
        "overall_scorer": None,
    },
    "output_max_tokens_note": (
        "seeker/supporter output is explicitly capped via ChatModelIndicator."
        "create_model(logger, max_tokens=60) in DgExperiment.generate_"
        "dialogue; observation_scorer/observation_usage_judge use max_"
        "tokens=30; overall_scorer's create_model call passes no max_tokens "
        "override. These are OUTPUT generation caps, not input-context "
        "truncation -- see harness_level_input_context_truncation above; "
        "the two must never be conflated."
    ),
    "source_refs": (
        "src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",
        "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_scores",
        "src/lib/dg/dg_experiment.py:DgExperiment.generate_observation_usages",
        "src/lib/dg/dg_experiment.py:DgExperiment.generate_overall_scores",
    ),
}

DG_STRUCTURE: dict[str, Any] = {
    "interaction_rounds": 10,
    "generated_utterances_per_round": 2,
    "total_generated_utterances": 20,
    "fixed_supporter_greeting_count": 1,
    "fixed_supporter_greeting_text_pattern": "Hi {seeker_name}! How are you these days?",
    "fixed_greeting_note": (
        "The greeting is NOT generated -- it is a hardcoded f-string (using "
        "basic_info.name -- see FIELD_VISIBILITY_TABLE) appended to both "
        "seeker_room (as HumanMessage, what the seeker 'hears') and "
        "supporter_room (as AIMessage, what the supporter 'said') before "
        "the 10-round loop starts, and logged as turn 0 in dialogue.csv."
    ),
    "round_loop": "for turn in range(1, 11): generate one seeker utterance, then one supporter utterance -- 10 rounds x 2 utterances = 20 generated utterances, plus the 1 fixed greeting",
    "per_round_supporter_visible_state": (
        "The fixed greeting, every previously-generated seeker/supporter "
        "utterance (rounds 1..t-1), and the just-generated, genuinely-real "
        "CURRENT seeker utterance for round t -- never related_sessions/topic/"
        "psychological_condition/physical_condition/more_details/basic_info's "
        "non-name fields/event_experience, which exist only inside the "
        "seeker-simulator's own hidden system prompt (surface D)."
    ),
    "source_refs": ("src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",),
}


def build_official_visibility_audit_report() -> dict[str, Any]:
    rows = build_task_arm_surface_rows()
    return {
        "protocol": "pm-paper1-official-visibility-audit-report-v2",
        "status": "B28R_ZERO_OUTCOME_STATIC_SOURCE_AUDIT_CORRECTED",
        "outcome_calls": 0,
        "pinned_source": {
            "repository": PINNED_REPOSITORY,
            "tag": PINNED_TAG,
            "commit": PINNED_COMMIT,
            "public_artifact_name": PUBLIC_ARTIFACT_NAME,
            "public_artifact_note": PUBLIC_ARTIFACT_NOTE,
        },
        "audited_source_files": dict(AUDITED_SOURCE_FILES),
        "audited_source_file_count": len(AUDITED_SOURCE_FILES),
        "audited_source_trees": dict(AUDITED_SOURCE_TREES),
        "audited_source_tree_listings": {k: list(v) for k, v in AUDITED_SOURCE_TREE_LISTINGS.items()},
        "surfaces": list(SURFACES),
        "surfaces_non_overlapping_note": (
            "The four surfaces are NOT guaranteed pairwise non-overlapping. "
            "Surface D's own three sub-categories can co-occur on one field "
            "(see FIELD_VISIBILITY_TABLE's dialog_history[].summary and "
            "subsequent_topics[].topic rows). Surface A and surface C are "
            "not guaranteed to coincide or to be in a strict-subset "
            "relationship -- see CANDIDATE_VS_PROMPT_VISIBILITY_NOTE for "
            "the exact conditions."
        ),
        "d_sub_categories": list(D_SUB_CATEGORIES),
        "field_visibility_table": [r.to_manifest_row() for r in FIELD_VISIBILITY_TABLE],
        "surface_b_no_pm_in_harness_note": SURFACE_B_NO_PM_IN_HARNESS_NOTE,
        "candidate_vs_prompt_visibility_note": CANDIDATE_VS_PROMPT_VISIBILITY_NOTE,
        "mechanical_invalidation_note": MECHANICAL_INVALIDATION_NOTE,
        "dg_rag_double_beginning_prompt_note": DG_RAG_DOUBLE_BEGINNING_PROMPT_NOTE,
        "official_rag_contract": OFFICIAL_RAG_CONTRACT,
        "dg_token_contract": DG_TOKEN_CONTRACT,
        "dg_structure": DG_STRUCTURE,
        "task_arm_surface_row_count": len(rows),
        "not_selected_this_round": {
            "memory_top_k": None,
            "memory_token_cap": None,
            "outer_k": None,
            "outer_seed": None,
            "already_visible_heuristic": "NOT_IMPLEMENTED_PENDING_MECHANICAL_DEFINITION (unchanged from B25)",
            "note": (
                "This audit only documents what the official harness does. It "
                "does not select memory top-k/token cap, does not choose an "
                "outer-fold K/seed, does not implement any already-visible "
                "heuristic, and does not promote the B25 lexical Jaccard proxy "
                "to a formal feature. MP/ME compilers are unmodified."
            ),
        },
    }


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def write_official_visibility_manifest(
    rows: tuple[TaskArmSurfaceRow, ...], report: dict[str, Any], out_dir: Path
) -> dict[str, Path]:
    """Write the task x arm x surface manifest (jsonl) and the full audit report (json).

    B28R.6: the returned report dict also carries both artifacts' own
    sha256 (not merely their paths) so a build report can bind to exact
    bytes, not just a filename.
    """

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "es_memeval_public_official_visibility_surface_rows_v1.jsonl"
    rendered_rows = "".join(_canonical(r.to_manifest_row()) + "\n" for r in rows)
    manifest_path.write_text(rendered_rows, encoding="utf-8")

    report_with_hash = dict(report)
    report_with_hash["surface_rows_manifest_filename"] = manifest_path.name
    report_with_hash["surface_rows_manifest_sha256"] = _sha_text(rendered_rows)
    report_with_hash["surface_rows_manifest_count"] = len(rows)
    rendered_report = _canonical(report_with_hash) + "\n"
    report_path = out_dir / "es_memeval_public_official_visibility_audit_v1.json"
    report_path.write_text(rendered_report, encoding="utf-8")

    return {"surface_rows_manifest": manifest_path, "report": report_path}
