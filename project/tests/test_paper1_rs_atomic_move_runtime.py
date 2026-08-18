from __future__ import annotations

from decimal import Decimal

import pytest

from metacom_pm.api import CallResult, Endpoint, chat_request_payload
from metacom_pm.io import canonical_json, sha256_text
from metacom_pm.paper1.rs_atomic_move.budget import PriceSnapshot
from metacom_pm.paper1.rs_atomic_move.contracts import (
    AtomicMoveFamily,
    ExtractorProposalBatch,
    ProposedAtomicMoveUnit,
    ProposedSpanQuote,
    SourceCardCompileInput,
    SourceTurnInput,
    VerifierDecision,
    VerifierDecisionBatch,
    VerifierRejectionReason,
)
from metacom_pm.paper1.rs_atomic_move.runtime import (
    CallParameters,
    RsAtomicMoveCompiler,
    RuntimeBinding,
)


def _endpoint() -> Endpoint:
    return Endpoint(
        base_url="https://example.invalid/compatible-mode/v1",
        model="qwen3-235b-a22b-instruct-2507",
        api_key_env="NEVER_READ_IN_OFFLINE_TEST",
        transport="openai_chat_completions",
        supports_strict_json_schema=False,
        enable_thinking=False,
    )


def _binding() -> RuntimeBinding:
    return RuntimeBinding(
        region="test-region",
        endpoint=_endpoint(),
        extractor=CallParameters(max_tokens=200, maximum_prompt_tokens=500),
        verifier=CallParameters(max_tokens=200, maximum_prompt_tokens=500),
    )


def _price() -> PriceSnapshot:
    return PriceSnapshot(
        snapshot_id="test-price",
        provider="Alibaba Cloud Model Studio",
        region="test-region",
        currency="USD",
        input_usd_per_million_tokens=Decimal("0.01"),
        output_usd_per_million_tokens=Decimal("0.01"),
    )


class FakeClient:
    def __init__(self, endpoint: Endpoint, outputs: list[object]) -> None:
        self.endpoint = endpoint
        self.outputs = list(outputs)
        self.calls = 0

    def chat(self, messages, *, temperature, max_tokens, seed, response_schema, retries):
        assert retries == 1
        supplied = self.outputs.pop(0)
        parsed = response_schema.model_validate(supplied.model_dump(mode="json"))
        payload = chat_request_payload(
            self.endpoint, messages, temperature=temperature, max_tokens=max_tokens,
            seed=seed, response_schema=response_schema,
        )
        self.calls += 1
        return (
            CallResult(
                text=canonical_json(parsed.model_dump(mode="json")),
                raw_response={"call": self.calls},
                usage={"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30},
                latency_ms=1.0,
                request_hash=sha256_text(canonical_json(payload)),
                provider_finish_reason="stop",
                normalized_finish_reason="complete",
                structured_output_audit={"initially_valid_json": True},
            ),
            parsed,
        )


def _compiler(tmp_path, client: FakeClient) -> RsAtomicMoveCompiler:
    return RsAtomicMoveCompiler(
        binding=_binding(),
        price=_price(),
        client=client,
        cache_root=tmp_path / "cache",
        attempt_ledger_root=tmp_path / "attempts",
        budget_ledger_path=tmp_path / "budget.jsonl",
        hard_budget_usd=Decimal("1.00"),
    )


SUPPORTER_TEXT = (
    "I'm sorry your manager did that. You really stepped up. "
    "Maybe you could start by updating your resume."
)
SEEKER_PRECEDING_TEXT = "My manager took credit for my work again."


def _source(target_dialogue_id: str = "esconv_0042", source_card_id: str | None = None) -> SourceCardCompileInput:
    return SourceCardCompileInput(
        source_card_id=source_card_id or "rs_src_" + "0" * 24,
        target_dialogue_id=target_dialogue_id,
        target_turn_index=5,
        preceding_turns=(
            SourceTurnInput(
                source_dialogue_id=target_dialogue_id, turn_index=4, role="seeker",
                text=SEEKER_PRECEDING_TEXT,
            ),
        ),
        target_turn=SourceTurnInput(
            source_dialogue_id=target_dialogue_id, turn_index=5, role="supporter",
            text=SUPPORTER_TEXT,
        ),
    )


def _quote(text: str, span_id: str = "s1") -> ProposedSpanQuote:
    return ProposedSpanQuote(span_id=span_id, exact_text=text)


def test_single_accepted_atomic_move(tmp_path):
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))
    verifier = VerifierDecisionBatch(decisions=(VerifierDecision(proposal_id="p1", accept=True),))

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier]))
    result = compiler.compile_source_card(_source())

    assert result.extractor_proposal_count == 1
    assert len(result.accepted_units) == 1
    unit = result.accepted_units[0]
    assert unit.atomic_move_family is AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE
    assert unit.source_dialogue_ids == ("esconv_0042",)
    # supporting_spans on the accepted unit are locally located, offset-bearing.
    span = unit.supporting_spans[0]
    assert span.source_dialogue_id == "esconv_0042"
    assert span.source_turn_index == 5
    assert SUPPORTER_TEXT[span.start_char : span.end_char] == span.exact_text
    assert result.verifier_rejections == 0
    assert result.structurally_invalid_proposals == 0


def test_multi_action_split_produces_two_independent_cards(tmp_path):
    reassurance = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
    )
    suggestion = ProposedAtomicMoveUnit(
        proposal_id="p2",
        atomic_move_family=AtomicMoveFamily.PROVIDING_SUGGESTIONS,
        action_description="suggest one small, bounded next step the user could take",
        supporting_spans=(_quote("Maybe you could start by updating your resume."),),
    )
    extractor = ExtractorProposalBatch(proposals=(reassurance, suggestion))
    verifier = VerifierDecisionBatch(
        decisions=(
            VerifierDecision(proposal_id="p1", accept=True),
            VerifierDecision(proposal_id="p2", accept=True),
        )
    )

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier]))
    result = compiler.compile_source_card(_source())

    assert len(result.accepted_units) == 2
    families = {u.atomic_move_family for u in result.accepted_units}
    assert families == {AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE, AtomicMoveFamily.PROVIDING_SUGGESTIONS}
    card_ids = {u.card_id for u in result.accepted_units}
    assert len(card_ids) == 2


def test_grounding_rejects_before_reaching_verifier(tmp_path):
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="x",
        supporting_spans=(_quote("this text does not appear in the source turn"),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor]))
    result = compiler.compile_source_card(_source())

    assert result.accepted_units == ()
    assert result.structurally_invalid_proposals == 1
    assert VerifierRejectionReason.AMBIGUOUS_SPAN in result.grounding_rejections[0].reasons


def test_seeker_grounded_proposal_is_rejected_before_reaching_verifier(tmp_path):
    # P0-2 end-to-end regression, now structural: a quote that exists only
    # in the seeker's preceding turn cannot be located inside the target
    # (supporter) turn's own text at all, so this never even reaches the
    # verifier, let alone gets accepted.
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.PROVIDING_SUGGESTIONS,
        action_description="suggest confronting the manager",
        supporting_spans=(_quote(SEEKER_PRECEDING_TEXT),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor]))
    result = compiler.compile_source_card(_source())

    assert result.accepted_units == ()
    assert result.structurally_invalid_proposals == 1
    assert VerifierRejectionReason.AMBIGUOUS_SPAN in result.grounding_rejections[0].reasons


def test_leaking_action_description_is_rejected_before_reaching_verifier(tmp_path):
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate that talking to HR was hard",  # leaks "HR"
        supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor]))
    result = compiler.compile_source_card(_source())

    assert result.accepted_units == ()
    assert VerifierRejectionReason.LEAKED_SOURCE_SPECIFIC_CONTENT in result.grounding_rejections[0].reasons


def test_verifier_rejection_excludes_the_proposal(tmp_path):
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))
    verifier = VerifierDecisionBatch(
        decisions=(
            VerifierDecision(
                proposal_id="p1", accept=False,
                rejection_reason=VerifierRejectionReason.WRONG_FAMILY,
            ),
        )
    )

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier]))
    result = compiler.compile_source_card(_source())

    assert result.accepted_units == ()
    assert result.verifier_rejections == 1


def test_verifier_missing_decision_for_grounded_proposal_fails_closed(tmp_path):
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))
    verifier = VerifierDecisionBatch(decisions=())  # no decision for p1

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier]))
    with pytest.raises(RuntimeError, match="did not decide grounded proposal_id"):
        compiler.compile_source_card(_source())


def test_verifier_extra_decision_for_unsent_proposal_fails_closed(tmp_path):
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))
    verifier = VerifierDecisionBatch(
        decisions=(
            VerifierDecision(proposal_id="p1", accept=True),
            VerifierDecision(proposal_id="p99", accept=True),  # never sent
        )
    )

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier]))
    with pytest.raises(RuntimeError, match="never sent"):
        compiler.compile_source_card(_source())


def test_card_id_does_not_collide_across_different_source_cards_with_same_proposal_id(tmp_path):
    # P0-1 regression: Qwen commonly reuses generic proposal_ids like "p1"
    # across independent extractor calls. card_id must be content-addressed
    # (source card + structured content), not derived from proposal_id alone.
    def make(action: str) -> tuple:
        proposal = ProposedAtomicMoveUnit(
            proposal_id="p1",  # deliberately identical across both cards
            atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
            action_description=action,
            supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
        )
        extractor = ExtractorProposalBatch(proposals=(proposal,))
        verifier = VerifierDecisionBatch(decisions=(VerifierDecision(proposal_id="p1", accept=True),))
        return extractor, verifier

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), []))

    extractor1, verifier1 = make("validate frustration")
    compiler.client.outputs = [extractor1, verifier1]
    result1 = compiler.compile_source_card(
        _source(target_dialogue_id="esconv_0042", source_card_id="rs_src_" + "1" * 24)
    )

    extractor2, verifier2 = make("acknowledge effort")
    compiler.client.outputs = [extractor2, verifier2]
    result2 = compiler.compile_source_card(
        _source(target_dialogue_id="esconv_0099", source_card_id="rs_src_" + "2" * 24)
    )

    assert result1.accepted_units[0].card_id != result2.accepted_units[0].card_id


def test_accepted_unit_source_dialogue_ids_is_the_target_dialogue_baseline(tmp_path):
    proposal = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(_quote("I'm sorry your manager did that. You really stepped up."),),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal,))
    verifier = VerifierDecisionBatch(decisions=(VerifierDecision(proposal_id="p1", accept=True),))

    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier]))
    result = compiler.compile_source_card(_source())

    from metacom_pm.paper1.rs_atomic_move.contracts import fold_exclusion_dialogue_ids
    ids = fold_exclusion_dialogue_ids(result.accepted_units[0])
    assert ids == frozenset({"esconv_0042"})


def test_run_identity_changes_when_max_tokens_changes(tmp_path):
    binding_a = RuntimeBinding(
        region="test-region", endpoint=_endpoint(),
        extractor=CallParameters(max_tokens=200, maximum_prompt_tokens=500),
        verifier=CallParameters(max_tokens=200, maximum_prompt_tokens=500),
    )
    binding_b = RuntimeBinding(
        region="test-region", endpoint=_endpoint(),
        extractor=CallParameters(max_tokens=99999, maximum_prompt_tokens=500),
        verifier=CallParameters(max_tokens=200, maximum_prompt_tokens=500),
    )
    compiler_a = RsAtomicMoveCompiler(
        binding=binding_a, price=_price(), client=FakeClient(_endpoint(), []),
        cache_root=tmp_path / "ca", attempt_ledger_root=tmp_path / "aa",
        budget_ledger_path=tmp_path / "ba.jsonl", hard_budget_usd=Decimal("1.00"),
    )
    compiler_b = RsAtomicMoveCompiler(
        binding=binding_b, price=_price(), client=FakeClient(_endpoint(), []),
        cache_root=tmp_path / "cb", attempt_ledger_root=tmp_path / "ab",
        budget_ledger_path=tmp_path / "bb.jsonl", hard_budget_usd=Decimal("1.00"),
    )
    assert compiler_a.run_identity_sha256 != compiler_b.run_identity_sha256


def test_run_manifest_is_auditable_not_only_an_opaque_hash(tmp_path):
    compiler = _compiler(tmp_path, FakeClient(_endpoint(), []))
    manifest = compiler.run_manifest
    assert manifest["extractor_call_parameters"]["max_tokens"] == 200
    assert "grounding_version" in manifest
    assert "contracts_code_sha256" in manifest
    assert "source_adapter_code_sha256" in manifest


def test_duplicate_semantic_content_within_one_source_card_is_deduplicated(tmp_path):
    quote = _quote("I'm sorry your manager did that. You really stepped up.")
    proposal_a = ProposedAtomicMoveUnit(
        proposal_id="p1",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(quote,),
    )
    proposal_b = ProposedAtomicMoveUnit(
        proposal_id="p2",
        atomic_move_family=AtomicMoveFamily.AFFIRMATION_AND_REASSURANCE,
        action_description="validate the user's frustration",
        supporting_spans=(quote,),
    )
    extractor = ExtractorProposalBatch(proposals=(proposal_a, proposal_b))
    verifier = VerifierDecisionBatch(
        decisions=(
            VerifierDecision(proposal_id="p1", accept=True),
            VerifierDecision(proposal_id="p2", accept=True),
        )
    )
    compiler = _compiler(tmp_path, FakeClient(_endpoint(), [extractor, verifier]))
    result = compiler.compile_source_card(_source())

    assert len(result.accepted_units) == 1
    assert result.duplicate_semantic_content_count == 1
