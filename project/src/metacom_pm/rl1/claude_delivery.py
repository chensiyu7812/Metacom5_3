"""Offline Claude wire adapter; no credentials, network, or qualification.

The full original joint-score schema remains in the unchanged system prompt
and in local validation. A transport-only wrapper supplies an object root.
Model capabilities must come from an explicitly recorded Models API response.
"""
from copy import deepcopy
import json

from .schema import digest

VERSION = 'pmrl1-claude-joint-delivery-v1'


def project_schema(schema):
    """Project documented JSON-output subset, retaining every local constraint.

    oneOf is replaced only for provably disjoint constant-tagged branches.
    No generic oneOf-to-anyOf weakening or output repair is permitted.
    """
    changes = []
    def visit(node, path):
        if not isinstance(node, dict):
            raise ValueError('schema node must be an object')
        out = deepcopy(node)
        for key in ('minLength', 'maxLength', 'minimum', 'maximum', 'multipleOf', 'maxItems'):
            if key in out:
                changes.append(dict(path=path, keyword=key, value=out.pop(key), enforcement='full local schema'))
        if out.get('minItems', 0) not in (0, 1):
            changes.append(dict(path=path, keyword='minItems', value=out.pop('minItems'), enforcement='full local schema'))
        if 'oneOf' in out:
            branches = out.pop('oneOf')
            candidates = set.intersection(*(set(b.get('properties', {})) for b in branches)) if branches else set()
            disjoint = False
            for key in candidates:
                if all(key in b.get('required', []) and 'const' in b['properties'][key] for b in branches):
                    values = [json.dumps(b['properties'][key]['const'], sort_keys=True) for b in branches]
                    disjoint = len(set(values)) == len(values)
                    if disjoint:
                        break
            if not disjoint or 'anyOf' in out:
                raise ValueError('oneOf branches need a unique required constant discriminator')
            out['anyOf'] = branches
            changes.append(dict(path=path, keyword='oneOf', enforcement='disjoint constant tags; original local oneOf'))
        if out.get('type') == 'object':
            if out.get('additionalProperties') is not False:
                raise ValueError('objects must forbid extra fields')
            out['properties'] = {k: visit(v, path + '/properties/' + k) for k, v in out['properties'].items()}
        if 'items' in out:
            out['items'] = visit(out['items'], path + '/items')
        for key in ('anyOf', 'allOf'):
            if key in out:
                out[key] = [visit(v, path + '/' + key + '/' + str(i)) for i, v in enumerate(out[key])]
        allowed = {'type', 'properties', 'required', 'additionalProperties', 'items', 'enum', 'const',
                   'anyOf', 'allOf', 'minItems', 'description', 'title'}
        if set(out) - allowed:
            raise ValueError('unreviewed schema keyword: ' + ','.join(sorted(set(out)-allowed)))
        return out
    return visit(schema, ''), changes


def prepare_request(messages, schema, model_info, *, effort='high'):
    if ([m.get('role') for m in messages] != ['system', 'user'] or
            any(not isinstance(m.get('content'), str) or not m['content'] for m in messages)):
        raise ValueError('exactly one complete system and user message required')
    if json.dumps(schema, ensure_ascii=False) not in messages[0]['content']:
        raise ValueError('complete original local schema must be delivered in the prompt')
    caps = model_info.get('capabilities', {})
    if not (caps.get('structured_outputs', {}).get('supported') and
            caps.get('thinking', {}).get('types', {}).get('adaptive', {}).get('supported') and
            caps.get('effort', {}).get(effort, {}).get('supported')):
        raise ValueError('recorded model lacks requested capabilities')
    if not model_info.get('id') or type(model_info.get('max_tokens')) is not int or model_info['max_tokens'] <= 0:
        raise ValueError('explicit model and native output boundary required')
    projected, changes = project_schema(schema)
    delivery_schema = dict(type='object', properties={'assessment': projected},
                           required=['assessment'], additionalProperties=False)
    instruction = ('\nCLAUDE DELIVERY WRAPPER (serialization only): Put the unchanged complete '
        'joint-score object under the sole key "assessment". The original full local schema '
        'above applies to that inner object. Preserve its exact field names, case, source IDs '
        'and criteria. Do not repair or average earlier scores.\n')
    body = dict(model=model_info['id'], system=messages[0]['content'] + instruction,
        messages=[deepcopy(messages[1])], max_tokens=model_info['max_tokens'], stream=True,
        thinking={'type': 'adaptive'}, output_config=dict(effort=effort,
            format=dict(type='json_schema', schema=delivery_schema)))
    return dict(version=VERSION, wire_body=body, identity=digest(dict(version=VERSION, body=body)),
        original_messages_identity=digest(messages), local_schema_identity=digest(schema),
        model_capabilities_identity=digest(model_info), projection_changes=changes,
        live_execution_enabled=False, qualification_granted=False)


def parse_message(raw, prepared, schema, validate_semantics):
    """Parse a fully collected message; caller retains raw stream and usage.

    Successful parsing is technical delivery only. The existing semantic/source
    validator is mandatory, and empirical scorer qualification is separate.
    Refusal/truncation never become q/m or trigger an automatic larger retry.
    """
    from jsonschema import Draft202012Validator
    if prepared['local_schema_identity'] != digest(schema):
        raise ValueError('local contract changed')
    body = prepared['wire_body']
    if prepared['identity'] != digest(dict(version=VERSION, body=body)):
        raise ValueError('outbound request changed')
    if raw.get('model') != body['model'] or not raw.get('id'):
        raise ValueError('response model/identity mismatch')
    usage = raw.get('usage', {})
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in ('input_tokens', 'output_tokens')):
        raise ValueError('complete usage required before delivery acceptance')
    if raw.get('stop_reason') != 'end_turn':
        raise ValueError('non-natural or refused delivery: ' + str(raw.get('stop_reason')))
    blocks = raw.get('content', [])
    texts = [b['text'] for b in blocks if b.get('type') == 'text']
    if len(texts) != 1 or any(b.get('type') not in ('text', 'thinking', 'redacted_thinking') for b in blocks):
        raise ValueError('exactly one JSON text block; thinking is never parsed as answer')
    def pairs(items):
        out = {}
        for k, v in items:
            if k in out:
                raise ValueError('duplicate JSON key')
            out[k] = v
        return out
    def constant(_):
        raise ValueError('non-finite JSON number')
    value = json.loads(texts[0], object_pairs_hook=pairs, parse_constant=constant)
    if not isinstance(value, dict) or set(value) != {'assessment'}:
        raise ValueError('unchanged one-field delivery wrapper required')
    assessment = value['assessment']
    Draft202012Validator(schema).validate(assessment)
    validate_semantics(assessment)
    return assessment
