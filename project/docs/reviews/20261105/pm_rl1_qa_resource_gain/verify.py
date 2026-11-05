"""Read-only source, ranking, request and outcome integrity checks."""
import hashlib
import json
from pathlib import Path
import sys
from collections import Counter

import numpy as np

PROJECT=Path(__file__).resolve().parents[4]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.calibration_workflow import verify_identity

OUT=PROJECT/'outputs/pm_rl1/qa_resource_gain_20261105_v1'
OLD=PROJECT/'outputs/pm_rl1/dataset_diagnostics_20260930_v1'


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (OUT/'PREPARATION_MANIFEST.json').exists():
        for rel,h in read(OUT/'PREPARATION_MANIFEST.json').items():
            assert sha(OUT/rel)==h,rel
    p=read(OUT/'alternate_G/PROTOCOL.json');verify_identity(p);verify_identity(p['runtime'])
    for group in ('sources','code'):
        for path,h in p[group].items():assert sha(Path(path))==h,path
    screening=read(OUT/'SCREENING_PROTOCOL.json');verify_identity(screening)
    for path,h in screening['sources'].items():assert sha(Path(path))==h,path
    for path,h in read(PROJECT/'outputs/pm_rl1/value_and_novelty_audit_20261105_v1/SOURCE_MANIFEST.json').items():
        assert sha(Path(path))==h,path
    decision=read(OUT/'DECISION_PROTOCOL.json');verify_identity(decision)
    assert decision['identity']==p['decision_identity']
    original={(r['owner'],r['group'],r['idx']):r for r in read(OLD/'qa_train_dev_review_private.json')}
    cases=read(OUT/'CANDIDATES_PRIVATE.json');case_map={r['case']:r for r in cases}
    assert len(cases)==len(case_map)==30
    for c in cases:
        row=c['source'];assert row==original[(row['owner'],row['group'],row['idx'])]
        assert row['split']=='train' and digest(row)==c['source_identity']
        assert not row['private_event_refs'] and not row['unresolved_refs']
    history=read(OUT/'HISTORY_PRIVATE.json')
    runtime_path=Path(read(OLD/'input_manifest.json')['runtime']['path'])
    runtime={u['owner_id']:u['sessions'] for u in read(runtime_path)['users'] if u['owner_id'] in history}
    assert history==runtime and len(history)==12
    assert sum(map(len,history.values()))==275
    for c in cases:
        ss={s['session_id']:s for s in history[c['source']['owner']]}
        for ref in c['source']['reference_resolution']:
            assert ref['session'] in ss
            if ref['kind']=='visible_turn':
                assert any(t['content']==ref['text'] and t['role']==ref['role'] for t in ss[ref['session']]['turns'])
    notes=read(OUT/'SOURCE_REVIEW_PRIVATE.json')['rows'];note_map={r['case']:r for r in notes}
    assert set(note_map)==set(case_map)
    assert Counter(r['decision'] for r in notes)=={
        'admit_factual_diagnostic':14,'admit_semantic_diagnostic':5,'exclude_before_generation':11}
    assert not any(r['question_changed'] or r['gold_changed'] for r in notes)
    enc=read(OUT/'ENCODING_COMPLETE.json');verify_identity(enc)
    assert sha(OUT/'VECTORS.npy')==enc['vectors_sha256']
    assert sha(OUT/'RANKS_PRIVATE.json')==enc['ranks_sha256']
    assert sha(OUT/'ENCODING_RECORDS_PRIVATE.json')==enc['records_sha256']
    vectors=np.load(OUT/'VECTORS.npy',allow_pickle=False)
    records=read(OUT/'ENCODING_RECORDS_PRIVATE.json');rankings=read(OUT/'RANKS_PRIVATE.json')
    assert vectors.shape==(305,1024) and np.isfinite(vectors).all()
    assert np.allclose(np.linalg.norm(vectors,axis=1),1,atol=1e-5)
    def session_text(s):
        return 'Conversation recorded on '+s['timestamp']+'\n'+'\n'.join(t['role']+': '+t['content'] for t in s['turns'])
    for i,r in enumerate(records):
        if r['kind']=='session':
            s=next(s for s in history[r['owner']] if s['session_id']==r['key'])
            assert r['text']==session_text(s)
        else:
            assert r['text']==case_map[r['key']]['source']['question']
            pool=[(j,s) for j,s in enumerate(records) if s['kind']=='session' and s['owner']==r['owner']]
            rescored=[(s['key'],float(vectors[i]@vectors[j])) for j,s in pool]
            rescored.sort(key=lambda x:(-x[1],x[0]))
            stored=rankings[r['key']]
            assert [s['session'] for s in stored]==[sid for sid,score in rescored]
            assert np.allclose([s['score'] for s in stored],[score for sid,score in rescored],atol=1e-6)
    cards=read(OUT/'CARDS_PRIVATE.json');requests=read(OUT/'alternate_G/REQUESTS_PRIVATE.json')
    assert digest(requests)==p['requests_identity']
    req_map={r['input_identity']:r for r in requests}
    assert len(cards)==95 and len(req_map)==len(requests)==p['max_calls']==86
    assert Counter(r['arm'] for r in cards)=={a:19 for a in ['OFF','C','D','R1','R2']}
    controls=read(OUT/'CONTROL_REVIEW_PRIVATE.json')
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(p['runtime']['model_dir'],local_files_only=True)
    for req in requests:
        verify_identity(req)
        assert digest(req['messages'])==req['messages_identity']
        native=tok.apply_chat_template(req['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        assert len(native)==req['input_tokens'] and digest(native)==req['token_ids_identity']
    for card in cards:
        c=case_map[card['case']];req=req_map[card['input_identity']]
        assert card['owner']==c['source']['owner']
        assert card['quality'] is None and card['reward'] is None
        assert req['selected_keys']==card['selected_keys']
        ss={s['session_id']:s for s in history[card['owner']]}
        keys=card['selected_keys']
        assert set(keys)<=set(ss)
        if card['arm']=='OFF':assert keys==[]
        if card['arm']=='C':assert keys==c['cited_sessions']
        if card['arm']=='D':assert keys==controls[card['case']]['approved_D']
        if card['arm'] in ('R1','R2'):
            assert keys==[r['session'] for r in rankings[card['case']][:int(card['arm'][1])]]
        expected='Historical conversations:\n'+('\n\n'.join(session_text(ss[k]) for k in keys) if keys else '(none supplied)')
        expected+='\n\nQuestion: '+c['source']['question']
        assert req['messages'][1]=={'role':'user','content':expected}
        assert req['selected_resource_identities']==[digest(ss[k]) for k in keys]
    assert len({c['owner'] for c in cards if c['case'] in decision['primary_cases']})==11
    # Negated mention must not silently pass an entity/alias scorer.
    import importlib.util
    spec=importlib.util.spec_from_file_location('qa_probe',PROJECT/'scripts/rl1/176_probe_qa_resource_gain.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    assert module.normalized_answer('Emily.')==module.normalized_answer('EMILY')
    assert module.normalized_answer('Not Emily')!=module.normalized_answer('Emily')
    assert module.normalized_answer('Emily or Sally')!=module.normalized_answer('Emily')
    raws=list((OUT/'alternate_G/raw').glob('*.json'))
    actual=[f for f in raws if not f.name.endswith('.started.json')]
    for f in actual:
        raw=read(f);req=next(r for r in requests if r['identity']==raw['request_identity'])
        assert raw['input_identity']==req['input_identity'] and raw['runtime_identity']==p['runtime']['identity']
        assert raw['text_identity']==digest(raw['text'])
    result=dict(status='PASS',source_candidates=30,source_admitted=19,primary_facts=14,primary_owners=11,
        secondary_semantic=5,excluded_before_generation=11,full_train_sessions=275,
        CPU_BGE_records=305,rankings_independently_recomputed=30,logical_conditions=95,unique_G_requests=86,
        natural_G_outputs=sum(read(f)['finish_reason']=='natural_stop' for f in actual),
        G_load_entered=(OUT/'alternate_G/LOAD_STARTED.json').exists(),new_rewards=0,new_training=0,
        test_gold_used=False,prior_sources_unchanged=True,
        scope='Source/ranking/request integrity, not an effect or deployment-latency result.')
    print(json.dumps(result,ensure_ascii=False,indent=2))


if __name__=='__main__':
    main()
