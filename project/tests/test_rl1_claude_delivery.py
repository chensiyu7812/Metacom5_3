"""Provider-independent serialization tests, not scorer validity evidence."""
from copy import deepcopy
import json
import pytest
from jsonschema import ValidationError

from metacom_pm.rl1.claude_delivery import prepare_request, parse_message, project_schema


def fixtures():
    schema = dict(oneOf=[dict(type='object', properties=dict(status=dict(const=s),
        reason=dict(type='string', minLength=1)), required=['status', 'reason'], additionalProperties=False)
        for s in ('scored', 'uncertain')])
    messages = [dict(role='system', content='Unchanged rubric\n'+json.dumps(schema, ensure_ascii=False)),
                dict(role='user', content='Complete legal sources and reply')]
    model = dict(id='MOCK:claude', max_tokens=128000, capabilities=dict(
        structured_outputs=dict(supported=True), thinking=dict(types=dict(adaptive=dict(supported=True))),
        effort=dict(high=dict(supported=True))))
    prepared = prepare_request(messages, schema, model)
    raw = dict(id='MOCK:message', model=model['id'], stop_reason='end_turn',
        usage=dict(input_tokens=100, output_tokens=20), content=[dict(type='thinking', thinking='not JSON'),
        dict(type='text', text=json.dumps(dict(assessment=dict(status='scored', reason='bound source'))))])
    return schema, messages, prepared, raw


def test_exact_sources_and_full_schema_survive_projection():
    schema, messages, p, raw = fixtures()
    assert p['wire_body']['messages'] == [messages[1]]
    assert p['wire_body']['system'].startswith(messages[0]['content'])
    assert p['wire_body']['max_tokens'] == 128000
    called = []
    value = parse_message(raw, p, schema, lambda x: called.append(x))
    assert called == [value] and value['status'] == 'scored'
    assert not p['live_execution_enabled'] and not p['qualification_granted']


def test_unsupported_constraints_retained_locally():
    schema, _, p, raw = fixtures()
    raw['content'][-1]['text'] = json.dumps(dict(assessment=dict(status='scored', reason='')))
    with pytest.raises(ValidationError):
        parse_message(raw, p, schema, lambda _: None)


@pytest.mark.parametrize('bad', [
    '{"assessment":{"status":"scored","status":"uncertain","reason":"x"}}',
    '{"assessment":{"status":"scored","reason":"x"}}}',
    '```json\n{"assessment":{"status":"scored","reason":"x"}}\n```',
    '{"assessment":{"status":"scored","reason":NaN}}'])
def test_no_duplicate_repair_or_fenced_json(bad):
    schema, _, p, raw = fixtures(); raw['content'][-1]['text'] = bad
    with pytest.raises(ValueError):
        parse_message(raw, p, schema, lambda _: None)


@pytest.mark.parametrize('reason', ['refusal', 'max_tokens', 'pause_turn', 'tool_use', None])
def test_non_natural_delivery_never_numeric(reason):
    schema, _, p, raw = fixtures(); raw['stop_reason'] = reason
    with pytest.raises(ValueError, match='non-natural'):
        parse_message(raw, p, schema, lambda _: None)


def test_semantic_validator_is_not_bypassed_by_valid_json():
    schema, _, p, raw = fixtures()
    def reject(_):
        raise ValueError('source reference absent')
    with pytest.raises(ValueError, match='source reference'):
        parse_message(raw, p, schema, reject)


def test_input_model_and_usage_bindings_required():
    schema, _, p, raw = fixtures()
    for field, value in [('model', 'another-model'), ('usage', {})]:
        broken = deepcopy(raw); broken[field] = value
        with pytest.raises(ValueError):
            parse_message(broken, p, schema, lambda _: None)
    p['wire_body']['max_tokens'] = 1024
    with pytest.raises(ValueError, match='outbound'):
        parse_message(raw, p, schema, lambda _: None)


def test_generic_overlapping_union_is_rejected():
    with pytest.raises(ValueError, match='discriminator'):
        project_schema(dict(oneOf=[dict(type='integer'), dict(type='number')]))
