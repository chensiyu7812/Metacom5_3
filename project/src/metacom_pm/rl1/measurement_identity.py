"""Content identities for qualified feedback; generation lineage stays separate."""
from .schema import digest

POLICY = 'qualified-content-feedback-v1'


def binding(generation_id, response_id, evidence_id, freeze, qualification):
    return dict(generation_request_id=generation_id, response_identity=response_id,
        evidence_identity=evidence_id, runtime_identity=freeze['runtime_identity'],
        rubric_identity=freeze['rubric_identity'], freeze_identity=freeze['identity'],
        qualification_identity=qualification['identity'], cache_policy=POLICY,
        measurement_purpose='training', measurement_draw_identity='canonical-training-draw')


def canonical(query, evidence, reply):
    if query.get('cache_policy') != POLICY:
        raise ValueError('unsupported content cache policy')
    required = {'generation_request_id', 'response_identity', 'evidence_identity',
        'runtime_identity', 'rubric_identity', 'freeze_identity', 'qualification_identity',
        'cache_policy', 'measurement_purpose', 'measurement_draw_identity'}
    if set(query) != required or any(not isinstance(v, str) or not v for v in query.values()):
        raise ValueError('complete measurement version and draw bindings required')
    purpose, draw = query['measurement_purpose'], query['measurement_draw_identity']
    if (purpose not in ('training', 'independent_repeat')
            or (purpose == 'training') != (draw == 'canonical-training-draw')):
        raise ValueError('independent repeats require a distinct explicit draw identity')
    if query['evidence_identity'] != digest(evidence) or query['response_identity'] != digest(reply):
        raise ValueError('measurement content identity mismatch')
    return {k: v for k, v in query.items() if k != 'generation_request_id'}
