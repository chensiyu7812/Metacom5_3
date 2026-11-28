#!/usr/bin/env python3
"""Bind explicit analyst observations to the one frozen 62-task source review."""
import argparse,json
from collections import Counter
from pathlib import Path
from metacom_pm.need_aware.data.v11 import jsonl
from metacom_pm.need_aware.data.personamem import write_json,write_jsonl,sha_file

def finalize(packets,notes,out):
    ps=jsonl(packets);ns=jsonl(notes);ix={r['task_id']:r for r in ns}
    if len(ix)!=len(ns) or set(ix)!={p['task_id'] for p in ps}:raise ValueError('review population mismatch')
    annotations=[];errors=Counter()
    for p in ps:
        n=ix[p['task_id']]
        if n['evidence_sufficiency'] not in ('sufficient','insufficient','ambiguous'):raise ValueError('unknown review label')
        if not n['reason'] or n['usage']!='development_diagnostic_only_never_training':raise ValueError('unreviewed/training leak')
        source={r['source_id']:r for r in p['full_legal_history']}
        for ref in n['source_refs']:
            r=source[ref['source_id']]
            if r['original_text_sha256']!=ref['sha256'] or r['coordinates']!=ref['coordinates']:raise ValueError('review source changed')
        outcomes={}
        for model,cells in p['outcomes'].items():
            outcomes[model]={}
            for arm,r in cells.items():
                category=('technical_unknown' if r['status']!='completed' else 'format_failure' if not r['parse_valid'] else
                          'official_correct' if r['correct'] else 'valid_format_official_wrong')
                outcomes[model][arm]=category;errors[model+'/'+arm+'/'+category]+=1
        n.update(outcomes=outcomes,official_score_changed=False,full_history_sha256=p['full_legal_history_sha256'],
                 full_history_records=p['lexical_search']['all_records_scanned'],
                 full_history_absence_proven=False,independent_second_review=False)
        annotations.append(n)
    out=Path(out)
    if out.exists():raise FileExistsError('review already frozen')
    write_jsonl(out/'ANNOTATIONS.private.jsonl',annotations)
    report=dict(protocol='naa-wp2-bounded-semantic-review-v1',tasks=len(annotations),
                who_others=sum(p['evaluation']['category']['who']=='others' for p in ps),
                direct_sufficiency=dict(Counter(r['evidence_sufficiency'] for r in annotations)),
                full_history_sufficiency=dict(Counter(r['full_history_sufficiency'] for r in annotations)),
                holder=dict(Counter(r['holder'] for r in annotations)),
                issues=dict(Counter(tag for r in annotations for tag in r['issues'])),
                model_outcomes=dict(errors),packet_sha256=sha_file(Path(packets)),notes_sha256=sha_file(Path(notes)),
                annotation_sha256=sha_file(out/'ANNOTATIONS.private.jsonl'),
                review_scope='One assisted source review: Direct passages and alternatives retrieved from every legal history. Whole histories hash/role/coordinate checked. No exhaustive human semantic absence proof; ambiguous retained.',
                official_labels_changed=0,independent_raters_completed=0,training_use_prohibited=True)
    write_json(out/'RECEIPT.json',report);return report

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('packets','notes','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();print(json.dumps(finalize(a.packets,a.notes,a.out),indent=2))
