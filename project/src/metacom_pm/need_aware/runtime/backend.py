"""NAA generation backends.

NAAHFBackend reuses the historical GE2 supervisor transport (bounded exchange,
device polling, immutable WIRE_FAILURE evidence, process-group kill on close) and
the A6000 device guard from limited_run; it only changes which worker is launched
(NAA hf_worker, under the NAA guard whose bound comes from the approved budget).

PlumbingBackend is a CPU stand-in for dry runs. Its outputs are labelled
result_kind='plumbing', contain no model text and can never be scored as a model.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import time

from ...rl1v3.generator import limited_run as L
from ...rl1v3.journal.ge2_worker import SubprocessGE2HF
from ...rl1v3.journal.pomdp_latency import MonotonicClock, duration_ns
from .budget import SafetyStop

PLUMBING_TEXT = 'PLUMBING-DRY-RUN: no model was called.'
_DEVICE_GUARD = L.device_guard          # the historical A6000 guard, captured before any patching


def safe_device_guard(*args, **kwargs):
    """Historical device guard; a refusal (other process, memory floor, identity) is a global safety stop."""
    try:
        return _DEVICE_GUARD(*args, **kwargs)
    except L.AdmissionError as exc:
        raise SafetyStop('device guard: ' + str(exc)) from exc


def safe_storage_guard(run_root):
    try:
        return L.storage_guard(run_root)
    except L.AdmissionError as exc:
        raise SafetyStop('storage guard: ' + str(exc)) from exc


class NAAHFBackend(SubprocessGE2HF):
    kind = 'hf_real_naa'

    def __init__(self, root, spec, manifest, out, deadline, *, guard_bound_s, device_guard=safe_device_guard):
        plan = dict(scope_sha256=manifest['scope_sha256'], python=manifest['runtime']['python_executable'])
        super().__init__(root, plan, {'spec': spec}, out, deadline)
        self.spec, self.manifest, self.guard_bound_s = spec, manifest, guard_bound_s
        self._device_guard = device_guard

    def _exchange(self, command, seconds):
        # The parent transport calls limited_run.device_guard on every poll; keep that call
        # path, but allow an injected guard so CPU tests can exercise the real transport.
        original = L.device_guard
        if self._device_guard is original:
            return super()._exchange(command, seconds)
        L.device_guard = self._device_guard
        try:
            return super()._exchange(command, seconds)
        finally:
            L.device_guard = original

    def load(self, seconds):
        L.require(self.p is None, 'one model load per backend session')
        L.require(time.monotonic() < self.deadline, 'global deadline before load')
        self._device_guard(initial=True)
        self.out.mkdir(parents=True, exist_ok=True)
        self.error = (self.out / 'worker.stderr.log').open('xb')
        cache = self.out / 'cache'
        env = dict(os.environ, PYTHONPATH=str(self.root / 'project/src'),
                   CUDA_VISIBLE_DEVICES=L.GPU, CUBLAS_WORKSPACE_CONFIG=':4096:8', HF_HUB_OFFLINE='1',
                   TRANSFORMERS_OFFLINE='1', PYTHONNOUSERSITE='1', PYTHONDONTWRITEBYTECODE='1',
                   HF_HOME=str(cache), TRITON_CACHE_DIR=str(cache / 'triton'), TORCH_HOME=str(cache / 'torch'),
                   PMRL1_LIMITED_SUPERVISOR_PID=str(os.getpid()), PMRL1_LIMITED_DEADLINE=str(self.deadline),
                   NAA_GUARD_MAX_SECONDS=str(self.guard_bound_s))
        clock = MonotonicClock(); spawn = clock.stamp()
        self.p = subprocess.Popen([sys.executable, '-m', 'metacom_pm.need_aware.runtime.worker_guard',
                                   self.plan['python'], '-m', self.manifest['runtime']['worker_module']],
                                  cwd=self.out, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=self.error,
                                  env=env, start_new_session=True)
        command = dict(operation='load', spec=self.spec, runtime=self.manifest['runtime'],
                       header_sha256=self.manifest['checkpoints'][self.spec['label']]['header_sha256'],
                       allowed_missing=self.manifest['checkpoints'][self.spec['label']].get('allowed_missing', []),
                       allowed_unused=self.manifest['checkpoints'][self.spec['label']].get('allowed_unused', []),
                       # WP4 adapted generators: {path, sha256} bound in the manifest; absent for base G
                       adapter=self.manifest['checkpoints'][self.spec['label']].get('adapter'),
                       boot_id=clock.boot_id, deadline_ns=int(min(self.deadline, time.monotonic() + seconds) * 1e9))
        result = self._exchange(command, seconds)
        done = clock.stamp()
        result.update(supervisor_load_ns=duration_ns(spawn, done),
                      supervisor_load_scope='spawn + guard + worker load + IPC, inclusive')
        return result

    def generate(self, request, seconds):
        clock = MonotonicClock(); started = clock.stamp()
        deadline_ns = int(min(self.deadline, time.monotonic() + seconds) * 1e9)
        result = self._exchange(dict(operation='generate', request=request, deadline_ns=deadline_ns,
                                     input_cap=self.manifest['caps']['input_cap'],
                                     backend_cap=self.manifest['caps']['backend_cap']), seconds)
        result['supervisor_exchange_ns'] = duration_ns(started, clock.stamp())
        return result


class PlumbingBackend:
    """Deterministic CPU stand-in. Exercises ledger/budget/resume/export only."""
    kind = 'plumbing_cpu'

    def __init__(self, spec, *, fail_on=()):
        self.spec = spec; self.loaded = False; self.calls = 0; self.fail_on = set(fail_on)

    def load(self, seconds):
        L.require(not self.loaded, 'one load per session'); self.loaded = True
        return dict(load_ns=0, model_loads=1, warmup_calls=0, plumbing=True)

    def generate(self, request, seconds):
        L.require(self.loaded, 'load required'); self.calls += 1
        if request['request_sha256'] in self.fail_on:
            raise L.AdmissionError('injected plumbing failure')
        return dict(token_ids=[request['decode']['eos_token_id'][0]], text=PLUMBING_TEXT, finish_reason='eos', input_tokens=len(request['input_ids']),
                    output_tokens=1, generation_ns=0, first_output_observation=None, plumbing=True)

    def close(self):
        self.loaded = False
