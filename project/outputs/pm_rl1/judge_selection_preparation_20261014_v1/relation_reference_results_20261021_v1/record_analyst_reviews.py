"""Persist explicit analyst decisions against completed final/source hashes only."""
from pathlib import Path
import sys
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
sys.path.insert(0,str(R/'project/src'))
from metacom_pm.rl1 import relation_reference as r
B=R/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1'
P=B/'relation_reference_preparation_20261021_v2'
protocol=r.read(P/'protocol.json');items=r.read(P/'inputs_private.json');refs=r.read(P/'references.json')
root=Path(protocol['run_dir'])

def record(decisions):
    for position,uptake,target,basis,kind,note in decisions:
        slot=protocol['schedule'][position-1];path=root/(slot['slot_id']+'.result.json')
        result=r.read(path);final=result['evaluation']['value']
        if not result['technical_valid']:raise ValueError('No semantic acceptance of invalid output')
        key=slot['material_id'];ref=refs[key]
        quotes=[final['coverage'],final['q_rationale']['reason']]+[a['reason'] for a in final['assessments']]
        finding=[]
        if kind:
            criterion=('Original v2: questions may presuppose personal facts; do not exempt all questions. '
                       'Action-stage instruction: another conversation or a suggested action does not establish this specific action. '
                       'Reference review R1 accepts the missing-specific-action relation; severity is separate.' if kind=='confirmed_checking_error' else
                       'Original v2: distinguish reference relation from q/local/material consequences; preserve material ambiguity. '
                       'Accepted partial references do not fix whole-reply scores or a unique reading of 04B.')
            source_checks=[]
            for c in ref['claims']:
                for s in c['source_checks']:
                    x=dict(source_id=s['source_id'],quote=s['quote'])
                    if x not in source_checks:source_checks.append(x)
            finding=[dict(kind=kind,claim='; '.join(c['claim'] for c in ref['claims']),criterion=criterion,reason=note,source_checks=source_checks)]
        review=dict(status='ANALYST_REVIEW',independent_human_reference=False,
            slot_id=slot['slot_id'],result_sha256=r.sha(path),reference_bundle_sha256=protocol['reference_bundle_sha256'],
            reference_uptake=uptake,target_relationship=target,score_basis=basis,
            public_final_quotes=quotes,findings=finding,analyst_note_zh=note,
            score_basis_meaning='Supported means publicly stated basis can be grounded; not independent validation of an exact numerical score.',
            analysis_scope='Complete public final inspected against original reply, existing full-source reference preparation and cited positions; no thinking used; no new independent human evaluation.')
        r.validate_review(review,slot,result,path,items[key],protocol)
        r.save_new(root/'reviews'/(slot['slot_id']+'.json'),review)
    print('Saved bound analyst reviews:',[d[0] for d in decisions])
