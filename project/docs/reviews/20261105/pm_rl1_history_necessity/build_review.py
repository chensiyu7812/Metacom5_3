"""Build one bounded blind packet, preserving exact old judgments separately."""
import html
import json
from pathlib import Path
import random
import sys

PROJECT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT / 'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.calibration_workflow import stamp, verify_identity
from metacom_pm.rl1.durable import save_json_once as save
from metacom_pm.rl1.schema import digest

OUT = PROJECT / 'outputs/pm_rl1/history_necessity_probe_20261105_v1'
REGISTRY = PROJECT / 'outputs/pm_rl1/incremental_help_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json'
read = lambda p: json.loads(p.read_text())
esc = html.escape


def norm(turns):
    return [(t.get('role', t.get('speaker')), t.get('text', t.get('content'))) for t in turns]


def main():
    selected = read(OUT / 'SELECTION_PRIVATE.json'); verify_identity(selected)
    results = {(r['case'], r['arm']): r for r in read(OUT / 'RESULTS_PRIVATE.json')}
    translations = read(OUT / 'TRANSLATIONS_PRIVATE.json')
    histories = read(OUT / 'HISTORY_SUMMARIES_PRIVATE.json')
    registry = read(REGISTRY); assert len(registry) == 45
    reused = {}
    for row in selected['cases']:
        c = row['case']
        hashes = {results[c, arm]['raw']['text_identity'] for arm in ('OFF', 'C')}
        for old in registry:
            ids = old.get('reply_identities', [])
            if isinstance(ids, dict): ids = list(ids.values())
            if set(ids) != hashes: continue
            evidence = old['evidence']
            assert norm(evidence['current_prefix']) == norm(row['prefix']['turns'])
            past = evidence['legal_past_source']
            assert '\n'.join(f'{role}: {text}' for role, text in norm(past['turns'])) == row['C']['search_text']
            assert past['date'] == row['C']['reported_at']
            for arm in ('OFF', 'C'):
                raw = results[c, arm]['raw']
                assert old['replies'][raw['text_identity']] == raw['text']
            assert old['direction'] in ('tie', 'resource_slightly_preferred')
            reused[c] = dict(record=old, registry=str(REGISTRY.resolve()), registry_sha256=sha(REGISTRY),
                C_over_OFF=0 if old['direction'] == 'tie' else 1,
                evidence_scope='Original exact current + target source retained; not relabeled as a newly judged expanded-history comparison.')
    assert set(reused) == {'H34', 'H79'}
    save(OUT / 'REUSED_HUMAN_PRIVATE.json', reused)
    cases = list(selected['cases']); rng = random.Random(20261105); rng.shuffle(cases)
    mappings, sections = [], []
    for number, row in enumerate(cases, 1):
        case = row['case']; qid = f'Q{number:02d}'
        arms = ['C', 'D'] if case in reused else ['OFF', 'C', 'D']; rng.shuffle(arms)
        if not all(results[case, a]['valid'] for a in arms):
            raise ValueError('Technical missing stays missing; do not substitute another case')
        mapping = dict(question=qid, case=case, owner=row['owner'], mode='pair' if case in reused else 'rank',
            display={label: dict(arm=arm, reply_identity=results[case, arm]['raw']['text_identity'])
                     for label, arm in zip('ABC', arms)}, reused_record=reused.get(case, {}).get('record', {}).get('record_id'))
        mappings.append(mapping)
        parts = [f'<section id="{qid}"><h2>{qid}</h2><p class="current">{esc(translations[case]["current_zh"])}</p>',
            '<details><summary>完整当前对话（英文原文）</summary><pre>' + esc('\n'.join(f'{role}: {text}' for role, text in norm(row['prefix']['turns']))) + '</pre></details>',
            '<details><summary>共同历史依据：两段合法过去记录（含中文摘要与完整原文）</summary><p>这些是过去的记录。状态可能变化；提出过的计划不代表已执行。历史支持者的话不是当前 AI 的个人经历。</p>']
        for source in sorted((row['C'], row['D']), key=lambda r: (r['reported_at'], r['key'])):
            sid = source['source_ids'][0]
            parts.append(f'<h3>{esc(source["reported_at"])}</h3><p>{esc(histories[sid])}</p><details><summary>本段完整英文</summary><pre>{esc(source["search_text"])}</pre></details>')
        parts.append('</details>')
        if case in reused:
            parts.append('<p class="note">本情境已有一项比较与你的旧回答精确对应，已复用。这里只补另一项比较，不需要重答旧题。</p>')
        parts.append('<div class="responses">')
        for label, arm in zip('ABC', arms):
            tr = translations[case]['replies'][arm]; raw = results[case, arm]['raw']
            assert tr['text_en'] == raw['text'] and tr['reply_identity'] == raw['text_identity']
            parts.append(f'<article><h3>回复 {label}</h3><div class="reply">{esc(tr["text_zh"])}</div><details><summary>英文原文</summary><pre>{esc(raw["text"])}</pre></details></article>')
        parts.append('</div>')
        orders = (['A=B', 'A>B', 'B>A', '不确定'] if len(arms) == 2 else
            ['A=B=C', 'A>B=C', 'B>A=C', 'C>A=B', 'A=B>C', 'A=C>B', 'B=C>A',
             'A>B>C', 'A>C>B', 'B>A>C', 'B>C>A', 'C>A>B', 'C>B>A', '不确定'])
        options = ''.join(f'<option value="{esc(s)}">{esc(s)}</option>' for s in orders)
        parts.append(f'<label for="{qid}-order">实际帮助的顺序（&gt; 表示更好，= 表示相当）</label><select id="{qid}-order" data-field="order"><option value="">尚未填写</option>{options}</select>')
        parts.append(f'<label for="{qid}-degree">如果有差别，整体程度</label><select id="{qid}-degree" data-field="degree"><option value="">可不填</option><option>略好</option><option>有实质改善</option><option>不同两条之间程度不同，见理由</option><option>不确定</option></select>')
        parts.append(f'<label for="{qid}-reason">一句主要理由；若有事实错误或不同策略都合适，也可写在这里</label><textarea id="{qid}-reason" data-field="reason" rows="3"></textarea></section>')
        sections.append('\n'.join(parts))
    packet = stamp(dict(selection_identity=selected['identity'], mapping=mappings,
        reused_human_identity=digest(reused), source_hashes={str(p.resolve()): sha(p) for p in
            [OUT / 'SELECTION_PRIVATE.json', OUT / 'RESULTS_PRIVATE.json', OUT / 'TRANSLATIONS_PRIVATE.json',
             OUT / 'HISTORY_SUMMARIES_PRIVATE.json', OUT / 'REUSED_HUMAN_PRIVATE.json', REGISTRY]},
        instructions='Actual helpfulness; ties/uncertainty allowed. Do not reward historical mention itself. No q/m, wait tradeoff or reward label.',
        primary_relations=['C/OFF', 'C/D'], secondary_relation='D/OFF when a full rank is provided',
        translation='Assistant prepared Chinese reading translations, original English retained. Current/history Chinese are summaries, not replacement source transcripts.'))
    save(OUT / 'HUMAN_PACKET_PRIVATE.json', packet)
    public = json.dumps(dict(study=packet['identity'], questions=[m['question'] for m in mappings]), ensure_ascii=False)
    template = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>PM-RL1：有界历史信息帮助性比较</title><style>
body{font:17px/1.7 system-ui,sans-serif;max-width:1250px;margin:auto;padding:24px;background:#f5f7fa;color:#203047}h1{font-size:27px}h2{font-size:22px}h3{font-size:18px}section{background:white;border:1px solid #dbe2eb;border-radius:12px;margin:24px 0;padding:22px}.current{background:#edf3fa;padding:14px}.responses{display:grid;grid-template-columns:repeat(auto-fit,minmax(270px,1fr));gap:16px;margin:16px 0}article{border:1px solid #d3dce7;border-radius:8px;padding:16px}.reply,pre{white-space:pre-wrap;overflow-wrap:anywhere}pre{font:14px/1.65 system-ui,sans-serif}details{margin:10px 0}summary{cursor:pointer;color:#28598b}.note{color:#4d647b}label{display:block;margin-top:14px}select,textarea,button{font:inherit;padding:10px;box-sizing:border-box}textarea{width:100%}select{max-width:100%}button{cursor:pointer;margin:5px;background:#fff;border:1px solid #7f95ac;border-radius:6px}.toolbar{position:sticky;top:0;background:#f5f7faf5;padding:10px;border-bottom:1px solid #ccd7e5;z-index:1}#export{width:100%;height:170px}small{color:#506479}
</style><h1>10 个情境：历史信息是否增加了实际帮助</h1>
<p>请按对当前用户的实际帮助比较。不同支持策略都可以，完全可以判相当；引用了真实历史本身不加分。无需打分，也无需判断愿意等几秒。</p>
<p>8 个情境各有三条回复，请选一个允许并列的顺序；另 2 个情境已复用旧回答，只显示尚需比较的两条。显示字母已打乱，不表示模型或输入条件。可分批填写。</p>
<p>当前情况与回复提供中文；完整英文和共同历史均可展开。中文译文如影响判断，可选“不确定”并指出。这里的判断不会直接写成 PPO 奖励。</p>
<div class="toolbar"><strong id="progress"></strong> <button id="download">下载已填答案 JSON</button><button id="show">显示可复制答案</button><small id="saved"></small></div>
__SECTIONS__
<p>请把下载或复制的 JSON 发回对话。页面本身不会向外发送答案；浏览器内保存仅供续填。</p><textarea id="export" hidden aria-label="可复制的答案 JSON"></textarea>
<script>const packet=__PUBLIC__;const key='pmrl1-history-'+packet.study;
function answers(){const data={};for(const id of packet.questions){const s=document.getElementById(id);const v={};s.querySelectorAll('[data-field]').forEach(e=>v[e.dataset.field]=e.value);if(v.order||v.reason)data[id]=v;}return data;}
function payload(){return JSON.stringify({study:packet.study,answers:answers()},null,2);}
function update(){const a=answers();document.getElementById('progress').textContent=`已填写 ${Object.values(a).filter(v=>v.order).length} / ${packet.questions.length}`;try{localStorage.setItem(key,JSON.stringify(a));document.getElementById('saved').textContent='本机浏览器已保存';}catch(e){document.getElementById('saved').textContent='浏览器保存不可用，请下载或复制答案';}}
try{const a=JSON.parse(localStorage.getItem(key)||'{}');for(const [id,v] of Object.entries(a)){const s=document.getElementById(id);if(s)s.querySelectorAll('[data-field]').forEach(e=>e.value=v[e.dataset.field]||'');}}catch(e){}
document.querySelectorAll('[data-field]').forEach(e=>e.addEventListener('input',update));
document.getElementById('show').onclick=()=>{const e=document.getElementById('export');e.hidden=false;e.value=payload();e.focus();e.select();};
document.getElementById('download').onclick=()=>{const u=URL.createObjectURL(new Blob([payload()],{type:'application/json'}));const a=document.createElement('a');a.href=u;a.download='pmrl1-history-answers.json';a.click();setTimeout(()=>URL.revokeObjectURL(u),1000);};update();</script></html>'''
    path = OUT / 'HUMAN_REVIEW_ZH.html'; assert not path.exists()
    path.write_text(template.replace('__SECTIONS__', '\n'.join(sections)).replace('__PUBLIC__', public))
    print(json.dumps(dict(questions=len(mappings), triplets=8, new_pair_questions=2, old_pairs_reused=2, study=packet['identity'])))


if __name__ == '__main__': main()
