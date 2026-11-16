"""Offline, exclusive-create confirmation views of frozen inputs; never user answers."""
from pathlib import Path
from decimal import Decimal as D
import json
import hashlib
import html
import os

os.umask(0o077)
P = Path(__file__).resolve().parent
OLD = P.with_name('relation_reference_preparation_20261021_v1')
read = lambda f: json.loads((P/f).read_text())
sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
def save(name, value):
    path=P/name;path.parent.mkdir(parents=True,exist_ok=True)
    content=value if isinstance(value,str) else json.dumps(value,ensure_ascii=False,indent=2)+'\n'
    if path.exists():
        assert path.read_bytes()==content.encode(), 'Never overwrite a changed prepared record'
        return
    with path.open('x') as f:
        f.write(content)

protocol=read('protocol.json');items=read('inputs_private.json');refs=read('references.json')
review=read('REFERENCE_REVIEW_PENDING.json');budget=read('budget.json')
reserve=D('0.786432');opening=D(budget['current_trial_usd']);mean=D(budget['history_mean_per_call_usd'])
rows=[];outbounds={}
for key,item in items.items():
    a=read('payloads/'+key+'__A.json');b=read('payloads/'+key+'__B.json')
    prefix=a['messages'][0]['content'];full=b['messages'][0]['content']
    assert full.startswith(prefix) and a['messages'][1]==b['messages'][1]
    suffix=full[len(prefix):]
    save('outbound_added/'+key+'.txt',suffix)
    outbounds[key]=dict(bytes=len(suffix.encode()),sha256=sha(P/'outbound_added'/ (key+'.txt')),
        exact_system_suffix=suffix,parsed=json.loads(suffix.split('\n',3)[3]))
for slot in protocol['schedule']:
    payload=read('payloads/'+slot['item_key']+'.json')
    # Same byte-screen serialization as existing validate_payload, not a provider tokenizer.
    n=len(json.dumps(payload['messages'],ensure_ascii=False,separators=(',',':')).encode())
    estimate=D(n+8192)*D('.30')/1000000+D(73327)/12*D('1.20')/1000000
    rows.append(dict(position=slot['position'],item_key=slot['item_key'],repetition=slot['repetition'],
        serialized_bytes=n,input_byte_screen_plus_historical_output_usd=str(estimate)))
def simulate(costs,stage,trial):
    spent=D(0);started=0;stop=None
    for index,c in enumerate(costs,1):
        if spent+reserve>stage or opening+spent+reserve>trial:
            stop=index;break
        spent+=c;started+=1
    return dict(started=started,first_undispatched_position=stop,settled_usd=str(spent),
        not_a_probability_or_forecast=True)
scenarios={
    'historical_mean':[mean]*28,
    'twice_historical_mean':[2*mean]*28,
    'actual_input_byte_screen_plus_historical_output':[D(x['input_byte_screen_plus_historical_output_usd']) for x in rows],
    'every_call_uses_full_reserve':[reserve]*28,
}
tail=dict(status='OFFLINE_PLANNING_ONLY',current_trial_usd=str(opening),unsettled_usd='0',
    reserve_usd=str(reserve),all_28_native_reserves_usd=str(reserve*28),
    formula='Before dispatch: settled stage cost + existing unresolved liabilities + next reservation <= stage cap; opening trial cost + same <= trial cap; shared/account guards also bind.',
    old=dict(stage='1.25',trial='2.40',stage_settled_ceiling=str(D('1.25')-reserve),trial_settled_ceiling=str(D('2.40')-opening-reserve)),
    proposed=dict(stage='2',trial='3.15',stage_settled_ceiling=str(D('2')-reserve),trial_settled_ceiling=str(D('3.15')-opening-reserve)),
    scenarios={k:dict(old=simulate(v,D('1.25'),D('2.40')),proposed=simulate(v,D(2),D('3.15'))) for k,v in scenarios.items()},
    per_slot_planning=rows,price_basis='Existing official table: input cache miss USD0.30/M, output USD1.20/M; fresh startup verification required, no online request performed.',
    exact_tokenizer=False,probability_of_tail_stop=None,approval=False)
assert sum(D(x['input_byte_screen_plus_historical_output_usd']) for x in rows)==sum(D(x['estimated_total_using_historical_output_usd']) for x in budget['actual_input_byte_screens'].values())
save('BUDGET_TAIL_CHECK.json',tail)
save('OUTBOUND_ADDED_MANIFEST.json',{k:{kk:vv for kk,vv in v.items() if kk not in ('exact_system_suffix','parsed')} for k,v in outbounds.items()})

e=items['dev06B']['evidence'];evidence_sections=[('当前对话 '+e['current_date'],e['current_prefix'])]+[(s['id']+' 合法历史 '+s['date'],s['turns']) for s in e['legal_past_sessions']]
full=['R1 / dev06B — 完整原始来源；无省略、无模型生成补充。','reply identity: '+protocol['schedule'][0]['reply_identity'],'evidence identity: '+protocol['schedule'][0]['evidence_identity'],'','完整待评回复',items['dev06B']['reply'],'']
for label,turns in evidence_sections:
    full += [label]+[f"[{t['id']}] {t['role']}\n{t['text']}\n" for t in turns]
save('R1_COMPLETE_SOURCES_EN.txt','\n'.join(full))

E=html.escape
parts=['''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>PM-RL1：三项来源复核与启动确认（待批）</title><style>
body{font:17px/1.7 system-ui,sans-serif;color:#203044;background:#f5f7fa;margin:0}main{max-width:1050px;margin:auto;padding:32px;background:white}h1,h2,h3{line-height:1.3}h2{border-top:2px solid #b4c7dc;padding-top:20px;margin-top:38px}a{color:#145c9f}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f5f9;padding:15px;font:14px/1.6 monospace}table{border-collapse:collapse;width:100%;font-size:15px}td,th{border:1px solid #bdcad8;padding:9px;text-align:left;vertical-align:top}.turn{border-left:3px solid #cad7e4;padding:9px 15px;margin:10px 0}.key{background:#fff2cd;border-left-color:#b97710}.note{background:#eef5fc;padding:16px}summary{cursor:pointer;font-weight:bold}blockquote{border-left:4px solid #a9bfd5;padding:8px 18px;margin:14px 0}small{color:#4c6075}@media print{body{background:white}main{padding:0}pre{font-size:10px}details{display:block}}
</style><main><h1>三项来源复核与启动确认</h1><p class="note">待真实复核与明确启动批准。本页没有代填答案，没有发送请求。累计仍225次；本页是预算余量修订，不扩大实验。</p>''']
parts.append('<p>新协议：<code>'+E(protocol['identity'])+'</code><br>参照哈希：<code>'+E(protocol['reference_bundle_sha256'])+'</code></p>')
parts.append('<nav><a href="#r1">R1完整来源</a> · <a href="#r2">R2局部问句</a> · <a href="#r3">R3行动控制</a> · <a href="#money">预算</a> · <a href="#outbound">B新增外传</a> · <a href="#confirm">一次确认范围</a></nav>')
parts.append('<h2 id="r1">R1：具体行动与来源是否匹配</h2><p>你此前已说明该问句预设谈话发生，这项不重问。本次只核对：完整记录能否支持<strong>已经和母亲谈过她的交友限制给自己带来的感受</strong>。当前争论、旧旅行争论及后续沟通建议是否对应这个具体行动，由你判断。未找到支持不等于现实中绝未发生，也不确定严重度。</p>')
parts.append('<h3>完整待评回复 dev06B</h3><pre>'+E(items['dev06B']['reply'])+'</pre>')
parts.append('<p>对应读法：最后一句问“你是否发现，和她谈这些规定给你的感受，有助于平息愤怒；还是通常会让争论升级？”这里只帮助定位；以完整英文为准。</p>')
parts.append('<p>重点原文位置：<a href="#R1-C:T007">C:T007交友争论</a>；<a href="#R1-H002:T004">H002:T004旅行主题</a>；<a href="#R1-H002:T008">H002:T008–010尝试沟通及回应</a>；<a href="#R1-H002:T021">H002:T021–022谈感受的建议</a>。以下完整展示10轮当前对话和两段57轮历史，不只摘有利句子。supporter指原记录中的支持者，不自动等同当前AI。</p>')
highlight={'C:T007','C:T008','C:T009','H002:T004','H002:T008','H002:T009','H002:T010','H002:T021','H002:T022','H002:T023','H002:T024','H002:T026'}
for label,turns in evidence_sections:
    parts.append('<h3>'+E(label)+f'（{len(turns)}轮）</h3>')
    for t in turns:
        parts.append(f'<div class="turn {"key" if t["id"] in highlight else ""}" id="R1-{E(t["id"])}"><strong>{E(t["id"])} · {"用户 seeker" if t["role"]=="seeker" else "原支持者 supporter"}</strong><div class="source-original">{E(t["text"])}</div></div>')
parts.append('<p class="note">R1待答：'+E(review['groups']['R1_specific_action_match']['question'])+'<br><strong>你的答案：尚未提供。</strong>可确认、指出支持的具体位置，或保留不确定；不要求同意草案。</p>')

parts.append('<h2 id="r2">R2：只确认局部关系，不认证整条回复</h2><p>以下五处是在问“有没有谈过”或邀请探索，并非询问“已完成某次特定谈话后的效果”。请核对这一局部关系说明。06A与母亲RS仍保留身份澄清问题；确认这些问句不代表m=0、q=4或整条回复无问题。</p>')
for key in review['groups']['R2_open_question_mapping']['materials']:
    c=refs[key]['claims'][0]
    parts.append('<h3>'+E(key)+'</h3><p>局部原文：<strong>'+E(c['response_quote'])+'</strong></p><pre>'+E(items[key]['reply'])+'</pre><p>关系草案：'+E(c['analyst_interpretation'])+'</p><p>限制：'+E(c['limitations'])+'</p>')
    for s in c['source_checks']:
        parts.append('<blockquote>'+E(s['source_id']+' / '+s['speaker'])+'<br>'+E(s['quote'])+'</blockquote>')
parts.append('<p class="note">R2待答：'+E(review['groups']['R2_open_question_mapping']['question'])+'<br><strong>你的答案：尚未提供。</strong>若不同意，可只指出哪一处。</p>')

parts.append('<h2 id="r3">R3：有支持的行动，不扩大到结果已完成</h2><h3>完整回复 dev108_OFF</h3><pre>'+E(items['dev108_OFF']['reply'])+'</pre>')
for s in refs['dev108_OFF']['claims'][0]['source_checks']:
    parts.append('<blockquote>'+E(s['source_id']+' / '+s['speaker'])+'<br>'+E(s['quote'])+'</blockquote>')
parts.append('<p>局部草案：C:T007明确报告减少饮酒，可为“正在采取挽救婚姻的步骤”提供行动依据；不能证明婚姻已挽救或已彻底戒酒。此项不判定“很高兴能帮到你”等其他部分，也不指定q/m。</p><p class="note">R3待答：'+E(review['groups']['R3_supported_action_control']['question'])+'<br><strong>你的答案：尚未提供。</strong></p>')

parts.append('<h2 id="money">最终预算修订：只准备，不启用</h2><p>本阶段实际费用＋未结责任上限拟改为<strong>$2</strong>；API试验累计线拟改为<strong>$3.15</strong>；共享$20不变。28次、累计253、容量317及其他守卫不变。容量317仍待启动批准后启用，当前活动容量289。</p><p>当前API试验保守记账$1.1189538，未结责任0。每条派发前仍预留$0.786432；完整usage确认后才释放未用部分。串行不意味着无需为下一条保留完整责任。</p>')
parts.append('<table><tr><th>项目</th><th>旧待批版</th><th>新待批版</th></tr><tr><td>新增费用＋责任上限</td><td>$1.25</td><td>$2</td></tr><tr><td>API累计线</td><td>$2.40</td><td>$3.15</td></tr><tr><td>可发下一条时，之前阶段已结费用上界（无其他未结）</td><td>$0.463568</td><td>$1.213568</td></tr><tr><td>累计线对应的上界</td><td>$0.4946142</td><td>$1.2446142</td></tr></table><p>本阶段上限更紧。若要发第28条，前27条实际费用之和须不超过对应上界，且账户/并发责任等守卫也满足。增加$0.75余量，不增加调用，也不授权花满。</p>')
parts.append('<table><tr><th>固定费用情景（非预测）</th><th>旧版可派发</th><th>新版可派发</th></tr>')
labels={'historical_mean':'每条均为历史均值 $0.0106715','twice_historical_mean':'每条均为两倍历史均值 $0.021343','actual_input_byte_screen_plus_historical_output':'实际输入字节筛查＋历史输出均值，按固定槽位顺序','every_call_uses_full_reserve':'每条均用满 $0.786432 最坏预留'}
for key,v in tail['scenarios'].items():
    parts.append('<tr><td>'+E(labels[key])+'</td><td>'+str(v['old']['started'])+'/28</td><td>'+str(v['proposed']['started'])+'/28</td></tr>')
parts.append('</table><p>输入字节情景总额约$0.5087116，历史均值情景约$0.298802；均不是精确tokenizer或账单。无法据这些情景估计尾停概率。28条全部用满预留合计$22.020096，故新$2上限也不能保证完成。usage不明则保留全额责任并硬停，不用后续余额猜测释放。</p><p>计价沿用已落盘官方依据：未命中输入$0.30/百万token，输出$1.20/百万token；真实启动必须重查，变化即停。本轮没有查账户或公开服务。若恰好花满阶段$2，累计为$3.1189538，仍低于拟议$3.15。</p>')

parts.append('<h2 id="outbound">B实际新增外传内容</h2><p>接收方仅DeepSeek官方 <code>https://api.deepseek.com/chat/completions</code>，用途仅固定28槽。A/B共用同一Flash/high服务；启动前核验既有服务身份。以下为B在原system末尾新增的<strong>真实内容</strong>，不是另拟样例；完整user消息、来源、回复及schema不变。12份不同附加内容用于14个B槽，06B与04B各重复一次。</p><p>新增字段包含：版本及绑定哈希、回复具体主张/预设、人物/行动/阶段/时间、来源关系与逐字引文、研究者已明确解释的有限英文整理、分析者关系草案和限制。确有人工解释及复核性质内容，需单独批准外传。没有预期q/m、整体偏好、资源赢家或期望收益方向；不发送原始人评表、研究者身份/备注、其他候选结果、封存材料或凭据文件。原合法来源内已有名字保留，不作“整份输入绝无姓名”的承诺。</p><p>未决关系仍标分析者草案；你的复核只支持有界参照，不变成独立金标。若真实答案要求改表，需先留存差异并更新绑定，不可悄悄替换这里的待批内容。</p>')
parts.append('<h3>公共辅助说明（所有B相同）</h3><pre>'+E(next(iter(outbounds.values()))['parsed']['reference_use_contract'])+'</pre>')
for key,v in outbounds.items():
    parts.append('<details><summary>'+E(key)+'：查看实际新增关系JSON（'+str(v['bytes'])+'字节）</summary><p>精确附加文本SHA256：<code>'+v['sha256']+'</code></p><pre>'+E(json.dumps(v['parsed']['relation_reference'],ensure_ascii=False,indent=2))+'</pre></details>')

parts.append('<h2 id="confirm">只需集中回复这几项</h2><p>R1、R2、R3请按上述限定范围提供真实答案，可保留未知或指出不同意处，不重新评分。不把你的计划认可代填为三项确认。</p><p>三项答案之外，是否明确批准<strong>本页协议 '+E(protocol['identity'][:12])+'</strong>：最多28次／累计253／容量317；新增费用与责任$2／API累计$3.15／共享$20；所列B新增内容及原合法评分输入发往同一官方服务；指定凭据届时仅进程读取；GET /models、GET /user/balance各一次；采用既定诊断派发政策。</p><p>语义错误/复核歧义作为结果继续；模型unknown保留缺测。身份/来源/服务异常、技术失败、截断、usage或责任不明、预算不足均硬停；无自动重试。旧STOP保留。完成或硬停后提交全部28槽状态和既定分支结论，不自动进入C、训练、验收或追加抽样。</p><p class="note">启动决定：尚未提供。当前所有待批记录仍为PENDING，合同未启用，新增真实评分0。</p></main></html>')
save('FINAL_CONFIRMATION_ZH.html','\n'.join(parts))
save('BUDGET_REVISION_RECEIPT.json',dict(status='PREPARED_NOT_AUTHORIZED',previous_protocol=protocol['previous_protocol_identity'],
    new_protocol=protocol['identity'],references_unchanged=sha(P/'references.json')==sha(OLD/'references.json'),
    schedule_unchanged=sha(P/'schedule.json')==sha(OLD/'schedule.json'),payloads_unchanged=all(sha(f)==sha(OLD/'payloads'/f.name) for f in (P/'payloads').glob('*.json')),
    review_answers=None,new_calls=0,contract_applied=False,tail_check_sha256=sha(P/'BUDGET_TAIL_CHECK.json'),
    confirmation_sha256=sha(P/'FINAL_CONFIRMATION_ZH.html')))
print(json.dumps({'tail_scenarios':tail['scenarios'],'source_turns':sum(len(ts) for _,ts in evidence_sections),'outbound_unique':len(outbounds)},ensure_ascii=False,indent=2))
