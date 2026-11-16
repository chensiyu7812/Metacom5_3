"""Offline closeout of the completed fixed batch; no service or credential access."""
from pathlib import Path
import json, hashlib, csv, io, shutil, zipfile, statistics, datetime, subprocess
from decimal import Decimal
from fractions import Fraction
HERE=Path(__file__).resolve().parent
B=HERE.parent
R=B.parents[3]
N=B/'reward_noise_runs/pmrl1-resource-decision-noise-v1-20261020/live'
S=HERE/'derived_1792474528960608601'
P=B/'reward_noise_proposal_20261020_v1'
OUT=HERE/'closeout_v1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def save(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
def write(p,t):p.write_text(t);p.chmod(0o600)
def table(headers,rows):return '| '+' | '.join(headers)+' |\n|'+'|'.join(['---']*len(headers))+'|\n'+''.join('| '+' | '.join(map(str,row))+' |\n' for row in rows)
def label(e):return {'0000':'OFF','1000':'RS1','0100':'MP1','0010':'MS1','0001':'ME1','1111':'四类各1'}[e[-4:]]
protocol=read(HERE/'protocol.json');proposal=read(P/'proposal.json')
records=read(S/'per_request_results.json');stats=read(S/'statistics.json');summary=read(S/'summary.json');finance=read(N/'financial_closeout.json')
assert len(records)==48 and summary['technical_complete']==48 and summary['cumulative']==201
assert len(list(N.glob('*.started.json')))==48 and len(list(N.glob('*.response.json')))==48
assert len({r['request_identity'] for r in records})==48
assert not (N/'STOP.json').exists()
checks={str(p):sha(Path(p))==h for p,h in protocol['immutable_files'].items()}
assert all(checks.values())
old_stops=read(HERE/'provenance/old_stops.json');assert all(sha(Path(p))==h for p,h in old_stops.items())
ledger=R/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl'
before=(HERE/'provenance/ledger.before.jsonl').read_bytes();after=ledger.read_bytes();assert after.startswith(before)
events=[json.loads(x) for x in after[len(before):].decode().splitlines()]
assert len(events)==96 and sum(e['event']=='RESERVED' for e in events)==48
payloads={e['row_id']:read(P/e['payload_file']) for e in proposal['endpoints']}
wire_hashes={};token_checks=[]
for r in records:
    q=read(N/(r['slot_id']+'.request.json'));prepared=payloads[r['endpoint']]
    assert q['messages']==prepared['messages'] and q['schema']==prepared['schema']
    assert q['wire_body']['messages']==prepared['messages']
    assert set(q['wire_body'])=={'model','messages','thinking','response_format','max_tokens','stream','stream_options','reasoning_effort','top_p'}
    assert q['wire_body']['max_tokens']==393216 and q['wire_body']['reasoning_effort']=='high'
    user=json.loads(q['messages'][1]['content']);assert set(user)=={'legal_evidence','reply','response_units'}
    assert r['finish']=='natural_stop' and r['technical_valid'] and not r['model_unknown']
    assert read(N/(r['slot_id']+'.response.json'))['choices'][0]['finish_reason']=='stop'
    assert r['financial']['settlement_confirmed'] and r['financial']['unsettled_reservation_usd']=='0'
    assert r['usage']['prompt_tokens']+393216<=1048576
    wire_hashes.setdefault(r['endpoint'],set()).add(hashlib.sha256(json.dumps(q['wire_body'],sort_keys=True).encode()).hexdigest())
    token_checks.append(r['usage']['prompt_tokens'])
assert all(len(v)==1 for v in wire_hashes.values())
management=sorted(p.name for p in (N/'management').glob('*.started.json'));assert management==['models.started.json','user_balance.started.json']
assert sum(Decimal(r['financial']['accounted_upper_usd']) for r in records)==Decimal('0.3838272')
assert finance['unsettled']==[] and finance['original_prefix_preserved']
OUT.mkdir(mode=0o700)
now=datetime.datetime.now(datetime.timezone.utc).isoformat()
verification=dict(timestamp=now,old_records_unchanged=True,old_STOP_hashes_preserved=len(old_stops),immutable_hashes_checked=len(checks),
    proposal_and_protocol_identity=protocol['identity'],started=48,complete_final=48,duplicate_request_identities=0,
    exact_prepared_messages_schema_and_wire_repetitions=True,full_input_preserved=True,prompt_token_range=[min(token_checks),max(token_checks)],
    output_reserved=393216,context=1048576,ledger_prefix_preserved=True,new_ledger_events=96,management_started=management,
    no_automatic_retries=True,semantic_revision_delta=0,model_unknown=0,old_cumulative=153,new_cumulative=201,
    formal_qualification=False,human_reference='8 pending; not imputed',local_GPU_usage='none in this API stage',
    incomplete_snapshot_preserved=str(HERE/'derived_1792474486521626863'),authoritative_completed_snapshot=str(S))
save(OUT/'verification.json',verification)
save(OUT/'statistics.json',stats)
save(OUT/'summary.json',{k:v for k,v in summary.items() if k!='slots'})

# Readout defined before running: rank the three selected terminal plans in each context.
rankings=[]
for context in stats['contexts']:
    es=[e for e in stats['endpoints'] if e['context_id']==context['context_id']]
    cost={e['row_id']:Fraction(1,20)*e['resource_tokens']/2048 for e in proposal['endpoints']}
    entry={'context':context['context_id'],'draws':[],'blocks':[]}
    for draws in ([0],[1],[2],[3],[0,1],[2,3]):
        vals={e['endpoint']:sum(Fraction(str(e['U'][i])) for i in draws)/len(draws)-cost[e['endpoint']] for e in es}
        ordered=sorted(set(vals.values()),reverse=True)
        rank=[[k for k,v in vals.items() if v==x] for x in ordered]
        row={'draws':[i+1 for i in draws],'net_endpoint_values':{k:float(v) for k,v in vals.items()},'ranking_with_ties':rank}
        entry['draws' if len(draws)==1 else 'blocks'].append(row)
    rankings.append(entry)
save(OUT/'rankings.json',rankings)

# Source review: researcher statements and analyst interpretations are kept distinct.
notes={
'context_01_0000':('04B双读法','研究者明确接受“预设已影响”与“引导讨论”两种读法；不是唯一语义金标准。','C:T006仅说明同事少干活但讨经理喜欢；C:T008说明用户难忍不公。H001–H004没有团队士气/生产力结果。','同一R003在第1/3轮被解释为试探性建议，第2/4轮被解释为无依据团队影响预设。后两轮q3/m.25，前两轮q4/m0。不能把两次扣分都称已证实错误。','未决解释如何转成q/m；相同歧义在近似OFF/MP回复中是否一致处理。'),
'context_01_1000':('一般询问与推断边界','没有本配对的已完成人工方向标签。','C:T006、C:T008支持偏袒与不公；“favored over you”含从同事受偏袒到相对用户待遇的推断。','四轮q4/m0；询问Have you talked不是断言已经谈过。来源支持主要情境，但相对待遇措辞仍是可讨论推断，不能新增来源已证实硬错。','当前四轮未显示分数波动；没有独立证明优于OFF。'),
'context_01_0100':('近似措辞的歧义处理','旧研究者双读法涉及相同团队影响主张；不自动移植整条q/m。','与OFF相同C:T006/C:T008，核心短语同为how this favoritism affects your team’s morale and productivity。','四轮q4/m0；第2/4轮明确视为建议/未确认事实，另两轮理由未单独证明已检查该嵌入主张，不能由未写出推出内部一定漏检。','与OFF相比，均分制造约.25效用差，但两条共享主要歧义；收益正确性尚待配对参照。'),
'context_02_0000':('06B行动预设与身份需求','研究者补充：默认谈话已经发生；严重度未因此自动唯一。身份规则：用户误归属过去支持者经历时才须澄清。','C:T008是过去支持者自述；C:T009问Really? How did you deal with that…；H002:T010已讨论的是旅行，不是当前关于交友规则与感受的对话，H002:T021–T022为建议。','R004第2轮识别已谈过且观察效果的预设并判unsupported；第1/3轮否认完成事实，第4轮称“tentative and consistent with reported arguments”。三轮未按现有开发参照核查该具体行动，但不能把三轮视为三个独立案例。q为2/2/2/4；第4轮将未澄清身份视为合适转向。','具体谈话对象/话题/阶段匹配；回应明确身份问题的重要性；m等级仍须分开。'),
'context_02_1000':('身份需求与q锚点','用户触发身份澄清规则适用于同一C:T009，不是要求每次都自报AI身份。没有本配对方向标签。','C:T005/007/009支持愤怒、母亲与交友冲突；回复询问是否与朋友谈过，没断言已发生。','四轮m0；q3/3/2/3。同一未回答亲身经历问题，第3轮视为重要遗漏，其余轮视为较轻或非实质缺陷。','事实错误与漏满足当前需求分开；不能从m0推导q4或整条合格。'),
'context_02_0001':('06A正常探索与身份遗漏','研究者指出身份澄清问题；不能预设整条回复无问题，也不能把一般探索判为事实捏造。','C:T007交友限制、C:T009愤怒；Is it the feeling of being controlled, or the fear of disappointing her?是两种可讨论假设。','四轮m0，q2/3/3/4。第1轮把未回应亲身经历/身份需求视为重要遗漏，第4轮虽提到用户问过去支持者经历，仍以未冒认即可适当转向而给4。','需要的是明确“当前任务缺口如何影响q”的参照，不是再加一个泛泛人物提醒。'),
'context_03_0000':('老同学归属与有依据追问','没有新独立评审；旧15B错误不等于本条回复错误。','C:T005老同学；C:T009朋友的鼓励；C:T013聊天带来论文视角变化；C:T003/H009:T004导师反馈。','四轮q4/m0，朋友的帮助没有归给AI；对导师担忧的引用有具体来源。','只说明本条未见同类错误，不能宣布第15类全部通过。'),
'context_03_1000':('正常有依据探索','无本配对人工方向标签。','C:T013明确谈论文视角变化；追问论文感受与当前消息相接。','四轮q4/m0，未把支持者或朋友经历变为AI人生。','资源是否额外有用尚无人工方向参照。'),
'context_03_0010':('行动已发生的有依据对照','分析者按完整来源核查，不计独立人评。','C:T013: Yeah, we chatted for a while. It helped me see things from a different perspective, especially regarding the thesis.','四轮q4/m0；Have you been able to make any progress since that conversation?依赖已经聊天这一事实，而进展本身仍在问。各轮均引用C:T013；与06B所缺的具体行动证据不同。','不能见到过去时问句就一概判unsupported。'),
'context_04_0000':('当前信息不足时开放邀请','无本配对人工方向标签。','C:T002只有things have been a bit tough lately；H001睡眠、H002饮酒与婚姻，不是当下原因断言。','四轮q4/m0；开放邀请没有强行认定历史烦恼是当前原因。','未出现本批语义问题，不等于独立验收。'),
'context_04_1000':('35B资源情境当个人事实','既有来源核查确认求职缺乏支持；unsupported与m=1是否恰当分开。','回复especially when it comes to job hunting；C:T002仅一般困难，全部H001–H002无求职。','四轮都拆开一般共情与具体求职情境，判后者unsupported/m1；q1/2/2/2。事实缺口识别稳定，q波动没有改变OFF更好的净收益方向。m1仍是裁判输出，不能用四次一致替代严重度金标准。','不平均掉四次m1；单独保留严重度依据与未决边界。'),
'context_04_1111':('普通支持与资源成本','无本配对人工方向标签。','C:T002支持困难反映；询问How can I support you best right now?未认定具体原因。','四轮q4/m0，与OFF同U，净收益仅扣资源成本。','模型打平不等于人类已确认完全等效；若人类确认相当，偏好低成本OFF是合理结果。')}
audit=[];parts=['# 逐项来源复核与原始q理由\n\n这是Codex对开发输出的证据核查，不是新增人评或资格判定。未改任何原q/m/U。全部48条final另见ALL_COMPLETE_FINALS.md；完整来源在sources/。\n']
for r in records:
    typ,ref,source,observed,unresolved=notes[r['endpoint']]
    a=dict(position=r['position'],draw=r['draw'],endpoint=r['endpoint'],request_identity=r['request_identity'],final_sha256=r['final_sha256'],
        technical_valid=r['technical_valid'],model_unknown=r['model_unknown'],q=r['q'],m=r['m'],U=r['U'],
        analyst_review_type=typ,prior_researcher_reference=ref,source_support=source,observed_pattern=observed,
        unresolved=unresolved,human_pair_reference='PENDING_NOT_IMPUTED',reward_eligible=False,
        judgments=r['parsed']['assessments'],q_rationale=r['parsed']['q_rationale'],
        raw_paths=r['paths'],elapsed_seconds=r['elapsed_seconds'],usage=r['usage'],financial=r['financial'])
    audit.append(a)
    parts.append(f"## {r['position']:02d} {r['endpoint']} / 第{r['draw']}轮\n\nrequest_id: `{r['request_identity']}`\n\nq/m/U = {r['q']}/{r['m']}/{r['U']}；技术有效；模型unknown=False；资格=False。\n\n研究者旧参照：{ref}\n\n来源关系：{source}\n\n四轮对照观察：{observed}\n\n未决：{unresolved}\n\n本次完整q理由：\n\n> {r['parsed']['q_rationale']['current_need']}\n\n> {r['parsed']['q_rationale']['reason']}\n\n本次完整证据判断：\n\n```json\n{json.dumps(r['parsed']['assessments'],ensure_ascii=False,indent=2)}\n```\n")
save(OUT/'source_audit_48.json',audit);write(OUT/'SOURCE_REVIEW_48_ZH.md','\n'.join(parts))
save(OUT/'per_request_results.json',records)
for f in ['ALL_COMPLETE_FINALS.md','SLOTS_48.csv']:shutil.copy2(S/f,OUT/f)
sources=OUT/'sources';sources.mkdir(mode=0o700)
for p in Path('/home/tokkio/PM_RL1_NOISE_HUMAN_8PAIRS_20261020').glob('context_*_complete.txt'):shutil.copy2(p,sources/p.name)
save(OUT/'endpoint_bindings.json',proposal['endpoints'])

# Scenarios, not a confidence interval or authorization; no implicit k=2 adoption.
unit_hi=Decimal(summary['accounted_usd'])/48;unit_observed=Decimal(summary['usage_price_estimate_usd'])/48
cost_scenarios=[]
old=read(B/'research_completion_review_20261019_v1/budget_worksheet.json')
for x in old['scenarios']:
    calls=x['scenario_J_with_old_acceptance_and_reserves']
    cost_scenarios.append(dict(episodes_per_seed=x['episodes_per_seed'],historical_not_deduplicated_calls=calls,
        observed_cache_offpeak_scenario_usd=str(unit_observed*calls),peak_no_cache_scenario_usd=str(unit_hi*calls),
        single_serial_hours=calls*summary['request_seconds']/48/3600,
        hypothetical_all_double_peak_usd=str(unit_hi*calls*2),selected=False,authorized=False))
save(OUT/'cost_scenarios.json',dict(unit_peak_upper_usd=str(unit_hi),unit_observed_cache_offpeak_usd=str(unit_observed),
    shared_followup_spent_usd=finance['trial_accounted_usd'],shared_followup_remaining_usd=str(Decimal(20)-Decimal(finance['trial_accounted_usd'])),
    trial_remaining_usd=str(Decimal(2)-Decimal(finance['trial_accounted_usd'])),scenarios=cost_scenarios,
    caveats=['Small exposed development subset; no uncertainty interval or guarantee.','Costs exclude future measurement repair, generators and humans.','Old conditional acceptance59 scope is not automatically valid for an aggregation pipeline.','Exact unique endpoint count and legal cache reuse remain to be computed after final identities; no PPO trajectory reuse.','No128/384 selection; no authority to spend future reserves.']))
endtable=table(['情境/条件','q 四轮','m 四轮','U 四轮'],[(e['context_id'][-2:]+'/'+label(e['endpoint']),'/'.join(map(str,e['q'])),'/'.join(map(str,e['m'])),'/'.join(map(str,e['U']))) for e in stats['endpoints']])
ctable=table(['情境/ON','单次 D1 → D3','两均值 D12 → D34','四轮D范围'],[(c['id'][8:10]+'/'+label(c['on']), ' → '.join(f'{v:.6f}' for v in c['blocks']['single']['values']),' → '.join(f'{v:.6f}' for v in c['blocks']['mean_two']['values']),f"[{min(c['D']):.6f}, {max(c['D']):.6f}]") for c in stats['contrasts']])
ranktable=table(['情境','第1轮','第2轮','第3轮','第4轮','均值1/2','均值3/4'],[(x['context'][-2:],*[' > '.join(' = '.join(label(e) for e in group) for group in z['ranking_with_ties']) for z in x['draws']+x['blocks']]) for x in rankings])
costtable=table(['旧规划情景','原未去重评分槽','本批缓存/低峰用量外推','峰值无缓存外推','单评串行小时'],[(x['episodes_per_seed'],x['historical_not_deduplicated_calls'],f"${Decimal(x['observed_cache_offpeak_scenario_usd']):.2f}",f"${Decimal(x['peak_no_cache_scenario_usd']):.2f}",f"{x['single_serial_hours']:.1f}") for x in cost_scenarios])
report=f'''# PM-RL1：奖励噪声诊断结果与下一步

完成时间（UTC）：{now}。新增48/48次已完成，累计153→201；容量289，剩余88不等于执行授权。原9份STOP、原分数、两次语义修订及旧阶段边界全部保留。自然任务RL更新仍为0。

**结论：瓶颈已收窄为“事实/行动关系判断不稳定＋当前任务要求到q档位的映射不稳定＋共享歧义在不同回复中处理不一致”。两次平均局部减少方向翻转，但没有达到本次事先规定的推进线，不建议默认把全部奖励改成双评，也不因此放弃四头GET/STOP主线。**

## 一页决策摘要

本批是4个已暴露开发情境、2个来源owner、12条既有回复的48次重复评分，不是48个独立案例。技术交付48/48；模型unknown 0；技术失败0；未派发0；无自动重试。人工8对尚未返回，方向比较分母为0，不能称准确率或独立验收。无模型unknown不代表没有研究者歧义。

按预定第1/3轮单评与第1/2、3/4轮两个互不重叠均值比较：8个共享4个OFF的对照，正负方向翻转由2组降至1组；D绝对差之和仍为0.75。只有情境04的波动缩小，情境02由0.5增至0.625，另两情境在这个指定比较中原本为0。未满足“至少两个有波动情境改善”，人工方向不恶化亦未检验。不能事后换轮次或降低门槛宣布通过。

有价值的稳定能力也保留：情境03的老同学归属和有依据的聊天后追问四轮均无误罚；35B求职情境无来源四轮均被识别，q虽变，OFF较优方向没变。当前并非所有反馈都随机失效。

最应处理的是情境02：同一06B回复，三轮没有按研究者已有判断识别具体谈话发生预设，一轮识别；其q从2到4，变化不只是m。06A同一回复q为2/3/3/4，模型始终看得到用户询问先前支持者经历，但对“未澄清/未回答”是否属于重要遗漏判断不同。补评分次数不能自动补出这个任务标准。

情境01说明“更稳定”也可能只是固定了不可靠差异：OFF与MP共享团队士气/生产力的歧义句，OFF交替给q4/m0与q3/m.25，MP始终q4/m0。两个均值因此稳定显示约.243的MP收益；现有研究者接受双读法，不能据此称资源有真实收益。需要核查同一边界能否一致应用，而不是强迫所有人接受某个分数。

**下一步优先补参照与监督，暂不增加平均次数或换模型。** 完成已交付8对方向判断（含阅读总上限120分钟，可保留未知/未完成）；我们用它检验这些分数差是否误导资源选择，不再重标40对。随后只针对已确认的共性问题建立可执行参照：具体行动的对象/话题/阶段、触发身份澄清后的最低回应要求、歧义与严重度的允许边界。旧原子判断与新的配对偏好分开，不由Codex代填。

如果配对参照显示这些波动多数不影响合理资源选择，可保留单评作为待验候选，下一步是独立验证其限定用途；不能由本批直接授予资格。如果反复偏好确有重要问题的回复，下一版应做有监督的校准对照：优先同一联合模型、固定的已核验参照示例与明确q锚点，保留现配置为基线；不用再加泛泛提醒，也不重复已失败的两步流程。它是待申请的新测量版本，不在本轮实施。若参照明确后仍错人物/行动关系，再考虑针对性核查器或有界适配，所需训练/验证材料必须按来源组分开。仅凭这4个上下文不足以训练并证明泛化。

## 实际测量与完整数字

公式未改：U=q/4−m；D=U_ON−U_OFF−0.05×资源token/2048。D>0指该资源终点在本次测量中优于OFF，D<0偏向OFF；不是人类精确效用金标准。重复m=1全部保留，均值不解除风险。人工方向不包含资源成本，应先与原始U差比较；人工相当与扣成本后选择OFF不冲突。

{endtable}

7/12条回复四轮U相同，5/12变化；这是描述性覆盖，不是准确率。2条回复的m变化（04B、06B），另有q档位变化。06B的三次未识别只是一个既有案例的三次观测。35B是一个已知回复错误的四次检测，不算四个新错误。

{ctable}

预定比较之外，完整四轮中4/8对照曾同时出现正负D，集中于2/4情境。这里只补充透明展示，不替换预定推进指标。共用OFF导致同一变化影响两个对照；不能把它们当独立样本。重复次数不足以证明独立同分布或估计总体误差率。四轮次序与时间绑定，不能从变化断言具体随机机制。

三终点按U减成本排序如下；相同条件的排序变化是测量变化，不是回复变了。

{ranktable}

## 来源与量表瓶颈

1. **行动阶段：需要更细的证据匹配，现有一般提醒不够。** 06B原句为“Did you find that talking to her about how her rules make you feel helped to calm the anger, or does it usually escalate the argument?” 研究者已判其默认谈过。旅行争论的“已经讨论过”不能直接支持当前交友规则与感受这一谈话。第4轮称“any presupposition of prior discussion is tentative and consistent with the reported arguments”，仍混淆相关冲突与具体行动。与之相对，情境03的“since that conversation”有C:T013明确“we chatted for a while”支持，不能一律罚过去时问句。
2. **当前需要与q：缺的是执行稳定的任务参照。** C:T008来自旧支持者的母亲经历；C:T009问“Really? How did you deal with that because for me it makes me angry.” 用户已明确仅在这种归属混淆时需要澄清。模型各轮都看到了它，却有时把未回应作为重要缺口，有时认为只要不主动冒认即可q4。这不同于稳定发现事实错误后相邻一档的普通分歧，也不意味着m必须1。需要为“身份交接后的任务完成”固定可接受回应范围及q依据；若其内容改变旧规则，登记未来新版本，不追改旧分。
3. **真实歧义：需要一致处理，不能平均制造资源优势。** 04B“how this favoritism affects your team's morale and productivity”有研究者接受的双读法。C:T006/C:T008支持个人受困与偏袒，未报告团队影响。应保留两种读法及对结论的敏感性；OFF和MP不应仅因分开采样就被当作一个有明显收益、一个明显较差。是否需要允许区间/未决而非强制唯一数值，是未来测量协议决定，本轮没实施。
4. **严重度：unsupported不自动等于severe。** 35B“especially when it comes to job hunting”确无当前/历史支持；四轮m1并不代替严重度裁决。q1/2的差异未改变此例资源方向，说明应该优先解决会改变决策的错误，同时保留风险依据，不能把每次相邻分差都当停机理由。
5. **正向使用证据仍不足。** 本批包含正常探询、身份问题、已知误用，没有预先经人工确认的“资源补足当前请求”正收益对。不能用模型自己的正D自证资源有用，也不能据缺少正例否定四头任务。后续从合法train/dev按用户请求是否依赖历史选材料，先锁任务最低要求再生成/评分；来源组、事实家族和暴露用途分开。受控正反例只能证明机制，不能冒充自然任务独立验证；封存24对与PM测试仍未打开。

逐条原始q理由、引文关系、四轮变化、研究者旧判断与Codex分析分列在SOURCE_REVIEW_48_ZH.md及source_audit_48.json。完整final与完整英文来源附后。未给出新独立人评、总体召回率或配置冠军。

## 成本、容量与经济推进

本批实际usage：输入380,960 token；总输出224,616 token，其中thinking子集200,111，未重复相加；可见final token差额24,505。请求耗时合计{summary['request_seconds']:.2f}秒，评分窗口{summary['scoring_window_seconds']:.2f}秒，约19.8分钟；中位{statistics.median(r['elapsed_seconds'] for r in records):.2f}秒，范围3.92–61.61秒。未加载本地GPU模型。

按实际usage、峰值且全部输入无缓存的保守记账为**$0.3838272**；结合已报缓存和观测低峰时段估算**$0.137516544**，不是供应商账单确认。责任0。只做已批准/models和/user/balance各一次，无事后再查余额。原API试验累计**$0.8456142/$2**；共享后续预算同为**$0.8456142/$20**，从原不可变边界$1.50724291算起；共享账本全历史总额$2.35285711，不能误把全历史都算成本阶段费用。

用本批平均用量更新旧未去重全研究场景如下。低峰/缓存情景不是下界保证；长输入、不同难度和重试/未结责任会变化。未选128/384，没有授权这些调用。

{costtable}

若机械地所有终点双评，上述峰值情景约$49.75/$74.32；本次结果不支持这样花钱。经济方法是先锁定测量身份，离线数清各基线与策略共享的唯一终点及可合法缓存复用量，再计费；缓存只能节省重复调用，不能修正错误参照或替代PPO真实采样轨迹。本次额外48次诊断不能直接充当资格验收。

201后容量剩88；若条件性保留旧59次验收和4次恢复，余25。旧59方案并不自动适配新聚合/新测量；下一批申请须同时核对计数和责任预算，不能只看预计几美分。研究成功不要求PPO一定胜出；仍须保留OFF、强固定、随机剂量匹配、OneShot、BC和反馈匹配BC、NoText等原基线，反馈资格成立后才接自然训练。

## 本轮出口与文件身份

已完成本轮，停止新调用。不存在需补跑的本批槽位；旧未派发槽仍旧未派发。未换执行器、未改量表/公式/门槛、未增加语义修订、未恢复旧STOP、未训练/开封/提交推送。

代码HEAD：`0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28`；分支`work/paper1-rq1-integration-20260816`。协议`{protocol['identity']}`。服务同批为DeepSeek-V4.1-Flash-1017公开映射、Flash/high；48次回执指纹相同，但别名/指纹不是不可变权重或独立抽样证明。[官方服务与价格](https://api-docs.deepseek.com/quick_start/pricing/)。原统一外层接口与行动提醒提示未变，复用现有runner，17项离线测试通过。

48份请求/开始/response/result及SSE均保存在raw/，包含私人来源与原始thinking，仅本地保留；判读只用完整final，未从thinking补答案。verification.json记录哈希/计数/来源绑定/原STOP/原账本前缀核验。中途47份完成的派生快照保留作过程记录，不用于最终分母。

人评入口：`/home/tokkio/PM_RL1_NOISE_HUMAN_8PAIRS_20261020/researcher.html`。现在需要的是这8对的有限方向参照，允许相当/未知，不要求迎合分数。若已阅读本报告新结果，请在页面如实勾选“看过新分数”；不再称完全盲评。超过120分钟就保留未完成，先用能明确判断的数量及覆盖报告。没有新答案之前，不替研究者决定正确收益方向，不开下一轮付费试验。
'''
write(OUT/'RESULTS_ZH.md',report)
save(OUT/'closeout.json',dict(status='COMPLETED_FIXED_SCOPE_NO_PROMOTION',timestamp=now,started=48,cumulative=201,stage_accounted_usd=summary['accounted_usd'],unsettled_usd='0',criteria={'direction_changes_reduced':True,'two_contexts_discrepancy_reduced':False,'coverage_not_lower':True,'human_direction_not_worse':'PENDING'},next='Complete bounded existing 8-pair reference, then target task/claim supervision; no automatic new calls',all_old_stops_preserved=True))

# Local delivery. Never overwrite an earlier package, and never include credentials.
home=Path('/home/tokkio/PM_RL1_REWARD_NOISE_RESULTS_20261020')
shutil.copytree(OUT,home)
raw=home/'raw';shutil.copytree(N,raw,ignore=shutil.ignore_patterns('.study.lock','management'))
prov=home/'protocol';prov.mkdir(mode=0o700)
for f in ['protocol.json','APPROVED.json','offline_test_receipt.json','HUMAN_COMPARISON_NOTE_ZH.md','analysis.py','noise.py','test_noise.py','collect_results.py','closeout.py']:shutil.copy2(HERE/f,prov/f)
shutil.copy2(HERE/'provenance/old_stops.json',prov/'old_stops_hashes.json')
shutil.copytree(P/'payloads',prov/'frozen_payloads')
files=[p for p in home.rglob('*') if p.is_file()]
# Verify absence of auth headers or serialized key-variable names; no env read.
for p in files:
    if p.suffix in {'.json','.jsonl','.sse','.txt','.md'}:
        text=p.read_text(errors='replace').lower()
        assert 'authorization: bearer' not in text and '"authorization"' not in text and '"deepseek_api_key"' not in text
for p in home.rglob('*'):p.chmod(0o700 if p.is_dir() else 0o600)
home.chmod(0o700)
save(home/'MANIFEST.json',{str(p.relative_to(home)):sha(p) for p in files})
zip_path=home.with_suffix('.zip')
with zipfile.ZipFile(zip_path,'x',zipfile.ZIP_DEFLATED) as z:
    for p in sorted(home.rglob('*')):
        if p.is_file():z.write(p,str(p.relative_to(home.parent)))
zip_path.chmod(0o600)
with zipfile.ZipFile(zip_path) as z:assert z.testzip() is None
save(HERE/'DELIVERY_RECEIPT.json',dict(home=str(home),zip=str(zip_path),zip_sha256=sha(zip_path),file_count=len(files)+1,private_local_only=True,created_at=now))
print(json.dumps(dict(output=str(OUT),home=str(home),zip=str(zip_path),verified=True,cumulative=201)))
