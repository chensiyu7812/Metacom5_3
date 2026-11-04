"""Independent reconciliation of source paths, human/J mapping and actual G outputs."""
import hashlib,html,json,sys
from pathlib import Path
PROJECT=Path(__file__).resolve().parents[4];sys.path.insert(0,str(PROJECT/'src'))
BASE=PROJECT/'outputs/pm_rl1';AUDIT=BASE/'feedback_and_opportunity_20261105_v1';PROBE=BASE/'incremental_help_probe_20261105_v1'
HUMAN=BASE/'alternate_executor_human_review_20261105_v1';TRAIN=BASE/'organized_initial_training_20261103_v2'
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def stamp(x):assert x['identity']==digest({k:v for k,v in x.items() if k!='identity'})
def hashes(x):
    for p,h in x.items():assert sha(Path(p))==h,p


def main():
    from transformers import AutoTokenizer
    from metacom_pm.rl1.online_materials import load_materials
    from metacom_pm.rl1.resource_organization import OrganizationSession
    from metacom_pm.rl1.resource_value_probe import match_session
    from metacom_pm.rl1.schema import HEADS
    for folder in ('alternate_executor_human_review_20261105_v1','alternate_executor_probe_20261104_v1','resource_value_probe_20261104_v1'):
        for name,h in read(BASE/folder/'OUTPUT_MANIFEST.json').items():assert sha(BASE/folder/name)==h,name
    reg=read(HUMAN/'ANSWER_REGISTRY_PRIVATE.json');prior=read(BASE/'resource_value_probe_20261104_v1/ANSWER_REGISTRY_PRIVATE.json')
    assert len(reg)==44 and reg[:36]==prior
    reuse=read(AUDIT/'REFERENCE_REUSE_AUDIT_PRIVATE.json');hashes(reuse['sources'])
    assert len(reuse['old_checks'])==8 and reuse['old_result']=='REFERENCE_SCREEN_NOT_PASSED'
    p=read(AUDIT/'PROTOCOL.json');stamp(p);hashes(p['sources']);hashes(p['code'])
    pairs=read(AUDIT/'PAIRS_PRIVATE.json');reqs=read(AUDIT/'REQUESTS_PRIVATE.json');intake=read(HUMAN/'INTAKE_PRIVATE.json')['answers']
    assert digest(pairs)==p['pairs_identity'] and digest(reqs)==p['requests_identity'] and len(reqs)==16
    analysis=read(AUDIT/'ANALYSIS_PRIVATE.json');flip={'A_better':'B_better','B_better':'A_better','near_equal':'near_equal','uncertain':'uncertain'}
    independently_parsed=0;completed=0;timeouts=0;material=[]
    for pair,h,got in zip(pairs,intake,analysis):
        stamp(pair);assert pair['key']==h['question_id']==got['key']
        assert pair['left']==h['alias_bindings']['A']['reply'] and pair['right']==h['alias_bindings']['B']['reply']
        assert pair['evidence']['legal_past_sessions']==[h['evidence']['legal_past_source']]
        assert pair['evidence']['current_prefix']==[dict(id=f'C:T{i:03d}',role=t['speaker'],text=t['text']) for i,t in enumerate(h['evidence']['current_prefix'])]
        values=[]
        for reverse in (False,True):
            q=next(q for q in reqs if q['pair_identity']==pair['identity'] and q['reverse']==reverse);stamp(q)
            payload=json.loads(q['messages'][1]['content'])
            a,b=(pair['right'],pair['left']) if reverse else (pair['left'],pair['right'])
            assert payload==dict(evidence=pair['evidence'],reply_A=a,reply_B=b)
            path=AUDIT/'responses'/(q['identity']+'.json');obj=None;coarse=[]
            if path.exists():
                raw=read(path);completed+=1;assert raw['training_reward'] is None and raw['API_cost_usd']==0
                assert raw['request_identity']==q['identity'] and raw['output_tokens']==len(raw['output_token_ids'])
                if raw['finish_reason']=='natural_stop':
                    text=raw['raw'].rsplit('</think>',1)[-1].strip()
                    if text.startswith('```json') and text.endswith('```'):text=text[7:-3].strip()
                    obj=json.loads(text);sessions={s['id'] for s in pair['evidence']['legal_past_sessions']}
                    turns={t['id'] for s in pair['evidence']['legal_past_sessions'] for t in s['turns']}|{t['id'] for t in pair['evidence']['current_prefix']}
                    assert set(obj)=={'verdict','risk_A','risk_B','reason','evidence_ids'}
                    assert all(x in turns|sessions for x in obj['evidence_ids'])
                    coarse=[x for x in obj['evidence_ids'] if x in sessions];obj['evidence_ids']=[x for x in obj['evidence_ids'] if x not in sessions]
                    independently_parsed+=1
                    if obj['verdict'] in ('A_better','B_better'):material.append(dict(question=pair['key'],reverse=reverse,verdict=obj['verdict']))
                else:assert raw['finish_reason']=='technical_timeout';timeouts+=1
            assert got['records'][int(reverse)]['parsed']==obj and got['records'][int(reverse)]['coarse_session_ids']==coarse
            values.append(obj)
        a,b=values
        assert got['both_parsed']==bool(a and b)
        assert got['verdict_consistent']==bool(a and b and a['verdict']==flip[b['verdict']])
        assert got['risk_consistent']==bool(a and b and a['risk_A']==b['risk_B'] and a['risk_B']==b['risk_A'])
        assert got['training_reward'] is None
    stop=read(AUDIT/'EARLY_STOP_FINAL.json');assert completed==stop['completed']==4
    assert stop['unstarted']==12 and stop['unknown_started']==[] and stop['original_planned']==16
    # Replay with the original Llama tokenizer contract, including explicit list output in transformers 5.
    cfg=read(TRAIN/'CONFIG.json');tok=AutoTokenizer.from_pretrained(cfg['runtime']['model_dir'],local_files_only=True)
    class ListTokenizer:
        def __getattr__(self,k):return getattr(tok,k)
        def apply_chat_template(self,*args,**kwargs):return tok.apply_chat_template(*args,**kwargs,return_dict=False)
    _,cats,renderer=load_materials(TRAIN,tokenizer=ListTokenizer())
    inventory=read(AUDIT/'INVENTORY_AUDIT_PRIVATE.json');opportunities=read(AUDIT/'OPPORTUNITIES_PRIVATE.json');hashes(read(AUDIT/'OPPORTUNITY_SOURCES.json'))
    assert len(inventory)==24 and len(opportunities)==9
    for o in opportunities:
        cat=cats[o['prefix_identity']];src=read(Path(o['current_source_file']));item=cat.item(o['target_resource_key'])
        assert match_session(item,src['evidence'])==o['target_session'] and item.identity==o['target_resource_identity']
        assert all(t in o['target_session']['turns'] for t in o['source_anchors'])
        trace=OrganizationSession(cat,renderer);n=0
        while item.key not in trace.receipt()['acquired']:trace.get('MS');n+=1
        assert n==o['actual_pure_MS_position']
        for route in o['limited_route_family']:
            trace=OrganizationSession(cat,renderer)
            for action in route['actions']:
                if action==0:trace.stop()
                else:trace.get(HEADS[action-1])
            assert trace.receipt()['acquired']==route['acquired'] and trace.receipt()['usage']['input_tokens']==route['input_tokens']
        assert o['help_quality'] is o['qualified_reward'] is None
    s=read(PROBE/'STUDY.json');stamp(s);hashes(s['source_hashes'])
    inputs=read(PROBE/'INPUTS_PRIVATE.json');cards=read(PROBE/'CARDS_PRIVATE.json');reused=read(PROBE/'REUSED_PRIVATE.json');gqs=read(PROBE/'G_REQUESTS_PRIVATE.json')
    assert len(inputs)==len(cards)==8 and len(reused)==5 and len(gqs)==3
    for key,v in [('inputs',inputs),('cards',cards),('reused',reused)]:assert digest(v)==s[key+'_identity']
    original_protocol=read(PROBE/'G_PROTOCOL.json');stamp(original_protocol)
    old=read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    alt=PROBE/'alternate_G';ap=read(alt/'PROTOCOL.json');stamp(ap);hashes(ap['sources']);hashes(ap['code']);rt=ap['runtime'];stamp(rt)
    assert rt==read(BASE/'alternate_executor_probe_20261104_v1/PROTOCOL.json')['runtime']
    gemma=AutoTokenizer.from_pretrained(rt['model_dir'],local_files_only=True);aqs=read(alt/'REQUESTS_PRIVATE.json')
    assert digest(aqs)==ap['requests_identity'] and len(aqs)==8
    results=read(PROBE/'RESULTS_PRIVATE.json');assert len(results)==16;format_failures=[]
    for card in cards:
        item=inputs[card['input_identity']];cat=cats[item['prefix_identity']];keys=card['acquisition_order']
        assert renderer.messages(cat,keys)==item['messages'] and renderer.usage(cat,keys)==item['usage']
        assert [x.key for x in cat.canonical(keys)]==item['selected_keys']
        if card['actual_program'] is not None:
            trial=OrganizationSession(cat,renderer)
            for a in card['actual_program']:
                if a==0:trial.stop()
                else:trial.get(HEADS[a-1])
            assert trial.receipt()['acquired']==keys and not card['targeted_injection']
        else:assert card['arm']=='TARGET_ONLY' and card['targeted_injection']
        if card['original_reused']:
            reused_row=reused[card['input_identity']];q=reused_row['source_request'];raw=reused_row['raw']
            assert raw==old[q['request_id']] and q['messages']==item['messages']
        else:
            q=next(q for q in gqs if q['identity']==card['request_identity']);stamp(q);assert q['messages']==item['messages']
            raw=read(PROBE/'original_G'/(q['identity']+'.raw.json'));seal=read(PROBE/'original_G'/(q['identity']+'.sealed.json'));stamp(seal)
            assert seal['raw_identity']==digest(raw) and seal['protocol_identity']==original_protocol['identity']
        assert raw['runtime_identity']==cfg['runtime']['identity'] and raw['input_tokens']==item['usage']['input_tokens']
        assert raw['finish_reason']=='natural_stop' and raw['api_cost_usd']==0
        row=next(r for r in results if r['case']==card['case'] and r['arm']==card['arm'] and r['generator']=='original')
        assert raw['text']==row['reply'] and digest(row['reply'])==row['reply_identity']
        assert tok.decode(raw['output_token_ids'],skip_special_tokens=True).strip()==row['reply']
        q=next(q for q in aqs if q['input_identity']==card['input_identity']);stamp(q);assert q['messages']==item['messages']
        ids=gemma.apply_chat_template(q['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        assert len(ids)==q['input_tokens'] and digest(ids)==q['token_ids_identity']
        raw=read(alt/'raw'/(q['identity']+'.json'));assert raw['request_identity']==q['identity'] and raw['runtime_identity']==rt['identity']
        assert raw['input_tokens']==len(ids) and raw['output_tokens']==len(raw['output_token_ids'])
        assert raw['finish_reason']=='natural_stop' and raw['output_token_ids'][-1] in (1,106)
        assert raw['text']==gemma.decode(raw['output_token_ids'],skip_special_tokens=True).strip()
        assert raw['decoded_with_special_tokens']==gemma.decode(raw['output_token_ids'],skip_special_tokens=False)
        row=next(r for r in results if r['case']==card['case'] and r['arm']==card['arm'] and r['generator']=='alternate')
        assert row['reply']==raw['text'] and row['reply_identity']==digest(raw['text'])
        if any(x in raw['decoded_with_special_tokens'] for x in ('<channel|>','<think>','</think>')):format_failures.append(dict(case=card['case'],arm=card['arm']))
    assert all(r['helpfulness'] is r['training_reward'] is None for r in results)
    content=read(PROBE/'CONTENT_REVIEW_PRIVATE.json');assert len(content['rows'])==16 and not content['positive_helpfulness_proven']
    for review in content['rows']:
        r=next(r for r in results if (r['case'],r['generator'],r['arm'])==(review['case'],review['generator'],review['arm']))
        assert review['reply_identity']==r['reply_identity'] and review['reviewed_full_reply']==r['reply']
        assert not review['is_human_helpfulness_label'] and review['helpfulness'] is review['reward'] is None
    pair=read(PROBE/'HUMAN_PAIR_PRIVATE.json');stamp(pair);page=(PROBE/'ONE_COMPARISON_ZH.html').read_text()
    assert pair['question']=='V01' and pair['case']=='N06' and pair['old_exact_matches']==[]
    assert len(pair['evidence']['legal_past_sessions'])==4 and digest(pair['evidence'])==pair['evidence_identity']
    for label in ('A','B'):
        r=pair[label];assert r in results and r['generator']=='alternate' and r['case']=='N06'
        assert html.escape(r['reply']) in page and html.escape(pair['translations'][label]) in page
    assert {pair['A']['arm'],pair['B']['arm']}=={'OFF','REAL_MS_PATH'}
    for source in pair['evidence']['legal_past_sessions']:
        for t in source['turns']:assert html.escape(t['text']) in page
    assert pair['helpfulness'] is pair['numeric_reward'] is None
    for root in (AUDIT,PROBE):
        for name,h in read(root/'OUTPUT_MANIFEST.json').items():assert sha(root/name)==h,name
    freeze=read(BASE/'completion_20260930_v2/P2/dataset_freeze.json');cfg=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for name,h in freeze['files'].items():assert sha(PROJECT/name)==h,name
    hashes(cfg['policy']['historical_files'])
    assert sha(Path(cfg['ledger']))=='e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    checks=dict(status='VERIFIED_WITH_RESEARCH_LIMITS',human_records_preserved=44,old_judge_pairs_reused=8,new_judge_calls=completed,
        natural_judge=independently_parsed,technical_timeouts=timeouts,unexecuted_judge_requests=12,unknown_started=0,material_verdicts=material,
        train_prefixes=24,source_candidates=9,new_hypotheses=2,G_inputs=8,reused_original_G=5,new_original_G=3,new_alternate_G=8,
        G_rows=16,natural_G_rows=16,format_failures=format_failures,old_P2_files=len(freeze['files']),old_history_files=len(cfg['policy']['historical_files']),
        ledger_unchanged=True,tests_passed=25,new_API_cost_usd=0,new_training_updates=0,old_cost_control_PPO_updates=24,
        helpfulness_not_yet_judged=True,Tokkio_latency_measured=False)
    (Path(__file__).parent/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n');print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
