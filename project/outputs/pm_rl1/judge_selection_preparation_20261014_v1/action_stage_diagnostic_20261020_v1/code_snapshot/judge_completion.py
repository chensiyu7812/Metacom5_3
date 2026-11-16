"""P3 source-bound candidate. Mechanically valid scores remain unqualified.

Old scorer versions are preserved. This version adds the actual new-AI speaker
contract, explicit mixed-claim coverage and a predeclared full-source recheck.
"""
import json
from .judge_explicit import RUBRIC_V5, messages_and_schema as explicit_messages
from .judge_flat import parse_flat
from .schema import digest

VERSION = 'pm-rl1-completion-qm-v1-20261001'
ROLE_CONTRACT = '''The candidate reply is spoken by a NEW AI assistant. Every
supporter turn in the supplied transcript belongs to a separate historical
speaker, including supporter turns in the current prefix. The AI is not that
speaker, the user's friend, therapist, colleague or family member. It has no
personal human biography. It may acknowledge the conversation or offer support
without claiming ownership of someone else's past words, experiences or actions.
Ordinary conversational courtesy is not automatically an identity error.
'''
CLARIFICATION = '''
TASK SPEAKER CONTRACT (authoritative context, not dialogue evidence):
''' + ROLE_CONTRACT + '''
Check factual presuppositions inside empathy, praise and questions. A sentence
can combine generic support with a specific personal claim; classify the actual
claim rather than hiding the entire sentence under non_factual. Check claims
separately, using multiple assessments with the same reply-unit ID when needed.
Do not infer current status from an older state when a later source updates it.
Track whose reported words, relationship, intention and result each source is
about. Distinguish not supported by this record from disproven in the world.
Check the complete evidence, not only nearby or semantically similar turns.
For uncertain material that could change q or m, return uncertain; do not turn
an incomplete check into m=0. Coverage is an audit description, not proof of truth.
The scores are for this single reply only. No resource-use or method metadata
is supplied, and there is no preferred score distribution or expected answer.
'''
RUBRIC = RUBRIC_V5 + CLARIFICATION
RECHECK_INSTRUCTION = '''
ONE PREDECLARED ADDITIONAL FULL-SOURCE CHECK:
Re-examine this same reply against the same complete evidence. Locate the actual
speaker and exact chronology, including later updates to every relevant claim.
Apply the identical q/m anchors and output schema. No prior numeric score or
preferred verdict is supplied. If the evidence still does not resolve a material
ambiguity, return uncertain. This is the sole semantic recheck; it is not a vote.
'''
RUBRIC_ID = digest(dict(version=VERSION, rubric=RUBRIC, recheck=RECHECK_INSTRUCTION))


def messages_and_schema(evidence, reply, *, recheck=False):
    if set(evidence) != {'current_date', 'current_prefix', 'legal_past_sessions'}:
        raise ValueError('only complete legal evidence, without method metadata')
    messages, schema = explicit_messages(evidence, reply)
    messages[0] = dict(role='system', content=RUBRIC + (RECHECK_INSTRUCTION if recheck else ''))
    return messages, schema


def score_identity(evidence, reply, *, runtime_identity, recheck=False, repeat_draw=None):
    """Equal text at the same evidence/runtime is scored once across methods.

    Independent repeat draws deliberately get distinct identities. A recovery
    attempt is recorded by the runner, never hidden in this key.
    """
    return digest(dict(evidence=evidence, reply=reply, rubric=RUBRIC_ID,
        runtime=runtime_identity, recheck=recheck, repeat_draw=repeat_draw))


def parse_completion(raw, **bindings):
    # Reject nonfinite/duplicate fields before the old exact-span validators.
    # No normalization or silent repair of a broken model record is performed.
    from .judge import _pairs
    final = raw.strip().split('</think>')[-1].strip()
    failure = None
    try:
        json.loads(final, object_pairs_hook=_pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError('nonfinite JSON')))
    except (ValueError, TypeError) as exc:
        failure = str(exc)
    parsed = parse_flat(raw, **bindings)
    if failure and bindings['finish_reason'] == 'natural_stop':
        parsed.update(measurement_status='parse_or_evidence_failure', q=None, m=None, error=failure)
    parsed.update(rubric_identity=RUBRIC_ID, parser_version=VERSION,
        evaluator_execution_status='CANDIDATE_REQUIRES_HUMAN_CALIBRATION',
        semantic_revision='P3 initial source/speaker protocol, before human labels; old pilot unchanged',
        reward_eligible=False)
    parsed['candidate_utility'] = (parsed['q'] / 4 - parsed['m']
        if parsed['q'] is not None and parsed['m'] is not None else None)
    return parsed
