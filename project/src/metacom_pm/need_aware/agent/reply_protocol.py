"""WP4 reply/MCQ protocols after the researcher's response-supervision amendment.

All evidence arms consume byte-identical raw evidence. No third-party filtering.
These rules are distinct from the frozen historical behavior-v1 implementation.
"""
from ..data.short_protocol import instruction, PROTOCOL
from ..data.contracts import digest

VERSION = 'naa-reply-protocol-v1'
ARMS = ('U0', 'U1', 'U1+', 'No-memory', 'Options-only')
SYSTEM = 'You are a helpful conversational assistant. Answer the current user request.'
U1 = ("Use prior conversation records when they help answer the current request. Prefer the user's current "
      "goal and explicit instructions over older assumptions. Do not force unrelated personalization. "
      "Distinguish statements, quoted text, fiction, translations, and earlier assistant suggestions; "
      "they need not be facts about the user. Infer implicit preferences only when supported by the context, "
      "and express uncertainty when evidence is weak. Do not invent personal details. Apply a change only "
      "to the same subject, attribute and situation; later order alone does not invalidate older facts. "
      "Respect requests not to use or remember information, within their stated scope. Avoid unnecessary "
      "sensitive disclosures and demographic stereotypes. If missing information matters, ask a focused "
      "question; otherwise provide useful help without unsupported assumptions. Information about other "
      "people remains available when relevant; never discard it solely because it concerns a third party.")
U1_PLUS = ("Additionally distinguish the speaker, the person an assertion or preference concerns (holder), "
           "and the person the current task is meant to help (beneficiary). Match a preference to the "
           "beneficiary before using it. A user quoting a friend's message does not acquire the friend's "
           "preferences. Conversely, if the request is for that friend, use relevant information about "
           "the friend. An email recipient may be the user; do not treat every email as another person's "
           "experience. Preserve multiple people's different preferences. Do not silently suppress "
           "third-party evidence. Clarify ambiguous identity only when it changes the answer.")


def messages(task, evidence, arm='U0', *, mcq=False):
    if arm not in ARMS:
        raise ValueError('unknown WP4 control')
    if arm == 'Options-only':
        if not mcq:
            raise ValueError('options-only is an MCQ diagnostic')
        return [dict(role='system', content=SYSTEM), dict(role='user', content=instruction(task.options))]
    policy = '' if arm not in ('U1','U1+') else '\n\n' + U1
    if arm == 'U1+':
        policy += '\n\n' + U1_PLUS
    block = evidence if arm != 'No-memory' else 'No earlier conversation records are provided.'
    text = block + '\n\nCurrent request from the user:\n' + task.user_query
    if mcq:
        text += '\n\n' + instruction(task.options)
    return [dict(role='system', content=SYSTEM+policy), *[dict(x) for x in task.current_messages],
            dict(role='user', content=text)]


def identity():
    return digest(dict(version=VERSION, system=SYSTEM, u1=U1, u1plus=U1_PLUS, mcq=PROTOCOL))
