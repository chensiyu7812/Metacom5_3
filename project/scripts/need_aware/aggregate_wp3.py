#!/usr/bin/env python3
"""Frozen contrasts, joint eligible denominators, complete pairs and uncertainty."""
import argparse,json
from pathlib import Path
from metacom_pm.need_aware.data.v11 import jsonl
from metacom_pm.need_aware.data.personamem import write_json,sha_file
from metacom_pm.need_aware.evaluation.wp3 import paired_on_joint_eligible,paired_frozen_subset,holm_family,ARMS
from metacom_pm.need_aware.evaluation.wp2 import counts

def aggregate(cells,policy,gemma_ids):
    if set(cells)!={'Qwen35|'+a for a in ARMS}|{'G0e|'+a for a in ('B0','E0s','C')}:raise ValueError('all ten planned cells, including missing exports, required')
    comparisons=[]
    for left,right in policy['primary_paired_family']:
        # Both cells must cover the same preselected tasks. Model comparisons
        # explicitly subset to frozen Gemma IDs in their separate family.
        r=paired_on_joint_eligible(cells[left],cells[right],policy);r.update(left=left,right=right)
        ci=r['ci95'];r['meaningful_gain_supported']=bool(ci and ci[0]>0 and r['paired_difference']>=policy['minimum_meaningful_difference'])
        r['noninferiority_exploratory']=(bool(ci and ci[0]>-policy['noninferiority_margin']) if [left,right] in policy['noninferiority_contrasts'] else None)
        r['inference_scope']='Independent confirmation owners; CI unadjusted, Holm p across predeclared family; NI only predeclared contrasts and sufficient power.'
        comparisons.append(r)
    holm_family(comparisons)
    cross=[]
    for arm in policy['cross_model_family']:
        r=paired_frozen_subset(cells['G0e|'+arm],cells['Qwen35|'+arm],gemma_ids,policy);r['arm']=arm;cross.append(r)
    holm_family(cross)
    return dict(protocol=policy['protocol'],cells={k:counts(v) for k,v in cells.items()},paired=comparisons,cross_model=cross,
                evidence_sufficiency={k:{s:counts([r for r in v if r['category'].get('evidence_sufficiency','unknown')==s])
                    for s in ('sufficient','insufficient','ambiguous','unknown')} for k,v in cells.items()})

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cells','policy','wp3','out'):p.add_argument('--'+n,required=True)
    a=p.parse_args();mapping=json.loads(Path(a.cells).read_text());policy=json.loads(Path(a.policy).read_text())
    wp3=Path(a.wp3)
    if sha_file(wp3/'FREEZE.json')!=policy['material_freeze_sha256']:raise ValueError('selection freeze mismatch')
    frozen=json.loads((wp3/'FREEZE.json').read_text())
    if sha_file(wp3/'selection.json')!=frozen['artifacts']['selection.json']:raise ValueError('subset changed')
    result=aggregate({k:jsonl(v) for k,v in mapping.items()},policy,json.loads((wp3/'selection.json').read_text())['gemma_task_ids'])
    if Path(a.out).exists():raise FileExistsError('aggregate exists')
    write_json(Path(a.out),result);print(json.dumps(result,indent=2))
