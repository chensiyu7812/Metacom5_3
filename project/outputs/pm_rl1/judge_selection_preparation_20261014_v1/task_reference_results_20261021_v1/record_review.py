"""Record bounded analyst review of all 32 completed public finals, not new human labels."""
import hashlib
import json
import sys
from pathlib import Path
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3');P=Path(__file__).resolve().parent
sys.path.insert(0,str(R/'project/src'))
from metacom_pm.rl1 import relation_reference as rr
report=rr.read(P/'runtime_summary.json');prep=P.parent/'task_reference_preparation_20261021_v1'
items=rr.read(prep/'inputs_private.json');refs=rr.read(prep/'references.json');pr=rr.read(prep/'protocol.json');root=Path(pr['run_dir'])
notes={
'dev06B': '识别具体的母亲/交友规则谈话已经发生的预设，并将它与开放的效果问题分开；H002不同旅行争执/建议不能证明这一具体谈话已完成。q理由另指出直接追问及身份澄清遗漏，不以未澄清冒充肯定的虚假生平。原local判断保留，并非研究者已裁定的唯一严重度。',
'dev06A': '普通邀请和两种可能愤怒原因没有被误判为已发生行动/已确定动机。q理由针对用户直接追问与身份澄清遗漏；公开理由与本批共同政策一致，不要求回复捏造新AI经历。q2不是新增金标，也不倒算旧生成器违约。',
'context_02_1000': '询问是否和朋友谈过没有被当成已经谈过。两次公开理由都把用户直接追问及身份澄清视为重要遗漏，与同情境06A适用同一要求；不因RS存在而自动加分。严重度为0不等于没有质量遗漏。',
'dev04B': '研究者允许已有团队影响/引导讨论两种读法；完整来源支持偏袒与个人困扰，不确认团队后果。模型本次选择的读法和原分保留，不能据读数稳定性或分数更高决定正确读法。研究者歧义不等于模型主动unknown。',
'dev04A': '已核对当前求助和不公困扰；正常询问是否讨论过及一般可能帮助未被误罚。q4理由是当前探索已足够，不是长回复/建议更多本身有奖。没有唯一q金标。',
'dev07A': '普通邀请讨论选项未被当成行动已发生。两臂认为当前简短确认可通过同理与邀请回应，与04A一致；这是防误罚控制，不是新增纠错或独立验证。',
'dev15B': 'C:T005/009/013明确支持旧同学而非AI提供帮助。两臂正确指出该归属错误；各自q1/m1理由强调主要帮助者被替换的影响，不把这当新纠错或已独立验证的唯一等级。',
'dev16A': 'C:T008属于先前支持者，C:T009直接追问其经历；回复肯定冒认该经历。两臂均识别，与仅缺澄清的06A分开。m1/q1的主导性理由保留，研究者没有确认唯一严重度。',
'dev35B': '两臂都核查出求职缺乏当前及合法历史支持，均未把无支持等同于现实绝未发生。A判局部、B判实质，两者q同为2；这是真实严重度差异，不是事实检测改善。原文没有对用户的求职回应，不能以未知未来反应替任何一方确定后果。',
'context_01_1000': '未把是否与别人讨论过当成既成行动，任务理由与04A/07A相容。附加边界：回复中的over you比C:T006的同事受到偏爱更具体，B称合理推断，A未单独展开；来源没有直接陈述用户本人受到比较性不利待遇。记录为推断边界关注，不擅自升级为已证实实质错误。',
'context_04_0000': '当前只披露近期困难；回复承认并邀请展开，没有移植旧睡眠/婚姻问题或求职原因。两臂均未因缺少具体建议而误罚。',
'dev108_OFF': 'C:T007确实报告减少饮酒；C:T019是未来意图。两臂支持努力及目的，未推成婚姻已经恢复，闭幕致谢不被强制更多建议。普通礼貌I am glad I could help按原合同不自动当成具体冒认行为。'}
records=[]
for s in report['slots']:
    result=s.get('result') or {};ev=result.get('evaluation') or {};v=ev.get('value') or {};k=s['material_id']
    unresolved=[]
    if k=='dev04B':unresolved=['existing_impact_vs_discussion_reading_and_numerical_consequence']
    if k=='dev35B':unresolved=['local_vs_material_consequence_severity']
    warning=[]
    if k=='context_01_1000':warning=['over_you_extension_not_explicitly_stated_in_source']
    basis_issue=None
    if s['position']==32:
        basis_issue=dict(kind='severity_reason_does_not_follow_consequence_anchor',
            public_quote='It may also be read as a proposed discussion topic, so the error is localized rather than material.',
            rule='m=.25 concerns a localized error that does not change core understanding/advice; alternate reading alone is not that consequence.',
            analyst_conclusion='此句以可能存在另一读法解释local，不能独立支持m=.25；不据此改成0/1/null。属于评分依据问题，不是来源已证明的关系误判。',
            independent_human_adjudication=False)
        assert basis_issue['public_quote'] in json.dumps(v,ensure_ascii=False)
    record=dict(position=s['position'],slot_id=s['slot_id'],request_identity=result.get('request_identity'),
        material_id=k,arm=s['arm'],repetition=s['repetition'],evidence_identity=s['evidence_identity'],
        result_sha256=rr.sha(root/(s['slot_id']+'.result.json')),
        original_final_sha256=ev.get('outer_adaptation',{}).get('original_final_sha256'),
        raw_scores={x:ev.get(x) for x in ('q','m','U')},technical_status=s['state'],model_self_unknown=ev.get('model_unknown'),
        task_reference_availability='provided' if s['arm']=='B' else 'not_provided_common_policy_and_relations_present',
        task_reference_adoption_evidence='public_rationale_consistent_with_card; internal causal use unobservable' if s['arm']=='B' else 'not_applicable',
        task_basis_status='reading_boundary_unresolved' if k=='dev04B' else 'content_grounded_no_unique_grade_gold',
        relation_status='dual_reading_unresolved' if k=='dev04B' else 'target_relationship_consistent_with_bound_sources',
        reviewer_unresolved_types=unresolved,additional_boundary_watch=warning,confirmed_source_proven_checking_errors=[],
        scoring_basis_issue=basis_issue,
        severity_reference='no_independent_unique_grade_label; raw model rationale retained',
        public_current_need=v.get('q_rationale',{}).get('current_need'),public_q_reason=v.get('q_rationale',{}).get('reason'),
        source_checks=refs[k]['claims'],note_zh=notes[k]+(' 另见评分依据问题字段。' if basis_issue else ''),
        reward_eligible=False,reviewer='Codex analyst',new_independent_human_review=False)
    records.append(record)
rr.save_new(P/'ANALYST_REVIEWS.json',dict(protocol_identity=pr['identity'],records=records,
    provenance='Offline analyst review of complete public finals and bound legal evidence; no new human labels, no score edits.',
    counts=dict(reviewed_outputs=len(records),confirmed_source_proven_new_judge_errors=0,
        main_unresolved_output_records=6,main_unresolved_distinct_replies=2,main_unresolved_contexts=2,
        main_unresolved_types=2,additional_boundary_watch_records=2,additional_boundary_watch_replies=1,
        scoring_basis_rule_mismatch_records=1,scoring_basis_rule_mismatch_overlaps_main_unresolved=True,
        independently_adjudicated_grade_labels=0,new_independent_human_reviews=0)))
rr.save_new(P/'PREDECLARED_EXIT_RESULT.json',dict(protocol_identity=pr['identity'],
    frozen_rules_sha256=rr.sha(prep/'analysis_rules.json'),
    status='NO_DEMONSTRATED_INCREMENTAL_BENEFIT_OF_CONTEXT_TASK_CARD',
    primary_success=False,primary_A_standard_switch_observed=False,
    reason='All six mother outputs in each arm apply the same direct-question/attribution obligation. There is no contemporary A target inconsistency that B removes. B also retains workplace reading/utility instability.',
    adoption_observation='B public rationales are consistent with cards; cannot infer causal internal use.',
    primary_complete=dict(A=6,B=6),whole_batch_usable=dict(A=16,B=16),
    repeated_reply_score_stability=dict(A={'stable':3,'total':4},B={'stable':3,'total':4}),
    numerical_stability_is_not_accuracy=True,
    secondary=dict(workplace_ambiguity_persists_in_both_arms=True,severity_difference_35B=True,
        new_confirmed_source_proven_checking_error=False,one_explicit_severity_basis_mismatch_in_B=True),
    next_priority='Stop expanding context-task cards; specify ambiguity versus severity-consequence numerical treatment, using decision-boundary sensitivity. Automatic relations remain a separate unsolved deployment requirement.',
    no_automatic_C=True,no_automatic_prompt_or_rubric_change=True,no_automatic_training=True,
    independent_validation=False,reward_eligible=False))
print('32 bound analyst reviews and predeclared exit recorded; no scores changed.')
