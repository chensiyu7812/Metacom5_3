#!/usr/bin/env python3
"""Render local Chinese audit report and minimal follow-up, no label changes."""
from pathlib import Path
from collections import Counter
import contextlib
import hashlib
import html
import io
import json
import sys
from audit_development import dump, table
from analyze_development import calculate

HERE=Path(__file__).resolve().parent
PROJECT=HERE.parents[2]
INTAKE=HERE/'intake'
read=lambda p:json.loads(p.read_text())
audit=[r for r in read(INTAKE/'development_item_audit_private.json') if r['slot']=='rater_1']
audit.sort(key=lambda r:r['order'])
by_order={r['order']:r for r in audit}
comparisons=read(INTAKE/'development_comparisons_private.json')
comp={r['Chen_order']:r for r in comparisons}
stats=calculate(INTAKE)
assert stats==read(HERE/'analysis/statistics.json')
form=read(PROJECT/'outputs/pm_rl1/completion_20260930_v2/P3/calibration/rater_1_form.json')
items={i['item_id']:i for i in form['items']}

followup_specs=[
 (6,'字段补充及风险含义确认',['risk_A','risk_B（确认原 local 的含义）','source_ids（保留非零风险时）'],
  'risk_A 在实际密文解开后为 ""。risk_B=local，有准确回复引文，但 source_ids=[]。原理由主要说问法不自然、逻辑不对；请确认你指的是事实/预设/明确边界错误，还是仅支持表达不佳。偏好 A 保留。若保留 local，请补合法来源编号；若只属于质量问题，由你重新选择风险，不由程序代填。',
  ['C:T003','C:T007','C:T008','C:T009']),
 (10,'字段补充',['risk_A','quote_B','source_ids'],
  'risk_A=""；risk_B=severe 已记录。quote_B 原值是中文来源描述“当前对话中提到‘我刚知道我的老板辞职了’”，不是 B 回复原句。请从下方 B 原文复制你指认的片段，并填写实际来源编号。偏好 A 与 severe 选项不替你更改。',
  ['C:T000','C:T006','C:T008']),
 (14,'字段补充',['risk_A','risk_B','quote_A（移出评论或换成确切片段）'],
  '两侧风险均为 ""。quote_A 实际是“更多感觉是表达问题。B的表达更舒服。”，属于评论，不能冒充回复引文。请选择两侧风险；确认该句保留为备注并清空引文字段，或提供相应原句。如果选择 local/severe，再补对应引文及来源。偏好 B、理由均保留，不要求改成平局。',
  ['C:T002','C:T004','C:T006']),
 (15,'字段补充',['risk_A','risk_B','quote_B（确切片段或确认清空）','source_ids（选择非零风险时）'],
  '两侧风险均为 ""。quote_B 原值是“本次对话中，从对话逻辑来看，应该是和老朋友而不是和AI聊了的。”，这不是候选回复原句。请亲自选择严重程度；如选择非零风险，复制候选回复片段并填来源。原偏好 A 保留，不从你已有理由推断 severe/local。',
  ['C:T005','C:T007','C:T013']),
 (16,'缺失偏好及风险依据确认',['preference','risk_A / risk_B（确认原 severe / severe）','quote_A','quote_B','source_ids','uncertainty（若选择无法判断）'],
  'preference=""，两侧风险都已记录 severe，但两侧引文均为空、source_ids=[]。理由主要质疑这种交接话术是否适合部署。请按照原角色契约区分“回复不贴切”和“实质身份/事实错误”，确认两侧风险。可以选择 tie 或 uncertain；选择 uncertain 时补说明，不强迫选胜方。保留 severe/local 时补对应回复原句和依据；ROLE 仅用于角色契约。',
  ['ROLE','C:T008','C:T009']),
 (31,'已有完整记录的事实确认',['risk_B（确认或修订）','事实核查说明 / 来源编号','preference（只确认是否维持 tie）'],
  '这题没有缺项，原记录为 tie、两侧 none_detected。请核对 B 的“have already discussed ... in your session”与 C:T012 的“Not yet ... next session”在时间上是否一致，并说明依据。风险与偏好分别回答；允许保留原判断，但请说明对这处差异的理解。若改为非零风险，再给 quote_B、source_ids。不会自动将事实差异变成你的整体偏好。',
  ['C:T011','C:T012','C:T018']),
 (35,'已有完整记录的事实确认',['risk_B（确认或修订）','事实核查说明 / 来源编号','preference（只确认是否维持 tie）'],
  '这题没有缺项，原记录为 tie、两侧 none_detected。B 提到“especially when it comes to job hunting”。请判断本题全部合法历史和当前对话是否支持这一具体背景；如果认为有支持，请给对应编号；如果认为它是试探性表达而非个人事实，也请说明。若认定无支持并标非零风险，再补 quote_B、source_ids（检查完整来源后可用 FULL_SOURCE）。整体偏好可独立保持 tie。',
  ['FULL_SOURCE'])]

followup=[]
for n,kind,fields,prompt,refs in followup_specs:
    r=by_order[n]
    followup.append(dict(Chen_order=n,Chen_item_id=r['item_id'],pair_id=r['pair_id'],group='development',
         category=kind,fields_to_supply_or_confirm=fields,question=prompt,reference_locator=refs,
         original_label=r['label'],response=None,provenance_of_future_reply='supplement_or_fact_adjudication_not_new_independent_blind_rater'))
dump(HERE/'minimum_followup_private.json',followup)
table(HERE/'minimum_followup_private.csv',[{k:v for k,v in r.items() if k!='original_label'} for r in followup])

notes={
 1:'原偏好及风险字段完整；两侧 q=4/m=0。',2:'资源差异下人工与自动均平局。',
 3:'一般支持控制：结构完整；双方均未检出风险。',4:'资源差异下人工与自动均平局。',
 6:'偏好可用且与自动相反；风险缺项与“质量/事实风险”边界需确认。',
 7:'理由“完全一样”应理解为近义：原文 It\'s / It is 并非逐字相同；不改原文，不额外要求重评。',
 10:'当前来源 C:T000 明确老板已辞职。人工方向与自动一致，但 severe 的引文/来源手续缺失。',
 14:'表达偏好与自动方向不同；没有客观唯一偏好，保留分歧，仅补风险/引文格式。',
 15:'C:T005/C:T013 指向老同学。自动给 B m=.25；人类风险尚空，不能按制题预期宣布 severe。',
 16:'偏好空且双 severe 缺引用。理由涉及部署话术，不能推填 uncertain 或把 severe 自动改为0。',
 23:'资源差异下人工与自动均平局。',26:'执行器差异下人工与自动均平局。',
 31:'形式完整但来源 C:T012 明确 Not yet；待人类事实确认，原 tie/none 保留。',
 32:'形式完整。自动把可选探询惩罚为局部边界错误；人类认为表达区别。作为裁判边界疑点保留，不强求改人评。',
 35:'形式完整。完整合法来源只有睡眠与饮酒/婚姻两段历史和3条当前消息，未见 job hunting；需事实确认。',
 37:'理由“完全相同”对应 I\'m / I am 的等效表达，非逐字相同；不影响原平局可用性。'}
audit_zh=[]
for r in audit:
    c=comp[r['order']];a=r['A_canonical_side'];scores=c['scores']
    audit_zh.append(dict(Chen题号=r['order'],Chen题ID=r['item_id'],pair_id=r['pair_id'],
       类型=c['control_type'] or c['contrast'],原偏好=r['label']['preference'],
       原风险A=r['label']['risk_A'],原风险B=r['label']['risk_B'],完整校验=r['strict_valid'],
       偏好可比=r['preference_comparable'],裁判A=f"q={scores[a]['q']}, m={scores[a]['m']}, U={scores[a]['utility']}",
       裁判B=f"q={scores[1-a]['q']}, m={scores[1-a]['m']}, U={scores[1-a]['utility']}",
       偏好吻合=c['preference_match'],审计说明=notes[r['order']]))
table(HERE/'逐题审计_开发16对.csv',audit_zh)

rules=[
 ('输入版本、盲映射、原始保全','包身份/表单身份及回复完全对应','满足','两份40条 envelope 无重复缺失，standalone submission 等于 original bundle 内对象，ZIP/成员 SHA 已核对。Du 文本映射单列；24对仍密封。'),
 ('开发标签完整接收','原 validate_label 全字段规则','不满足','11/16完整；5题共6个风险空值、1个偏好空值及引用问题。原批量入口遇首个无效字段即失败，因此本次是独立审计，未冒充正式 intake。'),
 ('独立双人证据','两份独立录入才可报独立一致性','证据不足','只有 Chen 原始记录加 Du 声明派生副本。原方案允许单人有限校准；不要求为凑两份重复做40题。'),
 ('8.4-1 技术资格','固定技术集首试≥95%，一次恢复后全可处理','证据不足','初版开发首试32/32有效（该子集满足）；全部79不同回复尚缺47封存回复。额外1次复核探针不加入首试分母。'),
 ('8.4-2 控制资格','封存四类来源确认严重控制均m=1且U更低，中性无严重误罚','证据不足','封存8控制未开封/未测。开发四严重控制的原人评全无完整非零风险依据，且计划→结果控制存在实质事实分歧；不能用制题意图充当人类确认。'),
 ('8.4-3 稳定性','12独立复评分，≥11同U，0严重翻转，0缺失','证据不足','12次均未执行；原1次完整来源复核不是独立复评分。'),
 ('8.4-4 方向/平局','封存自然明确方向≥8时≥75%吻合；平局≥5时≥80%识别','证据不足','开发只有8自然，吻合5/8；平局5/7、明确0/1。正式24对封存未开，不把开发结果冒充正式通过/失败。'),
 ('8.4-5 低差异分支','平局≥5且识别≥80%；其余明确方向全吻合；事实/稳定性通过','证据不足','开发显示低对比，但5/7平局吻合和0/1方向并不支持低差异资格。仍需事前封存验收；不因此扩卷或宣布128已准入。'),
 ('8.4-6 严重自然错误否决','不得偏好人类来源确认严重错误且漏风险','证据不足','目前没有合格的人类非零风险及事实裁决记录，不能宣告否决已触发或已排除。第35题自动反而检出风险且避开该侧。'),
 ('最终 measurement freeze','开发结案后固定协议/运行/人工来源及资格合同再开封','不满足','尚未创建；本次不代设 semantic_revisions，不解开24对，不改变固定数据划分。')]
table(HERE/'qualification_checklist.csv',[dict(项目=a,事前标准=b,状态=c,依据=d) for a,b,c,d in rules])

def esc(s):return html.escape(str(s))
CSS='''body{font:16px/1.75 system-ui,sans-serif;max-width:1120px;margin:40px auto;padding:0 24px;color:#17212b;background:#fff}h1{font-size:28px}h2{margin-top:32px;font-size:22px}h3{font-size:18px}table{border-collapse:collapse;width:100%;font-size:14px;margin:18px 0}td,th{border:1px solid #d6dee6;padding:9px;vertical-align:top;text-align:left}th{background:#f0f5fa}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:14px;font-size:14px}code{overflow-wrap:anywhere}a{color:#125e9e}.callout{padding:16px;background:#edf5fc;border-left:5px solid #287bb5}.muted{color:#52606d}details{margin:16px 0;border:1px solid #d6dee6;padding:12px}li{margin-bottom:8px}@media print{body{max-width:none;margin:0}details{break-inside:avoid}}'''
def html_table(headers, rr):
    return '<table><thead><tr>'+''.join('<th>'+esc(h)+'</th>' for h in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(c)+'</td>' for c in r)+'</tr>' for r in rr)+'</tbody></table>'
def page(title,body):return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>'+esc(title)+'</title><style>'+CSS+'</style><body><h1>'+esc(title)+'</h1>'+body+'</body></html>'

fb=['<p class="callout">只涉及已打开的开发题：5题补字段＋2题事实确认。不重做40题，不含封存题，不展示模型分数、方法名称或预期正确选项。</p>',
 '<p>统一沿用 Chen 原卷题号和 A/B。请逐项用文本回复即可；Du 无须再填一遍。保留原判断是允许的，事实裁决与主观偏好分开记录。后续补充将带日期与来源保留，不能伪装成首次盲评。</p>',
 '<p>原字段：preference=A/B/tie/uncertain；risk=none_detected/local/severe/uncertain。none_detected 表示未检出，不是“已证全对”；local/severe 需候选回复的原文片段及来源编号；uncertain 需说明。表达不自然通常归支持质量，只有具体事实、身份、时态或明确边界问题才归风险。此处解释沿用原量表，没有增加阈值。</p>',
 '<details><summary>原角色契约（英文原文）</summary><pre>'+esc(form['role_contract'])+'</pre></details>']
txt=['开发人评最小补充清单（2026-10-14）','只需5题补字段＋2题事实确认；均按 Chen 原卷题号、A/B。Du 不重复补填。',
 '风险选项 none_detected/local/severe/uncertain；偏好 A/B/tie/uncertain。非零风险补候选原文和来源；不确定补说明。不得因看到模型分数而把修订冒充原独立盲评。','']
for r in followup:
    item=items[r['Chen_item_id']];source=form['sources'][item['source_key']]
    head=f"第{r['Chen_order']}题 · {r['Chen_item_id']} · {r['category']}"
    fields='、'.join(r['fields_to_supply_or_confirm'])
    fb.extend(['<h2>'+esc(head)+'</h2>','<p><b>需要补充/确认：</b>'+esc(fields)+'</p>','<p>'+esc(r['question'])+'</p>',
       '<details><summary>你原有的完整答案（保持原文）</summary><pre>'+esc(json.dumps(r['original_label'],ensure_ascii=False,indent=2))+'</pre></details>',
       '<p><b>A 原回复</b></p><pre>'+esc(item['A'])+'</pre><p><b>B 原回复</b></p><pre>'+esc(item['B'])+'</pre>',
       '<details><summary>全部合法来源：当前cut '+esc(source['current_date'])+'；可核对来源编号</summary><pre>'+esc(json.dumps(source,ensure_ascii=False,indent=2))+'</pre></details>',
       '<p class="muted">你的补充：请写题号、字段和值；维持已填判断也请明确说明。没有预填新答案。</p>'])
    txt.extend([head,'需要补充/确认：'+fields,r['question'],'原答案：'+json.dumps(r['original_label'],ensure_ascii=False),
       'A：'+item['A'],'B：'+item['B'],'来源定位：'+', '.join(r['reference_locator']),
       '全部合法来源已附同名 HTML 文件，点击该题下方展开。','你的补充：',''])
(HERE/'最小补充清单_7题.html').write_text(page('开发16对：最小补充清单', ''.join(fb)))
(HERE/'最小补充清单_7题.txt').write_text('\n'.join(txt))

body=[]
body.append('<p class="callout"><b>这批真实人评可以用于开发诊断，目前不能证明裁判/奖励已合格。</b>已验收16对：11对全字段通过；15对偏好可比较；32个回复侧面有26个风险选项可读取、22个满足形式证据条件，但这22个全是“未检出风险”。24对验证标签继续封存。下一步只需5题补字段＋2题事实确认，随后再决定既定的一次语义修订与冻结。</p>')
body.append('<p>报告日期：2026-10-14。输入为用户本次提供的真实导出包，不沿用前次缺文件结论。所有数字按 Chen 的一套原始记录、唯一 pair 计算；Du 是派生核对材料。报告含开发集诊断分数，不能给后续封存评审作答案提示。</p>')
body.append('<h2>1. 来源、版本与盲测边界</h2>')
body.append('<p>仓库 <code>/home/tokkio/Metacom5_3</code>（实际目录 <code>/opt/tokkio-data0/tokkio_projects/Metacom5_3</code>）；分支 <code>work/paper1-rq1-integration-20260816</code>；HEAD <code>0c85538ad9a5f6065a7bc31ee0769cb76eaa0f28</code>。操作前后 git status 均干净。本目录被既有 outputs 忽略规则覆盖，未提交/推送/上传。</p>')
body.append('<p>真实 ZIP：<code>/home/tokkio/PM_RL1_Chen_Du_标注导出包.zip</code>，132,327 bytes；SHA-256：<code>630d09d7d275febb802e922fab182da9244af36d8388aef26ff6721ba684e7ee</code>。5个成员都已保留字节副本，哈希见 <a href="intake/input_manifest.json">input_manifest.json</a>。Chen/Du standalone JSON 与 original_encrypted_bundle 对应 submission 对象完全相同；manifest 的文件哈希和来源包哈希全部匹配。</p>')
body.append('<p>packet_identity：<code>d772956d6ddbe05b571d84f7e57537f5664da0fb7129af350a76a25e096182e2</code>。Chen 绑定 rater_1，form_identity <code>90047a19dec8a41b02ad8dbde8b388307b3a33e60411c903a6d7a5e590fc08db</code>；Du 绑定 rater_2，<code>1b530bc3fbfb75bf21188665bb88c4340e1b4c82d0653babf137a3778a71465b</code>。每份40题，无重复、缺失或替换，题目/回复/来源与冻结原卷一致。</p>')
body.append('<p>沿用仓库 <code>human_calibration.py</code> 的 RSA-OAEP/AES-GCM 解密及 <code>validate_label</code>，先按冻结映射拒绝非 development 项。成功运行解开32个开发 envelope，代表16个唯一题对；48个 validation envelope 对应24题继续加密。没有最终 measurement_freeze，因此不能开封。原始bundle的 submission 完全相同，未另行解密一遍。解密日志见 <a href="intake/decryption_access_log.json">decryption_access_log.json</a>。</p>')
body.append('<p>这24对是裁判校准验证集，来源于既有训练用户，不等于最终研究 test。额外8对备用未激活，原96/18/48任务切分没改。初版冻结、原题包、来源和评分摘要在本次前后只读核验均一致；私钥仅在原位置使用，未写入任何产物。</p>')
body.append('<p>Du 的 reviewer_kind 虽写 individual_human，provenance 明确是 user_declared_identical_copy。用户声明两人判断相同可以如实记录，但没有两份独立原始录入的可核验证据。只能按1套原始记录＋1套派生核对处理，不报告80样本、独立一致率或 Cohen κ。</p>')
body.append('<p>开发16题派生转换逐字段匹配；7题发生 A/B 换序。Du 的 reason/uncertainty 全部保持 Chen 原文，解释统一用 Chen 坐标。例：Chen第10题的“A更合适…B错了”在 Du 中实际指 Du B更合适、Du A出错。原文字未改，映射证据见 <a href="intake/Du_AB_provenance_private.csv">Du_AB_provenance_private.csv</a>。全卷另有1道封存题两侧逐字相同，导出按文本不换序、原随机位记录换序；该异常只做元数据记录，待合法开封后核验，未读其答案。</p>')
body.append('<p>导出说明记载使用中文辅助译文 pmrl1-zh-assist-v1。此次包未附该界面的实现/译文快照，因此可核验原题与答案绑定，不能完全重建评审实际看到的译文。中文评论进入 quote 字段可能与交互方式有关；证据不足以认定是评审疏忽或翻译错误。当前不要求全卷重填。</p>')
body.append('<h2>2. 字段、分母与实际可用性</h2>')
body.append(html_table(['字段','尺度/规则','本次处理'],[
 ['preference','A/B/tie/uncertain','有合法枚举和非空理由即可作偏好描述；不因风险缺项丢弃偏好。无法判断与缺失分别报告。'],
 ['risk_A/B','none_detected/local/severe/uncertain','先数选项；再逐侧核验引用。未检出不等于事实全对，未填不补0。'],
 ['quote_A/B','对应回复的精确子串','非零风险必填；即使风险未填，已有错误引用也记录。'],
 ['source_ids','本题来源ID，或 ROLE/FULL_SOURCE','唯一且有效；非零风险不可为空。编号合法也不自动证明语义成立。'],
 ['reason / uncertainty','文字理由/不确定说明','原文保留；有 uncertain 时必须说明；不根据理由反填偏好/风险。'],
 ['item_id','原表单ID','表单身份、题包身份、来源、A/B共同绑定，禁止按题号猜配。']]))
body.append(html_table(['指标','有效数','缺失或未满足','解释'],[
 ['40对用途','开发16；封存24','24未开封，效度未知','不是24无效。'],['原完整校验','11/16对','5/16未通过','自然7/8，控制4/8。'],
 ['偏好可比较','15/16对','1空值；0显式uncertain','自然8/8；控制7/8。'],['风险选项','26/32侧，双侧都有选项12/16对','6个空侧面','22 none_detected、1 local、3 severe。'],
 ['风险形式证据可用','22/32侧，双侧满足11/16对','6空值＋4非零选项缺必需依据','22个全部为 none_detected；其中存在事实争议，尚非金标准。'],
 ['来源齐备的非零风险','0个侧面','已填4个非零风险均缺source_ids；其中3个缺/错quote','当前不能可靠估计严重风险召回率。'],
 ['人类q/奖励绝对尺度','未采集','没有人类0–4分','偏好不能反推出人类q，更不能认证 U 差值或PPO学习正确。']]))
body.append('<p>完整校验是结构条件，不等于答案必然正确。偏好与风险字段分开保留只用于描述性分析，未绕过原正式接收规则。没有确定性的纯格式修复可以补出缺失判断；本次标签改动数为0。中文评论不能自动翻译成“精确英文引用”，也不能从理由推填风险等级。</p>')
body.append('<h2>3. 原界面12题究竟是什么情况</h2>')
body.append('<p>Work 的40有输入/29 judgments_recorded/28完整/12待核查是包中保留的浏览器状态，不能直接当作事实验收。12题映射到开发5题、封存7题。开发5题经解密确有字段问题，其他11题通过既有校验。封存7题只确认ID和所属组，不读取具体 issues 或答案，不把它们归类为无效。</p>')
body.append(html_table(['Chen题号/ID','实际原值与触发规则','当前仍可用','最小补救'],[
 ['6 / 6b9a48e7625f56d9a291','risk_A=""；risk_B=local；source_ids=[]。非零风险须来源。','偏好 A；B风险选项和精确quote_B','补 risk_A；确认 local 所指，保留时补source_ids。'],
 ['10 / 322cfa649b0caf7e0a44','risk_A=""；quote_B 为中文来源描述而非B原句；source_ids=[]。','偏好 A；B severe 选项','补 risk_A、quote_B、source_ids。'],
 ['14 / b71e6f51e2850dfd321a','risk_A=risk_B=""；quote_A 为“更多感觉是表达问题。B的表达更舒服。”。','偏好 B及理由','补两侧风险，确认移出评论或换精确quote；非零时补来源。'],
 ['15 / 5afe969c86289392306b','risk_A=risk_B=""；quote_B 为老朋友/AI的中文分析，不是回复片段。','偏好 A及理由','补两侧风险；修quote_B；非零时补来源。'],
 ['16 / 34ade110afd01145bfe0','preference=""；risk_A=risk_B=severe；quote_A=quote_B=""；source_ids=[]。','双severe只是已记录的选项，尚不能作事实依据','补偏好，确认两侧风险；非零补quote/来源；不确定补uncertainty。']]))
body.append('<p>原12题中其余7题（Chen原卷第5、9、11、12、24、29、30题）仍封存，题ID/映射可查 <a href="intake/sealed_inventory_private.csv">sealed_inventory_private.csv</a>。本轮不要求你为这7题补答；开封后才可验证原值与问题。</p>')
body.append('<h2>4. 与冻结初版裁判的对照</h2>')
body.append('<p>比较对象为冻结候选协议 <code>c56b2e305ca5b27e5511dbe953b693f3e2339244982cf8e66fa33a47df2fc1ae</code>，运行身份 <code>ad198b7104cb0d62927f94f0ea8821f21bdc6e6496cecb4f29cb5429a1a35879</code>。逐条核验同来源、同回复、primary draw、rubric/runtime、原始输出哈希、q/m/U与摘要。只用32次原单点评分，额外复核探针不替换。没有调用新模型。</p>')
body.append(html_table(['分组','偏好有效/总数','人类明确方向/平局','吻合','明确方向吻合','平局吻合'],[
 [s['group'],f"{s['comparable']}/{s['pairs']}",f"{s['clear']} / {s['ties']}",f"{s['matches']}/{s['comparable']}",f"{s['clear_matches']}/{s['clear']}",f"{s['tie_matches']}/{s['ties']}"] for s in stats['preference_strata'][:5]]))
body.append('<p>全部开发10/15（66.7%）仅为描述；自然5/8（62.5%）才是自然对照的描述性数值。自然7个人类平局中自动平局5个（71.4%），唯一明确偏好与自动相反（0/1）；不将大量平局解释为自动裁判无问题，也不为了“拉开差异”强迫人类选胜方。原卷A胜3/B胜1/平11/空1只是显示顺序计数，不是系统胜率。</p>')
body.append('<p>可信映射后的自然策略：4个资源对均为同执行器 OFF/ON，人类ON胜1、OFF胜0、平3，自动OFF胜1、平3；4个执行器对人类全平，自动主执行器胜1、副执行器胜1、平2。arm 与具体资源向量见 <a href="analysis/natural_strategies.csv">natural_strategies.csv</a>。这8对来自既有开发前缀，无任何PPO输出；不能推断RL增益或资源普遍无效。</p>')
body.append(html_table(['仅按已填风险选项（证据未必齐）','自动m=0','自动m=.25','自动m=1','有效侧数'],[[r['human_risk'],r['auto_m0'],r['auto_m025'],r['auto_m1'],r['denominator']] for r in stats['risk_confusion'] if r['cohort']=='enum_only']))
body.append('<p>26侧选项层面有：人工非零而自动0共2侧（第6题B、第16题B）；人工0而自动非零共3侧（第31题B、第32题A、第35题B）。这些是“不一致记录”，尚不是经事实裁决的漏判/误判。4个人类非零判断全缺必需来源，不能以此计算严重风险召回率。即使只看22个形式可用的 none_detected，自动有2个m=1、1个m=.25；其中31与35存在明确来源疑点，不能径直给裁判记2次严重误报。</p>')
body.append('<h2>5. 实质分歧及最小事实裁决</h2>')
body.append(html_table(['题号','实际证据','可支持的分析/处置'],[
 ['6','B是询问谈话有无平息怒气，也给了冲突升级选项。人工偏好A，认为B问法不自然；自动偏B并给A q=2。','偏好本身可保留。local是否属于具体预设/边界错误需评审说明；不能把表达不佳直接记成事实风险。自动q两档差的依据也值得开发修订时检查。'],
 ['10','C:T000: I just found out my boss resigned.；B断言没有辞职。','人工偏好与自动方向相同，有可定位来源；仅补缺失字段，不需要重做选择。'],
 ['14','两种普通支持回应；人类偏B更舒服。自动A q=4、B q=3，其理由强调未显式点名blog。','可能是自动过细的风格区分；主观偏好没有唯一正确答案。只补缺字段，不要求人类顺从模型。'],
 ['15','C:T005是老同学，C:T013是与老同学聊天后换视角。B写 Talking with me。','主体归属需依原角色契约；自动只给m=.25。人类风险为空，不能把制题预期m=1当真值。补风险等级及依据后才决定严重度修订。'],
 ['16','A认领自己的妈妈和过去话语；B明确那不是我的经历。原理由质疑转接话术适当性，却选择双severe。','这是质量与身份风险混在一起的疑点。尊重评审意见，但需明确其所标错误及原偏好，不由助手生成答案。'],
 ['31','当前C:T012明确 Not yet，计划下次与治疗师讨论；B写 have already discussed。','这题形式完整但把计划/完成视作无实质差异。需要一次事实确认，原tie与none仍保留；不能为提高吻合率直接改人评或改裁判为0。'],
 ['32','A提供探索选项或谈别的；来源C:T014希望先处理失望。自动m=.25并低q，人类认为两者无实质差别。','有自动把可选邀请当成强迫行动的过罚疑点；自动理由还将C:T014措辞归到C:T016。作为裁判失误候选记录，当前不增加人工题。'],
 ['35','B带入job hunting。已逐条检查本题全部合法来源：H00120条睡眠、H00223条饮酒/婚姻及当前3条消息，没有求职依据。','协调者的来源核查支持“无支持的具体背景”，不是人类金标签。需要确认B风险与原tie是否保持；不能把裁判m=1直接定为误报。']]))
body.append('<p>第31、35题是额外2道事实确认，不是新增题或缺项修复。依据既定方案8.3“有来源可裁决的事实问题单列一次裁决”，与上面5题集中反馈一次。原始偏好、风险、理由全保留；补充另记 human_fact_adjudication，不能回写成原始独立盲评。它们的必要性在于避免把尚有事实遗漏的人评直接当金标准，把原本正确的检出改坏。</p>')
body.append('<p>中文辅助阅读是否造成对比信息丢失，目前无法确认。第7/37题理由说“完全一样”，原英文只是缩写/展开差异；平局依然合理，无需再问。没有要求对每一个人机不一致都重评。</p>')
body.append('<h2>6. 既定P3标准：现在能够宣布什么</h2>')
body.append(html_table(['项目','事前标准','状态','证据'],rules))
body.append('<p>不调用 calibration_decision.decide 伪造最终结论：它要求16或24自然验证对＋8控制＋12复评分，本轮只有8自然开发对，固定分母不匹配。正式门槛保留原值，不看到结果后新设阈值。当前 reward_qualified=false，含义是资格尚未成立，不能据此宣称RL研究失败。</p>')
body.append('<p>可以支持的结论：原数据真实可读、版本可追踪；本组偏好多为相当；部分字段欠缺；已有候选存在风格/边界过罚疑点；部分人工记录自身也有事实遗漏疑点。不能证明：独立双人一致、裁判普遍可靠、严重风险检出率达标、单点评分稳定、奖励适合PPO、RL有收益或最终test有效。</p>')
body.append('<p>16对共享9个前缀（7个前缀各2对、2个各1对），仅3个owner（p1=5、p15=6、p18=5），本身有目的地包含既知失败。自然8对也只有3个owner。故只报配对描述，未计算独立二项区间、p值、显著胜率或κ；样本不足以稳定估计owner聚类泛化误差。不能把Du复制记录或控制题叠加扩大自然样本量。</p>')
body.append('<h2>7. 最小下一步与停止位置</h2>')
body.append('<ol><li><b>原计划内：</b>集中回复 <a href="最小补充清单_7题.html">7题最小补充清单</a>：第6/10/14/15/16题补字段；第31/35题仅做事实确认。不填其余开发题，不触碰封存7条待核查状态，不要求Du再复制一次。</li><li><b>原计划内、依赖补充：</b>另存补充记录与来源，复核开发接收是否完成；保留全部原选项以及仍有的主观分歧。据此才决定是否使用最多一次语义修订。重点是个人事实/支持质量边界和严重程度，不能以记住题目或迎合人评来提高开发分。</li><li><b>原计划内、后续单独执行：</b>冻结完整评分身份、人工来源、资格合同和开发接收哈希后，才开24对并执行原封存/12复评分。先按固定规则验收，不在封存失败后继续调提示重称独立通过。</li><li><b>需另行确认的变更：</b>若要增设独立评审、扩卷、换奖励/模型主线或启用B1人工终值窄任务，须列具体代价与范围再决定。本轮没有这类变更，也未创建任何冻结来绕开开封条件。</li></ol>')
body.append('<p>此次新增API费用0、新模型请求0、训练更新0。若最终身份完全不变，后续还有47个封存唯一回复＋12次独立复评分，共59个本地J请求；按已有33请求/1,750.58秒的批处理引擎速率粗算约0.87引擎小时，未含装载/长来源/失败余量，不是承诺或付费报价。若改身份，旧分数不能混用；重新测32开发＋47封存＋12复评分共91请求，约1.34引擎小时，同样只作敏感性估计。连同已耗33次分别为92或124次，须继续核算140请求上界及复核/恢复额度。本轮均未执行。</p>')
body.append('<h2>8. 逐题结果、复现与检查</h2>')
body.append(html_table(['Chen题号','题ID','类型','原偏好','完整校验','人机偏好吻合','说明'],[
 [r['Chen题号'],r['Chen题ID'],r['类型'],r['原偏好'] or '空',r['完整校验'],r['偏好吻合'] if r['偏好吻合'] is not None else '不比较',r['审计说明']] for r in audit_zh]))
body.append('<p>完整原字段、逐项规则、Du映射、引用错误原值见 <a href="intake/development_item_audit_private.json">逐字段审计JSON</a> / <a href="intake/development_item_audit_private.csv">CSV</a>；中文逐题表见 <a href="逐题审计_开发16对.csv">开发16对CSV</a>；分层统计见 <a href="analysis/statistics.json">统计JSON</a>、<a href="analysis/preference_strata.csv">偏好分层表</a>、<a href="analysis/risk_confusion.csv">风险列联表</a>；引用评分文件与哈希见 <a href="intake/score_binding_receipts.json">评分绑定回执</a>。可复现命令见 <a href="REPRODUCE.txt">REPRODUCE.txt</a>；可执行伴随笔记见 <a href="development_analysis.ipynb">development_analysis.ipynb</a>。</p>')
body.append('<p>检查：新增审计7项测试通过（包含48个真实封存envelope在密码操作前全部拒绝）；原协议/准入28项pytest通过；32条开发记录的校验结果与原validator逐项相符。Notebook按纯Python新命名空间顺序执行并保存输出；本机缺少Jupyter/nbformat/nbclient，未运行原生Jupyter内核或完成浏览器视觉验收，属于展示验证限制，不影响已运行的审计脚本与数值检查。</p>')
body.append('<p>执行记录透明保留：首次映射检查识别封存等文回复的换序歧义，在解密前停止；随后两次开发脚本调试分别修正评分文件应以request_id定位、控制题无自然策略sides字段，失败的局部产物保留为 intake_partial_01/02；三次均只读同16对开发标签（共96次开发envelope解密，32个不同envelope），始终0个封存解密。成功回执 intake/audit_receipt.json 描述单次成功运行。没有修改原仓库核心代码、原始标签或既有结果。</p>')
body.append('<p class="muted">方法依据：项目既定 PM_RL1_FEASIBLE_COMPLETION_PLAN_20260930_ZH.md §§8.2–8.4，runbook.md 的P3人工交接段；源文件 hash 留在 input_manifest。已有上一轮前置报告只负责原题包核查，不是本次人评分析。本目录是当前实际作答验收的独立新增产物。</p>')
(HERE/'PM_RL1_开发16对人评验收报告_20261014.html').write_text(page('PM-RL1 开发16对人评验收与裁判对照', ''.join(body)))

# Notebook: deliberately descriptive; does not touch the key or sealed JSON.
cells=[]
def md(s):cells.append(dict(cell_type='markdown',id=f'cell-{len(cells)}',metadata={},source=s.splitlines(True)))
def code(s):cells.append(dict(cell_type='code',id=f'cell-{len(cells)}',metadata={},source=s.splitlines(True),execution_count=None,outputs=[]))
md('# 开发16对验收伴随分析\n\n15对偏好可用、11对全字段通过；24对保持密封。这里只读取开发审计产物，不解密。')
md('## 方法与数据\n\nChen原始记录是唯一计数来源。Du派生文件不增加样本。数据为有目的的开发选择，16对共享9前缀、3owner；不计算独立样本置信区间。风险枚举可读与证据齐备分别统计。')
code("from pathlib import Path\nimport json, sys\naudit_root = Path('/home/tokkio/Metacom5_3/project/outputs/pm_rl1/human_acceptance_20261014_v2')\nsys.path.insert(0, str(audit_root))\nfrom analyze_development import calculate\nresult = calculate(audit_root / 'intake')\nsaved = json.loads((audit_root / 'analysis/statistics.json').read_text())\nassert result == saved\nprint({k: result['totals'][k] for k in ['pairs','preference_pairs','strict_complete','risk_enum_sides','risk_evidence_ready_sides']})\n")
md('## 结果\n\n表格足以展示这些固定小分母；不绘制会暗示稳定分布或独立样本量的图。')
code("for row in result['preference_strata'][:5]:\n    print(row['group'], '可比', row['comparable'], '吻合', str(row['matches'])+'/'+str(row['comparable']), '平局', str(row['tie_matches'])+'/'+str(row['ties']), '明确', str(row['clear_matches'])+'/'+str(row['clear']))\nprint('风险原选项列联表：')\nfor row in result['risk_confusion']:\n    if row['cohort'] == 'enum_only': print(row)\nassert result['totals']['usable_nonzero_risk_with_required_evidence'] == 0\n")
md('## 结论与验证范围\n\n自然吻合5/8，平局5/7，明确0/1。当前原始数据支持开发诊断，不支持奖励资格。5题补字段＋2题事实确认；后续修订另存，不能冒充原始盲评。\n\n本笔记用标准Python逐单元执行并保存输出。没有nbformat/nbclient/Jupyter内核，未完成原生Jupyter与浏览器视觉验收；复验命令见REPRODUCE.txt。')
ns={};execution=0
for cell in cells:
    if cell['cell_type']!='code':continue
    execution+=1;buf=io.StringIO()
    with contextlib.redirect_stdout(buf):exec(compile(''.join(cell['source']),'<notebook-cell>','exec'),ns)
    cell['execution_count']=execution;cell['outputs']=[dict(output_type='stream',name='stdout',text=buf.getvalue().splitlines(True))]
nb=dict(cells=cells,metadata=dict(kernelspec=dict(display_name='Python 3',language='python',name='python3'),language_info=dict(name='python',version=sys.version.split()[0])),nbformat=4,nbformat_minor=5)
dump(HERE/'development_analysis.ipynb',nb)
dump(HERE/'checks/notebook_execution.json',dict(code_cells_executed=execution,mode='fresh Python namespace sequential execution',
    outputs_saved=True,statistics_equal_saved=True,native_jupyter_execution=False,visual_viewer_check=False,
    gap='nbformat/nbclient/nbconvert/ipykernel unavailable; no native viewer check claimed'))
print('Rendered report, 7-item follow-up, Chinese audit CSV, qualification table and executed companion notebook.')
