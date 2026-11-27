"""Deterministic agent-identity and source-role context contract (candidate, not frozen).

Speaker identity is host knowledge (category 1): it is delivered by the context
organisation, never inferred by a semantic model. Source situations:

  A IMPORTED_HUMAN  dialogue written by a previous human supporter (e.g. ESConv
                    crowd workers; one per session, not assumed to be a clinician
                    or the same person across sessions). The current AI did not
                    say those words and has none of that person's experiences.
  B SAME_AGENT      earlier replies were produced by this same AI companion for this
                    user. Only host provenance (an agent/deployment log that binds the
                    reply to this agent) establishes B. A dataset in which the supporter
                    *role* is constant (e.g. EvoEmo) is not proof of B; it may be run as
                    B only as a declared experimental assumption.
  C EXTERNAL_CASE   third-party dialogues/cases (RS, ESC-RAG, examples). Both the
                    help-seeker and the supporter there are other people: neither is the
                    current user nor the current AI.
  U UNKNOWN_SOURCE  who wrote the earlier supporter turns is not established. The agent
                    must neither claim them as its own experiences nor deny them.

The frozen G0e/GSWS executor is NOT changed by this module. It is the shared identity
contract for bounded contrasts and later systems, applied identically to every arm.
"""
from __future__ import annotations

from dataclasses import dataclass

IMPORTED_HUMAN = 'A_imported_human_supporter'
SAME_AGENT = 'B_same_agent_history'
EXTERNAL_CASE = 'C_external_case'
UNKNOWN_SOURCE = 'U_unknown_supporter_identity'
SITUATIONS = (IMPORTED_HUMAN, SAME_AGENT, EXTERNAL_CASE, UNKNOWN_SOURCE)

IDENTITY_CONTRACT = (
    'You are the current AI companion, not the human supporter appearing in imported dialogue '
    'records. Do not claim human personal experiences as your own. Attribute historical statements, '
    'experiences and advice to their actual speakers. If the user mistakes you for a previous human '
    'supporter, briefly clarify your identity and continue helping. Do not repeat your AI identity '
    'unnecessarily.')
SAME_AGENT_NOTE = ('Earlier assistant turns in this conversation were written by you, this same AI companion. '
                   'They are your interaction history, not personal life experiences.')
EXTERNAL_NOTE = ('External examples describe other people. They are neither this user\'s history nor yours.')
UNKNOWN_NOTE = ('Earlier supporter turns are quoted records whose author is not established; they may not be '
                'yours. Do not claim their personal experiences as your own, and attribute them to the '
                'earlier supporter.')

# (seeker label, supporter label) for quoted evidence / memory records.
SPEAKER_LABELS = {
    IMPORTED_HUMAN: ('current user', 'previous human supporter (not you)'),
    SAME_AGENT: ('current user', 'you (this AI companion, earlier)'),
    EXTERNAL_CASE: ('help-seeker in an external example (not the current user)',
                    'supporter in an external example (not you)'),
    UNKNOWN_SOURCE: ('current user', 'earlier supporter (identity not established)'),
}
ROLE_LABEL = {k: v[1] for k, v in SPEAKER_LABELS.items()}


@dataclass(frozen=True)
class SourceIdentity:
    situation: str
    basis: str          # 'host_provenance' | 'experimental_assumption' | 'not_established'
    note: str


def classify_source(dataset, *, agent_log_match=False, assume_same_agent=False, external=False):
    """Deterministic situation from host provenance; never from dialogue text."""
    if external:
        return SourceIdentity(EXTERNAL_CASE, 'host_provenance', 'external example or case library')
    if agent_log_match:
        return SourceIdentity(SAME_AGENT, 'host_provenance', 'reply bound to this agent by deployment log')
    if dataset == 'ESConv':
        return SourceIdentity(IMPORTED_HUMAN, 'host_provenance',
                              'ESConv crowd-sourced human supporter; professional status not assumed')
    if assume_same_agent:
        return SourceIdentity(SAME_AGENT, 'experimental_assumption',
                              f'{dataset}: constant supporter role treated as this agent by experiment design only')
    return SourceIdentity(UNKNOWN_SOURCE, 'not_established', f'{dataset}: supporter author not established')


def system_prompt(base, situation):
    """Append the identity contract that matches the deterministic source situation."""
    if situation == IMPORTED_HUMAN:
        return base + ' ' + IDENTITY_CONTRACT
    if situation == SAME_AGENT:
        return base + ' ' + SAME_AGENT_NOTE + ' Do not invent personal history.'
    if situation == EXTERNAL_CASE:
        return base + ' ' + EXTERNAL_NOTE + ' Do not invent personal history.'
    if situation == UNKNOWN_SOURCE:
        return base + ' ' + UNKNOWN_NOTE + ' Do not invent personal history.'
    raise ValueError('unknown source situation')


def render_current_dialogue(turns, situation):
    """Native chat messages for the current visible prefix.

    B: seeker -> user, supporter -> assistant (they really are the agent's turns).
    A/U: earlier supporter turns are NOT given the native assistant role; the prefix is
       delivered as one attributed transcript followed by the latest user turn, so the
       model never sees another (or an unestablished) person's words as its own output.
    C: an external case is never the current dialogue.
    """
    if not turns or turns[-1]['role'] != 'seeker':
        raise ValueError('last visible turn must be the user')
    if situation == SAME_AGENT:
        return [dict(role='user' if t['role'] == 'seeker' else 'assistant', content=t['text']) for t in turns]
    if situation not in (IMPORTED_HUMAN, UNKNOWN_SOURCE):
        raise ValueError('current dialogue is A, B or U; external cases are never the current dialogue')
    earlier = turns[:-1]
    out = []
    if earlier:
        label = ROLE_LABEL[situation]
        lines = [f"[{'user' if t['role'] == 'seeker' else label}] {t['text']}" for t in earlier]
        head = ('the supporter lines were written by a previous human supporter, not by you'
                if situation == IMPORTED_HUMAN else 'the author of the supporter lines is not established')
        out.append(dict(role='user', content=f'Imported earlier part of this conversation (quoted record; {head}):\n'
                        + '\n'.join(lines)))
    out.append(dict(role='user', content=turns[-1]['text']))
    return out


def attribute_history(speaker, situation):
    """Speaker label for quoted historical evidence and Memory Writer records."""
    if situation not in SPEAKER_LABELS:
        raise ValueError('unknown source situation')
    seeker, supporter = SPEAKER_LABELS[situation]
    if speaker == 'seeker':
        return seeker
    if speaker == 'supporter':
        return supporter
    return speaker


def is_current_user(speaker, situation):
    """Whether a statement's speaker is the current user (subject binding for memory writes)."""
    return speaker == 'seeker' and situation != EXTERNAL_CASE
