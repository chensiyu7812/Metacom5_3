"""One new, exact-bound question after content review; no old questions repeated."""
import hashlib,html,json,random
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[4];BASE=PROJECT/'outputs/pm_rl1';ROOT=BASE/'incremental_help_probe_20261105_v1'
def read(p):return json.loads(p.read_text())
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def main():
    results=read(ROOT/'RESULTS_PRIVATE.json');inputs=read(ROOT/'INPUTS_PRIVATE.json')
    on=next(r for r in results if r['case']=='N06' and r['generator']=='alternate' and r['arm']=='REAL_MS_PATH')
    off=next(r for r in results if r['case']=='N06' and r['generator']=='alternate' and r['arm']=='OFF')
    op=next(r for r in read(BASE/'feedback_and_opportunity_20261105_v1/OPPORTUNITIES_PRIVATE.json') if r['case']=='N06')
    src=read(Path(op['current_source_file']));stored=read(Path(src['stored_source_path']));mem={x['key']:x for x in stored['memory']}
    sources=[]
    for k in on['acquisition_order']:
        item=mem[k];text=json.loads(item['content'])['full_source_conversation']
        matches=[s for s in src['evidence']['legal_past_sessions'] if s['date']==item['reported_at'] and '\n'.join(t['role']+': '+t['text'] for t in s['turns'])==text]
        assert len(matches)==1;sources.append(matches[0])
    assert len(sources)==4
    evidence=dict(current_date=src['evidence']['current_date'],current_prefix=src['evidence']['current_prefix'],legal_past_sessions=sources)
    previous=read(BASE/'alternate_executor_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json')
    old_exact=[r['asset_id'] for r in previous if set(r.get('reply_identities',[]))=={on['reply_identity'],off['reply_identity']}]
    assert not old_exact
    translations={
      'REAL_MS_PATH':'你现在对是否承诺参与研究感到犹豫，是可以理解的，尤其是你一直头痛、疲惫。在承担额外责任之前，你的身心状态必须放在首位。\n\n你之前提到担心无法平衡工作量，也不想放弃那些让你更开心的事情。那么，对于和导师谈谈、争取更灵活的安排，你现在感觉怎么样？',
      'OFF':'听起来社团现在为你提供了一个有帮助的出口。至于研究机会，当健康问题已经让你难以专注于现有课程时，你会犹豫要不要再承担新任务，是可以理解的。\n\n你说过身体状况没有自行好转。在决定是否参与研究之前，你有没有考虑过，可以采取哪些具体步骤来应对头痛和疲惫？'}
    reverse=random.Random(20261105).choice([False,True]);a,b=(off,on) if reverse else (on,off)
    pair=dict(question='V01',case='N06',study='pmrl1-incremental-'+read(ROOT/'STUDY.json')['identity'],
        A=a,B=b,evidence=evidence,evidence_identity=digest(evidence),translations={label:translations[r['arm']] for label,r in [('A',a),('B',b)]},
        translation_origin='assistant translation for convenience; exact English replies authoritative',
        selection='Post-generation mechanism diagnostic: N06 changes a specific support option in both target-only and legal path. N13 did not show the hypothesized constraint use; all outputs retained. Not an unbiased success-rate sample.',
        old_exact_matches=old_exact,helpfulness=None,numeric_reward=None)
    pair['identity']=digest(pair)
    with (ROOT/'HUMAN_PAIR_PRIVATE.json').open('x') as f:json.dump(pair,f,ensure_ascii=False,indent=2);f.write('\n')
    esc=html.escape
    page='<!doctype html><html lang="zh"><meta charset="utf-8"><title>PM-RL1 V01 新比较</title><style>body{max-width:980px;margin:36px auto;padding:0 20px;line-height:1.75;font-family:sans-serif}pre{white-space:pre-wrap;padding:16px;background:#f3f5f7}details{margin:18px 0}</style><h1>V01：研究机会与当前精力</h1><p>这是新回复，不是重发旧8对。只判断帮助本身；不需打q/m，也不需回答等待几秒。可选A/B略好、A/B有实质改善、相当、不确定。历史被正确提到本身不加分；不同合理策略均可接受。</p>'
    for label,r in [('A',a),('B',b)]:page+='<h2>'+label+'</h2><pre>'+esc(r['reply'])+'</pre><p>便于阅读的中文译文（以英文原文为准）：</p><pre>'+esc(translations[r['arm']])+'</pre>'
    page+='<details open><summary>完整当前对话</summary><pre>'+esc('\n\n'.join(t['id']+' '+t['role']+': '+t['text'] for t in evidence['current_prefix']))+'</pre></details>'
    page+='<p>以下是这次比较对应的全部4段合法历史。过去的建议或计划不表示已经执行。</p>'
    for source in sources:page+='<details><summary>'+esc(source['id']+' · '+source['date'])+'</summary><pre>'+esc('\n\n'.join(t['id']+' '+t['role']+': '+t['text'] for t in source['turns']))+'</pre></details>'
    page+='<p>可在对话中回复：V01：A/B略好、A/B有实质改善、相当或不确定；一句主要理由即可。</p></html>'
    with (ROOT/'ONE_COMPARISON_ZH.html').open('x') as f:f.write(page)
    print(json.dumps(dict(question='V01',A=a['arm'],B=b['arm'],complete_past_sessions=4,pair_identity=pair['identity']),ensure_ascii=False))


if __name__=='__main__':main()
