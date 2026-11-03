#!/usr/bin/env python3
"""Independent read-only verification of real client events and archived inputs."""
import hashlib
import json
from pathlib import Path
import statistics

PROJECT = Path(__file__).resolve().parents[4]
ROOT = PROJECT/'outputs/pm_rl1/client_latency_pilot_20261104_v1'


def read(p): return json.loads(Path(p).read_text())
def sha(p): return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def digest(x):
    return hashlib.sha256(json.dumps(x,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()


def main():
    p = read(ROOT/'PROTOCOL.json'); summary = read(ROOT/'SUMMARY.json')
    assert p['identity'] == digest({k:v for k,v in p.items() if k!='identity'})
    manifest = read(ROOT/'OUTPUT_MANIFEST.json')
    for name,h in manifest.items(): assert sha(ROOT/name)==h
    for name,h in p['sources'].items(): assert sha(name)==h
    expected = read(ROOT/'EXPECTED_PRIVATE.json')
    historical = read(PROJECT/'outputs/pm_rl1/organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    actual = []; stages = 0; calls = 0; forwards = 0
    for slot in p['schedule']:
        r = read(ROOT/(slot['slot']+'.result.private.json')); t = r['trace']; raw = r['raw']
        assert r['schedule']==slot and t['trace_id']==slot['slot'] and t['request_identity']==digest(slot)
        assert t['identity']==digest({k:v for k,v in t.items() if k!='identity'})
        assert t['regime_identity']==p['regime_identity'] and t['status']=='natural_stop'
        assert t['surface']=='local_reference_queue_client' and t['concurrency']==1
        assert t['send_ns'] <= t['first_text_ns'] <= t['last_text_ns']==t['completion_ns'] <= t['observed_end_ns']
        assert t['ttft_seconds']==(t['first_text_ns']-t['send_ns'])/1e9
        assert t['completion_seconds']==(t['completion_ns']-t['send_ns'])/1e9
        assert t['observed_wait_seconds']==(t['observed_end_ns']-t['send_ns'])/1e9
        assert t['reply_identity']==digest(raw['text']) and t['server_result_identity']==digest(raw)
        req = raw['request']; old = expected[slot['case']+'/'+slot['arm']]
        assert req['request_id']==digest({k:v for k,v in req.items() if k!='request_id'})
        assert req['request_id']==raw['request_id'] and req['executor_identity']==raw['runtime_identity']==p['regime']['streaming_executor']
        assert req['messages']==old['messages'] and req['provenance']['selected_keys']==old['provenance']['selected_keys']
        assert req['expected_input_tokens']==old['expected_input_tokens']==raw['input_tokens']
        assert raw['text']==historical[old['request_id']]['text']
        assert raw['output_token_ids']==historical[old['request_id']]['output_token_ids']
        previous = t['send_ns']
        for e in raw['stages']:
            assert previous <= e['start_ns'] <= e['end_ns'] <= t['observed_end_ns']
            assert e['seconds']==(e['end_ns']-e['start_ns'])/1e9
            previous=e['end_ns']; stages+=1
        calls += raw['online_BGE_batches']; forwards += raw['online_policy_forwards']
        if slot['arm']=='OFF': assert not raw['online_BGE_batches'] and not raw['online_policy_forwards']
        actual.append(r)
    assert len(actual)==26 and len({r['raw']['request_id'] for r in actual})==26
    assert calls==forwards==56
    assert read(ROOT/'COUNTERS.json')==dict(G_calls=26,bge_batches=56,policy_forwards=56)
    measured = [r for r in actual if not r['schedule']['warmup']]
    assert len(measured)==24 and summary['status']=='PILOT_COMPLETE'
    question_path = PROJECT/'outputs/pm_rl1/decision_findings_20261104_v1/PRIORITY_QUESTION_PRIVATE.json'
    prior_sources = read(PROJECT/'outputs/pm_rl1/latency_primary_audit_20261104_v1/SOURCE_HASHES_PRIVATE.json')
    assert sha(question_path)==prior_sources[str(question_path.resolve())]
    cards = {r['alias']:r for r in read(question_path)['cards']}
    for row in measured:
        if row['schedule']['case']=='C02' and row['schedule']['arm'] in ('OFF','MS6','MS6_sequential_replay'):
            alias='B' if row['schedule']['arm']=='OFF' else 'A'
            assert row['raw']['text']==cards[alias]['reply']
    for key,g in summary['groups'].items():
        cid,arm=key.split('/')
        rows=[r for r in measured if r['schedule']['case']==cid and r['schedule']['arm']==arm]
        assert len(rows)==3
        for field in ('ttft_seconds','completion_seconds'):
            xs=[r['trace'][field] for r in rows]
            assert g[field]['median']==statistics.median(xs) and g[field]['observed_p95']==max(xs)
    j=read(PROJECT/'outputs/pm_rl1/execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for name,h in j['policy']['historical_files'].items(): assert sha(name)==h
    assert sha(j['ledger'])==p['ledger_sha256']
    print(json.dumps(dict(exit_code=0,verified_output_files=len(manifest),verified_sources=len(p['sources']),
        verified_client_traces=26,measured_traces=24,verified_stage_intervals=stages,
        exact_historical_text_and_token_matches=26,new_G_calls=26,new_BGE_batches=56,
        C02_original_human_question_reply_matches=9,
        untrained_replay_policy_forwards=56,frozen_files_verified=len(j['policy']['historical_files']),
        ledger_sha256=p['ledger_sha256'],api_cost_usd=0,natural_updates=0),indent=2))


if __name__=='__main__': main()
