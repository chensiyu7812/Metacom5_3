"""Extract exact QA/Summary official messages without importing the harness.

Only literal strings and the three named f-string slots are evaluated.
No network, model, annotation data or executable upstream code is invoked.
"""
from __future__ import annotations

import ast
from pathlib import Path

from metacom_pm.io import sha256_file

SOURCE_SHA256 = {
    "qa": "0607d0316d508db0002fb63e18ab86f3dbd2119ec6d90978d7170ed3db99b1db",
    "summary": "93f8267f6aff734fd5f42a7fdd1844b2754e8f314d50d938663f4e1dc0ff6d0f",
}


def _parts(node: ast.AST) -> list[dict]:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [{"literal": node.value}]
    if isinstance(node, ast.JoinedStr):
        result = []
        for part in node.values:
            if isinstance(part, ast.Constant) and isinstance(part.value, str):
                result.append({"literal": part.value})
            elif (isinstance(part, ast.FormattedValue) and isinstance(part.value, ast.Name)
                  and part.value.id in {"question", "gold", "prediction"}
                  and part.conversion == -1 and part.format_spec is None):
                result.append({"slot": part.value.id})
            else:
                raise ValueError("unexpected executable official template expression")
        return result
    raise ValueError("expected literal or named-slot f-string")


def extract_templates(path: Path, *, task: str) -> list[dict]:
    if sha256_file(path) != SOURCE_SHA256[task]:
        raise ValueError("official source identity mismatch")
    # Other upstream methods use Python 3.12 f-string syntax. The pinned
    # scorer method itself is compatible with 3.11; parse only its exact
    # indented source, without rewriting any prompt bytes.
    lines = path.read_text().splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.startswith("    def llm_as_a_judge(")]
    if len(starts) != 1:
        raise ValueError("ambiguous official scorer method")
    start = starts[0]
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("    def ")), len(lines))
    tree = ast.parse("class _Official:\n" + "".join(lines[start:end]))
    methods = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "llm_as_a_judge"]
    if len(methods) != 1:
        raise ValueError("ambiguous official scorer method")
    messages = []
    for node in ast.walk(methods[0]):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in {"SystemMessage", "HumanMessage"}:
            if len(node.args) != 1 or node.keywords:
                raise ValueError("unexpected official message call")
            messages.append({"line": node.lineno, "role": "system" if node.func.id == "SystemMessage" else "user",
                             "parts": _parts(node.args[0])})
    messages.sort(key=lambda m: m["line"])
    if [m["role"] for m in messages] != ["system", "user"]:
        raise ValueError("official messages differ from expected two-message sequence")
    return [{k: v for k, v in m.items() if k != "line"} for m in messages]


def render_templates(templates: list[dict], *, question: str, gold: str, prediction: str) -> list[dict]:
    values = {"question": question, "gold": gold, "prediction": prediction}
    return [{"role": m["role"], "content": "".join(p["literal"] if "literal" in p else values[p["slot"]]
                                                              for p in m["parts"])} for m in templates]
