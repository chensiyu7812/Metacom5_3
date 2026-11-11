"""Independent integrity checks for the two completed development probes."""
from collections import Counter
import importlib.util
import json
from pathlib import Path
import sys

PROJECT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(PROJECT/'src'))
from metacom_pm.io import sha256_file as sha
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.calibration_workflow import verify_identity

BASE=PROJECT/'outputs/pm_rl1'
QA=BASE/'qa_resource_gain_20261105_v1'
TYPED=BASE/'typed_resource_views_20261111_v1'


def read(path):
    return json.loads(path.read_text())


def check_execution(root, expected):
    for name,h in read(root/'PREPARATION_MANIFEST.json').items():
        assert sha(root/name)==h, name
    p=read(root/'alternate_G/PROTOCOL.json');verify_identity(p);verify_identity(p['runtime'])
    for group in ('sources','code'):
        for name,h in p[group].items():
            if sha(Path(name))==h:continue
            # The completed generator used the preserved source. Only the
            # post-run collector's duplicate kwargs were fixed afterward.
            fix=read(root/'POST_EXECUTION_ANALYSIS_FIX.json')
            original=Path(fix['preserved_execution_source'])
            assert group=='code' and name==fix['path'] and h==fix['old_sha256']==sha(original)
            assert sha(Path(name))==fix['new_sha256'] and fix['new_generations']==0
            assert Path(name).read_text()==original.read_text().replace(
                "and raw['completed_assistant_turn']),quality=None,reward=None))",
                "and raw['completed_assistant_turn'])))")
    reqs=read(root/'alternate_G/REQUESTS_PRIVATE.json')
    assert digest(reqs)==p['requests_identity'] and len(reqs)==expected
    from transformers import AutoTokenizer
    tok=AutoTokenizer.from_pretrained(p['runtime']['model_dir'],local_files_only=True)
    assert digest(tok.chat_template)==p['runtime']['chat_template_identity']
    for r in reqs:
        verify_identity(r);assert digest(r['messages'])==r['messages_identity']
        ids=tok.apply_chat_template(r['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        assert len(ids)==r['input_tokens'] and digest(ids)==r['token_ids_identity']
        path=root/'alternate_G/raw'/(r['identity']+'.json')
        raw=read(path);start=read(path.with_name(r['identity']+'.started.json'))
        assert start['request']==r and start['protocol_identity']==p['identity']
        assert raw['runtime_identity']==r['runtime_identity'] and raw['request_identity']==r['identity']
        assert raw['input_identity']==r['input_identity'] and raw['text_identity']==digest(raw['text'])
        assert raw['input_tokens']==len(ids) and raw['output_tokens']==len(raw['output_token_ids'])
        assert tok.decode(raw['output_token_ids'],skip_special_tokens=True).strip()==raw['text']
        assert raw['finish_reason']=='natural_stop' and raw['completed_assistant_turn']
        assert raw['output_token_ids'][-1] in p['runtime']['policy']['eos_token_ids']
        assert raw['quality'] is None and raw['reward'] is None and raw['api_cost_usd']==0
    closed=read(root/'alternate_G/CLOSED.json');verify_identity(closed)
    assert closed['completed']==closed['natural']==closed['planned']==expected
    assert len(list((root/'alternate_G/raw').glob('*.started.json')))==expected
    return {r['input_identity']:r for r in reqs}


def main():
    qa_requests=check_execution(QA,86)
    typed_requests=check_execution(TYPED,42)
    # Recompute the QA screen from fixed source verdicts, not report prose.
    decision=read(QA/'DECISION_PROTOCOL.json');verify_identity(decision)
    results=read(QA/'RESULTS_PRIVATE.json');verdicts=read(QA/'BLIND_SOURCE_VERDICTS_PRIVATE.json')
    assessment=read(QA/'ASSESSMENT_00.json');assert len(results)==95
    expected=[]
    for r in results:
        req=qa_requests[r['input_identity']]
        raw=read(QA/'alternate_G/raw'/(req['identity']+'.json'))
        assert r['raw']==raw and r['valid'] and r['quality'] is None and r['reward'] is None
        v=verdicts[r['blind_review_id']];assert v['reply_identity']==digest(raw['text'])
        expected.append(dict(case=r['case'],arm=r['arm'],owner=r['owner'],valid=True,verdict=v['verdict']))
    assert len(verdicts)==86
    spec=importlib.util.spec_from_file_location('assessor',PROJECT/'scripts/rl1/177_assess_qa_resource_gain.py')
    assessor=importlib.util.module_from_spec(spec);spec.loader.exec_module(assessor)
    summary=assessor.summarize(expected,decision['primary_cases'],decision)
    assert all(assessment['summary'][k]==v for k,v in summary.items())
    primary=set(decision['primary_cases'])
    correct={a:sum(r['case'] in primary and r['arm']==a and r['verdict']=='correct' for r in expected)
             for a in ('OFF','C','D','R1','R2')}
    assert correct==dict(OFF=0,C=13,D=1,R1=10,R2=12)
    # Separately treat visible thought artifacts as failures; do not rewrite originals.
    strict=[]
    for r, original in zip(expected, results):
        strict.append(dict(r,verdict='incorrect' if verdicts[original['blind_review_id']]['format_artifact'] else r['verdict']))
    strict_summary=assessor.summarize(strict,decision['primary_cases'],decision)
    assert strict_summary['resource_gate_passed'] and strict_summary['short_retrieval_screen_passed']
    # Source-view comparison: same initial input; literal subset versus complete
    # parent source; no private summary, score, or analyst claim in G input.
    cards=read(TYPED/'CARDS_PRIVATE.json');inputs=read(TYPED/'INPUTS_PRIVATE.json')
    views=read(TYPED/'VIEWS_PRIVATE.json');outcomes=read(TYPED/'RESULTS_PRIVATE.json')
    assert len(cards)==len(outcomes)==42 and len(views)==6
    assert len({r['owner'] for r in views})==6
    families=read(TYPED/'STRATEGY_CANDIDATES.json')
    assert len(families['strategies'])==8
    for v in views:
        pid=v['prefix'];src=read(BASE/'organized_initial_training_20261103_v2/sources_private'/(pid+'.json'))
        stored=read(Path(src['stored_source_path']));memory={x['key']:x for x in stored['memory']}
        prefix=src['prefix'];assert prefix['split']=='train' and prefix['owner_id']==v['owner']
        assert v['semantic_relations_created']==v['current_facts_created']==0
        assert v['reward'] is None
        parents=sorted((memory[k] for k in v['parent_keys']),key=lambda x:(x['source_rank'],x['key']))
        for short,full,parent in zip(v['compact']['sessions'],v['full']['sessions'],parents):
            assert parent['owner_id']==prefix['owner_id'] and parent['source_rank']<prefix['cutoff_rank']
            assert short['recorded_at']==full['recorded_at']==parent['reported_at']<=prefix['timestamp']
            assert '\n'.join(t[1]+': '+t[2] for t in full['turns'])==json.loads(parent['content'])['full_source_conversation']
            assert all(t==full['turns'][t[0]] for t in short['turns'])
            assert short['omitted_turns']==len(full['turns'])-len(short['turns']) and full['omitted_turns']==0
            desired=set()
            for binding in v['bindings']:
                if binding['source_key']!=parent['key']:continue
                item=memory[binding['key']];body=json.loads(item['content'])
                assert parent['key'] in v['parent_keys'] and set(parent['source_ids']) & set(item['source_ids'])
                assert binding['original_compiler_statement']==body['past_report']
                found=[]
                for span in body['evidence']:
                    indices=[t[0] for t in full['turns'] if t[1]==span['speaker']
                             and t[2][span['start_char']:span['end_char']]==span['quote']]
                    assert len(indices)==1;found.extend(indices)
                    i=indices[0];desired.update(range(max(0,i-1),min(len(full['turns']),i+2)))
                assert sorted(set(found))==binding['evidence_turns']
            assert sorted(desired)==[t[0] for t in short['turns']]
        case_cards=[c for c in cards if c['case']==v['case']]
        assert len(case_cards)==7
        base=inputs[next(c['input_identity'] for c in case_cards if c['arm']=='B_basic')]['messages']
        for c in case_cards:
            req=typed_requests[c['input_identity']];ms=inputs[c['input_identity']]['messages']
            assert req['messages']==ms and ms[1]==base[1] and ms[0]['content'].startswith(base[0]['content'])
            assert ms[1]['content']==prefix['turns'][-1]['content']
            if c['arm'] in ('V_source_view','VS_source_and_strategy','F_full_sources'):
                payload=inputs[c['input_identity']]['source_payload']
                assert payload==v['full' if c['arm']=='F_full_sources' else 'compact']
                assert 'original_compiler_statement' not in ms[0]['content']
    for r in outcomes:
        req=typed_requests[r['input_identity']]
        assert r['raw']==read(TYPED/'alternate_G/raw'/(req['identity']+'.json'))
        assert r['valid'] and r['quality'] is None and r['reward'] is None
    print(json.dumps(dict(status='PASS',QA_unique_requests=86,QA_logical_conditions=95,
        QA_primary_correct_of_14=correct,QA_gate_survives_format_failure_sensitivity=True,
        typed_contexts=6,typed_owners=6,typed_conditions=42,strategies=8,
        all_native_tokens_and_raw_outputs_verified=True,source_windows_and_full_parents_verified=True,
        old_preparation_manifests_unchanged=True,training=0,API_cost_usd=0),ensure_ascii=False,indent=2))


if __name__=='__main__':main()
