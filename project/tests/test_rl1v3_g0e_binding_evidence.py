"""Public CPU checks on the actual, immutable joint replay and preflight packets."""
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.io import canonical_json,decode_contract,file_sha256,object_sha256
ROOT=Path(__file__).resolve().parents[2]
BASE=ROOT/'project/outputs/pm_rl1/v3'

def jl(p):return [json.loads(x) for x in p.read_text().splitlines()]

def test_all_120_real_bindings_and_471_traces_keep_old_new_identities_separate():
    root=BASE/'G0e_binding_20261118'
    rows=jl(root/'KEY_BINDINGS.jsonl');orders=jl(root/'ORDER_CHECKS.jsonl');requests=jl(root/'CPU_REQUESTS_ONLY.jsonl')
    assert len(rows)==len(requests)==120 and len(orders)==471
    assert Counter(Counter(r['prefix_id'] for r in rows).values())=={16:7,8:1}
    request_ids={r['request_id'] for r in requests};assert len(request_ids)==120
    for r in rows:
        old=decode_contract(K.TerminalKey,canonical_json(r['old_key']))
        new=decode_contract(K.TerminalKey,canonical_json(r['new_key']))
        trace=decode_contract(K.ExecutionTrace,canonical_json(r['new_trace']));trace.verify_key(new)
        assert old.sha256==r['old_key_sha256'] and new.sha256==r['new_key_sha256'] and old.sha256!=new.sha256
        assert old.acquired==new.acquired and old.ordered_path==new.ordered_path
        assert old.bank_version==new.bank_version and old.index_version==new.index_version
        assert set(r['changed_identity_fields'])=={'renderer_id','step2_id','g_id','decode_id'}
        assert r['request_sha256'] in request_ids and r['terminal_status']=='pending'
    by_key={}
    for r in orders:assert by_key.setdefault(r['key_sha256'],r['request_sha256'])==r['request_sha256']
    assert len(by_key)==120


def test_request_payload_whitelist_native_lengths_and_off():
    rows=jl(BASE/'G0e_binding_20261118/CPU_REQUESTS_ONLY.jsonl')
    assert sum(r['subset']=='OFF' for r in rows)==8
    for r in rows:
        assert len(r['input_ids'])==r['input_tokens'] and len(r['input_ids'])+320<=16384
        assert r['decode']['max_new_tokens']==320 and r['decode']['do_sample'] is False
        assert all(set(m)=={'role','content'} for m in r['messages'])
        text=canonical_json(r['messages'])
        assert r['prefix_id'] not in text and r['terminal_key_sha256'] not in text
        if r['subset']=='OFF':assert not any('<Notes>' in m['content'] for m in r['messages'])
        else:assert r['messages'][1]['content'].startswith('Notes')


def test_new_probe_does_not_expand_calls_or_mutate_old_off():
    root=BASE/'A0_preflight_supplement_20261118';plan=json.loads((root/'GPU_PLAN.json').read_text())
    old=BASE/'A0_bounded_cpu_20261118';oldplan=json.loads((old/'GPU_PLAN.json').read_text())
    assert object_sha256(oldplan)==plan['parent_plan_sha256']
    newrows=jl(root/'gemma_requests.jsonl');oldrows=jl(old/'gemma_requests.jsonl')
    assert [r for r in newrows if r['condition']=='OFF_reused']==[r for r in oldrows if r['condition']=='OFF_reused']
    assert len(newrows)==132
    for name,n in [('gemma',154),('needcard',7)]:
        cfg=plan['workloads'][name];assert sum(b['batch'] for b in cfg['batches'])+cfg['warmup_calls']==cfg['max_calls']==n
        assert file_sha256(root/cfg['requests_file'])==cfg['requests_sha256']
    for path,sha in plan['code_sha256'].items():assert file_sha256(ROOT/path)==sha
    assert file_sha256(root/plan['checkpoint_preflight_file'])==plan['checkpoint_preflight_sha256']
    assert plan['gpu_authorized'] is False and plan['j1']['requests_prepared']==0


def test_no_gpu_approval_is_rejected_before_device_access_or_output_creation(tmp_path):
    base=BASE/'A0_preflight_supplement_20261118';out=tmp_path/'forbidden'
    result=subprocess.run([sys.executable,str(ROOT/'project/scripts/rl1v3/a0_bounded_run_v2.py'),
        '--plan',str(base/'GPU_PLAN.json'),'--approval',str(base/'APPROVAL_TEMPLATE_NOT_AUTHORIZED.json'),
        '--workload','gemma','--out',str(out)],capture_output=True,text=True)
    assert result.returncode!=0 and 'separate researcher GPU authorization is required' in result.stderr
    assert not out.exists()


def test_review_pack_preserves_prior_development_checks_and_full_legal_candidate_sets():
    from metacom_pm.rl1v3.bank.v0_port import load_bank
    from metacom_pm.rl1v3.retrieve.v0 import search
    bank,_=load_bank(ROOT);root=BASE/'relevance_review_20261118'
    rows=jl(root/'REVIEW_SAMPLES.jsonl');catalog={r['record_id']:r for r in jl(root/'CANDIDATE_RECORDS.jsonl')}
    summary=json.loads((root/'SUMMARY.json').read_text())
    assert file_sha256(BASE/'relevance_dev_20261118/DIAGNOSTIC.jsonl')==summary['retained_prior_sha256']
    assert summary['retained_prior_rows']==12 and summary['recall_accuracy'] is None
    assert set(r['head'] for r in rows)=={'RS','MP','ME','MS'}
    for r in rows:
        meta=r['prefix'];p=bank.registry.prefix(meta['owner_id'],meta['session_id'],meta['cut_turn'])
        search_result=search(bank,r['head'],p)
        assert [(c.record_id,c.score) for c in search_result.ranked]==[(x['record_id'],x['score']) for x in r['legal_candidates']]
        assert len(search_result.ranked)==r['legal_candidate_count']
        for c in search_result.ranked:assert canonical_json(bank.by_id[c.record_id])==canonical_json(catalog[c.record_id])
        assert r['reviewer_fields']['topic_relevance']=='unreviewed'
        assert 1<=meta['fold']<=5
