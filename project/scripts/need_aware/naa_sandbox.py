#!/usr/bin/env python3
"""Run a naa_agent.py CPU stage inside a bubblewrap mount namespace without evaluation data.

Only runtime inputs (A runtime root, Direct coordinates, A model inventory), the B private
root, source code, the Python env and model tokenizer/encoder files are mounted; the
evaluation sidecar, training targets and raw source dataset are absent from the
namespace, and the network is unshared. The child re-checks the denial before running.
Model execution (`infer` without --plumbing) is not available here by design.
"""
import argparse
from pathlib import Path
import subprocess
import sys

NAA = Path('/opt/tokkio-data0/naa/20261127')
DENY = [NAA / 'artifacts/evaluation', NAA / 'artifacts/training', NAA / 'source']
READ = [Path('/opt/tokkio-data0/tokkio_envs/paper1-judges-py312'), Path('/opt/tokkio-data0/tokkio_envs/paper1-mistral-vllm-py312'),
        Path('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3'), Path('/opt/tokkio-data0/tokkio_models/paper1_judges/qwen35_9b'),
        Path('/opt/tokkio-data0/tokkio_models/huggingface/hub/models--BAAI--bge-small-en-v1.5'),
        NAA / 'artifacts/runtime', NAA / 'artifacts/direct', NAA / 'logs/native']
PY = '/opt/tokkio-data0/tokkio_envs/paper1-judges-py312/bin/python'


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--b-root', required=True)
    p.add_argument('args', nargs=argparse.REMAINDER)
    a = p.parse_args()
    args = a.args[1:] if a.args[:1] == ['--'] else a.args
    if not args or args[0] not in {'write', 'embed', 'retrieve', 'materialize', 'infer', 'export', 'aggregate'}:
        raise SystemExit('unknown stage')
    if args[0] == 'infer' and '--plumbing' not in args:
        raise SystemExit('model execution is not available inside the CPU sandbox')
    project = Path(__file__).resolve().parents[2]
    b_root = Path(a.b_root).resolve()
    cmd = ['bwrap', '--die-with-parent', '--new-session', '--unshare-all', '--clearenv',
           '--ro-bind', '/usr', '/usr', '--ro-bind', '/lib', '/lib', '--ro-bind', '/lib64', '/lib64',
           '--ro-bind', '/etc', '/etc', '--proc', '/proc', '--dev', '/dev', '--tmpfs', '/tmp']
    for r in READ:
        cmd += ['--ro-bind', str(r), str(r)]
    cmd += ['--ro-bind', str(project / 'src'), str(project / 'src'),
            '--ro-bind', str(project / 'scripts'), str(project / 'scripts'),
            '--bind', str(b_root), str(b_root),
            '--setenv', 'PYTHONPATH', str(project / 'src'), '--setenv', 'PYTHONDONTWRITEBYTECODE', '1',
            '--setenv', 'PYTHONNOUSERSITE', '1', '--setenv', 'PYTHONUTF8', '1', '--setenv', 'LANG', 'C.UTF-8',
            '--setenv', 'HF_HUB_OFFLINE', '1', '--setenv', 'TRANSFORMERS_OFFLINE', '1', '--setenv', 'CUDA_VISIBLE_DEVICES', '',
            '--setenv', 'HOME', '/tmp', '--setenv', 'NAA_DENY_PATHS', ':'.join(map(str, DENY)),
            PY, str(project / 'scripts/need_aware/naa_agent.py'), *args]
    sys.exit(subprocess.run(cmd).returncode)


if __name__ == '__main__':
    main()
