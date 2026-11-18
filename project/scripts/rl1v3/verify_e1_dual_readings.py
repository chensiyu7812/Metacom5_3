#!/usr/bin/env python3
"""Fresh native RAW reads from both persisted horizons. No model load."""
import argparse
import json
from pathlib import Path

from prepare_e1_qualification import NativeCounter
from metacom_pm.rl1v3.compile import asof as A, qualification as Q
from metacom_pm.rl1v3.io import canonical_json,object_sha256,file_sha256,write_json_once


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--bundle',type=Path,required=True)
    ap.add_argument('--model',type=Path,required=True);ap.add_argument('--out',type=Path,required=True)
    args=ap.parse_args();root=args.bundle
    spec=json.loads((root/'GENERATOR_BASELINE.json').read_text())['spec']
    counter=NativeCounter(args.model,dict(common=spec));rows=[]
    for b in map(json.loads,(root/'BINDINGS.jsonl').read_text().splitlines()):
        readings=[]
        for path in (b['snapshot_past'],b['snapshot_future']):
            snap=A.load_snapshot(root/path,expected_sha=b['snapshot_sha'])
            readout=dict(MP=A.read(snap,'MP',ordinal=1,token_counter=counter,context_remaining=16064),
                ME=A.read(snap,'ME',ordinal=1,token_counter=counter,context_remaining=16064),
                MS=Q.direct_raw(snap,b['selected_raw_id'],counter))
            readings.append(readout)
        assert canonical_json(readings[0])==canonical_json(readings[1])
        assert json.loads(canonical_json(readings[0]))==json.loads((root/b['reading_path']).read_text())
        rows.append(dict(owner_id=b['owner_id'],prefix_id=b['prefix_id'],snapshot_sha=b['snapshot_sha'],
            past_readings=readings[0],future_readings=readings[1],reading_sha256=object_sha256(readings[0]),
            same_readings=True))
    write_json_once(args.out,dict(protocol='dual-horizon-native-reads-1',
        bindings_file_sha256=file_sha256(root/'BINDINGS.jsonl'),tokenizer_identity=counter.identity,
        rows=rows,pairs=8,weights_loaded=False,generator_calls=0,independent_B_review=False))


if __name__=='__main__':main()
