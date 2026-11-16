"""Prepared transport repair: make the grammar's field structure model-visible.

NOT live-evaluated. v4 raw output revealed schema guessing followed by whitespace
looping. This repair does not reopen semantic tuning or qualify a reward model.
"""
from .judge_flat import messages_and_schema as flat_messages, parse_flat, RUBRIC_V4
from .schema import digest

VERSION = 'pm-rl1-qm-explicit-structure-v5-prepared'
OUTPUT_STRUCTURE = '''
OUTPUT STRUCTURE (the following field names and nesting are mandatory):
The top-level JSON object has exactly: status, q, q_rationale, assessments,
coverage, uncertainty_reasons.
- status: string, scored or uncertain.
- q: integer from 0 through 4 when scored; null when uncertain.
- q_rationale: an OBJECT with exactly these four fields:
  current_need: nonempty string;
  response_unit_ids: nonempty array of legal reply-unit ID strings;
  source_turn_ids: nonempty array of legal source-turn ID strings;
  reason: nonempty string with the decisive quality justification.
- assessments: an ARRAY of objects. Each object has exactly these five fields:
  response_unit_id: one legal reply-unit ID string;
  relation: one of non_factual, supported, contradicted, unsupported, uncertain;
  severity: numeric 0 for non_factual/supported/uncertain, or 0.25/1 for an error;
  source_turn_ids: array of legal source-turn ID strings, nonempty for supported
    or contradicted;
  reason: nonempty string explaining the relationship to the cited source.
- coverage: nonempty STRING, not an object or array.
- uncertainty_reasons: ARRAY of nonempty strings; empty for scored, nonempty
  for uncertain. A scored record cannot contain uncertain assessments.
Use the supplied source/reply IDs exactly. Do not invent alternative keys such as
q_reason, relations, unit_id or source_ids. Do not output the schema itself.
Do not output kind, m or misuse_findings; the program derives the latter two.
This specifies formatting only. It adds no quality preference or score target.
'''
RUBRIC_V5 = RUBRIC_V4 + OUTPUT_STRUCTURE
RUBRIC_ID = digest(dict(protocol=VERSION,text=RUBRIC_V5))


def messages_and_schema(evidence,reply):
    messages,schema=flat_messages(evidence,reply)
    messages[0]=dict(role='system',content=RUBRIC_V5)
    return messages,schema


def parse_explicit(raw,**bindings):
    return parse_flat(raw,**bindings) | dict(rubric_identity=RUBRIC_ID,parser_version=VERSION,
        evaluator_execution_status='PREPARED_NOT_LIVE_VALIDATED',reward_eligible=False)
