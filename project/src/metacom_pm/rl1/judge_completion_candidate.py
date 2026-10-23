"""PROPOSED, NOT ENABLED: the single post-human semantic revision candidate.

The old module, scales, parser and rewards remain unchanged. Importing this
module does not select it for a run or create a measurement freeze.
"""
from . import judge_completion as original
from .schema import digest

VERSION = 'pm-rl1-completion-qm-v2-proposed-20261014'
ADDITION = '''
DEVELOPMENT CLOSEOUT: EVIDENCE AND ANCHOR APPLICATION
Before selecting q, state the current user's actual request and the response's
concrete contribution or omission. Distinguish asking for a personal experience
from asking for practical advice under the NEW AI contract. An exploratory
question can be appropriate, but do not treat one style of exploration as a
complete answer and another as a major omission without a task-specific reason.
Do not require a personal anecdote that this assistant is forbidden to invent.
For adjacent q anchors, explain what this current turn calls for that is more
fully met, or what concrete limitation remains. q=3 does not require an important
defect; q=2 still requires the important missed need/constraint in its anchor.
Do not decide from absence of a preferred empathy phrase, repeating the topic
noun, or a stylistic variant alone.
This does not prescribe equal scores or override a genuine quality difference.

For each error assessment, explicitly distinguish (a) what the reply asserts,
(b) who acted or spoke, (c) intention versus completed action and current versus
past state, and (d) the consequence that justifies the existing severity anchor.
Attribute benefits to the named person in the source before considering the
assistant's role boundary. Do not replace a friend with a historical supporter.
Check that every ID cited in the reason actually contains the attributed words.
A source ID being legal is not evidence that it entails the stated relationship.
No mention in the complete record means unsupported, not disproven in the world.
Distinguish explicit presuppositions from genuinely tentative alternatives.
An optional invitation to talk or explore is not an instruction to act now;
identify a concrete violated user constraint before assigning boundary misuse.
Apply the existing local/severe anchors to the actual consequence; a factual
error category alone is not its severity, and fluent empathy does not excuse it.
If a material factual or severity ambiguity remains, use the existing uncertain
status and explain it. Do not invent an answer or change q/m scales or weights.
'''
RUBRIC = original.RUBRIC + ADDITION
RECHECK_INSTRUCTION = original.RECHECK_INSTRUCTION
RUBRIC_ID = digest(dict(version=VERSION, rubric=RUBRIC, recheck=RECHECK_INSTRUCTION))


def messages_and_schema(evidence, reply, *, recheck=False):
    messages, schema = original.messages_and_schema(evidence, reply, recheck=recheck)
    messages[0] = dict(role='system', content=RUBRIC + (RECHECK_INSTRUCTION if recheck else ''))
    return messages, schema


def parse_completion(raw, **bindings):
    result = original.parse_completion(raw, **bindings)
    return result | dict(rubric_identity=RUBRIC_ID, parser_version=VERSION,
        semantic_revision='Proposed single post-human revision; never implies qualification',
        reward_eligible=False)
