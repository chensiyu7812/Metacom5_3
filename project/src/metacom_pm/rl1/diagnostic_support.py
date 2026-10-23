"""Public extraction of the append-only budget and serialization primitives.

No credential reader, model loader, private case or implicit network client.
Historical engine files and ledger records remain unchanged.
"""
import contextlib
from decimal import Decimal
import fcntl
import hashlib
import json
import os
from pathlib import Path
import time
from . import judge_completion_candidate as judge
NANO = 10**9
API_WORST = 786432000
VALID = ('measured_candidate', 'semantic_uncertainty')

def canonical(x):
    return json.dumps(x, ensure_ascii=False, sort_keys=True, separators=(',', ':'))


def digest(x):
    return hashlib.sha256(canonical(x).encode()).hexdigest()


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def read(path):
    return json.loads(Path(path).read_text())


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open('x') as f:
        f.write(json.dumps(value, ensure_ascii=False, indent=2) + '\n')


def nanodollars(x):
    return int(Decimal(str(x)) * NANO)


def usd(n):
    return str(Decimal(n) / NANO)


class Budget:
    """Append-only shared money ledger, serialized for this writer family.

    Old writers do not all take this lock: live approval MUST reconcile all other
    liabilities and ensure no concurrent legacy paid writer. No implicit lease.
    UNKNOWN settlement retains the complete reservation indefinitely.
    """
    def __init__(self, path, *, trial, trial_cap, shared_cap, baseline,
                 opening, external_liability=0, old_cap=nanodollars(50)):
        self.path = Path(path)
        self.trial = trial
        self.trial_cap, self.shared_cap = trial_cap, shared_cap
        self.baseline, self.opening = baseline, opening
        self.external_liability, self.old_cap = external_liability, old_cap
        if min(trial_cap, shared_cap, baseline, opening, external_liability, old_cap) < 0:
            raise ValueError('negative budget or liability is invalid')

    @contextlib.contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with Path(str(self.path) + '.selection.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield
            fcntl.flock(lock, fcntl.LOCK_UN)

    def events(self):
        return [json.loads(s) for s in self.path.read_text().splitlines()] if self.path.exists() else []

    def _totals(self, events):
        reserved, settled = {}, {}
        for e in events:
            if e['event'] == 'RESERVED':
                if e['reservation_id'] in reserved:
                    raise ValueError('duplicate financial reservation')
                reserved[e['reservation_id']] = e
            elif e['event'] == 'SETTLED':
                if e['reservation_id'] in settled:
                    raise ValueError('duplicate settlement')
                settled[e['reservation_id']] = e
        total, trial = self.opening, 0
        for key, e in reserved.items():
            if key in settled:
                value = nanodollars(settled[key]['actual_cost_usd'])
            else:
                value = nanodollars(e['maximum_cost_usd'])
            if value < 0:
                raise ValueError('negative financial amount')
            total += value
            if e.get('selection_trial') == self.trial:
                trial += value
        return total, trial, reserved, settled

    def _append(self, e):
        with self.path.open('a') as f:
            f.write(canonical(e) + '\n'); f.flush(); os.fsync(f.fileno())

    def reserve(self, reservation_id, amount, binding):
        with self.locked():
            total, trial, reserved, _ = self._totals(self.events())
            if reservation_id in reserved:
                raise ValueError('attempt already reserved; no automatic retry')
            if amount < 0 or trial + amount > self.trial_cap:
                raise ValueError('trial pre-reservation budget exhausted')
            if total - self.baseline + self.external_liability + amount > self.shared_cap:
                raise ValueError('shared follow-up budget exhausted')
            if total + self.external_liability + amount > self.old_cap:
                raise ValueError('older programme cap exhausted')
            self._append(dict(event='RESERVED', reservation_id=reservation_id,
                maximum_cost_usd=usd(amount), selection_trial=self.trial,
                stage='pmrl1-smallpool', call_class='PRIMARY', logical_call_id=reservation_id,
                call_hash=reservation_id, provider='DeepSeek official API', model='deepseek-flash',
                hard_cap_usd='50', opening_cost_usd=usd(self.opening),
                binding=binding, timestamp=time.time(), protocol='pmrl1-selection-reservation-v1'))

    def settle(self, reservation_id, actual, outcome):
        # Missing usage is NOT a zero-cost settlement, including HTTP/timeout failures.
        if actual is None:
            return False
        with self.locked():
            _, _, reserved, settled = self._totals(self.events())
            if reservation_id not in reserved or reservation_id in settled or actual < 0:
                raise ValueError('invalid settlement')
            self._append(dict(event='SETTLED', reservation_id=reservation_id,
                actual_cost_usd=usd(actual), outcome=outcome, timestamp=time.time(),
                selection_trial=self.trial, protocol='pmrl1-selection-reservation-v1'))
            return actual <= nanodollars(reserved[reservation_id]['maximum_cost_usd'])
