"""Actual snapshot-only MS bridge over the preserved PrefixPort and C0.

This is a new journal bank/index identity. It cannot read rows outside the
bound A snapshot; it never adds approval to semantic candidates.
"""
from dataclasses import replace
from .. import contracts as K
from ..bank import bank_v0 as B
from ..bank.v0_port import PrefixPort
from ..compile import asof as A
from ..io import object_sha256, file_sha256


class LocalRegistry:
    """Delegate legal sources; hash only the snapshot-local identity."""
    def __init__(self, registry, snapshot):
        self.original = registry
        self.version = 'journal-local-sources:' + object_sha256(dict(
            protocol='pmrl1-j-source-local-registry-v1',
            as_of=snapshot['as_of'], source_frontier_sha256=snapshot['source_frontier_sha256']))

    def __getattr__(self, key):
        return getattr(self.original, key)


class SnapshotPrefixPort(PrefixPort):
    def __init__(self, registry, prefix, snapshot, tokenizer, **identity):
        A.verify_snapshot(snapshot)
        if snapshot['as_of'] != A.PrefixAsOf.from_prefix(registry,prefix):
            raise ValueError('snapshot cutoff differs from actual prefix')
        self.snapshot = snapshot
        records = []
        for item in snapshot['views']:
            row = item['record']
            if row.kind != 'MS_RAW' or item['disposition'] != 'raw_available':
                continue
            A.verify_record(row, registry)
            entry = registry.entry(row.owner_id,row.session_id)
            if registry.reason(entry.source_id,prefix) is not None:
                raise ValueError('snapshot contains illegal source')
            record = B._base(entry,'MS',
                'SOURCE_EXACT historical session; original speaker attribution; present validity unknown.\n'+row.text,
                dict(protocol='pmrl1-j-snapshot-ms-port-v1',snapshot_sha256=snapshot['snapshot_sha']),
                row.source_refs,legacy_id=row.record_id)
            records.append(replace(record,record_id=row.record_id,writer_identity=row.writer_identity))
        inputs = dict(protocol='pmrl1-j-snapshot-ms-port-v1',snapshot_sha256=snapshot['snapshot_sha'],
            source_frontier_sha256=snapshot['source_frontier_sha256'],code_sha256=file_sha256(__file__))
        local_registry = LocalRegistry(registry,snapshot)
        version=B._identity(records,local_registry,inputs)
        bank=B.Bank([replace(r,bank_version=version) for r in records],local_registry,inputs,())
        super().__init__(bank,prefix,tokenizer,**identity)

    def availability(self):
        # Public inventory needs only existence, never count or hidden similarity.
        return {h:int(bool(self.bank.candidates(h,self.prefix))) for h in K.HEAD_ORDER}

    def action_mask(self, acquired=(), *, input_tokens_before=None):
        # Capacity measurements remain private; no speculative successful GET.
        acquired,before,_=self._context(acquired,input_tokens_before)
        units=self.unit_tokens(acquired=acquired,input_tokens_before=before)
        return tuple('GET_'+h for h in K.HEAD_ORDER if h in units and
            before+units[h]+self.output_reserve_tokens<=self.native_context_tokens)+('STOP',)
