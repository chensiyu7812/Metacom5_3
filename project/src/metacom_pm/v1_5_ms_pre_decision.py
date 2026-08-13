"""MS USE/ASK/IGNORE pre-decision, enforced before any resource reaches the
compiler -- root fix for the evo::p6 MS+RS composition leak found in
paper1_rs_ms_panel_v2_blind_review_v2_closeout_v1.json.

Root cause: the prior architecture always handed the MS candidate's exact
source text to the generator and asked it to decide USE/ASK/IGNORE as part
of a single generation call. MS+R0 alone correctly resolved to IGNORE on a
topically mismatched candidate, but once RS was also asked to contribute a
strategy move in the SAME call, the combined generation leaked the
mismatched, irrelevant source content into the reply. Relying on the
generator's own in-context restraint is not sufficient once other resources
compete for the same reply.

Fix: the USE/ASK/IGNORE decision is made HERE, before compilation, not
inside the generation call. If the decision is IGNORE, the MS candidate is
never constructed into a resource at all -- it is physically absent from
whatever gets compiled into messages, identically to how an M0 (MS not
requested) arm already works. RS composition cannot leak a source it was
never given, and this holds regardless of which other components are also
active for the same state.
"""

from __future__ import annotations

from typing import Literal, Mapping

from .v1_5_component_general_v3 import V3Candidate

MSPreDecision = Literal["USE", "ASK", "IGNORE"]


def ms_candidate_or_none(
    *,
    pre_decision: MSPreDecision,
    evidence_id: str,
    meaning_cue: str,
    exact_source: str,
    owner_id: str,
    allowed_response_change: str,
    forbidden_inference: str,
    time_status: str = "STRICTLY_PAST",
) -> V3Candidate | None:
    """The only sanctioned way to construct an MS candidate for compilation.

    Returns None for IGNORE -- the candidate is never built, so its
    exact_source can never be embedded in any compiled prompt, regardless of
    which other components (RS, MP, ME) are also being compiled for the same
    state. There is no other code path that may hand exact_source to the
    compiler once pre_decision is IGNORE.
    """

    if pre_decision not in ("USE", "ASK", "IGNORE"):
        raise ValueError(f"unknown MS pre_decision: {pre_decision!r}")
    if pre_decision == "IGNORE":
        return None
    return V3Candidate(
        component="MS",
        evidence_id=evidence_id,
        meaning_cue=meaning_cue,
        exact_source=exact_source,
        owner_id=owner_id,
        time_status=time_status,
        allowed_response_change=allowed_response_change,
        forbidden_inference=forbidden_inference,
    )


def assert_source_absent_from_compiled_text(*, exact_source: str, compiled_messages: list[Mapping[str, str]]) -> None:
    """Regression guard: once pre_decision is IGNORE, exact_source must not
    appear anywhere in what would be sent to a generator, in any arm."""

    haystack = " ".join(str(message.get("content", "")) for message in compiled_messages)
    if exact_source and exact_source in haystack:
        raise AssertionError("IGNORE-decided MS source leaked into compiled messages")
