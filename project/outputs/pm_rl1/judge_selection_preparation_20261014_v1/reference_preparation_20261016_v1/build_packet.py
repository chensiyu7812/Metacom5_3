"""One-off offline document preparation. No runner imports, scoring or submissions."""
from pathlib import Path
from collections import Counter
import ast, hashlib, html, json, re

O=Path(__file__).resolve().parent; B=O.parent; R=B.parents[3]
P3=R/'project/outputs/pm_rl1/completion_20260930_v2/P3'
sources={}
def sha(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for chunk in iter(lambda:f.read(65536),b''):h.update(chunk)
    return h.hexdigest()
def read(p):
    p=Path(p).resolve();sources[str(p)]=sha(p);return json.loads(p.read_text())
def save(p,j):
    with Path(p).open('x') as f:json.dump(j,f,ensure_ascii=False,indent=2);f.write('\n')
def digest(j):return hashlib.sha256(json.dumps(j,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def literal(path,name):
    sources[str(path)]=sha(path)
    for node in ast.parse(path.read_text()).body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id==name for t in node.targets):return ast.literal_eval(node.value)
    raise ValueError(name)
def static_html_prefix(path):
    # Stop before the embedded form-data payload; no mixed question array is read.
    out=[];marker='<script id="form-data"'
    with path.open() as f:
        while True:
            c=f.read(1)
            if not c:raise ValueError('missing safe boundary')
            out.append(c)
            if ''.join(out[-len(marker):])==marker:return ''.join(out[:-len(marker)])

plan=read(B/'plan.json');keys=['dev04A','dev04B','dev06A','dev06B','dev07A','dev15B','dev16A','dev35B']
contexts={};items=[];mapping=[]
for i,key in enumerate(keys,1):
    x=plan['items'][key];assert x['split']=='development' and digest(x['evidence'])==x['evidence_identity']
    cid=next((k for k,v in contexts.items() if digest(v)==x['evidence_identity']),None)
    if cid is None:cid=f'context_{len(contexts)+1:02}';contexts[cid]=x['evidence']
    item=dict(item_id=f'P{i:02}',reply=x['reply'],reply_identity=digest(x['reply']),evidence_identity=x['evidence_identity'],context_id=cid)
    items.append(item);mapping.append(dict(item_id=item['item_id'],old_item_key=key,pair_id=x['pair_id'],origin_job_id=x['origin_job_id'],prefix_index=x['prefix_index'],kind=x['kind'],owner=x['owner'],context_id=cid,reply_identity=item['reply_identity'],evidence_identity=item['evidence_identity']))
assert len(contexts)==4
assert items[4]['context_id']==items[0]['context_id'] and items[4]['evidence_identity']==items[0]['evidence_identity']
role=literal(R/'project/src/metacom_pm/rl1/judge_completion.py','ROLE_CONTRACT')
semantic=literal(R/'project/src/metacom_pm/rl1/judge.py','RUBRIC').split('Return ONE JSON object',1)[0]
addition=literal(R/'project/src/metacom_pm/rl1/judge_completion_candidate.py','ADDITION')
packet=dict(version='pmrl1-eight-reference-20261016-v1',client_date='2026-10-16',items=items,contexts=contexts,role_contract=role,original_semantic_rules=semantic,original_v2_addition=addition,old_scores_replaced=False)
packet['identity']=digest(packet)
save(O/'materials/packet.json',packet)
save(O/'coordinator/item_bindings.json',mapping)
for cid,e in contexts.items():
    lines=[cid+' — complete legal source',f"current_date: {e['current_date']}",'CURRENT PREFIX']
    lines += [f"{t['id']} [{t['role']}] {t['text']}" for t in e['current_prefix']]
    for h in e['legal_past_sessions']:
        lines += [f"PAST SESSION {h['id']} {h['date']}"]+[f"{t['id']} [{t['role']}] {t['text']}" for t in h['turns']]
    with (O/'materials'/f'{cid}_complete.txt').open('x') as f:f.write('\n\n'.join(lines)+'\n')

app=(O/'form_app.js').read_text()
intro='''<p>这八条用于建立开发参照，不是准确率测试。没有标准答案预填；模型名称、模型分数及旧人工答案不展示。若您看过相关结果，请如实记录，本次不能因此称完全盲评。</p>
<p><b>共同任务：</b>一位新接入的AI依据历史背景，直接回复当前用户。所有历史supporter是另一位说话者；AI不拥有其家人、个人经历或既往行动。普通“我在听”等礼貌表达不自动构成身份错误。</p>
<p><b>如何填写：</b>先读本题完整当前对话，再查完整合法历史；逐条记录实际断言/预设、人物和时间、证据关系、具体后果、当前需要与遗漏。原规则不足时保留未知；人物可判，严重度或q仍可未知。q范围仅是本次参照记录，不换算为正式分数或奖励。</p>
<p>同一回复可有多个主张；无主张时不强造。没有来源支持不等于现实为假。纠正事实后核心理解或建议如何改变，是后果分析的辅助问题，不能按改几个字来判local。</p>
<p><b>独立与保存：</b>两位评审先填写同样八条，再讨论。若仅请第二人看争议项，只能称补充裁决，不能估计整批两人一致性。页面只在本地工作；浏览器草稿和每次导出的JSON分开保留。后续讨论另填讨论记录，不覆盖原答案。</p>'''
rules='<details><summary>原英文身份合同与量表（原文，不含新锚点）</summary><pre>'+html.escape(role+'\n'+semantic+'\n'+addition)+'</pre></details>'
for slot in ['researcher','reviewer_2']:
    title='研究者原始作答' if slot=='researcher' else '第二位评审原始作答'
    doc='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'none'; img-src data:; base-uri 'none'; form-action 'none'"><title>PM-RL1 八条开发参照</title><style>body{font:16px/1.65 system-ui,sans-serif;background:#f5f6f8;color:#172332;margin:0}main{max-width:1000px;margin:auto;padding:22px}.card,header{background:white;padding:22px;margin:18px 0;border:1px solid #d1dae4;border-radius:7px}label{display:block;margin:14px 0}textarea{display:block;width:100%;min-height:70px;box-sizing:border-box}textarea,select,button,input{font:inherit;padding:7px}select{display:block;max-width:100%}pre,.reply,.turn{white-space:pre-wrap;overflow-wrap:anywhere}.reply{background:#eef4fa;padding:14px}.turn{border-bottom:1px solid #eee;padding:8px}fieldset{margin:15px 0;border:1px solid #ccd4dc}summary,button{cursor:pointer}nav{position:sticky;top:0;background:#f5f6f8;padding:10px;z-index:2}#status{font-size:14px;color:#435469}pre{font:inherit}</style></head>'''
    doc+='<body data-slot="'+slot+'"><main><header><h1>'+title+'</h1>'+intro+rules+'<div id="reviewer"></div></header><nav><button id="export">导出当前原始答案JSON（可含未知或草稿）</button><label>恢复本人的导出文件 <input id="import" type="file" accept="application/json"></label><div id="status">尚未填写；不自动填零或生成判断。</div></nav><div id="items"></div></main><script type="application/json" id="packet-data">'+json.dumps(packet,ensure_ascii=False).replace('<','\\u003c')+'</script><script>'+app+'</script></body></html>'
    with (O/f'{slot}.html').open('x') as f:f.write(doc)

# Verify five naturally generated replies from original exact requests, not an old renderer.
lock=read(P3/'calibration/selection_lock_private.json');generated=[]
for pair in lock['natural_pairs']:
    if pair['group']!='development' or pair['index'] not in {102,109,111}:continue
    for side in pair['sides']:
        rawpath=Path(side['raw_path']);raw=read(rawpath)
        match=[k for k in keys if plan['items'][k]['kind']=='natural' and plan['items'][k]['prefix_index']==pair['index'] and plan['items'][k]['reply']==raw['text']]
        if not match:continue
        assert sha(rawpath)==side['raw_sha256']
        reqpath=rawpath.with_name(rawpath.name.replace('.raw.','.request.'));req=read(reqpath);ev=plan['items'][match[0]]['evidence']
        assert [m['role'] for m in req['messages']]==['system','user']
        assert req['messages'][-1]['content']==ev['current_prefix'][-1]['text']
        text=req['messages'][0]['content'];quoted=json.loads(text.split('<quoted_conversation_context>\n',1)[1].split('\n</quoted_conversation_context>',1)[0])
        assert quoted==[dict(speaker=t['role'],text=t['text']) for t in ev['current_prefix'][:-1]]
        assert 'not your own past messages' in text and 'separate speaker' in text and 'Do not claim personal memories' in text
        generated.append(dict(item=match[0],request_id=req['request_id'],request_path=str(reqpath),raw_path=str(rawpath),raw_sha256=sha(rawpath),request_sha256=sha(reqpath),runtime=req['executor_identity'],renderer=req['renderer_identity'],request_roles=['system','user'],role_instruction=text.split('\n<quoted_conversation_context>',1)[0],current_prefix_equal=True,reply_equal=True))
assert len(generated)==5
judgeplan=read(R/'project/outputs/pm_rl1/p3_v2_after_confirmation_20261014/development_plan.json');judge_bindings=[]
for key in keys:
    req=next(x for x in judgeplan['requests'] if x['job_id']==plan['items'][key]['origin_job_id'])
    assert role in req['messages'][0]['content']
    user=json.loads(req['messages'][1]['content']);assert user['reply']==plan['items'][key]['reply'] and user['legal_evidence']==plan['items'][key]['evidence']
    judge_bindings.append(dict(item=key,request_id=req['request_id'],role_contract_present=True,reply_and_evidence_exact=True))
human_summary=read(P3/'calibration/packet_summary.json');intake_meta=read(R/'project/outputs/pm_rl1/human_acceptance_20261014_v2/intake/structural_receipt.json')
original1=read(R/'project/outputs/pm_rl1/human_acceptance_20261014_v2/intake/rater_1_development_original_private.json')
assert original1['form_identity']==human_summary['forms']['rater_1']['form_identity']
human_prefix={}
for slot in ['rater_1','rater_2']:
    p=P3/'calibration/human_handoff_final'/f'{slot}.html';prefix=static_html_prefix(p)
    assert '新接入的 AI 助手' in prefix and '包括当前对话中的 supporter' in prefix
    human_prefix[slot]=dict(static_prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),form_identity=human_summary['forms'][slot]['form_identity'],role_text_consistent=True)
    with (O/'coordinator'/f'{slot}_instructions_only.html').open('x') as f:f.write(prefix)
save(O/'coordinator/identity_bindings.json',dict(generated=generated,controls=[x for x in mapping if x['kind']=='control'],judge_bindings=judge_bindings,human_instrument=human_prefix,original_human_form_matches=True,individual_understanding_proven=False,old_renderer_not_current_request=True))

# Metadata-only stock count. Do not read held-out replies, evidence or labels.
lengths=read(P3/'verification/future_train_dev_source_lengths.json');sets={g:{x['index'] for x in lock['natural_pairs'] if x['group']==g}|set(lock['control_slots'].get(g,[])) for g in ['development','validation','reserve']};locked=set.union(*sets.values());outside=[x for x in lengths['rows'] if x['index'] not in locked];same_dev=[x for x in outside if x['owner'] not in lock['validation_owners']]
assert len(lengths['rows'])==114 and len(outside)==81 and len(same_dev)==9
inventory=dict(kind='metadata_only_not_certified_fresh_validation',frozen_source_prefixes=114,train=96,dev=18,locked_unique_prefixes=len(locked),outside_exact_locked_prefixes=81,outside_locked_and_reserved_validation_owners=9,remaining_development_metadata=same_dev,unexposed_owner_disjoint_validation_certified=0,reason='Every one of the 15 owners is already in development or reserved validation. Nine unused exact dev prefixes remain within exposed owner-history envelopes; no response/exposure audit or new labels supplied.',not_read=['sealed human answers','new source content','new response content'],selection=None)
save(O/'coordinator/validation_inventory.json',inventory)
baseline={}
for p in list((B/'live_runs').rglob('STOP.json'))+[R/'project/outputs/paper1_api_budget/cumulative_paid_api_budget.jsonl',R/'project/docs/pm_rl1_completion_20260930_v2/execution_contract.json',B/'outer_format_v1_20261015/protocol.json',R/'project/src/metacom_pm/rl1/judge_completion_candidate.py',R/'project/src/metacom_pm/rl1/representation_direct.py']:
    baseline[str(p)]=sha(p)
assert len(list((B/'live_runs').rglob('*.started.json')))==54
save(O/'coordinator/preparation_manifest.json',dict(client_date='2026-10-16',packet_identity=packet['identity'],current_scoring_attempts=120,new_scoring_attempts=0,human_answers_received_this_preparation=0,old_results_changed=False,sealed_labels_read=False,validation_text_accident=True,source_files=sources,unchanged_control_baseline=baseline))
print(json.dumps(dict(packet_identity=packet['identity'],items=len(items),contexts=len(contexts),verified_generation_requests=len(generated),judge_bindings=len(judge_bindings),dev07A_explicit_binding=items[4],inventory_counts={k:v for k,v in inventory.items() if isinstance(v,int)}),ensure_ascii=False,indent=2))
