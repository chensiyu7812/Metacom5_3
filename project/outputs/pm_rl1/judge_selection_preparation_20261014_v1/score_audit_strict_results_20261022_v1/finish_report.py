"""Human-readable closeout from sealed local outputs; no new inference requests."""
from pathlib import Path
import json, html, os, shutil, hashlib, zipfile
from datetime import datetime, timezone
from decimal import Decimal

os.umask(0o077)
R=Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
B=R/'project/outputs/pm_rl1/judge_selection_preparation_20261014_v1'
O=Path(__file__).resolve().parent
read=lambda p:json.loads(Path(p).read_text())
rows=read(O/'ITEM_RESULTS.json');cost=read(O/'VALIDATION_AND_COST.json');close=read(O/'CLOSEOUT.json')
assert close['new_attempts']==3 and close['cumulative']==307 and close['valid']==3 and close['failed']==2
def save(name,x):
    p=O/name;p.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with p.open('x',encoding='utf-8') as f:f.write(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2)+'\n')
    p.chmod(0o600)
v3=read(O/'results/04_V3_ON_r1.json')['evaluation']['value']
bad=v3['findings'][2]['criterion']
assert 'q=3 covers an appropriate reply with an important defect' in bad
rubric=(O/'frozen_preparation/FROZEN_RUBRIC_EN.txt').read_text()
assert '3: appropriate, coherent and responsive, with no important defect.' in rubric
review=dict(author='Codex source/rule review; not new independent human evaluation',
    no_scores_changed=True,no_gold_labels_created=True,
    new_valid_target_controls=[dict(item='V4_OFF',finding='Ordinary invitation/availability not treated as a biographical claim',
        evidence=[dict(source_id='C:T000',quote='Hey, I just need to talk to someone. Is that okay?')],status='local_target_supported'),
      dict(item='V3_ON',finding='Actual attempt to talk is recognized; no claim that it succeeded',
        evidence=[dict(source_id='C:T010',quote="I tried talking to my parents, but we just end up arguing about future plans. They don't really get it.")],status='local_target_supported')],
    confirmed_rule_misstatements=[dict(item='V3_ON',path='/findings/2/criterion',actual=bad,
        frozen_rule='3: appropriate, coherent and responsive, with no important defect.',
        corrected_elsewhere_path='/score_review/checks/quality/criterion',
        corrected_elsewhere=v3['score_review']['checks']['quality']['criterion'],
        conclusion='The criterion contains a direct negation error; the same output elsewhere quotes q3 correctly. This is a confirmed explanation inconsistency, not proof q4 must change or a new user/source factual error.')],
    reviewer_unresolved=[dict(item='V3_ON',type='historical_constraint_quality',
        source_id='H009:T009',quote="I guess that's a good idea. But I'm just so tired of explaining everything over and over, you know?",
        output_reason=v3['score_review']['checks']['quality']['reason'],
        question='Does a low-pressure re-offer adequately respect this earlier fatigue, or does the reason dismiss a relevant constraint merely because it was not restated?',
        conclusion='Earlier fatigue is recorded but its current quality consequence is not uniquely determined. No exact replacement q or m inferred; no new questionnaire.')],
    field_precision_caveats=[dict(item='V3_ON',path='/check/claims/3/action_stage',value='not_applicable',
        observation='The corresponding source and prose correctly recognize an attempted parental conversation, but this field does not encode attempted stage explicitly. Target relation recognized does not certify all structured stage fields.')],
    inherited=dict(V3_OFF_r1='Prior accounting recognized; one original-interface observation only',
        dev06B_r1='Original invalid final remains null; no recovery or semantic success'),
    failed_new=dict(dev04B='Invalid whole tool arguments; raw text available but no validated audit or formal semantic outcome'),
    unobserved=['dev35B/r1','dev06B/r2','V3_OFF/r2'],
    denominators=dict(new_valid=2,new_started=3,new_planned=6,all_valid=3,all_started=5,all_planned=8,
        valid_distinct_replies=3,planned_distinct_replies=6,valid_contexts=2,planned_contexts=5,
        valid_owners=2,planned_owners=4,complete_valid_repeat_pairs=0),
    model_unknown=dict(new=0,new_denominator=2,all=0,all_denominator=3,failed_and_unstarted=None),
    model_score_review_unresolved=dict(new=0,new_denominator=2,all=0,all_denominator=3),
    analyst_categories=dict(confirmed_source_disproved_new_accusations=0,confirmed_rubric_restatement_error=1,reviewer_unresolved_quality_case=1,
        note='Counts describe these valid outputs only, not an accuracy estimate or independent cases. Multiple caveats concern one V3_ON output.'),
    routing=dict(comparable_valid_outputs=3,old_trigger_flags=1,new_supplement_flags=0,
        new_retain_candidate=3,actual_supplement_calls=0,actual_saved_calls=0,
        interpretation='Proposed routing only; the rule misstatement shows mechanically valid supported checks do not establish trustworthy acceptance.'),
    conclusion='INCONCLUSIVE_TECHNICAL_STOP_WITH_LOCAL_CONTROL_EVIDENCE_AND_ONE_CONFIRMED_RUBRIC_RESTATEMENT_ERROR',
    next='Do not enable automatic routing or reward use. Delivery guarantee remains unestablished; key missed-score target and planned repeats are incomplete. No extra sampling or retrospective repair is authorized.')
save('LOCAL_REVIEW.json',review)
notes={1:'旧接口有效：识别初评已处理；只是一份观察',2:'旧接口失败：完整final多余右括号，正式值仍null',
 3:'新接口有效：普通邀请未被误判为个人事实',4:'新接口有效：来源中的谈话尝试识别正确；q3条款复述自相矛盾',
 5:'新接口失败：完整工具参数末尾多余右括号',6:'04B技术STOP后未派发',7:'04B技术STOP后未派发',8:'04B技术STOP后未派发'}
report='''# PM-RL1 严格交付接续：结果与决定

本轮已实际运行并按既定技术守卫停止：新增3次，2份有效、1份格式失败；剩余3槽未派发。累计307/容量374。旧两次与本轮合并为原8槽中的5次尝试：3有效、2失败、3未派发。

**这次增加了两项控制的有效观察，但官方Beta strict工具参数仍出现非法JSON。关键漏判目标及重复未完成，不能启用自动反馈路由或奖励。** 本轮结束，没有改提示、分数、来源、量表、PPO，也没有重试、删括号、补核、生成、GPU任务或训练。

## 1. 原8槽状态（旧、新交付分开）

|槽|材料/重复|交付|状态|历史q/m/U，非本轮新评分|结论|
|---|---|---|---|---|---|
'''
for x in rows:
    state={'completed':'有效','failed':'技术失败','not_dispatched':'未派发'}[x['status']]
    report+=f'|{x["position"]}|{x["item"]}/r{x["repetition"]}|{"旧final" if x["inherited_attempt"] else "Beta strict工具参数"}|{state}|{x["old_q"]}/{x["old_m"]}/{x["old_U"]}|{notes[x["position"]]}|\n'
report+='''
新接口有效交付2/3已开始、2/6获准槽；混合接口合计3/5已开始、3/8原计划槽。6条不同回复仅3条有有效审查，覆盖2/5语境、2/4来源owner；均为已暴露开发材料。没有完整有效重复组，未派发不算模型答错。旧06B失败不恢复成有效结果，V3_OFF也没有完成跨接口重复。历史初评不是同期联合评分对照。

## 2. 有效结果究竟支持什么

**V4_OFF：普通邀请控制通过局部核对。** 当前原文C:T000是“Hey, I just need to talk to someone. Is that okay?”；完整回复为“That sounds completely okay. I'm here to listen. What's on your mind?”。审查将其解释为同意交谈、提供当下倾听与开放邀请，未把普通第一人称可用性当成冒认先前支持者经历。对照初评的三项理由逐一关联，没有制造新评分缺陷。这支持该控制的局部行为，不认证唯一q4。

**V3_ON：有支持的行动被识别，但评分说明仍不完全可靠。** C:T010明确：“I tried talking to my parents, but we just end up arguing about future plans. They don't really get it.”。审查引用该句，正确支持回复中的既往谈话归属，未把“尝试过”当成仅有建议，也没有推断谈话成功。不过/check/claims/3/action_stage仍为not_applicable，结构化行动字段的精度没有完全落实，不能仅凭解释文字宣布自动行动阶段识别已验收。

还发现一处**可直接核对的量表复述错误**。同份输出/findings/2/criterion说“q=3 covers an appropriate reply with an important defect”；冻结量表第11行则是“3: appropriate, coherent and responsive, with no important defect.”。随后/score_review/checks/quality/criterion又写回“no important defect”。这是一份有效输出内部的判据矛盾，不是量表缺失，也不直接证明历史q4必须降低。程序的schema/引文/绑定校验不能发现这种语义矛盾，当前自动路由仍将其列为retain_numeric_candidate，因此不能把这个路由当奖励准入。

此外，H009:T009说“I guess that's a good idea. But I'm just so tired of explaining everything over and over, you know?”。审查承认回复再次建议学校辅导员，却以当前前缀未重述疲倦为部分依据，将遗漏判为不阻断q4。此前疲倦与当前可选建议之间的质量后果尚有可讨论空间；没有独立唯一q标签，保留为**复核者未决**，不冒称确定事实错误、不新造q/m。

旧V3_OFF/r1仍只支持“已有缺陷已被初评分处理”的一次局部观察。其来源C:T006说“Lily leaving”，H009:T001说Lily moving，未建立家庭成员关系；初评已经处理unsupported/local。新触发式与旧触发式在这同一输出上的差异是真实的离线规则差异，不是两臂模型实验，也没有实际节省调用。

模型check unknown及score-review unresolved在本轮2份有效输出中均为0；旧新3份有效输出中也均为0。失败和未派发的这些字段是缺失，不补0。上述分析者未决和量表复述错误独立记录，不能因模型全部写supported就消失。新有效输出未见来源直接反证的新指控，但有1条已确认判据错述、1个质量未决案例，集中在同一V3_ON，不扩算成多个独立病例。没有完整金标，不报告语义准确率。

## 3. 严格工具交付为什么仍然停止

04B请求真实发送至官方`https://api.deepseek.com/beta/chat/completions`，`submit_audit`设置strict=true、tool_choice=auto，Flash/high及输出边界不变。返回恰好一个工具调用，content为空，finish_reason=tool_calls，完整usage及[DONE]到齐；不是超时、截断、未结费用或拒绝工具交付。

然而完整arguments共11,152字符，末尾偏移11,151（从0计）多出一个右花括号，解析报`Extra data: line 1 column 11152 (char 11151)`。独立逐段拼接原始SSE arguments与保存内容逐字相同，多余字符已在收到的流里。可以确认这次交付违反完整JSON要求；不能仅凭一次现象断言服务内部使用了何种解码机制，或推算普遍失败率。

失败的完整参数仍在finals/05_dev04B_r1.txt和raw/strict中。只做字节与括号定位，没有解析前缀、删除字符、从thinking找答案或建立“恢复有效”记录。其正式审查value保持null；原旧06B也保持null。04B的文字不能计为有效歧义处理证据。STOP是技术出口，不是已证明04B的某一读法错误。

## 4. 时间、用量、实际记账与责任

|请求|耗时秒|输入token|总输出token|thinking子集|保守记账USD|按usage/缓存/时段估算USD|
|---|---:|---:|---:|---:|---:|---:|
'''
for x in rows:
    if x['elapsed_seconds'] is not None:
        report+=f'|{x["item"]}/r{x["repetition"]}{"（旧）" if x["inherited_attempt"] else "（新）"}|{x["elapsed_seconds"]:.3f}|{x["prompt_tokens"]}|{x["completion_tokens"]}|{x["reasoning_tokens"]}|{x["accounted_upper_usd"]}|{x["usage_price_estimate_usd"]}|\n'
report+=f'''
新增保守账 **${cost['continuation_accounted_usd']}**；同阶段含旧两次合计 **${cost['phase_accounted_usd']}**，没有重置$1上限。完整usage按缓存及时段估算新增${cost['continuation_usage_price_estimate_usd']}，整阶段${cost['phase_usage_price_estimate_usd']}；本轮落在既有计费器的非高峰时段，估算低于保守账。未取得平台账单对账，不将估算差额当成已确认退费。

API试验及共享后续保守累计 **${cost['trial_accounted_including_liability_usd']}**，含原历史基线总账${cost['full_ledger_including_liability_usd']}；已知未结责任 **$0**。本轮models、balance各一次，整阶段各两次，均为相应授权的管理查询，不计评分。前检可用余额按既有币种费率折算$1.8285（不是外汇报价），当时足够预留；没有充值或修改账户。

新增请求合计{cost['continuation_usage']['request_elapsed_seconds']:.3f}秒，输入61,302、输出35,839，其中thinking 26,452是输出子集；旧新请求共{cost['whole_phase_usage']['request_elapsed_seconds']:.3f}秒。GPU时间0。本次停机因格式失败，非预算不足：整阶段已花${cost['phase_accounted_usd']}加下一条原生预留$0.786432仍低于$1，但技术守卫独立有效，不能因此继续派发。

共享$20剩余账面责任空间约${cost['shared_remaining_usd']}，不等于后续阶段已获授权。旧全研究场景仅滚动加入此次实耗后：单评约$26.90/$39.24、旧等均价审查约$51.90/$76.59，仍非精确去重预算或新报价，仍不能宣称完整四头研究装进$20。本次3项不足以估计总体成功率或恢复成本；未选择128/384，正式比较和独立终评全部保留。

## 5. 按预定规则作出的决定

本批属于**技术中断、方法推进条件尚不能判定**。两个新控制显示局部正确行为；关键06B漏判目标没有新有效结果，35B严重度检查和两组重复仍缺。不能将这次当语义方法全面失败，也不能将有效控制当自动反馈合格。

应停止把“启用strict”当成交付可靠性的已证实修复，不能再用同样承诺直接申请补跑。此次原始流定位已充分，不需要新增模型请求来重复确认这个格式故障。下一项工程决定必须明确如何保证或处理序列化失败，以及哪些转换有权进入正式结果；当前禁止删括号和重试的协议不能自行改变。剩余3槽没有自动接续权，已开始5槽永不重派。

评分端保留此次明确的判据矛盾及历史约束未决：已有规则足以指出q3复述错误，无需另造量表或重发人评；它说明“审查说supported”本身尚不能成为资格证明。此次不启用自动保留/补核路由，不改旧分，也不制作修正后的OFF/ON收益。

完整研究继续保留四头RS/MP/MS/ME顺序GET/STOP和读后决策、真实BC起点、OFF/FixedDev/匹配随机/OneShot/BC-union/PPO/NoText、多种子及独立终评。当前自然更新0。到此停止，不自动进入C、提示修订、补核、资格验收、封存或训练。

## 附件入口

- ITEM_RESULTS.json / csv：全部8槽、实际请求身份、回复/来源/初评分哈希、历史分数、用量与状态。
- LOCAL_REVIEW.json：逐项局部核对、明确判据错述、未决与分母；不是新增独立人评。
- STRICT_DELIVERY_FAILURE_DIAGNOSIS.json：原始流独立拼接、偏移、哈希和尾部片段；未修复。
- finals/ 与 raw/old、raw/strict：完整旧final、新工具参数、原始SSE、请求、响应、结果、封印和STOP。
- materials/：6条完整回复、当前对话、合法历史及历史初评分。
- VALIDATION_AND_COST.json / VERIFICATION.json：真实成本、计数、封印与历史完整性核对。
'''
save('REPORT_ZH.md',report)
parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PM-RL1 严格交付接续结果</title><style>body{max-width:1120px;margin:28px auto;padding:0 18px;font:17px/1.7 system-ui;color:#17212b}pre{white-space:pre-wrap;overflow-wrap:anywhere;padding:18px;background:#f3f5f7}details{padding:12px;border:1px solid #cbd4df;margin:15px 0}summary{cursor:pointer;font-weight:600}a{color:#175c91}</style><h1>PM-RL1 严格交付接续结果</h1><p><b>新增3次：2有效、1格式失败，余下3槽未派发。累计307/374。已停止。</b></p><p>新增保守账$0.0613974；同阶段合计$0.1162971；未结责任$0。旧分、失败与STOP保留，无训练。</p><p><a href="REPORT_ZH.md">中文报告</a> · <a href="ITEM_RESULTS.csv">全部8槽</a> · <a href="LOCAL_REVIEW.json">来源与规则复核</a> · <a href="STRICT_DELIVERY_FAILURE_DIAGNOSIS.json">交付故障证据</a></p><pre>'+html.escape(report)+'</pre>']
for x in rows:
    parts.append(f'<details><summary>{x["position"]}. {x["item"]}/r{x["repetition"]}：{html.escape(notes[x["position"]])}</summary><pre>{html.escape(json.dumps(x,ensure_ascii=False,indent=2))}</pre>')
    fp=O/f'finals/{x["position"]:02d}_{x["item"]}_r{x["repetition"]}.txt'
    if fp.exists():parts.append('<h3>完整交付原文（含失败原文，未修复）</h3><pre>'+html.escape(fp.read_text())+'</pre>')
    parts.append('</details>')
parts.append('<h2>完整来源与历史初评分</h2>')
for fp in sorted((O/'materials').glob('*.txt')):
    parts.append('<details><summary>'+html.escape(fp.name)+'</summary><pre>'+html.escape(fp.read_text())+'</pre></details>')
parts.append('</html>');save('阅读结果.html',''.join(parts))
print('Report and reader completed:',O)
