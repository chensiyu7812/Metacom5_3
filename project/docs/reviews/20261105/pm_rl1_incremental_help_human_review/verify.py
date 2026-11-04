"""Reconcile V01 against displayed English/Chinese and original G requests."""
import hashlib,html,json,re,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[4];BASE=PROJECT/'outputs/pm_rl1'
SOURCE=BASE/'incremental_help_probe_20261105_v1';ROOT=BASE/'incremental_help_human_review_20261105_v1'
def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def main():
    for folder in (SOURCE,BASE/'alternate_executor_probe_20261104_v1',BASE/'alternate_executor_human_review_20261105_v1',ROOT):
        for name,h in read(folder/'OUTPUT_MANIFEST.json').items():assert sha(folder/name)==h,name
    intake=read(ROOT/'INTAKE_PRIVATE.json');row=intake['answer'];received=read(ROOT/'RECEIVED_ANSWER_PRIVATE.json')
    for path,h in intake['sources'].items():assert sha(Path(path))==h,path
    assert row['original_answer']==received['answer'] and sha(ROOT/'RECEIVED_ANSWER_PRIVATE.json')==intake['raw_sha256']
    assert received['answer']=='我觉得是相当的，都可以。只是支持策略的不同。和导师去沟通安排以及先考虑应对头疼和疲惫，感觉都是解决方案的一种。所以都可以。'
    pair=read(SOURCE/'HUMAN_PAIR_PRIVATE.json');page=(SOURCE/'ONE_COMPARISON_ZH.html').read_text();results=read(SOURCE/'RESULTS_PRIVATE.json')
    reqs=read(SOURCE/'alternate_G/REQUESTS_PRIVATE.json');inputs=read(SOURCE/'INPUTS_PRIVATE.json')
    assert row['instrument_identity']==pair['identity'] and row['study']==pair['study']
    for label in ('A','B'):
        displayed=html.unescape(re.search('<h2>'+label+r'</h2><pre>(.*?)</pre>',page,re.S).group(1));binding=row['alias_bindings'][label]
        assert binding['reply']==displayed and digest(displayed)==binding['reply_identity']
        assert html.escape(pair['translations'][label]) in page
        match=[r for r in results if r['generator']=='alternate' and r['case']=='N06' and r['reply']==displayed];assert len(match)==1
        r=match[0];assert r['arm']==binding['arm'] and r['actual_program']==binding['actions']
        req=next(q for q in reqs if q['input_identity']==r['input_identity']);raw=read(SOURCE/'alternate_G/raw'/(req['identity']+'.json'))
        assert req['messages']==inputs[r['input_identity']]['messages'] and raw['text']==displayed and raw['finish_reason']=='natural_stop'
    assert row['alias_bindings']['A']['actions']==[3,3,3,3,0] and row['alias_bindings']['B']['actions']==[0]
    assert row['outcome']=='tie' and row['winner_alias'] is None and row['exact_qm'] is row['numeric_reward'] is None
    assert row['evidence']==pair['evidence'] and digest(row['evidence'])==row['evidence_identity'] and len(row['evidence']['legal_past_sessions'])==4
    reg=read(ROOT/'ANSWER_REGISTRY_PRIVATE.json');old=read(BASE/'alternate_executor_human_review_20261105_v1/ANSWER_REGISTRY_PRIVATE.json')
    assert len(reg)==45 and reg[:44]==old and len({r['asset_id'] for r in reg})==45
    latest=reg[-1];assert latest['intake_identity']==digest(row) and latest['raw_label']['original_answer']==received['answer']
    assert latest['direction']=='tie' and not latest['qualified_reward'] and latest['numeric_reward'] is None
    assert all(x['q_value'] is None for x in old if x.get('q_status')=='interval')
    summary=read(ROOT/'SUMMARY.json');assert not summary['positive_candidate_latency_stage_triggered'] and not summary['positive_candidate_training_stage_triggered']
    sys.path.insert(0,str(PROJECT/'src'))
    from metacom_pm.rl1.online_materials import load_materials
    from metacom_pm.rl1.resource_organization import OrganizationSession
    audit=read(ROOT/'SLIGHT_POSITIVE_PATH_AUDIT_PRIVATE.json')
    for path,h in audit['sources'].items():assert sha(Path(path))==h,path
    candidates={x['case']:x for x in read(BASE/'feedback_and_opportunity_20261105_v1/OPPORTUNITIES_PRIVATE.json')}
    _,catalogs,renderer=load_materials(BASE/'organized_initial_training_20261103_v2',prefix_ids=[candidates[r['case']]['prefix_identity'] for r in audit['rows']])
    cache=[]
    for folder in (BASE/'alternate_executor_probe_20261104_v1',SOURCE/'alternate_G'):
        runtime=read(folder/'PROTOCOL.json')['runtime']['identity']
        for q in read(folder/'REQUESTS_PRIVATE.json'):cache.append((runtime,q,read(folder/'raw'/(q['identity']+'.json'))))
    assert len(cache)==audit['candidate_cache_unique_requests_checked']==44 and len(audit['rows'])==2
    for row2 in audit['rows']:
        candidate=candidates[row2['case']];cat=catalogs[candidate['prefix_identity']];session=OrganizationSession(cat,renderer)
        while candidate['target_resource_key'] not in session.receipt()['acquired']:session.get('MS')
        keys=session.receipt()['acquired'];actual=renderer.messages(cat,keys);target=renderer.messages(cat,[candidate['target_resource_key']])
        assert row2['actual_keys']==keys and row2['actual_MS_actions']==[3]*len(keys)+[0]
        assert digest(actual)==row2['actual_messages_identity'] and digest(target)==row2['target_only_messages_identity']
        assert actual!=target and not row2['actual_equals_judged_input']
        matches=[q['identity'] for rt,q,raw in cache if q['messages']==actual and rt==row2['runtime']]
        assert matches==row2['exact_actual_cache_matches']==[]
        judged=[raw for rt,q,raw in cache if q['identity']==row2['exact_judged_input'] and rt==row2['runtime'] and q['messages']==target]
        assert len(judged)==1 and digest(judged[0]['text'])==row2['preferred_reply_identity']
        reference=next(x for x in old if x.get('question_id')==row2['question'])
        assert reference['degree']=='slight' and reference['slight_edge_reply_identity']==row2['preferred_reply_identity']
        assert row2['real_path_preference'] is row2['real_path_latency'] is None
    for name,h in read(ROOT/'CLOSEOUT_MANIFEST.json').items():assert sha(ROOT/name)==h,name
    checks=dict(status='VERIFIED',new_answer_bound=1,old_records_preserved=44,total_records=45,
        original_G_probe_files_unchanged=len(read(SOURCE/'OUTPUT_MANIFEST.json')),A_actual_four_MS_path=True,B_OFF=True,
        full_legal_past_sessions=4,choice='相当',source_usage_not_relabelled_as_positive_reward=True,
        exact_quality_difference_unassigned=True,existing_slight_positives_preserved=2,candidate_cached_requests_checked=44,
        exact_cache_for_these_actual_paths=0,new_questions=0,new_model_calls=0,new_training_updates=0,API_cost_usd=0)
    (Path(__file__).parent/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n');print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
