#!/usr/bin/env python3
"""Deliver existing development materials; no labels, inference or sealed data.

Blind A/B mapping stays in the private coordinator directory. Historical
regression scores are on a separate page; future scores stay explicitly pending.
"""
import argparse
import csv
import hashlib
import html
import json
from pathlib import Path
import sys
import zipfile

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.rl1.schema import digest

VERSION = 'pmrl1-development-human-delivery-v1'
STYLE = """body{font:17px/1.65 system-ui,sans-serif;background:#f3f5f7;color:#182639;margin:0}
main{max-width:1050px;margin:auto;padding:24px}h1{font-size:29px}h2{font-size:23px}
article,.box{background:white;border:1px solid #dce3ea;border-radius:12px;padding:22px;margin:20px 0}
nav{position:sticky;top:0;background:#e7eef7;padding:12px;z-index:2;border-bottom:1px solid #bdcbdc}
button{background:#153e68;color:white;padding:9px 14px;border:0;border-radius:6px;cursor:pointer;margin:3px}
input,select,textarea{font:inherit;padding:8px;box-sizing:border-box;max-width:100%;border:1px solid #9aabba;border-radius:5px}
textarea{width:100%;min-height:86px}label{display:block;margin:12px 0}input[type=text]{width:100%}
.replies{display:grid;grid-template-columns:1fr 1fr;gap:20px}.reply{background:#f2f6fb;padding:16px;border-radius:8px;white-space:pre-wrap}
.turn{white-space:pre-wrap;padding:8px 0;border-bottom:1px solid #eee}summary{cursor:pointer;font-weight:600;padding:6px}
pre{white-space:pre-wrap;overflow-wrap:anywhere;font:14px/1.6 ui-monospace,monospace}.note{background:#fff5db;padding:12px;border-radius:8px}
.muted{color:#536273}a{color:#174e88}table{border-collapse:collapse}td,th{border:1px solid #cad4df;padding:8px;text-align:left}
@media(max-width:700px){.replies{grid-template-columns:1fr}main{padding:10px}article{padding:14px}nav{position:static}}
"""
SCRIPT = r"""
const DATA=JSON.parse(document.getElementById('packet').textContent);
const key=DATA.packet_identity+':'+DATA.phase;
const byId=id=>document.getElementById(id);
const e=(tag,text,cls)=>{const n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n};
let storageOK=true;
const fields=DATA.phase==='blind'?
 [['preference','更合适的回复',[['','请选择'],['A','A 更合适'],['B','B 更合适'],['tie','基本相当'],['uncertain','无法判断']]],
 ['risk_A','A 的事实／时序／主体／边界误用',[['','请选择'],['0','未发现'],['0.25','局部问题'],['1','实质问题'],['uncertain','无法判断']]],
 ['risk_B','B 的事实／时序／主体／边界误用',[['','请选择'],['0','未发现'],['0.25','局部问题'],['1','实质问题'],['uncertain','无法判断']]]]:
 [['score_review','对历史评分的核对',[['','请选择'],['reasonable','处理合理'],['missed','存在漏判／漏扣'],['overpenalized','存在误判／误扣'],['inconsistent','理由与量表或分数不一致'],['mixed','多类问题'],['uncertain','无法判断']]],
 ['reply_issue','回复本身是否有影响判断的缺陷',[['','请选择'],['yes','有'],['no','未发现'],['uncertain','无法判断']]]];
const common=[['reason','关键理由（无法判断时写出原因）'],['source_quote_ids','依据的来源ID与原文片段（如 C:T006、H002:T010；若无事实主张请说明）'],['uncertainty','歧义、证据不足或需保留的问题；无则填“无”'],['minutes','本题实际用时（分钟，可选）']];
function evidenceBlock(row,host){
 const ev=row.evidence;host.append(e('h3','当前对话 · 截止 '+ev.current_date));
 function turns(rows,parent){for(const t of rows)parent.append(e('div',t.id+' · '+t.role+'\n'+t.text,'turn'))}
 turns(ev.current_prefix,host);
 const history=e('section'),controls=e('div');
 const expand=e('button','展开全部历史来源');expand.type='button';expand.onclick=()=>history.querySelectorAll('details').forEach(x=>x.open=true);
 const collapse=e('button','收起历史来源');collapse.type='button';collapse.onclick=()=>history.querySelectorAll('details').forEach(x=>x.open=false);
 const search=e('input');search.type='text';search.placeholder='输入来源ID或英文短语，展开包含它的历史会话';search.setAttribute('aria-label',row.id+' 来源搜索');
 search.oninput=()=>{const q=search.value.trim().toLowerCase();if(q)history.querySelectorAll('details').forEach(d=>d.open=d.textContent.toLowerCase().includes(q))};
 controls.append(expand,collapse,search);host.append(e('h3','完整合法历史来源 · '+ev.legal_past_sessions.length+' 个会话'),controls);
 for(const s of ev.legal_past_sessions){const d=e('details');d.append(e('summary',s.id+' · '+s.date+' · '+s.turns.length+' 条话语'));const body=e('div');turns(s.turns,body);d.append(body);history.append(d)}
 host.append(history);
}
for(const row of DATA.rows){
 const card=e('article');card.id=row.id;card.append(e('h2',row.id));
 const replies=e('div',undefined,'replies');for(const [side,text] of Object.entries(row.replies)){const b=e('section');b.append(e('h3','回复 '+side),e('div',text,'reply'));replies.append(b)}card.append(replies);
 evidenceBlock(row,card);
 if(DATA.phase==='regression'){
  const ref=e('details');ref.open=true;ref.append(e('summary','既有问题与历史评分（已暴露的回归材料）'));
  ref.append(e('h3','历史评分使用的回复句段编号'));for(const u of row.response_units)ref.append(e('div',u.id+'\n'+u.text,'turn'));
  ref.append(e('p',row.reference.role+'：'+row.reference.target),e('p','依据性质：'+row.reference.reference_authority,'muted'));
  ref.append(e('p','这些说明不是完整人工金标；历史评分不是尚未执行的新 S/A 阶段结果。','note'));
  const score=row.historical_score;ref.append(e('p','历史 q = '+score.q+'；m = '+score.m),e('p','质量理由：'+score.q_rationale.reason));
  for(const a of score.assessments)ref.append(e('p',a.response_unit_id+' · '+a.relation+' · 程度 '+a.severity+' · 来源 '+a.source_turn_ids.join(', ')+'\n'+a.reason));
  const raw=e('details');raw.append(e('summary','查看完整原始评分JSON'),e('pre',JSON.stringify(score,null,2)));ref.append(raw);card.append(ref);
 }
 const form=e('section');form.append(e('h3','填写判断'));
 for(const [name,title,options] of fields){const label=e('label',title+' '),input=e('select');input.id=row.id+'_'+name;input.dataset.row=row.id;input.dataset.field=name;for(const [v,t] of options){const o=e('option',t);o.value=v;input.append(o)}label.append(input);form.append(label)}
 for(const [name,title] of common){const label=e('label',title),input=e(name==='minutes'?'input':'textarea');input.id=row.id+'_'+name;input.dataset.row=row.id;input.dataset.field=name;if(name==='minutes'){input.type='number';input.min='0';input.step='0.1'}label.append(input);form.append(label)}
 card.append(form);byId('cards').append(card);
 const a=e('a',row.id);a.href='#'+row.id;a.style.margin='8px';byId('jump').append(a);
}
function snapshot(){const rows=DATA.rows.map(r=>{const x={id:r.id};document.querySelectorAll('[data-row="'+r.id+'"]').forEach(n=>x[n.dataset.field]=n.value);return x});return {version:DATA.version,packet_identity:DATA.packet_identity,phase:DATA.phase,reviewer:byId('reviewer').value,independence_disclosure:byId('disclosure').value,exported_at:new Date().toISOString(),rows}}
function complete(r){return fields.every(([f])=>r[f]!=='')&&r.reason.trim()&&r.source_quote_ids.trim()&&r.uncertainty.trim()}
function update(){const s=snapshot();byId('progress').textContent=s.rows.filter(complete).length+'/'+s.rows.length+' 题字段已填齐（不代表已验收）';try{localStorage.setItem(key,JSON.stringify(s))}catch(err){storageOK=false}byId('storage').textContent=storageOK?'已在本浏览器暂存；离开前请导出JSON。':'浏览器无法暂存，请导出JSON保存，之后用“导入续填”恢复。'}
function restore(s){
 if(s.packet_identity!==DATA.packet_identity||s.phase!==DATA.phase||s.version!==DATA.version||!Array.isArray(s.rows)||s.rows.length!==DATA.rows.length||new Set(s.rows.map(r=>r.id)).size!==DATA.rows.length||s.rows.some(r=>!DATA.rows.some(d=>d.id===r.id)))throw Error('材料版本或题号不匹配，未导入');
 for(const r of s.rows){for(const [f,,opts] of fields)if(typeof r[f]!=='string'||!opts.some(o=>o[0]===r[f]))throw Error('选项无效，未导入');for(const [f] of common)if(typeof r[f]!=='string')throw Error('文本字段无效，未导入')}
 if(typeof s.reviewer!=='string'||typeof s.independence_disclosure!=='string')throw Error('评分者信息无效，未导入');
 byId('reviewer').value=s.reviewer;byId('disclosure').value=s.independence_disclosure;for(const r of s.rows)for(const [f] of [...fields,...common])byId(r.id+'_'+f).value=r[f];update();
}
byId('export').onclick=()=>{const blob=new Blob([JSON.stringify(snapshot(),null,2)],{type:'application/json;charset=utf-8'}),url=URL.createObjectURL(blob),a=e('a');a.href=url;a.download='PM_RL1_'+DATA.phase+'_'+new Date().toISOString().slice(0,10)+'.json';document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);byId('message').textContent='已导出。请保留原文件；未填题目仍为缺失。'};
byId('import').onchange=async event=>{try{const file=event.target.files[0];if(file){restore(JSON.parse(await file.text()));byId('message').textContent='已恢复填写。'}}catch(err){byId('message').textContent=err.message}event.target.value=''};
document.addEventListener('input',event=>{if(event.target.dataset.field||['reviewer','disclosure'].includes(event.target.id))update()});document.addEventListener('change',event=>{if(event.target.dataset.field)update()});
try{const saved=localStorage.getItem(key);if(saved)restore(JSON.parse(saved))}catch(err){byId('message').textContent='未恢复浏览器暂存：'+err.message}
update();document.body.dataset.ready='true';
"""


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n')


def page(title, body, data=None):
    script = '' if data is None else ('<script id="packet" type="application/json">'+
        json.dumps(data, ensure_ascii=False).replace('<', '\\u003c')+'</script><script>'+SCRIPT+'</script>')
    return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><style>'+STYLE+'</style><body>'+body+script+'</body></html>'


def review_page(data, title, intro):
    body='<nav><button id="export">导出填写结果 JSON</button><label style="display:inline">导入续填 <input id="import" type="file" accept=".json"></label> <span id="progress"></span></nav><main>'
    body+='<p><a href="00_先读说明.html">返回说明</a> · <a href="原评分指令_EN.txt">原完整评分指令</a></p><h1>'+title+'</h1><p>'+intro+'</p>'
    body+='<div class="box"><label>评分者姓名或稳定代号<input id="reviewer" type="text"></label><label>独立性／暴露说明：是否参与调规则、是否见过这些材料或模型评分、是否使用了其他工具<textarea id="disclosure"></textarea></label><p id="storage"></p><p id="message" role="status"></p></div><div id="jump"></div><div id="cards"></div></main>'
    return page(title, body, data)


def build(out, private):
    prep=PROJECT/'outputs/pm_rl1/completion_preparation_20261022'
    previous=PROJECT/'outputs/pm_rl1/judge_selection_preparation_20261014_v1/score_audit_validation_preparation_20261022_v1'
    read=lambda p:json.loads(p.read_text())
    paths=[prep/'stage_materials_private.json',prep/'development_pairs_private.json',prep/'STAGE_MATERIALS.json',
           prep/'primary_requests_private.json',previous/'historical_scores_private.json',previous/'LOCAL_REFERENCE_NOTES.json',
           previous/'inputs_private.json',previous/'LOCAL_REFERENCE_PROVENANCE.json']
    sources={str(p):sha(p) for p in paths}
    materials={x['key']:x for x in read(paths[0])};pairs=read(paths[1]);manifest=read(paths[2]);requests={x['identity']:x for x in read(paths[3])}
    scores=read(paths[4]);notes=read(paths[5])['items'];old_inputs=read(paths[6])
    for path,expected in read(paths[7])['paths'].items():
        if sha(path)!=expected:raise ValueError('historical reference source changed')
        sources[path]=expected
    if len(materials)!=22 or len(pairs)!=8:raise ValueError('unexpected existing stage scope')
    mappings={m['material_key']:m['request_identity'] for m in manifest['mapping']}
    rubric=None
    for k,item in materials.items():
        r=requests[mappings[k]];data=json.loads(r['wire_body']['messages'][1]['content'])
        if data['reply']!=item['reply'] or data['legal_evidence']!=item['evidence']:raise ValueError('stage source differs')
        text=r['wire_body']['messages'][0]['content'].split('\nOUTPUT CONTRACT pmrl1-primary-full-schema-v1:\n')[0]
        if hashlib.sha256(text.encode()).hexdigest()!=manifest['single_prompt_sha256']:raise ValueError('rubric mismatch')
        if rubric is not None and rubric!=text:raise ValueError('multiple rubrics')
        rubric=text
    packet=digest(dict(version=VERSION,sources=sources,builder=sha(Path(__file__))))
    blind=[];regression=[];mapping=[]
    swaps=set(sorted(range(8),key=lambda n:digest([VERSION,'presentation',pairs[n]['prefix_identity']]))[:4])
    for i,p in enumerate(pairs):
        order=[1,0] if i in swaps else [0,1];rid=f'D{i+1:02d}'
        for side in range(2):
            item=materials[f'newdev_{i+1:02d}_{side}']
            if item['reply']!=p['replies'][side] or item['evidence']!=p['evidence']:raise ValueError('pair binding mismatch')
        blind.append(dict(id=rid,evidence=p['evidence'],replies={s:p['replies'][j] for s,j in zip('AB',order)}))
        for s,j in zip('AB',order):mapping.append(dict(display_id=rid,side=s,material_key=f'newdev_{i+1:02d}_{j}',primary_request_identity=mappings[f'newdev_{i+1:02d}_{j}']))
    for i,k in enumerate(sorted(scores)):
        item=materials[k];rid=f'K{i+1:02d}'
        if old_inputs[k]!={f:item[f] for f in ('reply','evidence')}:raise ValueError('regression source changed')
        if not scores[k]['technical_valid']:raise ValueError('invalid historical score')
        units=json.loads(requests[mappings[k]]['wire_body']['messages'][1]['content'])['response_units']
        regression.append(dict(id=rid,evidence=item['evidence'],replies={'待核对':item['reply']},
            response_units=units,reference=notes[k],historical_score=scores[k]['evaluation']['value']))
        mapping.append(dict(display_id=rid,side='',material_key=k,primary_request_identity=mappings[k],historical_score_identity=digest(scores[k]['evaluation']['value'])))
    out.mkdir(parents=True,exist_ok=False);private.mkdir(parents=True,exist_ok=False,mode=0o700)
    (out/'原评分指令_EN.txt').write_text(rubric)
    for phase,rows,title,name,intro in [
        ('blind',blind,'第一部分：8对新开发回复','01_新开发盲评.html','请先完成并导出本页，再打开第二部分。A/B均衡呈现，不显示资源条件或自动评分。所有判断都可填“无法判断”。新开发材料不是未见验证集或最终test。'),
        ('regression',regression,'第二部分：6条已知问题回归','02_已知问题核验.html','请先完成并导出第一部分。本页包含已暴露的历史评分与既有问题说明，不算独立盲评；核对回复缺陷与评分处理是否有误，不重复回答已确认的身份问题。')]:
        data=dict(version=VERSION,packet_identity=packet,phase=phase,rows=rows)
        (out/name).write_text(review_page(data,title,intro))
    with (out/'03_新评分依据核验_待补材料.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['核验编号','显示题号','回复侧','当前状态','新评分身份','评分是否合理','回复缺陷与评分错误区别','审查新增纠错或误罚','来源ID与原文','无法判断原因','核验者','分钟'])
        for i,m in enumerate(mapping):w.writerow([f'S{i+1:02d}',m['display_id'],m['side'],'PENDING_NEW_STAGE_SCORES']+['']*8)
    guide="""<main><h1>PM-RL1 人评材料</h1><p>本包是当前开发核验材料：8对新开发回复和6条已知问题回归，可以分次填写并交回。</p>
<div class="box"><h2>按这个顺序填写</h2><ol><li>打开 <a href="01_新开发盲评.html">第一部分：8对新开发回复</a>。先看当前对话与截止日期，再按需要核对完整合法历史，选偏好、分别判断A/B误用并写依据。完成后点击“导出填写结果 JSON”。</li><li>再打开 <a href="02_已知问题核验.html">第二部分：6条已知问题回归</a>，核对回复与历史评分依据并导出JSON。问题说明含已有局部研究者意见和Codex分析，均未提供完整唯一金标。</li><li>把两份导出的JSON原文件发回本对话。可分批交回；未填和“无法判断”都保留，不能计为无错误。换设备续填时，用对应页面“导入续填”。</li></ol></div>
<div class="box"><h2>判断规则</h2><p>只评最后一条用户话语之后的新回复，先前支持者话语是背景。当前明确修正优先于旧状态；支持者的建议或自身经历不是用户的确认。问题也可能带事实预设，但普通邀请、假设或共情并不自动构成个人事实断言。新的AI可以引用旧支持者的经验，但不能把它说成自己的；这项身份规则已经确认，无需重新选择研究定义。</p><p>质量q原尺度为0–4：严重不适配；主要缺陷损害多数支持；基本回应但漏掉重要需求；恰当连贯且无重要缺陷；充分满足当前这一步的需要。短回复也可充分满足需要，不因更长、建议更多或显示记忆而加分。本包第一部分只需偏好和风险判断，无需额外重打全部q。</p><p>误用m为0（未发现）、0.25（局部且不改变核心理解/建议）、1（实质误用）。无法判断是缺失/未决，不是0。没在当前对话出现的事实可能有历史依据；“没有支持”应以完整合法来源为范围。回复有缺陷不等于模型漏扣，原评分可能已处理。事实错误、严重度和q应分别说明。</p><p><a href="原评分指令_EN.txt">原完整英文评分指令</a>与已有阶段请求逐字一致，包含既定澄清及模型输出约定。英文回复与来源保持原文，未生成可能改变歧义的翻译。你可以用中文填写理由，不需按模型JSON格式作答。如规则仍有真实歧义，写下两种读法，不强行猜唯一分数。</p></div>
<div class="box"><h2>现在能做与待补齐部分</h2><table><tr><th>部分</th><th>现在的材料</th><th>用途</th></tr><tr><td>8对新开发</td><td>16条回复与完整来源，可填写</td><td>不见自动分数的偏好/风险参照；已有开发暴露，非独立终评</td></tr><tr><td>6条回归</td><td>回复、来源、既有问题、历史评分，可填写</td><td>已有问题核验，不算新增独立场景</td></tr><tr><td>22条新评分依据</td><td><a href="03_新评分依据核验_待补材料.csv">待补材料清单</a>；新评分/审查尚未产生</td><td>以后收到真实输出再核验，不用6条旧评分替代新阶段结果</td></tr></table><p>原阶段总人力估计约2.7–7.8小时，包含未来22条评分依据核对，不是现在14题的必需完成时长。请记录实际时间，允许分次完成。此前旧资格卷不要求重填；最终48对盲评尚无策略结果，本包没有伪造那些材料，也没有打开旧封存标签或最终test。</p></div>
<p class="note">本页为本地离线工具，不会自动发送答案。浏览器暂存只作方便，离开前请导出文件。独立性按实际记录：看过模型分数、参与过规则讨论或借助了AI，都请在“独立性／暴露说明”中写明。无需追求所有题都有确定答案。</p></main>"""
    (out/'00_先读说明.html').write_text(page('PM-RL1 人评说明',guide))
    (out/'打开方式.txt').write_text('解压整个文件夹，双击00_先读说明.html。按第一部分、第二部分顺序填写并分别导出JSON。可断网使用。第三部分待新阶段评分产生后补齐。\n')
    write_json(private/'COORDINATOR_MAPPING_PRIVATE.json',dict(packet_identity=packet,mapping=mapping,sources=sources,A_OFF_count=4,B_OFF_count=4))
    files={p.name:sha(p) for p in sorted(out.iterdir())}
    delivery=dict(version=VERSION,packet_identity=packet,blind_pairs=8,regressions=6,pending_basis_reviews=22,
        source_and_reply_text_unchanged=True,independent_validation=False,final_evaluation=False,
        human_labels_collected=0,new_model_calls=0,new_cost_usd='0',files=files,
        coordinator_mapping_distributed=False,reviewer_assigned=False)
    write_json(out/'MANIFEST.json',delivery);write_json(private/'DELIVERY.json',delivery)
    archive=out.with_suffix('.zip')
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED) as z:
        for p in sorted(out.iterdir()):z.write(p,out.name+'/'+p.name)
    for p in private.iterdir():p.chmod(0o600)
    return dict(delivery,zip_path=str(archive),zip_sha256=sha(archive))


if __name__=='__main__':
    ap=argparse.ArgumentParser(__doc__);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--private',type=Path,required=True)
    a=ap.parse_args();print(json.dumps(build(a.out,a.private),ensure_ascii=False,indent=2))
