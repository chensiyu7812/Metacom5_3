#!/usr/bin/env python3
"""Researcher-authorized metadata projection ONLY; formal answers remain sealed.

The CSV is cached as opaque bytes in a separate chmod-600 file. Arrow converts
only two allowlisted columns; no Python row contains a question/answer/persona.
This command cannot create RuntimeTask objects or expose benchmark outcomes.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import urllib.request
from metacom_pm.need_aware.data.personamem import REVISION, sha_file, load_rows, write_json

COLUMNS=['persona_id','chat_history_32k_link']


def project(path):
    import pyarrow as pa
    import pyarrow.csv as csv
    table=csv.read_csv(path,read_options=csv.ReadOptions(block_size=2**22),
        parse_options=csv.ParseOptions(newlines_in_values=True),
        convert_options=csv.ConvertOptions(include_columns=COLUMNS,
            column_types={k:pa.string() for k in COLUMNS}))
    assert table.column_names==COLUMNS
    return table.to_pylist()


def run(a):
    os.umask(0o077);root=Path(a.out);root.mkdir(parents=True,exist_ok=True)
    sealed=root/'SEALED_benchmark.csv'
    if not sealed.exists():
        url=f'https://huggingface.co/datasets/bowen-upenn/PersonaMem-v2/resolve/{REVISION}/benchmark/text/benchmark.csv'
        tmp=sealed.with_suffix('.partial')
        with urllib.request.urlopen(url,timeout=90) as stream,tmp.open('wb') as dest:
            shutil.copyfileobj(stream,dest)
        tmp.rename(sealed)
    sealed.chmod(0o600)
    meta=project(sealed)
    owners={r['persona_id'] for r in meta};families={r['chat_history_32k_link'] for r in meta}
    overlap={}
    for split in ('train','val'):
        rows=load_rows(a.source,split)
        overlap[split]=dict(owners=len(owners & {r['persona_id'] for r in rows}),
            history_paths=len(families & {r['chat_history_32k_link'] for r in rows}))
    result=dict(protocol='naa-formal-groups-metadata-only-v1',revision=REVISION,
        sealed_sha256=sha_file(sealed),columns_read=COLUMNS,rows=len(meta),owners=len(owners),
        history_families=len(families),overlap=overlap,answers_projected=False,
        answers_scored=False,formal_model_calls=0,
        limitation='history-family identity is pinned source path, not semantic or byte-duplicate audit of unopened test histories')
    write_json(root/'GROUPS_METADATA.private.json',meta);write_json(root/'SUMMARY.json',result)
    print(json.dumps(result))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--out',required=True)
    run(p.parse_args())
