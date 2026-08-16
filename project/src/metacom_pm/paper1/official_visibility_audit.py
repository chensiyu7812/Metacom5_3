"""B28: official ES-MemEval RQ2 runtime-visibility / baseline-contract audit.

Zero-outcome, static source-code audit -- not computed from ``evo_emo.json``
or the sanitized runtime artifact at all. This module is a hand-encoded,
mechanically-verified record of exactly what the pinned official ES-MemEval
harness (repository ``slptongji/ES-MemEval``, tag ``v1.0.0``, commit
``692624208acc077b8867698c1d6fcd998dee641a``) actually does, read directly
from that commit's source via the GitHub API before writing anything here
(every claim below cites the specific file(s)/function(s) it came from; see
``AUDITED_SOURCE_FILES`` for the exact blob sha of every file read).

The public artifact this project uses is ``ES-MemEval-Public-v1.0.0-1427``
-- the pinned public release, not a row-exact reproduction of the paper's
1209-QA figure (``PAPER_QA_COUNT``/``PUBLIC_QA_COUNT`` in
``metacom_pm.paper1.data.materializer``); this module never conflates the
two.

Four non-overlapping surfaces, per (task, arm):

- **A -- retrieval corpus**: which strict-past session/document a
  Retriever *could* index. Being indexable does NOT mean the text is
  currently in the Generator's prompt -- see ``CANDIDATE_VS_PROMPT_VISIBILITY_NOTE``.
- **B -- PM-visible decision state**: what a PM deciding a memory-injection
  action could see at decision time (current query/turn, task type, and for
  DG, prior *generated* turns only).
- **C -- Generator-visible prompt/context**: what actually ends up inside
  the frozen Generator's final prompt for this arm.
- **D -- evaluator-only**: fields only the scorer/evaluator/seeker-simulator
  ever reads -- answer, evidence, reference summary/theme/group,
  observation, related_sessions, DG background (topic/psychological_
  condition/physical_condition/more_details), basic_info, event_experience,
  social_relationship, and the never-read session-level emotion/topic
  labels (confirmed absent from every code path, not just the tested
  system's).

This module never runs generation, never calls a scorer, never invokes
BGE-M3 or any embedding model, and never reads ``evo_emo.json`` -- it is a
pure, hardcoded documentation-and-schema artifact, checked by tests for
internal consistency (e.g. that no D-surface field name leaks into an A/B/C
entry).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
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

SURFACE_A_RETRIEVAL_CORPUS = "A_retrieval_corpus"
SURFACE_B_PM_VISIBLE_DECISION_STATE = "B_pm_visible_decision_state"
SURFACE_C_GENERATOR_VISIBLE_PROMPT = "C_generator_visible_prompt_context"
SURFACE_D_EVALUATOR_ONLY = "D_evaluator_only"
SURFACES = (
    SURFACE_A_RETRIEVAL_CORPUS,
    SURFACE_B_PM_VISIBLE_DECISION_STATE,
    SURFACE_C_GENERATOR_VISIBLE_PROMPT,
    SURFACE_D_EVALUATOR_ONLY,
)

TASK_QA = "qa"
TASK_SUMMARIZATION = "summarization"
TASK_DIALOGUE_GENERATION = "dialogue_generation"
TASKS = (TASK_QA, TASK_SUMMARIZATION, TASK_DIALOGUE_GENERATION)

ARM_NO_MEMORY = "no_memory"
ARM_FULL_HISTORY = "full_history"
ARM_OFFICIAL_RAG_TOP4 = "official_rag_top4"
ARMS = (ARM_NO_MEMORY, ARM_FULL_HISTORY, ARM_OFFICIAL_RAG_TOP4)

# Fields confirmed, by direct source reading, to be read ONLY by the
# evaluator/scorer or the DG seeker-simulator's hidden system prompt --
# never by anything that builds the tested system's (the "Generator" /
# supporter's) own prompt. RawDialogHistory's session-level "emotion"/
# "topic" labels are included even though no code path (evaluator or
# tested-system) reads them at all in this harness -- confirmed absent from
# ChatRoomBuilder, the seeker-simulator prompt builder, and every scorer.
EVALUATOR_ONLY_FIELDS = frozenset(
    {
        "answer",
        "evidence",
        "theme",
        "group",
        "summary",
        "observation",
        "capability",
        "related_sessions",
        "topic",
        "psychological_condition",
        "physical_condition",
        "more_details",
        "basic_info",
        "event_experience",
        "social_relationship",
        "emotion",
    }
)

CANDIDATE_VS_PROMPT_VISIBILITY_NOTE = (
    "'Candidate comes from history' (surface A, retrieval-corpus "
    "membership) is NOT the same claim as 'candidate text is currently in "
    "the Generator's prompt' (surface C). For Full History, surface A and "
    "surface C coincide (AlwaysAllDocumentStore returns every indexed "
    "session unconditionally, and SessionWiseMemoryInplaceStrategy/"
    "-PrependStrategy inserts all of it). For Official RAG Top-4, surface "
    "C is a strict subset of surface A: only the top-4 sessions by BGE-M3 "
    "similarity to the current query are ever in the prompt for a given "
    "call, and for DG this subset can change every round as the live "
    "query changes. This project's own eligible-candidate-pool layer "
    "(metacom_pm.paper1.features.zero_outcome_census.build_eligible_pool) "
    "is analogous to surface A, not surface C -- it must never be read as "
    "'what the Generator currently sees.'"
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


@dataclass(frozen=True)
class TaskArmSurfaceRow:
    task: str
    arm: str
    arm_officially_shipped_script: bool
    surface: str
    description: str
    source_refs: tuple[str, ...]

    def to_manifest_row(self) -> dict[str, Any]:
        return {
            "protocol": "pm-paper1-official-visibility-task-arm-surface-row-v1",
            "task": self.task,
            "arm": self.arm,
            "arm_officially_shipped_script": self.arm_officially_shipped_script,
            "surface": self.surface,
            "description": self.description,
            "source_refs": list(self.source_refs),
        }


_QA_SUM_SOURCE_REFS_COMMON = (
    "src/lib/shared/chat_rooms/chat_room_builder.py:ChatRoomBuilder.fill_chat_room",
    "src/lib/shared/chat_rooms/chat_room.py:ChatRoom.begin_session/append/end_session/drop_session/generate_without_append",
)


def _qa_sum_rows(task: str, experiment_file: str) -> tuple[TaskArmSurfaceRow, ...]:
    rows: list[TaskArmSurfaceRow] = []

    rows.append(
        TaskArmSurfaceRow(
            task=task,
            arm=ARM_NO_MEMORY,
            arm_officially_shipped_script=False,
            surface=SURFACE_A_RETRIEVAL_CORPUS,
            description=(
                "No officially-shipped no-memory script exists for QA/Summarization "
                "(unlike DG's dg_gpt4o.py) -- constructing this arm means using the "
                "same harness with an empty/no-op memory_strategy (e.g. NoPromptStrategy), "
                "so the retrieval corpus is empty by construction, not because the "
                "harness ships a dedicated empty-store class for this task."
            ),
            source_refs=(f"{experiment_file}:QaExperimentParameters.memory_strategy" if task == TASK_QA else f"{experiment_file}:SumExperimentParameters.memory_strategy",),
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
                "Document (all turns joined 'role: content' per line), added via "
                "record_session when ChatRoomBuilder.fill_chat_room replays the "
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
                "one-Document-per-session indexing as Full History, but held in a "
                "FAISS vector index rather than a plain list -- see OFFICIAL_RAG_CONTRACT."
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
                surface=SURFACE_B_PM_VISIBLE_DECISION_STATE,
                description=(
                    f"The officially-asked query text itself ({query_field_ref}) "
                    "and the task type -- nothing else. Each question/summary item is "
                    "answered in its own fresh room.begin_session()/drop_session() "
                    "pair, so no other question in the same seeker's group, and no "
                    "prior generated answer, is part of the decision state."
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
                "block, unranked, in store-insertion (chronological) order -- then "
                "hard-truncated: the whole 'Question + Relevant Memory' string is "
                "tiktoken-encoded (o200k_base) and cut to the first "
                "context_length(16000) - system_prompt_tokens tokens if it exceeds "
                "that, decoded back to text. Truncation can cut mid-document and "
                "always removes the *tail* of the assembled content, i.e. later "
                "(chronologically-later) sessions are the ones truncated away first."
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
                "Identical inplace mechanism and truncation as Full History, except "
                "'Relevant Memory' contains only the up-to-4 sessions returned by "
                "the BGE-M3/FAISS retriever for this exact query, each formatted "
                "'{rank}. [date]\\n{text}\\n' (1-indexed by retrieval rank)."
            ),
            source_refs=(f"{experiment_file}:_create_room.inplace_behavior",),
        )
    )

    for arm, shipped in ((ARM_NO_MEMORY, False), (ARM_FULL_HISTORY, True), (ARM_OFFICIAL_RAG_TOP4, True)):
        rows.append(
            TaskArmSurfaceRow(
                task=task,
                arm=arm,
                arm_officially_shipped_script=shipped,
                surface=SURFACE_D_EVALUATOR_ONLY,
                description=(
                    ("question['answer']/question['evidence']/question['capability']" if task == TASK_QA
                     else "summary['answer']/summary['evidence']/summary['theme']/summary['group']/summary['capability']")
                    + " -- gold reference, evidence session-ids, and a task-difficulty "
                    "tag logged to the results CSV only, never passed into the room or "
                    "the prompt. Scoring (F1/BERTScore/LLM-judge for QA; ROUGE-1/2/L + "
                    "event-based LLM-judge for Summarization) reads these plus the "
                    "generated answer, strictly post-generation."
                ),
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
                "No DocumentStore/retriever at all -- dg_gpt4o_full.py replays the "
                "entire dialog_history as literal chat messages directly into the "
                "supporter room's persistent history, once, before the live rounds "
                "begin. There is no separate 'corpus' object distinct from the "
                "conversation itself for this arm."
            ),
            source_refs=("src/exe/dg/dg_gpt4o_full.py:room",),
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
                "per-session indexing as QA/Summarization RAG, built once via "
                "ChatRoomBuilder.fill_chat_room before the live 10-round exchange "
                "begins -- but re-*retrieved* dynamically every round (see surface C)."
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
                surface=SURFACE_B_PM_VISIBLE_DECISION_STATE,
                description=(
                    "At round t: the fixed opening greeting (turn 0, identical across "
                    "all arms), every previously-*generated* seeker/supporter "
                    "utterance from rounds 1..t-1, and the genuinely-generated CURRENT "
                    "seeker utterance for round t (appended to supporter_room "
                    "immediately before the supporter is asked to reply). Task type = "
                    "DG. related_sessions/topic/psychological_condition/physical_"
                    "condition/more_details/basic_info/event_experience never reach "
                    "this surface at any round -- see DG_STRUCTURE and surface D."
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
                "generated. No truncation/max-token logic exists anywhere in this "
                "path -- context grows unbounded across the 10 rounds (a difference "
                "from QA/Summarization's explicit tiktoken truncation)."
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
                "beginning_prompt, then for every historical session in chronological "
                "order: SystemMessage('happens on {date}') + that session's real "
                "turns as HumanMessage(seeker)/AIMessage(supporter) -- then "
                "SystemMessage('happens now') + beginning_prompt again, then the live "
                "exchange. Same 'no truncation logic found' caveat as No Memory."
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
                "beginning_prompt (once), then -- freshly, on EVERY supporter "
                "generation call, not injected once -- up to 4 sessions retrieved by "
                "similarity to the current last message in the live conversation, "
                "reconstructed as real role-tagged System/Human/AI messages (sorted "
                "by date, each preceded by a 'happens on {date}' marker), followed by "
                "'happens now', then the in-progress live exchange. Genuinely dynamic: "
                "the retrieved set can change every round as the query (the latest "
                "message) changes. No truncation/max-token logic found here either."
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
                surface=SURFACE_D_EVALUATOR_ONLY,
                description=(
                    "The entire seeker-simulator system prompt: basic_info, "
                    "dialog_history session-level 'summary' fields (never raw "
                    "dialogue, never emotion/topic labels), event_experience, "
                    "related_sessions' raw dialogue text (used only to brief the "
                    "SEEKER simulator, never given to the supporter), and the "
                    "subsequent_topic's topic/psychological_condition/physical_"
                    "condition/more_details. Also session['observation'] (used only "
                    "by generate_observation_scores/generate_observation_usages) and "
                    "the three LLM-judge scoring prompts (overall memory/"
                    "personalization/emotional-support score, observation relevance "
                    "score, observation-usage judgement) -- all strictly "
                    "post-generation, none ever reach the supporter_room."
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
        TASK_DIALOGUE_GENERATION: "prepend -- retrieved sessions are reconstructed as separate role-tagged SystemMessage/HumanMessage/AIMessage turns inserted before the in-progress conversation history, freshly on every supporter generation call (never injected only once)",
    },
    "truncation_max_token_behavior": {
        TASK_QA: "hard token-level truncation: the assembled 'Question + Relevant Memory' string is tiktoken-encoded (o200k_base) and, if it exceeds context_length(16000) minus the fixed system-prompt's token count, cut to the first N tokens and decoded back -- always removes the tail of the assembled string (chronologically/rank-later sessions truncated first)",
        TASK_SUMMARIZATION: "identical truncation mechanism as QA",
        TASK_DIALOGUE_GENERATION: "no equivalent truncation/max-token logic found anywhere in dg_experiment.py, dg_gpt4o_rag.py, or dg_gpt4o_full.py -- a confirmed asymmetry with QA/Summarization worth flagging for M2 design, not resolved by this audit",
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

DG_STRUCTURE: dict[str, Any] = {
    "interaction_rounds": 10,
    "generated_utterances_per_round": 2,
    "total_generated_utterances": 20,
    "fixed_supporter_greeting_count": 1,
    "fixed_supporter_greeting_text_pattern": "Hi {seeker_name}! How are you these days?",
    "fixed_greeting_note": (
        "The greeting is NOT generated -- it is a hardcoded f-string appended "
        "to both seeker_room (as HumanMessage, what the seeker 'hears') and "
        "supporter_room (as AIMessage, what the supporter 'said') before the "
        "10-round loop starts, and logged as turn 0 in dialogue.csv."
    ),
    "round_loop": "for turn in range(1, 11): generate one seeker utterance, then one supporter utterance -- 10 rounds x 2 utterances = 20 generated utterances, plus the 1 fixed greeting",
    "per_round_supporter_visible_state": (
        "The fixed greeting, every previously-generated seeker/supporter "
        "utterance (rounds 1..t-1), and the just-generated, genuinely-real "
        "CURRENT seeker utterance for round t -- never related_sessions/topic/"
        "psychological_condition/physical_condition/more_details/basic_info/"
        "event_experience, which exist only inside the seeker-simulator's own "
        "hidden system prompt (surface D)."
    ),
    "source_refs": ("src/lib/dg/dg_experiment.py:DgExperiment.generate_dialogue",),
}


def build_official_visibility_audit_report() -> dict[str, Any]:
    rows = build_task_arm_surface_rows()
    return {
        "protocol": "pm-paper1-official-visibility-audit-report-v1",
        "status": "B28_ZERO_OUTCOME_STATIC_SOURCE_AUDIT",
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
        "surfaces": list(SURFACES),
        "evaluator_only_fields": sorted(EVALUATOR_ONLY_FIELDS),
        "candidate_vs_prompt_visibility_note": CANDIDATE_VS_PROMPT_VISIBILITY_NOTE,
        "mechanical_invalidation_note": MECHANICAL_INVALIDATION_NOTE,
        "official_rag_contract": OFFICIAL_RAG_CONTRACT,
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
    """Write the task x arm x surface manifest (jsonl) and the full audit report (json)."""

    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "es_memeval_public_official_visibility_surface_rows_v1.jsonl"
    rendered_rows = "".join(_canonical(r.to_manifest_row()) + "\n" for r in rows)
    manifest_path.write_text(rendered_rows, encoding="utf-8")

    report_with_hash = dict(report)
    report_with_hash["surface_rows_manifest_filename"] = manifest_path.name
    report_with_hash["surface_rows_manifest_sha256"] = _sha_text(rendered_rows)
    report_with_hash["surface_rows_manifest_count"] = len(rows)
    report_path = out_dir / "es_memeval_public_official_visibility_audit_v1.json"
    report_path.write_text(_canonical(report_with_hash) + "\n", encoding="utf-8")

    return {"surface_rows_manifest": manifest_path, "report": report_path}
