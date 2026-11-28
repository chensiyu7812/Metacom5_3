"""NAA run admission. No approval is created here, by a manifest, by a test or by a dry run.

A real model run requires a researcher-written approval bound to the exact manifest
SHA, caps, model labels and the clean checkout HEAD. Without it the runner refuses
BEFORE any GPU census, lock, model byte read or worker spawn. Old A0/PP1/GE2/G6
approvals cannot transfer (different protocol and manifest identity).
"""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from ..data.contracts import digest
from ...rl1v3.generator.limited_run import AdmissionError, require

APPROVAL_PROTOCOL = 'naa-wp2-approval-v1'
MANIFEST_PROTOCOL = 'naa-wp2-manifest-v1'


def manifest_sha256(manifest):
    return digest(manifest)


def load_manifest(path):
    manifest = json.loads(Path(path).read_text())
    require(manifest.get('protocol') == MANIFEST_PROTOCOL, 'unknown manifest protocol')
    require(manifest.get('authorized') is False, 'a manifest is never an authorization')
    return manifest


def authorize(manifest, approval, *, root):
    require(isinstance(approval, dict), 'approval object')
    require(approval.get('protocol') == APPROVAL_PROTOCOL, 'approval protocol (old approvals cannot transfer)')
    require(approval.get('authorized') is True, 'no explicit authorization')
    require(approval.get('manifest_sha256') == manifest_sha256(manifest), 'approval bound to a different manifest')
    caps = manifest['caps']
    require(type(approval.get('max_physical_calls')) is int
            and 0 < approval['max_physical_calls'] <= caps['max_physical_calls'], 'approved physical call cap')
    require(isinstance(approval.get('max_gpu_seconds'), (int, float))
            and 0 < approval['max_gpu_seconds'] <= caps['max_gpu_seconds'], 'approved GPU seconds')
    if 'per_model_gpu_seconds' in approval:
        share = caps.get('per_model_gpu_seconds') or caps['max_gpu_seconds'] / len(manifest['model_order'])
        require(0 < approval['per_model_gpu_seconds'] <= share, 'approved per-model GPU seconds')
    require(set(approval.get('models', ())) <= set(manifest['model_order'])
            and approval.get('models'), 'approved model labels')
    require(bool(approval.get('researcher')) and bool(approval.get('decision_evidence')),
            'researcher signature/evidence missing')
    head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
    require(approval.get('executor_checkout_head') == head, 'approval must pin actual checkout HEAD')
    dirty = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root, text=True)
    require(not dirty, 'dirty tracked checkout')
    return approval


def refuse_without(approval_path):
    if approval_path is None or not Path(approval_path).is_file():
        raise AdmissionError('no approval file: model execution refused (CPU preparation only)')
    return json.loads(Path(approval_path).read_text())
