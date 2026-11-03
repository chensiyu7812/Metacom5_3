"""Bind source-level findings and one targeted preference question to real data."""
import hashlib
import html
import json
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[4]
BASE = PROJECT/'outputs/pm_rl1'
sources = {}


def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    sources[str(path.resolve())] = sha(path)
    return json.loads(path.read_text())


def main():
    root = BASE/'decision_branches_20261104_v2'
    for name,expected in read(root/'OUTPUT_MANIFEST.json').items():
        assert not Path(name).is_absolute() and '..' not in Path(name).parts
        assert sha(root/name)==expected
    cases = read(root/'CASES_PRIVATE.json'); ranks = read(root/'MS_RANKINGS_PRIVATE.json')
    endpoints = read(BASE/'actual_training_feedback_20261103_v1/ENDPOINTS_PRIVATE.json')
    inputs = read(BASE/'actual_training_feedback_20261103_v1/INPUTS_PRIVATE.json')
    menus = {m['identity']:m for m in read(BASE/'organized_initial_training_20261103_v2/MENU_PRIVATE.json')['endpoints']}
    c1,c2,c3,c4 = cases
    me = next(a for o in c1['first_read_observations'] for a in o['acquired'] if a['head']=='ME')
    record = json.loads(me['content'])
    assert record['past_report']=='seeker communicated need for clarity in relationship intentions to ex-boyfriend'
    quote = "say he wants me back or something to that effect. i'd like him to be more direct in what he wants from me"
    history = next(h for h in c1['evidence']['legal_past_sessions'] if h['date']=='2024-09-12')
    assert next(t['text'] for t in history['turns'] if t['id']=='H004:T013')==quote
    assert record['evidence'][0]['quote']==quote
    corrected = dict(record, past_report='The seeker wanted the ex-boyfriend to be more direct about what he wanted from the seeker.')
    target = next(r for r in ranks[2]['initial_MS_ranking'] if r['reported_at']=='2025-06-05')
    selected = [e for e in endpoints if e['prefix_identity']==c3['prefix_identity']]
    reached = [e['endpoint_identity'] for e in selected if target['key'] in menus[e['endpoint_identity']]['requests']['ON']['provenance']['selected_keys']]
    assert target['rank']==13 and not reached and len(selected)==22
    turn = next(t for s in c3['evidence']['legal_past_sessions'] for t in s['turns'] if t['id']=='H014:T008')
    assert "clearer boundaries" in turn['text'] and turn['text'] in target['search_text']
    findings = [dict(case_id='C01',kind='analyst_source_entailment_finding',
        original_record=record, source_session=history,
        issue='The cited source expresses a desired clarification, not a completed communication to the ex. The full cited session does not establish that communication.',
        repair_candidate=corrected, original_catalog_modified=False, candidate_generated=False,
        human_label=False, q=None,m=None,
        downstream_limit='The actual one-ME reply equals OFF; this observed source error did not cause a changed reply at this terminal.'),
        dict(case_id='C03',kind='verified_retrieval_coverage_finding',
        target_key=target['key'],initial_rank=target['rank'],source_turn=turn,
        initial_top_date=ranks[2]['initial_MS_ranking'][0]['reported_at'],
        programs_checked=len(selected),programs_reaching_target=reached,
        implication='Topic-relevant history exists but was never delivered in these 22 programs.',
        limits='Not proof of response-quality gain, whole-catalog unreachability, or needing thirteen GETs; ranking changes after each read.')]
    # Targeted opportunity check: a response that actually brings in historical
    # supervisor context, rather than asking humans to grade near-paraphrases.
    pair = [e for e in endpoints if e['prefix_identity']==c2['prefix_identity']
            and e['actions'] in ([0],[3,3,3,3,3,3,0])]
    assert len(pair)==2
    pair.sort(key=lambda e:inputs[e['ON']]['reply_identity'])
    cards = []
    for alias,e in zip(('A','B'),pair):
        item=inputs[e['ON']]
        cards.append(dict(alias=alias,endpoint_identity=e['endpoint_identity'],input_identity=e['ON'],
            actions=e['actions'],resource_tokens=e['resource_tokens'],reply=item['reply'],
            evidence_identity=item['evidence_identity'],reply_identity=item['reply_identity']))
    assert len({c['evidence_identity'] for c in cards})==1
    ms = next(c for c in cards if c['actions']!=[0])
    assert "undervalued by your supervisor" in ms['reply']
    supporting_turns = [t for s in c2['evidence']['legal_past_sessions'] for t in s['turns']
                        if t['id'] in ('H012:T004','H012:T016')]
    question = dict(question_id='pmrl1-c02-history-benefit-20261104-v1',
        scope='targeted train diagnostic, not prevalence or independent held-out evaluation',
        selection='C02 selected by metadata; this contrast subsequently chosen for explicit history use. Outcome-informed diagnostic selection.',
        decision='Does explicit historical work context add useful support here, and can the current q/m scale represent that preference?',
        evidence=c2['evidence'],supporting_turns=supporting_turns,cards=cards,
        old_answers_used=['Different reasonable strategies can be equally acceptable.','Memory demonstration alone is not quality.','Past speaker/action ownership must be supported.'],
        why_new='No exact old human label covers these complete inputs; existing answers do not determine this quality comparison.',
        alternatives={'historical_reply_better':'Retain as a positive resource candidate; test whether q/m ranks it likewise before training.',
            'equivalent':'No positive quality margin established; do not add a GET bonus or infer equal numeric U.',
            'OFF_better':'Record a negative candidate and inspect G use; do not reward resource consumption.',
            'uncertain':'Preserve missingness; do not force an advantage.'},
        answer=None,qm=None,qualified_reward=False,
        sufficiency='One preference cannot supply scalar PPO rewards or prove sequential adaptation. Other two groups stay in reserve, not mandatory.')
    output=BASE/'decision_findings_20261104_v1';output.mkdir(mode=0o700,exist_ok=False)
    def save(name,obj):
        p=output/name;p.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n');p.chmod(0o600)
    save('FINDINGS_PRIVATE.json',findings);save('PRIORITY_QUESTION_PRIVATE.json',question)
    esc=html.escape
    page=['<!doctype html><html lang="zh"><meta charset="utf-8"><title>PM-RL1：一个有明确用途的新比较</title>',
        '<style>body{max-width:920px;margin:32px auto;padding:0 20px;font:17px/1.65 sans-serif}blockquote{border-left:4px solid #aaa;padding:0 18px}summary{cursor:pointer}pre{white-space:pre-wrap}</style>',
        '<h1>只比较一次：历史信息是否让当前回应更有帮助</h1>',
        '<p>这不是原8对问卷。先前关于“不同支持策略都可接受”的答案已复用；此处不预定哪个回复更好。问题仅决定历史信息在这例中是否存在值得学习的质量增量。一个偏好不自动变成PPO奖励。</p>',
        '<h2>完整当前对话</h2>']
    for t in c2['evidence']['current_prefix']:page.append(f'<p><b>{esc(t["role"])}：</b>{esc(t["text"])}</p>')
    page.append('<p>来源核对：此前用户确实说过感到不被上司重视、上司削弱其努力；不能把这点当作新编事实。是否有必要在这轮提起，仍是质量判断。</p>')
    for t in supporting_turns:page.append(f'<blockquote>{esc(t["text"])}</blockquote>')
    for c in cards:page.append(f'<h2>回复{c["alias"]}</h2><blockquote>{esc(c["reply"]).replace(chr(10),"<br>")}</blockquote>')
    page.append('<p>可答：A更好 / B更好 / 相当 / 两者都有问题 / 不确定。若有差别，一句话说明关键原因即可。若你愿意给原q/m等级，可同时填写并保留区间；不要求为了回答而强选数值，也不会稍后把相同问题换表重问。</p>')
    page.append('<details><summary>完整合法历史</summary>')
    for s in c2['evidence']['legal_past_sessions']:
        page.append(f'<h3>{esc(s["id"])} · {esc(s["date"])}</h3>')
        for t in s['turns']:page.append(f'<p>{esc(t["id"])} {esc(t["role"])}：{esc(t["text"])}</p>')
    page.append('</details><details><summary>判断后查看动作、成本与后续使用</summary>')
    for c in cards:page.append(f'<p>{c["alias"]}：{esc(str(c["actions"]))}；资源tokens={c["resource_tokens"]}。</p>')
    page.append('<p>有明确历史增益→检验q/m能否保留这个方向，再作监督候选；相当→不虚构质量优势；更差→查G或资源适用性；不确定→留缺失。此比较不能证明读后调整比一次性固定计划更好，也不要求填其余两个备用情境。</p></details></html>')
    p=output/'ONE_QUESTION_ZH.html';p.write_text('\n'.join(page));p.chmod(0o600)
    sources[str(Path(__file__).resolve())]=sha(Path(__file__))
    assert all(sha(Path(p))==h for p,h in sources.items())
    save('SOURCE_HASHES_PRIVATE.json',sources)
    save('OUTPUT_MANIFEST.json',{p.name:sha(p) for p in output.iterdir()})
    print(json.dumps(dict(source_findings=len(findings),original_records_changed=0,
        priority_questions_prepared=1,answers_received=0,new_rewards=0,new_G=0,new_J=0,
        aliases=[dict(alias=c['alias'],actions=c['actions']) for c in cards])))


if __name__=='__main__':main()
