"""Deterministic agent-identity and source-role context contract (candidate, not frozen).

Speaker identity is host knowledge (category 1): it is delivered by the context
organisation, never inferred by a semantic model. Three source situations:

  A IMPORTED_HUMAN  dialogue written by a previous human supporter (e.g. ESConv);
                    the current AI did not say those words and has none of that
                    person's experiences.
  B SAME_AGENT      earlier replies were produced by this same AI companion for this
                    user; they are the agent's own interaction history.
  C EXTERNAL_CASE   third-party dialogues/cases (RS, ESC-RAG, examples); neither the
                    user's nor the AI's history.

The frozen G0e/GSWS executor is NOT changed by this module. It is the shared
identity contract for the next bounded contrast, applied identically to every arm.
"""
from __future__ import annotations

IMPORTED_HUMAN, SAME_AGENT, EXTERNAL_CASE = 'A_imported_human_supporter', 'B_same_agent_history', 'C_external_case'

IDENTITY_CONTRACT = (
    'You are the current AI companion, not the human supporter appearing in imported dialogue '
    'records. Do not claim human personal experiences as your own. Attribute historical statements, '
    'experiences and advice to their actual speakers. If the user mistakes you for a previous human '
    'supporter, briefly clarify your identity and continue helping. Do not repeat your AI identity '
    'unnecessarily.')
SAME_AGENT_NOTE = ('Earlier assistant turns in this conversation were written by you, this same AI companion. '
                   'They are your interaction history, not personal life experiences.')
EXTERNAL_NOTE = ('External examples describe other people. They are neither this user\'s history nor yours.')

ROLE_LABEL = {
    IMPORTED_HUMAN: 'previous human supporter (not you)',
    SAME_AGENT: 'you (this AI companion, earlier)',
    EXTERNAL_CASE: 'third party in an external example',
}


def system_prompt(base, situation):
    """Append the identity contract that matches the deterministic source situation."""
    if situation == IMPORTED_HUMAN:
        return base + ' ' + IDENTITY_CONTRACT
    if situation == SAME_AGENT:
        return base + ' ' + SAME_AGENT_NOTE + ' Do not invent personal history.'
    if situation == EXTERNAL_CASE:
        return base + ' ' + EXTERNAL_NOTE + ' Do not invent personal history.'
    raise ValueError('unknown source situation')


def render_current_dialogue(turns, situation):
    """Native chat messages for the current visible prefix.

    B: seeker -> user, supporter -> assistant (they really are the agent's turns).
    A: the imported human supporter's turns are NOT given the native assistant role;
       the prefix is delivered as one attributed transcript followed by the latest user
       turn, so the model never sees another person's words as its own output.
    """
    if not turns or turns[-1]['role'] != 'seeker':
        raise ValueError('last visible turn must be the user')
    if situation == SAME_AGENT:
        return [dict(role='user' if t['role'] == 'seeker' else 'assistant', content=t['text']) for t in turns]
    if situation != IMPORTED_HUMAN:
        raise ValueError('current dialogue is A or B; external cases are never the current dialogue')
    earlier = turns[:-1]
    out = []
    if earlier:
        lines = [f"[{'user' if t['role'] == 'seeker' else ROLE_LABEL[IMPORTED_HUMAN]}] {t['text']}" for t in earlier]
        out.append(dict(role='user', content='Imported earlier part of this conversation (quoted record; the '
                        'supporter lines were written by a previous human supporter, not by you):\n' + '\n'.join(lines)))
    out.append(dict(role='user', content=turns[-1]['text']))
    return out


def attribute_history(speaker, situation):
    """Speaker label for quoted historical evidence."""
    if speaker == 'seeker':
        return 'user'
    if speaker == 'supporter':
        return ROLE_LABEL[situation]
    return speaker
