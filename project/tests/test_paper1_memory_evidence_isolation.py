"""B8/B12: QA/Summary gold-adjacent evidence must be physically isolated to splits/.

B12 deepened this from a two-file check to a scan of the whole active
runtime namespace (``data.memory_source``, ``memory.*``, ``candidates.*``,
``features.*``) -- not just ``candidates``/``features`` -- and added the
``exact_evidence_fingerprint``/``fold_id``/``group_component_id`` names to
the forbidden set (B12.6: split/fold opaque identity must never become a
model feature either). These tests check the isolation structurally
(dataclass fields, module source AST, generated manifest content) rather
than only behaviorally, so a future accidental re-introduction of an
evidence read anywhere in the runtime surface fails a test even if no
existing behavioral test happens to exercise it.
"""

import ast
import dataclasses
import inspect
import json
from pathlib import Path

from metacom_pm.paper1 import candidates as candidates_pkg
from metacom_pm.paper1 import features as features_pkg
from metacom_pm.paper1 import memory as memory_pkg
from metacom_pm.paper1.candidates import compilers as candidates_compilers
from metacom_pm.paper1.data import es_memeval, memory_source
from metacom_pm.paper1.data.memory_source import (
    Target,
    enumerate_targets,
    parse_memory_source_users,
)
from metacom_pm.paper1.data.es_memeval import load_users
from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users
from metacom_pm.paper1.features import build_census, zero_outcome_census
from metacom_pm.paper1.memory import me as memory_me
from metacom_pm.paper1.memory import mp as memory_mp
from metacom_pm.paper1.memory import ms as memory_ms
from metacom_pm.paper1.splits.evidence import SplitEvidenceRecord, enumerate_split_evidence

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"

FORBIDDEN_ATTR_OR_KEY_NAMES = {
    "evidence",
    "evidence_refs",
    "answer",
    "gold",
    "observation",
    "exact_evidence_fingerprint",
    "fold_id",
    "group_component_id",
    "basic_info",
}

# The evaluator/split-only types+functions: legitimate only inside
# metacom_pm.paper1.splits.evidence (and es_memeval.py's own definitions).
FORBIDDEN_EVALUATOR_IMPORTS = {
    "UserRecord",
    "QuestionItem",
    "QuestionGroup",
    "SummaryItem",
    "SubsequentTopic",
    "parse_users",
}

# The runtime surface B12 requires stay evidence-blind: sanitized data
# loader, memory extraction, candidate compilers, census/features.
RUNTIME_SURFACE_MODULES = (
    memory_source,
    memory_pkg,
    memory_mp,
    memory_ms,
    memory_me,
    candidates_pkg,
    candidates_compilers,
    features_pkg,
    zero_outcome_census,
)


def _forbidden_accesses(module) -> list[str]:
    """AST-level check: real attribute/subscript access to a forbidden name,
    plus any import of the splits-only evidence reader or the evaluator/
    split-only raw types.

    Deliberately ignores docstrings/comments (an explanatory sentence like
    "never reads evidence" must not itself trip the check) and only flags
    actual code-level field access and imports.
    """

    tree = ast.parse(inspect.getsource(module))
    hits: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN_ATTR_OR_KEY_NAMES:
            hits.append(f"attribute access .{node.attr}")
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in FORBIDDEN_ATTR_OR_KEY_NAMES:
                hits.append(f"string key/constant {node.value!r}")
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            module_name = getattr(node, "module", None) or ""
            imported_names = {alias.name for alias in node.names}
            full = " ".join([module_name, *imported_names])
            if "splits.evidence" in full or "SplitEvidenceRecord" in full:
                hits.append(f"import of splits-only evidence module: {full!r}")
            if "es_memeval" in module_name:
                forbidden_here = imported_names & FORBIDDEN_EVALUATOR_IMPORTS
                if forbidden_here:
                    hits.append(f"import of evaluator/split-only type(s) {sorted(forbidden_here)} from {module_name!r}")
    return hits


def test_runtime_target_has_no_evidence_field():
    field_names = {f.name for f in dataclasses.fields(Target)}
    assert "evidence_refs" not in field_names
    assert not any("evidence" in name for name in field_names)


def test_split_evidence_record_is_a_distinct_type_owned_by_splits():
    field_names = {f.name for f in dataclasses.fields(SplitEvidenceRecord)}
    assert "evidence_refs" in field_names
    assert SplitEvidenceRecord.__module__.startswith("metacom_pm.paper1.splits")


def test_runtime_surface_never_accesses_evidence_gold_observation_or_fold_identity():
    for module in RUNTIME_SURFACE_MODULES:
        hits = _forbidden_accesses(module)
        assert hits == [], f"{module.__name__}: {hits}"


def test_es_memeval_module_itself_is_not_imported_by_the_runtime_surface():
    # es_memeval.py is evaluator/split-only; nothing in the sanitized runtime
    # surface should import it at all, not even for `Session`/`Turn` (those
    # are re-exported through memory_source's own re-import, which is
    # allowed since memory_source.py is the one place permitted to bridge
    # the two -- but memory/candidates/features must go through
    # memory_source, not es_memeval, directly).
    for module in (memory_mp, memory_ms, memory_me, candidates_compilers, zero_outcome_census):
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "metacom_pm.paper1.data.es_memeval":
                raise AssertionError(f"{module.__name__} imports es_memeval directly: {ast.dump(node)}")


def test_candidate_manifest_rows_never_carry_evidence_or_gold_fields():
    users = parse_memory_source_users(load_users(EVO_PATH))
    targets = [t for t in enumerate_targets(users) if t.owner_id == "p1"][:30]
    rows = build_census(users, targets)
    rendered = json.dumps([row.to_manifest_row() for row in rows]).lower()
    for token in ("evidence", "answer", "gold", "observation", "fold_id", "group_component_id"):
        assert token not in rendered


def test_split_evidence_only_enters_the_splits_layer_manifests():
    users = parse_evaluator_users(load_users(EVO_PATH))
    records = enumerate_split_evidence(users)
    assert len(records) == 1427 + 125 + 34
    # evidence really is present here (this IS the splits-only reader)
    assert any(r.evidence_refs for r in records)


def test_split_evidence_record_ids_match_runtime_target_ids():
    raw = load_users(EVO_PATH)
    targets = enumerate_targets(parse_memory_source_users(raw))
    records = enumerate_split_evidence(parse_evaluator_users(raw))
    assert {t.target_id for t in targets} == {r.target_id for r in records}


def test_sanitized_module_only_imports_the_safe_subset_of_es_memeval():
    tree = ast.parse(inspect.getsource(memory_source))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "metacom_pm.paper1.data.es_memeval":
            imported = {alias.name for alias in node.names}
            forbidden = imported & FORBIDDEN_EVALUATOR_IMPORTS
            assert forbidden == set(), f"memory_source.py imports evaluator-only names: {forbidden}"


def test_es_memeval_module_never_reads_answer_question_or_theme_text():
    # es_memeval.py is allowed to carry evidence (session-id references),
    # but never any gold *text* field -- answer/question/theme were never
    # parsed into any type here, full or sanitized.
    source = inspect.getsource(es_memeval)
    tree = ast.parse(source)
    string_constants = {
        node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    for forbidden in ("answer", "question", "theme"):
        assert forbidden not in string_constants
