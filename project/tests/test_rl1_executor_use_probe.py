from copy import deepcopy
import json
import pytest

from metacom_pm.rl1.executor_use_probe import FIELDS, INSTRUCTION, intervene, request_for
from metacom_pm.rl1.schema import digest


def item(on=False):
    system = 'role rules\n<quoted_conversation_context>\n[]\n</quoted_conversation_context>'
    if on:
        system += '\n<resources>\n' + json.dumps([dict(address='r', content='whole source')]) + '\n</resources>'
    row = dict(prefix_identity='prefix', executor_identity='runtime', renderer_identity='renderer', renderer_route='original',
               messages=[dict(role='system', content=system), dict(role='user', content='current concern')],
               selected_keys=['r'] if on else [], selected_resource_identities=['source'] if on else [],
               catalog_identity='catalog', usage=dict(resource_tokens=10 if on else 0, input_tokens=30,
               native_context_limit=1000, native_remaining_tokens=970, within_native_context=True, truncation=False),
               reusable_old_requests=[])
    row['identity'] = digest({k:row[k] for k in FIELDS})
    return row


@pytest.mark.parametrize('on', [False, True])
def test_only_generic_instruction_changes_visible_content_and_identity(on):
    original = item(on); snapshot = deepcopy(original); changed = intervene(original, lambda _: 150)
    assert original == snapshot
    assert changed['messages'][0]['content'].replace('\n' + INSTRUCTION, '', 1) == original['messages'][0]['content']
    assert changed['messages'][1:] == original['messages'][1:]
    assert changed['selected_resource_identities'] == original['selected_resource_identities']
    assert changed['renderer_identity'] != original['renderer_identity']
    req = request_for(changed, runtime={'identity':'runtime'}, draw_identity='probe', code_identity='code')
    assert req['provenance']['selected_keys'] == original['selected_keys']
    assert req['messages'] == changed['messages']
    with pytest.raises(ValueError, match='already modified'):
        intervene(changed, lambda _: 150)


def test_disguised_off_and_false_resource_addresses_rejected():
    forged = item(True); forged['selected_keys'] = []; forged['selected_resource_identities'] = []
    forged['usage']['resource_tokens'] = 0; forged['identity'] = digest({k:forged[k] for k in FIELDS})
    with pytest.raises(ValueError, match='OFF contains resources'):
        intervene(forged, lambda _: 150)
    forged = item(True); forged['selected_keys'] = ['different']; forged['identity'] = digest({k:forged[k] for k in FIELDS})
    with pytest.raises(ValueError, match='addresses differ'):
        intervene(forged, lambda _: 150)
