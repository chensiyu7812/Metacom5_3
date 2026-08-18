"""Contracts for the RS atomic-move compiler.

This is a standalone compiler, separate from ``paper1.semantic_memory``
(MP/MS/ME). The 2026-08-17 semantic-memory-compiler amendment scopes Qwen
extractor/verifier authorization to MP/MS/ME candidate construction only; it
does not authorize RS live calls. Building this module (schema, prompts,
grounding, renderer, offline fixtures) is unscoped implementation work and
requires no new authorization. A live smoke against the real API requires
its own researcher-reviewed authorization artifact and its own budget
ledger, independent of the memory compiler's USD 5.00 cap.

Design constraints (binding, not just style):
- Qwen may extract; it may never emit a fit/burden/helpfulness/worth-
  opening/ON-OFF/confidence judgment. See
  ``PM_PAPER1_FINAL_EXECUTION_BLUEPRINT_20260816_ZH.md`` line 179:
  "不得使用人工/LLM 的 atomic_move_fit、burden_fit 等 utility-like score."
- ``atomic_move_family`` reuses the frozen 8-class ESConv strategy taxonomy
  (not a new open-ended enum) -- the semantic-memory compiler's v3 smoke
  showed a free-form subtype field collapses to ~1 unique value per unit and
  becomes unusable as a census/feature ontology; this compiler must not
  repeat that mistake.
- Final card text is never Qwen's raw prose beyond ``action_description``
  itself, and is produced by a deterministic, versioned, hash-bound
  renderer (mirrors ``semantic_memory/renderer.py``).
- Every ``ProposedAtomicMoveUnit`` proposal is anchored to exactly one
  target (dialogue_id, turn_index) -- the specific supporter turn a source
  card represents -- and this is now true *by construction*, not just by a
  check that can be forgotten. Qwen's ``supporting_spans`` are
  ``ProposedSpanQuote`` objects (``span_id`` + ``exact_text`` only, no
  location). ``grounding.py`` locates each quote exclusively inside the
  target supporter turn's own text; a preceding turn's text is never even
  searched, so a proposal grounded in what the seeker said cannot pass no
  matter what location Qwen might have claimed for it -- there is no
  location field left for Qwen to claim one in. This also fixes an earlier
  self-contradiction: the extractor prompt said "the local validator
  derives character offsets" while the schema still required Qwen to supply
  ``start_char``/``end_char`` on every span; now it structurally does not
  ask for them. The full, offset-bearing ``SupportingSpan`` is assembled
  locally (single unique match required; an absent or non-unique quote
  fails closed as a grounding rejection, never guessed) and is what
  ``AcceptedAtomicMoveUnit`` carries. Likewise Qwen does not carry a
  ``source_dialogue_ids`` field; ``AcceptedAtomicMoveUnit.source_turn_index``/
  ``source_dialogue_ids`` are assigned locally by the runtime from the
  compile input's own target identity (plus, when available, a locally-
  computed dedup-equivalence-group manifest for ``source_dialogue_ids`` --
  never taken from a model output).
- This is not "privacy redaction" in the legal-PII sense (ESConv is already
  public, anonymized data). The concern is stopping another dialogue's
  specific person/relationship/number/event from being read by the
  Generator as if it were a fact about the *current* user -- a treatment-
  validity/factual-contamination risk, not a privacy risk. Only
  ``action_description`` is ever rendered into the card text the Generator
  sees (``renderer.py``'s ``render_atomic_move``); ``supporting_spans`` are
  grounding evidence only and are never rendered. So the entire
  contamination gate lives in ``renderer.py``'s scan of
  ``action_description`` for a leaked person/kinship/number/date -- there
  is deliberately no separate Qwen-facing "delexicalized_slots" schema.
  An earlier version had Qwen propose typed redaction slots
  (``slot_type``/``replacement_placeholder``); that gave false mechanical
  confidence, since neither field was ever checked against anything (a
  proposal could label the real span "Jack" as ``date_or_time`` with
  placeholder text "Jack" and still pass). Because the evidence spans
  themselves are never rendered, checking them for leaks was solving the
  wrong problem; only ``action_description`` matters, and that already has
  a real mechanical gate.
"""

from __future__ import annotations

from enum import StrEnum
from pathlib import Path

from pydantic import Field, model_validator

from metacom_pm.io import sha256_file
from metacom_pm.paper1.contracts import StrictContract

RS_ATOMIC_MOVE_SCHEMA_VERSION = "paper1-rs-atomic-move-schema-v2"
CONTRACTS_CODE_SHA256 = sha256_file(Path(__file__))


class AtomicMoveFamily(StrEnum):
    """The frozen 8-class ESConv strategy taxonomy. Reused verbatim, not
    reinvented, so this stays a closed, already-validated enum."""

    QUESTION = "question"
    RESTATEMENT_OR_PARAPHRASING = "restatement_or_paraphrasing"
    REFLECTION_OF_FEELINGS = "reflection_of_feelings"
    SELF_DISCLOSURE = "self_disclosure"
    AFFIRMATION_AND_REASSURANCE = "affirmation_and_reassurance"
    PROVIDING_SUGGESTIONS = "providing_suggestions"
    INFORMATION = "information"
    OTHERS = "others"


class ProposedSpanQuote(StrictContract):
    """A quote Qwen claims appears in the target supporter turn. No location
    fields: ``grounding.py`` locates it (uniquely, or rejects) inside the
    target turn's own text only -- Qwen cannot claim a location, so it
    cannot claim a location in some other (e.g. seeker) turn either."""

    span_id: str = Field(min_length=1)
    exact_text: str = Field(min_length=1)


class SupportingSpan(StrictContract):
    """The locally-assembled, offset-bearing, location-verified span. Never
    constructed from Qwen's output directly -- see ``grounding.py``'s
    ``locate_span_in_target_turn``."""

    span_id: str = Field(min_length=1)
    source_dialogue_id: str = Field(pattern=r"^esconv_[0-9]{4}$")
    source_turn_index: int = Field(ge=0)
    exact_text: str = Field(min_length=1)
    start_char: int = Field(ge=0)
    end_char: int = Field(ge=0)

    @model_validator(mode="after")
    def _check_span_order(self) -> "SupportingSpan":
        if self.end_char <= self.start_char:
            raise ValueError("supporting span end_char must exceed start_char")
        return self


class ProposedAtomicMoveUnit(StrictContract):
    """Extractor output. Purely structural/factual; no utility fields exist
    in this schema, so none can be smuggled in. Neither the target turn
    identity nor which dialogue(s) a card belongs to is asserted here --
    both are checked/assigned locally against the compile input, not
    declared by Qwen. ``supporting_spans`` are unlocated quotes
    (``ProposedSpanQuote``); grounding.py locates each one, exclusively
    within the target turn, before this proposal is trusted for anything."""

    proposal_id: str = Field(min_length=1)
    atomic_move_family: AtomicMoveFamily
    action_description: str = Field(
        min_length=1,
        description=(
            "One atomic support action only, third-person, present tense, "
            "e.g. 'validate the user's frustration'. Must not describe more "
            "than one distinct action -- if the source turn both reflects a "
            "feeling and offers a suggestion, that is two proposals, not one "
            "action_description joining them with 'and' or 'before'. Must be "
            "written generically: never include a specific name, kinship/"
            "relationship term, number, date, or location from the source "
            "dialogue -- write 'validate the user's frustration', never "
            "'validate Jack's frustration about missing Tuesday's meeting'."
        ),
    )
    supporting_spans: tuple[ProposedSpanQuote, ...] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_span_ids_unique(self) -> "ProposedAtomicMoveUnit":
        ids = [s.span_id for s in self.supporting_spans]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate span_id within one proposal: {ids}")
        return self


class VerifierRejectionReason(StrEnum):
    """The full reason vocabulary used across both the deterministic
    grounding layer (``grounding.py``) and the LLM verifier. Not every value
    here is reachable from the verifier's own output schema -- see
    ``VerifierDecidableRejectionReason``."""

    MULTIPLE_DISTINCT_ACTIONS = "multiple_distinct_actions"
    UNGROUNDED_ADDITION = "ungrounded_addition"
    LEAKED_SOURCE_SPECIFIC_CONTENT = "leaked_source_specific_content"
    WRONG_FAMILY = "wrong_family"
    AMBIGUOUS_SPAN = "ambiguous_span"


class VerifierDecidableRejectionReason(StrEnum):
    """The subset of ``VerifierRejectionReason`` the LLM verifier may
    actually choose, used as ``VerifierDecision.rejection_reason``'s type so
    it appears in the JSON schema sent to the model.

    ``AMBIGUOUS_SPAN`` and ``LEAKED_SOURCE_SPECIFIC_CONTENT`` are
    deliberately excluded, not just discouraged in the prompt:

    - ``AMBIGUOUS_SPAN`` is assigned only by ``locate_spans`` (a proposal
      with an ambiguous span is filtered out by grounding before the
      verifier ever runs, so the verifier can never legitimately need it).
    - ``LEAKED_SOURCE_SPECIFIC_CONTENT`` is a live, mechanical, position-
      aware regex check on ``action_description`` (``renderer.
      leaked_source_specific_terms``, run deterministically by
      ``grounding.check_action_description_not_leaking`` before the
      verifier ever runs). Live-verified 2026-08-18 on a 64-card diverse
      smoke: after already asking the LLM verifier to judge this criterion
      with explicit PASS/REJECT examples, 6-7 of 8 sampled
      ``leaked_source_specific_content`` verifier rejections were false
      positives -- in every sampled case the verifier was reacting to
      specificity present in the cited ``supporting_spans`` (a pronoun, a
      relationship word, a named event) even though ``action_description``
      itself stayed correctly generic, exactly the failure the deterministic
      scanner does not make (it only ever reads ``action_description``).
      Asking the same model to re-judge a criterion its own deterministic
      gate already enforces added rejection noise, not additional recall,
      so this criterion is retired from the verifier's decidable set
      entirely rather than patched with more prompt examples."""

    MULTIPLE_DISTINCT_ACTIONS = "multiple_distinct_actions"
    UNGROUNDED_ADDITION = "ungrounded_addition"
    WRONG_FAMILY = "wrong_family"


class AcceptedAtomicMoveUnit(StrictContract):
    """Final accepted, source-grounded atomic move. The ``rendered_card_text``
    is produced by the deterministic renderer from ``action_description``
    alone, never from Qwen's raw prose beyond that one field;
    ``rendered_card_text_sha256`` binds it to the renderer version.
    ``source_turn_index`` and ``source_dialogue_ids`` are assigned locally
    by the runtime from the compile input's target identity, never copied
    from a Qwen-declared field."""

    card_id: str = Field(pattern=r"^rs_atomic_[0-9a-f]{24}$")
    source_dialogue_ids: tuple[str, ...] = Field(min_length=1)
    source_turn_index: int = Field(ge=0)
    atomic_move_family: AtomicMoveFamily
    action_description: str = Field(min_length=1)
    supporting_spans: tuple[SupportingSpan, ...] = Field(min_length=1)
    rendered_card_text: str = Field(min_length=1)
    rendered_card_text_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    renderer_version: str = Field(min_length=1)
    compiler_version: str = Field(min_length=1)
    extractor_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    extractor_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_prompt_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    verifier_response_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")

    @model_validator(mode="after")
    def _forbid_utility_like_fields(self) -> "AcceptedAtomicMoveUnit":
        # Defense in depth: StrictContract already forbids extra fields, so
        # a utility field could not have been attached even accidentally.
        # This validator exists so a future schema edit that adds one of
        # these names back fails loudly and immediately, not silently.
        forbidden = {
            "fit",
            "burden",
            "burden_fit",
            "atomic_move_fit",
            "helpfulness",
            "worth_opening",
            "should_open",
            "on_off",
            "confidence",
        }
        present = forbidden & set(type(self).model_fields)
        if present:
            raise ValueError(f"forbidden utility-like fields present in schema: {present}")
        return self


class SourceTurnInput(StrictContract):
    """One source dialogue turn as the extractor is allowed to see it:
    identity + exact text only. No situation/outcome/questionnaire fields
    (those are already excluded upstream by ``rs/strategy_bank.py``)."""

    source_dialogue_id: str = Field(pattern=r"^esconv_[0-9]{4}$")
    turn_index: int = Field(ge=0)
    role: str = Field(pattern=r"^(seeker|supporter)$")
    text: str = Field(min_length=1)


class SourceCardCompileInput(StrictContract):
    """The full extractor input for one supporter turn: the turn itself plus
    enough preceding visible dialogue for the action to be understood in
    context. This mirrors ``StrategySourceCard.retrieval_text`` (preceding
    turns) + ``example_response`` (the target supporter turn), already
    stripped of ``situation``/outcome fields by the source catalog.

    Cross-field-consistent by construction: ``target_turn`` must actually
    *be* the declared target (same dialogue/index, supporter role), and
    every preceding turn must be strictly earlier, in the same dialogue,
    and uniquely indexed -- callers (``source_adapter.py`` today) get this
    checked rather than silently trusted, so a future bug there fails loudly
    instead of quietly feeding grounding.py an inconsistent target."""

    source_card_id: str = Field(pattern=r"^rs_src_[0-9a-f]{24}$")
    target_dialogue_id: str = Field(pattern=r"^esconv_[0-9]{4}$")
    target_turn_index: int = Field(ge=0)
    preceding_turns: tuple[SourceTurnInput, ...]
    target_turn: SourceTurnInput

    @model_validator(mode="after")
    def _check_target_and_preceding_consistency(self) -> "SourceCardCompileInput":
        if (self.target_turn.source_dialogue_id, self.target_turn.turn_index) != (
            self.target_dialogue_id,
            self.target_turn_index,
        ):
            raise ValueError(
                "target_turn does not match the declared target_dialogue_id/target_turn_index"
            )
        if self.target_turn.role != "supporter":
            raise ValueError("target_turn must be a supporter turn")
        seen_indices: set[int] = set()
        for turn in self.preceding_turns:
            if turn.source_dialogue_id != self.target_dialogue_id:
                raise ValueError("preceding_turns must be from the same dialogue as the target")
            if turn.turn_index >= self.target_turn_index:
                raise ValueError("preceding_turns must be strictly earlier than the target turn")
            if turn.turn_index in seen_indices:
                raise ValueError("preceding_turns must have unique turn_index values")
            seen_indices.add(turn.turn_index)
        indices = [turn.turn_index for turn in self.preceding_turns]
        if indices != sorted(indices):
            raise ValueError("preceding_turns must be in ascending turn_index order")
        return self


class ExtractorProposalBatch(StrictContract):
    proposals: tuple[ProposedAtomicMoveUnit, ...] = ()

    @model_validator(mode="after")
    def _check_proposal_ids_unique(self) -> "ExtractorProposalBatch":
        ids = [p.proposal_id for p in self.proposals]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate proposal_id within one extractor batch: {ids}")
        return self


class VerifierDecision(StrictContract):
    proposal_id: str = Field(min_length=1)
    accept: bool
    rejection_reason: VerifierDecidableRejectionReason | None = None

    @model_validator(mode="after")
    def _reason_iff_rejected(self) -> "VerifierDecision":
        if self.accept and self.rejection_reason is not None:
            raise ValueError("an accepted decision must not carry a rejection_reason")
        if not self.accept and self.rejection_reason is None:
            raise ValueError("a rejected decision must carry a rejection_reason")
        return self


class VerifierDecisionBatch(StrictContract):
    decisions: tuple[VerifierDecision, ...] = ()

    @model_validator(mode="after")
    def _check_decision_ids_unique(self) -> "VerifierDecisionBatch":
        ids = [d.proposal_id for d in self.decisions]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate proposal_id decided twice in one verifier batch: {ids}")
        return self


def fold_exclusion_dialogue_ids(card: AcceptedAtomicMoveUnit) -> frozenset[str]:
    """All ESConv dialogue IDs a card is source-grounded in. A formal RS
    effect state must exclude this card from its Strategy Bank if the
    state's own current dialogue ID is in this set (leave-current-dialogue-
    out / fold-exclusive rule), regardless of how many turns were merged
    into one atomic-move card."""

    return frozenset(card.source_dialogue_ids)
