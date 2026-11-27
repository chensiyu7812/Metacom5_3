"""NAA batch scope and call budget, derived from one frozen manifest + one approval.

Replaces nothing in GE2: the historical WorkerCallBudget (two tasks, 8-10 terminal
slots) keeps guarding GE2. This class only admits physical calls whose exact
request_sha256 is listed in the NAA manifest, within the approved caps, and counts
calls already recorded in the ledger so a resumed run cannot exceed them.
"""
from __future__ import annotations

from collections import Counter

from ...rl1v3.generator.limited_run import require

BUDGET_VERSION = 'naa-batch-budget-v1'


class NAABatchBudget:
    def __init__(self, manifest, approval, ledger):
        caps = manifest['caps']
        self.allowed = {}
        for row in manifest['requests']:
            if row['status'] == 'ready' and 'duplicate_of' not in row:
                self.allowed[row['request_sha256']] = row['model_label']
        require(len(self.allowed) == manifest['counts']['physical_unique'], 'manifest physical identity count')
        self.max_physical = min(caps['max_physical_calls'], approval['max_physical_calls'])
        self.max_gpu_seconds = min(caps['max_gpu_seconds'], approval['max_gpu_seconds'])
        self.max_attempts = caps['max_attempts_per_request']
        self.max_retries_total = caps['max_retries_total']
        self.max_loads = caps['max_model_loads_per_model']
        self.models = tuple(approval['models'])
        # Equal per-model share of the approved GPU seconds: a slow model cannot starve the other.
        self.per_model_seconds = self.max_gpu_seconds / max(1, len(self.models))
        self.ledger = ledger

    def state(self):
        attempts = self.ledger.attempts()
        return dict(physical=self.ledger.physical_calls(), gpu_seconds=self.ledger.gpu_seconds(),
                    retries=sum(max(0, n - 1) for n in attempts.values()), attempts=attempts,
                    loads=self.ledger.model_loads())

    def claim_load(self, model_label):
        require(model_label in self.models, 'model not approved: ' + model_label)
        s = self.state()
        require(s['loads'][model_label] < self.max_loads, 'model load cap')
        require(s['gpu_seconds'] < self.max_gpu_seconds, 'GPU seconds cap')
        require(self.ledger.gpu_seconds(model_label) < self.per_model_seconds, 'per-model GPU seconds share')

    def seconds_left(self, model_label, session_id=None, session_elapsed_s=0.):
        """Remaining GPU seconds: earlier sessions from the ledger + the live session's elapsed time."""
        total = self.ledger.gpu_seconds(exclude_session=session_id) + session_elapsed_s
        own = self.ledger.gpu_seconds(model_label, exclude_session=session_id) + session_elapsed_s
        return min(self.max_gpu_seconds - total, self.per_model_seconds - own)

    def claim(self, request_sha256, model_label, *, session_id=None, session_elapsed_s=0.):
        s = self.state()
        require(self.allowed.get(request_sha256) == model_label, 'request not in approved manifest scope')
        require(s['physical'] < self.max_physical, 'physical call cap')
        require(self.seconds_left(model_label, session_id, session_elapsed_s) > 0, 'GPU seconds cap/per-model share')
        n = s['attempts'][request_sha256]
        require(n < self.max_attempts, 'per-request attempt cap')
        if n >= 1:
            require(s['retries'] < self.max_retries_total, 'total retry cap')
        return n + 1


def default_caps(physical_unique, *, gpu_seconds=43200, max_physical_calls=None):
    """WP2 proposal caps (not an approval): one attempt + at most one retry per request;
    retries can only use the headroom between unique requests and the physical cap."""
    cap = max_physical_calls or physical_unique + min(64, max(1, physical_unique // 30))
    if cap < physical_unique:
        raise ValueError('physical cap below unique requests')
    return dict(max_physical_calls=cap, max_gpu_seconds=gpu_seconds, max_attempts_per_request=2,
                max_retries_total=max(0, cap - physical_unique), max_model_loads_per_model=3,
                load_seconds=900, request_seconds=300, consecutive_failure_stop=3)


def summarize(manifest):
    c = Counter((r['model_label'], r['arm'], r['status']) for r in manifest['requests'])
    return {f'{m}|{a}|{s}': n for (m, a, s), n in sorted(c.items())}
