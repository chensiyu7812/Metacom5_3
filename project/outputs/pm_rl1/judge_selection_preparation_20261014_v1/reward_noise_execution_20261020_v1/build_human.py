"""Local paired-direction worksheet. Contains no scores or resource labels."""
from pathlib import Path
import json,html,hashlib,os,zipfile
from datetime import datetime
from zoneinfo import ZoneInfo
HERE=Path(__file__).resolve().parent;BASE=HERE.parent;PROP=BASE/'reward_noise_proposal_20261020_v1'
os.umask(0o077)
out=Path('/home/tokkio/PM_RL1_NOISE_HUMAN_8PAIRS_20261020');out.mkdir(mode=0o700,exist_ok=False)
proposal=json.loads((PROP/'proposal.json').read_text());items={};contexts={}
for endpoint in proposal['endpoints']:
    d=json.loads((PROP/endpoint['payload_file']).read_text());u=json.loads(d['messages'][1]['content'])
    items[endpoint['row_id']]={'reply':u['reply'],'reply_identity':endpoint['reply_identity']}
    contexts[endpoint['context_id']]=u['legal_evidence']
zh={
'context_01_0000':'听起来，不公平的对待让你感到沮丧，那种不公感正沉重地压在你心上。看到别人因为似乎与实际工作态度无关的原因而受到偏袒，你有这种感受完全可以理解。\n\n既然你提到自己无法忍受不公，你有没有考虑过直接和经理谈谈，这种偏袒如何影响你们团队的士气和生产力？还是说，你希望寻找不把他们牵涉进来的应对办法？',
'context_01_1000':'听起来，工作中看到的不公平对待让你深感沮丧。看到别人只是因为赞同经理，而不是凭实际工作态度，就比你更受青睐，你有这种感受完全可以理解。\n\n你有没有和其他人谈过这件事，比如同事，或不在你经理直接团队里的主管？有时，向能够提供不同视角的人说说自己的担忧，能让你不那么孤立，也更有力量应对这个问题。',
'context_01_0100':'听起来，工作中看到的不公平对待让你深感沮丧。看到别人只是因为赞同经理，而不是凭实际工作态度，就比你更受青睐，你有这种感受完全可以理解。\n\n既然你提到自己无法忍受不公，你有没有考虑过直接和经理谈谈，这种偏袒如何影响你们团队的士气和生产力？还是你更想先探索其他策略？',
'context_02_0000':'很遗憾你有这种感受。听起来，你和妈妈之间的情况让你很紧张。被告知可以和谁、不能和谁做朋友时，如果你感到愤怒，想反抗这些限制是自然的。\n\n你是否发现，和她谈论她的规矩给你的感受，有助于平息愤怒，还是说这通常会让争吵升级？',
'context_02_1000':'很遗憾你有这种感受。听起来，和妈妈之间的情况让你很沮丧，尤其涉及选择自己的朋友这样重要的事情。\n\n既然你提到这让你生气，我想问：当妈妈不赞同你的朋友时，你有没有和朋友谈过自己的感受？有时，向关心你的人分享这些感受，可以让负担轻一些。',
'context_02_0001':'很遗憾你有这种感受。听起来，和妈妈之间的情况让你很沮丧，尤其是在选择自己的朋友这件事上。\n\n既然你提到自己感到愤怒，你愿意多谈谈具体是什么触发了这种愤怒吗？是被控制的感觉，还是害怕让她失望？',
'context_03_0000':'听起来这非常有帮助。一个了解你的人带来的新视角，竟然能改变你对论文这样具有挑战性的事情的整个看法，真令人感慨。你是否发现，他们的见解具体回应了导师提出的某些问题，还是更多涉及你对待这项工作的方式？',
'context_03_1000':'听起来那是一次很有力量的谈话。有时，一个关心你的人带来的新视角，就能帮助我们转变心态，这真令人感慨。你现在对自己的论文感觉如何？',
'context_03_0010':'听起来，那是一次很有力量的转变。有时，只要有人倾听，就能帮助我们更清楚地看到自己的长处和能力，尤其当我们在论文这样的项目中感到迷茫时。\n\n你现在对这项工作感觉如何？自从那次谈话后，你有没有取得什么进展？',
'context_04_0000':'很遗憾你最近过得艰难。你愿意谈谈发生了什么，或者有没有某件特别放在心上、想分享的事？',
'context_04_1000':'很遗憾你最近过得艰难。听起来，你正经历一段充满挑战的时期，尤其是在找工作这件事上。你愿意谈谈，现在具体是什么让事情变得困难吗？',
'context_04_1111':'很遗憾你最近过得艰难。听起来，你正在经历一段困难时期。如果你想分享心里的事，我愿意倾听。今天我可以怎样支持你？'}
assert set(zh)==set(items)
def esc(x):return html.escape(str(x))
def turns(ts):return '\n'.join(f"[{t['id']}] {t['role']}: {t['text']}" for t in ts)
for c,e in contexts.items():
    text='CURRENT DATE: '+e['current_date']+'\n\nCURRENT PREFIX\n'+turns(e['current_prefix'])
    for session in e['legal_past_sessions']:
        text+='\n\nPAST SESSION '+session['id']+' '+session['date']+'\n'+turns(session['turns'])
    (out/(c+'_complete.txt')).write_text(text+'\n')
bindings=[];sections=[]
for i,c in enumerate(proposal['contrasts'],1):
    left,right=(c['off'],c['on']) if i%2 else (c['on'],c['off']);cid=left.rsplit('_',1)[0];e=contexts[cid]
    bid=f'P{i:02d}';bindings.append(dict(pair_id=bid,contrast=c['id'],left_endpoint=left,right_endpoint=right,
        left_reply_identity=items[left]['reply_identity'],right_reply_identity=items[right]['reply_identity']))
    source=esc((out/(cid+'_complete.txt')).read_text())
    section=f'<section data-pair="{bid}"><h2>第{i}组</h2><p>当前日期：{esc(e["current_date"])}</p><details open><summary>完整当前对话</summary><pre>{esc(turns(e["current_prefix"]))}</pre></details><details><summary>完整合法来源（含全部历史；点击展开）</summary><pre>{source}</pre></details><div class="pair">'
    for side,key in [('A',left),('B',right)]:
        section+=f'<article><h3>回复{side} · 英文原文</h3><pre>{esc(items[key]["reply"])}</pre><details open><summary>辅助中文译文</summary><pre>{esc(zh[key])}</pre></details></article>'
    section+='</div><fieldset><legend>综合当前请求与完整来源，你怎样比较这两条回复？</legend>'
    for val,label in [('A','A较好'),('B','B较好'),('tie','基本相当'),('unknown','无法判断')]:
        section+=f'<label><input type="radio" name="{bid}_direction" value="{val}">{label}</label>'
    section+='</fieldset><label>最重要的理由：哪句话满足了需要，或存在重要问题？有来源依据时写ID/原句。<textarea data-field="reason" rows="4"></textarea></label><label>若无法判断：具体缺什么，或哪两种理解都合理？<textarea data-field="uncertainty" rows="2"></textarea></label></section>'
    sections.append(section)
public_binding=[{k:v for k,v in x.items() if k in ('pair_id','left_reply_identity','right_reply_identity')} for x in bindings]
metadata=dict(version='pmrl1-noise-paired-reference-zh-guide-v1-20261020',proposal_identity=proposal['identity'],
    pairs=public_binding,max_minutes=120,translation='Codex auxiliary reply translation v1; English source and reply authoritative; complete source not translated',
    old_exposure_disclosed=True,model_scores_shown=False,resource_condition_shown=False)
(HERE/'human_private_mapping.json').write_text(json.dumps(bindings,ensure_ascii=False,indent=2)+'\n')
(HERE/'human_translation_v1.json').write_text(json.dumps(zh,ensure_ascii=False,indent=2)+'\n')
script='''const meta=META; const key=meta.version; let prior={};try{prior=JSON.parse(localStorage.getItem(key)||'{}')}catch(e){}
const started=prior.started||new Date().toISOString();
function data(){return {version:meta.version,proposal_identity:meta.proposal_identity,started,exported:new Date().toISOString(),old_exposure_disclosed:true,new_scores_seen:document.querySelector('#seen').value||null,self_reported_minutes:document.querySelector('#minutes').value||null,answers:[...document.querySelectorAll('section[data-pair]')].map((s,i)=>({pair_id:s.dataset.pair,...meta.pairs[i],direction:s.querySelector('input:checked')?.value||null,reason:s.querySelector('[data-field=reason]').value,uncertainty:s.querySelector('[data-field=uncertainty]').value}))}}
for(const s of document.querySelectorAll('section[data-pair]')){const a=prior.answers?.find(x=>x.pair_id===s.dataset.pair);if(a){const r=s.querySelector(`input[value="${a.direction}"]`);if(r)r.checked=true;s.querySelector('[data-field=reason]').value=a.reason||'';s.querySelector('[data-field=uncertainty]').value=a.uncertainty||''}}
document.querySelector('#seen').value=prior.new_scores_seen||'';document.querySelector('#minutes').value=prior.self_reported_minutes||'';
function save(){try{localStorage.setItem(key,JSON.stringify(data()))}catch(e){}const n=data().answers.filter(x=>x.direction).length;document.querySelector('#progress').textContent=`已选择 ${n}/8 组；未填会保留为空。`}
document.addEventListener('input',save);document.addEventListener('change',save);save();
document.querySelector('#download').onclick=()=>{const d=data(),blob=new Blob([JSON.stringify(d,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='PMRL1_noise_pairs_'+new Date().toISOString().replaceAll(':','-')+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
'''.replace('META',json.dumps(metadata,ensure_ascii=False).replace('<','\\u003c'))
page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PM-RL1：8组回复比较</title><style>body{font:17px/1.65 system-ui;margin:auto;max-width:1250px;padding:25px;color:#172334;background:#f4f6fa}section{background:white;padding:25px;margin:28px 0;border-radius:10px}.pair{display:grid;grid-template-columns:1fr 1fr;gap:22px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}article{border:1px solid #ccd5df;padding:15px;border-radius:8px}details{margin:14px 0}summary{cursor:pointer;font-weight:600}label{display:block;margin:12px 0}fieldset label{display:inline-block;margin-right:22px}textarea{box-sizing:border-box;width:100%;font:inherit}button{font:inherit;padding:12px 20px;background:#164b85;color:white;border:0;border-radius:7px}footer{position:sticky;bottom:0;background:#e7eef7;padding:12px}@media(max-width:800px){.pair{grid-template-columns:1fr}}</style><h1>8组回复比较</h1><p>只比较回复是否回应当前用户、是否有重要事实或身份问题。资源条件和模型分数均不展示。你看过部分旧材料，这次不称完全盲评。</p><p><strong>共同身份前提：</strong>当前回复者是新接入的AI，不是历史对话中的真人支持者。AI可以参考并准确转述历史支持者的经历/建议，不能把它们认作自己的亲身经历。无需每次机械声明AI身份；用户把先前经历或行动归给当前AI时，需要清楚处理身份承接。</p><p>允许基本相当、两种理解都合理、无法判断。普通鼓励和开放邀请不要求逐句对应历史。不要为了本研究需要正收益而偏爱某条回复，也不用强定q/m。英文原文为判断依据，中文译文仅辅助；含预设的措辞若拿不准请记为未知。</p><p>总计最多120分钟，包含来源阅读；达到时间就导出已做部分，不必硬填。每组写一个最重要的理由即可。填写完成前请先不阅读本轮模型分数或结果附录。页面仅在本机保存，不联网。</p><label>已阅读本轮模型分数吗？<select id="seen"><option value="">未填写</option><option value="no">没有</option><option value="yes">有（照实记录即可）</option></select></label><label>本次实际用时（分钟，可结束时填）<input type="number" min="0" max="120" id="minutes"></label>'''+''.join(sections)+'''<footer><span id="progress"></span> <button id="download">下载我的作答JSON</button></footer><script>'''+script+'</script></html>'
(out/'researcher.html').write_text(page)
(out/'README_ZH.md').write_text('打开 researcher.html，比较8组回复；完整来源在页面中和4份文本文件中。最多120分钟，不必强行判定。下载作答JSON后交回即可。新模型结果未放入此包；条件映射仅留协调目录。英文原文权威，中文为本版辅助译文。\n')
manifest=dict(created_at=datetime.now(ZoneInfo('Asia/Tokyo')).isoformat(),metadata=metadata,
    files={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in out.iterdir() if f.is_file()},
    answers_prefilled=False,scores_included=False)
(out/'MANIFEST.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
for f in out.iterdir():f.chmod(0o600)
with zipfile.ZipFile(out.with_suffix('.zip'),'x',compression=zipfile.ZIP_DEFLATED) as z:
    for f in out.iterdir():z.write(f,arcname=out.name+'/'+f.name)
out.with_suffix('.zip').chmod(0o600)
print(json.dumps({'page':str(out/'researcher.html'),'zip':str(out.with_suffix('.zip')),'pairs':8,'source_groups':4,'answers_prefilled':False},ensure_ascii=False))
