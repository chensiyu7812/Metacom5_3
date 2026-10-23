from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Turn
from metacom_pm.paper1.multi_view_memory.batch import run_session_prefix
from metacom_pm.paper1.multi_view_memory.contracts import (
    ExtractorSessionOutput,
    VerifierSessionOutput,
)
from metacom_pm.paper1.multi_view_memory.grounding import (
    MULTI_VIEW_GROUNDING_VERSION,
    prior_profile_sha256,
    source_sha256,
)
from metacom_pm.paper1.multi_view_memory.runtime import SessionCompilationResult


class EmptyCompiler:
    compiler_identity_sha256 = "c" * 64

    def compile_session(self, source):
        extractor = ExtractorSessionOutput(
            owner_id=source.owner_id,
            session_id=source.session_id,
        )
        verifier = VerifierSessionOutput(
            owner_id=source.owner_id,
            session_id=source.session_id,
            decisions=(),
        )
        return SessionCompilationResult(
            compiler_version="test",
            grounding_version=MULTI_VIEW_GROUNDING_VERSION,
            owner_id=source.owner_id,
            session_id=source.session_id,
            source_sha256=source_sha256(source),
            prior_profile_sha256=prior_profile_sha256(source),
            extractor=extractor,
            verifier=verifier,
            grounding=(),
            accepted_units=(),
            rejected_decisions=(),
            extractor_cache_hit=False,
            verifier_cache_hit=True,
        )


def _users():
    return (
        MemorySourceUser(
            owner_id="u1",
            sessions=(
                Session(
                    session_id="s2",
                    timestamp="2025-02-01",
                    chronological_rank=1,
                    turns=(Turn(idx=0, role="seeker", content="second"),),
                ),
                Session(
                    session_id="s1",
                    timestamp="2025-01-01",
                    chronological_rank=0,
                    turns=(Turn(idx=0, role="seeker", content="first"),),
                ),
            ),
            question_groups=(),
            summaries=(),
            subsequent_topics=(),
        ),
    )


def test_batch_is_stably_ordered_and_resumes_an_exact_prefix(tmp_path):
    results = tmp_path / "results.jsonl"
    report = tmp_path / "report.json"
    first = run_session_prefix(
        users=_users(),
        compiler=EmptyCompiler(),
        maximum_sessions=1,
        results_path=results,
        report_path=report,
    )
    assert first["completed_sessions"] == 1
    second = run_session_prefix(
        users=_users(),
        compiler=EmptyCompiler(),
        maximum_sessions=2,
        results_path=results,
        report_path=report,
    )
    assert second["completed_sessions"] == 2
    assert second["accepted_units"] == 0
    assert [line for line in results.read_text(encoding="utf-8").splitlines()]
    assert sha256_text(canonical_json(second))
