from metacom_pm.paper1.data.memory_source import MemorySourceUser, Session, Turn
from metacom_pm.paper1.semantic_memory.batch import ordered_public_sessions, run_session_prefix
from metacom_pm.paper1.semantic_memory.contracts import (
    ExtractorSessionOutput,
    VerifierSessionOutput,
)
from metacom_pm.paper1.semantic_memory.grounding import (
    prior_memory_table_sha256,
    source_sha256,
)
from metacom_pm.paper1.semantic_memory.runtime import SessionCompilationResult


def _user(owner_id: str, sessions: tuple[Session, ...]) -> MemorySourceUser:
    return MemorySourceUser(
        owner_id=owner_id,
        sessions=sessions,
        question_groups=(),
        summaries=(),
        subsequent_topics=(),
    )


class EmptyCompiler:
    def __init__(self) -> None:
        self.sources = []

    @property
    def compiler_version(self):
        return "test-compiler-v1"

    @property
    def grounding_version(self):
        return "test-grounding-v1"

    def compile_session(self, source):
        self.sources.append(source)
        return SessionCompilationResult(
            compiler_version=self.compiler_version,
            grounding_version=self.grounding_version,
            owner_id=source.owner_id,
            session_id=source.session_id,
            source_sha256=source_sha256(source),
            prior_memory_table_sha256=prior_memory_table_sha256(source),
            extractor=ExtractorSessionOutput(
                owner_id=source.owner_id, session_id=source.session_id
            ),
            verifier=VerifierSessionOutput(
                owner_id=source.owner_id, session_id=source.session_id, decisions=()
            ),
            grounding=(),
            accepted_units=(),
            rejected_decisions=(),
            extractor_cache_hit=False,
            verifier_cache_hit=False,
        )


def test_batch_uses_owner_then_timestamp_session_order_and_exact_prefix_resume(tmp_path) -> None:
    later = Session(
        session_id="z",
        timestamp="2024-02-01",
        chronological_rank=1,
        turns=(Turn(idx=0, role="seeker", content="later"),),
    )
    earlier = Session(
        session_id="a",
        timestamp="2024-01-01",
        chronological_rank=0,
        turns=(Turn(idx=0, role="seeker", content="earlier"),),
    )
    other = Session(
        session_id="b",
        timestamp="2024-03-01",
        chronological_rank=0,
        turns=(Turn(idx=0, role="seeker", content="other"),),
    )
    users = (_user("p2", (other,)), _user("p1", (later, earlier)))
    assert [(row.owner_id, row.session.session_id) for row in ordered_public_sessions(users)] == [
        ("p1", "a"),
        ("p1", "z"),
        ("p2", "b"),
    ]

    first = EmptyCompiler()
    report = run_session_prefix(
        users=users,
        compiler=first,
        maximum_sessions=2,
        results_path=tmp_path / "results.jsonl",
        report_path=tmp_path / "report.json",
    )
    assert report["completed_sessions"] == 2
    assert [source.session_id for source in first.sources] == ["a", "z"]

    resumed = EmptyCompiler()
    resumed_report = run_session_prefix(
        users=users,
        compiler=resumed,
        maximum_sessions=2,
        results_path=tmp_path / "results.jsonl",
        report_path=tmp_path / "report.json",
    )
    assert resumed_report["complete"] is True
    assert resumed.sources == []
