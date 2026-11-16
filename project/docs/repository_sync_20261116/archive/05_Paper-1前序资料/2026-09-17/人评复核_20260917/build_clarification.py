from pathlib import Path
import json, hashlib, html

OUT=Path(__file__).resolve().parent
AUDIT=Path('/home/tokkio/人评结果分析_20260917')
SRC={r['human_item_number']:r for r in json.loads((AUDIT/'重点案例证据.json').read_text())}
raw_A=Path('/home/tokkio/paper1_pairwise_teacher_rater_a_sheet_v2_zh_v1_rated.json')
assert hashlib.sha256(raw_A.read_bytes()).hexdigest()=='0272f503c61811484c9b7da2c6bb25e331538376bd0e1b683e4f2dd3c6e5a94b'

notes=[
 (3,'译文不能替原文增加事实',
  '原题：还记得艾米莉想养宠物的事吗？',
  [('历史原文（2025-11-05）','她一直想养一只宠物，我和玛格丽特已经开始认真讨论。'),
   ('原页面的问题','pet 被译为“猫”，同一会话后面又被译为“狗狗”；原文未指定这两种动物。'),
   ('候选回复的差别','候选 A 指定了“养狗”；候选 B 说“养宠物”，并回顾责任、工作繁忙和对家庭的可能好处。')],
  '应核对“狗”是否有英文证据，不能用译文里的“猫”作为原始事实。你原来选 B 的方向未必需要改变，但理由中关于猫的依据需要澄清。DG 可查完整过去历史，不局限于相关摘录。'),
 (11,'总结是否正确，要核对结局',
  '原题：安娜的恋爱关系如何随时间发展？',
  [('参考答案要点','未来规划分歧、反复争吵和外部压力，最终导致分手。'),
   ('候选 A 的实际结论摘译','他们克服了挑战，关系更加牢固，最终搬到一起生活。'),
   ('候选 B 摘译','没有足够的信息，无法准确总结这段关系。')],
  'A 不是“正确总结”，它把关键结局写反了。B 也没有完成摘要任务。比较应考虑这些实际缺陷，不能仅凭 A 写了分析过程和结论就判它更好；也不是规定所有拒答都优于所有有缺陷的回答。'),
 (27,'一句事实答案也能完成 QA',
  '原题：求助者正在考虑搬去哪里？',
  [('参考答案','求助者正在考虑搬到加利福尼亚州。'),
   ('候选 A 的最后答案','unknown（不知道）。'),
   ('候选 B 的完整回答','求助者正在考虑搬到加利福尼亚州。')],
  'B 已直接回答问题。这个 QA 任务不要求先承接情绪，简短本身不是缺点。评审看得到参考答案，不等于生成模型也拿到了该参考答案；两者的输入角色不同。'),
 (64,'两边同样差，也可以判相当',
  '这道情绪支持题中，两个候选逐字相同。完整对话可展开查看。',
  [('候选 A（完整译文）','我无法帮助你处理这个问题。还有什么其他需要我帮忙的吗？'),
   ('候选 B（完整译文）','我无法帮助你处理这个问题。还有什么其他需要我帮忙的吗？')],
  '如果能判断两者同样差，equivalent 正是允许的选项。它不是“两个都很好”的意思。uncertain 用于证据不足、无法判断正确性或无法权衡实质利弊，不是表达不满意的选项。'),
 (81,'答案自己列出的“记忆”，仍然要核实',
  '原题：约翰采取了哪些措施解决工资单金额不符？',
  [('参考答案','Unknown（没有可据以回答具体措施的答案）。'),
   ('候选 A（完整译文）','我无法协助处理这个请求。还有什么其他需要我帮忙的吗？'),
   ('候选 B 的内容摘译','2024-08-10 发现问题；08-12 联系人力资源部门；08-15 获悉问题已经解决。')],
  '这些日期和步骤来自候选回复本身，不是独立提供的参考证据。不能因为它写着“相关记忆”“分析步骤”，就把其中陈述视为已经验证。A 的拒答不理想，B 的无依据细节也不能因看起来更努力而获得奖励。'),
 (95,'事实和任务相当时，可以保留风格分歧',
  '原题情境：用户想倾诉，总帮别人却觉得被利用，还没有向对方表达。',
  [('候选 A 的做法概括','理解难以开口，并直接给出沟通与设置边界的示例。'),
   ('候选 B 的做法概括','理解难以开口，先问用户是否想听开启沟通的建议。'),
   ('你们记录的偏好','你更喜欢 A，同学更喜欢 B，共同判为实质相当。')],
  '当前没有明确证据说明用户只接受其中一种方式，也未显示清晰的实质净优势，因此原来的相当判断有可辩护依据。评审个人更喜欢一种表达，不自动意味着它对题中用户更好；这类分歧不必为了匹配 AI 而消除。')
]
examples=[]
for n,title,question,blocks,explanation in notes:
    s=SRC[n]
    en={k:s[k] for k in ('task_input','reference_material','response_A','response_B')}
    if n==3:
        session=next(v for v in s['complete_history']['sessions'] if v['timestamp']=='2025-11-05')
        en['reference_material']='Prior session [2025-11-05]\n'+'\n'.join(t['role']+': '+t['content'] for t in session['turns'])
    examples.append({'case_id':f'clarify_A{n:02d}','original_A_item':n,'presentation_id':s['presentation_id'],
       'title':title,'question_zh':question,'evidence_blocks_zh':blocks,'explanation_zh':explanation,
       'english_source':en,'source_scope':'A3 displays one relevant complete past session; other cases retain the full original shown input and reference.',
       'translation_status':'New assistant-authored explanatory translations/paraphrases; English source remains authoritative; not a full replacement translation.'})
payload={'schema':'paper1-post-rating-comprehension-notes-v1','date':'2026-09-17','purpose':'six explanatory cases; not independent judgements, not revised verdicts, not consensus labels',
         'examples':examples,'user_provenance':json.loads((OUT/'provenance_addendum.json').read_text())}
(OUT/'clarification_examples.json').write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n')
digest=hashlib.sha256((OUT/'clarification_examples.json').read_bytes()).hexdigest()
cards=[]
for i,e in enumerate(examples,1):
    blocks=''.join('<div class="evidence"><b>'+html.escape(k)+'</b><p>'+html.escape(v)+'</p></div>' for k,v in e['evidence_blocks_zh'])
    english=''.join('<h4>'+html.escape(k)+'</h4><pre>'+html.escape(v if v is not None else 'No separate reference for ESC.')+'</pre>' for k,v in e['english_source'].items())
    options=''.join(f'<label><input type="radio" name="{e["case_id"]}" value="{value}">{label}</label>' for value,label in [('understood','已理解这个区别'),('different_understanding','我有不同理解'),('unsure','暂不确定')])
    cards.append(f'<article data-case="{e["case_id"]}"><p class="eyebrow">例 {i}/6 · 原 A 卷第 {e["original_A_item"]} 题</p><h2>{html.escape(e["title"])}</h2><p>{html.escape(e["question_zh"])}</p>{blocks}<div class="point"><b>本例澄清</b><p>{html.escape(e["explanation_zh"])}</p></div><details><summary>展开原始英文核对</summary>{english}</details><fieldset><legend>可选：记录你的理解</legend>{options}</fieldset><label class="comment-label">疑问或不同看法（可留空）<textarea rows="3" placeholder="有疑问时写一句即可；不要求重判胜者。"></textarea></label></article>')
data=json.dumps({'digest':digest,'case_ids':[e['case_id'] for e in examples]},ensure_ascii=False).replace('<','\\u003c')
page='''<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>判题口径澄清 · 六个例子</title>
<style>body{margin:0;background:#f3f6f8;color:#243546;font:17px/1.75 system-ui,"Noto Sans CJK SC",sans-serif}main{max-width:900px;margin:auto;padding:32px 22px 80px}header,article{background:white;padding:28px 34px;border:1px solid #dde4e9;border-radius:10px;margin-bottom:24px}h1{font-size:28px;line-height:1.4}h2{font-size:23px;line-height:1.45;margin-top:4px}p{margin:10px 0}.eyebrow{color:#486984;font-size:14px}.evidence{border-left:3px solid #c3d6e4;padding:9px 16px;margin:14px 0;background:#f8fafb}.point{border-left:3px solid #b4883b;background:#faf7ef;padding:12px 16px;margin:20px 0}summary{cursor:pointer;color:#185b86}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.7 ui-monospace,monospace;background:#f5f7f9;padding:12px}fieldset{border:0;padding:16px 0 8px;margin:0}legend{padding-top:15px;font-weight:600}fieldset label{display:inline-block;margin:5px 20px 5px 0}input{margin-right:7px;accent-color:#246890}textarea{box-sizing:border-box;width:100%;margin-top:6px;padding:12px;border:1px solid #bdcbd5;border-radius:5px;font:16px/1.5 inherit}.comment-label{display:block}.toolbar{display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:20px}button,.import-label{border:1px solid #246890;background:#fff;color:#185675;border-radius:5px;padding:10px 16px;cursor:pointer;font:inherit}button.primary{background:#246890;color:white}#status{font-size:14px;color:#4a5d6c;min-height:1.75em}.fine{font-size:14px;color:#506271}a{color:#185b86}@media(max-width:650px){main{padding:16px 10px 45px}header,article{padding:20px 17px}h1{font-size:24px}h2{font-size:21px}fieldset label{display:block}body{font-size:16px}}@media print{body{background:white}main{max-width:none;padding:0}article{break-inside:avoid}.toolbar,fieldset,.comment-label{display:none}}</style></head><body><main>
<header><p class="eyebrow">Metacom5_3 · 2026-09-17 · 事后口径澄清</p><h1>先看六个例子，把判断标准对齐</h1><p>你们的原始评分已保留。这里集中解释已经发现的翻译和任务理解问题，包含一个原判断合理的风格例子。每例只需看关键中文；需要时可展开英文。</p><p>这些是看过人类与 AI 结果后整理的说明，不是新的盲评卷，也不要求照着 AI 改分。你可以只提出仍有疑问的地方。</p><p class="fine">A：两人共同看中文题，确认最终判定一致，收到一份联合记录。B：研究者报告为 GPT-6 Astra（极高），作答时未见 A。六例选自已发现的问题，不用于估计整体准确率。</p><div class="toolbar"><button class="primary" id="export" type="button">导出讨论记录 JSON</button><label class="import-label">恢复讨论记录<input id="import" type="file" accept="application/json,.json" hidden></label><span id="progress">已记录 0/6</span></div><p id="status" role="status">可以分次阅读。备注保存在本机浏览器；离开前可导出备份，也可直接在对话里回复疑问。</p></header>
'''+''.join(cards)+'''
<p class="fine">QA/Summary 先看是否回答正确、是否忠实；ESC/DG 还要看当前需求、记忆正确性与相关性。相当可以包括双方同样差。资料中的参考答案供评审核对，不是自动提供给生成器的输入。六例澄清不自动替代原定独立人评要求。</p></main><script id="page-data" type="application/json">'''+data+'''</script><script>
"use strict";
const meta=JSON.parse(document.getElementById('page-data').textContent);
const key='paper1-comprehension-'+meta.digest;
const allowed=new Set(['understood','different_understanding','unsure']);
const cards=[...document.querySelectorAll('article[data-case]')];
function collect(){return {schema:'paper1-post-rating-comprehension-notes-v1',source_digest:meta.digest,record_type:'assisted_comprehension_notes_not_ratings',notes:cards.map(c=>({case_id:c.dataset.case,understanding_status:c.querySelector('input:checked')?.value??null,comment:c.querySelector('textarea').value}))};}
function valid(x){return x&&x.schema==='paper1-post-rating-comprehension-notes-v1'&&x.source_digest===meta.digest&&x.record_type==='assisted_comprehension_notes_not_ratings'&&Array.isArray(x.notes)&&x.notes.length===6&&x.notes.every((n,i)=>n.case_id===meta.case_ids[i]&&(n.understanding_status===null||allowed.has(n.understanding_status))&&typeof n.comment==='string');}
function progress(){const n=collect().notes.filter(n=>n.understanding_status!==null||n.comment.trim()).length;document.getElementById('progress').textContent='已记录 '+n+'/6';}
function apply(x){if(!valid(x))throw new Error('文件不是本版六例的讨论记录；请使用这里导出的 JSON。');cards.forEach((c,i)=>{c.querySelectorAll('input').forEach(el=>el.checked=el.value===x.notes[i].understanding_status);c.querySelector('textarea').value=x.notes[i].comment;});progress();}
function save(){progress();try{localStorage.setItem(key,JSON.stringify(collect()));document.getElementById('status').textContent='已保存到本机浏览器；可随时导出，允许只记录部分例子。';}catch{document.getElementById('status').textContent='浏览器未允许本机保存，请使用“导出讨论记录 JSON”。';}}
try{const stored=localStorage.getItem(key);if(stored)apply(JSON.parse(stored));}catch{document.getElementById('status').textContent='未恢复旧进度；可以开始阅读并导出新记录。';}
cards.forEach(c=>{c.addEventListener('change',save);c.querySelector('textarea').addEventListener('input',save);});
document.getElementById('export').addEventListener('click',()=>{const url=URL.createObjectURL(new Blob([JSON.stringify(collect(),null,2)+'\\n'],{type:'application/json;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='paper1_comprehension_notes_v1.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);});
document.getElementById('import').addEventListener('change',async event=>{try{const f=event.target.files[0];if(!f)return;const x=JSON.parse(await f.text());apply(x);save();}catch(err){document.getElementById('status').textContent=String(err.message);}finally{event.target.value='';}});
</script></body></html>'''
(OUT/'判题口径澄清_6例.html').write_text(page,encoding='utf-8')
print('Built 6 explanation cards; raw English retained; no outcome labels written.')

if __name__=='__main__':
    assert len(examples)==6
    for e in examples:
        s=SRC[e['original_A_item']]
        assert e['english_source']['response_A']==s['response_A']
        assert e['english_source']['response_B']==s['response_B']
        assert e['english_source']['task_input']==s['task_input']
