"""Read-only analysis of sealed attempts. Never calls a model or repairs final JSON."""
from pathlib import Path
from decimal import Decimal
from datetime import datetime, timezone
import importlib.util, json, os, hashlib, shutil, html, csv

os.umask(0o077)
R = Path('/opt/tokkio-data0/tokkio_projects/Metacom5_3')
spec = importlib.util.spec_from_file_location('entry', R/'project/scripts/rl1/123_score_audit_validation.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
pr, items, scores, rubric = m.load(); p = m.existing.engine()
root = Path(pr['run_dir']); out = Path(__file__).resolve().parent
auth = m.BASE/'score_audit_validation_authorization_20261022_v1'
started, results = p.replay(root, pr)
m.d.verify_receipts(p, root, pr, started, results); m.v.historical_guard(pr, m.BASE)
m.v.require_approval(pr, m.r.read(auth/'APPROVED.json'))
assert (root/'STOP.json').exists() and len(started)==2 and len(results)==2
summary = m.v.summary(pr, root, p, scores)
now = datetime.now(timezone.utc).isoformat()

def save(name, x):
    dest=out/name; dest.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with dest.open('x',encoding='utf-8') as f:
        f.write(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2)+'\n')
    dest.chmod(0o600)

save('ALL_SLOTS.json',summary)
save('STOP.json',m.r.read(root/'STOP.json'))
rows=[]; raws={}; financial=[]
from deepseek_access import cost_from_usage
for slot in summary['slots']:
    sid=slot['slot_id']; key=slot['item_key']; result=slot['result']
    original=scores[key]['evaluation']
    row=dict(position=slot['position'],item=key,repetition=slot['repetition'],status=slot['status'],
        request_id=result['request_identity'] if result else None,
        historical_score_request=scores[key]['request_identity'],reply_sha256=slot['reply_identity'],
        evidence_sha256=slot['evidence_identity'],old_q=original['value']['q'],old_m=original['m'],old_U=original['U'],
        new_q=None,new_m=None,new_U=None,
        technical_valid=result['technical_valid'] if result else None,
        model_unknown=None,model_unresolved=None,elapsed_seconds=None,prompt_tokens=None,
        completion_tokens=None,reasoning_tokens=None,accounted_upper_usd=None,
        usage_price_estimate_usd=None,unsettled_usd=None,routing=None,
        reason='prior slot 2 technical STOP; never dispatched' if not result else '')
    if result:
        req=m.r.read(root/(sid+'.request.json'))
        preview=m.r.read(m.PREP/'outbound_private'/f'{slot["position"]:02d}.json')
        assert (req['messages'],req['schema'])==(preview['messages'],preview['schema'])
        raw=m.r.read(root/(sid+'.response.json'));raws[slot['position']]=raw
        final=raw['choices'][0]['message']['content'];save(f'finals/{slot["position"]:02d}_{key}_r{slot["repetition"]}.txt',final)
        fin=cost_from_usage(raw);financial.append(fin)
        usage=result['usage'];ev=result['evaluation']
        row.update(elapsed_seconds=result['elapsed_seconds'],prompt_tokens=usage['prompt_tokens'],
            completion_tokens=usage['completion_tokens'],reasoning_tokens=usage['completion_tokens_details']['reasoning_tokens'],
            accounted_upper_usd=result['financial']['accounted_upper_usd'],usage_price_estimate_usd=fin['usage_price_estimate_usd'],
            unsettled_usd=result['financial']['unsettled_reservation_usd'],routing=slot['candidate_routing']['action'])
        if result['technical_valid']:
            row.update(model_unknown=ev['value']['check']['status']=='uncertain',
                model_unresolved=any(x['status']=='unresolved' for x in ev['value']['score_review']['checks'].values()) or any(x['disposition']=='unresolved' for x in ev['value']['score_review']['findings']),
                reason='Valid audit recognizes the same localized defect was already accounted; no new score produced.')
        else:
            row['reason']=ev['error'];row['invalid_final_not_recovered']=True
    rows.append(row)
save('ITEM_RESULTS.json',rows)
with (out/'ITEM_RESULTS.csv').open('x',encoding='utf-8-sig',newline='') as f:
    fields=list(dict.fromkeys(k for x in rows for k in x));w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)

# Lexical syntax diagnosis only. Do not parse a prefix, remove trailing bytes, or admit a derived score.
bad=raws[2]['choices'][0]['message']['content'];stack=[];inside=False;escape=False;extra=[]
for i,ch in enumerate(bad):
    if inside:
        if escape:escape=False
        elif ch=='\\':escape=True
        elif ch=='"':inside=False
    elif ch=='"':inside=True
    elif ch in '{[':stack.append(ch)
    elif ch in '}]':
        if not stack:extra.append(dict(offset_zero_based=i,character=ch))
        else:
            assert (stack.pop(),ch) in [('{','}'),('[',']')]
assert extra==[dict(offset_zero_based=10675,character='}')] and not stack and not inside
save('FORMAT_FAILURE_DIAGNOSIS.json',dict(request_id=rows[1]['request_id'],
    final_sha256=hashlib.sha256(bad.encode()).hexdigest(),characters=len(bad),
    finish_reason=raws[2]['choices'][0]['finish_reason'],extra_closing_tokens=extra,
    suffix=bad[-120:],parser_error=rows[1]['reason'],original_body_response_format='json_object',
    complete_usage=True,timeout=False,truncation=False,source_binding_valid=True,
    repair_performed=False,prefix_parsed=False,derived_valid_result_created=False,
    formal_audit_value=None,semantic_success_counted=False,
    interpretation='Completed final has an extra closing brace. This is syntax delivery failure; full schema/source validation was not reached.'))

fin=pr['financial_baseline'];s=p.s
budget=p.DiagnosticBudget(Path(fin['ledger_path']),trial=fin['financial_trial_identity'],study=m.v.VERSION,
    stage_cap=s.nanodollars('1'),trial_cap=s.nanodollars('3.65'),shared_cap=s.nanodollars('20'),
    baseline=s.nanodollars('1.50724291'),opening=s.nanodollars('.03079930'))
total,trial,reserved,settled=budget._totals(budget.events())
assert not(set(reserved)-set(settled))
cost=dict(accounted_upper_usd=s.usd(budget.stage_total(reserved,settled)),
    usage_price_estimate_usd=str(sum(Decimal(x['usage_price_estimate_usd']) for x in financial)),
    invoice_confirmed=False,trial_accounted_usd=s.usd(trial),shared_followup_usd=s.usd(total-budget.baseline),
    full_ledger_usd=s.usd(total),known_unsettled_usd='0',shared_remaining_usd=s.usd(s.nanodollars(20)-(total-budget.baseline)),
    prompt_tokens=sum(x['prompt_tokens'] or 0 for x in rows),completion_tokens=sum(x['completion_tokens'] or 0 for x in rows),
    reasoning_tokens_subset=sum(x['reasoning_tokens'] or 0 for x in rows),
    request_elapsed_seconds=sum(x['elapsed_seconds'] or 0 for x in rows),local_gpu_seconds=0,
    management_requests=dict(models=1,user_balance=1),ledger_path=fin['ledger_path'],ledger_sha256=m.r.sha(fin['ledger_path']),
    model='deepseek-flash',published_mapping=pr['config']['published_mapping'],thinking='enabled/high',
    fingerprints=sorted(set(x['fingerprint'] for x in results.values())),
    stage_limit_usd='1',trial_limit_usd='3.65',shared_limit_usd='20',
    native_single_reserve_usd='.786432',stop_cause='technical JSON delivery, not budget exhaustion')
save('VALIDATION_AND_COST.json',cost)
save('LOCAL_REVIEW.json',dict(author='Codex evidence review, not independent human labels',
    valid_audit_reference=dict(item='V3_OFF',source_ids=['C:T006','H009:T001'],score_path='/assessments/2/reason',
        finding='already_accounted',observation='Explicit same-claim linkage is supported by the historical initial score; quality/severity support remains a machine judgment, not new human gold.'),
    failed_final_text_only=dict(item='dev06B',
        observation='The final text discusses the prior-discussion presupposition separately from its possible effects, and criticizes the original non_factual classification.',
        limitation='Invalid JSON; no recovered object or formal valid audit; cannot count as target repair, passing repeat, or new numeric score.'),
    planned_controls_not_observed=['V4_OFF','V3_ON','dev04B','dev35B'],complete_repeat_pairs=0,
    valid_delivery_denominator=dict(valid=1,started=2,planned=8,distinct_replies_with_valid_audit=1,planned_distinct_replies=6),
    model_unknown=dict(count=0,denominator_valid=1,failed_status=None,not_dispatched_status=None),
    semantic_disputes='No adjudication of pre-existing q/severity boundaries; unmeasured is not resolved.',
    same_output_routing=dict(comparable_outputs=1,old_trigger=True,new_action='retain_numeric_candidate',
        actual_repairs=0,actual_savings_usd='0',not_independent_two_arm_experiment=True),
    decision='INCONCLUSIVE_TECHNICAL_STOP: local prior-accounting behavior observed once; true-miss repeated target and controls not completed.',
    next_step='Address output delivery in a separately approved engineering continuation, before another semantic modification. Preserve the two attempts, allow no automatic retry or brace repair; remaining six slots need explicit continuation scope. No C/PPO/qualification.'))
save('CLOSEOUT.json',dict(status='STOPPED_SCOPE_CLOSED',utc=now,protocol_identity=pr['identity'],
    baseline=302,new_attempts=2,cumulative=304,active_capacity=374,stage_cumulative_cap=310,
    authorized_max=8,valid=1,failed=1,not_dispatched=6,remaining_executable_without_new_decision=0,
    phase_budget_exhausted=False,cost=cost,old_stops_preserved=True,old_scores_preserved=True,
    new_numeric_scores=0,repairs=0,generations=0,training_updates=0,reward_eligible=False))
save('VERIFICATION.json',dict(utc=now,protocol_identity=pr['identity'],original_code_and_inputs_unchanged=True,
    historical_started_and_stop_hashes_unchanged=True,sealed_attempts_verified=2,exact_outbound_preview_matches=2,
    old_302_preserved=True,management_requests=2,unsettled=0,independent_retries=0,
    original_contract_sha256=m.r.sha(R/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json'),
    offline_tests_passed=13,pytest_not_installed=True,tests_ran_with_unittest=True,
    natural_updates=0,no_gpu_loaded=True))

report='''# PM-RL1 评分审查诊断：本批结果

**已实际执行，因第2项JSON交付失败按规则停止。结论是诊断未完成，不是审查方法已通过，也不是语义方法已被否定。**

本批2次真实尝试：1份有效、1份技术失败，余下6项未派发。累计304/容量374；本阶段310边界不变，但STOP后不再自动接续。此前302次、所有STOP、原q/m/U及本次失败全部保留。没有修补JSON、重试、补核评分、生成、GPU占用或PPO更新。

第一项V3_OFF能把“回复有问题”与“初评分漏判”分开：它引用原 `/assessments/2/reason`，确认“Lily离开被写成家庭变化”已被初评判为unsupported/local。原文C:T006只说“Lily leaving”，H009:T001说“Finding out Lily is moving…”；两者不建立家庭成员关系。新审查标记already_accounted，并分别核对q、严重度、覆盖；未虚构另一个遗漏。旧触发式在同一输出上会要求补核，新触发式保留原数字候选。这里只观察到一次机制行为，不证明原q3/m0.25是独立金标，也没有实际节省一次调用。

第二项06B自然结束并交付完整usage，但完整final的最后一个字符是额外右花括号：`Extra data: line 1 column 10676 (char 10675)`。不是超时、截断、未知费用或输入来源丢失。请求已经使用json_object模式和完整schema说明；这一次仍出现语法交付故障。原失败value保持null。诊断只记录末尾多余字符，没有提取JSON前缀、删括号或派生“恢复成功”。

失败final的可见文字讨论了“先前具体谈话已经发生”的前提，也指出原初评将其视为non_factual的问题；这些文字仅供阅读，不计入有效核查成功率，不代替schema和来源链完整校验，更没有得到新的q/m/U。不能据它宣布06B已修复。06B第二次、V3_OFF第二次和四个控制均未运行，因此重复稳定性、误指控及歧义处理没有得到本轮证据。

## 全部8项

| 顺序 | 材料/重复 | 状态 | 原q/m/U（仅历史） | 本次处理 |
|---|---|---|---|---|
'''
for x in rows:
    state={'completed':'有效交付','failed':'技术失败','not_dispatched':'未派发'}[x['status']]
    note='识别已有处理；保留原数字候选，不进入训练' if x['position']==1 else '完整final末尾多余}；正式审查null' if x['position']==2 else '第2项技术STOP；未计调用、未计错误'
    report+=f'| {x["position"]} | {x["item"]}/r{x["repetition"]} | {state} | {x["old_q"]}/{x["old_m"]}/{x["old_U"]} | {note} |\n'
report+='''
有效交付为已开始的1/2、计划槽的1/8；6条不同回复仅1条有有效新审查。0组完整重复。模型unknown为0/1份有效结果；失败与未派发的unknown状态缺失，不能补0。未派发不算答错。没有完整主张金标，不报告语义准确率。5个当前语境、4个owner全是已暴露开发材料，重复不增加独立样本；V3_OFF/ON共享情境，04B/35B共享owner。

## 真实用量与账本

'''
report+=f'两次串行请求合计{cost["request_elapsed_seconds"]:.3f}秒（约{cost["request_elapsed_seconds"]/60:.2f}分钟）；输入{cost["prompt_tokens"]:,}、总输出{cost["completion_tokens"]:,} tokens，其中thinking {cost["reasoning_tokens_subset"]:,}是输出子集，不重复相加。未加载本地模型，GPU时间0。\n\n'
report+='| 请求 | 秒 | 输入token | 输出token（含thinking） | thinking子集 | 保守记账USD | usage计价估算USD |\n|---|---:|---:|---:|---:|---:|---:|\n'
for x in rows[:2]:report+=f'| {x["item"]}/r1 | {x["elapsed_seconds"]:.3f} | {x["prompt_tokens"]} | {x["completion_tokens"]} | {x["reasoning_tokens"]} | {x["accounted_upper_usd"]} | {x["usage_price_estimate_usd"]} |\n'
report+=f'\n本批保守记账 **${cost["accounted_upper_usd"]}**；按完整usage含缓存计价估算 **${cost["usage_price_estimate_usd"]}**，未冒称已获得平台账单对账。API试验及共享后续累计 **${cost["trial_accounted_usd"]}**；含历史基线总账${cost["full_ledger_usd"]}；已知未结责任 **0**。models、balance各请求1次，不计评分次数。\n\n'
report+='''停止由JSON故障触发，不是$1预算耗尽。每次$0.786432预留已在完整usage结算后释放未用部分；剩余阶段金额不构成追加调用授权。共享$20仍约剩$18.15557；它不等于完整研究已能在预算内完成。

原完整研究粗估场景加本次实耗后，单评约$26.84/$39.18，旧等价审查场景约$51.84/$76.53。只是旧估算加已发生费用，未精确去重，不是新报价；本次2次且包含失败，不足以估计完整研究的审查率、恢复率或费用分布。没有选128/384，也未删除四头、BC、OneShot、NoText及独立评价。

## 按既定分支得出的下一步

本轮属于技术出口：未达到“两个06B均识别真实漏核、两个V3_OFF均识别已有处理、控制不出现明确回归”的完整判读条件。也没有足够有效数据满足语义负结果分支。不能把第2项的语法故障称为关系理解失败，不能把第1项成功外推为自动奖励合格。

优先解决完整JSON的交付可靠性，不再追加熟题语义提示修补。本次已经有完整来源、量表、schema和初评分关联字段；剩余缺口是模型是否可靠交付并执行它们。后续工程处理应保留source_evidence和评分规则，不静默删括号，也不将失败文本升格为正式结果。若拟修复接口或改变失败处置，须单列具体接续版本及范围；只讨论尚未开始的6槽，不重派这2次。没有可靠新交付方案时，剩余槽继续保留，不把每次语法失败循环包装成新的语义研究。此处没有启用任何修复或新调用。

只有完整诊断证据支持后，才讨论与自动核查/有界反馈的接线；本批不自动进入C、资格验收、封存、PPO或新人评。完整四头研究目标不变。本阶段到此停止，等待集中决定。

## 附件

- ITEM_RESULTS.json / csv：8项身份、历史分数、状态、用量及未派发原因。
- finals/：两次完整final原文；第二份保持非法JSON原字节。
- materials/：6条完整英文回复、当前对话、合法历史及原初评分。
- raw/：本批原始请求、response、SSE、started/result/seal、STOP。
- FORMAT_FAILURE_DIAGNOSIS.json：只定位额外字符，不修复或重解析成正式结果。
- LOCAL_REVIEW.json：分析者意见与模型结果分开；不是新增独立人评。
- VALIDATION_AND_COST.json / VERIFICATION.json：账本与输入/历史完整性验证。
'''
save('REPORT_ZH.md',report)
for f in (m.PREP/'materials').glob('*.txt'):
    dest=out/'materials'/f.name;dest.parent.mkdir(exist_ok=True,mode=0o700);shutil.copyfile(f,dest);dest.chmod(0o600)
for f in root.iterdir():
    if f.is_file() and not f.name.startswith('.'):
        dest=out/'raw'/f.name;dest.parent.mkdir(exist_ok=True,mode=0o700);shutil.copyfile(f,dest);dest.chmod(0o600)
for name in ['protocol.json','SCHEDULE.json','MATERIALS.json','EXPOSURE.json','ANALYSIS_RULES.json','OUTBOUND_SCOPE.json','FROZEN_RUBRIC_EN.txt','LOCAL_REFERENCE_PROVENANCE.json','RUBRIC_DELIVERY_GAP.json','OFFLINE_TESTS.txt']:
    dest=out/'frozen_preparation'/name;dest.parent.mkdir(exist_ok=True,mode=0o700);shutil.copyfile(m.PREP/name,dest);dest.chmod(0o600)
for name in ['APPROVED.json','activation.json','RESEARCHER_APPROVAL.txt']:
    dest=out/'authorization'/name;dest.parent.mkdir(exist_ok=True,mode=0o700);shutil.copyfile(auth/name,dest);dest.chmod(0o600)
save('PROVENANCE.json',dict(protocol_identity=pr['identity'],files={str(f):m.r.sha(f) for f in root.iterdir() if f.is_file()},
    historic_scores={x['item_key']:dict(path=x['old_result_path'],sha256=m.r.sha(x['old_result_path'])) for x in m.r.read(m.PREP/'MATERIALS.json')},
    source_inputs=str(m.PREP/'inputs_private.json'),source_inputs_sha256=m.r.sha(m.PREP/'inputs_private.json')))

parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PM-RL1 评分审查结果</title><style>body{max-width:1100px;margin:28px auto;padding:0 20px;font:17px/1.7 system-ui;color:#17212b}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f3f5f7;padding:18px}details{border:1px solid #ccd4dd;margin:16px 0;padding:12px}a{color:#1564a2}summary{cursor:pointer;font-weight:bold}</style><h1>PM-RL1 评分审查结果</h1>',
       '<p><b>2次尝试后技术停止：1有效、1失败、6未派发。累计304/374。方法判读未完成。</b></p>',
       '<p><a href="REPORT_ZH.md">中文报告</a> · <a href="ITEM_RESULTS.csv">8项表格</a> · <a href="VALIDATION_AND_COST.json">费用与用量</a> · <a href="FORMAT_FAILURE_DIAGNOSIS.json">失败定位</a></p>',
       '<pre>'+html.escape(report)+'</pre>']
for x in rows:
    parts.append(f'<details><summary>{x["position"]}. {x["item"]} / r{x["repetition"]} — {html.escape(x["status"])}</summary><pre>{html.escape(json.dumps(x,ensure_ascii=False,indent=2))}</pre>')
    if x['position'] in raws:
        raw=raws[x['position']];parts.append('<h3>完整final原文（未修复）</h3><pre>'+html.escape(raw['choices'][0]['message']['content'])+'</pre>')
    parts.append('</details>')
parts.append('<h2>完整回复、来源与历史初评分</h2>')
for f in sorted((out/'materials').glob('*.txt')):
    parts.append('<details><summary>'+html.escape(f.name)+'</summary><p><a href="materials/'+f.name+'">独立文本</a></p><pre>'+html.escape(f.read_text())+'</pre></details>')
parts.append('</html>');save('阅读结果.html',''.join(parts))
print(json.dumps({'result_path':str(out),'cumulative':304,'valid':1,'failed':1,'unstarted':6,'accounted':cost['accounted_upper_usd']},ensure_ascii=False))
