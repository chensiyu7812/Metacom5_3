"""Forward-only diagnostic scheduling, independent of providers and training.

This component never sends requests or approves spending. A live coordinator
must verify stage authorization and atomically reserve all applicable budget
accounts in `reserve` before dispatching a returned claim. A crash after an
external reservation leaves that liability for reconciliation; it is not a
license to re-send. Historical runners and STOPs are deliberately untouched.
"""
from contextlib import contextmanager
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sqlite3

from .schema import digest

RETRIES = {'development': 2, 'qualification': 1, 'repeat': 0}
TECHNICAL = {'format_failure', 'schema_failure'}
OUTCOMES = TECHNICAL | {'valid', 'semantic_unknown', 'unavailable', 'global_risk'}


@dataclass(frozen=True)
class Slot:
    slot_id: str
    input_identity: str
    config_identity: str
    role: str = 'development'
    dependencies: tuple[str, ...] = ()


class RecoverySchedule:
    """Durable diagnostic slots; callbacks supply provenance, not score choices.

    One outstanding claim at a time intentionally makes restart and unknown
    delivery conservative. Different slots can continue after *settled* local
    failures. Dependent audit/resolution slots wait for valid prerequisites.
    Inputs must already be bound; dynamic downstream payloads are built by the
    coordinator in a separately bound schedule, never guessed from a future
    score. This class is not a formal learning-batch runner.
    """
    def __init__(self, path, slots, *, protocol_identity, max_attempts, recovery_cap=16,
                 circuit_threshold=3):
        slots = tuple(slots)
        if not protocol_identity or not slots:
            raise ValueError('explicit protocol and nonempty schedule required')
        if any(type(n) is not int or n < 0 for n in (max_attempts, recovery_cap)) or circuit_threshold != 3:
            raise ValueError('invalid fixed capacity/circuit rule')
        seen = set()
        for s in slots:
            if (not isinstance(s, Slot) or not all(isinstance(x, str) and x for x in
                    (s.slot_id, s.input_identity, s.config_identity)) or s.slot_id in seen
                    or s.role not in RETRIES or not set(s.dependencies) <= seen):
                raise ValueError('unique, bound, topologically ordered slots required')
            seen.add(s.slot_id)
        self.slots = slots
        self.protocol = protocol_identity
        self.max_attempts, self.recovery_cap = max_attempts, recovery_cap
        self.identity = digest(dict(version='pmrl1-recovery-schedule-v1', protocol=protocol_identity,
            slots=[asdict(s) for s in slots], max_attempts=max_attempts,
            recovery_cap=recovery_cap, circuit_threshold=circuit_threshold))
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.transaction() as db:
            db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
            db.execute('CREATE TABLE IF NOT EXISTS attempts (id TEXT PRIMARY KEY, slot TEXT NOT NULL, '
                'ordinal INTEGER NOT NULL, claim TEXT NOT NULL, result TEXT, UNIQUE(slot,ordinal))')
            old = db.execute("SELECT value FROM meta WHERE key='identity'").fetchone()
            if old and old[0] != self.identity:
                raise ValueError('cannot change a started schedule')
            db.execute("INSERT OR IGNORE INTO meta VALUES ('identity',?)", (self.identity,))
        self.path.chmod(0o600)

    @contextmanager
    def transaction(self):
        db = sqlite3.connect(self.path, timeout=30)
        try:
            db.execute('PRAGMA synchronous=FULL')
            db.execute('BEGIN IMMEDIATE')
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    @staticmethod
    def _rows(db):
        return [(json.loads(c), json.loads(r) if r else None) for c, r in
                db.execute('SELECT claim,result FROM attempts ORDER BY rowid')]

    def _view(self, db):
        rows = self._rows(db)
        grouped = {s.slot_id: [] for s in self.slots}
        slots = {s.slot_id: s for s in self.slots}
        streaks, stopped = {}, set()
        global_stop = None
        for claim, result in rows:
            slot = slots.get(claim.get('slot_id'))
            core = {k: v for k, v in claim.items() if k not in ('attempt_id', 'reservation')}
            if (slot is None or claim.get('attempt_id') != digest(core)
                    or claim.get('schedule_identity') != self.identity
                    or claim.get('protocol_identity') != self.protocol
                    or claim.get('input_identity') != slot.input_identity
                    or claim.get('config_identity') != slot.config_identity
                    or claim.get('role') != slot.role
                    or claim.get('ordinal') != len(grouped[slot.slot_id])
                    or claim.get('reservation', {}).get('attempt_id') != claim['attempt_id']):
                raise ValueError('persisted claim drift; reconcile before dispatch')
            grouped[claim['slot_id']].append((claim, result))
            if result is None:
                global_stop = 'OUTSTANDING_DELIVERY_OR_SETTLEMENT'
                continue
            if not result['identity_ok'] or not result['settled'] or result['outcome'] == 'global_risk':
                global_stop = 'GLOBAL_RECONCILIATION_REQUIRED'
            config = claim['config_identity']
            outcome = result['outcome']
            last, count = streaks.get(config, (None, 0))
            streaks[config] = (outcome, count + 1 if last == outcome else 1) if outcome in TECHNICAL else (None, 0)
            if streaks[config][1] >= 3:
                stopped.add(config)
        recovered = sum(c['ordinal'] > 0 for c, _ in rows)
        states = {}
        for slot in self.slots:
            attempts = grouped[slot.slot_id]
            if attempts and attempts[-1][1] is None:
                state = 'OUTSTANDING'
            elif attempts and (not attempts[-1][1]['identity_ok'] or not attempts[-1][1]['settled']):
                state = 'UNRESOLVED'
            elif attempts and attempts[-1][1]['outcome'] == 'valid':
                state = 'VALID'
            elif attempts and attempts[-1][1]['outcome'] not in TECHNICAL:
                state = 'UNRESOLVED'
            elif any(states[d] != 'VALID' for d in slot.dependencies):
                state = 'DEPENDENCY_PENDING'
            elif slot.config_identity in stopped:
                state = 'CONFIG_STOPPED'
            elif attempts and (len(attempts) > RETRIES[slot.role] or recovered >= self.recovery_cap):
                state = 'RECOVERY_EXHAUSTED'
            else:
                state = 'RECOVERY_READY' if attempts else 'READY'
            states[slot.slot_id] = state
        return dict(global_stop=global_stop, states=states, attempts=len(rows),
            recovery_attempts=recovered, config_stops=sorted(stopped),
            attempt_capacity_exhausted=len(rows) >= self.max_attempts), grouped

    def claim_next(self, reserve):
        """Reserve externally, then persist once. No implicit retry or dispatch.

        `reserve(claim)` must atomically check authorization, funds (including
        in-flight liabilities), and all global counters. It returns a receipt
        bound to this attempt, or raises. This component cannot establish that
        financial truth itself and is not a substitute for the live broker.
        """
        with self.transaction() as db:
            view, grouped = self._view(db)
            if view['global_stop'] or view['attempts'] >= self.max_attempts:
                return None
            # Complete untouched independent slots before retrying local errors.
            for target in ('READY', 'RECOVERY_READY'):
                for slot in self.slots:
                    if view['states'][slot.slot_id] != target:
                        continue
                    ordinal = len(grouped[slot.slot_id])
                    claim = dict(schedule_identity=self.identity, protocol_identity=self.protocol,
                        slot_id=slot.slot_id, input_identity=slot.input_identity,
                        config_identity=slot.config_identity, role=slot.role, ordinal=ordinal,
                        independent_draw_identity=slot.slot_id if slot.role == 'repeat' else None)
                    claim['attempt_id'] = digest(claim)
                    reservation = reserve(dict(claim))
                    if (not isinstance(reservation, dict) or reservation.get('attempt_id') != claim['attempt_id']
                            or not reservation.get('reservation_identity')):
                        raise ValueError('bound reservation receipt required; reconcile any external liability')
                    claim['reservation'] = reservation
                    db.execute('INSERT INTO attempts VALUES (?,?,?,?,NULL)',
                        (claim['attempt_id'], slot.slot_id, ordinal, json.dumps(claim, sort_keys=True, allow_nan=False)))
                    return claim
            return None

    def settle(self, attempt_id, *, outcome, input_identity, config_identity,
               settlement_identity, result_identity, settled=True):
        if outcome not in OUTCOMES or type(settled) is not bool or not result_identity:
            raise ValueError('explicit supported outcome and immutable result required')
        if settled and not settlement_identity:
            raise ValueError('settled result needs a financial receipt')
        with self.transaction() as db:
            row = db.execute('SELECT claim,result FROM attempts WHERE id=?', (attempt_id,)).fetchone()
            if row is None:
                raise ValueError('unknown attempt; cannot invent completed work')
            claim = json.loads(row[0])
            result = dict(outcome=outcome, input_identity=input_identity, config_identity=config_identity,
                identity_ok=(input_identity == claim['input_identity'] and config_identity == claim['config_identity']),
                settlement_identity=settlement_identity, result_identity=result_identity, settled=settled)
            encoded = json.dumps(result, sort_keys=True, allow_nan=False)
            if row[1] is not None and row[1] != encoded:
                raise ValueError('attempt outcome is immutable; use explicit reconciliation, never overwrite')
            db.execute('UPDATE attempts SET result=? WHERE id=?', (encoded, attempt_id))

    def report(self):
        with self.transaction() as db:
            view, _ = self._view(db)
            rows = self._rows(db)
        first = [(c, r) for c, r in rows if c['ordinal'] == 0]
        # A schema-valid semantic unknown is a delivered result, not usable reward.
        technical_valid = sum(bool(r and r['identity_ok'] and r['settled'] and
                                  r['outcome'] in ('valid', 'semantic_unknown')) for _, r in first)
        return view | dict(schedule_identity=self.identity,
            first_attempts=len(first), first_technical_valid=technical_valid,
            first_technical_valid_rate=technical_valid / len(first) if first else None,
            qualification_granted=False, training_authorized=False,
            attempts_log=[dict(claim=c, result=r) for c, r in rows])
