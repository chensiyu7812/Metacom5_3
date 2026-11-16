"""Build local evidence artifacts using stdlib only. No external requests."""
from pathlib import Path
import json, collections, csv, io, html, re

OUT=Path(__file__).resolve().parents[1]
def load(rel):return json.loads((OUT/rel).read_text())
def write(rel,data):
    p=OUT/rel
    encoded=data.encode('utf-8')
    if p.exists():assert p.read_bytes()==encoded, f'Changed derived output: {p}'
    else:p.write_bytes(encoded)
records=load('materials/selected_existing_records.json')
contexts=load('materials/contexts.json')
review=load('analyst_review.json')['rows']
annotations=load('materials/original_annotation_bindings.json')
byid={r['row_id']:r for r in records}
assess={r['row_id']:r for r in review}
names={'plausibly_acceptable':'有可接受依据（分析者）','explicit_problem':'存在明确问题（分析者）','unresolved':'仍未确定'}
plan_names={'0000':'OFF','1000':'RS×1','0100':'MP×1','0010':'MS×1','0001':'ME×1','1111':'四类各1条'}
stat=collections.Counter(r['classification'] for r in review)
contrasts=[]
for r in records:
    if sum(r['counts'])==0:continue
    on=assess[r['row_id']]['classification'];off=assess[r['context_id']+'_0000']['classification']
    contrasts.append(dict(context_id=r['context_id'],on_row_id=r['row_id'],off_row_id=r['context_id']+'_0000',
        on=on,off=off,resource_tokens=r['resource_tokens'],not_qualified_reward=True))
stats=dict(analyst_description_counts=dict(stat),paired_contrasts=len(contrasts),
    transitions=dict(collections.Counter(x['off']+' -> '+x['on'] for x in contrasts)),
    definite_bad_OFF_to_acceptable_ON=0,explicit_problem_OFF_count=0,
    no_independent_human_validation=True,new_calls=0,
    past_generation_seconds=sum(r['generation_seconds'] for r in records),
    past_input_tokens=sum(r['input_tokens'] for r in records),
    past_output_tokens=sum(r['output_tokens'] for r in records),
    past_resource_tokens=sum(r['resource_tokens'] for r in records),
    past_peak_allocated_bytes=max(r['peak_allocated_bytes'] for r in records),
    current_gpu_seconds=0,current_API_usd=0)
write('analysis_summary.json',json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
write('paired_contrasts.json',json.dumps(contrasts,ensure_ascii=False,indent=2)+'\n')

text=['# 24条已有回复的资源对照与原文依据','',
 '版本：acceptability-resource-offline-v1-20261019。下列描述来自Codex离线适用性分析，不是新增模型评分、独立人评或资格标签。',
 '全部回复与资源均从既有实际生成记录原样读取；没有修改任何内部输出。主张的来源必须取自各行自己的上下文。','',
 '## 原八题人评：保持原值，不自动转为二值','',
 '| 原题 | 原q | 原m | 本次24槽中的同文同上下文 |','|---|---|---|---|']
human_reuse={
 'dev04A':'认可承接情绪和建议；不得把“建议长期是否有效”作为本轮必须知道的事实。',
 'dev04B':'原答认可；补充接受预设/引导两读法。保留双读法，不生成唯一新标签。',
 'dev06A':'认可支持策略但指出身份澄清遗漏；是否整体不合格未定。',
 'dev06B':'原答认可支持策略并指出身份遗漏；补充确认谈话已发生预设。严重度没有重标。',
 'dev07A':'认可简短承接与继续探询；没有历史选项清单不是事实错误。',
 'dev15B':'明确帮助来自老同学而不是AI；控制题不等于自然执行器输出。',
 'dev16A':'补充明确亲历归属可能误导；允许保存有归属的旧经验，不因此赋予AI该经历；m仍为.25。',
 'dev35B':'明确求职没有依据；原答列举历史睡眠/婚姻，不构成当前原因已确定。'}
for a in annotations:
    b,h=a['binding'],a['original_human_answer'];q=h['q_value'] if h['q_status']=='single' else h['q_min']+'–'+h['q_max']
    text.append(f"| {b['old_item_key']} | {q} | {h['m_status']} | {', '.join(a['matches_selected_pool']) or '无；不移植分数'} |")
text += ['','原标注仅一人；自由文字不等于完整原子金标。中文阅读版及英文原文身份保留；不将翻译的措辞差异抹去。','']
for a in annotations:
    k=a['binding']['old_item_key'];text += [f"- **{k}**：{human_reuse[k]}"]
text += ['','## 原始回复逐项记录','']
for r in records:
    v=assess[r['row_id']];plan=''.join(map(str,r['counts']))
    text += [f"### {r['row_id']} — {plan_names[plan]}",'',
        f"状态：既有自然结束；资源token {r['resource_tokens']}；分析者描述：{names[v['classification']]}。",'',
        '**完整英文回复**','']
    text += ['> '+line if line else '>' for line in r['reply'].splitlines()]
    text += ['',f"当前需要：{v['current_need']}",'',f"资源提供/采用：{v['resource_delta']}",'',
        f"判断与限制：{v['reason']}",'','原文依据：','']
    for e in v['evidence']:text.append(f"- [{r['context_id']} / {e['id']}, {e['role']}] {e['text']}")
    text += ['','实际交付的完整资源（OFF为空；保持原JSON内容）：','','```json',json.dumps(r['resources'],ensure_ascii=False,indent=2),'```','',
        f"request_id：`{r['request_id']}`；reply_identity：`{r['reply_identity']}`；原输出文件SHA256：`{r['raw_file_sha256']}`。",'',
        f"原始文件：`{r['raw_path']}`。",'']
write('RESOURCE_COMPARISON_ZH.md','\n'.join(text)+'\n')

buf=io.StringIO();writer=csv.DictWriter(buf,fieldnames=['row_id','context_id','prefix_index','counts','resource_tokens','status','analyst_description','input_tokens','output_tokens','generation_seconds','reply_identity','request_id','original_human_item','reward_eligible'])
writer.writeheader()
for r in records:
    writer.writerow(dict(row_id=r['row_id'],context_id=r['context_id'],prefix_index=r['prefix_index'],
        counts=json.dumps(r['counts']),resource_tokens=r['resource_tokens'],status=r['status'],
        analyst_description=names[assess[r['row_id']]['classification']],input_tokens=r['input_tokens'],
        output_tokens=r['output_tokens'],generation_seconds=r['generation_seconds'],reply_identity=r['reply_identity'],
        request_id=r['request_id'],original_human_item=','.join(a['binding']['old_item_key'] for a in annotations if r['row_id'] in a['matches_selected_pool']),reward_eligible=False))
write('ROWS_24.csv',buf.getvalue())

# Small local document renderer; no dependencies, JavaScript, remote fonts or network.
def inline(s):
    s=html.escape(s)
    s=re.sub(r'`([^`]+)`',r'<code>\1</code>',s)
    return re.sub(r'\*\*([^*]+)\*\*',r'<strong>\1</strong>',s)
def markdown(s):
    output=[];intable=False;incode=False;inlist=False
    for line in s.splitlines():
        if line.startswith('```'):
            output.append('</code></pre>' if incode else '<pre><code>');incode=not incode;continue
        if incode:output.append(html.escape(line)+'\n');continue
        istable=line.startswith('|')
        islist=line.startswith('- ') or bool(re.match(r'^\d+\. ',line))
        if intable and not istable:output.append('</tbody></table></div>');intable=False
        if inlist and not islist:output.append('</ul>');inlist=False
        if istable:
            if re.fullmatch(r'[|:\- ]+',line):continue
            cells=line.strip('|').split('|')
            if not intable:output.append('<div class="table"><table><tbody>');intable=True
            output.append('<tr>'+''.join('<td>'+inline(c.strip())+'</td>' for c in cells)+'</tr>');continue
        if islist:
            if not inlist:output.append('<ul>');inlist=True
            output.append('<li>'+inline(re.sub(r'^(?:- |\d+\. )','',line))+'</li>');continue
        if not line:continue
        m=re.match(r'^(#{1,4}) (.*)$',line)
        if m:output.append(f'<h{len(m[1])}>{inline(m[2])}</h{len(m[1])}>')
        elif line.startswith('>'):output.append('<blockquote>'+inline(line[1:].strip())+'</blockquote>')
        else:output.append('<p>'+inline(line)+'</p>')
    if intable:output.append('</tbody></table></div>')
    if inlist:output.append('</ul>')
    return '\n'.join(output)

body=['<nav><a href="#decision">结论</a><a href="#minimum">一页最低要求</a><a href="#proposal">最小修订建议</a><a href="#rows">24条对照</a><a href="#sources">完整来源</a></nav>']
for anchor,name in [('decision','DECISION_BRIEF_ZH.md'),('minimum','MINIMUM_REQUIREMENTS_DRAFT_ZH.md'),('proposal','MINIMAL_CHANGE_PROPOSAL_ZH.md')]:
    body.append(f'<section id="{anchor}">'+markdown((OUT/name).read_text())+'</section>')
body.append('<section id="rows"><h1>24条既有回复与实际资源</h1><p>描述均为分析者适用性判断，不是新的正式合格标签。点击展开每项全文与绑定。</p>')
for r in records:
    v=assess[r['row_id']]
    body.append(f'<details><summary>{r["row_id"]} · {plan_names["".join(map(str,r["counts"]))]} · {names[v["classification"]]} · {r["resource_tokens"]}资源tokens</summary>')
    body.append('<h3>完整英文回复</h3><blockquote class="full">'+html.escape(r['reply'])+'</blockquote>')
    body.append('<p><strong>资源变化：</strong>'+html.escape(v['resource_delta'])+'</p><p><strong>判读：</strong>'+html.escape(v['reason'])+'</p>')
    body.append('<h3>本时点来源依据</h3>')
    for e in v['evidence']:body.append('<p><code>'+html.escape(e['id'])+'</code> '+html.escape(e['text'])+'</p>')
    body.append('<details><summary>实际交付的完整资源</summary><pre>'+html.escape(json.dumps(r['resources'],ensure_ascii=False,indent=2))+'</pre></details>')
    body.append('<p>request_id <code>'+r['request_id']+'</code></p><p>reply_identity <code>'+r['reply_identity']+'</code></p></details>')
body.append('</section><section id="sources"><h1>完整合法来源（逐上下文隔离）</h1><p>较晚上下文的历史可能包含较早切点的后续；不能跨时点混作可见证据。</p>')
for cid in contexts:
    body.append('<details><summary>'+cid+'</summary><pre>'+html.escape((OUT/'materials'/f'{cid}_complete.txt').read_text())+'</pre></details>')
body.append('</section>')
style='''body{font-family:system-ui,"Noto Sans CJK SC",sans-serif;background:#f6f7f9;color:#17202a;margin:0;line-height:1.8}main{max-width:1100px;margin:auto;padding:24px}nav{position:sticky;top:0;background:#fff;padding:12px;border-bottom:1px solid #ddd;display:flex;gap:18px;flex-wrap:wrap}a{color:#2459a6}section{background:white;padding:28px;margin:20px 0;border-radius:8px}h1{font-size:1.6rem;line-height:1.45}h2{font-size:1.2rem;margin-top:30px}h3{font-size:1rem}p,li{max-width:92ch}code{font-size:.86em;overflow-wrap:anywhere}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f2f4f7;padding:14px;font-size:.86em}blockquote{border-left:3px solid #8ba4c3;padding:5px 16px;margin:18px 0;color:#374151}.full{white-space:pre-wrap}details{border:1px solid #d6dde5;border-radius:5px;margin:12px 0;padding:12px}summary{cursor:pointer;font-weight:600}.table{overflow:auto}table{border-collapse:collapse;width:100%;font-size:.92em}td{border:1px solid #d6dde5;padding:9px;vertical-align:top}tr:first-child{background:#eef2f7;font-weight:600}@media print{nav{position:static}section{padding:0;break-before:page}body{background:white}}'''
doc='<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PM-RL1 资源适用性与合格性诊断</title><style>'+style+'</style><main>'+''.join(body)+'</main></html>'
write('review.html',doc)

nb={'nbformat':4,'nbformat_minor':5,'metadata':{'kernelspec':{'display_name':'Python 3','language':'python','name':'python3'}},'cells':[
 {'cell_type':'markdown','id':'scope','metadata':{},'source':['# PM-RL1 离线复算\n','只读取本包派生数据，不调用模型、读取凭据或修改旧账本。24槽/4上下文/2owner；分析者描述不是人评或奖励。']},
 {'cell_type':'code','id':'read','execution_count':None,'metadata':{},'outputs':[],'source':['from pathlib import Path\n','import json, collections\n','root = Path.cwd()  # 在本包根目录启动\n','rows = json.loads((root / "materials/selected_existing_records.json").read_text())\n','review = json.loads((root / "analyst_review.json").read_text())["rows"]\n','assert len(rows) == len(review) == 24\n','assert {r["prefix_index"] for r in rows} == {111,102,104,109}\n','collections.Counter(r["classification"] for r in review)']},
 {'cell_type':'code','id':'pairs','execution_count':None,'metadata':{},'outputs':[],'source':['pairs = json.loads((root / "paired_contrasts.json").read_text())\n','assert len(pairs) == 20\n','collections.Counter((p["off"],p["on"]) for p in pairs)']},
 {'cell_type':'code','id':'reuse','execution_count':None,'metadata':{},'outputs':[],'source':['human = json.loads((root / "materials/original_annotation_bindings.json").read_text())\n','[(x["binding"]["old_item_key"], x["matches_selected_pool"]) for x in human]']},
 {'cell_type':'markdown','id':'limitation','metadata':{},'source':['没有计算准确率或正式接受率。所有未决项保留；没有把事实问题数量当独立上下文数量。原始文件绑定与前后哈希检查见verification.json；数据提取实现见code/extract_existing.py。']} ]}
write('recompute.ipynb',json.dumps(nb,ensure_ascii=False,indent=2)+'\n')
print(json.dumps(stats,ensure_ascii=False))
