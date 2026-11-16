"""Persist explicitly supplied Codex observations; no inference or model calls."""
import json,hashlib,os
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
B=Path(__file__).resolve().parent.parent
ROOT=B/'live_runs/output_interface_v1_AB_diagnostic'
PLAN=json.loads((B/'plan.json').read_text())
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
def write_review(rid,explanation,checks,dimensions,*,unknown=False,material=False,equivalent=False,issues=None,hard_stop_evidence=None):
    files=list(ROOT.glob('*/'+rid+'.response.json'));assert len(files)==1
    response=files[0];result=json.loads(response.with_name(rid+'.result.json').read_text());req=result['request'];orig=result['original_request']
    item=PLAN['items'][orig['item_key']];e=item['evidence'];turns={t['id']:t for t in e['current_prefix']+[t for h in e['legal_past_sessions'] for t in h['turns']]}
    value=dict(time_jst=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),reviewer='Codex source-bound diagnostic review; not independent human rater',
        request_id=rid,original_slot_request_id=orig['request_id'],item_key=orig['item_key'],draw=orig['draw'],
        response_sha256=sha(response),raw_sha256=sha(response.with_name(rid+'.raw.json')),
        explanation=explanation,source_checks=[dict(source_id=k,exact_quote=turns[k]['text'],finding=v) for k,v in checks],
        material_source_proven_error=material,critical_unknown=unknown,unexplained_equivalence_difference=equivalent,
        other_hard_stop_reasons=[],hard_stop_evidence=hard_stop_evidence or [],dimensions=dimensions,issues=issues or [],
        model_score_unchanged=True,complete_final_only=True,thinking_used_as_answer=False,
        legal_evidence_identity=item['evidence_identity'],complete_evidence_reviewed=True,
        independent_human_observations=0,qualification='NOT_EVALUATED',
        diagnostic_policy_version='unresolved-review-diagnostic-continuation-v1-20261015')
    target=ROOT/'stage'/(rid+'.review.json');temp=target.with_suffix('.pending')
    with temp.open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n');f.flush();os.fsync(f.fileno())
    os.link(temp,target);temp.unlink()
    print(json.dumps(dict(reviewed=rid,item=orig['item_key'],candidate=req['candidate'],unknown=unknown,material=material,equivalent=equivalent),ensure_ascii=False))
