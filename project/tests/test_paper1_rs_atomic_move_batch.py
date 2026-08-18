from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from metacom_pm.paper1.rs.strategy_bank import StrategySourceCard
from metacom_pm.paper1.rs_atomic_move.batch import run_source_card_prefix
from metacom_pm.paper1.rs_atomic_move.contracts import SourceCardCompileInput
from metacom_pm.paper1.rs_atomic_move.runtime import SourceCardCompileResult


HEX64 = "c" * 64


def _card(card_id: str, dialogue_id: str, turn: int, response: str) -> StrategySourceCard:
    return StrategySourceCard(
        card_id=card_id,
        source_dialogue_id=dialogue_id,
        source_turn_index=turn,
        strategy_label="Affirmation and Reassurance",
        retrieval_text="seeker: I feel awful.",
        guidance_text="Use the strategy.",
        example_response=response,
        retrieval_text_sha256=HEX64,
        example_response_sha256=HEX64,
    )


class _FakeCompiler:
    compiler_version = "test-compiler-v1"

    def __init__(self, accepted_counts: list[int], run_identity: str = "identity-a") -> None:
        self.accepted_counts = list(accepted_counts)
        self.calls = 0
        self._run_identity = run_identity

    @property
    def run_identity_sha256(self) -> str:
        return self._run_identity

    @property
    def run_manifest(self) -> dict:
        return {"run_identity": self._run_identity}

    def compile_source_card(self, source: SourceCardCompileInput) -> SourceCardCompileResult:
        n = self.accepted_counts[self.calls]
        self.calls += 1
        return SourceCardCompileResult(
            accepted_units=(),
            extractor_proposal_count=n,
            structurally_invalid_proposals=0,
            verifier_rejections=0,
        )


def test_full_scope_over_the_whole_catalog_reports_complete(tmp_path):
    card = _card("rs_src_" + "0" * 24, "esconv_0001", 1, "You are doing great.")
    data = [
        {"dialog": []},
        {"dialog": [{"speaker": "seeker", "content": "I feel awful."}, {"speaker": "supporter", "content": "You are doing great."}]},
    ]
    compiler = _FakeCompiler([3])

    report = run_source_card_prefix(
        cards=(card,), esconv_data=data, compiler=compiler,
        maximum_cards=1, preceding_turns=6, run_scope="full",
        results_path=tmp_path / "results.jsonl", report_path=tmp_path / "report.json",
    )
    assert report["run_scope"] == "full"
    assert report["selected_cards"] == 1
    assert report["completed_cards"] == 1
    assert report["extractor_proposals"] == 3
    assert report["complete"] is True
    assert compiler.calls == 1


def test_full_scope_requires_selecting_the_entire_catalog(tmp_path):
    card1 = _card("rs_src_" + "1" * 24, "esconv_0000", 0, "You are doing great.")
    card2 = _card("rs_src_" + "2" * 24, "esconv_0001", 0, "That sounds hard.")
    combined = [
        {"dialog": [{"speaker": "supporter", "content": "You are doing great."}]},
        {"dialog": [{"speaker": "supporter", "content": "That sounds hard."}]},
    ]
    compiler = _FakeCompiler([1])
    with pytest.raises(ValueError, match="must select every card"):
        run_source_card_prefix(
            cards=(card1, card2), esconv_data=combined, compiler=compiler,
            maximum_cards=1, preceding_turns=6, run_scope="full",
            results_path=tmp_path / "results.jsonl", report_path=tmp_path / "report.json",
        )


def test_smoke_scope_never_reports_complete_even_when_its_own_prefix_finishes(tmp_path):
    card1 = _card("rs_src_" + "1" * 24, "esconv_0000", 0, "You are doing great.")
    card2 = _card("rs_src_" + "2" * 24, "esconv_0001", 0, "That sounds hard.")
    combined = [
        {"dialog": [{"speaker": "supporter", "content": "You are doing great."}]},
        {"dialog": [{"speaker": "supporter", "content": "That sounds hard."}]},
    ]
    compiler = _FakeCompiler([2])
    report = run_source_card_prefix(
        cards=(card1, card2), esconv_data=combined, compiler=compiler,
        maximum_cards=1, preceding_turns=6, run_scope="smoke",
        results_path=tmp_path / "results.jsonl", report_path=tmp_path / "report.json",
    )
    assert report["selected_cards"] == 1
    assert report["completed_cards"] == 1
    assert report["complete"] is False  # a 1-of-2-card smoke is never "complete"


def test_run_source_card_prefix_resumes_without_recompiling(tmp_path):
    combined = [
        {"dialog": [{"speaker": "supporter", "content": "You are doing great."}]},
        {"dialog": [{"speaker": "supporter", "content": "That sounds hard."}]},
    ]
    card1 = _card("rs_src_" + "1" * 24, "esconv_0000", 0, "You are doing great.")
    card2 = _card("rs_src_" + "2" * 24, "esconv_0001", 0, "That sounds hard.")

    compiler = _FakeCompiler([2])
    results_path = tmp_path / "results.jsonl"
    report_path = tmp_path / "report.json"
    report1 = run_source_card_prefix(
        cards=(card1, card2), esconv_data=combined, compiler=compiler,
        maximum_cards=1, preceding_turns=6, run_scope="smoke",
        results_path=results_path, report_path=report_path,
    )
    assert report1["completed_cards"] == 1
    assert compiler.calls == 1

    # resume with maximum_cards=2 -- must not recompile card1
    compiler2 = _FakeCompiler([5])  # only card2's compile is queued
    report2 = run_source_card_prefix(
        cards=(card1, card2), esconv_data=combined, compiler=compiler2,
        maximum_cards=2, preceding_turns=6, run_scope="smoke",
        results_path=results_path, report_path=report_path,
    )
    assert report2["completed_cards"] == 2
    assert compiler2.calls == 1  # only the new card, card1 was resumed from disk
    assert report2["extractor_proposals"] == 2 + 5


def test_run_source_card_prefix_fails_closed_on_prefix_mismatch(tmp_path):
    combined = [{"dialog": [{"speaker": "supporter", "content": "You are doing great."}]}]
    card1 = _card("rs_src_" + "1" * 24, "esconv_0000", 0, "You are doing great.")
    results_path = tmp_path / "results.jsonl"
    compiler = _FakeCompiler([1])
    run_source_card_prefix(
        cards=(card1,), esconv_data=combined, compiler=compiler,
        maximum_cards=1, preceding_turns=6, run_scope="full",
        results_path=results_path, report_path=tmp_path / "report.json",
    )
    # A different card at the same prefix position must be rejected.
    different_card = _card("rs_src_" + "9" * 24, "esconv_0000", 0, "You are doing great.")
    with pytest.raises(RuntimeError, match="not the exact ordered prefix"):
        run_source_card_prefix(
            cards=(different_card,), esconv_data=combined, compiler=compiler,
            maximum_cards=1, preceding_turns=6, run_scope="full",
            results_path=results_path, report_path=tmp_path / "report.json",
        )


def test_resume_fails_closed_when_compiler_identity_changed(tmp_path):
    # P0-5 regression: a prompt/model/renderer edit must not silently keep
    # stale results, even for rows with zero accepted units (no internal
    # accepted-unit hash to fall back on).
    combined = [{"dialog": [{"speaker": "supporter", "content": "You are doing great."}]}]
    card1 = _card("rs_src_" + "1" * 24, "esconv_0000", 0, "You are doing great.")
    results_path = tmp_path / "results.jsonl"
    compiler_v1 = _FakeCompiler([0], run_identity="identity-a")
    run_source_card_prefix(
        cards=(card1,), esconv_data=combined, compiler=compiler_v1,
        maximum_cards=1, preceding_turns=6, run_scope="full",
        results_path=results_path, report_path=tmp_path / "report.json",
    )
    compiler_v2 = _FakeCompiler([0], run_identity="identity-b-after-prompt-edit")
    with pytest.raises(RuntimeError, match="different compiler/prompt/schema/renderer"):
        run_source_card_prefix(
            cards=(card1,), esconv_data=combined, compiler=compiler_v2,
            maximum_cards=1, preceding_turns=6, run_scope="full",
            results_path=results_path, report_path=tmp_path / "report.json",
        )


def test_resume_fails_closed_when_run_scope_changed(tmp_path):
    combined = [
        {"dialog": [{"speaker": "supporter", "content": "You are doing great."}]},
        {"dialog": [{"speaker": "supporter", "content": "That sounds hard."}]},
    ]
    card1 = _card("rs_src_" + "1" * 24, "esconv_0000", 0, "You are doing great.")
    card2 = _card("rs_src_" + "2" * 24, "esconv_0001", 0, "That sounds hard.")
    results_path = tmp_path / "results.jsonl"
    compiler = _FakeCompiler([0])
    run_source_card_prefix(
        cards=(card1, card2), esconv_data=combined, compiler=compiler,
        maximum_cards=1, preceding_turns=6, run_scope="smoke",
        results_path=results_path, report_path=tmp_path / "report.json",
    )
    with pytest.raises(RuntimeError, match="different compiler/prompt/schema/renderer"):
        run_source_card_prefix(
            cards=(card1, card2), esconv_data=combined, compiler=compiler,
            maximum_cards=2, preceding_turns=6, run_scope="full",
            results_path=results_path, report_path=tmp_path / "report.json",
        )


def test_resume_rejects_a_corrupted_accepted_unit_in_an_existing_row(tmp_path):
    # Regression: resume previously only counted len(accepted_units) without
    # re-validating each stored unit against the live schema -- a corrupted
    # or schema-stale blob would be silently trusted.
    combined = [{"dialog": [{"speaker": "supporter", "content": "You are doing great."}]}]
    card1 = _card("rs_src_" + "1" * 24, "esconv_0000", 0, "You are doing great.")
    results_path = tmp_path / "results.jsonl"
    compiler = _FakeCompiler([0])
    run_source_card_prefix(
        cards=(card1,), esconv_data=combined, compiler=compiler,
        maximum_cards=1, preceding_turns=6, run_scope="full",
        results_path=results_path, report_path=tmp_path / "report.json",
    )
    # Corrupt the stored row's accepted_units with a schema-invalid blob.
    rows = [json.loads(line) for line in results_path.read_text().splitlines()]
    rows[0]["accepted_units"] = [{"not": "a valid AcceptedAtomicMoveUnit"}]
    results_path.write_text("\n".join(json.dumps(r) for r in rows) + "\n")

    with pytest.raises(ValidationError):
        run_source_card_prefix(
            cards=(card1,), esconv_data=combined, compiler=compiler,
            maximum_cards=1, preceding_turns=6, run_scope="full",
            results_path=results_path, report_path=tmp_path / "report.json",
        )
