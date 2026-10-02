"""Frozen RQ1 supporter messages for RS ON/OFF counterfactuals.

ESC-Eval's tested supporter uses the literal system prompt ``You are a
helpful assistant!`` and a 256-token greedy generation cap.  Paper-1 keeps
that surface and, for RS=ON only, inserts exactly one typed Step2 RS resource
message before the same visible conversation prefix.  No target supporter
response, role card, evaluator score, or future turn is available here.
"""

from __future__ import annotations

from pydantic import Field, model_validator

from metacom_pm.io import canonical_json, sha256_text

from ..contracts import Head, StrictContract, TaskType, TreatmentAssignment
from .rq2_prompts import (
    GeneratorMessage,
    LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256,
    LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256,
    LOCAL_GENERATOR_MODEL_REVISION,
    LOCAL_GENERATOR_SERVER_PROTOCOL,
    LOCAL_GENERATOR_TOKENIZER_CONFIG_SHA256,
)
from .step2 import Step2ResourceEnvelope

RQ1_PROMPT_PROTOCOL = "pm-paper1-esc-eval-supporter-rs-messages-v1"
ESC_SUPPORTER_SYSTEM_PROMPT = "You are a helpful assistant!"


class Rq1GeneratorRequest(StrictContract):
    protocol: str = RQ1_PROMPT_PROTOCOL
    task_type: TaskType = TaskType.ESC_RESPONSE
    prompt_template_id: str = "paper1-esc-eval-supporter-rs-v1"
    provider: str = "local A6000 Transformers reference server"
    model: str = "meta/llama-3.1-8b-instruct"
    model_revision: str = LOCAL_GENERATOR_MODEL_REVISION
    model_artifact_identity_sha256: str = LOCAL_GENERATOR_ARTIFACT_IDENTITY_SHA256
    serving_protocol: str = LOCAL_GENERATOR_SERVER_PROTOCOL
    tokenizer_config_sha256: str = LOCAL_GENERATOR_TOKENIZER_CONFIG_SHA256
    chat_template_sha256: str = LOCAL_GENERATOR_CHAT_TEMPLATE_SHA256
    temperature: int = 0
    max_output_tokens: int = 256
    messages: tuple[GeneratorMessage, ...] = Field(min_length=2)
    resource_sha256: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$")
    request_messages_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    privileged_fields_present: bool = False

    @model_validator(mode="after")
    def validate_request(self) -> "Rq1GeneratorRequest":
        if self.protocol != RQ1_PROMPT_PROTOCOL:
            raise ValueError("RQ1 prompt protocol drifted")
        if self.task_type is not TaskType.ESC_RESPONSE:
            raise ValueError("RQ1 request must be an ESC response request")
        if self.temperature != 0 or self.max_output_tokens != 256:
            raise ValueError("RQ1 decoding drifted from the frozen Generator surface")
        if self.messages[0] != GeneratorMessage(
            role="system", content=ESC_SUPPORTER_SYSTEM_PROMPT
        ):
            raise ValueError("official ESC supporter system prompt drifted")
        if self.messages[-1].role != "user":
            raise ValueError("RQ1 request must stop at the current seeker turn")
        resource_messages = [
            message for message in self.messages[1:] if message.role == "system"
        ]
        if bool(resource_messages) != bool(self.resource_sha256):
            raise ValueError("RS resource message/hash presence mismatch")
        if len(resource_messages) > 1:
            raise ValueError("RQ1 request may contain at most one typed RS bundle")
        if self.privileged_fields_present:
            raise ValueError("RQ1 request cannot contain role card/outcome/future fields")
        identity = canonical_json(
            [message.model_dump(mode="json") for message in self.messages]
        )
        if sha256_text(identity) != self.request_messages_hash:
            raise ValueError("request_messages_hash does not match exact messages")
        return self


def build_esc_supporter_request(
    *,
    visible_turns: tuple[GeneratorMessage, ...],
    resource: Step2ResourceEnvelope | None = None,
) -> Rq1GeneratorRequest:
    if not visible_turns or visible_turns[-1].role != "user":
        raise ValueError("visible ESC prefix must end at a seeker/user turn")
    if any(message.role == "system" for message in visible_turns):
        raise ValueError("visible ESC turns may contain only user/assistant roles")
    messages = [GeneratorMessage(role="system", content=ESC_SUPPORTER_SYSTEM_PROMPT)]
    resource_sha256 = None
    if resource is not None:
        if (
            resource.assignment is not TreatmentAssignment.ON
            or resource.head is not Head.RS
            or resource.resource_block is None
        ):
            raise ValueError("RQ1 can receive only one delivered RS=ON resource")
        messages.append(
            GeneratorMessage(role="system", content=resource.rendered_resource_block)
        )
        resource_sha256 = resource.resource_block.resource_sha256
    messages.extend(visible_turns)
    exact = tuple(messages)
    return Rq1GeneratorRequest(
        messages=exact,
        resource_sha256=resource_sha256,
        request_messages_hash=sha256_text(
            canonical_json([message.model_dump(mode="json") for message in exact])
        ),
    )


__all__ = [
    "ESC_SUPPORTER_SYSTEM_PROMPT",
    "RQ1_PROMPT_PROTOCOL",
    "Rq1GeneratorRequest",
    "build_esc_supporter_request",
]
