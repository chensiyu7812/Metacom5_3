"""One bounded output simplification for the same blinded Compass diagnostic.

Reuses its previously exercised two-field verdict protocol. No numeric q/m is
inferred from pair preference, and model disagreement is not human accuracy.
"""
import json
import re
from .judge import RUBRIC
from .evidence import evidence_turns
from .schema import digest
from metacom_pm.paper1.evaluation.local_teacher import parse_local_verdict

PAIR_RUBRIC = RUBRIC.split('For each independently checkable personal claim', 1)[0] + '''
Compare the two new replies A and B to the SAME final seeker turn. Neither is a
reference answer. Use the current-turn appropriateness and factual-risk rules
above to choose A_better, B_better, equivalent, or uncertain. A small style or
verbosity preference is not a substantive advantage. Both good or both equally
bad can be equivalent. Use uncertain when decisive evidence/semantics is unclear.
Your rationale must cite the decisive legal source-turn IDs and explain the
relationship to the reply text. A supporter suggestion, question, own experience
or hypothetical example is not a user-confirmed personal fact. Track dates and
corrections. Do not penalize a supported fact because only past sessions contain it.
Return exactly {"verdict":"A_better|B_better|equivalent|uncertain", "rationale":"..."}.
Do not output absolute q/m scores or additional fields. No rationale length cap.
'''
PAIR_RUBRIC_ID = digest(dict(protocol='rl1-blinded-pair-two-field-v2', text=PAIR_RUBRIC))


def messages_and_schema(item):
    evidence_turns(item['evidence'])
    messages = [dict(role='system', content=PAIR_RUBRIC), dict(role='user', content=json.dumps(
        dict(legal_evidence=item['evidence'], replies=item['replies']), ensure_ascii=False))]
    schema = dict(type='object', additionalProperties=False, required=['verdict', 'rationale'], properties=dict(
        verdict={'enum': ['A_better', 'B_better', 'equivalent', 'uncertain']},
        rationale={'type': 'string', 'minLength': 1}))
    return messages, schema


def parse_pair(raw, item, finish_reason):
    if finish_reason != 'natural_stop':
        return dict(status='technical_failure', reason=finish_reason, verdict=None, reward_eligible=False)
    try:
        value = parse_local_verdict(raw)
        ids = sorted(set(re.findall(r'\b(?:C|H\d{3}):T\d{3}\b', value['rationale'])))
        turns = evidence_turns(item['evidence'])
        if any(s not in turns for s in ids):
            raise ValueError('rationale cites an unavailable source ID')
        return dict(status='model_review_candidate' if ids else 'model_review_without_source_ids',
                    verdict=dict(pairwise=value['verdict'], rationale=value['rationale']),
                    cited_sources={s: turns[s] for s in ids}, q=None, m=None,
                    reward_eligible=False, semantic_validation=False, reviewer_kind='model')
    except (ValueError, KeyError, TypeError) as exc:
        return dict(status='parse_failure', reason=str(exc), verdict=None, reward_eligible=False)
