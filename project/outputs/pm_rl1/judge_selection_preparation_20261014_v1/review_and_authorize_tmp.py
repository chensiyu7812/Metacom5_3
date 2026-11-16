from pathlib import Path
import sys,json
HERE=Path(__file__).resolve().parent/'outer_format_v1_20261015'
sys.path.insert(0,str(HERE));sys.path.insert(0,str(HERE.parent))
import selection as s
import continue_v1 as c
from resume_engineering import now,slots
plan=s.load_plan();p=s.read(HERE/'protocol.json');assert p==c.protocol(plan)
releases={};reviews=[]
for req in slots(plan)[:2]:
    rid=req['request_id'];candidate=req['candidate'];label=p['configs'][candidate]['label']
    dpath=HERE/'derived'/(rid+'.derived.json');d=s.read(dpath)
    final=d['evaluation']['measurement']['flat_judge_output']
    item=plan['items'][req['item_key']];source=item['evidence']['current_prefix'][-1]
    data=json.loads(s.payload(plan,req)[0][1]['content']);units=data['response_units']
    explanations=[
        'R001 验证当下感受；C:T006直接表达脆弱感。A标supported、B标non_factual，差别保留；未发现主体或严重度反转。',
        'R002 是关于分享经历所需勇气的一般支持。C:T006提供分享／脆弱语境，但不直接陈述勇气事实。A以supported引用上下文、B以non_factual处理；引用合法不代表逐字蕴含，不能把本处当成语义准确率通过。',
        'R003 把一般鼓励与具体个人动机放在同一句。C:T006直接支持想帮助别人的动机。A显式按supported引用；B承认反映已述动机却整句non_factual且无单元引用，未落实混合断言检查要求，属于保留的分类／覆盖理由问题。所述动机本身有来源支持；当前没有证明它造成错误主体、时间、事实或严重度结论，不由此新增实质错误硬停，也不宣布该问题已解决。',
        'R004 是可选择的探索邀请，不是要求立即行动；没有发现当前来源中的具体禁止约束遭违反。',
        'R005 是一般支持性策略建议，没有声称用户已采取行动或已有疗效。'
    ]
    unit_checks=[dict(unit=u,model_assessment=next(a for a in final['assessments'] if a['response_unit_id']==u['id']),review=explanations[i]) for i,u in enumerate(units)]
    review=dict(time_jst=now(),reviewer='Codex source-bound developmental diagnostic; not an independent human rater',
        request_id=rid,item_key=req['item_key'],response_sha256=s.sha(d['original_response_path']),
        original_raw_hashes=d['original_hashes'],derived_record_sha256=s.sha(dpath),
        explanation='完整final的外层格式适配和原schema／来源ID／严格证据检查均通过。逐项理由问题另存，不修改模型判断。现有来源没有证明实质主体／时间／事实／引用／严重度错误或关键语义unknown已触发硬停；仅允许继续原首轮工程槽位，不构成语义选型通过。',
        material_source_proven_error=False,critical_unknown=False,unexplained_equivalence_difference=False,
        source_checks=[dict(source_id=source['id'],exact_quote=source['text'],finding='当前用户表达帮助他人的动机及开放分享的脆弱感；不是朋友或历史支持者的行动')],
        unit_checks=unit_checks,format_valid=True,schema_and_mechanical_evidence_valid=True,
        semantic_reasoning_issues_preserved=True,semantic_qualification='NOT_EVALUATED',
        hard_stop_rule='original four-config protocol selection_rules.semantic_gate: source-proven MATERIAL actor/time/fact/citation/severity error; critical unknown and unexplained equivalence differences stay blocking',
        initial_four_scope='original execution checklist: engineering is not semantic selection; observed material errors are not bypassed',
        new_independent_samples=0,semantic_revision_delta=0)
    rpath=HERE/'derived'/(rid+'.review.json');s.save(rpath,review);reviews.append(str(rpath))
    if d['evaluation']['measurement']['measurement_status'] in s.VALID and not c.review_valid(review,plan,req,rid,Path(d['original_response_path'])):
        releases[candidate]=dict(derived_path=str(dpath),review_path=str(rpath),
            immutable_bindings=d['original_hashes']|{str(dpath):s.sha(dpath),str(rpath):s.sha(rpath)},
            releases_only='the old dev02B outer-format parse failure; original STOP remains immutable',
            remaining_original_slots=[r['request_id'] for r in slots(plan) if r['candidate']==candidate and r['ordinal']>1])
auth=dict(status='APPROVED',time_jst=now(),authorization_reference='User explicitly approved final-envelope-only adapter, offline two-final reparse and conditional original remaining six engineering attempts; no other phases.',
    protocol_identity=p['identity'],original_plan_identity=plan['identity'],new_calls_limit=6,pool_call_cap=8,cumulative_cap=74,original_cap=140,
    old_calls=66,existing_pool_started=2,semantic_revision_delta=0,semantic_revisions_used=1,
    format_only_releases=releases,tests_log_sha256=s.sha(HERE/'tests_v1_corrected.log'),tests=76,
    offline_reparse_summary_sha256=s.sha(HERE/'offline_reparse_summary.json'),
    phases=['engineering'],candidates=list(s.CANDIDATES[:2]),DeepSeek_authorized=False,
    GPU_guard=dict(uuid='GPU-ba5f65be-ecfa-7fda-b239-af9efd468db4',free_MiB_at_least=45000,utilization_percent=0,max_wait_seconds=300),
    old_stops_deleted=False,old_scores_replaced=False,automatic_retry=False)
s.save(HERE/'continuation_authorization.json',auth)
assert set(c.validate_release(plan,p,auth,s.HERE/'live_runs'))==set(s.CANDIDATES[:2])
print('Conditional format-only releases bound for A and B; old STOP retained; no inference yet.')
