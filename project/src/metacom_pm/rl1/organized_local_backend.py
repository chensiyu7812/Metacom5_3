"""Organized G worker using the already reviewed latest-snapshot GPU rule.

Keep the historical backend bytes frozen for the active scoring experiment.
Only loading admission and its explicit directory binding differ; generation,
model identity, decoding, journaling and finite call accounting are inherited.
"""
from pathlib import Path
import os
import time

from .local_backend import LocalBackend, ENGINEERING, authorize, check_static
from .local_gpu_guard import LocalGPUCheck
from .schema import digest
from .supervised_learning import save_json


class OrganizedLocalBackend(LocalBackend):
    def _ensure(self):
        if self.protocol['scope'] == ENGINEERING:
            return super()._ensure()
        authorize(self.protocol, self.approval)
        if (self.protocol.get('gpu_sampling_policy') != 'last_xml'
                or self.protocol.get('run_directory') != str(self.root.resolve())):
            raise ValueError('organized GPU sampling policy or fixed run directory changed')
        self.root.mkdir(parents=True, exist_ok=True, mode=0o700)
        from .durable import save_json_once
        save_json_once(self.root/'BACKEND.json', self.protocol)
        if self.generator is not None:
            self.gpu_guard.check(own_pid=os.getpid())
            return
        loads = sorted(self.root.glob('load_*.started.json'))
        if len(loads) >= self.protocol['max_loads']:
            raise ValueError('load envelope exhausted; interrupted load is not retried')
        if any(os.environ.get(k) != '1' for k in ('HF_HUB_OFFLINE', 'TRANSFORMERS_OFFLINE')):
            raise ValueError('offline local model loading required')
        check_static(self.protocol)
        self.gpu_guard = LocalGPUCheck(self.protocol['gpu_uuid'], self.protocol['runtime'],
                                      self.root/'gpu_checks', latest_snapshot=True)
        self.gpu_guard.check()
        index = len(loads)
        save_json(self.root/f'load_{index:04d}.started.json', dict(protocol_identity=self.identity))
        started = time.monotonic()
        self.generator = self.generator_factory(self.protocol['runtime'])
        observed = dict(self.generator.manifest, identity=self.generator.identity)
        save_json(self.root/f'load_{index:04d}.observed.json', dict(
            status='LOADER_RETURNED_NOT_YET_VALIDATED', runtime=observed,
            canonical_runtime_identity=digest(observed), seconds=time.monotonic()-started))
        if (digest(observed) != digest(self.protocol['runtime'])
                or digest(self.generator.manifest) != self.generator.identity):
            self.generator = None
            raise ValueError('loaded generator differs from frozen runtime')
        save_json(self.root/f'load_{index:04d}.done.json', dict(
            runtime=self.protocol['runtime'], seconds=time.monotonic()-started))
