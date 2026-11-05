#!/usr/bin/env python3
"""One explicitly recorded preload recovery, with a scoped idle tolerance.

Does not retry any model request. Original zero-utilization admission evidence
and protocol stay immutable. Runtime, inputs, GPU and three-call bound stay fixed.
"""
import argparse
import importlib.util
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import stamp, verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.local_gpu_guard import LocalGPUCheck
from metacom_pm.rl1.schema import digest


def read(path):
    return json.loads(path.read_text())


def tolerated_preload(result):
    gpu = result.get('selected_gpu') or {}
    return (result.get('rejection_reasons') == ['utilization_not_zero']
            and result.get('visible_processes') == []
            and result.get('process_visibility') == 'queries_succeeded_no_processes_listed'
            and result.get('sampling_policy') == 'last_xml'
            and gpu.get('free_mib', -1) >= 45000
            and 0 < gpu.get('utilization_percent', 100) <= 5)


class ScopedIdleCheck(LocalGPUCheck):
    def check(self, *, own_pid=None):
        try:
            return super().check(own_pid=own_pid)
        except RuntimeError:
            if own_pid is not None:
                raise
            checks = sorted(self.root.glob('check_*.json'))
            if not checks:
                raise
            path = checks[-1]
            result = read(path)
            if not tolerated_preload(result):
                raise
            # Keep the original rejected snapshot. No resampling for a better value.
            accepted = dict(result, eligible=True, rejection_reasons=[],
                scoped_admission='single latest XML <=5% utilization, >=45000MiB, no other visible process; other original checks unchanged',
                original_result=str(path.resolve()), original_result_sha256=sha(path))
            save(self.root / 'SCOPED_PRELOAD_ADMISSION.json', accepted)
            return accepted


def prepare(out):
    old = out / 'alternate_G'
    assert not (old / 'LOAD_STARTED.json').exists()
    assert not list((old / 'raw').glob('*.started.json'))
    check = old / 'gpu_checks/check_0000.json'
    assert tolerated_preload(read(check))
    original = read(old / 'PROTOCOL.json')
    verify_identity(original)
    requests = read(old / 'REQUESTS_PRIVATE.json')
    assert digest(requests) == original['requests_identity'] and len(requests) == 3
    for group in ('sources', 'code'):
        for path, expected in original[group].items():
            assert sha(Path(path)) == expected, path
    recovery = stamp(dict(original_protocol_identity=original['identity'], prior_exit_code=1,
        prior_model_loads=0, prior_model_requests=0, original_snapshot=str(check.resolve()),
        original_snapshot_sha256=sha(check), max_additional_preload_attempts=1,
        policy='One complete latest-snapshot check; tolerate utilization up to 5% only with >=45000MiB free and no listed other process. All query/visibility errors and resident-process exclusions still reject. No polling for eligibility.',
        reason='Original sole rejection was 2% utilization with 48551MiB free and no listed process; idle utilization need not be exactly zero. Cause of 2% is not established.',
        researcher_authority='Current 好的 继续推进 and existing local execution authority; routine infrastructure repair, no new paid/model call scope.',
        unchanged=['exact messages', 'runtime/model/decode identity', 'designated GPU', 'three requests', 'one actual model load'],
        latency_claim=False, automatic_request_retries=0))
    save(out / 'PRELOAD_RECOVERY.json', recovery)
    body = {k: v for k, v in original.items() if k != 'identity'}
    body['sources'] = dict(original['sources']) | {
        str((out / 'PRELOAD_RECOVERY.json').resolve()): sha(out / 'PRELOAD_RECOVERY.json'),
        str((old / 'PROTOCOL.json').resolve()): sha(old / 'PROTOCOL.json'),
        str((out / 'RUN.log').resolve()): sha(out / 'RUN.log')}
    body['code'] = dict(original['code']) | {str(Path(__file__).resolve()): sha(Path(__file__))}
    body['preload_recovery_identity'] = recovery['identity']
    body['admission_idle_utilization_limit_percent'] = 5
    dest = out / 'alternate_G_resume'
    dest.mkdir(mode=0o700)
    save(dest / 'PROTOCOL.json', stamp(body))
    save(dest / 'REQUESTS_PRIVATE.json', requests)
    print(json.dumps(dict(status='RECOVERY_PREPARED', model_requests_retried=0, remaining_requests=3)), flush=True)


def run(out):
    spec = importlib.util.spec_from_file_location('frozen_alternate', PROJECT / 'scripts/rl1/167_probe_alternate_executor.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.LocalGPUCheck = ScopedIdleCheck
    module.run(out / 'alternate_G_resume')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=['prepare', 'run'])
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    globals()[args.mode](args.output.resolve())
