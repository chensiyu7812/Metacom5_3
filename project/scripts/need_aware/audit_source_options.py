#!/usr/bin/env python3
"""Audit full train/val option shape without reading formal test labels."""
import argparse
from collections import Counter
import json
from pathlib import Path
from metacom_pm.need_aware.data.personamem import load_rows,write_json

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--source-root',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    root=Path(a.source_root);files={s['rfilename'] for s in json.loads((root/'hf_metadata.json').read_text())['siblings']};report={}
    for split in ['train','val']:
        rows=load_rows(root,split);shapes=Counter();bad=duplicates=0
        for row in rows:
            try:
                options=json.loads(row['incorrect_answers']);shapes[len(options)]+=1
                duplicates+=len(set([row['correct_answer'],*options]))!=len(options)+1
            except (ValueError,TypeError):bad+=1
        report[split]={'incorrect_option_count_histogram':dict(shapes),'invalid_options_json':bad,
                       'rows_with_duplicate_option_text':duplicates,
                       'missing_32k_ref_in_pinned_metadata':sum(r['chat_history_32k_link'] not in files for r in rows)}
    write_json(a.output,report);print(json.dumps(report,indent=2))
