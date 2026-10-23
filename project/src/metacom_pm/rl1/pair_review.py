"""Blinded second-checkpoint diagnostic; no majority-vote gold or reward adapter."""
import json
from .evidence import evidence_turns
from .judge import RUBRIC, _pairs
from .judge_indexed import response_units
from .schema import digest

PAIR_RUBRIC = RUBRIC.split('For each independently checkable personal claim', 1)[0] + '''
There are two new replies A and B to the SAME final seeker turn. Evaluate each
individually with the q and m definitions above, then compare their CURRENT-TURN
QUALITY. Neither reply is a reference answer. Do not force a winner when both
are appropriate, both similarly poor, or differ only in acceptable style.
Use A_better/B_better only for a substantive current-need difference; otherwise
equivalent. Use uncertain if the decisive comparison cannot be resolved.
Report a decisive rationale with legal source-turn IDs and response-unit IDs for
each reply. Read the full supplied past, track speaker/time and current updates.
Selecting an existing source ID does not prove that it supports the claim.
Supported past facts must not be penalized just because absent from this session.
Separate factual error, tentative question, generic advice, omission and style.
For each reply status is scored or uncertain. A scored q is an integer 0..4 and
m is 0,0.25,1. If unresolved semantic/evidence ambiguity prevents either score,
set status uncertain, q and m null. Explain limits rather than invent certainty.
Return exactly the supplied JSON schema. Do not quote or copy another judge's
verdict: none is supplied. This is a model diagnostic, not human validation.
'''
PAIR_RUBRIC_ID = digest({'protocol': 'rl1-blinded-pair-review-v1', 'text': PAIR_RUBRIC})


def messages_and_schema(item):
    turns = evidence_turns(item['evidence'])
    units = {label: response_units(item['replies'][label]) for label in ('A', 'B')}
    text = {'type': 'string', 'minLength': 1}
    def obj(props):
        return dict(type='object', properties=props, required=list(props), additionalProperties=False)
    assessments = {}
    for label in ('A', 'B'):
        assessments[label] = obj(dict(
            decisive_reason=text,
            source_turn_ids={'type': 'array', 'minItems': 1, 'items': {'enum': list(turns)}},
            response_unit_ids={'type': 'array', 'minItems': 1, 'items': {'enum': [u['id'] for u in units[label]]}},
            limitations={'type': 'string'}, status={'enum': ['scored', 'uncertain']},
            q={'enum': [0, 1, 2, 3, 4, None]}, m={'enum': [0, .25, 1, None]}))
    schema = obj(dict(assessments=obj(assessments), comparison_reason=text,
                      pairwise={'enum': ['A_better', 'B_better', 'equivalent', 'uncertain']}))
    return [dict(role='system', content=PAIR_RUBRIC), dict(role='user', content=json.dumps(dict(
        legal_evidence=item['evidence'], replies=item['replies'],
        response_units={label: [{k: u[k] for k in ('id', 'text')} for u in values]
                        for label, values in units.items()}), ensure_ascii=False))], schema


def parse_pair(raw, item, finish_reason):
    if finish_reason != 'natural_stop':
        return dict(status='technical_failure', reason=finish_reason, verdict=None, reward_eligible=False)
    final = raw.strip()
    if final.startswith('```json') and final.endswith('```'):
        final = final[7:-3].strip()
    try:
        value = json.loads(final, object_pairs_hook=_pairs)
        if set(value) != {'assessments', 'comparison_reason', 'pairwise'}:
            raise ValueError('top-level keys differ')
        if set(value['assessments']) != {'A', 'B'}:
            raise ValueError('reply labels differ')
        turns = evidence_turns(item['evidence'])
        for label, v in value['assessments'].items():
            if set(v) != {'decisive_reason', 'source_turn_ids', 'response_unit_ids', 'limitations', 'status', 'q', 'm'}:
                raise ValueError('assessment keys differ')
            if not isinstance(v['decisive_reason'], str) or not v['decisive_reason'].strip():
                raise ValueError('empty rationale')
            if not isinstance(v['limitations'], str):
                raise ValueError('invalid limitations')
            ids = {u['id'] for u in response_units(item['replies'][label])}
            if not isinstance(v['source_turn_ids'], list) or not v['source_turn_ids'] or any(s not in turns for s in v['source_turn_ids']):
                raise ValueError('source IDs invalid')
            if not isinstance(v['response_unit_ids'], list) or not v['response_unit_ids'] or any(s not in ids for s in v['response_unit_ids']):
                raise ValueError('response IDs invalid')
            if v['status'] == 'scored':
                if type(v['q']) is not int or v['q'] not in range(5) or type(v['m']) not in (int, float) or v['m'] not in (0, .25, 1):
                    raise ValueError('q/m invalid')
            elif v['status'] != 'uncertain' or v['q'] is not None or v['m'] is not None or not v['limitations'].strip():
                raise ValueError('uncertain status requires null scores and a reason')
        if value['pairwise'] not in ('A_better', 'B_better', 'equivalent', 'uncertain'):
            raise ValueError('unknown pair verdict')
        if not isinstance(value['comparison_reason'], str) or not value['comparison_reason'].strip():
            raise ValueError('empty comparison reason')
        return dict(status='model_review_candidate', verdict=value, reward_eligible=False,
                    semantic_validation=False, reviewer_kind='model')
    except (ValueError, TypeError, KeyError) as exc:
        return dict(status='parse_failure', reason=str(exc), verdict=None, reward_eligible=False)
