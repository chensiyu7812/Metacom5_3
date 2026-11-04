"""One opt-in instruction intervention with exact OFF/resource input preservation.

The fixed G runner accepts its original messages-only wire format. This adapter
also constructs genuine OFF requests, which its resource-only factory excludes.
No dummy resource, source annotation, target answer or reward is introduced.
"""
from copy import deepcopy
import json

from .calibration_workflow import stamp
from .resource_comparison_runner import VERSION as WIRE_VERSION, execution_identity, visible_request
from .schema import digest

VERSION = 'pmrl1-current-need-executor-probe-v1'
INSTRUCTION = (
    "Prioritize the user's present concern and explicitly expressed preferences. "
    "Use an optional record only when it helps you choose a more relevant response now, "
    "for example by respecting a constraint, avoiding an already-tried suggestion, or "
    "building on what the user has said they need. A true historical detail is not, "
    "by itself, a reason to mention it. Do not move to another problem merely because "
    "a record discusses it. Do not infer a stable preference for advice or reflection "
    "from a past activity. When the benefit is unclear, a focused reflection or question "
    "is appropriate. Do not require advice, a memory mention, or a longer reply. "
    "Give the reply directly, without an evidence checklist or analysis."
)
FIELDS = ('prefix_identity', 'executor_identity', 'renderer_identity', 'renderer_route', 'messages',
          'selected_keys', 'selected_resource_identities', 'catalog_identity', 'usage')
MARKER = '\n<quoted_conversation_context>'


def check_input(item):
    if item['identity'] != digest({k:item[k] for k in FIELDS}):
        raise ValueError('input identity mismatch')
    messages = item['messages']
    if len(messages) != 2 or [m['role'] for m in messages] != ['system', 'user']:
        raise ValueError('exact two-message direct-reply input required')
    keys = item['selected_keys']
    if len(keys) != len(set(keys)) or len(keys) != len(item['selected_resource_identities']):
        raise ValueError('invalid resource provenance')
    system = messages[0]['content']
    if not keys:
        if '<resources>' in system or item['usage']['resource_tokens'] != 0:
            raise ValueError('OFF contains resources')
    else:
        resources = json.loads(system.split('<resources>\n', 1)[1].split('\n</resources>', 1)[0])
        if [r['address'] for r in resources] != keys:
            raise ValueError('resource addresses differ from provenance')


def intervene(item, count_chat):
    check_input(item)
    changed = deepcopy(item)
    system = changed['messages'][0]['content']
    if system.count(MARKER) != 1 or INSTRUCTION in system:
        raise ValueError('unsupported or already modified system input')
    changed['messages'][0]['content'] = system.replace(MARKER, '\n' + INSTRUCTION + MARKER, 1)
    changed['renderer_identity'] = digest(dict(parent=item['renderer_identity'], version=VERSION, instruction=INSTRUCTION))
    changed['renderer_route'] = VERSION
    tokens = count_chat(changed['messages'])
    usage = changed['usage']
    usage.update(input_tokens=tokens, native_remaining_tokens=usage['native_context_limit'] - tokens,
                 within_native_context=tokens < usage['native_context_limit'])
    if not usage['within_native_context'] or usage['truncation']:
        raise ValueError('complete input exceeds native capacity')
    changed['identity'] = digest({k:changed[k] for k in FIELDS})
    check_input(changed)
    return changed


def request_for(item, *, runtime, draw_identity, code_identity):
    check_input(item)
    if item['executor_identity'] != runtime['identity']:
        raise ValueError('executor changed')
    request = stamp(dict(version=WIRE_VERSION, prepared_input_identity=item['identity'],
        execution_identity=execution_identity(runtime, code_identity), base_runtime_identity=runtime['identity'],
        draw_identity=draw_identity, renderer_identity=item['renderer_identity'], messages=deepcopy(item['messages']),
        provenance={k:deepcopy(item[k]) for k in ('prefix_identity', 'catalog_identity', 'selected_keys', 'selected_resource_identities')},
        expected_input_tokens=item['usage']['input_tokens']))
    visible_request(request, runtime, code_identity)
    return request
