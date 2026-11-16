#!/usr/bin/env python3
"""Read already-opened development notes; append analysis, never edit labels.

Manual qualitative interpretations are explicitly declared below. Checks verify
their quotations and bindings, not semantic truth. No decryption, key access,
model call, new human label, measurement freeze or qualification occurs here.
"""
import argparse
from collections import Counter
import csv
import hashlib
import html
import json
import os
from pathlib import Path
import subprocess


TEXT_FIELDS=('reason','uncertainty','quote_A','quote_B')
sha=lambda b:hashlib.sha256(b).hexdigest()


def read(p):
    return json.loads(p.read_text())


def dump(p,value):
    p.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def csv_write(p,rows):
    with p.open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader()
        for r in rows:w.writerow({k:json.dumps(v,ensure_ascii=False) if isinstance(v,(dict,list)) else v for k,v in r.items()})


INTERPRETATIONS={
 6:dict(kind='expression_and_logic_objection',extract='A更合适',
    existing_information='已明确偏好A，已填B=local，并指出B问法不自然、逻辑不对；不是未作答。',
    analyst_interpretation='文字重点是表达/问法是否合适；不足以唯一确定其local指事实预设错误还是支持质量。不得从偏好A推出A风险=0。',
    unresolved='A风险枚举没有明确记录；B的local与理由是否使用同一风险概念尚不明确。',
    action='保留偏好与原local，记录概念歧义；本轮不重复要求抄已存在的B引文。'),
 10:dict(kind='explicit_current_fact_error',extract='所以B错了应该',
    existing_information='已经写明A更合适、老板已辞职、因此B错误，并已选择B=severe。',
    analyst_interpretation='人工指出的具体事实能对应C:T000及B第一句；空source_ids表示编号未存入对应字段，不表示没有依据。',
    unresolved='A风险枚举没有明确记录；分析者整理的引用不能冒称评审亲手填入的原始字段。',
    action='自行整理回复引文与来源定位，另存分析注释；不要求重抄或再次选择已填的B严重程度。'),
 14:dict(kind='explicit_style_preference',extract='B的表达更舒服。',
    existing_information='preference=B，reason和quote_A都表达B更舒服；quote_A只是装入了补充评论。',
    analyst_interpretation='这是明确的表达偏好，能够作为人评使用；不能由未提事实问题推断两侧风险均为0。',
    unresolved='两侧风险等级未被明确表达；这不妨碍使用B偏好。',
    action='把quote_A中的内容另记为评论，保留原字段；不为格式重复请求这段话。'),
 15:dict(kind='explicit_subject_attribution_objection',extract='应该是和老朋友而不是和AI聊了的',
    existing_information='已明确指出老朋友/AI主体差异，并给出A更合适；判断对象和错误类型清楚。',
    analyst_interpretation='可与C:T005、C:T013和B的Talking with me对齐。严重程度没有明确选择，不能把“B错了”直接编码为severe。',
    unresolved='两侧风险等级未明确；错误是否属local还是severe不能由整理者补出。',
    action='自行对齐主体和来源，保留定性错误指认；暂不赋数值m，不让评审重复定位原文。'),
 16:dict(kind='explicit_narrative_uncertainty',extract='我无法判断这种回复是否贴切',
    existing_information='已引用两种回复的中文意思，说明交接场景与话术疑虑，并直接表示无法判断贴切性；不是空白题。',
    analyst_interpretation='在文字分析层记录“明确表达不确定”，不擅自写入preference=uncertain。原双severe仍保留，不能与文字中的不贴切自动视为同义。',
    unresolved='原pref为空；双severe究竟指事实/身份错误还是整体不适当，文字不能唯一确定。',
    action='按有实质作答但不支持确定胜方的记录保留；不催选A/B，不自动把双severe改为0。'),
 31:dict(kind='complete_with_source_disagreement',extract='并无实质差别',
    existing_information='偏好tie、双方none_detected与理由齐全，原本就是完整作答。',
    analyst_interpretation='前轮发现的计划/已完成差异是来源核查问题，不是漏填。原人评与协调者事实核查并列，不以“补齐”之名让人评改向裁判。',
    unresolved='若今后用于事实金标准，尚需来源裁决；当前可保留为人机/来源分歧案例。',
    action='撤出当前补填清单，保留已有事实分歧，原记录不改。'),
 35:dict(kind='complete_with_source_disagreement',extract='并无实质差别',
    existing_information='偏好tie、双方none_detected与理由齐全，原本就是完整作答。',
    analyst_interpretation='前轮完整来源核查发现job hunting缺少支持，是事实效度疑点；不能把它说成用户未完成这题。',
    unresolved='若今后用于事实金标准，尚需来源裁决；当前可保留为人机/来源分歧案例。',
    action='撤出当前补填清单，保留已有事实分歧，原记录不改。')}

# These English spans/IDs are ANALYST alignments to existing human notes.
# They are not translations supplied by the human, new labels, or an amendment
# to what the human originally entered in quote/source_ids.
ALIGNMENTS={
 10:dict(human_fields=['reason','quote_B'],human_span='老板辞职了',side='B',
         reply_span='Your boss has not resigned, and you will have to keep reporting to that same boss.',
         source_ids=['C:T000'],relation='The source says resigned; the candidate says not resigned.',
         human_severity_already_explicit='severe',proposed_new_human_severity=None),
 15:dict(human_fields=['reason','quote_B'],human_span='应该是和老朋友而不是和AI聊了的',side='B',
         reply_span='Talking with me helped you see your thesis from a different perspective.',
         source_ids=['C:T005','C:T013'],relation='The source names an old college friend; the candidate claims credit as me.',
         human_severity_already_explicit=None,proposed_new_human_severity=None)}


def html_table(headers,rows):
    e=lambda v:html.escape(str(v))
    return '<table><tr>'+''.join('<th>'+e(h)+'</th>' for h in headers)+'</tr>'+''.join('<tr>'+''.join('<td>'+e(v)+'</td>' for v in r)+'</tr>' for r in rows)+'</table>'


def run(repo,out):
    os.umask(0o077)
    old=repo/'project/outputs/pm_rl1/human_acceptance_20261014_v2'
    packet=repo/'project/outputs/pm_rl1/completion_20260930_v2/P3/calibration'
    paths=[old/'intake/development_item_audit_private.json',old/'intake/Du_AB_provenance_private.json',
        old/'intake/audit_receipt.json',old/'analysis/statistics.json',old/'minimum_followup_private.json',
        packet/'rater_1_form.json',packet/'rater_1_map_private.json',packet/'rater_2_map_private.json',
        repo/'project/src/metacom_pm/rl1/calibration_form.html',repo/'project/src/metacom_pm/rl1/human_calibration.py']
    hashes={str(p):sha(p.read_bytes()) for p in paths}
    old_files={r['path']:r['sha256'] for r in read(old/'FILES.json')}
    for p in paths:
        if p.is_relative_to(old):assert sha(p.read_bytes())==old_files[str(p.relative_to(old))]
    form=read(packet/'rater_1_form.json');mapping=read(packet/'rater_1_map_private.json')
    form_items={i['item_id']:i for i in form['items']}
    all_rows=read(old/'intake/development_item_audit_private.json')
    assert len(all_rows)==32 and all(r['group']=='development' for r in all_rows)
    rows=sorted((r for r in all_rows if r['slot']=='rater_1'),key=lambda r:r['order'])
    assert len(rows)==16 and len({r['pair_id'] for r in rows})==16
    du=read(old/'intake/Du_AB_provenance_private.json')
    assert len(du)==16 and all(r['derived_fields_match'] and r['free_text_reference_frame']=='Chen/rater_1' for r in du)
    decoded=[];source_alignments=[];misplaced=[]
    for r in rows:
        label=r['label'];item=form_items[r['item_id']];meta=mapping[r['item_id']]
        assert meta['group']=='development' and r['pair_id']==meta['pair_id']
        assert r['prefix_identity']==item['source_key']
        text_evidence=[dict(field=f,text=label[f]) for f in TEXT_FIELDS if label[f].strip()]
        assert text_evidence
        interpretation=INTERPRETATIONS.get(r['order'],dict(kind='explicit_tie_with_reason',extract=label['reason'],
            existing_information='有原始偏好和理由，风险字段齐备。',analyst_interpretation='保留原评价；文字内容可用于解释相当判断。',
            unresolved='没有新增字段问题；形式完整不等于事实金标准。',action='不要求重复作答。'))
        assert any(interpretation['extract'] in x['text'] for x in text_evidence)
        for side in 'AB':
            q=label['quote_'+side]
            if q and q not in item[side]:
                misplaced.append(dict(Chen_order=r['order'],item_id=r['item_id'],original_field='quote_'+side,
                    original_text=q,analysis_location='annotation_notes',raw_field_changed=False,
                    evidence_type='source_paraphrase' if r['order']==10 else 'reviewer_comment'))
        decoded.append(dict(Chen_order=r['order'],item_id=r['item_id'],pair_id=r['pair_id'],group='development',
            raw_label=label,raw_strict_valid=r['strict_valid'],has_written_assessment=bool(text_evidence),
            text_evidence=text_evidence,**interpretation,
            formal_preference=label['preference'],formal_risk_A=label['risk_A'],formal_risk_B=label['risk_B'],
            narrative_uncertainty_present='我无法判断这种回复是否贴切' in label['reason'],
            analyst_coding_only=True,human_label_replaced=False))
        if r['order'] in ALIGNMENTS:
            spec=ALIGNMENTS[r['order']]
            assert all(spec['human_span'] in label[f] for f in spec['human_fields'])
            assert spec['reply_span'] in item[spec['side']]
            source=form['sources'][item['source_key']]
            turn_map={t['id']:t for t in source['current_prefix']}
            for session in source['legal_past_sessions']:
                turn_map.update({t['id']:t for t in session['turns']})
            cited=[turn_map[k] for k in spec['source_ids']]
            source_alignments.append(dict(Chen_order=r['order'],item_id=r['item_id'],pair_id=r['pair_id'],**spec,
                human_original_statements={f:label[f] for f in spec['human_fields']},
                sources=cited,source_identity=item['source_key'],reply_sha256=sha(item[spec['side']].encode()),
                alignment_author='assistant_research_coordinator',human_original_source_ids=label['source_ids'],
                raw_label_mutated=False,formal_gold_authorized=False,
                method='Manual semantic alignment followed by exact raw-span/source-ID checks; not a machine translation equality test'))
    stats=read(old/'analysis/statistics.json')
    summary=dict(scope='development_notes_reanalysis',user_statement='双方40题均已完成，许多内容写在备注；界面可能有问题。',
        user_statement_provenance='Latest user message; not an independently verified statement about sealed contents',
        development_pairs_reviewed=len(decoded),development_pairs_with_written_assessment=sum(x['has_written_assessment'] for x in decoded),
        development_blank_assessment_pairs=sum(not x['has_written_assessment'] for x in decoded),
        original_structured_preferences_present=sum(x['formal_preference'] in ('A','B','tie','uncertain') for x in decoded),
        original_comparable_preferences=stats['totals']['preference_pairs'],
        additional_explicit_narrative_uncertainty=sum(x['narrative_uncertainty_present'] for x in decoded),
        strict_valid_unchanged=sum(x['raw_strict_valid'] for x in decoded),
        human_explicit_numeric_risk_choices=stats['totals']['risk_enum_sides'],
        explicit_risk_severity_missing_slots=[dict(Chen_order=x['Chen_order'],item_id=x['item_id'],field='risk_'+s) for x in decoded for s in 'AB' if x['raw_label']['risk_'+s]==''],
        misplaced_nonliteral_quote_fields=len(misplaced),source_linked_existing_written_objections=len(source_alignments),
        risk_with_existing_explicit_severe_and_reconstructed_source=1,
        above_reconstructed_sources_are_analyst_notes_not_formal_human_intake=True,
        inspected_original_record_sets=1,derived_copy_record_sets=1,Du_AB_reference='Chen original form; unchanged',
        validation_pairs_sealed=24,validation_human_contents_read_this_turn=0,
        decryption_calls_this_turn=0,private_key_access_this_turn=False,
        human_label_mutations=0,formal_risk_imputations=0,formal_preference_imputations=0,
        model_calls=0,API_usd=0,training_updates=0,reward_qualified=False,
        current_repeat_annotation_requests=[],
        prior_seven_item_request_disposition='Superseded as a mandatory blanket refill request; do not discard substantive uncertainty or factual disagreements',
        formal_intake_disposition='Not completed by this notes audit; original validator and qualification rules unchanged',
        platform_bug='Not established; actual Chinese assisted UI implementation/translation snapshot not present in supplied ZIP',
        repository_HEAD=subprocess.check_output(['git','-C',str(repo),'rev-parse','HEAD'],text=True).strip())
    assert summary['development_pairs_with_written_assessment']==16
    assert summary['original_comparable_preferences']==15 and summary['additional_explicit_narrative_uncertainty']==1
    assert summary['strict_valid_unchanged']==11 and len(summary['explicit_risk_severity_missing_slots'])==6
    assert summary['misplaced_nonliteral_quote_fields']==3
    assert [x['Chen_order'] for x in source_alignments]==[10,15]
    assert all(x['raw_label']==next(r['label'] for r in rows if r['item_id']==x['item_id']) for x in decoded)
    out.mkdir(exist_ok=False)
    dump(out/'summary.json',summary);dump(out/'notes_reconciliation_private.json',decoded)
    dump(out/'analyst_source_alignments_private.json',source_alignments);dump(out/'misplaced_notes_private.json',misplaced)
    csv_write(out/'开发16题_备注释读.csv',[dict(题号=x['Chen_order'],题目ID=x['item_id'],原偏好=x['formal_preference'],原风险A=x['formal_risk_A'],原风险B=x['formal_risk_B'],原理由=x['raw_label']['reason'],现有信息=x['existing_information'],释读=x['analyst_interpretation'],仍未明确=x['unresolved'],当前处理=x['action']) for x in decoded])
    dump(out/'request_disposition.json',dict(supersedes=str(old/'minimum_followup_private.json'),
         current_user_action_required=[],original_requests_6_10_14_15_16='Read existing notes first; remove requests to restate reasons or manually copy locatable citations. Retain numerical ambiguity explicitly.',
         original_requests_31_35='Already completed records; keep source-disagreement cases, not mandatory missing-answer replacements.',
         future_formal_numeric_constraint='Six blank risk enums and identity-item field/meaning ambiguity are not silently imputed. If a formal decision requires them, ask only that concrete issue together, never the whole questionnaire again.',
         means_formal_intake_passed=False))
    body=[]
    body.append('<h1>人评备注复核：已作答与字段完整必须分开</h1><p><b>复核结论：已打开的开发16题全部有实质文字作答，空白题为0。15题有可比较偏好；第16题虽然选择框为空，理由已明确表达“我无法判断这种回复是否贴切”。此前把7题补充清单整体当作继续工作的前置条件，处理过于机械，本轮撤回这一要求。</b></p>')
    body.append('<p>用户声明双方40题全部完成，许多信息写在备注。本报告将该声明完整登记；24题封存内容仍未查看，不能冒称已逐题核实40题。只读取上轮已经解密的开发答案，不碰密钥或重新解密。日期：2026-10-14。</p>')
    body.append('<h2>1. 已写在备注里的信息</h2>')
    body.append(html_table(['Chen题号','原文信息','现在的处理'],[[x['Chen_order'],x['existing_information'],x['action']] for x in decoded if x['Chen_order'] in (6,10,14,15,16)]))
    body.append('<p>原导出里没有另一个独立“备注”键；文字集中在 reason、uncertainty、quote_A、quote_B。后两个框在原程序中被要求必须是候选回复的精确原句。中文来源说明或评价意见被放入这里，会触发格式失败；该失败不说明人没有看题或没有作出判断。</p>')
    body.append('<h2>2. 已自行补齐分析层的来源定位</h2>')
    for x in source_alignments:
        body.append('<h3>第'+str(x['Chen_order'])+'题 · '+html.escape(x['item_id'])+'</h3>')
        body.append('<p>原人工理由：'+html.escape(x['human_original_statements']['reason'])+'</p>')
        body.append('<p>对应B回复原句：<code>'+html.escape(x['reply_span'])+'</code></p>')
        for t in x['sources']:body.append('<p>来源 <code>'+html.escape(t['id'])+'</code>：'+html.escape(t['text'])+'</p>')
    body.append('<p>第10题的人类原始选择已是 severe；来源和错误句可以定位，不能再概括为“没有任何风险依据”。第15题明确指出主体归属问题，也有可核对来源，但并未明确 local/severe，因此不代填等级。这里增加的是分析者对原备注的出处整理，不是生成新的人类答案；原JSON没有任何改动，也没有设置 human_fact_adjudication/source_confirmed 来冒充人类签认。</p>')
    body.append('<h2>3. 哪些数字需要纠正，哪些保持不变</h2>')
    body.append(html_table(['维度','此次结论'],[
      ['开发题是否作答','16/16有实质文字；0题完全空白。'],
      ['偏好信息','15题原选择可比较；另1题在备注明确表示无法判断贴切性。文字分析登记该不确定，不擅改原preference空值。'],
      ['原程序全字段校验','仍为11/16，不将文字分析包装成原校验已通过。'],
      ['风险数值选项','仍为26/32侧；6个空风险字段没有明确等级，不能靠“偏好另一侧”推出0。'],
      ['引文框中的额外信息','第10、14、15题3处为来源说明/评论，已另存注释，未删除原文。'],
      ['事实依据的内容','第10、15题共2处明确人工指认可对齐来源；其中第10还已有人工severe选择。'],
      ['严格完整风险与语义证据','旧22/32是字段规则口径，不代表只有这些侧面有可读信息。新增来源注释不并入该分母，也不虚报召回率。'],
      ['自然偏好与裁判','仍为5/8吻合；备注复核没有把原人评改向裁判，也没有重新计算一组更好看的数字。'],
      ['Du及封存','Du仍是派生副本；24题仍封存；不新增独立样本。']]))
    body.append('<h2>4. 这批备注对研究说明了什么</h2>')
    body.append('<p>第6、14题主要关注回复是否自然、逻辑和情感表达是否合适；这本身就是支持适当性的有用证据，不能因为没有标准来源编号就丢掉。第10、15题能明确指认时态/主体问题，说明人工材料并非只有笼统的好坏感受。第16题提出了新AI接手旧对话时话术是否自然的真实疑问，即使两句有不同的身份真实性，评审仍可能觉得两者都不适合部署；这一意见应同时保留在支持质量分析中。</p>')
    body.append('<p>风险选项和文字意见目前有混用迹象：“严重不贴切”与“严重身份/事实错误”未必同义。原量表q与m也不假定正交，因此不能强行把某句完全归入单一类别；需要在现有备注中区分评审实际指认的内容，并把无法确定的等级保持未知。这揭示的是人类意见与机器量表对接的问题，不是要求评审重新做整套题。</p>')
    body.append('<p>第31、35题本来字段齐全，前轮提出的是与来源核查的分歧，不是漏答。现在保留原tie/none和该分歧，不把改变人评作为当前继续分析的条件；但在正式用它们证明事实判定可靠之前，仍不能忽略来源冲突。评论复核既不证明裁判全错，也不证明人工所有判断无误。</p>')
    body.append('<h2>5. 平台是否有问题</h2>')
    body.append('<p>已确认的是信息分散在文本框、原校验只认指定字段，以及导出包含中文辅助界面版本说明 pmrl1-zh-assist-v1。当前ZIP没有附该辅助页面的代码、译文快照或浏览器保存日志，无法定位是否发生选择未保存、界面提示歧义或导出损失。不能据此断言平台有程序bug，也不能据此归咎于人工漏填。40 entered/29 judgments_recorded/28 complete/12 pending仍只是原界面状态。</p>')
    body.append('<h2>6. 更新后的下一步</h2>')
    body.append('<p><b>现在无需重填7题或重新做人评。</b>已有偏好、定性错误指认、不能判断的原因和表达意见已经整理为独立释读层。引用定位由分析侧完成；原始人工记录保持不变。本轮不新增必须回复的问题。</p>')
    body.append('<p>还未完成的是正式数值接收与奖励资格：6个风险空值、原第16题双severe与文字含义的关系不能凭空补齐。若后续某项具体资格判断确实依赖它们，只集中确认必要的等级/含义，不重复请求已经写清的理由或要求再次复制原文。这是保留真实测量边界，不代表你们没有完成标注。未修改量表、阈值、核心接收器或数据划分，未创建最终冻结、未打开封存集、未训练或调用API。</p>')
    body.append('<p>前轮7题文件保留作为历史记录，当前安排以本报告及 <a href="request_disposition.json">request_disposition.json</a> 为准。其必要事实疑点没有删除，只撤回“一律补填完7题才能继续”的工作安排。</p>')
    body.append('<p>逐题释读：<a href="开发16题_备注释读.csv">CSV</a> / <a href="notes_reconciliation_private.json">完整JSON</a>；来源对齐：<a href="analyst_source_alignments_private.json">证据JSON</a>；统计：<a href="summary.json">summary.json</a>。脚本是显式的人工语义编码清单加机械引用校验，不宣称算法从备注自动推导正确答案。</p>')
    style='body{max-width:1040px;margin:32px auto;padding:0 24px;font:16px/1.8 system-ui;color:#182331}table{border-collapse:collapse;width:100%;font-size:14px}td,th{border:1px solid #ccd6e0;padding:10px;text-align:left;vertical-align:top}th{background:#eff5fa}code{overflow-wrap:anywhere}h2{margin-top:32px}a{color:#155f9c}'
    doc='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>PM-RL1 人评备注复核与更正</title><style>'+style+'</style><body>'+''.join(body)+'</body></html>'
    (out/'PM_RL1_人评备注复核与更正_20261014.html').write_text(doc)
    checks=dict(input_hashes_unchanged=all(sha(Path(p).read_bytes())==v for p,v in hashes.items()),
        raw_labels_identical=True,exact_alignment_checks_passed=2,source_spans_verified=3,
        development_only_guard=True,original_strict_counts_unchanged=True,old_analysis_statistics_unchanged=True,
        no_new_crypto_calls=True,no_private_key_read=True,no_formal_label_imputation=True,
        git_status=subprocess.check_output(['git','-C',str(repo),'status','--short'],text=True))
    assert checks['input_hashes_unchanged'] and checks['git_status']==''
    dump(out/'CHECKS.json',checks)
    dump(out/'input_manifest.json',dict(files=[dict(path=p,sha256=v) for p,v in hashes.items()],
        user_correction='All forty pairs were completed; substantial information entered in free text; possible interface issue.',
        analyst_interpretations_provenance='INTERPRETATIONS and ALIGNMENTS in reconcile_notes.py; exact quotations checked against already-decrypted development only'))
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',type=Path,required=True);p.add_argument('--out',type=Path,required=True)
    a=p.parse_args();run(a.repo,a.out)
