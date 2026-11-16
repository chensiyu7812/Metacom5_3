import json,csv,hashlib,sys
from pathlib import Path
from decimal import Decimal
from datetime import datetime
from zoneinfo import ZoneInfo
OUT=Path(__file__).resolve().parent;B=OUT.parent;R=B.parents[3]
sys.path[:0]=[str(B/'outer_format_v1_20261015'),str(B)]
import selection as s
R=s.REPO;data=json.loads((OUT/'results_private.json').read_text());summary=data['summary'];p=json.loads((OUT/'protocol.json').read_text());rows=data['rows'];now=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat()
ledger=R/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl';fin=json.loads((B/'live_runs/output_interface_v1_D_development/stage/financial_closeout.json').read_text())
with (OUT/'per_request_usage_private.csv').open('x') as f:
 cols=['slot','item','draw','request_id','record_class','status','input_tokens','output_tokens','thinking_tokens','final_tokens','elapsed_seconds','usage_price_estimate_usd','accounted_upper_usd','local_GPU_seconds','unsettled_liability_usd'];w=csv.DictWriter(f,fieldnames=cols);w.writeheader()
 for r in rows:
  if not r['started']:continue
  u=r['usage'];v={k:r[k] for k in ['slot','item','draw','request_id','record_class','status','elapsed_seconds','usage_price_estimate_usd','accounted_upper_usd']};think=u['completion_tokens_details']['reasoning_tokens'];v.update(input_tokens=u['prompt_tokens'],output_tokens=u['completion_tokens'],thinking_tokens=think,final_tokens=u['completion_tokens']-think,local_GPU_seconds=0,unsettled_liability_usd=0);w.writerow(v)
notes={'dev02B':'旧首轮；帮助动机与脆弱感预设单独核查','dev15B':'旧首轮；朋友归属正确；严重度仍非独立金标准','dev37A':'旧首轮；收尾回应','dev37B':'旧首轮；与37A同U，relation分类变化','dev01A':'压力来源有支持；问句分类粒度粗','dev01B':'问句中的活动/工作/关系前提逐项核查','dev02A':'泛称与if/perhaps建议；不假定已分享','dev03A':'困难问句预设明确核查','dev03B':'同困难语境；relation与03A不同而分数同','dev04A':'Since前提与是否沟通拆查；q3边界','dev04B':'复核未决①：预设与local后果；不排除','dev06A':'区分历史支持者；q2重要需要遗漏边界','dev06B':'复核未决②：既往沟通预设；不排除','dev07A':'短探索q4；与04A锚点边界','dev07B':'缩写等义对一致','dev10A':'当前辞职与既往骚扰来源支持','dev10B':'内部JSON重复键；技术STOP，正式null'}
table=['|槽|题目/独立draw|记录类别|正式q/m/U|状态/要点|','|---:|---|---|---|---|']
for r in rows:
 score='/'.join('null' if r[k]is None else str(r[k]) for k in ['q','m','U']);cls={'prior_D_engineering':'旧首轮实时','new_D_development_diagnostic':'本轮实时','not_dispatched':'未派发'}[r['record_class']]
 table.append(f"|{r['slot']}|{r['item']} / {r['draw']}|{cls}|{score}|{notes.get(r['item'],'') if r['started'] else 'dev10B技术STOP；不计尝试、不算答错'}|")
report=f'''# D开发诊断接续结果

更新：{now}。**已执行并停止；不建议申请当前D配置的冻结验收。** 本轮13次新评分尝试（12次有效数值、1次技术失败），累计107→120，未触及143硬上限。D共17/40槽开始、16槽得到有效数值；第17槽dev10B发生严格JSON解析失败，按原技术停止规则结束。余23槽未派发：15条主评分、4次预定重复、4个机制变体。当前固定四候选筛选到此结束，不恢复A/B/C/D，不继续换模型追分。

失败原因是**完整final内部重复JSON键**：q_rationale中重复response_unit_ids、source_turn_ids、reason，assessment中也重复response_unit_id。原接口报`duplicate JSON key: response_unit_ids`，验证阶段outer_format_or_JSON。输出完整、usage齐全，不是超时、thinking未完成、外层围栏或来源ID失效；正式q/m/U全部null。文本里出现的q=0和severity=1只保留在原文中，绝不当作有效分数，不去重键、不恢复解析、不补跑。原STOP：[记录](../live_runs/output_interface_v1_D_development/deepseek_flash_high/STOP.json)。

## D的40槽

17/32主评分已尝试（53.1%），其中16/32有有效数值（50%）；全部40槽尝试覆盖42.5%。预定重复0/4、机制变体0/4；不宣称重复稳定性已通过。旧首轮4/4技术有效、本轮12/13分别列示；合并为16/17仅是开发技术覆盖描述，不是正式验收。A/B旧严格失败与离线派生没有混入D结果，也不增加独立样本。

'''+ '\n'.join(table)+f'''

逐项完整final、待评回复、来源原句与复核理由见[原文附件](ORIGINALS_AND_SOURCE_REVIEW_ZH.md)；每条原始输出及请求路径、回复哈希、完整来源身份在[结果JSON](results_private.json)，简表在[40槽CSV](all_40_slots_private.csv)。23个未派发项仍保留独立原槽身份，包括4个预定重复；不合并或重编号。

## 证据支持的语义观察

- **主体、事实与时间：** 15B既有结果仍为1/1/−0.75，正确认出帮助者是旧大学朋友而非新AI；其严重度理由指向核心帮助来源被改写，不能由人物正确自动证明m=1唯一正确。15A、16A/B及主体变体未运行，因此不能说已覆盖新AI冒领历史支持者的全部风险。10A正确保留“老板已辞职”及继任忧虑。10B可读原文确实发现否认辞职与C:T000冲突，但技术失败阻止其成为正式评分。
- **引用支持与混合断言：** 02B、01B、03A、04A的个人前提得到具体核查。04B这次把个人价值与团队后果拆开，承认后者未获来源支持，改善了旧A/B的漏核查；仍不能宣布其local判定已正确。06B在R003拆分事实与一般评价，却仍将R004整体视作探索问句，未充分核查既往沟通预设。合法来源ID并不证明整句获支持。
- **严重度：** 本轮未发现已由来源证明的D实质错误，**不等于证明其没有错误**。有2个正式记录的复核未决案例（04B、06B），模型主动unknown为0；15B保留既有严重度标定边界，未自动升级或抹除。04B的`localized unsupported assumption, not a core contradiction`仍没有充分解释为何不改变核心建议。人类原有未知全部保留。
- **q锚点：** 06A给2（未回应明确如何处理），06B给3（探索沟通）；04A给3（仍探索），07A/B给4（协作探索足够）。这些回复并非同一预定等义对；不能凭风格偏好或相邻q分歧新增硬停，但“何时探索已满足请求”的锚点尚须集中标定。q没有独立绝对金标准。
- **等义与稳定性：** 07缩写对及既有37对均4/0/1，无已观察到的数值等义异常。37的supported/non_factual分类变化仍保留；03相似问句也有分类变化。37重复及纯格式变体全部未派发，不能用原近等义对替代重复测试。**35A/B、35重复未运行，没有任何改善证据。**

## 人工比较及分母

按已修正的[回复哈希映射](../AB_diagnostic_continuation_20261015/reference_binding_addendum.json)逐条断言一致；第10题按原Chen回复身份映射，未用Du显示位置。Du为派生记录、Codex为辅助复核，新增独立人评均为0。

- 16对中7对有双侧有效模型数值且人类可比较：5/7一致。6个人类平局中5/6一致；唯一已覆盖的人类明确偏好为06，模型偏好B、人类A（0/1一致）。04模型偏好A、人类平局。**04和06两项争议均保留在7对分母内并标记，不排除后美化。** 其余9对无完整双侧数值：10B技术失败，其余有未派发；其中16的人类偏好本身也未知。全16对人类可比15，实际双侧比较覆盖仅7/16；不能称总体准确率。
- 风险32条中16条有效模型m，3条对应人类未知（06A、10A、15B），实际可比13条，11/13一致。两个不一致是04B（模型local、人类none）与06B（模型none、人类local），均属保留争议，不用人类标签当绝对金标准。其余19条不进入比较：3个人类未知、1条技术失败、15条未派发；全32个人类未知共6条（另3条未派发）。local按原0.25映射，未混用0.5。逐项排除理由及未知字段保存在结果JSON。

## 集中裁决所需的具体问题

1. **嵌入预设及其后果。** 04B：`have you considered talking directly to your manager about how this favoritism affects your team's morale and productivity?` 来源仅说同事少工作却被偏爱，以及用户无法容忍不公；没有团队后果报告。06B：`Did you find that talking to her about how her rules make you feel helped to calm the anger, or does it usually escalate the argument?` 当前确有母女争论，历史有旅行相关长谈，但未明确这次朋友规则感受沟通。问题：这类句子是在提出可选探询议题，还是预设了特定已发生事实；若为后者，它是否改变核心理解/建议？保留原04B离线裁决，不要求接受模型分数。
2. **严重度与q的独立锚点。** 15B的`Talking with me helped...`把旧朋友帮助归给新AI，事实错位清楚；04B的local理由与06/07的探索评分仍需后果和任务满足程度的独立说明。问题：在原量表内，什么具体内容使错误/遗漏改变核心理解或当前需要，而不仅是偏好的措辞与详略？不重新打分、不要求人工迎合D。

## 真实用量、费用与责任

|范围|输入token|总输出token|其中thinking / final|响应耗时|按实际usage与时段/缓存计价|保守账本上界|
|---|---:|---:|---:|---:|---:|---:|
|本轮13次（含失败）|119,200|59,224|52,630 / 6,594|380.807秒|$0.040807680（¥0.27205120）|$0.1068288|
|D累计17次|197,457|75,785|67,163 / 8,622|486.202秒|$0.059227662（¥0.39485108）|$0.1501791|
|整个C/D API试验21次|275,614|77,759|C未提供细分，不补0|502.747秒|$0.068880444（¥0.45920296）|$0.1759950|

thinking已包含于总输出，未重复相加。单次token、响应时延、费用及失败状态见[逐请求用量](per_request_usage_private.csv)。本阶段进程墙钟789.068秒，含人工式来源复核等待；新增请求平均响应29.293秒，最大64.871秒（runner还另记本地解析开销）。本地GPU时间0、显存使用不适用，未加载模型、换卡、下载依赖或操作其他用户进程。

本轮只新增1次GET余额（不计评分），成功返回CNY19.00、USD0.00。沿用上一轮模型元数据并核对[当前官方价格](https://api-docs.deepseek.com/quick_start/pricing/)；13次新响应服务model/fingerprint与原记录一致。Flash别名/指纹不是不可变权重保证。

逐请求预留仍$0.786432；完整usage到齐后才按峰价、全输入未缓存上界结算。**未结责任0，API试验已记账$0.175995，2美元停止线余额$1.824005；未重置旧$0.0691662。** 共享累计上界$1.68323791，相对不可重置边界$1.50724291新增$0.175995，纳入共享20美元预算，余$19.824005。上表低值是官方价表×完整usage估算，未另查账单核销；保守上界继续留账。停止原因是技术故障，不是预算不足。

## 完整研究成本更新（估算，不选128/384）

D共17次的小样本均值：输入11,615 token，总输出4,458（实测范围1,193–9,939）；单次实测时段/缓存均费$0.003484，同一用量峰价未缓存上界均费$0.008834。下面区间是这两种**均值计价情景**，不是置信区间或费用保证；输出尾部、来源长度、缓存和采样时段可能改变。技术失败照计成本，不能只用成功样本。

|仅J评分情景|新增槽数|均值计价区间USD|按当前均值的串行响应小时|
|---|---:|---:|---:|
|D余23槽（仅反事实成本，已STOP）|23|0.080–0.203|0.183|
|唯一胜者验收（本轮不建议申请）|59|0.206–0.521|0.469|
|128 episodes对应既定核心J槽数|2,817|9.81–24.89|22.38|
|384 episodes对应既定核心J槽数|4,353|15.17–38.45|34.58|
|另加原可选RQ-X/语义核查/恢复|576|2.01–5.09|4.58|
|128情景核心+59验收+576可选|3,452|12.03–30.50|27.42|
|384情景核心+59验收+576可选|4,988|17.38–44.06|39.63|

上述未来费用另加已经发生的API试验费用；尚未包括生成器、训练GPU、人工工作，也不宣称整个研究满足96小时边界。用观测单次极值做更宽敏感性包络，核心J为$2.15–38.12／$3.32–58.90；这也不是未来保证。若按原生上限，每请求$0.786432责任远大于经验均值，仍必须逐条预留。即使采用非高峰且不依赖缓存的均值，核心J也约$12.44／$19.23；加验收、可选及其它共享付费，20美元可行性不能由本轮便宜试跑推出。详见[cost_projection.json](cost_projection.json)。不选择128/384，不降低high、不缩短输入/输出。

## 结论、身份与停止点

**不值得直接申请当前D冻结验收。** 主要依据是原技术硬停止已经触发，覆盖不足、预定稳定性项目未测，以及04B/06B未决边界仍阻塞推荐；不是按不等覆盖给四配置排名。A21/40为来源证明的主体错误STOP；B12/40为超时技术STOP；C4/40为等义分差STOP；D17/40为JSON重复键STOP。各原因不同，不能宣称四者同一种语义错误或D全面语义失败。共同的测量风险包括接口可靠性、个人事实/建议边界、严重度后果依据和q锚点；下一步应集中决定测量方案如何修订及哪些历史观察仍可用，而不是追加候选或自动恢复追分。本轮未实施新的测量方案。

仓库/分支/HEAD保持原身份；协议`{p['identity']}`，原计划`{p['original_plan_identity']}`，接口`{p['interface']['identity']}`。只修改既有runner的D接续范围、历史注册、财务试验继承与既有服务指纹绑定；6项必要离线测试通过。完整代码哈希见[实现变更](implementation_change.json)。原342个历史文件和原账本前缀哈希全部保留，新13次跨版本原槽唯一。完整输入与原调用body一致；语义修订仍1次，外层接口、q/m/U、模型参数、资格门槛不变。

账本66旧调用+A21+B12+C4+D17=120。容量289、原本地146历史边界及本轮143硬停身份保留；上限余额不是绕过STOP的授权。未执行23个余槽、恢复、freeze、封存24对、12次验收复评、PPO或Step 2；未提交、推送、上传私人文件。该阶段进程已正常退出，等待集中研究决策。
'''
(OUT/'RESULTS_ZH.md').write_text(report)
(OUT/'CONTINUATION_AMENDMENT_ZH.md').write_text(f'''# D剩余开发诊断接续授权（已执行）

{now}。依据当前研究者明确批准：只执行原D剩余36槽，107起、143硬停、总容量289。原每配置40槽中的预定重复保持独立身份，已开始槽跨接口去重。A/B/C STOP不可恢复。

继承C/D API财务试验身份`{p['financial_trial_identity']}`，累计2美元包含原0.0691662与所有责任，纳入共享20；一次新增余额GET已经使用，未新增models GET。沿用原限定数据外传范围和官方账户，凭据仅进程内，不改变env。

统一未决歧义诊断规则不变，来源证明错误/技术/原定等义等硬停仍生效；本修订不授予推荐/freeze/奖励资格，不新增语义提示修订。

原runner/helper代码和公开状态先归档为本目录*.before；必要接续实现及6项离线测试记录在implementation_change.json和relevant_tests_v2.log。新协议`{p['identity']}`；旧协议及所有STOP原样保留。

实际13次后因dev10B重复JSON键技术STOP，累计120。未完成23槽不续派。本文件为批准与执行的版本化记录，不是新实验或下一阶段授权。
''')
status=f'''# PM-RL1 当前状态

更新：{now}。**D剩余开发诊断已实际执行13次并触发技术STOP；累计107→120。当前固定四候选筛选结束，不建议申请当前D冻结验收，等待集中研究决策。** D共17/40槽尝试，16个有效数值、1个技术失败；23槽未派发（15主评分、4预定重复、4机制变体）。未派发不算错误或调用。

真实仓库`{R}`；分支`work/paper1-rq1-integration-20260816`、HEAD `0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28`保持不变。只准备本地状态，没有提交、推送、清理未提交文件。本页不包含题目原文、私人标注、完整来源、密钥或账户回执。

本轮授权仅D原剩余36槽、累计143硬停，289仍是容量；A/B/C原STOP不恢复。旧66+A21+B12+C4+D17=120。旧2次严格失败正式null、离线派生及后续实时记录分别保留。D此次完整输出含重复JSON键，原严格解析失败，正式q/m/U为null，不修复内部内容、不重试、不从thinking提取答案。原342个历史文件及账本前缀不变，无跨版本重复派发。

本轮12条技术有效、1条失败；D累计技术有效16/17。模型主动unknown0，复核未决语义案例2，已由来源证明的D实质错误0不等于证明无错误。混合断言核查部分改善，局部/严重后果依据与q锚点仍有边界；争议留在比较表并标记，不美化分母。人工比较使用修正后的回复哈希映射，Codex不是独立人评，Du派生不计第二评审。主体、时间更新与近等义部分测试成功，但剩余主体风险、后续严重度风险、4重复及4变体未覆盖，不能宣布合格或冠军。

沿用原runner、官方Flash/high、有效参数、完整输入、v2提示、量表和统一外层接口。必要D接续、跨版本去重、预算继承及服务指纹延续测试6项通过；语义修订仍1次。协议`{p['identity']}`；接口`{p['interface']['identity']}`。诊断派发与资格分离是此前看到部分结果后批准的规则，未伪称事前固定。原合同及容量修订历史均保留。

仅新增1次获准只读余额查询；无models/额外账户请求、充值或配置修改。指定凭据仅在本次官方请求进程中使用，未持久化或写日志。仅发送已授权原评分内容及完整合法来源，没有外传人工标签、复核或其它候选输出。服务身份与上轮回执一致；别名不是不可变权重保证。

本轮输入119,200、输出59,224 token（thinking52,630已包含），响应380.807秒；进程墙钟789.068秒含来源复核等待，已正常退出。本地GPU时间0，未操作其他用户进程。实际usage按当时时段/缓存价格计算约$0.040807680，保守记账$0.1068288；API试验累计usage估费$0.068880444、保守上界$0.175995，未结责任0。2美元停止线未重置、剩$1.824005；共享累计上界$1.68323791，对原边界新增$0.175995，计入共享20。估费不是逐项账单核销。

按D真实小样本用量外推，原128/384情景核心J均值计价区间约$9.81–24.89／$15.17–38.45；不含生成器/GPU/人工，缓存与长思考尾部存在不确定性，尚不能保证共享20美元及96小时可行。不选择episodes。

A21/40主体错误STOP、B12/40超时STOP、C4/40等义异常STOP、D17/40内部JSON重复键STOP全部保留，不在不等覆盖下排名。下一步是集中审议测量可靠性、事实预设/严重度/q锚点，而非追加模型追分；本轮不实施新测量设计。未恢复任何配置，未执行freeze、封存24对、12次验收复评、PPO或未来Step 2。长期两阶段目标与当前GET/STOP边界见[路线说明](PM_RL1_TWO_STAGE_ROUTE_20261015_ZH.md)。

本地详细合并结果：`project/outputs/pm_rl1/judge_selection_preparation_20261014_v1/D_development_20261015/RESULTS_ZH.md`；同目录有40槽CSV、逐请求用量、完整final/来源复核、成本投影及身份与核验记录。原状态已归档为CURRENT_STATUS.before.md。本轮已停止。
'''
(R/'project/docs/PM_RL1_CURRENT_STATUS.md').write_text(status)
print('written RESULTS_ZH.md, CONTINUATION_AMENDMENT_ZH.md, per_request_usage_private.csv, PM_RL1_CURRENT_STATUS.md')
