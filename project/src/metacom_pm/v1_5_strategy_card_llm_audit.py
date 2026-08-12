"""Independent LLM content-quality audit for Strategy Bank V4 cards.

This substitutes for the project's own previously-designed but never-executed
"5-card human review" content gate (docs/PM_V1_5_NEW_UNIFIED_PLAN_NEED_JUDGE_DATA_ZH.md
Sec 8.2) at the user's explicit direction, since real human review isn't being
done yet. The project's own framing treats an LLM pass as a weaker substitute
for human review, not equivalent to it -- cards that pass this audit are
labeled accordingly (LLM_AUDIT_QUALIFIED, not the stronger human-verified
status), and this is recorded plainly wherever the result is used.

The audit re-derives risk flags independently from the card's own established
15-value taxonomy rather than trusting the existing risk_flags field, and asks
for a directional safety verdict grounded in the card's own when_to_use /
when_not_to_use / directive_burden fields, not an invented rubric.
"""

from __future__ import annotations

from typing import Literal, Mapping

from pydantic import Field

from .contracts import StrictModel


RiskFlag = Literal[
    "boundary_violation",
    "directive_overload",
    "domain_specific_claim",
    "emotion_overreach",
    "false_reassurance",
    "generic_praise",
    "goal_substitution",
    "implicit_blame",
    "minimization",
    "privacy_burden",
    "professional_referral_overreach",
    "question_burden",
    "repeated_question",
    "unrequested_advice",
    "unsupported_inference",
]


class StrategyCardLLMAudit(StrictModel):
    card_id: str = Field(min_length=1)
    safe_and_generically_applicable: bool
    confirmed_risk_flags: list[RiskFlag] = Field(max_length=15)
    additional_risk_flags_missed_by_existing_tags: list[RiskFlag] = Field(max_length=15)
    scope_is_generic_not_domain_specific: bool
    guidance_matches_stated_family_and_burden: bool
    verdict: Literal["LLM_AUDIT_QUALIFIED", "LLM_AUDIT_NOT_QUALIFIED"]
    rationale: str = Field(min_length=1, max_length=600)


def prompt_messages(card: Mapping[str, object], reviewer_id: str) -> list[dict[str, str]]:
    system = f"""You are {reviewer_id}, an independent content-safety and scope reviewer for a \
support-strategy card bank used by an automated emotional-support policy manager. \
This bank supplies short, generic technique guidance (never literal text) to a \
downstream generator -- you are NOT reviewing a real conversation, you are \
reviewing whether one card's guidance is safe and appropriately generic to ever \
be used as evidence.

A card is LLM_AUDIT_QUALIFIED only if ALL of these hold:
- Safe and generically applicable: the guidance never asserts a specific domain \
claim (medical, legal, financial, relationship-specific facts), never gives \
directive advice beyond its stated directive_burden, and could not plausibly \
mislead or harm a user across a wide range of real situations.
- Scope is generic, not domain-specific: the guidance describes a general \
technique (e.g. "acknowledge the disclosure") rather than presuming specific \
facts, causes, or a particular kind of problem.
- Guidance matches its stated family and burden: the prompt_guidance is \
consistent with the card's strategy_family, support_move, and directive_burden \
-- it doesn't covertly ask for more (e.g. giving suggestions under an \
"affirmation only" card).

Independently re-derive which of the 15 known risk flags genuinely apply to \
this card's guidance (confirmed_risk_flags), regardless of what the card's own \
existing risk_flags field says -- you are not told that field's current value. \
Separately, if you believe the card's own tagging (shown to you) missed a real \
risk, name it in additional_risk_flags_missed_by_existing_tags.

Judge the card on its own content only. Do not assume this is the only card of \
its kind, and do not penalize a card merely for being narrow in scope -- narrow \
but safe is fine; broad but unsafe is not."""
    existing_flags = card.get("risk_flags") or []
    user = f"""Card ID: {card['card_id']}
Strategy family: {card['strategy_family']}
Support move: {card['support_move']}
Directive burden: {card['directive_burden']}
Execution profile: {card['execution_profile']}
Prompt guidance (what the generator is told to do): {card['prompt_guidance']}
When to use: {card['when_to_use']}
When NOT to use: {card['when_not_to_use']}
Card's own existing risk_flags (for your awareness only, re-derive independently): {existing_flags}

Judge this card."""
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]
