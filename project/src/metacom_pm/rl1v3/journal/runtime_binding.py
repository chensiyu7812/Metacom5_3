"""Journal versioned R1/R2/R5 repairs. Historical B bindings and C0 stay unchanged.

Only source-local A identities are hashed. The full corpus/source registry remains
input provenance, never a past snapshot/cache identity. Semantic approval is not
created here; relations retain their original disposition and approval evidence.
"""
from __future__ import annotations

import dataclasses
from dataclasses import dataclass
from typing import Mapping

from ..compile import asof as A
from ..env import research_v32 as R
from ..env.c0_binding import C0FiniteHeadEnv, TerminalIdentity, TerminalTable
from ..io import canonical_json, object_sha256

PROTOCOL = 'pmrl1-j-prefix-binding-2'
IDENTITY_FIELDS = tuple(f.name for f in dataclasses.fields(TerminalIdentity))


def plain(obj):
    import json
    return json.loads(canonical_json(obj))


def local_frontier(registry, prefix):
    registry.context(prefix)
    return tuple(dict(A.source_binding(e.source), source_sha256=A.source_sha(e.source),
                      reported_at=plain(e.reported_at),
                      known_at=plain(A.K.TimePoint(session_rank=e.source.chronological_rank + 1)),
                      ready_at=plain(e.ready_at))
                 for e in sorted(registry.visible(prefix), key=lambda e: e.source.chronological_rank))


@dataclass(frozen=True)
class JournalBinding:
    prefix_id: str
    prefix_context_sha256: str
    source_frontier_sha256: str
    snapshot_sha256: str
    writer_identity: str
    external_snapshot: str
    port_identity: str
    identity_fields: tuple[tuple[str, str], ...]
    protocol: str = PROTOCOL

    @property
    def sha256(self):
        return object_sha256(self)


def binding_for(registry, prefix, snapshot, port, *, external_snapshot='none'):
    A.verify_snapshot(snapshot)
    snap = plain(snapshot)
    if snap['as_of'] != plain(A.PrefixAsOf.from_prefix(registry, prefix)):
        raise R.BindingMismatch('snapshot as_of differs from actual registry prefix')
    if snap['source_frontier']['sources'] != plain(local_frontier(registry, prefix)):
        raise R.BindingMismatch('snapshot frontier differs from legal local sources')
    if getattr(port, 'prefix', None) != prefix:
        raise R.BindingMismatch('port prefix differs from actual prefix')
    port_snapshot = getattr(port, 'snapshot', None)
    if port_snapshot is None:
        raise R.BindingMismatch('port must expose its actual snapshot')
    A.verify_snapshot(port_snapshot)
    if port_snapshot['snapshot_sha'] != snapshot['snapshot_sha']:
        raise R.BindingMismatch('port snapshot mismatch')
    ident = getattr(port, 'identity', None)
    if not isinstance(ident, Mapping) or any(not ident.get(k) for k in IDENTITY_FIELDS):
        raise R.BindingMismatch('port lacks complete terminal identities')
    # Bind the concrete adapter implementation, as well as the resource and renderer identities.
    import inspect, hashlib
    source = inspect.getsourcefile(type(port))
    if source is None:
        raise R.BindingMismatch('port implementation source unavailable')
    with open(source, 'rb') as f:
        port_hash = hashlib.sha256(f.read()).hexdigest()
    return JournalBinding(prefix.prefix_id, prefix.runtime_sha256,
                          object_sha256(local_frontier(registry, prefix)), snapshot['snapshot_sha'],
                          snapshot['writer_identity'], external_snapshot,
                          f'{type(port).__module__}.{type(port).__qualname__}:{port_hash}',
                          tuple((k, ident[k]) for k in IDENTITY_FIELDS))


class VerifiedEpisode(R.BoundEpisode):
    """Construct the actual C0 environment from the validated port, never an unrelated env.

    Inherits B's already repaired STOP/after_stop and observation behavior. The
    separate journal composite key cannot collide with historical v0.1 bindings.
    """
    def __init__(self, *, registry, prefix, snapshot, port, binding: JournalBinding,
                 table=None, intervals=None):
        actual = binding_for(registry, prefix, snapshot, port,
                             external_snapshot=binding.external_snapshot)
        if actual != binding:
            raise R.BindingMismatch('frozen binding differs from actual port/snapshot/frontier')
        self.env = C0FiniteHeadEnv(prefix=prefix, history_sessions=prefix.cutoff_rank,
            availability=dict(port.availability()), read=lambda h, acquired: port.read(h, acquired=acquired),
            identity=TerminalIdentity(**dict(binding.identity_fields)),
            table=table or TerminalTable({}, table_id=PROTOCOL + ':pending'),
            prefix_tokens=port.base_tokens, read_takes_acquired=True, dynamic_mask=port.action_mask)
        self.registry, self.prefix, self.snapshot, self.port = registry, prefix, snapshot, port
        self.binding = binding
        self.intervals = dict(intervals or {})
        self.invalid_log = []

    def _validate_current(self):
        if binding_for(self.registry, self.prefix, self.snapshot, self.port,
                       external_snapshot=self.binding.external_snapshot) != self.binding:
            raise R.BindingMismatch('episode port or snapshot changed after construction')

    def reset(self):
        self._validate_current()
        return super().reset()

    def try_step(self, state, action):
        self._validate_current()
        result, info = super().try_step(state, action)
        if action.startswith('GET_') and not isinstance(info, R.Invalid):
            legal = {v['record'].record_id: v for v in self.snapshot['views']
                     if v['disposition'] in ('raw_available', 'supported_report')}
            read = result.readings[-1]
            if any(rid not in legal or legal[rid]['record'].text not in read.reading_text
                   for rid in read.record_ids):
                raise R.BindingMismatch('actual read is not grounded in the bound snapshot')
        return result, info

    def composite_key(self, state):
        return object_sha256(dict(protocol=PROTOCOL, binding_sha256=self.binding.sha256,
                                  c0_key_sha256=self.env.terminal_key(state).sha256))


def relation_exchange(snapshot):
    """Lossless sidecar exchange including RELATION; no promotion or re-projection.

    A's materializer owns semantics. Unknown/unapproved relations keep their
    original quarantine state. This exchange is private and never a ReadingView.
    """
    A.verify_snapshot(snapshot)
    s = plain(snapshot)
    rows = []
    for v in s['views']:
        r = v['record']
        head = {'MP': 'MP', 'ME': 'ME', 'MS_RAW': 'MS', 'MS_SUM': 'MS', 'RELATION': None}[r['kind']]
        rows.append(dict(record_id=r['record_id'], head=head, kind=r['kind'],
                         record=r, disposition=v['disposition'], current_validity=v['current_validity'],
                         semantic_approved=(r['review_status'] == 'human_approved' and r['subject'] != 'unknown'),
                         content_sha256=object_sha256(r)))
    return dict(protocol='pmrl1-j-asof-exchange-2', snapshot_sha256=s['snapshot_sha'],
                source_frontier=s['source_frontier'], as_of=s['as_of'], writer_identity=s['writer_identity'],
                rows=rows, invalidations=s['invalidations'], approval_created=False)
