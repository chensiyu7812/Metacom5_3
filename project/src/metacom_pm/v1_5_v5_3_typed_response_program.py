"""V5.3 Step2: typed response program, replacing V5.2's clause-append composer.

V5.2's ``base_generation_messages`` (v1_5_v5_2_locked_composer.py) never shows
MP/MS/ME content to the generator; ``compose_locked_response`` string-appends
``locked_clauses`` after generation. That guarantees the resource text cannot
be rewritten, but also guarantees the generator cannot absorb, select,
bridge, or organize a reply around the resource -- diagnosed as the primary
V5.2 architecture failure (global failure ledger V15-ARCH-31), and confirmed
directly in real E7 grounding-risk data: 11 of 37 independent-overlap risk
items have V5.2's exact backend clause boilerplate ("An earlier session
recorded...", "I am keeping that as past context...", "You previously
said...", "...on record is...") pasted verbatim into the user-visible reply,
and this happens in 0 of the 22 items with no MS/ME/MP evidence block.

V5.3 instead compiles a machine-auditable *typed response program* per
execution candidate (current_goal, allowed reply actions, owner/time/source/
evidence_id/literal_evidence, required_contribution, epistemic_mode,
forbidden_inferences, atomic move budget, visible style constraints, and a
``cannot_integrate`` reason when no natural use exists). The generator reads
this program plus the literal evidence and must return one natural reply
*and* which evidence IDs it actually used, as a single structured response
(not free text with an appended trace line -- fragile to parse and an extra
leak surface). The final user-visible reply is never
``primary_response + locked_clauses``.

This module only builds and structurally validates the program and the
generator request/response contract. It does not call any generator; that is
wired in a separate execution script, mirroring how v1_5_v5_2_locked_composer
is consumed by the (separate) V5.2 execution scripts.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Literal, Mapping

from .v1_5_typed_resource_adapter import TypedResourceCandidate
from .v1_5b_policy_runtime import COMPONENTS, Component, action_component_bits


def _clean(value: str) -> str:
    return " ".join(str(value or "").split())


EpistemicMode = Literal[
    "current_fact", "past_fact", "unverified_continuity", "defeasible_analogy"
]

# Per plan section 2.4's fixed component execution semantics.
_REQUIRED_CONTRIBUTION_BY_COMPONENT: Mapping[str, str] = {
    "MP_PREFERENCE": (
        "change the response's phrasing/format/burden to match the preference; "
        "never read the preference back to the user as a rule"
    ),
    "MP_PROFILE": (
        "actually change the scope, timing, or burden of what is suggested; "
        "omit if the constraint has no object in this reply"
    ),
    "MS": (
        "carry forward one specific prior goal or observation as a naturally "
        "sourced past reference, with a falsifiable opening for whether it "
        "still applies now"
    ),
    "ME": (
        "offer a specific past action-and-result as one declinable option; "
        "never escalate a single past outcome into a rule or guarantee"
    ),
    "RS": "complete exactly one atomic support move, with no appended second task",
}

_EPISTEMIC_MODE_BY_COMPONENT: Mapping[str, EpistemicMode] = {
    "MP_PREFERENCE": "current_fact",
    "MP_PROFILE": "current_fact",
    "MS": "unverified_continuity",
    "ME": "defeasible_analogy",
    "RS": "current_fact",
}

_FORBIDDEN_INFERENCES: tuple[str, ...] = (
    "current_cause",
    "stable_personality_trait",
    "unmentioned_third_party",
    "diagnosis",
    "outcome_guarantee",
)


@dataclass(frozen=True)
class ExecutionEvidence:
    component: str
    evidence_id: str
    owner_id: str | None
    source_kind: str
    strictly_prior: bool
    age_sessions: int | None
    literal_evidence: str
    epistemic_mode: EpistemicMode
    required_contribution: str
    usage_boundary: str = ""


@dataclass(frozen=True)
class TypedResponseProgram:
    requested_action_id: str
    current_goal: str
    allowed_reply_actions: tuple[str, ...]
    evidence: tuple[ExecutionEvidence, ...]
    forbidden_inferences: tuple[str, ...]
    atomic_move_budget: int
    maximum_burden: int
    visible_style_constraints: tuple[str, ...]
    cannot_integrate_reason: str | None = field(default=None)

    @property
    def is_m0(self) -> bool:
        return not self.evidence and self.cannot_integrate_reason is None and self.requested_action_id == "M0+R0"


def _literal_evidence_for(candidate: TypedResourceCandidate) -> str:
    if candidate.component == "MP":
        return _clean(candidate.preference or candidate.profile_fact)
    if candidate.component == "MS":
        return _clean(candidate.prior_observation)
    if candidate.component == "ME":
        # past_action/observed_outcome are the fields TypedResourceCandidate
        # actually requires and validates for ME_REUSABLE_OUTCOME; the
        # optional ``mechanism`` field is a V5.2-specific "literal_span:"
        # provenance convention for that architecture's own clause builder
        # and must not be reused as if it were the required evidence text.
        return _clean(f"{candidate.past_action} {candidate.observed_outcome}")
    if candidate.component == "RS":
        return _clean(candidate.support_move)
    raise ValueError(f"unsupported component: {candidate.component}")


def _usage_boundary_for(candidate: TypedResourceCandidate) -> str:
    if candidate.component == "RS":
        return _clean(f"use when: {candidate.when_to_use} | do not use when: {candidate.when_not_to_use}")
    return ""


def _evidence_key(candidate: TypedResourceCandidate) -> str:
    return candidate.subtype if candidate.component == "MP" else candidate.component


def build_typed_response_program(
    *,
    requested_action_id: str,
    current_goal: str,
    current_user_id: str,
    candidates: Mapping[str, TypedResourceCandidate],
    cannot_integrate_reason: str | None = None,
    expected_execution_candidate_ids: Mapping[str, str] | None = None,
) -> TypedResponseProgram:
    if not _clean(current_goal):
        raise ValueError("current_goal must be non-empty")
    if not _clean(current_user_id):
        raise ValueError("current_user_id must be non-empty")

    requested_bits: Mapping[Component, bool] = action_component_bits(requested_action_id)
    requested_components = {c for c in COMPONENTS if requested_bits[c]}
    if requested_components != set(candidates):
        raise ValueError(
            f"requested_action_id {requested_action_id!r} implies components "
            f"{sorted(requested_components)} but candidates provided {sorted(candidates)}"
        )

    evidence: list[ExecutionEvidence] = []
    for component in COMPONENTS:
        candidate = candidates.get(component)
        if candidate is None:
            continue
        if candidate.component != component:
            raise ValueError(f"candidate under key {component!r} has component {candidate.component!r}")
        if component == "RS":
            if candidate.owner_id is not None:
                raise ValueError("RS candidates must not carry a user owner_id")
        elif candidate.owner_id != current_user_id:
            raise ValueError(
                f"{component} candidate owner_id {candidate.owner_id!r} does not match "
                f"current_user_id {current_user_id!r}"
            )
        if expected_execution_candidate_ids is not None:
            expected_id = expected_execution_candidate_ids.get(component)
            if expected_id is not None and expected_id != candidate.resource_id:
                raise ValueError(
                    f"{component} candidate resource_id {candidate.resource_id!r} does not match "
                    f"the exact Rank-1 execution candidate id {expected_id!r}"
                )
        key = _evidence_key(candidate)
        if key not in _REQUIRED_CONTRIBUTION_BY_COMPONENT:
            raise ValueError(f"unsupported candidate key: {key}")
        evidence.append(
            ExecutionEvidence(
                component=component,
                evidence_id=candidate.resource_id,
                owner_id=candidate.owner_id,
                source_kind=candidate.source_kind,
                strictly_prior=candidate.strictly_prior,
                age_sessions=candidate.age_sessions,
                literal_evidence=_literal_evidence_for(candidate),
                epistemic_mode=_EPISTEMIC_MODE_BY_COMPONENT[key],
                required_contribution=_REQUIRED_CONTRIBUTION_BY_COMPONENT[key],
                usage_boundary=_usage_boundary_for(candidate),
            )
        )
    if any(not item.literal_evidence for item in evidence):
        raise ValueError("compiled empty literal_evidence for at least one candidate")

    atomic_budget = 1 if "RS" in candidates else 0
    return TypedResponseProgram(
        requested_action_id=requested_action_id,
        current_goal=_clean(current_goal),
        allowed_reply_actions=("respond",) if not cannot_integrate_reason else ("m0_fallback",),
        evidence=tuple(evidence),
        forbidden_inferences=_FORBIDDEN_INFERENCES,
        atomic_move_budget=atomic_budget,
        maximum_burden=1,
        visible_style_constraints=(
            "concise",
            "no internal labels, resource IDs, or field names",
            "no verbatim record-log phrasing",
        ),
        cannot_integrate_reason=cannot_integrate_reason,
    )


@dataclass(frozen=True)
class GeneratorResponse:
    """The generator's single structured output (e.g. via a JSON-schema
    constrained provider response_schema, not free text with an appended
    trace line -- see the module docstring for why the free-text form was
    replaced)."""

    reply: str
    used_evidence_ids: tuple[str, ...]
    realized_response_act: str


def parse_generator_response_dict(raw: Mapping[str, object]) -> GeneratorResponse:
    reply = raw.get("reply")
    used_ids = raw.get("used_evidence_ids")
    act = raw.get("realized_response_act")
    if not isinstance(reply, str) or not isinstance(act, str):
        raise ValueError("generator response missing reply/realized_response_act strings")
    if not isinstance(used_ids, (list, tuple)) or not all(isinstance(i, str) for i in used_ids):
        raise ValueError("generator response used_evidence_ids must be a list of strings")
    return GeneratorResponse(
        reply=_clean(reply), used_evidence_ids=tuple(used_ids), realized_response_act=_clean(act)
    )


def evidence_aware_generation_messages(
    *, current_context: str, program: TypedResponseProgram
) -> list[dict[str, str]]:
    """Build the generator request.

    2026-08-06: a real live test (10 real states, real NVIDIA-hosted
    Llama-3.1-8B-Instruct calls) found 5/10 replies presented the user's own
    evidence in first person as the assistant's own experience -- one
    fabricated a spouse and child that belong to the user. The worst case's
    evidence was clean third person ("Emily is feeling..."), so this is not
    just "the model continued a quoted I" -- it is a narrator-identity
    collapse the previous prompt never addressed. ExecutionEvidence already
    carried owner_id (the real user id for MP/MS/ME, None for RS), but this
    function never rendered it into the request at all, so the generator had
    no signal whatsoever about whose facts these were. The fix below is
    deliberately the minimal, already-available-data version of a claim
    ownership tag (render owner_id, do not invent a new predicate/object
    extraction layer -- see PM_V1_5_V5_3_STEP2_LIVE_TEST_FINDINGS_
    20260806_ZH.md for why a full semantic Claim IR is a separate, harder,
    not-yet-justified investment). Evidence also moves into the system
    message, separated from current_context, so it reads as background the
    assistant knows rather than more things the user just said in this turn.
    """

    if not _clean(current_context):
        raise ValueError("current_context must be non-empty")
    if program.cannot_integrate_reason is not None:
        raise ValueError("cannot_integrate programs must not be sent to the generator")
    system_lines = [
        f"Current goal: {program.current_goal}",
        "You are the assistant responding to the user. You are not the user and you are not "
        "role-playing the user.",
        "Write one natural, coherent reply that genuinely incorporates every evidence item "
        "below; every item listed has already been confirmed to have a natural use in this "
        "reply, so use all of them.",
        "Every evidence item below with an owner describes THAT PERSON's own fact, "
        "statement, or past experience -- never yours, regardless of whether its literal "
        "wording is first person, third person, or a name. Always address it to that person "
        "as \"you/your\". Never claim their spouse, child, job, education, relationship, "
        "decision, emotion, or past action as your own experience or biography.",
        "You may use first person only to describe your own present conversational act "
        "(e.g. \"I hear you\", \"I'm sorry\", \"I want to understand\"), never to narrate a "
        "personal life event, relationship, or biography.",
        "Forbidden: inventing a current cause, a stable personality trait, an unmentioned "
        "third party, a diagnosis, or an outcome guarantee.",
        "Forbidden in the visible reply: internal labels (MP/MS/ME/RS), resource IDs, field "
        "names, or verbatim record-log phrasing that sounds like a system note.",
        f"Atomic support-move budget: {program.atomic_move_budget}. Do not exceed it.",
        "Return the required structured response: reply, used_evidence_ids, realized_response_act.",
    ]
    evidence_lines: list[str] = []
    for item in program.evidence:
        tentativeness = (
            "state this tentatively and leave room for it to no longer apply"
            if item.epistemic_mode == "unverified_continuity"
            else "offer this as one declinable option, not a rule"
            if item.epistemic_mode == "defeasible_analogy"
            else "this is presently true"
        )
        boundary = f" -- boundary: {item.usage_boundary}" if item.usage_boundary else ""
        owner = (
            f"owner=the person you are talking to (address as you/your)"
            if item.owner_id
            else "owner=none (a permitted support move, not a personal fact)"
        )
        evidence_lines.append(
            f"- evidence_id={item.evidence_id} component={item.component} {owner} "
            f"epistemic_mode={item.epistemic_mode} ({tentativeness}): "
            f'"{item.literal_evidence}" -- required contribution: {item.required_contribution}{boundary}'
        )
    if evidence_lines:
        system_lines.append(
            "Background facts the assistant already knows (not things the user is currently "
            "saying in this turn):\n" + "\n".join(evidence_lines)
        )
    return [
        {"role": "system", "content": " ".join(system_lines)},
        {"role": "user", "content": _clean(current_context)},
    ]


_INTERNAL_ID_RE = re.compile(r"(?:mem|strat|card)_[0-9a-f]{8,}", re.IGNORECASE)
_INTERNAL_LABEL_RE = re.compile(r"\b(?:MP|MS|ME|RS|M0|R0)\b")

# Derived directly from v1_5_v5_2_locked_composer.py's own fixed clause
# templates (the exact source of the leak, confirmed against real E7
# grounding-risk data: 11/37 independent-overlap items reproduce these
# fragments verbatim, 0/37 non-evidence items ever do), not from a handful
# of examples noticed by inspection.
_RECORD_LOG_PHRASE_RE = re.compile(
    r"an earlier session recorded"
    r"|i am keeping (?:that|this) as past context"
    r"|you previously said"
    r"|that past result (?:may be a reason not to repeat|can be one optional starting point)"
    r"|(?:on record| on record is)\b"
    r"|i will keep the response within that constraint"
    r"|\bthe seeker\b",
    re.IGNORECASE,
)


def typed_response_guard_errors(
    *, response: GeneratorResponse, program: TypedResponseProgram
) -> tuple[str, ...]:
    """Machine-checkable structural/binding errors only.

    Whether a used evidence item is stale, conflicting, overgeneralized, or
    imposes unwarranted meaning is a semantic question for the independent
    grounding-risk review, not this guard (plan section 2.5).
    """

    cleaned = _clean(response.reply)
    errors: list[str] = []
    if not cleaned:
        return ("EMPTY_RESPONSE",)
    if _INTERNAL_ID_RE.search(cleaned) or _INTERNAL_LABEL_RE.search(cleaned):
        errors.append("INTERNAL_LABEL_OR_ID_LEAK")
    if _RECORD_LOG_PHRASE_RE.search(cleaned):
        errors.append("RECORD_LOG_PHRASING_LEAK")
    authorized_ids = {item.evidence_id for item in program.evidence}
    used_ids = set(response.used_evidence_ids)
    unauthorized = used_ids - authorized_ids
    if unauthorized:
        errors.append("TRACE_REFERENCES_UNAUTHORIZED_EVIDENCE_ID")
    # Every evidence item in a program was already confirmed (pre-generation,
    # by whatever built cannot_integrate/the program itself) to have a
    # natural use; the generator is not given discretion to silently skip
    # one. A gap here is a real Step2 nonuse event, not a quiet pass.
    missing = authorized_ids - used_ids
    if missing:
        errors.append("REQUIRED_EVIDENCE_NOT_USED")
    if len(response.used_evidence_ids) != len(set(response.used_evidence_ids)):
        errors.append("DUPLICATE_EVIDENCE_ID_IN_TRACE")
    return tuple(errors)


# Heuristic only -- calibrated against the 10 real replies from the
# 2026-08-06 live test (5 confirmed violations, 1 mixed, 4 clean; see
# PM_V1_5_V5_3_STEP2_LIVE_TEST_FINDINGS_20260806_ZH.md), NOT a complete
# semantic check. Two signals, checked independently:
# (a) a direct first-person possessive over a biographical noun ("my
#     husband", "my college degree" -- up to two words of adjective/modifier
#     tolerated between the possessive and the noun); catches p7/p10's
#     clearest cases.
# (b) within a single sentence, a sustained-personal-reflection verb phrase
#     ("I've been thinking/weighing/considering/...") co-occurring with a
#     first-person possessive ("my"/"our") anywhere in that sentence --
#     catches p9/p13's paraphrased narrative-voice cases, which have no
#     single forbidden noun.
# Recall on the 10-reply calibration set: 3/3 direct-noun cases caught, plus
# the two narrative cases this second signal was added for. This will still
# miss cases with neither signal -- treat a pass as "no obvious violation",
# not proof of correct attribution. Independent human review on a fresh
# sample is still required before trusting an aggregate pass rate.
_FIRST_PERSON_BIOGRAPHICAL_NOUN_RE = re.compile(
    r"\b(?:my|our)\b(?:\s+\w+){0,2}\s+(?:husband|wife|spouse|partner|"
    r"ex[- ]?(?:boyfriend|girlfriend|partner|husband|wife)|son|daughter|"
    r"child|kids?|mother|father|mom|dad|family|job|career|degree|boss|"
    r"supervisor|manager|therapist|doctor|diagnosis|illness|pregnancy)\b"
    r"|\bas a (?:business owner|graduate student|freelancer|software engineer|"
    r"project manager|office worker)\b",
    re.IGNORECASE,
)
_PERSONAL_REFLECTION_VERB_RE = re.compile(
    r"\bi(?:'ve| have)?(?:\s+been)?\s+(?:trying to|struggling with|weighing|"
    r"considering|dealing with|thinking about|working towards|facing|"
    r"navigating|balancing|reflecting on|reminded of)\b",
    re.IGNORECASE,
)
_MY_OUR_POSSESSIVE_RE = re.compile(r"\b(?:my|our)\b", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def speaker_attribution_guard_errors(*, response: GeneratorResponse) -> tuple[str, ...]:
    """Heuristic fail-fast for the assistant claiming the user's evidence as
    its own biography (see module-level 2026-08-06 note and the regex
    docstrings above). Deliberately separate from typed_response_guard_errors:
    that function is scoped to machine-checkable structural/binding errors
    only (its own docstring), and folding an incomplete heuristic into it
    would misrepresent this as a complete check.
    """

    cleaned = _clean(response.reply)
    if _FIRST_PERSON_BIOGRAPHICAL_NOUN_RE.search(cleaned):
        return ("POSSIBLE_ASSISTANT_SELF_ATTRIBUTION_OF_USER_FACT",)
    for sentence in _SENTENCE_SPLIT_RE.split(cleaned):
        if _PERSONAL_REFLECTION_VERB_RE.search(sentence) and _MY_OUR_POSSESSIVE_RE.search(sentence):
            return ("POSSIBLE_ASSISTANT_SELF_ATTRIBUTION_OF_USER_FACT",)
    return ()


_M0_FALLBACK_FAMILY: Mapping[str, str] = {
    "listen_only": "I hear you.",
    "acknowledge": "That sounds like a lot to carry.",
    "concise_reflection": "It sounds like that's been weighing on you.",
    "one_focused_question": "Can you tell me a bit more about what feels most important right now?",
    "no_history_available": "I don't have anything else on record for this -- can you fill me in?",
    "one_optional_suggestion": "One thing that sometimes helps is taking a short pause before responding.",
}


def m0_fallback_response(boundary: str = "one_focused_question") -> str:
    if boundary not in _M0_FALLBACK_FAMILY:
        raise ValueError(f"unknown M0 fallback boundary: {boundary!r}")
    return _M0_FALLBACK_FAMILY[boundary]
