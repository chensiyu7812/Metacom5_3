"""Outcome-blind memory realization and joint composition primitives.

The PM and the retriever decide *whether* to request a component and which
catalog item is Rank-1.  They do not decide which literal fragment should be
shown to the response generator or how several requested components should
share one reply.  This module makes that missing boundary explicit.

It deliberately contains no learned threshold and reads no response outcome,
reviewer label, future turn, event graph, summary, or QA evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Literal, Mapping, Sequence

from .v1_5b_policy_runtime import COMPONENTS, action_component_bits, compile_component_bits


_SPACE = re.compile(r"\s+")
_TOKEN = re.compile(r"[a-z0-9']+")
_SEEKER_LINE = re.compile(r"^SEEKER:\s*(.+?)\s*$", re.IGNORECASE)

# This is a structural phatic/acknowledgement filter, not a semantic utility
# classifier.  A line is rejected only when it contains almost no content
# outside this small closed vocabulary.
_PHATIC = {
    "a", "alot", "bye", "goodbye", "great", "hello", "hey", "hi", "hmm",
    "i", "it", "lot", "much", "no", "ok", "okay", "really", "so", "sure",
    "thanks", "thank", "that", "the", "this", "u", "yes", "you", "your",
}


def compact(value: object) -> str:
    return _SPACE.sub(" ", str(value or "")).strip()


def normalized_tokens(text: str) -> tuple[str, ...]:
    return tuple(_TOKEN.findall(text.lower()))


def parse_raw_ms_session(raw_session_text: str) -> tuple[str, ...]:
    """Return exact seeker-turn payloads from a frozen raw-session resource."""

    turns: list[str] = []
    for raw_line in str(raw_session_text or "").splitlines():
        match = _SEEKER_LINE.match(raw_line.strip())
        if match and compact(match.group(1)):
            turns.append(compact(match.group(1)))
    return tuple(turns)


def is_low_information_turn(text: str) -> bool:
    """Reject short greetings, thanks, acknowledgements, and bare backchannels.

    The rule intentionally keeps short concrete facts such as "I lost my job"
    because ``lost`` and ``job`` are outside the closed phatic vocabulary.
    """

    tokens = normalized_tokens(text)
    if not tokens:
        return True
    content = [token for token in tokens if token not in _PHATIC]
    if len(content) >= 2:
        return False
    return len(tokens) <= 12


def current_seeker_query(visible_dialogue: Sequence[Mapping[str, object]]) -> str:
    """Build the span-selector query from currently visible seeker text only."""

    parts = [
        compact(turn.get("content"))
        for turn in visible_dialogue
        if str(turn.get("speaker") or "").lower() == "seeker"
        and compact(turn.get("content"))
    ]
    return "\n".join(parts)


@dataclass(frozen=True)
class SelectedMemorySpan:
    exact_span: str
    source_turn_index: int
    semantic_score: float
    informative_turn_count: int
    raw_turn_count: int


def select_ms_exact_span(
    raw_session_text: str,
    semantic_scores: Mapping[str, float],
) -> SelectedMemorySpan | None:
    """Choose one exact informative seeker turn using caller-supplied scores.

    ``semantic_scores`` is normally produced by the frozen BGE encoder from
    the visible seeker query to each exact prior seeker turn.  Supplying the
    scores keeps selection deterministic and makes unit testing independent
    of the model runtime.  Ties prefer the more content-bearing and then later
    source turn; no generated summary is introduced.
    """

    turns = parse_raw_ms_session(raw_session_text)
    informative = [
        (index, turn)
        for index, turn in enumerate(turns)
        if not is_low_information_turn(turn)
    ]
    if not informative:
        return None
    missing = [turn for _, turn in informative if turn not in semantic_scores]
    if missing:
        raise ValueError("semantic_scores missing at least one informative exact turn")
    index, turn = max(
        informative,
        key=lambda item: (
            float(semantic_scores[item[1]]),
            len([token for token in normalized_tokens(item[1]) if token not in _PHATIC]),
            item[0],
        ),
    )
    return SelectedMemorySpan(
        exact_span=turn,
        source_turn_index=index,
        semantic_score=float(semantic_scores[turn]),
        informative_turn_count=len(informative),
        raw_turn_count=len(turns),
    )


ResourceRole = Literal[
    "SILENT_RESPONSE_MODIFIER",
    "TENTATIVE_CONTINUITY_BRIDGE",
    "DECLINABLE_PAST_OPTION",
    "PRIMARY_SUPPORT_ACT",
]
JointMemoryRelation = Literal["NOT_APPLICABLE", "COMPLEMENTARY", "REDUNDANT", "CONFLICT", "UNKNOWN"]


@dataclass(frozen=True)
class PlannedResource:
    component: str
    role: ResourceRole
    exact_content: str
    requires_literal_mention: bool


@dataclass(frozen=True)
class JointCompositionPlan:
    requested_action_id: str
    feasible_action_id: str
    primary_response_act: str
    resources: tuple[PlannedResource, ...]
    suppressed: Mapping[str, str]
    assembly_order: tuple[str, ...]


_ROLE = {
    "MP": "SILENT_RESPONSE_MODIFIER",
    "MS": "TENTATIVE_CONTINUITY_BRIDGE",
    "ME": "DECLINABLE_PAST_OPTION",
    "RS": "PRIMARY_SUPPORT_ACT",
}


def build_joint_composition_plan(
    *,
    requested_action_id: str,
    realized_content: Mapping[str, str | None],
    component_scores: Mapping[str, float] | None = None,
    joint_memory_relation: JointMemoryRelation = "NOT_APPLICABLE",
) -> JointCompositionPlan:
    """Project requested components into one coherent response plan.

    The 16 requested actions remain unchanged.  Projection only removes a
    component whose resource could not be safely realized.  MP changes reply
    behavior silently; RS owns the primary discourse act.  MS and ME may both
    enter only when their relation was established outcome-blind as
    complementary.  Unknown/redundant/conflicting pairs retain the higher PM
    score (ME wins an exact tie) instead of forcing two unrelated memories
    into one reply.
    """

    bits = dict(action_component_bits(requested_action_id))
    scores = dict(component_scores or {})
    suppressed: dict[str, str] = {}
    accepted: dict[str, str] = {}
    for component in COMPONENTS:
        if not bits[component]:
            continue
        content = compact(realized_content.get(component))
        if not content:
            bits[component] = False
            suppressed[component] = "NO_SAFE_REALIZED_RESOURCE"
        else:
            accepted[component] = content

    if bits.get("MS") and bits.get("ME") and joint_memory_relation != "COMPLEMENTARY":
        ms_score = float(scores.get("MS", 0.0))
        me_score = float(scores.get("ME", 0.0))
        loser = "MS" if me_score >= ms_score else "ME"
        bits[loser] = False
        accepted.pop(loser, None)
        suppressed[loser] = f"JOINT_MEMORY_{joint_memory_relation}_LOWER_PRIORITY"

    resources = tuple(
        PlannedResource(
            component=component,
            role=_ROLE[component],  # type: ignore[arg-type]
            exact_content=accepted[component],
            requires_literal_mention=component in {"MS", "ME"},
        )
        for component in COMPONENTS
        if bits[component]
    )
    assembly = ["ACKNOWLEDGE_CURRENT_MESSAGE"]
    if bits.get("MP"):
        assembly.append("APPLY_MP_SILENTLY")
    if bits.get("MS"):
        assembly.append("OPTIONAL_TENTATIVE_MS_BRIDGE")
    if bits.get("ME"):
        assembly.append("OPTIONAL_DECLINABLE_ME_OPTION")
    assembly.append("EXECUTE_RS_PRIMARY_ACT" if bits.get("RS") else "EXECUTE_SUPPORTIVE_R0_ACT")
    assembly.append("ONE_COHERENT_REPLY")
    return JointCompositionPlan(
        requested_action_id=requested_action_id,
        feasible_action_id=compile_component_bits(bits),
        primary_response_act="RS" if bits.get("RS") else "R0",
        resources=resources,
        suppressed=suppressed,
        assembly_order=tuple(assembly),
    )
