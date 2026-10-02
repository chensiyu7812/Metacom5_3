"""Explicit, meaning-preserving format repairs for a separate diagnostic view."""
from __future__ import annotations

import json
import re

from metacom_pm.paper1.evaluation.local_teacher import parse_local_verdict


def recover_teacher_format(raw: str, *, thinking: bool = False) -> dict:
    text = raw.strip()
    if thinking:
        if "</think>" not in text:
            raise ValueError("no completed thinking section")
        text = text.split("</think>", 1)[1].strip()
    if text.startswith("```json\n") and text.endswith("\n```"):
        text = text[8:-4].strip()
    changes = []
    # Repair only an exact bare enum in the verdict field, never infer a label.
    text, n = re.subn(r'("verdict"\s*:\s*)(A_better|B_better|equivalent|uncertain)(\s*[,}])',
                     r'\1"\2"\3', text)
    if n:
        changes.append("quoted_bare_verdict_enum")

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate key")
            result[key] = value
        return result

    try:
        value = json.loads(text, object_pairs_hook=unique)
    except json.JSONDecodeError:
        try:
            value = json.loads(text + "}", object_pairs_hook=unique)
        except json.JSONDecodeError:
            match = re.fullmatch(r'\{\s*"verdict"\s*:\s*"(A_better|B_better|equivalent|uncertain)"\s*,\s*"rationale"\s*:\s*([^{}]+)\s*\}', text, re.S)
            if not match:
                raise ValueError("not an unambiguous flat response")
            rationale = match[2].strip()
            if rationale.startswith('"') or '"verdict"' in rationale or '"rationale"' in rationale:
                raise ValueError("ambiguous unquoted rationale")
            value = {"verdict": match[1], "rationale": rationale}
            changes.append("quoted_plain_rationale_without_changing_text")
        else:
            changes.append("closed_single_missing_object_brace")
    if isinstance(value, dict):
        trimmed = {key.strip(): content for key, content in value.items()}
        if len(trimmed) != len(value):
            raise ValueError("duplicate key after whitespace normalization")
        if set(trimmed) != set(value):
            value = trimmed
            changes.append("trimmed_JSON_key_whitespace")
    for typo in ["rationationale", "rationacle", "rationable"]:
        if isinstance(value, dict) and set(value) == {"verdict", typo}:
            value = {"verdict": value["verdict"], "rationale": value[typo]}
            changes.append("renamed_" + typo + "_to_rationale")
    parsed = parse_local_verdict(json.dumps(value, ensure_ascii=False))
    if not changes:
        raise ValueError("no recognized format repair")
    return {**parsed, "repairs": changes}


def recover_reasoning_result(raw: str) -> dict:
    """Read an explicit final selection, including explicitly rejected alternatives.

    Never select a label from the reasoning body, infer a winner, or resolve
    conflicting endorsements. The original full result explanation is retained.
    """
    text = raw.strip()
    if text.count("**Reasoning:**") != 1 or text.count("**Result:**") != 1:
        raise ValueError("expected one reasoning and one result section")
    match = re.fullmatch(r"\*\*Reasoning:\*\*\s*(.+?)\s*\*\*Result:\*\*\s*(.+)", text, re.S)
    if not match:
        raise ValueError("incomplete reasoning/result sections")
    reasoning, result = match[1].strip(), match[2].strip()
    punctuated = re.fullmatch(r"(A_better|B_better|equivalent|uncertain)\.", result)
    if punctuated:
        return {"verdict": punctuated[1], "rationale": reasoning,
                "repairs": ["removed_single_terminal_result_period"]}
    positive, negative = set(), set()
    for token in re.finditer(r"\b(A_better|B_better|equivalent|uncertain)\b", result):
        statement = re.match(r"\s+is\s+(incorrect|not correct|correct)\b", result[token.end():], re.I)
        if statement:
            (positive if statement[1].lower() == "correct" else negative).add(token[1])
        elif re.search(r"\bcorrect (?:answer|result|choice) is\s*(?:\*\*)?$", result[:token.start()], re.I):
            positive.add(token[1])
        else:
            raise ValueError("result label lacks an explicit endorsement or rejection")
    if len(positive) != 1 or positive & negative:
        raise ValueError("missing or contradictory explicit result")
    return {"verdict": next(iter(positive)), "rationale": reasoning + "\n\n" + result,
            "repairs": ["read_single_explicit_endorsement_and_rejected_alternatives"]}
