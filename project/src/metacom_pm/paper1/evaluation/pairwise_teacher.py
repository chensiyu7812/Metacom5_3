"""Task-aware blinded pairwise teacher prompt and fail-closed parser."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from metacom_pm.io import canonical_json, sha256_text


PAIRWISE_TEACHER_PROTOCOL = "paper1-pairwise-material-effect-teacher-v1"
VERDICTS = frozenset({"A_better", "B_better", "equivalent", "uncertain"})

COMMON_INSTRUCTION = """You are a blinded pairwise evaluator. Compare Response A and Response B for the exact task below.

Judge a clear, meaningful difference in correctness, usefulness, appropriateness, coherence, or safety. Do not reward a response merely for being longer, warmer, more personalized, more strategy-heavy, or for mentioning memory. If neither response has a discernible material advantage, choose equivalent. If the evidence is insufficient, the advantages conflict without a defensible overall choice, or correctness cannot be determined, choose uncertain. Never infer which response is ON/OFF or which system produced it.

Return exactly one JSON object with exactly two keys: verdict and rationale. verdict must be one of A_better, B_better, equivalent, uncertain. rationale must be a concise explanation grounded only in the supplied material."""

TASK_RUBRICS = {
    "ESC": (
        "Emotional-support response: prefer the response that is materially better overall "
        "for the seeker's current message, including empathy, relevance, helpfulness, "
        "naturalness, and absence of harmful or unsupported claims. Extra empathy or advice "
        "alone is not an advantage when it is unnecessary or poorly matched."
    ),
    "QA": (
        "Question answering: use the supplied reference answer to judge semantic correctness. "
        "Prefer a materially more correct and directly responsive answer; harmless wording "
        "differences between equally correct answers are equivalent."
    ),
    "Summary": (
        "Longitudinal summary: use the supplied reference material to judge coverage of the "
        "requested events, temporal/causal coherence, factual faithfulness, and concision. "
        "A tiny wording or overlap difference is not material."
    ),
    "DG": (
        "Dialogue-generation turn: judge the next supporter response for correct use of prior "
        "history, appropriate personalization, emotional-support quality, and non-harm. A "
        "memory mention is not beneficial if irrelevant, repetitive, stale, or incorrect."
    ),
}

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": sorted(VERDICTS)},
        "rationale": {"type": "string"},
    },
    "required": ["verdict", "rationale"],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class ParsedTeacherVerdict:
    verdict: str
    rationale: str


def build_pairwise_teacher_prompt(
    *,
    task: str,
    task_input: str,
    response_a: str,
    response_b: str,
    reference_material: str | None,
) -> str:
    if task not in TASK_RUBRICS:
        raise ValueError(f"unsupported pairwise task: {task!r}")
    if not task_input.strip() or not response_a.strip() or not response_b.strip():
        raise ValueError("task input and both anonymous responses must be nonempty")
    sections = [
        COMMON_INSTRUCTION,
        f"TASK: {task}\nRUBRIC: {TASK_RUBRICS[task]}",
        f"TASK INPUT:\n{task_input}",
    ]
    if reference_material is not None:
        if not reference_material.strip():
            raise ValueError("reference material cannot be blank when supplied")
        sections.append(f"AUTHORIZED REFERENCE MATERIAL:\n{reference_material}")
    sections.extend(
        (f"RESPONSE A:\n{response_a}", f"RESPONSE B:\n{response_b}")
    )
    return "\n\n".join(sections)


def parse_pairwise_teacher_response(raw: str) -> ParsedTeacherVerdict:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError("teacher output is not one JSON object") from exc
    if not isinstance(value, dict) or set(value) != {"verdict", "rationale"}:
        raise ValueError("teacher output must have exactly verdict and rationale")
    verdict = value["verdict"]
    rationale = value["rationale"]
    if verdict not in VERDICTS:
        raise ValueError("teacher verdict is outside the frozen four-class set")
    if not isinstance(rationale, str) or not rationale.strip() or len(rationale) > 600:
        raise ValueError("teacher rationale must contain 1..600 nonblank characters")
    return ParsedTeacherVerdict(verdict=verdict, rationale=rationale.strip())


def pairwise_teacher_identity_payload() -> dict[str, Any]:
    return {
        "protocol": PAIRWISE_TEACHER_PROTOCOL,
        "common_instruction_sha256": sha256_text(COMMON_INSTRUCTION),
        "task_rubric_sha256": {
            task: sha256_text(rubric) for task, rubric in sorted(TASK_RUBRICS.items())
        },
        "response_schema_sha256": sha256_text(canonical_json(RESPONSE_SCHEMA)),
        "verdicts": sorted(VERDICTS),
    }


__all__ = [
    "COMMON_INSTRUCTION",
    "PAIRWISE_TEACHER_PROTOCOL",
    "ParsedTeacherVerdict",
    "RESPONSE_SCHEMA",
    "TASK_RUBRICS",
    "VERDICTS",
    "build_pairwise_teacher_prompt",
    "pairwise_teacher_identity_payload",
    "parse_pairwise_teacher_response",
]
