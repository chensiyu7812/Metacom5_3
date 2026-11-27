"""NAA batch scope and call budget, derived from one frozen manifest + one approval.

Replaces nothing in GE2: the historical WorkerCallBudget (two tasks, 8-10 terminal
slots) keeps guarding GE2. This class only admits physical calls whose exact
request_sha256 is listed in the NAA manifest, within the approved caps, and counts
calls already recorded in the ledger so a resumed run cannot exceed them.

v2 stop scopes (typed, so the runner never confuses them):
  GlobalStop  -- global GPU seconds, total physical attempts, scope/integrity violation,
                 device/storage safety (SafetyStop): the whole experiment stops.
  ModelStop   -- this model's GPU-second share, its load cap, its consecutive failures
                 or its technical smoke: release the device, continue with the next model.
  RequestSkip -- this request's attempt cap or the global retry headroom: skip it only.
"""
from __future__ import annotations

from collections import Counter

from ...rl1v3.generator.limited_run import AdmissionError

BUDGET_VERSION = 'naa-batch-budget-v2'


class GlobalStop(AdmissionError):
    scope = 'global'


class SafetyStop(GlobalStop):
    scope = 'global_safety'


class ModelStop(AdmissionError):
    scope = 'model'


class RequestSkip(AdmissionError):
    scope = 'request'


class NAABatchBudget:
    def __init__(self, manifest, approval, ledger):
        caps = manifest['caps']
        self.allowed = {}
        for row in manifest['requests']:
            if row['status'] == 'ready' and 'duplicate_of' not in row:
                self.allowed[row['request_sha256']] = row['model_label']
        if len(self.allowed) != manifest['counts']['physical_unique']:
            raise GlobalStop('manifest physical identity count')
        self.max_physical = min(caps['max_physical_calls'], approval['max_physical_calls'])
        self.max_gpu_seconds = min(caps['max_gpu_seconds'], approval['max_gpu_seconds'])
        self.max_attempts = caps['max_attempts_per_request']
        self.max_retries_total = caps['max_retries_total']
        self.max_loads = caps['max_model_loads_per_model']
        self.models = tuple(approval['models'])
        share = caps.get('per_model_gpu_seconds') or self.max_gpu_seconds / max(1, len(self.models))
        self.per_model_seconds = min(share, approval.get('per_model_gpu_seconds', share))
        self.ledger = ledger

    def state(self):
        attempts = self.ledger.attempts()
        return dict(physical=self.ledger.physical_calls(), gpu_seconds=self.ledger.gpu_seconds(),
                    retries=sum(max(0, n - 1) for n in attempts.values()), attempts=attempts,
                    loads=self.ledger.model_loads())

    def seconds_left(self, model_label, session_id=None, session_elapsed_s=0.):
        """(global, model) remaining GPU seconds: earlier sessions + the live session's elapsed time."""
        total = self.ledger.gpu_seconds(exclude_session=session_id) + session_elapsed_s
        own = self.ledger.gpu_seconds(model_label, exclude_session=session_id) + session_elapsed_s
        return self.max_gpu_seconds - total, self.per_model_seconds - own

    def claim_load(self, model_label):
        if model_label not in self.models:
            raise ModelStop('model not approved: ' + model_label)
        s = self.state()
        if s['physical'] >= self.max_physical:
            raise GlobalStop('physical call cap')
        g, m = self.seconds_left(model_label)
        if g <= 0:
            raise GlobalStop('global GPU seconds cap')
        if m <= 0:
            raise ModelStop('per-model GPU seconds share')
        if s['loads'][model_label] >= self.max_loads:
            raise ModelStop('model load cap')
        return min(g, m)

    def claim(self, request_sha256, model_label, *, session_id=None, session_elapsed_s=0.):
        s = self.state()
        if self.allowed.get(request_sha256) != model_label:
            raise GlobalStop('request not in approved manifest scope')
        if s['physical'] >= self.max_physical:
            raise GlobalStop('physical call cap')
        g, m = self.seconds_left(model_label, session_id, session_elapsed_s)
        if g <= 0:
            raise GlobalStop('global GPU seconds cap')
        if m <= 0:
            raise ModelStop('per-model GPU seconds share')
        n = s['attempts'][request_sha256]
        if n >= self.max_attempts:
            raise RequestSkip('per-request attempt cap')
        if n >= 1 and s['retries'] >= self.max_retries_total:
            raise RequestSkip('total retry cap')
        return n + 1


def default_caps(physical_unique, *, gpu_seconds=43200, max_physical_calls=None, per_model_gpu_seconds=None):
    """WP2 proposal caps (not an approval): one attempt + at most one retry per request;
    retries can only use the headroom between unique requests and the physical cap."""
    cap = max_physical_calls or physical_unique + min(64, max(1, physical_unique // 30))
    if cap < physical_unique:
        raise ValueError('physical cap below unique requests')
    caps = dict(max_physical_calls=cap, max_gpu_seconds=gpu_seconds, max_attempts_per_request=2,
                max_retries_total=max(0, cap - physical_unique), max_model_loads_per_model=3,
                load_seconds=900, request_seconds=300, consecutive_failure_stop=3,
                smoke_calls=16, smoke_max_length_stops=8)
    if per_model_gpu_seconds:
        caps['per_model_gpu_seconds'] = per_model_gpu_seconds
    return caps


def summarize(manifest):
    c = Counter((r['model_label'], r['arm'], r['status']) for r in manifest['requests'])
    return {f'{m}|{a}|{s}': n for (m, a, s), n in sorted(c.items())}
