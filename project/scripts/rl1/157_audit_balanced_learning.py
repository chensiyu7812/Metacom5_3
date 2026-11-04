#!/usr/bin/env python3
"""Read-only evidence audit, optionally save a NEW local report; no models/API."""
import argparse
from collections import Counter
import json
from pathlib import Path
import statistics
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.balanced_objective import BalancedObjective,revalue_handoff,timing_receipt
from metacom_pm.rl1.calibration_workflow import verify_identity
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import file_sha,save_json

BASE=PROJECT/'outputs/pm_rl1'


def read(path):return json.loads(Path(path).read_text())


def checked(root):
    manifest=read(root/'OUTPUT_MANIFEST.json')
    for name,sha in manifest.items():
        if file_sha(root/name)!=sha:raise ValueError('output changed: '+name)
    return len(manifest)


def audit(output=None):
    menu=read(BASE/'organized_initial_training_20261103_v2/MENU_PRIVATE.json')
    responses=read(BASE/'organized_initial_generation_20261103_v2/RESPONSES_PRIVATE.json')
    handoff=read(BASE/'organized_initial_validation_20261103_v1/HANDOFF_PRIVATE.json')
    memo=BASE/'memoized_online_validation_20261104_v1';checked(memo)
    for name,sha in read(memo/'SOURCES.json').items():assert file_sha(name)==sha
    replay=read(memo/'REPLAYS_PRIVATE.json');validation=read(memo/'SUMMARY.json')
    assert {r['endpoint_identity'] for r in replay}=={e['identity'] for e in menu['endpoints']}
    assert len(replay)==validation['programs']==487 and validation['unique_public_observations']==591
    assert {k:sum(r['stats'][k] for r in replay) for k in validation['totals']}==validation['totals']
    receipts=[];coverage={};verified_files=0;new_pairs={};exact_matches=0
    question=read(BASE/'decision_findings_20261104_v1/PRIORITY_QUESTION_PRIVATE.json')
    cards={r['alias']:r['reply'] for r in question['cards']};human_matches=0
    evidence_roots=['client_latency_pilot_20261104_v1','memoized_latency_pilot_20261104_v1']
    for dirname in evidence_roots:
        root=BASE/dirname;p=read(root/'PROTOCOL.json');verify_identity(p);verified_files+=checked(root)
        for name,sha in p['sources'].items():assert file_sha(name)==sha
        recent=dirname.startswith('memoized');measured=[];bge=0;forwards=0
        for slot in p['schedule']:
            r=read(root/(slot['slot']+'.result.private.json'));raw=r['raw'];t=r['trace']
            assert r['schedule']==slot and t['trace_id']==slot['slot'] and t['regime_identity']==p['regime_identity']
            if recent or slot['arm']=='MS6_sequential_replay':actions=[3]*6+[0];family='sequential'
            else:actions={'OFF':[0],'MS1':[3,0],'MS6':[3]*6+[0]}[slot['arm']];family='fixed'
            e=next(e for e in menu['endpoints'] if e['prefix_identity']==p['cases'][slot['case']] and e['actions']==actions)
            response=responses[e['requests']['ON']['request_id']]
            receipt=timing_receipt(e,response,trace=t,raw=raw,payload=slot,path_family=family,source_identity=p['identity'])
            assert raw['text']==response['text'] and raw['output_token_ids']==response['output_token_ids'];exact_matches+=1
            previous=t['send_ns']
            for stage in raw['stages']:
                assert previous<=stage['start_ns']<=stage['end_ns']<=t['observed_end_ns']
                assert stage['seconds']==(stage['end_ns']-stage['start_ns'])/1e9
                previous=stage['end_ns']
            bge+=raw['online_BGE_batches']
            forwards+=sum(s['stage']=='actor_forward_scripted_action' for s in raw['stages'])
            if not slot['warmup']:
                receipts.append(receipt);measured.append(r)
                key=dirname+'/'+slot.get('path',family)
                coverage.setdefault(key,set()).add(e['identity'])
                if slot['case']=='C02' and actions in ([0],[3]*6+[0]):
                    assert raw['text']==cards['B' if actions==[0] else 'A'];human_matches+=1
        assert len(p['schedule'])==(14 if recent else 26)
        assert bge==forwards==(98 if recent else 56)
        if recent:
            summary=read(root/'SUMMARY.json')
            assert summary['counters']==dict(BGE_batches=bge,policy_forwards=forwards,G_calls=14)
            for cid in p['cases']:
                lookup={(r['schedule']['repeat'],r['schedule']['path']):r for r in measured if r['schedule']['case']==cid}
                new_pairs[cid]={f:statistics.median(lookup[(i,'memoized')]['trace'][f]-lookup[(i,'legacy')]['trace'][f]
                    for i in range(3)) for f in ('ttft_seconds','completion_seconds')}
                for path in ('legacy','memoized'):
                    g=summary['groups'][cid+'/'+path]
                    for f in ('ttft_seconds','completion_seconds'):
                        assert g[f]==statistics.median(lookup[(i,path)]['trace'][f] for i in range(3))
            assert new_pairs==summary['paired_memoized_minus_legacy']
    # Weight zero is an audit placeholder, NOT an operating choice: quality
    # absence must block compilation for any weight and any timing coverage.
    pending=revalue_handoff(handoff,menu,timings={},responses=responses,
        objective=BalancedObjective(0.,'AUDIT_ONLY_NO_SELECTED_DEPLOYMENT'),path_family='sequential')
    assert pending['status']=='PENDING_QUALITY' and pending['targets']==pending['measured']==[]
    j=read(BASE/'execution_bridges_20261103_v1/J_CONFIG_PRIVATE.json')
    for name,sha in j['policy']['historical_files'].items():assert file_sha(name)==sha
    ledger_sha=file_sha(j['ledger'])
    assert ledger_sha=='e43efd58c264d29e89fadf1bc5b9c2162e2247a452bfa32f7296979e55ede417'
    summary=dict(status='VERIFIED',real_programs_exactly_preserved=487,real_observations_exactly_preserved=591,
        usage_calls=validation['totals']['usage_calls'],usage_computations=validation['totals']['usage_misses'],
        verified_output_files=verified_files,verified_real_traces=exact_matches,measured_timing_receipts=len(receipts),
        paired_memoized_minus_legacy=new_pairs,timing_coverage={k:len(v) for k,v in coverage.items()},
        sequential_STOP_costs=0,oneshot_costs=0,no_text_costs=0,
        C02_exact_prior_human_reply_matches=human_matches,
        current_behavior_bound_timing_receipts=sum(r['behavior_identity'] is not None for r in receipts),
        actual_handoff_status=pending['status'],pending_quality_endpoints=len(pending['pending']),
        selected_seconds_weight=None,frozen_files_verified=len(j['policy']['historical_files']),ledger_sha256=ledger_sha,
        new_G_calls_this_stage=14,new_BGE_batches_this_stage=98,new_untrained_policy_forwards_this_stage=98,
        API_cost_usd=0,natural_BC_checkpoints=0,natural_PPO_updates=0)
    if output is not None:
        if output.exists():raise ValueError('new output required')
        output.mkdir(parents=True,mode=0o700)
        save_json(output/'SUMMARY.json',summary);save_json(output/'TIMING_RECEIPTS_PRIVATE.json',receipts)
        paths=[Path(__file__)]+[PROJECT/'src/metacom_pm/rl1'/(n+'.py') for n in ('balanced_objective','balanced_learning')]
        paths += [BASE/n/'OUTPUT_MANIFEST.json' for n in [*evidence_roots,'memoized_online_validation_20261104_v1']]
        paths += [BASE/'organized_initial_training_20261103_v2/MENU_PRIVATE.json',
            BASE/'organized_initial_validation_20261103_v1/HANDOFF_PRIVATE.json']
        save_json(output/'SOURCES.json',{str(p.resolve()):file_sha(p) for p in paths})
        save_json(output/'OUTPUT_MANIFEST.json',{p.name:file_sha(p) for p in output.iterdir()})
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path)
    audit(parser.parse_args().output)
