"""Single development scope clarification plus derived m/findings protocol.

Original q/m anchors and weights stay fixed. The model explicitly classifies
non-factual units; the parser never infers this classification from its prose.
"""
import json
from hashlib import sha256
from .evidence import evidence_turns
from .judge import RUBRIC, _pairs, _keys
from .judge_indexed import response_units, parse_indexed
from .schema import digest

VERSION = 'pm-rl1-qm-scoped-derived-v3'
RUBRIC_V3 = RUBRIC.split('For each independently checkable personal claim', 1)[0] + '''
SCOPE CLARIFICATION: A reply sentence is not automatically a personal factual
assertion. Generic advice, a tentative question, an evaluative phrase such as
"that is encouraging", and inclusive "we" used for a general human experience
are non_factual unless they actually assert a specific personal event or fact.
Their appropriateness still matters to q, but absence of a supporting historical
quote is not itself a misuse. Do not turn subjective praise into a fabricated
user preference. A question may presuppose a personal fact: assess that actual
presupposition when present, rather than exempting every question mechanically.
A user's explicit report of trying/working on something supports recognition of
effort; it does not prove completion, success, or symptom improvement. Conversely,
unresolved difficulty does not contradict that the user is trying. Read the full
current prefix for these distinctions. A death alone does not prove that a meeting
never happened before it: use actual chronological evidence, not a shortcut.

For each checked reply unit give kind personal_fact, boundary_issue, or non_factual.
Non-factual units use relation not_applicable and severity 0. For personal facts
or boundary issues use supported/contradicted/unsupported/uncertain. Supported and
uncertain use severity 0; a definite contradicted/unsupported error uses 0.25 or 1
according to the unchanged m severity anchors. A supported/contradicted relation
requires source-turn IDs that support that relationship, not merely the topic.
Unsupported requires checking the complete legal material, not just a short list.
Assess independently checkable claims separately if one reply unit contains more
than one. Do not manufacture claims; the list can be empty. Explain coverage.

Select legal source-turn IDs and reply-unit IDs; the program restores exact raw
text. It computes m=max(error severity), or 0 when no error, and constructs the
error indexes. Do NOT output m or misuse_findings yourself. These are fixed
arithmetic derivations, not a second semantic decision. Non_factual entries remain
in the audit record but do not become personal-error claims.
If unresolved ambiguity prevents q or m, use status uncertain, q null, and explicit
uncertainty_reasons. Otherwise status scored, q integer 0..4, no uncertainty reasons
or uncertain claims. q is the same quality scale defined above; never create a
quality difference merely to reward using resources or to fill the score range.
Return exactly the provided JSON schema, after any private reasoning.
'''
RUBRIC_ID = digest(dict(protocol=VERSION, text=RUBRIC_V3))


def messages_and_schema(evidence, reply):
    turns = evidence_turns(evidence); units = response_units(reply)
    text = {'type': 'string', 'minLength': 1}
    source_ids = {'type': 'array', 'items': {'enum': list(turns)}}
    response_id = {'enum': [u['id'] for u in units]}
    def obj(p): return dict(type='object', properties=p, required=list(p), additionalProperties=False)
    schema = obj(dict(status={'enum': ['scored', 'uncertain']}, q={'enum': [0, 1, 2, 3, 4, None]},
        q_rationale=obj(dict(current_need=text, response_unit_ids={'type': 'array', 'minItems': 1, 'items': response_id},
            source_turn_ids={**source_ids, 'minItems': 1}, reason=text)),
        assessments={'type': 'array', 'items': obj(dict(response_unit_id=response_id,
            kind={'enum': ['personal_fact', 'boundary_issue', 'non_factual']},
            relation={'enum': ['supported', 'contradicted', 'unsupported', 'uncertain', 'not_applicable']},
            severity={'enum': [0, .25, 1]}, source_turn_ids=source_ids, reason=text))},
        coverage=text, uncertainty_reasons={'type': 'array', 'items': text}))
    return [dict(role='system', content=RUBRIC_V3), dict(role='user', content=json.dumps(dict(
        legal_evidence=evidence, reply=reply, response_units=[{k: u[k] for k in ('id', 'text')} for u in units]),
        ensure_ascii=False))], schema


def parse_scoped(raw, **bindings):
    base = dict(response_sha256=sha256(bindings['reply'].encode()).hexdigest(),
                legal_evidence_identity=digest(bindings['evidence']), rubric_identity=RUBRIC_ID,
                judge_runtime_identity=bindings['runtime_identity'], measurement_draw_id=bindings['draw_id'],
                parser_version=VERSION, raw_output_sha256=sha256(raw.encode()).hexdigest(),
                reward_eligible=False, q=None, m=None)
    if bindings['finish_reason'] != 'natural_stop':
        return base | dict(measurement_status='technical_failure', technical_reason=bindings['finish_reason'])
    final = raw.strip()
    if '</think>' in final:
        if final.count('</think>') != 1:
            return base | dict(measurement_status='parse_or_evidence_failure', error='multiple thinking closures')
        final = final.split('</think>', 1)[1].strip()
    try:
        value = json.loads(final, object_pairs_hook=_pairs)
        _keys(value, 'status q q_rationale assessments coverage uncertainty_reasons')
        if not isinstance(value['assessments'], list): raise ValueError('assessments must be list')
        turns = evidence_turns(bindings['evidence']); units = {u['id'] for u in response_units(bindings['reply'])}
        claims = []
        for a in value['assessments']:
            _keys(a, 'response_unit_id kind relation severity source_turn_ids reason')
            if a['response_unit_id'] not in units: raise ValueError('unavailable reply unit')
            if not isinstance(a['source_turn_ids'], list) or any(s not in turns for s in a['source_turn_ids']):
                raise ValueError('unavailable source unit')
            if not isinstance(a['reason'], str) or not a['reason'].strip(): raise ValueError('missing assessment reason')
            if a['kind'] == 'non_factual':
                if a['relation'] != 'not_applicable' or type(a['severity']) not in (int, float) or a['severity'] != 0:
                    raise ValueError('non-factual classification conflicts with relation/severity')
            elif a['kind'] in ('personal_fact', 'boundary_issue'):
                claims.append({k: v for k, v in a.items() if k != 'kind'})
            else:
                raise ValueError('unknown assessment kind')
        # Validate types before arithmetic; semantic assignments are model-authored.
        if any(type(c['severity']) not in (int, float) or c['severity'] not in (0, .25, 1) for c in claims):
            raise ValueError('invalid severity')
        indexes = [i for i, c in enumerate(claims) if c['severity'] > 0]
        m = max((c['severity'] for c in claims), default=0) if value['status'] == 'scored' else None
        projected = dict(status=value['status'], q=value['q'], m=m, q_rationale=value['q_rationale'],
                         claims=claims, misuse_findings=indexes, coverage=value['coverage'],
                         uncertainty_reasons=value['uncertainty_reasons'])
        parsed = parse_indexed(json.dumps(projected, ensure_ascii=False), **bindings)
        return parsed | {k: v for k, v in base.items() if k not in ('q', 'm')} | dict(
            scoped_judge_output=value, derived_m=m, derived_error_indexes=indexes,
            derivation='max of explicitly classified personal/boundary error severities; non-factual judgments remain audited',
            semantic_revision='one train-development scope clarification; reused exam, not unseen validation')
    except (ValueError, TypeError, KeyError) as exc:
        return base | dict(measurement_status='parse_or_evidence_failure', error=str(exc))
