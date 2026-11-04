#!/usr/bin/env python3
"""Real-data negative control using exact ON/OFF scoring-input equality.

Selected AFTER inspecting equality. This can test avoidance of known useless
reads, not resource benefit, context heterogeneity or generalization.
"""
import argparse
import importlib.util
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.calibration_workflow import stamp
from metacom_pm.rl1.supervised_learning import save_json,file_sha
from metacom_pm.rl1.schema import digest

spec=importlib.util.spec_from_file_location('bounded_diagnostic',Path(__file__).with_name('159_bounded_real_diagnostic.py'))
base=importlib.util.module_from_spec(spec);spec.loader.exec_module(base)
base.SCOPE='REAL_DATA_EXACT_REPLY_COST_CONTROL'


def prepare(out):
    if out.exists():raise ValueError('new control directory required')
    menu=base.read(base.BASE/'organized_initial_training_20261103_v2/MENU_PRIVATE.json')
    proof=base.read(base.BASE/'actual_training_feedback_20261103_v1/ENDPOINTS_PRIVATE.json')
    equal={p['endpoint_identity']:p for p in proof if p['ON']==p['OFF']}
    candidates=[e for e in menu['endpoints'] if e['identity'] in equal]
    pids={e['prefix_identity'] for e in candidates if e['actions']!=[0]}
    selected=[];excluded=[]
    for e in candidates:
        if e['prefix_identity'] not in pids:continue
        # Every selectable intermediate state must itself have a known STOP
        # reward. Do not fill unmeasured/mismatching intermediate replies.
        paths={tuple(x['actions']) for x in candidates if x['prefix_identity']==e['prefix_identity']}
        if all(tuple(e['actions'][:i]+[0]) in paths for i in range(len(e['actions']))):selected.append(e)
        else:excluded.append(e['identity'])
    source=out.with_name(out.name+'_inputs');source.mkdir(parents=True,mode=0o700)
    save_json(source/'ENDPOINTS_PRIVATE.json',selected)
    save_json(source/'PROTOCOL.json',stamp(dict(scope=base.SCOPE,selection='all exact canonical ON/OFF matches with prefix-closed STOP support',
        selected_after_outcome_inspection=True,endpoints=digest(selected),excluded_nonclosed=excluded,
        quality_gain_basis='same complete evidence and exact reply; no absolute q/m inferred',
        no_claim_of_resource_benefit_or_generalization=True,source_menu_identity=menu['identity'])))
    save_json(source/'EQUALITY_PROOF_PRIVATE.json',{e['identity']:equal[e['identity']] for e in selected})
    base.FEEDBACK=source;base.prepare(out)
    original=base.read(out/'PROTOCOL.json')
    body={k:v for k,v in original.items() if k!='identity'}
    body.update(scope=base.SCOPE,feedback_utility='exact canonical input equality implies delta utility zero; absolute quality unknown',
        selection_after_outcome_inspection=True,comparison_goal='BC/PPO learn to avoid certified useless reads; no heterogeneous positive cases',
        baseline_methods=['fixed OFF','uniform random over allowed actions','BC','PPO'],
        control_script_sha256=file_sha(Path(__file__)))
    save_json(out/'DIAGNOSTIC_PROTOCOL.json',stamp(body))
    print(dict(prefixes=len(pids),endpoints=len(selected),excluded_nonclosed=len(excluded)))


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('mode',choices=['prepare','states','run']);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();base.FEEDBACK=a.output.with_name(a.output.name+'_inputs')
    if a.mode=='prepare':prepare(a.output)
    elif a.mode=='states':base.states(a.output)
    else:base.run(a.output,exact=base.read(base.FEEDBACK/'EQUALITY_PROOF_PRIVATE.json'))
