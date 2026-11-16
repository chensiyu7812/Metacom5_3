#!/usr/bin/env python3
"""Materialize assistant-reviewed observations; not automatic lexical labels or human gold."""
import json,hashlib
from pathlib import Path
from collections import Counter
P=Path(__file__).resolve().parent
sessions=json.loads((P/'SELECTED_COMPLETE_SESSIONS_PRIVATE.json').read_text())
byid={s['sample_id']:s for s in sessions}
# Each tuple is manually specified only after reading the complete selected session.
# Categories: suggestion, intention, attempt, subjective_outcome, explicit_preference.
D={
'M01': [('suggestion',[21],'专业帮助只是建议，未证实求助'),('intention',[10],'考虑换工作，恐惧阻碍，未实施'),('attempt',[18],'已通过写日记梳理想法'),('subjective_outcome',[14],'与 Eliza 谈过后关系改善的自述；不能归因于当前建议')],
'M02': [('suggestion',[19],'可以依靠朋友支持'),('intention',[20],'计划更常联系'),('attempt',[14],'自报已开始寻求专业帮助'),('subjective_outcome',[14,16],'求助后更有希望、开始理解饮酒原因；早期主观结果，非戒酒成功')],
'M03': [('suggestion',[14],'建议考虑瑜伽静修或放松'),('intention',[15,19],'考虑参加静修及多和 Matthew 谈；均未证明实施'),('attempt',[11],'已简短向 Matthew 提及情绪'),('subjective_outcome',[5],'约会整体顺利但难以放松；不能概括为压力已解决')],
'M04': [('attempt',[3,11],'参加治疗会谈及写作工作坊'),('subjective_outcome',[7,11],'治疗后既释然又焦虑；工作坊有帮助但冒名顶替感仍出现')],
'M05': [('suggestion',[13,17],'建议找工作外支持或医生'),('intention',[14,20],'考虑联系他人、了解可用选择；未完成'),('attempt',[4],'已改乘公共交通'),('subjective_outcome',[4],'公交不可靠、通勤更长且疲惫；实际约束'),('unknown',[18],'就医是否发生及其效果未报告；时间和钱是已报告障碍')],
'M06': [('suggestion',[18],'建议依靠 David 并谈谈'),('intention',[13,21,23],'计划联系 Lily 和向 David 表达感受'),('attempt',[19],'自报已经同居'),('subjective_outcome',[19],'同居对丧犬后的情绪有所帮助的自述')],
'M07': [('suggestion',[17],'建议表达时注意措辞'),('intention',[16,24],'条件性愿意修复并说将来尝试；未实际修复'),('unknown',[20,24],'父亲是否回应、是否和解未知')],
'M08': [('attempt',[7],'自报已经减少饮酒'),('suggestion',[16,18],'建议共同活动、约会等'),('intention',[19],'计划避免饮酒'),('unknown',[7,19],'未提供婚姻改善或戒酒保持结果；支持者保证成功不是结果证据')],
'M09': [('suggestion',[11],'建议一次写一段经历'),('intention',[12],'考虑以工作压力等主题起步'),('attempt',[16],'自报长期通过写作整理想法'),('explicit_preference',[12],'当场赞同分块写作建议；仅该情境，不能升格为稳定回复偏好'),('unknown',[20],'博客尚无已发表或受众效果证据')],
'M10': [('suggestion',[17],'建议从小步骤开始'),('intention',[12,18],'考虑找外部资源或教授，未完成'),('subjective_outcome',[20],'此轮谈话后感觉轻松一些；即时会话反馈，非求助教授的结果')],
'M11': [('attempt',[8,14],'已在治疗中尝试压力管理并与新朋友交流'),('subjective_outcome',[6,10],'新友谊提供分散注意、治疗进步起伏且焦虑仍可触发'),('intention',[16],'计划继续治疗、允许新经历')],
'M12': [('attempt',[6],'已向上级表达困扰'),('subjective_outcome',[6,8],'仍感到不被倾听且被打断；不得重复当作尚未试过的建议'),('suggestion',[16,19],'建议联系关系网或专业人员'),('intention',[17,20,23],'考虑联系或治疗，尚未做'),('unknown',[29,30],'说本次聊天提供思路，不等于治疗或换工作的结果')],
'M13': [('suggestion',[8,16],'建议学校辅导员及重拾阅读'),('intention',[17],'计划重新拿起书'),('unknown',[7,15],'尚未找老师；以往阅读习惯目前不能带来投入，不能说仍有效')],
'M14': [('suggestion',[7,21],'历史支持者提供作息及放松建议；建议本身不等于有效知识'),('unknown',[12,20],'明确指出善心不能阻止醒来担忧；期待睡好并不是睡眠改善结果')],
'M15': [('suggestion',[9,13,19],'建议学习分块、计划和休息'),('intention',[26],'明确将尝试建议'),('unknown',[18,26],'从未用清单或计划本，尚无执行及效果证据；感谢不等于验证有效')],
'M16': [('attempt',[9,19],'已每晚尝试日记，以及冥想或散步'),('subjective_outcome',[9,19],'日记有帮助但有时焦虑太强；冥想/散步有少量帮助，两个动作的贡献无法拆开'),('intention',[15],'在研究更严格预算，不等于已实施预算')],
'M17': [('attempt',[7,8,11,13],'多次要求结束通话并实际挂断'),('subjective_outcome',[7,8,11,22],'朋友继续重复、挂断后易生气，明确说光谈不奏效'),('explicit_preference',[33],'明确不喜欢画画；仅该人自报的活动偏好'),('suggestion',[28,37],'支持者建议转移活动或玩手机'),('intention',[35],'考虑上网，未验证实际使用'),('unknown',[38],'认为方案可能适用面对面而不解决电话情境；不是已试行结果')],
'M18': [('attempt',[17],'正在与 Matthew 理解彼此，尚在进行'),('subjective_outcome',[19,21],'导师赞扬帮助提醒能力、慢慢平衡；主观变化非某个已识别支持策略的因果效果')],
'M19': [('attempt',[2,8,12],'已报名并参加写作工作坊'),('subjective_outcome',[8,12],'写作一点转移注意、给希望，启动仍困难且压力有时上升'),('suggestion',[13],'建议先写几行'),('intention',[14],'计划周末写一两页，未完成')],
'M20': [('attempt',[4,12],'曾借钱并催还；已因离家近工时好换工作'),('subjective_outcome',[4,6,12],'催还引发紧张、新工作仍孤独和不适；不能说换工作已减压'),('suggestion',[15],'建议短步行'),('intention',[14,16],'想开始运动和步行，未证明已做'),('unknown',[18],'此轮倾诉更舒服，不能当步行收益')],
'M21': [('attempt',[2],'已领养新小狗'),('subjective_outcome',[4,10],'预期缓解丧犬，实际有愧疚；小狗带来分散注意也带来训练负担，混合结果'),('subjective_outcome',[14],'David 在场有帮助，同时担忧依赖')],
'M22': [('suggestion',[12,15,24],'建议网约车、更新简历、招聘网站'),('intention',[16,23],'考虑现在去做或考虑 Uber'),('unknown',[20],'相信尝试会奏效是预测，不是已执行结果')],
'M23': [('attempt',[6,8],'已照护母亲、家人有部分分担'),('explicit_preference',[14],'过去喜欢散步；历史偏好，不自动断言当前有效或仍喜欢'),('intention',[16,22,24],'计划为散步留时间及找兄弟姐妹分担'),('unknown',[24],'此次联络尚未发生，是否有效未知')],
'M24': [('intention',[14],'计划今晚和 Jack 谈'),('subjective_outcome',[14],'称以往坦诚交流似有帮助，但不是今晚谈话结果'),('attempt',[15,16],'对已开始绘画的提问给出确认性回应'),('subjective_outcome',[15,16],'绘画有帮助的回答必须携带支持者问句先行词，单独 It does help 指代不足')]
}
assert set(D)==set(byid)
records=[]
for sid,entries in D.items():
 s=byid[sid]
 for j,(category,indices,note) in enumerate(entries,1):
  spans=[dict(turn_index=i,speaker=s['source']['turns'][i]['role'],start_char=0,end_char=len(s['source']['turns'][i]['text']),quote=s['source']['turns'][i]['text']) for i in indices]
  records.append(dict(record_id=sid+'-'+str(j).zfill(2),sample_id=sid,owner_id=s['source']['owner_id'],session_id=s['source']['session_id'],reported_at=s['source']['reported_at'],category=category,source_sha256=s['normalized_source_sha256'],evidence=spans,review_note_zh=note,reviewer='Codex assistant semantic first-pass; not independent human gold',review_status='reviewed_source_complete_single_reviewer',causal_effect_established=False,current_validity='not_revalidated_at_later_target',event_identity=None,relation_to_other_session=None,formal_training_label=False))
for s in sessions:s['review_status']='complete_session_read_single_assistant_first_pass'
(P/'SELECTED_COMPLETE_SESSIONS_PRIVATE.json').write_text(json.dumps(sessions,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
(P/'SEMANTIC_OBSERVATIONS_PRIVATE.json').write_text(json.dumps(records,ensure_ascii=False,indent=2)+'\n')
coverage=[]
for s in sessions:
 sid=s['sample_id'];rr=[r for r in records if r['sample_id']==sid]
 coverage.append(dict(sample_id=sid,key=s['key'],review_scope='all complete exported session turns read',reviewer='Codex assistant; single reviewer',source_sha256=s['normalized_source_sha256'],coverage={c:dict(status='observed_with_source_span' if any(r['category']==c for r in rr) else 'not_identified_in_this_first_pass; not_a_world_negative',record_ids=[r['record_id'] for r in rr if r['category']==c]) for c in ('suggestion','intention','attempt','subjective_outcome','explicit_preference','unknown')},exhaustive_event_extraction=False,independent_human_adjudication='pending'))
(P/'SEMANTIC_REVIEW_COVERAGE.json').write_text(json.dumps(coverage,ensure_ascii=False,indent=2)+'\n')
manifest=json.loads((P/'SAMPLE_MANIFEST.json').read_text())
for m in manifest:m['review_status']='complete_session_read_single_assistant_first_pass';m['coverage_path']='SEMANTIC_REVIEW_COVERAGE.json';m['independent_human_adjudication']='pending'
(P/'SAMPLE_MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2,sort_keys=True)+'\n')
summary=dict(reviewed_complete_sessions=len(sessions),reviewed_owners=len({s['source']['owner_id'] for s in sessions}),unreviewed_selected_sessions=0,observations=len(records),observations_by_category=dict(Counter(r['category'] for r in records)),sessions_by_category={c:len({r['sample_id'] for r in records if r['category']==c}) for c in ('suggestion','intention','attempt','subjective_outcome','explicit_preference','unknown')},labels='assistant-reviewed illustrative source records; neither lexical counts nor independently adjudicated gold; not exhaustive event prevalence',external_G_J_embedding_or_paid_calls=0,assistant_semantic_observations_created=len(records),human_labels=0,production_modified=False)
(P/'REVIEW_SUMMARY.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(summary,ensure_ascii=False,indent=2))
