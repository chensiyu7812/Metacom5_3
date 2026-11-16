"""Render local, self-contained review packet from completed read-only exports."""
from pathlib import Path
import html
import json

P=Path(__file__).resolve().parent
PREP=P.parent/'task_reference_preparation_20261021_v1'
def read(p): return json.loads(p.read_text())
def esc(s): return html.escape(str(s))
def pretty(x): return json.dumps(x,ensure_ascii=False,indent=2)
def table(headers,rows):
    return '<table><thead><tr>'+''.join('<th>'+esc(x)+'</th>' for x in headers)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+esc(x)+'</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table>'
report=read(P/'runtime_summary.json');reviews=read(P/'ANALYST_REVIEWS.json');items=read(PREP/'inputs_private.json')
review_by={r['slot_id']:r for r in reviews['records']}
parts=['<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PM-RL1 共享任务参照结果</title><style>body{font:17px/1.7 system-ui,sans-serif;max-width:1100px;margin:30px auto;padding:0 20px;color:#202830}h1,h2,h3{line-height:1.3}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#f4f6f8;padding:16px;border-radius:8px}table{border-collapse:collapse;width:100%;font-size:14px}th,td{border:1px solid #cbd4dd;padding:7px;vertical-align:top}th{background:#eaf0f5}details{margin:14px 0;border:1px solid #d8dfe5;padding:12px;border-radius:8px}summary{cursor:pointer;font-weight:bold}.warn{padding:12px;background:#fff2ce}a{color:#185b8a}.summary{font-family:inherit;background:#f0f6f8}</style><h1>PM-RL1：共享任务参照A/B结果</h1>']
parts+=['<p class="warn">本批是已暴露材料上的开发诊断；分析者复核不是新增独立人评。旧成绩及STOP保留，本批不授予奖励资格。</p>','<p><a href="REPORT_ZH.md">中文报告</a> · <a href="SLOT_RESULTS.csv">逐项CSV</a> · <a href="ALL_PUBLIC_FINALS.md">全部完整final</a> · <a href="PREDECLARED_EXIT_RESULT.json">预定分支判读</a></p>','<pre class="summary">'+esc((P/'REPORT_ZH.md').read_text())+'</pre>','<h2>全部计划槽位</h2>']
rows=[]
for s in report['slots']:
    r=s.get('result') or {};e=r.get('evaluation') or {};v=review_by.get(s['slot_id'],{})
    rows.append([s['position'],s['material_id'],s['arm'],s['repetition'],s['state'],e.get('q'),e.get('m'),e.get('U'),v.get('task_basis_status'),v.get('relation_status')])
parts.append(table(['序号','回复','臂','重复','交付','q','m','U','任务理由','关系核查'],rows))
parts.append('<h2>逐项原文与核对</h2>')
for s in report['slots']:
    r=s.get('result') or {};e=r.get('evaluation') or {};v=review_by.get(s['slot_id'],{})
    name=f"{s['position']:02d}_{s['material_id']}_{s['arm']}_r{s['repetition']}.txt"
    final=(P/'public_finals'/name).read_text() if (P/'public_finals'/name).exists() else '没有完整final；保持缺测。'
    parts+=['<details><summary>'+esc(f"{s['position']:02d} {s['material_id']} / {s['arm']} / r{s['repetition']} — q/m/U {e.get('q')}/{e.get('m')}/{e.get('U')}")+'</summary>',
        '<h3>完整待评回复</h3><pre>'+esc(items[s['material_id']]['reply'])+'</pre>',
        '<h3>分析者复核（不改原分）</h3><p>'+esc(v.get('note_zh','未完成'))+'</p>',
        '<pre>'+esc(pretty(v))+'</pre>',
        '<h3>模型完整final</h3><pre>'+esc(final)+'</pre>',
        '<details><summary>输入、来源和请求绑定</summary><pre>'+esc(pretty({k:s[k] for k in ('slot_id','reply_identity','evidence_identity')}|{'request_identity':r.get('request_identity')}))+'</pre></details></details>']
parts.append('<h2>12条原回复及完整合法来源</h2><p>同情境不同回复共用来源，重复不是新病例。保留原英文与稳定ID，未读取新封存材料。</p>')
for k,item in items.items():
    parts.append('<details><summary>'+esc(k)+'</summary><pre>'+esc(pretty(item))+'</pre></details>')
parts.append('</html>')
with (P/'RESULTS_READER_ZH.html').open('x') as f:f.write('\n'.join(parts))
