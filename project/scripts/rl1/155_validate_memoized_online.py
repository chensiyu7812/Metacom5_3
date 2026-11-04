#!/usr/bin/env python3
"""Replay all 487 real programs against archived states; no weights or API."""
import argparse
from dataclasses import asdict,replace
from pathlib import Path
import sys
import time

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.memoized_online import RequestRenderer,MemoizedHeadSession
from metacom_pm.rl1.online_materials import read,load_materials
from metacom_pm.rl1.organized_feedback import generation_request
from metacom_pm.rl1.schema import digest
from metacom_pm.rl1.supervised_learning import save_json,file_sha


def run(output):
    if output.exists(): raise ValueError('new output directory required')
    source=PROJECT/'outputs/pm_rl1/organized_initial_training_20261103_v2'
    c,catalogs,renderer=load_materials(source)
    states=read(source/'OBSERVATIONS_PRIVATE.json'); menu=read(source/'MENU_PRIVATE.json')
    seen=set(); rows=[]; started=time.monotonic()
    for index,e in enumerate(menu['endpoints']):
        memo=RequestRenderer(renderer); session=MemoizedHeadSession(catalogs[e['prefix_identity']],memo)
        for action in e['actions']:
            before=session.observe(); key=digest(asdict(before));seen.add(key)
            if key not in states or digest(states[key]['observation'])!=key:
                raise ValueError('actual observation differs from the real encoded source')
            after=session.step(action,expected_observation=key)
            if action==0 and after!=replace(before,stopped=True,action_mask=(False,)*5):
                raise ValueError('terminal observation changed')
        request=generation_request(session.terminal(executor_identity=c['runtime']['identity'],draw_identity=c['draw_identity']))
        if request!=e['requests']['ON']: raise ValueError('actual resources or generator input changed')
        rows.append(dict(endpoint_identity=e['identity'],stats=memo.stats))
        if (index+1)%100==0: print('validated',index+1,flush=True)
    if seen!=set(states): raise ValueError('not all archived policy inputs covered')
    summary=dict(status='ALL_REAL_PROGRAMS_EXACTLY_PRESERVED',programs=len(rows),
        unique_public_observations=len(seen),new_G_calls=0,new_BGE_calls=0,api_cost_usd=0,natural_updates=0,
        totals={k:sum(r['stats'][k] for r in rows) for k in rows[0]['stats']},seconds=time.monotonic()-started)
    output.mkdir(parents=True,mode=0o700)
    save_json(output/'SUMMARY.json',summary);save_json(output/'REPLAYS_PRIVATE.json',rows)
    paths=[Path(__file__),source/'PACKAGE_MANIFEST.json']+[PROJECT/'src/metacom_pm/rl1'/(n+'.py') for n in ['memoized_online','online_materials','organized_policy_interface','resource_organization']]
    save_json(output/'SOURCES.json',{str(p.resolve()):file_sha(p) for p in paths})
    save_json(output/'OUTPUT_MANIFEST.json',{p.name:file_sha(p) for p in output.iterdir()})
    print(summary,flush=True)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True)
    run(parser.parse_args().output)
