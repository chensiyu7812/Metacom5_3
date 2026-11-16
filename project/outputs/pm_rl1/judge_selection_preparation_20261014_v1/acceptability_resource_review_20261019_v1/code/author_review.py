"""Explicit analyst interpretations; never model scores or human references."""
from pathlib import Path
import json

OUT=Path(__file__).resolve().parents[1]
rows=json.loads((OUT/'materials/selected_existing_records.json').read_text())
contexts=json.loads((OUT/'materials/contexts.json').read_text())
byid={r['row_id']:r for r in rows}
review=[]

def add(cid,plan,status,need,delta,reason,spans,source_ids,issue=None):
    rid=cid+'_'+plan
    r=byid[rid]
    allowed={t['id']:t for t in contexts[cid]['current_prefix']}
    for s in contexts[cid]['legal_past_sessions']:
        allowed.update({t['id']:t for t in s['turns']})
    for span in spans:assert span in r['reply'],(rid,span)
    for sid in source_ids:assert sid in allowed,(rid,sid)
    review.append(dict(row_id=rid,context_id=cid,analyst='Codex',
        classification=status,classification_kind='offline_applicability_hypothesis_not_eligibility_label',
        reward_eligible=False,human_label=None,new_model_request=False,
        current_need=need,resource_delta=delta,reason=reason,reply_spans=spans,
        evidence=[dict(id=sid,role=allowed[sid]['role'],text=allowed[sid]['text']) for sid in source_ids],
        issue=issue,old_scores_untouched=True))

need='承接对职场偏袒的不满，并允许分析、探询或建议；不要求唯一最佳处理办法。'
add('context_01','0000','unresolved',need,'无资源。',
    '承接与建议得到原研究者认可；团队士气/生产力的事实预设与一般讨论双读法仍保留，不能自动变成新的合格标签。',
    ["how this favoritism affects your team's morale and productivity"],['C:T001','C:T006','C:T008'],'team_impact_reading')
add('context_01','1000','plausibly_acceptable',need,'RS建议询问是否与他人讨论，回复出现相同动作。',
    '有可追溯的策略采用；询问讨论是否发生，没有认定发生。避开OFF团队影响争点，但OFF并非已裁定不合格，不能计确定跨门槛改善。',
    ['Have you talked to anyone else about this situation'],['C:T006','C:T008'])
add('context_01','0100','unresolved',need,'MP记录姐妹支持照护压力，与本次职场问题并非同一事实。',
    '未看到姐妹细节进入回复；仍保留与OFF相同的团队影响双读法。',
    ["how this favoritism affects your team's morale and productivity"],['C:T006','C:T008','H004:T007'],'team_impact_reading')
add('context_01','0010','plausibly_acceptable',need,'MS是照护母亲的旧会话；回复未明确使用其中独有信息。',
    '当前已明确存在职场偏袒与困扰，讨论工作环境并未额外认定士气或生产力后果；存在合理可接受依据，但不是人类认证。',
    ['how this favoritism affects your work environment'],['C:T006','C:T008','H003:T004'])
add('context_01','0001','plausibly_acceptable',need,'ME记录过去获得支持；未发现需要此条历史才能支持的新事实。',
    '记录事件、寻求HR支持被表达为可选策略，不断言已经实施。比OFF更具体不自动意味着更优。',
    ['such as documenting specific instances or seeking support from HR'],['C:T006','C:T008','H004:T019'])
add('context_01','1111','plausibly_acceptable',need,'组合含相同RS和三类记忆；可见提问与RS一致，不能识别各项边际贡献。',
    '以是否与他人讨论的开放问题承接；没有充分证据表明额外三类记忆相对单RS有必要收益。',
    ['have you discussed this specific situation with anyone else'],['C:T006','C:T008'])

need='用户询问前一支持者如何处理其亲身经历；新AI不能认领，需以不误导方式处理身份承接，同时回应愤怒与交友自主。'
for plan,delta,reason,spans,ids,issue in [
 ('0000','无资源。','研究者确认了谈话已发生的预设；旧旅行讨论不能直接支持本次谈话。还存在未澄清身份；原人评给2–3/.25，不能据此补造总体不合格标签。',
  ['Did you find that talking to her about how her rules make you feel helped to calm the anger'],['C:T008','C:T009','H002:T004','H002:T010','H002:T021'],'action_presupposition_and_identity_omission'),
 ('1000','RS询问是否向朋友表达感受，回复有明确对应。','不再使用OFF的已发生母女谈话句式，但仍没有处理用户对前一支持者经历的询问；事实风险减少与总体合格须分开。',
  ['Have you talked to any of your friends about how you feel'],['C:T008','C:T009'],'identity_omission'),
 ('0100','MP是旧会话中的“最受宠孩子”；未被回复明确引用。','控制感/不信任以问题探索，不是既定动机；仍未回应身份承接，保留整体适当性边界。',
  ["Is it the feeling of being controlled, or the sense that she doesn't trust your judgment?"],['C:T007','C:T008','C:T009','H002:T020'],'identity_omission'),
 ('0010','MS是此前关于与男友旅行和父母信念的讨论。','回复复述当前交友自主与愤怒；没有明确借用旅行经历。提问允许多种继续方式，但身份承接问题未解决。',
  ['Do you want to talk more about what specifically makes you angry'],['C:T007','C:T008','C:T009','H002:T004'],'identity_omission'),
 ('0001','ME描述此前一个月旅行/关系讨论；回复即原06A。','OFF的具体已发生谈话预设不再出现；原研究者仍指出缺少身份澄清。不能把少一个问题算已经整体合格。',
  ['Is it the feeling of being controlled, or the fear of disappointing her?'],['C:T008','C:T009','H002:T004','H002:T010'],'identity_omission'),
 ('1111','组合包含旅行谈话ME和该MS，以及RS/MP。','“how have you tried”再次预设沟通尝试；当前有争论、历史有另一话题沟通，支持关系并不确定。身份问题同样保留。',
  ['how have you tried to communicate that to her?'],['C:T007','C:T008','C:T009','H002:T004','H002:T010'],'identity_omission_and_communication_reading')]:
    add('context_02',plan,'unresolved',need,delta,reason,spans,ids,issue)

need='肯定老同学的帮助，延续对论文新视角的讨论；帮助者和谈话已发生均在当前对话中明确。'
for plan,delta,span in [
 ('0000','当前对话本身已经提供导师反馈、老同学及新视角；无需历史即可支持回复。','their insights'),
 ('1000','RS提供肯定/鼓励继续求助；回复有肯定，但无法排除仅由当前对话引出。','How are you feeling about your thesis now?'),
 ('0100','MP记录治疗费用顾虑；回复没有使用该历史内容。',"now that you've had that conversation"),
 ('0010','MS是过去论文受挫记录；新回复也可由当前论文与朋友谈话直接支持，未检出必要的独有历史贡献。','Have you been able to make any progress since that conversation?'),
 ('0001','ME记录另一过去谈话使人更乐观；当前已明确朋友谈话有帮助，不能将两次事件混为一条来源。','this new view'),
 ('1111','组合回复的视角/卸下重担已在当前对话出现；未检出额外历史对最低需求的必要贡献。','lift that weight off your shoulders')]:
    add('context_03',plan,'plausibly_acceptable',need,delta,
        '未将老同学的帮助归给AI；后续问题与当前话题衔接。泛化肯定不是最优性证明，仍只有分析者复核。',
        [span],['C:T003','C:T005','C:T009','C:T011','C:T013'])

need='用户只说近来困难；先承接并询问具体原因，不能擅自指定求职、睡眠或婚姻为当前原因。'
for plan,delta,span in [
 ('0000','无资源已能承接与澄清。',"what's been going on"),
 ('0100','MP记录过去睡眠困难；回复没有把它升级为当前困境。','What specifically has been making things difficult?'),
 ('0010','MS记录过去饮酒/婚姻问题；回复没有把它升级为当前困境。','How can I support you today?'),
 ('0001','ME记录过去饮酒影响婚姻；回复维持开放探询。',"what's been going on"),
 ('1111','含同一求职RS，但回复未出现求职断言；不能由单RS一次结果推断其必然被采用。','How can I support you today?')]:
    add('context_04',plan,'plausibly_acceptable',need,delta,
        '对当前尚未说明的困难保持开放；未检出需要资源才能满足的最低需求。这里的认可只是草案适用性分析。',
        [span],['C:T002','H001:T003','H002:T003'])
add('context_04','1000','explicit_problem',need,
    '实际RS原文为“share that it is a difficult time to be job hunting”；回复将该情境套到当前用户。',
    '当前前缀和两次合法过去会话没有求职依据。原研究者已明确指出同一回复问题；这是来源不支持的个人情境指派，不是证明用户现实中绝不求职。OFF无此问题。',
    ['especially when it comes to job hunting'],['C:T002','H001:T003','H002:T003'],'unsupported_job_hunting_from_RS')

assert set(byid)=={r['row_id'] for r in review}
review.sort(key=lambda r:list(byid).index(r['row_id']))
p=OUT/'analyst_review.json'
data=json.dumps({'version':'acceptability-applicability-analyst-v1','not_independent_human':True,
    'not_reward_labels':True,'no_new_q_m':True,'classification_definitions':{
    'plausibly_acceptable':'按最低要求草案有可接受依据；不是正式合格认证',
    'explicit_problem':'存在可定位的问题；不重写旧q/m或STOP',
    'unresolved':'整体合格边界仍未确定；不是失败、平局或零奖励'},'rows':review},ensure_ascii=False,indent=2)+'\n'
if p.exists():assert p.read_text()==data
else:p.write_text(data)
print('Authored analyst reviews:',len(review))
