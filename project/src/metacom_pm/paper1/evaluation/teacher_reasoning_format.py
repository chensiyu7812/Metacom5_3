"""Bounded Selene output-format diagnostic; preserve the four-class task."""
from __future__ import annotations

import re

JSON_INSTRUCTION = (
    "Return exactly one JSON object with exactly two keys: verdict and rationale. "
    "verdict must be one of A_better, B_better, equivalent, uncertain. "
    "rationale must be a concise explanation grounded only in the supplied material."
)
REASONING_INSTRUCTION = (
    "Your reply must strictly follow this format:\n"
    "**Reasoning:** A concise explanation grounded only in the supplied material.\n"
    "**Result:** One of A_better, B_better, equivalent, uncertain.\n"
    "Write the explanation first and the final result last."
)


def reasoning_first_prompt(prompt: str) -> str:
    if prompt.count(JSON_INSTRUCTION) != 1:
        raise ValueError("expected exactly one output-format instruction")
    return prompt.replace(JSON_INSTRUCTION, REASONING_INSTRUCTION)


def parse_reasoning_result(raw: str, *, thinking: bool = False) -> dict[str, str]:
    if thinking:
        raise ValueError("this output-format diagnostic is for nonthinking Selene")
    text = raw.strip()
    if text.count("**Reasoning:**") != 1 or text.count("**Result:**") != 1:
        raise ValueError("exactly one reasoning and result required")
    match = re.fullmatch(
        r"\*\*Reasoning:\*\*\s*(.+?)\s*\*\*Result:\*\*\s*"
        r"(A_better|B_better|equivalent|uncertain)\s*", text, re.DOTALL,
    )
    if not match or not match[1].strip():
        raise ValueError("expected complete reasoning followed by one four-class result")
    return {"verdict": match[2], "rationale": match[1].strip()}
