import ast
from pathlib import Path

import pytest

from metacom_pm.paper1.evaluation.static_official_templates import _parts, render_templates, extract_templates


def test_literal_json_braces_and_prediction_are_preserved():
    node = ast.parse('f\'Question: {question}\\n{{"score": 0}}\\n{gold}\\n{prediction}\'', mode="eval").body
    template = [{"role": "user", "parts": _parts(node)}]
    actual = render_templates(template, question="q", gold="g", prediction="{question}\nScore: 2")
    assert actual[0]["content"] == 'Question: q\n{"score": 0}\ng\n{question}\nScore: 2'


@pytest.mark.parametrize("expression", ['f"{question.upper()}"', 'f"{unknown}"', 'f"{prediction!r}"'])
def test_template_never_evaluates_code_or_unknown_fields(expression):
    with pytest.raises(ValueError):
        _parts(ast.parse(expression, mode="eval").body)


def test_unpinned_source_is_rejected(tmp_path: Path):
    source = tmp_path / "source.py"
    source.write_text("raise RuntimeError('must not execute')")
    with pytest.raises(ValueError, match="identity"):
        extract_templates(source, task="qa")
