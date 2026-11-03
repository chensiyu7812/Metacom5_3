#!/usr/bin/env python3
"""Analyze cached real train branches; prepare a small, unlabelled human draft.

No model, provider, optimizer or automatic reward assignment. Existing menus,
sources and questionnaires are immutable. This is an exploratory diagnostic.
"""
import argparse
from collections import Counter, defaultdict
from dataclasses import replace
import hashlib
import html
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.rl1.evidence import prefix_from_dict
from metacom_pm.rl1.judge import RUBRIC
from metacom_pm.rl1.resource_organization import OrganizationCatalog, OrganizedItem
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.temporal_evidence_ledger import words

BASE = PROJECT/'outputs/pm_rl1'
HEAD = {0:'STOP', 1:'RS', 2:'MP', 3:'MS', 4:'ME'}


def build(output):
    if output.exists():
        raise ValueError('Use a new output directory')
    sources = {}
    def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()
    def read(path):
        path = Path(path).resolve()
        sources[str(path)] = sha(path)
        return json.loads(path.read_text())
    def verify(folder, manifest='OUTPUT_MANIFEST.json'):
        for name, expected in read(folder/manifest).items():
            if Path(name).is_absolute() or '..' in Path(name).parts or sha(folder/name) != expected:
                raise ValueError('Changed source: '+name)
    train = BASE/'organized_initial_training_20261103_v2'
    feedback = BASE/'actual_training_feedback_20261103_v1'
    review = BASE/'reference_guided_review_20261103_v1'
    human = BASE/'human_answer_reanalysis_20261103_v2'
    for folder, manifest in [(train,'PACKAGE_MANIFEST.json'), (feedback,'OUTPUT_MANIFEST.json'),
                             (review,'OUTPUT_MANIFEST.json'), (human,'OUTPUT_MANIFEST.json')]:
        verify(folder, manifest)
    config = read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for path, expected in config['policy']['historical_files'].items():
        if sha(path) != expected: raise ValueError('Historical source changed')
    sources[str(Path(config['ledger']).resolve())] = sha(config['ledger'])
    menus = {m['identity']:m for m in read(train/'MENU_PRIVATE.json')['endpoints']}
    endpoints = read(feedback/'ENDPOINTS_PRIVATE.json')
    inputs = read(feedback/'INPUTS_PRIVATE.json')
    observations = read(train/'OBSERVATIONS_PRIVATE.json')
    registry = read(human/'ANSWER_REGISTRY_PRIVATE.json')
    old_scores = read(review/'LOCAL_REVIEW_CARDS_PRIVATE.json')
    by_prefix = defaultdict(dict)
    for row in endpoints:
        menu = menus[row['endpoint_identity']]
        if any(row[k] != menu[k] for k in ('prefix_identity','actions','resource_tokens')):
            raise ValueError('Endpoint join differs')
        assert row['actions'][-1] == 0 and 0 not in row['actions'][:-1]
        key = tuple(row['actions'][:-1])
        assert key not in by_prefix[row['prefix_identity']]
        by_prefix[row['prefix_identity']][key] = row
    for key, item in inputs.items():
        assert digest(item['evidence']) == item['evidence_identity']
        assert digest(item['reply']) == item['reply_identity']
        assert item['q'] is item['m'] is None and not item['qualified_reward']
    src = {pid:read(train/'sources_private'/(pid+'.json')) for pid in by_prefix}
    for pid, value in src.items():
        assert prefix_from_dict(value['prefix']).identity == pid
        assert value['prefix']['split'] == 'train'
    bound_sources = read(train/'INPUT_HASHES_PRIVATE.json')
    library_path, = [p for p in bound_sources if p.endswith('/RS_LIBRARY_PRIVATE.json')]
    library = read(library_path)
    assert sha(library_path) == bound_sources[library_path]
    library_items = {r['key']:OrganizedItem(**r) for r in library['items']}
    assert digest([r.identity for r in library_items.values()]) == library['identity']
    # Action-prefix tree, not an assertion of complete environment coverage.
    graph = []
    for pid, terminals in sorted(by_prefix.items()):
        nodes = {a[:i] for a in terminals for i in range(len(a)+1)}
        s = src[pid]; stored = read(s['stored_source_path'])
        assert sha(s['stored_source_path']) == bound_sources[s['stored_source_path']]
        metadata = stored['frozen_RS_metadata']
        local = [replace(r,original_rank=metadata[k][0],bge_similarity=metadata[k][1]) if k in metadata else r
                 for k,r in library_items.items()]
        catalog = OrganizationCatalog(prefix_from_dict(s['prefix']),
            local+[OrganizedItem(**r) for r in stored['memory']],provenance_identity=stored['catalog_identity'])
        assert catalog.identity == s['catalog_identity']
        acquired = {():()}
        for h in sorted(nodes):
            if h:
                prior = acquired[h[:-1]]
                acquired[h] = prior+(catalog.rank(HEAD[h[-1]],prior)[0]['key'],)
        signature = {h:tuple(r.key for r in catalog.canonical(keys)) for h,keys in acquired.items()}
        cached = defaultdict(list)
        for h,row in terminals.items():
            actual = menus[row['endpoint_identity']]['requests']['ON']['provenance']['selected_keys']
            assert list(signature[h]) == actual
            cached[signature[h]].append(row['endpoint_identity'])
        for h in sorted(nodes):
            immediate = {a:terminals[h+(a,)] for a in range(1,5) if h+(a,) in terminals}
            descendant_heads = sorted({a[len(h)] for a in terminals if a[:len(h)] == h and len(a)>len(h)})
            stop = terminals.get(h)
            graph.append(dict(prefix_identity=pid, history=list(h),
                selected_keys=list(signature[h]),
                cached_equivalent_terminal_endpoints=cached.get(signature[h],[]),
                STOP_endpoint=stop['endpoint_identity'] if stop else None,
                immediate_GET_then_STOP={HEAD[a]:r['endpoint_identity'] for a,r in immediate.items()},
                sampled_descendant_heads=[HEAD[a] for a in descendant_heads],
                continuation_only_heads=[HEAD[a] for a in descendant_heads if a not in immediate],
                identical_reply_extensions=[r['endpoint_identity'] for r in immediate.values()
                    if stop and r['ON']==stop['ON']],
                quality_advantages=None))
    # Reuse q/m-independent terminal cost preferences, without pruning states.
    equivalent = defaultdict(list)
    for row in endpoints: equivalent[row['prefix_identity'],row['ON']].append(row)
    constraints = []
    for group in equivalent.values():
        cheap = min(group, key=lambda r:(r['resource_tokens'],r['endpoint_identity']))
        for row in group:
            if row['resource_tokens'] > cheap['resource_tokens']:
                constraints.append(dict(preferred_endpoint=cheap['endpoint_identity'],
                    dispreferred_endpoint=row['endpoint_identity'], input_identity=row['ON'],
                    exact_return_difference=(row['resource_tokens']-cheap['resource_tokens'])/40960,
                    scope='fixed cached terminal outcomes only; not future sampling or intermediate-state dominance'))
    matches = []
    for card in old_scores:
        for iid,item in inputs.items():
            if (card['evidence_identity'],card['reply_identity']) == (item['evidence_identity'],item['reply_identity']):
                matches.append(dict(input_identity=iid, old_material_key=card['key'],
                    candidate=card['candidate'], qualified_reward=False,
                    affected_endpoints=[e['endpoint_identity'] for e in endpoints if e['ON']==iid]))
    # Metadata-only selection rule, fixed before inspecting the selected ON replies.
    selection = []; owners = set()
    for lo,hi in [(1,1),(2,6),(7,12),(13,1000)]:
        pid = next(p for p in sorted(src) if lo<=len(src[p]['prefix']['turns'])<=hi
                   and src[p]['prefix']['owner_id'] not in owners)
        owners.add(src[pid]['prefix']['owner_id']); selection.append(pid)
    cases = []; ranks = []
    for i,pid in enumerate(selection,1):
        s = src[pid]; branches = by_prefix[pid]; prefix = prefix_from_dict(s['prefix'])
        stored = read(s['stored_source_path'])
        q = words(prefix.query)
        ms = sorted([r for r in stored['memory'] if r['head']=='MS'],
                    key=lambda r:(-len(q & words(r['search_text'])),r['key']))
        first = menus[branches[(3,)]['endpoint_identity']]['requests']['ON']['provenance']['selected_keys']
        assert first == [ms[0]['key']]
        ranks.append(dict(case_id=f'C{i:02}', prefix_identity=pid,
            initial_MS_ranking=[dict(rank=j+1,key=r['key'],reported_at=r['reported_at'],
                lexical_overlap=len(q & words(r['search_text'])),
                search_text=r['search_text']) for j,r in enumerate(ms)]))
        cards = []
        # Five already-generated programs; orders remain separate even if replies coincide.
        for actions in [(),(3,),(4,),(3,4),(4,3)]:
            row = branches[actions]; item = inputs[row['ON']]
            cards.append(dict(actions=list(actions)+( [0]), endpoint_identity=row['endpoint_identity'],
                input_identity=row['ON'], evidence_identity=item['evidence_identity'],
                reply_identity=item['reply_identity'], reply=item['reply'],
                resource_tokens=row['resource_tokens'],
                selected_keys=menus[row['endpoint_identity']]['requests']['ON']['provenance']['selected_keys'],
                exact_old_human_references=[r['asset_id'] for r in registry
                    if r['evidence_identity']==item['evidence_identity'] and item['reply_identity'] in r['replies']]))
        single_read = [dict(observation_identity=k, acquired=r['observation']['acquired'])
            for k,r in observations.items() if r['prefix_identity']==pid
            and sum(r['observation']['counts'])==1 and not r['observation']['stopped']]
        cases.append(dict(case_id=f'C{i:02}',prefix_identity=pid,owner_id=prefix.owner_id,
            selection_turn_count=len(prefix.turns),evidence=s['evidence'],
            first_read_observations=single_read,cards=cards,
            all_endpoint_ids=[r['endpoint_identity'] for r in branches.values()],
            human_review_proposed=i>1, analyst_is_human_label=False))
    # One answer slot per complete evidence+reply; no score is invented for ties.
    proposed = {c['input_identity']:c for case in cases[1:] for c in case['cards']}
    template = dict(status='DRAFT_NOT_ANSWERED_NOT_REWARD',
        purpose='Three real train-context diagnostic groups; not formal evaluation or global judge qualification.',
        source_menu_identity=read(train/'MENU_PRIVATE.json')['identity'],
        original_qm_rubric=RUBRIC,
        groups=[dict(case_id=c['case_id'], prefix_identity=c['prefix_identity'],
            preference_groups=None, both_problematic=None, reason=None) for c in cases[1:]],
        replies={k:dict(evidence_identity=v['evidence_identity'],reply_identity=v['reply_identity'],
            q_min=None,q_max=None,m=None,reason=None) for k,v in proposed.items()},
        rules=['Ranks do not become scalar rewards.', 'Preserve q intervals; never take their midpoint.',
               'A tie does not assert equal cardinal utility.', 'No answer is missing, not zero.',
               'Human q/m cover only these exact inputs, not the whole pool or a judge protocol.'])
    stats = dict(train_prefixes=len(by_prefix),programs=len(endpoints),
        sampled_history_nodes=len(graph),histories_with_generated_STOP=sum(r['STOP_endpoint'] is not None for r in graph),
        histories_without_generated_STOP=sum(r['STOP_endpoint'] is None for r in graph),
        histories_without_any_equivalent_generated_STOP=sum(not r['cached_equivalent_terminal_endpoints'] for r in graph),
        missing_unique_resource_states=len({(r['prefix_identity'],tuple(r['selected_keys'])) for r in graph
            if not r['cached_equivalent_terminal_endpoints']}),
        read_histories_with_STOP_and_immediate_alternative=sum(bool(r['history']) and r['STOP_endpoint'] is not None
            and bool(r['immediate_GET_then_STOP']) for r in graph),
        immediate_read_STOP_comparisons=sum(len(r['immediate_GET_then_STOP']) for r in graph if r['history'] and r['STOP_endpoint']),
        identical_reply_read_extensions=sum(len(r['identical_reply_extensions']) for r in graph if r['history']),
        exact_terminal_cost_preferences=len(constraints),
        existing_candidate_scores_matching_training_inputs=len(matches),
        candidate_matched_endpoints=sum(len(r['affected_endpoints']) for r in matches),
        qualified_training_inputs=0,selected_contexts=len(cases),selected_owners=len(owners),
        selected_programs=sum(len(c['all_endpoint_ids']) for c in cases),
        proposed_human_contexts=3,proposed_programs=sum(len(c['cards']) for c in cases[1:]),
        proposed_unique_replies=len(proposed),
        exact_old_human_matches_in_proposed=sum(bool(v['exact_old_human_references']) for v in proposed.values()),
        human_answers_received=0,new_G=0,new_J=0,new_cost_usd=0,natural_updates=0,
        frozen_historical_files_verified=len(config['policy']['historical_files']))
    output.mkdir(parents=True,mode=0o700)
    def save(name,value):
        path=output/name;path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');path.chmod(0o600)
    save('SUMMARY.json',stats);save('BRANCHES_PRIVATE.json',graph)
    save('EXACT_COST_PREFERENCES_PRIVATE.json',constraints);save('EXISTING_SCORE_MATCHES_PRIVATE.json',matches)
    save('CASES_PRIVATE.json',cases);save('MS_RANKINGS_PRIVATE.json',ranks);save('ANSWER_TEMPLATE_PRIVATE.json',template)
    # Readable, self-contained local draft. Full evidence is retained, no remote assets.
    esc=html.escape
    page=['<!doctype html><html lang="zh"><meta charset="utf-8"><title>PM-RL1 决策诊断材料</title>',
        '<style>body{max-width:980px;margin:32px auto;font:17px/1.65 sans-serif;padding:0 20px}pre{white-space:pre-wrap}article{border:1px solid #ccc;border-radius:10px;padding:18px;margin:20px 0}summary{cursor:pointer}blockquote{border-left:3px solid #777;padding-left:15px}table{border-collapse:collapse}td,th{border:1px solid #ccc;padding:7px}</style>',
        '<h1>三个情境的诊断草稿</h1><p>先看差异是否值得评价，再决定是否填写。旧8对问卷不重发；这些是训练前缀的新回复，旧分数不复制。每个情境来源只读一次，相同回复只出现一次。A/B等为本页中性标识，不代表方法。此页不是新的人评答案。</p>',
        '<p>每组只需指出：哪些回复明显更好、哪些相当、哪些都有问题，或无法确定；指出影响判断的一处差异即可。不要求查找来源编号。来源与费用分开显示，先判断回复质量。</p>',
        '<p>如果希望本组用于原q/m奖励，还需要各回复的q等级（可保留区间）与m：q=4充分满足本轮需要并尊重已知限制；3合适、连贯、回应了需要，且没有重要缺陷；2基本回应，但遗漏或处理错了重要的明确需要/限制；1主导性的错误、越界或不匹配破坏了大部分支持；0严重不匹配或不可用。3不要求存在重要缺陷，简短追问也可得4，不因更长、更多建议或展示记忆而加分。</p>',
        '<p>m=0在完整已给证据中未发现用户事实、时序、身份、意图/结果或明确边界错误；0.25是未改变核心理解/建议的局部错误；1是改变核心理解/建议的实质错误。无法判断请留空并说明，不为了给数值而硬判。只有偏好而没有这些数值时，先用于排序诊断/监督，不冒充PPO标量奖励。区间保留原样，不取中点。</p>',
        '<details><summary>沿用的完整q/m尺度原文（不是要求填写逐条claim）</summary><pre>'+esc(RUBRIC)+'</pre></details>']
    prompts={
        'C02':'新增历史背景是否改善当前回应，还是这些回复只是同样可接受的不同问法？决定是否值得继续读历史，并检查q等级能否表达你认为重要的差别。',
        'C03':'在用户已经说尝试过工作边界之后，哪种追问更合适？决定继续读资源是否带来实际收益，还是应先改检索。',
        'C04':'对研究机会的犹豫，继续读取后不同的回应重点是否更有帮助？决定追加读取是否值得；不需要你评价任何医疗方案。'}
    for case in cases[1:]:
        page += [f'<article><h2>{case["case_id"]}</h2><p>{prompts[case["case_id"]]}</p>',
            '<p>已复用旧结论：多种支持策略都可能合适；计划不能当完成；历史说话者不能当当前AI。新问题仅判断这组新回复的差异。原文可核实事实，但不能替你决定支持质量。</p>',
            '<h3>当前完整对话</h3>']
        for turn in case['evidence']['current_prefix']:
            page.append(f'<p><b>{esc(turn["role"])}：</b>{esc(turn["text"])}</p>')
        page.append('<details><summary>完整合法历史（可按需展开）</summary>')
        for s in case['evidence']['legal_past_sessions']:
            page.append(f'<h4>{esc(s["id"])} · {esc(s["date"])}</h4>')
            for turn in s['turns']:page.append(f'<p>{esc(turn["id"])} {esc(turn["role"])}：{esc(turn["text"])}</p>')
        page.append('</details>')
        unique={c['input_identity']:c for c in case['cards']}
        # Deterministic reply-hash order conceals which card is OFF / continuation.
        aliases={key:chr(65+i) for i,key in enumerate(sorted(unique))}
        for key in sorted(unique):
            page.append(f'<h3>回复 {aliases[key]}</h3><blockquote>{esc(unique[key]["reply"]).replace(chr(10),"<br>")}</blockquote>')
        page += ['<p>可直接用中文回复：本组优先___；相当___；都有问题/不确定___；原因___。若填写q/m，按A/B等回复标识写即可。</p>',
            '<details><summary>判断后查看：动作与成本，以及答案怎样使用</summary><table><tr><th>回复</th><th>动作</th><th>资源tokens</th></tr>']
        for c in case['cards']:
            actions=' → '.join(HEAD[a] for a in c['actions'])
            page.append(f'<tr><td>{aliases[c["input_identity"]]}</td><td>{actions}</td><td>{c["resource_tokens"]}</td></tr>')
        page.append('</table><p>若有明确改善：保留对应资源路径作监督候选；若相当：不虚构质量增益，再比较成本；若更差：查检索与G使用；若不确定：保持缺失，不硬造赢家。任一结果均回接本组原回复，不能扩大为全训练集标签。三组只能支持小样本诊断，不能证明泛化或读后策略必胜。</p></details></article>')
        case['blind_aliases']={v:k for k,v in aliases.items()}
    page.append('</html>')
    path=output/'REVIEW_DRAFT_ZH.html';path.write_text('\n'.join(page));path.chmod(0o600)
    save('CASES_PRIVATE.json',cases)
    sources[str(Path(__file__).resolve())]=sha(__file__)
    sources[str((PROJECT/'src/metacom_pm/rl1/judge.py').resolve())]=sha(PROJECT/'src/metacom_pm/rl1/judge.py')
    if any(sha(path)!=expected for path,expected in sources.items()):raise ValueError('Input changed during analysis')
    save('SOURCE_HASHES_PRIVATE.json',sources)
    save('OUTPUT_MANIFEST.json',{p.name:sha(p) for p in output.iterdir()})
    print(json.dumps(stats,ensure_ascii=False))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True)
    build(p.parse_args().output)
