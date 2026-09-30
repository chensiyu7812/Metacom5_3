"""Transport-only simplification of v3: one relation decision, legal combinations.

No raw v3 output is repaired. The semantic scope and q/m anchors remain v3.
"""
import json
from hashlib import sha256
from .evidence import evidence_turns
from .judge import _pairs, _keys
from .judge_indexed import response_units
from .judge_scoped import RUBRIC_V3, parse_scoped
from .schema import digest

VERSION = 'pm-rl1-qm-scoped-flat-v4'
RUBRIC_V4 = RUBRIC_V3.replace(
    'For each checked reply unit give kind personal_fact, boundary_issue, or non_factual.\n'
    'Non-factual units use relation not_applicable and severity 0. For personal facts\n'
    'or boundary issues use supported/contradicted/unsupported/uncertain.',
    'For each checked reply unit make ONE relation decision: non_factual, supported,\n'
    'contradicted, unsupported, or uncertain. Use non_factual with severity 0 for\n'
    'non-factual units; use the other relations for personal facts or boundary issues.')
RUBRIC_ID = digest(dict(protocol=VERSION, text=RUBRIC_V4))


def messages_and_schema(evidence, reply):
    turns = evidence_turns(evidence); units = response_units(reply)
    text = {'type': 'string', 'minLength': 1}
    sources = {'type': 'array', 'items': {'type': 'string', 'enum': list(turns)}}
    response = {'type': 'string', 'enum': [u['id'] for u in units]}
    def obj(p): return dict(type='object', properties=p, required=list(p), additionalProperties=False)
    def assessment(relation):
        return obj(dict(response_unit_id=response, relation={'const': relation},
            severity={'enum': [.25, 1] if relation in ('contradicted', 'unsupported') else [0]},
            source_turn_ids={**sources, **({'minItems': 1} if relation in ('supported', 'contradicted') else {})},
            reason=text))
    def record(uncertain):
        relations = ['non_factual', 'supported', 'contradicted', 'unsupported'] + (['uncertain'] if uncertain else [])
        return obj(dict(status={'const': 'uncertain' if uncertain else 'scored'},
            q={'type': 'null'} if uncertain else {'type': 'integer', 'enum': [0, 1, 2, 3, 4]},
            q_rationale=obj(dict(current_need=text,
                response_unit_ids={'type': 'array', 'minItems': 1, 'items': response},
                source_turn_ids={**sources, 'minItems': 1}, reason=text)),
            assessments={'type': 'array', 'items': {'oneOf': [assessment(r) for r in relations]}},
            coverage=text, uncertainty_reasons={'type': 'array', 'items': text,
                **({'minItems': 1} if uncertain else {'maxItems': 0})}))
    schema = {'oneOf': [record(False), record(True)]}
    return [dict(role='system', content=RUBRIC_V4), dict(role='user', content=json.dumps(dict(
        legal_evidence=evidence, reply=reply,
        response_units=[{k: u[k] for k in ('id', 'text')} for u in units]), ensure_ascii=False))], schema


def parse_flat(raw, **bindings):
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
        mapped = []
        for a in value['assessments']:
            _keys(a, 'response_unit_id relation severity source_turn_ids reason')
            relation = a['relation']
            if relation not in ('non_factual', 'supported', 'contradicted', 'unsupported', 'uncertain'):
                raise ValueError('unknown relation')
            allowed = (.25, 1) if relation in ('contradicted', 'unsupported') else (0,)
            if type(a['severity']) not in (int, float) or a['severity'] not in allowed:
                raise ValueError('relation/severity conflict')
            mapped.append(a | dict(kind='non_factual' if relation == 'non_factual' else 'personal_fact',
                                   relation='not_applicable' if relation == 'non_factual' else relation))
        parsed = parse_scoped(json.dumps(value | dict(assessments=mapped), ensure_ascii=False), **bindings)
        return parsed | {k: v for k, v in base.items() if k not in ('q', 'm')} | dict(
            flat_judge_output=value,
            transport_revision='single relation decision; legal combinations constrained before generation; no semantic repair')
    except (ValueError, TypeError, KeyError) as exc:
        return base | dict(measurement_status='parse_or_evidence_failure', error=str(exc))
