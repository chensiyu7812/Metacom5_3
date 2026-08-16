"""B8/B12/B18: QA/Summary/DG gold-adjacent data must be physically isolated to splits/.

B12 deepened this from a two-file check to a scan of the whole active
runtime namespace (``data.memory_source``, ``memory.*``, ``candidates.*``,
``features.*``) -- not just ``candidates``/``features`` -- and added the
``exact_evidence_fingerprint``/``fold_id``/``group_component_id`` names to
the forbidden set (B12.6: split/fold opaque identity must never become a
model feature either).

B18 rebuilt the runtime data path around a materializer/sanitized-artifact
split: ``metacom_pm.paper1.data.materializer`` is now the only module
allowed to read raw ``evo_emo.json`` for the runtime side (besides the
evaluator/split-only ``es_memeval``/``splits.evidence`` pair, which the
runtime surface must never import either). This file checks isolation on
several independent, non-redundant layers -- deliberately not just one
field-name scan (B18.6):

1. AST-level forbidden attribute/subscript/import scan of every runtime
   surface module's own source (structural, catches accidental reads even
   if no existing behavioral test happens to exercise them).
2. AST-level import-boundary scan: no runtime surface module may import
   ``data.es_memeval``, ``data.materializer``, or ``splits.evidence`` at
   all, structurally -- not just "doesn't currently call the forbidden
   function".
3. Dataclass/pydantic-model field-name scan of every sanitized runtime type
   (``MemorySourceUser``/``Session``/``Turn``/``Target``) and every
   candidate/feature schema type (``CandidateRecord``/``CandidateLineage``/
   ``CandidateFeatureSnapshot``/``TargetHeadCensusRow``/``EligiblePoolRow``)
   -- the shape itself must never carry a forbidden field, independent of
   whether any current code path happens to populate one.
4. A schema-level scan of the actual bytes of a freshly-materialized
   sanitized runtime artifact (built via ``materializer.
   write_sanitized_runtime_artifact`` into a tmp path, mirroring
   ``scripts/paper1/05_materialize_sanitized_runtime_artifact.py``'s own
   self-check) -- this is the only layer that is a literal field-name scan,
   and it exists in addition to, never instead of, layers 1-3.
"""

import ast
import dataclasses
import hashlib
import inspect
import json
from pathlib import Path

from metacom_pm.paper1 import candidates as candidates_pkg
from metacom_pm.paper1 import features as features_pkg
from metacom_pm.paper1 import memory as memory_pkg
from metacom_pm.paper1.candidates import compilers as candidates_compilers
from metacom_pm.paper1.contracts import CandidateLineage, CandidateRecord
from metacom_pm.paper1.data import es_memeval, materializer, memory_source
from metacom_pm.paper1.data.es_memeval import load_users
from metacom_pm.paper1.data.es_memeval import parse_users as parse_evaluator_users
from metacom_pm.paper1.data.materializer import build_sanitized_runtime_users, load_raw_users
from metacom_pm.paper1.data.memory_source import (
    MemorySourceUser,
    Session,
    Target,
    Turn,
    enumerate_targets,
)
from metacom_pm.paper1.features import (
    build_census,
    feature_readiness_audit,
    me_candidate_audit,
    mp_extraction_audit,
    zero_outcome_census,
)
from metacom_pm.paper1.features.zero_outcome_census import CandidateFeatureSnapshot, EligiblePoolRow
from metacom_pm.paper1.memory import me as memory_me
from metacom_pm.paper1.memory import mp as memory_mp
from metacom_pm.paper1.memory import ms as memory_ms
from metacom_pm.paper1.memory.ms import SessionDocument
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
    "related_sessions",
    "more_details",
    "physical_condition",
    "psychological_condition",
    "emotion",
    "topic",
}

# The evaluator/split-only types+functions: legitimate only inside
# metacom_pm.paper1.splits.evidence and metacom_pm.paper1.data.es_memeval's
# own definitions.
FORBIDDEN_EVALUATOR_IMPORTS = {
    "UserRecord",
    "QuestionItem",
    "QuestionGroup",
    "SummaryItem",
    "SubsequentTopic",
    "parse_users",
}

# B18: modules a runtime surface module must never import from, structurally,
# regardless of whether it currently calls anything forbidden from them.
FORBIDDEN_RUNTIME_IMPORT_MODULES = (
    "metacom_pm.paper1.data.es_memeval",
    "metacom_pm.paper1.data.materializer",
    "metacom_pm.paper1.splits.evidence",
)

# The runtime surface B12/B18 requires stay evidence-blind and raw-JSON-blind:
# sanitized data loader, memory extraction, candidate compilers, census/features.
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
    mp_extraction_audit,
    me_candidate_audit,
    feature_readiness_audit,
)


def _forbidden_accesses(module) -> list[str]:
    """AST-level check: real attribute/subscript access to a forbidden name,
    plus any import of the splits-only evidence reader, the raw materializer,
    or the evaluator/split-only raw types.

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
            if any(forbidden in full for forbidden in FORBIDDEN_RUNTIME_IMPORT_MODULES):
                hits.append(f"import of raw-loader/materializer/splits-evidence module: {full!r}")
            if "SplitEvidenceRecord" in full:
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
    assert field_names.isdisjoint(FORBIDDEN_ATTR_OR_KEY_NAMES)


def test_sanitized_runtime_types_never_carry_a_forbidden_field_structurally():
    # B18.3: shape-level check, independent of whether any current code path
    # happens to populate a forbidden field -- the dataclass itself must not
    # have room for one.
    for dc in (MemorySourceUser, Session, Turn, Target, SessionDocument):
        field_names = {f.name for f in dataclasses.fields(dc)}
        hit = field_names & FORBIDDEN_ATTR_OR_KEY_NAMES
        assert hit == set(), f"{dc.__name__} carries forbidden field(s): {hit}"


def test_candidate_and_census_schema_types_never_carry_a_forbidden_field_structurally():
    for dc in (CandidateFeatureSnapshot, EligiblePoolRow):
        field_names = {f.name for f in dataclasses.fields(dc)}
        hit = field_names & FORBIDDEN_ATTR_OR_KEY_NAMES
        assert hit == set(), f"{dc.__name__} carries forbidden field(s): {hit}"
    # CandidateRecord/CandidateLineage are Codex-A-owned pydantic contracts
    # (contracts.py) -- read-only structural check, never edited from here.
    for model in (CandidateRecord, CandidateLineage):
        field_names = set(model.model_fields.keys())
        hit = field_names & FORBIDDEN_ATTR_OR_KEY_NAMES
        assert hit == set(), f"{model.__name__} carries forbidden field(s): {hit}"


def test_split_evidence_record_is_a_distinct_type_owned_by_splits():
    field_names = {f.name for f in dataclasses.fields(SplitEvidenceRecord)}
    assert "evidence_refs" in field_names
    assert SplitEvidenceRecord.__module__.startswith("metacom_pm.paper1.splits")


def test_runtime_surface_never_accesses_evidence_gold_observation_or_fold_identity():
    for module in RUNTIME_SURFACE_MODULES:
        hits = _forbidden_accesses(module)
        assert hits == [], f"{module.__name__}: {hits}"


def test_runtime_surface_never_imports_raw_loader_materializer_or_splits_evidence():
    # B18.6: fail-closed import-boundary check. Every module in the active
    # runtime namespace -- including memory_source.py itself, which is the
    # one module allowed to *define* the sanitized types but must still never
    # import the raw loader, the materializer, or the splits-only evidence
    # reader -- must not import any of them, structurally.
    for module in RUNTIME_SURFACE_MODULES:
        tree = ast.parse(inspect.getsource(module))
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module in FORBIDDEN_RUNTIME_IMPORT_MODULES:
                raise AssertionError(f"{module.__name__} imports {node.module}: {ast.dump(node)}")
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name in FORBIDDEN_RUNTIME_IMPORT_MODULES:
                        raise AssertionError(f"{module.__name__} imports {alias.name}: {ast.dump(node)}")


def test_materializer_is_the_only_runtime_side_module_that_imports_es_memeval():
    # B18: materializer.py itself never imports es_memeval either -- it is an
    # independent raw-JSON parser, not a thin wrapper over the evaluator
    # loader. Only metacom_pm.paper1.splits.evidence (out of scope for this
    # file's RUNTIME_SURFACE_MODULES) is allowed to depend on es_memeval.
    tree = ast.parse(inspect.getsource(materializer))
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module == "metacom_pm.paper1.data.es_memeval":
            raise AssertionError(f"materializer.py imports es_memeval: {ast.dump(node)}")


def test_candidate_manifest_rows_never_carry_evidence_or_gold_fields():
    users = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
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
    raw = load_raw_users(EVO_PATH)
    targets = enumerate_targets(build_sanitized_runtime_users(raw))
    records = enumerate_split_evidence(parse_evaluator_users(load_users(EVO_PATH)))
    assert {t.target_id for t in targets} == {r.target_id for r in records}


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


def test_freshly_materialized_artifact_bytes_contain_no_forbidden_json_key(tmp_path):
    # B18.6 layer 4: a schema-level scan of the actual materialized artifact
    # bytes, in addition to (never instead of) the structural AST/field-name
    # checks above -- mirrors scripts/paper1/05_materialize_sanitized_
    # runtime_artifact.py's own self-check, but rebuilt independently here so
    # this test does not depend on that script having already been run.
    out_path = tmp_path / "sanitized_runtime_artifact.json"
    materializer.write_sanitized_runtime_artifact(EVO_PATH, out_path)
    artifact_text = out_path.read_text(encoding="utf-8")

    forbidden_tokens = (
        '"answer"',
        '"evidence"',
        '"theme"',
        '"group"',
        '"related_sessions"',
        '"more_details"',
        '"physical_condition"',
        '"psychological_condition"',
        '"basic_info"',
        '"observation"',
        '"summary"',
    )
    found = [tok for tok in forbidden_tokens if tok in artifact_text]
    assert found == [], f"sanitized runtime artifact unexpectedly contains: {found}"

    # B23: emotion/topic checked as exact JSON keys (quoted name + the
    # canonical no-space ':' separator), not a bare word scan -- the corpus
    # legitimately contains dialogue turns that use these as ordinary
    # English words (e.g. "let's change the topic"), which must never trip
    # this check; only an actual "emotion"/"topic" *field* may.
    forbidden_key_tokens = ('"emotion":', '"topic":')
    found_keys = [tok for tok in forbidden_key_tokens if tok in artifact_text]
    assert found_keys == [], f"sanitized runtime artifact unexpectedly contains key(s): {found_keys}"

    payload = json.loads(artifact_text)
    assert payload["schema"] == materializer.SANITIZED_ARTIFACT_SCHEMA_VERSION


def test_dialogue_content_containing_the_words_emotion_or_topic_is_not_flagged(tmp_path):
    # B23 grounding: the real corpus has dialogue turns that legitimately use
    # "emotion(s)"/"topic(s)" as ordinary English words (e.g. p1/esc786 turn
    # 18 discusses "friendship", p1/p1_conv_6 turn 4 says "a mix of
    # emotions") -- confirm this content survives materialization verbatim
    # and that the precise-key forbidden scan does not flag it.
    raw = load_raw_users(EVO_PATH)
    p1 = next(u for u in raw if u["id"] == "p1")
    turn_texts = [t["content"] for s in p1["dialog_history"] for t in s["dialogue"]]
    assert any("emotion" in t.lower() for t in turn_texts), "expected a known real 'emotion(s)' mention"
    assert any("topic" in t.lower() for t in turn_texts), "expected a known real 'topic(s)' mention"

    out_path = tmp_path / "sanitized_runtime_artifact.json"
    materializer.write_sanitized_runtime_artifact(EVO_PATH, out_path)
    artifact_text = out_path.read_text(encoding="utf-8")
    assert '"emotion":' not in artifact_text
    assert '"topic":' not in artifact_text
    # the ordinary-word content itself is preserved verbatim, just never as a key
    assert "emotion" in artifact_text.lower()
    assert "topic" in artifact_text.lower()


def test_materialized_artifact_round_trips_through_load_sanitized_runtime_users(tmp_path):
    out_path = tmp_path / "sanitized_runtime_artifact.json"
    materializer.write_sanitized_runtime_artifact(EVO_PATH, out_path)
    loaded = memory_source.load_sanitized_runtime_users(out_path)
    direct = build_sanitized_runtime_users(load_raw_users(EVO_PATH))
    assert {u.owner_id for u in loaded} == {u.owner_id for u in direct}
    assert sum(len(u.sessions) for u in loaded) == sum(len(u.sessions) for u in direct)


def test_sanitized_artifact_sha256_is_deterministic_across_rebuilds(tmp_path):
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    materializer.write_sanitized_runtime_artifact(EVO_PATH, out_a)
    materializer.write_sanitized_runtime_artifact(EVO_PATH, out_b)
    sha_a = hashlib.sha256(out_a.read_bytes()).hexdigest()
    sha_b = hashlib.sha256(out_b.read_bytes()).hexdigest()
    assert sha_a == sha_b
