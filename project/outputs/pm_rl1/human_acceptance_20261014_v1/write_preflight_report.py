#!/usr/bin/env python3
"""Write a local, explicitly partial Chinese receipt from verified preflight data."""
from pathlib import Path
import csv
import hashlib
import html
import json
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent


def table(headers, rows):
    cell=lambda x:html.escape(str(x))
    return '<table><thead><tr>'+''.join('<th>'+cell(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join(
        '<tr>'+''.join('<td>'+cell(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'


def main():
    summary=json.loads((HERE/'preflight/preflight_summary.json').read_text())
    tests=ET.parse(HERE/'checks/intake_and_gate_tests.xml').getroot().find('testsuite').attrib
    assert int(tests['failures'])==int(tests['errors'])==0
    fields=[
        ['item_id','固定题目ID','必须由packet_identity、form_identity及冻结map联合核对，不按题号猜配'],
        ['preference','A / B / tie / uncertain','平局是有效判断；无法判断单列；缺失不补为平局'],
        ['risk_A、risk_B','none_detected / local / severe / uncertain','逐侧检查；未检出问题不是事实全对；无法判断不是风险0'],
        ['quote_A、quote_B','对应候选回复的原文子串','非零风险必填；引用归属应随A/B可信换序映射检查'],
        ['source_ids','本题合法来源编号或ROLE/FULL_SOURCE的列表','必须唯一、属于本题；非零风险需依据；编号合法不等于语义支持'],
        ['reason','非空文字','保留原文；与选项矛盾或A/B指代不明时单列待确认，不据理由补出选项'],
        ['uncertainty','文字','任一判断为uncertain时必须说明原因'],
    ]
    qualification=[
        ['8.4-1 技术集','首试≥95%，固定恢复后全部可处理','证据不足','初版开发首试32/32结构有效；40对固定技术集对应79条不同回复，还有47条封存回复未测。1次额外复核不能加到首试分母。'],
        ['8.4-2 严重/中性控制','四类来源确认严重错误均m=1且U更低；中性不误罚严重','证据不足','封存8对未开封/未评分；制题假设不是人类确认。'],
        ['8.4-3 独立复评分','12次中至少11次U相同，严重状态无翻转','证据不足','已准备12次，未执行。现有1次复核探针不是重复稳定性检查。'],
        ['8.4-4 自然方向/平局','明确方向≥8时吻合≥75%；平局≥5时识别≥80%','证据不足','实际人评导出缺失，无法确定有效方向数、平局数、吻合分子或分母。'],
        ['8.4-5 低差异分支','明确方向不足8；≥5平局且识别≥80%；其余明确方向全对及其他门槛通过','证据不足','不能从两个派生文件或界面完整性计数推断低差异；备用仅按预定信息不足条件启用。'],
        ['8.4-6 严重自然错误否决','不能偏好来源确认的严重错误侧且漏判其风险','证据不足','没有已接收的人类/来源裁决，不能确认触发，也不能宣称排除。'],
    ]
    for filename,headers,rows in [('field_dictionary.csv',['字段','尺度','处理规则'],fields),
                                  ('qualification_checklist.csv',['规则','事前标准','本次状态','证据'],qualification)]:
        with (HERE/filename).open('x',encoding='utf-8-sig',newline='') as f:
            writer=csv.writer(f);writer.writerow(headers);writer.writerows(rows)
    sections=[]
    def section(title,body):sections.append('<section><h2>'+html.escape(title)+'</h2>'+body+'</section>')
    section('结论与停止位置', '<p><strong>已完成原题包、版本、80个表单条目与40个真实pair的映射核查；尚未取得人评导出，未完成答案验收。</strong></p>'
        '<p>指定的 /home/tokkio/PM_RL1_40对人工校准包_20261001.zip 只有 rater_1.html、rater_2.html、填写说明.txt，是空白交付题包。'
        '本地文件搜索及可连接文档会话检查未找到 PM_RL1_Chen_Du_标注导出包.zip 或 pending_review.json。'
        '这不否定用户已完成人评，也不证明任何一题漏填。</p>'
        '<p>当前可审核的人工答案为“尚无文件可核验”，有效偏好/风险对数应记未知，不能写成0对有效、28对有效或12对无效。'
        '请提供已完成导出包在当前环境的路径；不要求重新做40题，也不索要私钥。</p>')
    section('版本、身份与来源', '<p>日期：2026-10-14（Asia/Tokyo）。分支：'+html.escape(summary['repository_branch'])+
        '；提交：<code>'+summary['repository_commit']+'</code>。开始及收尾的Git工作区无跟踪文件改动；新增审计材料仅存本独立忽略目录，未提交或推送。</p>'+
        table(['对象','已核实的身份'],[['原题包SHA256',summary['original_zip_sha256']],['packet_identity',summary['packet_identity']],
        *[[r+' form_identity',v] for r,v in summary['form_identities'].items()]])+
        '<p>原ZIP与P3本地交付ZIP逐字一致，ZIP内三个成员与 human_handoff_final 对应文件逐字一致；表单内嵌JSON与冻结form匹配。'
        '40条冻结文件/代码检查通过。逐文件哈希见 preflight/input_manifest.json（不输出私钥或私钥哈希）。'
        'Chen/Du 对应哪一个rater槽位尚未核实，不能按姓名或文件排列推定。</p>')
    section('真实分析单位与开封边界', table(['校准分组','题型','pair数','前缀数','owner数','已有首轮自动分可比较pair数'],
        [[r['group'],r['kind'],r['pairs'],r['prefixes'],r['owners'],r['first_scores_available_pairs']] for r in summary['strata']])+
        '<p>共40对、27个不同前缀、15个owner；13个前缀各有两对，另14个前缀各一对。开发16对来自9个前缀/3个owner；'
        '封存24对来自18个前缀/12个owner，两组owner互斥。备用8对未交付/未启用。校准分组不等于PM原train/dev/test划分；'
        '封存校准采用原train用户，不是最终研究test。</p>'
        '<p>依据原方案8.3及runbook：先只读16对开发标签，最多一次语义修订，冻结完整评分身份、人工接收来源、资格合同与验证入口后再开24对封存。'
        '当前无最终measurement_freeze，也无旧human_intake接收记录。本次没有解密任何答案，不能为完成40对统计而跳过此步骤。</p>')
    section('Chen/Du来源与A/B风险', '<p>按用户说明保留事实：两人均完成并声明判断相同；Du文件由Chen已保存记录转换，不是独立录入导出。'
        '它不能产生另外40个独立样本，复制后的吻合率、Cohen κ或置信区间不能证明独立评审一致性。'
        '应保存“原始录入来源＋另一位一致性声明/派生记录”的不同来源，不否定同学的实际参与。</p>'
        '<p>原两份rater表单有17对A/B相反、23对方向相同；按 pair_id、回复全文哈希和swapped共同核对。'
        '其中1对的两侧回复文字完全相同，因此17处盲映射交换中，有不同文本的实际换侧是16对；相同文本不能由侧位解释成回复质量差异。这不是Du已正确转换17题的证据。还须检查导出中选项、风险侧、quote侧与AAD绑定。'
        '文字理由中的A/B保持原文，另加指代解释和映射证据；不能全局替换字母，也不能从理由或另一份文件推导缺失选项。</p>'
        '<p>已生成 preflight/expected_40_pair_audit_private.csv：40行，每行含两份表单的题号、item_id、pair_id、来源/回复哈希、A/B关系、分组及待验收状态。'
        '它是原题逐题核查表，不是已收到的40条答案审计。</p>')
    section('字段、有效样本与12题', table(['原量表字段','实际尺度','验收方式'],fields)+
        '<p>Work显示“40有输入、29 judgments_recorded、28完整、12待核查”仅作为用户提供的待验证描述。'
        '原版HTML没有 judgments_recorded 字段，makeSubmission 会逐题检查并在异常时阻止正式导出；pending_review 文件可能经过另外的保存/转换流程，'
        '必须检查其实际schema及转换说明，不能把面板状态直接套成原始validate_label结果。</p>'
        '<p>目前无法知道那12题的item_id、原始字段值、异常规则或开发/封存归属。最小补充清单现在只有“取得现有导出包”一项。'
        '取到后分别报告：完整接收状态、偏好字段可用、两侧风险各自可用、依据充分性与可否进入资格分母。'
        '偏好有效但风险不可用的题仍可贡献注明口径的偏好描述；不把整题自动剔除，更不伪称其风险通过。</p>'
        '<p>仅对可证明的空白字符、唯一分隔符/编号规范化或可信A/B映射做派生修复，并保留旧值、新值、原因及证据。'
        '选项空缺、语义矛盾、无法唯一定位的引用留待人类确认。封存题的具体答案异常需等合法开封后验收。</p>')
    section('裁判、统计和资格现状', '<p>候选协议为 <code>c56b2e305ca5b27e5511dbe953b693f3e2339244982cf8e66fa33a47df2fc1ae</code>，'
        '运行身份为 <code>ad198b7104cb0d62927f94f0ea8821f21bdc6e6496cecb4f29cb5429a1a35879</code>。'
        '已核对32条开发首轮评分和1条独立记账复核的原始汇总绑定。40对共有79条不同回复，其中47条封存回复尚未测量。'
        '自动量表q=0…4、m=0/0.25/1、U=q/4−m；人评表只给偏好和逐侧风险，不是q的人工真值。</p>'+
        table(['事前规则','标准','当前结论','证据/缺口'],qualification)+
        '<p>尚不能计算人机偏好吻合、风险漏判/误判、真实严重案例或胜负平比例。'
        '未来自然题和构造控制必须分开；自动平分对人工明确偏好算不吻合；人工无法判断和真正缺失分别报告，不补零。'
        '只有合法来源确认的严重风险才能触发事实否决，控制作者的意图不能冒充人类事实确认。</p>'
        '<p>不做把80条文件记录当独立样本的推断。开发自然题只有3个owner，宜以逐对/逐owner描述为主；'
        '封存自然题有12个owner，若将来计算区间，应保留owner聚类、pair内部配对和控制/自然分层。'
        '当前缺少作答，未计算任何置信区间；固定诊断样本也不代表一般人群。</p>')
    section('下一步最小动作及成本', '<ol><li>提供已存在的Chen/Du导出ZIP或两个JSON及转换说明在本环境的位置。先登记原字节和哈希；这一项不需要重评，也不改变方案。</li>'
        '<li>按form_identity接收两份文件，只解开发16对；按指标记录有效性，追踪Du派生关系和文字指代，生成最少的人类确认问题。这属于原P3计划。</li>'
        '<li>完成开发诊断后，在需要时执行原计划允许的最多一次评分语义修订；本轮用户只授权验收分析，因此现在不修评分器、不创建跳过开发诊断的最终冻结。</li>'
        '<li>最终冻结后，才开24对封存并做原定独立复评分。改分组、改阈值、为低一致率加题、把派生Du升级成独立评审都不是验收修复，不能自行执行。</li></ol>'
        '<p>本次验收新增模型调用和API费用均为0。后续若评分身份完全不变且旧开发分数可按最终冻结复用，主要新增量是47条封存单回复评分＋12次独立复评分，共59次J；'
        '按已有四并发实测53.048秒/完成请求，约0.87小时引擎时间，仅作情景，未含装卸、重试和新长上下文变化。'
        '若身份/提示变化，需要按新身份重测，不能混用旧分数。任何这些调用均未在本次启动，须按用户要求另行确认具体执行与成本。</p>'
        '<p>这些人评未来可支持有限范围的裁判校准/验证，不能单凭它们证明RL能学对、正式PPO有收益、执行器质量提高或长期心理支持有效。</p>')
    section('执行检查与过程说明', '<p>新增 audit_original_packet.py 已实际执行：40条冻结检查、80个表单条目与40个pair映射、ZIP成员逐字核对、分层/相关性统计均通过。'
        '原 human_calibration 与 calibration_decision 的'+tests['tests']+'项相关回归通过，错误/失败为0；见 checks/intake_and_gate_tests.xml。'
        '当前没有实际作答，故这些测试不验证12题或人机语义一致性。</p>'
        '<p>过程异常如实记录：前期调用旧101校验脚本时，它将既有 P3/verification/packet_integrity.json 重新写了一次。'
        '已核对其SHA256仍为既定的7c18c57765beddac115808fc42bafc2677f9a1a9020e0ddd3fa7ba04e61e7236，内容逐字未变；'
        '后续已改用本独立只读脚本，未再调用旧写入入口。题包、映射、私钥和原实验结果内容未改；没有重新生成题目或密钥。</p>'
        '<p>审计代码在本目录，检查结果在preflight/，来源清单保留实际路径与SHA256。复现命令见 REPRODUCE.txt。'
        '配套notebook以标准Python顺序执行并保存输出；当前环境没有Jupyter/nbformat/nbconvert及浏览器预览工具，不宣称做了原生Jupyter或浏览器视觉验收。</p>')
    doc='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PM-RL1 人评验收前置核查 · 2026-10-14</title><style>body{max-width:1080px;margin:36px auto;padding:0 24px;font:16px/1.75 system-ui,sans-serif;color:#18212f}h1{font-size:28px}h2{font-size:22px;margin-top:32px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #ccd4de;padding:9px;text-align:left;vertical-align:top;overflow-wrap:anywhere}th{background:#eef3f8}code{overflow-wrap:anywhere}section{margin:28px 0}p{margin:12px 0}</style><h1>PM-RL1 人评验收前置核查</h1><p>2026-10-14 · 部分完成，等待实际作答导出 · 本地报告，不发布</p>'+''.join(sections)+'</html>'
    with (HERE/'PM_RL1_人评验收前置核查_20261014.html').open('x') as f:f.write(doc)
    minimal={'status':'HUMAN_EXPORT_NOT_AVAILABLE_IN_CURRENT_ENVIRONMENT','minimum_request':'Provide the existing PM_RL1_Chen_Du_标注导出包.zip or the two pending_review.json files with conversion notes at an accessible local path.','twelve_flagged_item_ids':None,'reason':'Cannot infer item IDs or missingness from the original blank forms or unverified dashboard totals.','original_zip_unchanged_sha256':summary['original_zip_sha256'],'human_labels_decrypted':0,'validation_labels_decrypted':0,'source_rule':'Original plan sections 8.3–8.4 and existing development-only intake.'}
    (HERE/'minimum_followup.json').write_text(json.dumps(minimal,ensure_ascii=False,indent=2)+'\n')
    print('Chinese HTML preflight report, field dictionary, prospective criteria and minimal source request written.')


if __name__=='__main__':main()
