"""One stable blind form; exact old pair/evidence reuse, no wait-price questions."""
import html,json,random,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.durable import save_json_once as save
BASE=PROJECT/'outputs/pm_rl1';ROOT=BASE/'alternate_executor_probe_20261104_v1';PRIOR=BASE/'resource_value_probe_20261104_v1'
read=lambda p:json.loads(p.read_text())


def main():
    results=read(ROOT/'RESULTS_PRIVATE.json');inventory={x['case']:x for x in read(PRIOR/'INVENTORY_PRIVATE.json')}
    inputs=read(ROOT/'INPUTS_PRIVATE.json');old=read(PRIOR/'ANSWER_REGISTRY_PRIVATE.json');pairs=[];skipped=[]
    excluded={(x['case'],x['arm']) for x in read(ROOT/'CONTENT_REVIEW_PRIVATE.json')['format_failures']}
    def add(case,arm,other,kind):
        left=next(r for r in results if r['case']==case and r['arm']==arm)
        right=next(r for r in results if r['case']==case and r['arm']==other)
        a=left['new_reply'];b=right['old_reply'] if kind=='OFF_cross_G' else right['new_reply']
        assert left['finish_reason']==right['finish_reason']=='natural_stop'
        off=inputs[next(r for r in results if r['case']==case and r['arm']=='A_OFF')['input_identity']]['messages']
        context=json.loads(off[0]['content'].split('<quoted_conversation_context>\n')[1].split('\n</quoted_conversation_context>')[0])
        evidence=dict(current_prefix=context+[dict(speaker='seeker',text=off[1]['content'])],
                      legal_past_source=inventory[case].get('target_source'),scope='past source, not a current status or private personality gold')
        reused=[h['record_id'] for h in old if sorted(h.get('reply_identities',[]))==sorted([digest(a),digest(b)]) and h.get('evidence')==evidence]
        row=dict(case=case,kind=kind,left_arm=arm,right_arm=other,left_model='alternate',
                 right_model='original' if kind=='OFF_cross_G' else 'alternate',left=a,right=b,evidence=evidence,reused=reused)
        if (case,arm) in excluded:skipped.append(dict(**row,reason='technical_format_failure_not_zero_gain'));return
        if a==b or reused:skipped.append(dict(**row,reason='identical_text' if a==b else 'exact_old_reference'));return
        pairs.append(row)
    for case in sorted({r['case'] for r in results if r['arm']=='C_target_full_MS'}):add(case,'C_target_full_MS','A_OFF','within_G_resource')
    for case in ('N18','N21'):add(case,'A_OFF','A_OFF','OFF_cross_G')
    rng=random.Random(20261104);rng.shuffle(pairs);display=[];private=[]
    for i,row in enumerate(pairs,1):
        reverse=bool(rng.randrange(2));a,b=(row['right'],row['left']) if reverse else (row['left'],row['right'])
        qid=f'G{i:02d}';display.append(dict(id=qid,A=a,B=b,evidence=row['evidence']))
        private.append(dict(**row,id=qid,reverse=reverse,A_identity=digest(a),B_identity=digest(b),evidence_identity=digest(row['evidence'])))
    save(ROOT/'HUMAN_PAIRS_PRIVATE.json',private);save(ROOT/'HUMAN_PAIRS_SKIPPED_PRIVATE.json',skipped)
    e=lambda x:html.escape(x if isinstance(x,str) else json.dumps(x,ensure_ascii=False,indent=2))
    parts=['<!doctype html><html lang="zh"><meta charset="utf-8"><title>新回复盲评</title><style>body{font:17px/1.7 system-ui;max-width:1150px;margin:30px auto;padding:0 16px;background:#f5f7fa}article{background:white;margin:24px 0;padding:24px;border:1px solid #ccc}.pair{display:grid;grid-template-columns:1fr 1fr;gap:24px}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:95%;min-height:65px}button,select{font:inherit}#status{position:sticky;top:0;background:#fff;padding:10px}@media(max-width:750px){.pair{display:block}}</style>',
      '<h1>新回复盲评</h1><p>这些是新输出，已排除完全相同回复及精确匹配的旧判断。旧原则继续沿用：真实历史不是自动加分；建议与澄清可以同样合理；略好与实质改善分开。请按当前顾虑判断哪条更有帮助，不因更长、更多建议或记忆展示而加分。合法历史供核对，过去报告不表示现在仍然成立。此页不问等待时间，不要求q/m。</p>',
      '<p>内容均为完整原文。原计划中1对有已确认格式失败，单独保留，不请你重复判断技术错误，也不算零收益。其余材料用于病例诊断，尚不能证明候选模型整体更强。可以在此选择并导出答案，也可直接在对话里回复“G01：相当，原因……”；不确定或暂未回答都保留，不强行选边。网页答案仅保存在当前浏览器，导出后才有JSON文件。</p><div id="status"></div>']
    choices=['未回答','A实质更好','A略好','相当','B略好','B实质更好','不确定']
    for q in display:
        ev=q['evidence'];past=ev['legal_past_source'];turns=past.get('turns',[]) if past else []
        history='\n'.join(t['role']+': '+t['text'] for t in turns)
        current='\n'.join(t['speaker']+': '+t['text'] for t in ev['current_prefix'])
        parts.append('<article id="'+q['id']+'"><h2>'+q['id']+'</h2><details open><summary>当前对话</summary><pre>'+e(current)+'</pre></details><details><summary>合法历史（可选核对；同样适用于两条评价）</summary><pre>'+e(history)+'</pre></details><div class="pair"><section><h3>A</h3><pre>'+e(q['A'])+'</pre></section><section><h3>B</h3><pre>'+e(q['B'])+'</pre></section></div><select data-id="'+q['id']+'">'+''.join('<option>'+s+'</option>' for s in choices)+'</select><p>一句关键理由即可：</p><textarea data-id="'+q['id']+'"></textarea></article>')
    key='pmrl1-alternate-'+read(ROOT/'PROTOCOL.json')['identity'];ids=[q['id'] for q in display]
    script='''<button onclick="download()">导出已填答案JSON</button><script>
const KEY=__KEY__,IDS=__IDS__;let answers={};try{answers=JSON.parse(localStorage.getItem(KEY)||'{}')}catch(e){}
function persist(){localStorage.setItem(KEY,JSON.stringify(answers));document.getElementById('status').textContent='已回答 '+IDS.filter(id=>answers[id]?.choice&&answers[id].choice!=='未回答').length+' / '+IDS.length+'；可随时导出或在对话中回答。'}
document.querySelectorAll('select,textarea').forEach(el=>{const id=el.dataset.id,k=el.tagName==='SELECT'?'choice':'reason';el.value=answers[id]?.[k]||(k==='choice'?'未回答':'');el.addEventListener('input',()=>{answers[id]??={};answers[id][k]=el.value;persist()})});persist();
function download(){const blob=new Blob([JSON.stringify({study:KEY,answers},null,2)],{type:'application/json'});const u=URL.createObjectURL(blob),a=document.createElement('a');a.href=u;a.download='PM_RL1_G_PROBE_20261104_ANSWERS.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
</script></html>'''.replace('__KEY__',json.dumps(key)).replace('__IDS__',json.dumps(ids))
    (ROOT/'HUMAN_REVIEW_ZH.html').write_text('\n'.join(parts)+script)
    print(json.dumps(dict(new_blind_pairs=len(private),skipped=len(skipped),human_answers_received=0)))


if __name__=='__main__':main()
