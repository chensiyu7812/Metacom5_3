"""Explicit dispatch of preserved legacy and new organized request identities."""
from .bound_generation import validate_and_project as legacy_project
from .organized_feedback import VERSION, visible_generation_request


def project(request, runtime_identity):
    if request.get('version') != VERSION:
        return legacy_project(request, runtime_identity)
    expected = {'version','executor_identity','renderer_identity','draw_identity','messages',
                'expected_input_tokens','provenance','request_id'}
    p = request.get('provenance', {})
    fields = {'prefix_identity','catalog_identity','interface_identity','retrieval_method',
              'selected_resource_identities','selected_keys','usage'}
    if (set(request) != expected or request['executor_identity'] != runtime_identity
            or set(p) != fields or type(request['expected_input_tokens']) is not int
            or request['expected_input_tokens'] < 1
            or not all(isinstance(p[k],str) and p[k] for k in (
                'prefix_identity','catalog_identity','interface_identity','retrieval_method'))
            or len(p['selected_keys']) != len(set(p['selected_keys']))
            or len(p['selected_keys']) != len(p['selected_resource_identities'])
            or p['usage'].get('input_tokens') != request['expected_input_tokens']
            or p['usage'].get('truncation') is not False
            or p['usage'].get('within_native_context') is not True):
        raise ValueError('complete organized generation source/runtime/input length required')
    return visible_generation_request(request)
