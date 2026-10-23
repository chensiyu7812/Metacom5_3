"""Official-aligned RQ2 Generator request-message construction.

The official ES-MemEval task prompts and message placement are reproduced at
the pinned v1.0.0 commit.  Typed Paper-1 resource blocks replace the official
retriever's memory string, but the task request and evaluation protocol are
not redefined.  This module emits provider-facing chat messages; a hosted NIM
service's internal serialization template is outside client control and must
not be claimed as locally hash-frozen.
"""

from __future__ import annotations

from typing import Literal

from pydantic import Field, model_validator

from metacom_pm.io import canonical_json, sha256_text

from ..contracts import Head, StrictContract, TaskType, TreatmentAssignment
from .step2 import Step2ResourceEnvelope

RQ2_PROMPT_PROTOCOL = "pm-paper1-official-aligned-rq2-generator-messages-v2"
ES_MEMEVAL_COMMIT = "692624208acc077b8867698c1d6fcd998dee641a"
CANONICAL_MEMORY_HEAD_ORDER = (Head.MP, Head.ME, Head.MS)
LOCAL_GENERATOR_SERVER_PROTOCOL = (
    "paper1-local-llama31-transformers-aiohttp-reference-server-v1"
)
LOCAL_GENERATOR_MODEL_REVISION = "d10aef7999a2b5ba950ab3974312feeedbfe0b77"
LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256 = (
    "61ca4a878558de3dad5ce518ba4ec6619b7848babc6450ca90290087366df1a3"
)
LOCAL_GENERATOR_TOKENIZER_CONFIG_SHA256 = (
    "24e8a6dc2547164b7002e3125f10b415105644fcf02bf9ad8b674c87b1eaaed6"
)
LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256 = (
    "b48c47f6443892716176eb200bf4ef108f64e06ca26ed0fa8ebc0a4b3992fcb2"
)

QA_SYSTEM_PROMPT = """## Task Description
You are given a user question and a set of retrieved memory fragments.
Your task is to filter and summarize the relevant information from the memory fragments and generate a concise, accurate answer to the user's question based on the most pertinent details.
You may need to evaluate the relevance and accuracy of each memory fragment, and if needed, disregard irrelevant or incorrect information.
If the question cannot be answered with the available information, return "unknown."

## Input Format
Question: What did Sarah experience on her birthday in 2024?
Relevant Memory:\x20
1. [2024-08-15] Sarah spent her birthday with her family at a beach resort.
2. [2024-08-15] Sarah was surprised with a birthday cake from her friends.
3. [2024-08-14] Sarah was stressed at work before her birthday, dealing with tight deadlines.
4. [2024-08-15] Sarah enjoyed a quiet dinner with close friends on her birthday evening.

## Output Format
Answer: On her birthday in 2024, Sarah celebrated with family at a beach resort and was surprised with a birthday cake from her friends."""

SUMMARY_SYSTEM_PROMPT = """## Task Description
You are given a user question and a set of retrieved memory fragments\x20
(from long-term emotional support dialogues).\x20
Your task is to generate a concise, accurate summary answer to the question,\x20
integrating all relevant information across the fragments.

## Instructions
- Carefully read all memory fragments.\x20\x20
- Identify which fragments are relevant to answering the question.\x20\x20
- Summarize across multiple fragments, integrating events, emotions, and causal links.\x20\x20
- Ensure the answer is coherent, factually grounded, and free of hallucinations.\x20\x20
- If multiple fragments describe related events, merge them into a single concise narrative.\x20\x20
- If the question cannot be answered from the available fragments, return `"unknown"`.\x20\x20
- Keep the answer short and focused (3–5 sentences).\x20\x20

## Input Format
Question: How did Nick cope with academic challenges over time?\x20\x20
Relevant Memory:\x20\x20
1. [2024-11-15] Nick lost interest in physics due to poor teaching quality.\x20\x20
2. [2025-01-20] Nick started skipping classes and failing his courses.\x20\x20
3. [2025-05-30] Nick was overwhelmed by assignments and considered dropping a course.\x20\x20
4. [2025-07-05] Nick decided to switch majors after guidance from his professor.\x20\x20
5. [2025-09-12] Nick’s workload became more manageable after adjusting to his new major.\x20\x20

## Output Format
Answer: Nick initially lost interest in physics due to poor teaching and began skipping classes, which led to academic failures. By mid-2025, he was overwhelmed by assignments and considered dropping a course. After receiving guidance from his professor, he switched majors, which helped him manage his workload more effectively and regain academic stability."""

DG_SUPPORTER_SYSTEM_PROMPT_TEMPLATE = """In emotional support conversations, there are typically two roles: a supporter and a seeker. You are a professional AI supporter talking to your seeker {display_name}.

However, this isn't a real conversation; it's a test of your memory. You'll need to utilize the previous dialogues to generate responses, demonstrating that you truly remember the previous events, even if it may be less relevant to the current conversation.
For example, when a seeker brings up a topic, you can say, "Oh, you mentioned this before, and you said..." The seeker you're talking to is also asked to elicit your memory as much as possible.
However, if you don't have a memory, don't make it up. Faulty memories can lower your score.

Additionally, your output is limited to 60 tokens, so don't try to say anything too long."""


def dg_supporter_system_prompt(display_name: str) -> str:
    if not display_name.strip() or "\n" in display_name or "\r" in display_name:
        raise ValueError("DG display_name must be a nonempty single line")
    return DG_SUPPORTER_SYSTEM_PROMPT_TEMPLATE.format(display_name=display_name)


class GeneratorMessage(StrictContract):
    role: Literal["system", "user", "assistant"]
    content: str = Field(min_length=1)


class Rq2GeneratorRequest(StrictContract):
    protocol: str = RQ2_PROMPT_PROTOCOL
    task_type: TaskType
    prompt_template_id: str
    provider: Literal["local A6000 Transformers reference server"] = (
        "local A6000 Transformers reference server"
    )
    model: Literal["meta/llama-3.1-8b-instruct"] = "meta/llama-3.1-8b-instruct"
    model_revision: Literal[LOCAL_GENERATOR_MODEL_REVISION] = LOCAL_GENERATOR_MODEL_REVISION
    model_artifact_identity_sha256: Literal[LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256] = (
        LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256
    )
    serving_protocol: Literal[LOCAL_GENERATOR_SERVER_PROTOCOL] = LOCAL_GENERATOR_SERVER_PROTOCOL
    tokenizer_config_sha256: Literal[LOCAL_GENERATOR_TOKENIZER_CONFIG_SHA256] = (
        LOCAL_GENERATOR_TOKENIZER_CONFIG_SHA256
    )
    chat_template_sha256: Literal[LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256] = (
        LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256
    )
    temperature: Literal[0] = 0
    max_output_tokens: int
    messages: tuple[GeneratorMessage, ...] = Field(min_length=2)
    resource_heads: tuple[Head, ...] = ()
    resource_sha256s: tuple[str, ...] = ()
    provider_internal_chat_template_hash_available: Literal[True] = True
    request_messages_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    hidden_seeker_simulator_fields_present: Literal[False] = False

    @model_validator(mode="after")
    def validate_request(self) -> "Rq2GeneratorRequest":
        if self.protocol != RQ2_PROMPT_PROTOCOL:
            raise ValueError("RQ2 prompt protocol mismatch")
        if self.resource_heads != tuple(
            sorted(
                self.resource_heads,
                key=CANONICAL_MEMORY_HEAD_ORDER.index,
            )
        ):
            raise ValueError("resource heads must use canonical MP,ME,MS order")
        if len(self.resource_heads) != len(set(self.resource_heads)):
            raise ValueError("a request cannot repeat a resource head")
        if len(self.resource_heads) != len(self.resource_sha256s):
            raise ValueError("resource head/hash counts do not match")
        identity = canonical_json(
            [message.model_dump(mode="json") for message in self.messages]
        )
        if sha256_text(identity) != self.request_messages_hash:
            raise ValueError("request_messages_hash does not match exact role/content messages")
        if self.task_type in {TaskType.QA, TaskType.SUMMARY}:
            if self.max_output_tokens != 256 or len(self.messages) != 2:
                raise ValueError("QA/Summary request shape or output limit drifted")
        elif self.task_type is TaskType.DIALOGUE_GENERATION:
            if self.max_output_tokens != 60:
                raise ValueError("official DG supporter output limit is 60 tokens")
            if self.messages[-1].role != "user":
                raise ValueError("DG supporter request must end at the current seeker turn")
        else:
            raise ValueError("RQ2 prompt builder does not accept ESC response tasks")
        return self


def _ordered_resources(
    resources: tuple[Step2ResourceEnvelope, ...],
) -> tuple[Step2ResourceEnvelope, ...]:
    if any(resource.assignment is not TreatmentAssignment.ON for resource in resources):
        raise ValueError("only assigned ON resources belong in a Generator request")
    if any(resource.resource_block is None for resource in resources):
        raise ValueError("an ON resource envelope is missing its resource block")
    heads = [resource.head for resource in resources]
    if any(head is Head.RS for head in heads):
        raise ValueError("RQ2 prompt accepts MP/ME/MS resources only")
    if len(heads) != len(set(heads)):
        raise ValueError("RQ2 prompt cannot repeat a memory head")
    return tuple(sorted(resources, key=lambda resource: CANONICAL_MEMORY_HEAD_ORDER.index(resource.head)))


def _request(
    *,
    task_type: TaskType,
    prompt_template_id: str,
    max_output_tokens: int,
    messages: tuple[GeneratorMessage, ...],
    resources: tuple[Step2ResourceEnvelope, ...],
) -> Rq2GeneratorRequest:
    ordered = _ordered_resources(resources)
    resource_blocks = tuple(resource.resource_block for resource in ordered)
    assert all(block is not None for block in resource_blocks)
    return Rq2GeneratorRequest(
        task_type=task_type,
        prompt_template_id=prompt_template_id,
        max_output_tokens=max_output_tokens,
        messages=messages,
        resource_heads=tuple(resource.head for resource in ordered),
        resource_sha256s=tuple(block.resource_sha256 for block in resource_blocks if block),
        request_messages_hash=sha256_text(
            canonical_json([message.model_dump(mode="json") for message in messages])
        ),
    )


def build_static_rq2_request(
    *,
    task_type: TaskType,
    question: str,
    resources: tuple[Step2ResourceEnvelope, ...] = (),
) -> Rq2GeneratorRequest:
    if task_type not in {TaskType.QA, TaskType.SUMMARY}:
        raise ValueError("static RQ2 request is QA or Summary only")
    if not question.strip():
        raise ValueError("question must be nonempty")
    ordered = _ordered_resources(resources)
    human = f"Question: {question}"
    if ordered:
        human += "\nRelevant Memory:\n" + "\n".join(
            resource.rendered_resource_block for resource in ordered
        )
    system = QA_SYSTEM_PROMPT if task_type is TaskType.QA else SUMMARY_SYSTEM_PROMPT
    template = (
        "paper1-es-memeval-qa-official-relevant-memory-v1"
        if task_type is TaskType.QA
        else "paper1-es-memeval-summary-official-relevant-memory-v1"
    )
    return _request(
        task_type=task_type,
        prompt_template_id=template,
        max_output_tokens=256,
        messages=(
            GeneratorMessage(role="system", content=system),
            GeneratorMessage(role="user", content=human),
        ),
        resources=ordered,
    )


def build_dg_supporter_request(
    *,
    display_name: str,
    current_dialogue: tuple[GeneratorMessage, ...],
    resources: tuple[Step2ResourceEnvelope, ...] = (),
) -> Rq2GeneratorRequest:
    if not current_dialogue or current_dialogue[-1].role != "user":
        raise ValueError("DG current dialogue must end with the current seeker/user turn")
    if any(message.role == "system" for message in current_dialogue):
        raise ValueError("DG current dialogue may contain only supporter/seeker messages")
    ordered = _ordered_resources(resources)
    messages: list[GeneratorMessage] = [
        GeneratorMessage(role="system", content=dg_supporter_system_prompt(display_name))
    ]
    messages.extend(
        GeneratorMessage(role="system", content=resource.rendered_resource_block)
        for resource in ordered
    )
    messages.append(
        GeneratorMessage(role="system", content="The following dialogue happens now.")
    )
    messages.extend(current_dialogue)
    return _request(
        task_type=TaskType.DIALOGUE_GENERATION,
        prompt_template_id="paper1-es-memeval-dg-official-supporter-typed-memory-v1",
        max_output_tokens=60,
        messages=tuple(messages),
        resources=ordered,
    )


__all__ = [
    "CANONICAL_MEMORY_HEAD_ORDER",
    "ES_MEMEVAL_COMMIT",
    "DG_SUPPORTER_SYSTEM_PROMPT_TEMPLATE",
    "GeneratorMessage",
    "QA_SYSTEM_PROMPT",
    "RQ2_PROMPT_PROTOCOL",
    "Rq2GeneratorRequest",
    "SUMMARY_SYSTEM_PROMPT",
    "build_dg_supporter_request",
    "build_static_rq2_request",
    "dg_supporter_system_prompt",
]
