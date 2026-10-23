"""Local development judges and natural-end generation helpers.

No paid APIs or formal label construction. Historical Gemini parsing stays intact.
"""
from __future__ import annotations

import json
from typing import Any

from metacom_pm.paper1.evaluation.pairwise_teacher import VERDICTS


def repeated_tail(tokens: list[int], block: int = 32, repeats: int = 4) -> bool:
    """Detect a long exact token cycle, without penalizing ordinary word repetition."""
    if len(tokens) < block * repeats:
        return False
    last = tokens[-block:]
    return all(tokens[-block * (i + 1): -block * i] == last for i in range(1, repeats))


def natural_finish_reason(tokens: list[int], eos_ids: list[int], guard_reason: str | None,
                          remaining_context: int) -> str:
    # An EOS at the context boundary is still a natural completion.
    if tokens and tokens[-1] in eos_ids:
        return "stop"
    if guard_reason:
        return guard_reason
    if len(tokens) >= remaining_context:
        return "context_exhausted"
    return "incomplete_unknown"


def parse_local_verdict(raw: str, *, thinking: bool = False) -> dict[str, Any]:
    """Parse the complete final answer, never search arbitrary prose for a verdict.

    A complete Markdown fence is a harmless wrapper. Qwen's template pre-fills
    <think>, so only a closing tag may be present in the generated continuation.
    """
    text = raw.strip()
    if thinking:
        if "</think>" not in text:
            raise ValueError("thinking did not produce a final answer")
        text = text.split("</think>", 1)[1].strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[8:-4].strip()
    elif text.startswith("```\n") and text.endswith("\n```"):
        text = text[4:-4].strip()

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    value = json.loads(text, object_pairs_hook=unique)
    if not isinstance(value, dict) or set(value) != {"verdict", "rationale"}:
        raise ValueError("expected exactly verdict and rationale")
    if not isinstance(value["verdict"], str) or value["verdict"] not in VERDICTS:
        raise ValueError("invalid verdict")
    if not isinstance(value["rationale"], str) or not value["rationale"].strip():
        raise ValueError("missing rationale")
    return value


def binary_benefit(verdict: str | None, a_arm: str) -> int | None:
    if a_arm not in {"ON", "OFF"}:
        raise ValueError("invalid A orientation")
    if verdict is None or verdict == "uncertain":
        return None
    if verdict == "equivalent":
        return 0
    if verdict not in VERDICTS:
        raise ValueError("invalid verdict")
    return int((verdict == "A_better") == (a_arm == "ON"))
