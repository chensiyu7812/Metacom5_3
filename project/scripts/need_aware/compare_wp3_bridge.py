#!/usr/bin/env python3
"""Old official vs new short protocol on exactly 60 preselected tasks."""
import argparse,json
from pathlib import Path
from metacom_pm.need_aware.data.v11 import jsonl
from metacom_pm.need_aware.data.personamem import write_json,sha_file
from metacom_pm.need_aware.evaluation.wp3 import paired_frozen_subset,holm_family

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('old-scored','new-cells','wp3','policy','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();root=Path(a.wp3);policy=json.loads(Path(a.policy).read_text());mapping=json.loads(Path(a.new_cells).read_text())
    if sha_file(root/'FREEZE.json')!=policy['material_freeze_sha256']:raise ValueError('bridge freeze changed')
    rel='bridge/runtime/tasks.mcq.jsonl';freeze=json.loads((root/'FREEZE.json').read_text())
    if sha_file(root/rel)!=freeze['artifacts'][rel]:raise ValueError('bridge task set changed')
    ids=[r['task_id'] for r in jsonl(root/rel)];result=[];inputs={}
    if len(ids)!=60 or len(set(ids))!=60:raise ValueError('bridge denominator')
    for m in ('Qwen35','G0e'):
        for arm,oldarm in [('B0','B'),('C','C')]:
            old=Path(a.old_scored)/f'scored.{m}.{oldarm}.private.jsonl';new=Path(mapping[m+'|'+arm])
            left,right=jsonl(old),jsonl(new)
            if {r['task_id'] for r in right}!=set(ids):raise ValueError('new bridge subset mismatch')
            if any(r['result_kind']!='model' for r in left+right):raise ValueError('bridge requires actual model provenance')
            r=paired_frozen_subset(left,right,ids,policy);r.update(model=m,arm=arm,old_protocol='official WP2 unchanged',new_protocol=policy['scoring_protocol'])
            result.append(r);inputs[str(old)]=sha_file(old);inputs[str(new)]=sha_file(new)
    holm_family(result)
    report=dict(protocol='naa-wp3-protocol-bridge-v1',paired=result,input_sha256=inputs,
                limitation='Protocol effect on exposed development tasks; not independent confirmation or equivalence proof.')
    if Path(a.out).exists():raise FileExistsError('bridge report already sealed')
    write_json(Path(a.out),report);print(json.dumps(report,indent=2))
