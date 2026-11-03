"""Independent checks for the actual branch analysis; no mock learning."""
from collections import Counter
import hashlib
import html
from html.parser import HTMLParser
import json
from pathlib import Path

PROJECT=Path(__file__).resolve().parents[4]
BASE=PROJECT/'outputs/pm_rl1'


def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    root=BASE/'decision_branches_20261104_v2';findings=BASE/'decision_findings_20261104_v1'
    manifests=0;sources={}
    for folder in (root,findings):
        for name,expected in read(folder/'OUTPUT_MANIFEST.json').items():
            assert not Path(name).is_absolute() and '..' not in Path(name).parts
            assert sha(folder/name)==expected
            manifests+=1
        sources.update(read(folder/'SOURCE_HASHES_PRIVATE.json'))
    for p,h in sources.items():assert sha(Path(p))==h
    cfg=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for p,h in cfg['policy']['historical_files'].items():assert sha(Path(p))==h
    prior=read(PROJECT/'docs/reviews/20261103/pm_rl1_reference_guided_review/CHECKS.json')
    assert sha(Path(cfg['ledger']))==prior['prior_ledger_sha256']
    v1=BASE/'decision_branches_20261104_v1'
    oldhash=next(h for p,h in read(v1/'SOURCE_HASHES_PRIVATE.json').items() if p.endswith('/151_analyze_real_decision_branches.py'))
    assert sha(BASE/'decision_branches_20261104_v1_EXECUTED_SCRIPT.py')==oldhash
    graph=read(root/'BRANCHES_PRIVATE.json');stats=read(root/'SUMMARY.json')
    feedback=BASE/'actual_training_feedback_20261103_v1'
    endpoints={e['endpoint_identity']:e for e in read(feedback/'ENDPOINTS_PRIVATE.json')}
    inputs=read(feedback/'INPUTS_PRIVATE.json')
    constraints=read(root/'EXACT_COST_PREFERENCES_PRIVATE.json')
    for c in constraints:
        a,b=endpoints[c['preferred_endpoint']],endpoints[c['dispreferred_endpoint']]
        assert a['prefix_identity']==b['prefix_identity'] and a['ON']==b['ON']
        assert c['exact_return_difference']==(b['resource_tokens']-a['resource_tokens'])/40960>0
    assert len(constraints)==62
    comparisons=[]
    for node in graph:
        if not node['history'] or node['STOP_endpoint'] is None:continue
        a=endpoints[node['STOP_endpoint']]
        assert a['actions']==node['history']+[0]
        for key in node['immediate_GET_then_STOP'].values():
            b=endpoints[key]
            assert b['prefix_identity']==a['prefix_identity']
            assert b['actions'][:-2]==node['history'] and len(b['actions'])==len(a['actions'])+1
            comparisons.append((a,b))
    assert len(comparisons)==stats['immediate_read_STOP_comparisons']==250
    assert sum(a['ON']==b['ON'] for a,b in comparisons)==23
    # Independent join to every real encoded public observation, including
    # states whose STOP generation is absent.
    train=BASE/'organized_initial_training_20261103_v2'
    obs=read(train/'OBSERVATIONS_PRIVATE.json')
    sig=lambda rows:tuple((r['head'],r['content'],r['reported_at']) for r in rows)
    obs_index={(r['prefix_identity'],sig(r['observation']['acquired'])):k for k,r in obs.items()}
    assert len(obs_index)==len(obs)==591
    src=read(train/'INPUT_HASHES_PRIVATE.json')
    library=read(Path(next(p for p in src if p.endswith('/RS_LIBRARY_PRIVATE.json'))))
    rs={r['key']:r for r in library['items']};catalogs={}
    for pid in {n['prefix_identity'] for n in graph}:
        s=read(train/'sources_private'/(pid+'.json'))
        catalogs[pid]=rs|{r['key']:r for r in read(Path(s['stored_source_path']))['memory']}
    mapped=set()
    for n in graph:
        rows=[catalogs[n['prefix_identity']][k] for k in n['selected_keys']]
        oid=obs_index[n['prefix_identity'],sig(rows)];mapped.add(oid)
        o=obs[oid]['observation'];counts=Counter(n['history'])
        assert o['counts']==[counts[h] for h in range(1,5)]
    assert mapped==set(obs)
    assert len({(n['prefix_identity'],tuple(n['selected_keys'])) for n in graph})==591
    assert len({(n['prefix_identity'],tuple(n['selected_keys'])) for n in graph if n['cached_equivalent_terminal_endpoints']})==431
    assert all(i['q'] is i['m'] is None and not i['qualified_reward'] for i in inputs.values())
    question=read(findings/'PRIORITY_QUESTION_PRIVATE.json')
    assert question['answer'] is question['qm'] is None and not question['qualified_reward']
    page=(findings/'ONE_QUESTION_ZH.html').read_text();HTMLParser().feed(page)
    for c in question['cards']:
        assert c['reply']==inputs[c['input_identity']]['reply']
        assert html.escape(c['reply']).replace('\n','<br>') in page
    for session in question['evidence']['legal_past_sessions']:
        for t in session['turns']:assert html.escape(t['text']) in page
    for t in question['evidence']['current_prefix']:assert html.escape(t['text']) in page
    draft=(root/'REVIEW_DRAFT_ZH.html').read_text();HTMLParser().feed(draft)
    assert '3合适、连贯、回应了需要，且没有重要缺陷' in draft
    assert '3总体合适但有实质不足' not in draft
    finding=read(findings/'FINDINGS_PRIVATE.json')[0]
    assert {k for k in finding['original_record'] if finding['original_record'][k]!=finding['repair_candidate'][k]}=={'past_report'}
    checks=dict(analysis_exit_code=0,findings_exit_code=0,independent_verification_exit_code=0,
        artifacts_verified=manifests,bound_sources_verified=len(sources),
        frozen_historical_files_verified=len(cfg['policy']['historical_files']),
        original_ledger_sha256=sha(Path(cfg['ledger'])),
        actual_observations_matched=591,unique_states_with_generation=431,unique_states_without_generation=160,
        exact_terminal_preferences_verified=62,read_stop_comparisons_verified=250,
        human_page_original_replies_and_full_evidence_verified=True,
        original_q3_anchor_verified=True,v1_executed_script_archived=True,
        new_human_question_dispatched=1,human_answers_ingested=0,new_G=0,new_J=0,
        new_cost_usd=0,natural_updates=0,
        output_manifests={p.name:sha(p/'OUTPUT_MANIFEST.json') for p in (root,findings)})
    here=Path(__file__).resolve().parent
    (here/'SUMMARY.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2)+'\n')
    (here/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
