#!/usr/bin/env python3
"""Exercise the preserved As-of gate with actual conversation prefixes, CPU only.

The 12 end-history QA cases are a separate Direct diagnostic and are never
converted into fabricated next-turn PrefixSpecs for this check.
"""
import argparse
from collections import Counter
from pathlib import Path

from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.compile import asof as A
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
from metacom_pm.rl1v3.journal.representations import jl
from metacom_pm.rl1v3.io import canonical_json, decode_contract, file_sha256, write_json_once

p = argparse.ArgumentParser()
p.add_argument('--root', type=Path, required=True)
p.add_argument('--representations', type=Path, required=True)
p.add_argument('--prefixes', type=Path, required=True)
p.add_argument('--out', type=Path, required=True)
a = p.parse_args()
registry = S.load(a.root / 'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
ledger = A.Ledger(a.representations / 'ledger')
tokenizer = NativeTokenizer('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3',
    a.root / 'project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json')
writers = {r.writer_identity for r in ledger.rows}
assert len(writers) == 1
writer = next(iter(writers))
assert all(not r.semantically_approved for r in ledger.rows)
results = []
unique_sums = set()
for row in jl(a.prefixes):
    prefix = decode_contract(K.PrefixSpec, canonical_json(row['prefix']))
    snapshot = A.materialize(registry, prefix, ledger, writer=writer)
    A.verify_snapshot(snapshot)
    for item in snapshot['views']:
        record = item['record']
        assert item['disposition'] == ('raw_available' if record.kind == 'MS_RAW' else 'quarantine')
        if record.kind == 'MS_SUM':
            fallback = A.summary_or_raw(snapshot, record.record_id)
            assert fallback['condition'] == 'SUM_TO_RAW_FALLBACK'
            unique_sums.add(record.record_id)
    assert not A.candidate_ids(snapshot, 'MP')
    assert not A.candidate_ids(snapshot, 'ME')
    reading = A.read(snapshot, 'MS', ordinal=1, token_counter=tokenizer, context_remaining=16064)
    results.append(dict(prefix_id=prefix.prefix_id, snapshot_sha256=snapshot['snapshot_sha'],
        dispositions=dict(Counter(v['disposition'] for v in snapshot['views'])),
        semantic_MP_ME_unavailable=True,
        raw_read_status='available' if isinstance(reading, K.ReadingView) else reading['status'],
        reading_tokens=reading.tokens if isinstance(reading, K.ReadingView) else None))
receipt = dict(protocol='pmrl1-j-representation-preserved-asof-gate-v1',
    real_conversation_prefixes=len(results), end_history_QA_converted_to_fake_prefix=False,
    writer_identity=writer, semantic_approved_new=0,
    summary_candidates_verified_to_fall_back_to_RAW=len(unique_sums),
    source_prefixes_sha256=file_sha256(a.prefixes),
    representation_report_sha256=file_sha256(a.representations / 'REPORT.json'),
    results=results, GPU_loads=0, model_calls=0,
    qualification='Actual old As-of/ReadingView CPU check only; separate source-exact QA diagnostic is not semantically admitted by this gate.')
write_json_once(a.out, receipt)
print(canonical_json(receipt))
