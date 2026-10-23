#!/usr/bin/env python3
"""Offline replay of the original learning handoff after Claude was deferred.

No key/account/network/model/optimizer access. Writes only new artifacts; old
snapshots and failed calls are immutable, including the ledger's old prefix.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

PROJECT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(PROJECT/'src'))
from metacom_pm.rl1.learning_preparation import TerminalCandidate
from metacom_pm.rl1.learning_handoff import candidate_menu, prepare_handoff
from metacom_pm.rl1.schema import digest


def read(path):
    return json.loads(path.read_text())


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(out):
    prepared=PROJECT/'outputs/pm_rl1/completion_preparation_20261022'
    pilot=PROJECT/'outputs/pm_rl1/claude_pilot_20261022_v1'
    protocol=read(pilot/'protocol.json')
    closed=read(pilot/'live/CLOSED.json')
    pause=read(pilot/'USER_DEFERRED.json')
    if pause['claude_execution_enabled'] or pause['reason']!='USER_DEFERRED_FRIEND_ACCOUNT':
        raise ValueError('expected deferred Claude scope')
    sources=read(prepared/'SOURCE_HASHES_PRIVATE.json')
    ledger=Path(protocol['ledger']['path'])
    unchanged=0
    for name,expected in sources.items():
        if Path(name)==ledger:
            actual=hashlib.sha256(ledger.read_bytes()[:protocol['ledger']['bytes']]).hexdigest()
        else:
            actual=sha(Path(name))
        if actual!=expected:
            raise ValueError('historical source drift: '+name)
        unchanged+=1
    for name,expected in protocol['immutable_files'].items():
        if sha(Path(name))!=expected:
            raise ValueError('pilot frozen input/code drift: '+name)
    for seal in (pilot/'live').glob('*.seal.json'):
        for name,expected in read(seal).items():
            if Path(name).name!=name or sha(seal.parent/name)!=expected:
                raise ValueError('pilot attempt seal drift')
    additions=[json.loads(s) for s in ledger.read_bytes()[protocol['ledger']['bytes']:].decode().splitlines()]
    if (len(additions)!=2 or [e['event'] for e in additions]!=['RESERVED','SETTLED']
            or additions[0]['reservation_id']!=additions[1]['reservation_id']
            or closed['attempts']!=1 or closed['stage_cost_or_liability_usd']!='0'
            or closed['unsettled_reservations']!=0):
        raise ValueError('pilot accounting differs; reconcile instead of claiming zero')
    data=read(prepared/'bc_terminal_candidates_private.json')
    candidates=[TerminalCandidate(**(r|dict(counts=tuple(r['counts'])))) for r in data]
    menu=candidate_menu(candidates,source_identity=sha(prepared/'bc_terminal_candidates_private.json'),
        scope='initial_train')
    handoff=prepare_handoff(candidates,menu=menu,receipts={})
    if handoff['status']!='PENDING_QUALIFICATION' or handoff['targets']:
        raise ValueError('unqualified real pool cannot produce targets')
    report=dict(status='OFFLINE_HANDOFF_VERIFIED_CLAUDE_DEFERRED',
        historical_sources_verified=unchanged,ledger_old_prefix_verified=True,
        appended_events=len(additions),total_attempts=closed['cumulative_attempts'],
        new_Claude_attempts=1,new_Claude_scores=0,new_cost_usd='0',
        shared_followup_usd=closed['shared_followup_usd'],unsettled_reservations=0,
        train_candidates=len(candidates),train_prefixes=len(menu['prefix_identities']),
        handoff_status=handoff['status'],qualified_BC_targets=0,BC_checkpoints=0,natural_updates=0,
        menu_identity=menu['identity'],handoff_identity=handoff['identity'],
        verification_network_requests=0,verification_model_inference=0,
        formal_runner_complete=False,full_learning_loop_complete=False,
        source_code={str(p.relative_to(PROJECT)):sha(p) for p in
            (Path(__file__).resolve(),PROJECT/'src/metacom_pm/rl1/learning_handoff.py')})
    report['identity']=digest(report)
    out.mkdir(parents=True,exist_ok=False,mode=0o700)
    for name,value in [('menu_private.json',menu),('handoff_private.json',handoff),('SUMMARY.json',report)]:
        with (out/name).open('x') as f:json.dump(value,f,ensure_ascii=False,indent=2);f.write('\n')
        (out/name).chmod(0o600)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(__doc__)
    parser.add_argument('--out',type=Path,required=True)
    args=parser.parse_args()
    print(json.dumps(run(args.out),ensure_ascii=False))
