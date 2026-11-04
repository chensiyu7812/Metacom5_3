"""Reconcile actual artifacts and input tokens; no G load, calls or training."""
import hashlib,html,json,statistics
from pathlib import Path
from transformers import AutoTokenizer
PROJECT=Path(__file__).resolve().parents[4];BASE=PROJECT/'outputs/pm_rl1';ROOT=BASE/'alternate_executor_probe_20261104_v1'
def read(p):return json.loads(p.read_text())
def sha(p):
    with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
def digest(x):return hashlib.sha256(json.dumps(x,sort_keys=True,ensure_ascii=False,separators=(',',':'),allow_nan=False).encode()).hexdigest()
def stamp(x):assert x['identity']==digest({k:v for k,v in x.items() if k!='identity'})


def main():
    p=read(ROOT/'PROTOCOL.json');stamp(p);rt=p['runtime'];stamp(rt)
    for group in ('sources','code'):
        for path,h in p[group].items():assert sha(Path(path))==h,path
    for folder in ('resource_value_probe_20261104_v1','executor_revision_20261104_v1','executor_revision_20261104_v2'):
        for name,h in read(BASE/folder/'OUTPUT_MANIFEST.json').items():assert sha(BASE/folder/name)==h,name
    model=Path(rt['model_dir'])
    for name,h in rt['model_files'].items():assert sha(model/name)==h,name
    tokenizer=AutoTokenizer.from_pretrained(model,local_files_only=True)
    inputs=read(ROOT/'INPUTS_PRIVATE.json');cards=read(ROOT/'CARDS_PRIVATE.json');old=read(ROOT/'ORIGINALS_PRIVATE.json');req=read(ROOT/'REQUESTS_PRIVATE.json')
    assert len(inputs)==len(req)==36 and len(cards)==len(old)==41
    for name,obj in [('inputs',inputs),('cards',cards),('originals',old),('requests',req)]:assert digest(obj)==p[name+'_identity']
    assert inputs==read(BASE/'resource_value_probe_20261104_v1/INPUTS_PRIVATE.json')
    raws={}
    for r in req:
        stamp(r);item=inputs[r['input_identity']];assert r['messages']==item['messages'] and digest(r['messages'])==r['messages_identity']
        assert r['selected_keys']==item['selected_keys'] and r['selected_resource_identities']==item['selected_resource_identities']
        ids=tokenizer.apply_chat_template(r['messages'],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
        assert len(ids)==r['input_tokens'] and digest(ids)==r['token_ids_identity']
        assert read(ROOT/'raw'/(r['identity']+'.started.json'))==dict(request=r,protocol_identity=p['identity'])
        raw=read(ROOT/'raw'/(r['identity']+'.json'));raws[r['input_identity']]=raw;tokens=raw['output_token_ids']
        assert raw['runtime_identity']==rt['identity'] and raw['request_identity']==r['identity']
        assert raw['input_tokens']==len(ids) and raw['output_tokens']==len(tokens) and tokens[-1] in (1,106)
        assert raw['finish_reason']=='natural_stop' and raw['completed_assistant_turn'] and raw['api_cost_usd']==0
        assert raw['text']==tokenizer.decode(tokens,skip_special_tokens=True).strip() and raw['text_identity']==digest(raw['text'])
        assert raw['decoded_with_special_tokens']==tokenizer.decode(tokens,skip_special_tokens=False)
        assert raw['quality'] is raw['reward'] is None and 0<raw['first_token_seconds']<=raw['generation_seconds']
    assert len(list((ROOT/'raw').glob('*.json')))==72
    results=read(ROOT/'RESULTS_PRIVATE.json');review=read(ROOT/'CONTENT_REVIEW_PRIVATE.json');stamp(review)
    inventory={x['case']:x for x in read(BASE/'resource_value_probe_20261104_v1/INVENTORY_PRIVATE.json')}
    assert len(results)==len(review['rows'])==41 and len(review['format_failures'])==1 and not review['qualified_stronger_G']
    for c,o,r,a in zip(cards,old,results,review['rows']):
        assert c['case']==o['case']==r['case']==a['case'] and c['arm']==o['arm']==r['arm']==a['arm']
        raw=raws[c['input_identity']];assert r['new_reply']==raw['text'] and r['old_reply']==o['reply']
        assert a['new_reply_identity']==digest(r['new_reply']) and a['old_reply_identity']==digest(r['old_reply'])
        for q in a['new_reply_anchors']:assert r['new_reply'][q['start']:q['end']]==q['quote']
        assert a['old_reply_anchor']['quote']==r['old_reply']
        for q in a['source_anchors']:assert q in inventory[a['case']]['target_source']['turns']
        assert a['quality'] is a['reward'] is a['human_quality_label'] is None
    bad=[v for v in raws.values() if '<channel|>' in v['decoded_with_special_tokens']];assert len(bad)==1
    assert bad[0]['request_identity']==review['format_failures'][0]['request_identity']
    pairs=read(ROOT/'HUMAN_PAIRS_PRIVATE.json');skips=read(ROOT/'HUMAN_PAIRS_SKIPPED_PRIVATE.json');page=(ROOT/'HUMAN_REVIEW_ZH.html').read_text()
    assert len(pairs)==8 and len(skips)==1 and skips[0]['reason']=='technical_format_failure_not_zero_gain'
    assert sum(x['kind']=='within_G_resource' for x in pairs)==6 and sum(x['kind']=='OFF_cross_G' for x in pairs)==2
    for q in pairs:
        left=next(r for r in results if r['case']==q['case'] and r['arm']==q['left_arm']);right=next(r for r in results if r['case']==q['case'] and r['arm']==q['right_arm'])
        assert q['left']==left['new_reply'] and q['right']==right['old_reply' if q['kind']=='OFF_cross_G' else 'new_reply']
        a,b=(q['right'],q['left']) if q['reverse'] else (q['left'],q['right'])
        assert q['A_identity']==digest(a) and q['B_identity']==digest(b) and q['evidence_identity']==digest(q['evidence']) and not q['reused']
        assert q['evidence']['legal_past_source']==inventory[q['case']]['target_source']
        assert q['evidence']['current_prefix']==[dict(speaker=t['role'],text=t['text']) for t in inventory[q['case']]['current_prefix']]
        assert html.escape(a) in page and html.escape(b) in page
    assert 'Gemma' not in page and 'Llama' not in page and page.count('<select ')==8
    freeze=read(BASE/'completion_20260930_v2/P2/dataset_freeze.json');cfg=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for name,h in freeze['files'].items():assert sha(PROJECT/name)==h,name
    for name,h in cfg['policy']['historical_files'].items():assert sha(Path(name))==h,name
    assert sha(Path(cfg['ledger']))=='e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    closed=read(ROOT/'CLOSED.json');stamp(closed);assert closed['completed']==closed['natural']==closed['completed_assistant_turns']==36
    times={k:dict(min=min(v[k] for v in raws.values()),median=statistics.median(v[k] for v in raws.values()),max=max(v[k] for v in raws.values())) for k in ('first_token_seconds','generation_seconds')}
    checks=dict(status='VERIFIED',unique_new_G=36,cards=41,natural=36,format_failures=1,qualified_stronger_G=False,human_pairs=8,human_answers_received=0,
        old_P2_files=len(freeze['files']),old_history_files=len(cfg['policy']['historical_files']),old_ledger_unchanged=True,API_cost_usd=0,new_PM_updates=0,new_G_training_updates=0,
        old_cost_control_PPO_updates=24,component_timing_seconds=times,Tokkio_latency_measured=False,production_promoted=False)
    (Path(__file__).parent/'CHECKS.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2)+'\n');print(json.dumps(checks,ensure_ascii=False))


if __name__=='__main__':main()
