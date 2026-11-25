#!/usr/bin/env python3
"""Replay private existing-evidence attribution without reading a model API."""
import argparse
import json
from pathlib import Path
from metacom_pm.rl1v3.io import file_sha256
from metacom_pm.rl1v3.journal.failure_attribution import attribute, aggregate


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--cases',type=Path,required=True)
    parser.add_argument('--protected-hashes',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    protected=json.loads(args.protected_hashes.read_text())['files']
    changed=[path for path,digest in protected.items() if file_sha256(path)!=digest]
    if changed:raise ValueError('protected originals changed: '+str(len(changed)))
    cases=[json.loads(x) for x in args.cases.read_text().splitlines() if x]
    rows=[attribute(x) for x in cases]
    args.out.mkdir(parents=True,exist_ok=False)
    with (args.out/'ATTRIBUTION_PRIVATE.jsonl').open('x') as handle:
        for row in rows:handle.write(json.dumps(row,ensure_ascii=False)+'\n')
    public=aggregate(rows)
    with (args.out/'COUNTS_PUBLIC.json').open('x') as handle:
        json.dump(public,handle,ensure_ascii=False,indent=2);handle.write('\n')
    with (args.out/'VALIDATION_PUBLIC.json').open('x') as handle:
        json.dump(dict(cases_checked=len(cases),protected_originals_checked=len(protected),
            changed_originals=0,case_file_sha256=file_sha256(args.cases),
            private_attribution_sha256=file_sha256(args.out/'ATTRIBUTION_PRIVATE.jsonl'),
            public_counts_sha256=file_sha256(args.out/'COUNTS_PUBLIC.json'),
            formal_reward=None),handle,indent=2);handle.write('\n')
    print(json.dumps(dict(cases_checked=len(cases),protected_originals_checked=len(protected),changed_originals=0)))


if __name__=='__main__':main()
