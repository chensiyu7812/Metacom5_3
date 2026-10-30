"""G-only, source-addressed fixed comparisons, with the original decoding code.

New request provenance never pretends to be the old <=4-count protocol. A new
execution-wrapper identity binds the unchanged base model/runtime and projection.
Neither import nor preparation loads a model. Unknown starts are never repeated.
"""
from copy import deepcopy
import fcntl
import json
import os
from pathlib import Path
import time

from .calibration_workflow import stamp, verify_identity
from .durable import save_json_once as save_once
from .generation import LocalNaturalGenerator
from .local_backend import load_generator, check_static
from .schema import digest

VERSION = 'pmrl1-addressed-fixed-generation-v2-20261030'


def execution_identity(runtime, code_identity):
    return digest(dict(version=VERSION, base_runtime=runtime['identity'], code_identity=code_identity,
                       projection='original LocalNaturalGenerator.generate; messages-only'))


def request_for(row, *, runtime, draw_identity, code_identity):
    identity_fields = ('prefix_identity','executor_identity','renderer_identity','renderer_route','messages',
                       'selected_keys','selected_resource_identities','catalog_identity','usage')
    if row['identity'] != digest({k:row[k] for k in identity_fields}):
        raise ValueError('prepared input identity changed')
    if row['executor_identity'] != runtime['identity'] or row['reusable_old_requests']:
        raise ValueError('new execution requires an unchanged base runtime and a fresh input')
    if (len(row['selected_keys']) != len(set(row['selected_keys'])) or
            len(row['selected_keys']) != len(row['selected_resource_identities']) or not row['selected_keys']):
        raise ValueError('unique explicit selected resources required')
    return stamp(dict(version=VERSION, prepared_input_identity=row['identity'],
        execution_identity=execution_identity(runtime, code_identity), base_runtime_identity=runtime['identity'],
        draw_identity=draw_identity, renderer_identity=row['renderer_identity'], messages=deepcopy(row['messages']),
        provenance=dict(prefix_identity=row['prefix_identity'], catalog_identity=row['catalog_identity'],
            selected_keys=list(row['selected_keys']), selected_resource_identities=list(row['selected_resource_identities'])),
        expected_input_tokens=row['usage']['input_tokens']))


def visible_request(request, runtime, code_identity):
    verify_identity(request)
    if (request['version'] != VERSION or request['base_runtime_identity'] != runtime['identity']
            or request['execution_identity'] != execution_identity(runtime, code_identity)):
        raise ValueError('addressed request/execution identity changed')
    body = dict(messages=deepcopy(request['messages']), executor_identity=runtime['identity'],
                draw_identity=request['draw_identity'], renderer_identity=request['renderer_identity'])
    return dict(request_id=digest(body), **body)


def protocol_for(requests, *, runtime, assets, packages, gpu_uuid, code_identity,
                 source_package_identity, engineering=False, run_directory=None):
    verify_identity(runtime)
    if not requests or len({x['identity'] for x in requests}) != len(requests):
        raise ValueError('finite unique request set required')
    for x in requests: visible_request(x, runtime, code_identity)
    if not engineering and run_directory is None: raise ValueError('fixed production run directory required')
    return stamp(dict(version=VERSION, scope='ENGINEERING_ONLY' if engineering else 'BOUNDED_RESOURCE_COMPARISON',
        runtime=runtime, assets=assets, packages=packages, gpu_uuid=gpu_uuid, code_identity=code_identity,
        source_package_identity=source_package_identity, request_ids=[x['identity'] for x in requests],
        max_G_loads=1, max_G_calls=len(requests), max_BGE_loads=0, max_BGE_calls=0,
        API_calls=0, automatic_retry=False, training_updates=0,gpu_sampling_policy='last_xml',
        run_directory=str(Path(run_directory).resolve()) if run_directory else None))


def authorize(protocol, approval):
    verify_identity(protocol)
    if protocol['scope'] == 'ENGINEERING_ONLY': return
    if (protocol['scope'] != 'BOUNDED_RESOURCE_COMPARISON' or not isinstance(approval,dict)
            or approval.get('status') != 'APPROVED' or approval.get('protocol_identity') != protocol['identity']
            or approval.get('operations') != ['resource_comparison_generation']
            or not approval.get('user_authorization_reference')):
        raise ValueError('this fixed G-only comparison stage is not authorized')
    from metacom_pm.io import sha256_file as sha
    record = approval.get('researcher_authorization_record')
    if not record or sha(Path(record)) != approval.get('researcher_record_sha256'):
        raise ValueError('actual researcher authorization record required')


class FixedResourceComparison:
    def __init__(self, protocol, requests, root, *, approval=None, factory=None, guard=None, invoke=None):
        verify_identity(protocol)
        if [r['identity'] for r in requests] != protocol['request_ids']: raise ValueError('fixed request set/order changed')
        for r in requests: visible_request(r, protocol['runtime'], protocol['code_identity'])
        engineering = protocol['scope'] == 'ENGINEERING_ONLY'
        if engineering != all(x is not None for x in (factory, guard, invoke)):
            raise ValueError('synthetic stage needs all doubles; production accepts none')
        if not engineering and any(x is not None for x in (factory,guard,invoke)):
            raise ValueError('production cannot inject a different model implementation')
        self.protocol, self.requests, self.approval = deepcopy((protocol,requests,approval))
        self.root = Path(root); self.generator = None; self.factory = factory or load_generator
        if not engineering and str(self.root.resolve()) != protocol['run_directory']:
            raise ValueError('fixed run directory changed; cannot reset load or call allowance')
        self.guard = guard; self.invoke = invoke or LocalNaturalGenerator.generate

    def _load(self):
        if self.generator is not None:
            self.guard.check(own_pid=os.getpid()); return
        if (self.root/'load.started.json').exists():
            raise ValueError('one-load scope used; no implicit reload after process loss')
        if self.protocol['scope'] != 'ENGINEERING_ONLY':
            if any(os.environ.get(k) != '1' for k in ('HF_HUB_OFFLINE','TRANSFORMERS_OFFLINE')):
                raise ValueError('offline local-only loading required')
            check_static(self.protocol)
            from .local_gpu_guard import LocalGPUCheck
            if self.protocol.get('gpu_sampling_policy')!='last_xml':raise ValueError('GPU sampling policy changed')
            self.guard = LocalGPUCheck(self.protocol['gpu_uuid'], self.protocol['runtime'], self.root/'gpu_checks',latest_snapshot=True)
        self.guard.check()
        save_once(self.root/'load.started.json', dict(protocol_identity=self.protocol['identity']))
        start = time.monotonic(); g = self.factory(self.protocol['runtime'])
        observed = dict(g.manifest, identity=g.identity)
        save_once(self.root/'load.observed.json', dict(runtime=observed, seconds=time.monotonic()-start))
        if digest(observed) != digest(self.protocol['runtime']) or digest(g.manifest) != g.identity:
            raise ValueError('loaded original model/runtime identity mismatch')
        self.generator = g
        save_once(self.root/'load.done.json', dict(runtime_identity=g.identity))

    def _validate(self, request, result):
        visible = visible_request(request, self.protocol['runtime'], self.protocol['code_identity'])
        if (result.get('request_id') != visible['request_id'] or result.get('runtime_identity') != self.protocol['runtime']['identity']
                or result.get('input_tokens') != request['expected_input_tokens']
                or result.get('finish_reason') not in ('natural_stop','technical_timeout','repetition_guard','context_exhausted','unexpected_stop','empty_output')
                or result.get('api_cost_usd') != 0):
            raise ValueError('G output/runtime/input-token/finish binding changed')
        if result['finish_reason']=='natural_stop' and (not isinstance(result.get('text'), str) or not result['text'].strip()):
            raise ValueError('empty completed reply')

    def step(self):
        authorize(self.protocol, self.approval)
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        with (self.root/'.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            save_once(self.root/'PROTOCOL.json', self.protocol)
            completed = []
            for request in self.requests:
                key = request['identity']; started = self.root/(key+'.started.json')
                raw = self.root/(key+'.raw.json'); sealed = self.root/(key+'.sealed.json')
                if sealed.exists():
                    result = json.loads(raw.read_text()); self._validate(request,result)
                    receipt = json.loads(sealed.read_text()); verify_identity(receipt)
                    if receipt['request_identity'] != key or receipt['raw_identity'] != digest(result) or receipt['protocol_identity'] != self.protocol['identity']:
                        raise ValueError('sealed result changed')
                    completed.append(receipt); continue
                if started.exists():
                    if json.loads(started.read_text()) != dict(protocol_identity=self.protocol['identity'],request=request):
                        raise ValueError('started request changed')
                    if not raw.exists():
                        return dict(status='RECONCILIATION_REQUIRED', request_identity=key, reason='unknown previous model entry')
                    result = json.loads(raw.read_text()); self._validate(request,result)
                    recovered = True
                else:
                    self._load()  # A known GPU preflight failure never marks a G request started.
                    save_once(started, dict(protocol_identity=self.protocol['identity'],request=request))
                    result = self.invoke(self.generator, visible_request(request,self.protocol['runtime'],self.protocol['code_identity']))
                    save_once(raw,result); self._validate(request,result); recovered = False
                receipt = stamp(dict(protocol_identity=self.protocol['identity'], request_identity=key,
                    execution_identity=request['execution_identity'], raw_identity=digest(result),
                    provenance_identity=digest(request['provenance']), finish_reason=result['finish_reason'],
                    reward=None, measurement_qualified=False))
                save_once(sealed,receipt)
                return dict(status='GENERATION_RECORDED',request_identity=key,finish_reason=result['finish_reason'],
                            recovered_without_model_call=recovered)
            result = stamp(dict(status='CLOSED_FIXED_COMPARISON', protocol_identity=self.protocol['identity'],
                completed=len(completed), natural_stops=sum(r['finish_reason']=='natural_stop' for r in completed),
                non_natural=sum(r['finish_reason']!='natural_stop' for r in completed), API_calls=0,
                training_updates=0, quality_effect='not_evaluated'))
            save_once(self.root/'CLOSED.json',result)
            return result
