"""B8: QA/Summary gold-adjacent evidence must be physically isolated to splits/.

These tests check the isolation structurally (dataclass fields, module
source text, generated manifest content) rather than only behaviorally, so a
future accidental re-introduction of an evidence read in candidates/features
fails a test even if no existing behavioral test happens to exercise it.
"""

import ast
import dataclasses
import inspect
import json
from pathlib import Path

from metacom_pm.paper1 import candidates as candidates_pkg
from metacom_pm.paper1 import features as features_pkg
from metacom_pm.paper1.candidates import compilers as candidates_compilers
from metacom_pm.paper1.data.es_memeval import Target, enumerate_targets, load_users, parse_users
from metacom_pm.paper1.features import build_census, zero_outcome_census
from metacom_pm.paper1.splits.evidence import SplitEvidenceRecord, enumerate_split_evidence

ROOT = Path(__file__).resolve().parents[1]
EVO_PATH = ROOT / "data/external/evo_emo.json"

FORBIDDEN_ATTR_OR_KEY_NAMES = {"evidence", "evidence_refs", "answer", "gold", "observation"}


def _forbidden_accesses(module) -> list[str]:
    """AST-level check: real attribute/subscript access to a forbidden name.

    Deliberately ignores docstrings/comments (an explanatory sentence like
    "never reads evidence" must not itself trip the check) and only flags
    actual code-level field access, plus any import of the splits-only
    evidence module.
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
            names = " ".join(
                [getattr(node, "module", None) or ""] + [alias.name for alias in node.names]
            )
            if "splits.evidence" in names or "SplitEvidenceRecord" in names:
                hits.append(f"import of splits-only evidence module: {names!r}")
    return hits


def test_runtime_target_has_no_evidence_field():
    field_names = {f.name for f in dataclasses.fields(Target)}
    assert "evidence_refs" not in field_names
    assert not any("evidence" in name for name in field_names)


def test_split_evidence_record_is_a_distinct_type_owned_by_splits():
    field_names = {f.name for f in dataclasses.fields(SplitEvidenceRecord)}
    assert "evidence_refs" in field_names
    assert SplitEvidenceRecord.__module__.startswith("metacom_pm.paper1.splits")


def test_candidates_module_never_accesses_evidence_gold_or_observation_fields():
    for module in (candidates_pkg, candidates_compilers):
        hits = _forbidden_accesses(module)
        assert hits == [], f"{module.__name__}: {hits}"


def test_features_module_never_accesses_evidence_gold_or_observation_fields():
    for module in (features_pkg, zero_outcome_census):
        hits = _forbidden_accesses(module)
        assert hits == [], f"{module.__name__}: {hits}"


def test_candidate_manifest_rows_never_carry_evidence_or_gold_fields():
    users = parse_users(load_users(EVO_PATH))
    targets = [t for t in enumerate_targets(users) if t.owner_id == "p1"][:30]
    rows = build_census(users, targets)
    rendered = json.dumps([row.to_manifest_row() for row in rows]).lower()
    for token in ("evidence", "answer", "gold", "observation"):
        assert token not in rendered


def test_split_evidence_only_enters_the_splits_layer_manifests():
    users = parse_users(load_users(EVO_PATH))
    records = enumerate_split_evidence(users)
    assert len(records) == 1427 + 125 + 34
    # evidence really is present here (this IS the splits-only reader)
    assert any(r.evidence_refs for r in records)


def test_split_evidence_record_ids_match_runtime_target_ids():
    users = parse_users(load_users(EVO_PATH))
    targets = enumerate_targets(users)
    records = enumerate_split_evidence(users)
    assert {t.target_id for t in targets} == {r.target_id for r in records}
