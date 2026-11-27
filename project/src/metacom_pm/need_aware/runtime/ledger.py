"""Append-only, hash-chained run ledger with resume. Nothing is ever rewritten or deleted.

Every attempt (success, failure, timeout, capacity refusal, reuse) is an event, so
the denominator is always complete. A crash can leave a torn final line: it is kept,
and the next process continues in a new segment linked to the last valid event.
"""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import json
import os
from pathlib import Path

from ..data.contracts import digest

LEDGER_VERSION = 'naa-ledger-v1'


class LedgerError(ValueError):
    pass


def _utc():
    return datetime.now(timezone.utc).isoformat()


class Ledger:
    def __init__(self, root, *, manifest_sha256):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.manifest_sha256 = manifest_sha256
        self.events = []
        self.prev = None
        segments = sorted(self.root.glob('LEDGER.*.jsonl'))
        torn = False
        for seg in segments:
            lines = seg.read_bytes().split(b'\n')
            for i, raw in enumerate(lines):
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except json.JSONDecodeError:
                    if i != len(lines) - 1 or seg != segments[-1]:
                        raise LedgerError('corrupt ledger line inside history: ' + seg.name)
                    torn = True
                    continue
                if row['previous_event_sha256'] != self.prev or row['manifest_sha256'] != manifest_sha256:
                    raise LedgerError('ledger chain/manifest mismatch at ' + seg.name)
                body = {k: v for k, v in row.items() if k != 'event_sha256'}
                if digest(body) != row['event_sha256']:
                    raise LedgerError('ledger event hash mismatch')
                self.prev = row['event_sha256']
                self.events.append(row)
        # Each process appends to its own new segment; earlier segments stay byte-identical.
        self.path = self.root / f'LEDGER.{len(segments) + 1:03d}.jsonl'
        self.torn_tail_seen = torn

    def add(self, event, **fields):
        body = dict(version=LEDGER_VERSION, seq=len(self.events), event=event, utc=_utc(),
                    manifest_sha256=self.manifest_sha256, previous_event_sha256=self.prev, **fields)
        body['event_sha256'] = digest(body)
        line = (json.dumps(body, ensure_ascii=False, sort_keys=True) + '\n').encode()
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
        try:
            os.write(fd, line)
            os.fsync(fd)
        finally:
            os.close(fd)
        self.prev = body['event_sha256']
        self.events.append(body)
        return body

    # ---- resume state -------------------------------------------------
    def completed(self):
        """request_sha256 -> successful ATTEMPT_RESULT event (first one wins)."""
        out = {}
        for e in self.events:
            if e['event'] == 'ATTEMPT_RESULT' and e['request_sha256'] not in out:
                out[e['request_sha256']] = e
        return out

    def attempts(self):
        return Counter(e['request_sha256'] for e in self.events if e['event'] == 'ATTEMPT_START')

    def physical_calls(self):
        return sum(e['event'] == 'ATTEMPT_START' for e in self.events)

    def gpu_seconds(self, model_label=None, exclude_session=None):
        """Occupied-GPU wall seconds: per model session, the latest elapsed stamp seen
        (so a crashed session still counts up to its last durable event)."""
        per = {}
        for e in self.events:
            if ('session_id' in e and 'session_elapsed_s' in e and model_label in (None, e.get('model_label'))
                    and e['session_id'] != exclude_session):
                per[e['session_id']] = max(per.get(e['session_id'], 0.), e['session_elapsed_s'])
        return sum(per.values())

    def model_loads(self):
        return Counter(e['model_label'] for e in self.events if e['event'] == 'LOAD_START')

    def settled_logical(self):
        return {e['logical_id'] for e in self.events if e['event'] in ('ATTEMPT_RESULT', 'REUSE', 'NOT_EVALUABLE')}
