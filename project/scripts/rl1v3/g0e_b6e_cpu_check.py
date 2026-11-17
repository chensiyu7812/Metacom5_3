"""Use B's unchanged C0 finite environment with real G0e packets; CPU only."""
import argparse
from collections import Counter
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT/'project/src'))
from metacom_pm.rl1v3.generator.g0e_port import make_port_factory
from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv,TerminalIdentity,TerminalTable
from metacom_pm.rl1v3.env.finite_head import PendingTerminal
from metacom_pm.rl1v3.io import write_json_once,write_jsonl_once


def run(out):
    f=make_port_factory(root=ROOT);reports=[]
    cov=[json.loads(x) for x in (ROOT/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl').read_text().splitlines()]
    for row in cov:
        # Dev-only construction; keep held-out fold 6 outside new G0e examples.
        if row['fold']>5:continue
        p=f.prefix(row);port=f.for_prefix(p)
        env=C0FiniteHeadEnv(prefix=p,history_sessions=p.cutoff_rank,availability=port.availability(),
            read=port.read,identity=TerminalIdentity(**port.identity),table=TerminalTable({},table_id='G0e-unrun-pending'),
            prefix_tokens=port.base_tokens,token_capacity=port.effective_context_tokens-320,
            read_takes_acquired=True,dynamic_mask=port.action_mask)
        keys={};orders=[]
        def visit(state):
            packet=port.request_packet(env.readings(state))
            assert env.terminal_key(state)==packet.key and env.execution_trace(state)==packet.trace
            assert state.input_tokens==packet.token_ledger['billed_input_tokens']
            try:env.step(state,'STOP')
            except PendingTerminal:pass
            else:raise AssertionError('unrun STOP was not pending')
            assert keys.setdefault(packet.key.sha256,packet.request_sha256)==packet.request_sha256
            orders.append(dict(key=packet.key.sha256,trace=packet.trace.sha256,input_tokens=len(packet.input_ids)))
            for action in env.legal_actions(state):
                if action!='STOP':visit(env.step(state,action)[0])
        visit(env.reset());reports.append(dict(prefix_id=p.prefix_id,fold=row['fold'],keys=keys,orders=orders,
            subsets=len(keys),order_count=len(orders),all_stop_pending=True))
        print(p.prefix_id[:12],len(keys),len(orders),flush=True)
    write_jsonl_once(out/'B_ENV_REQUEST_REPLAY.jsonl',reports)
    write_json_once(out/'B_ENV_SUMMARY.json',dict(prefixes=len(reports),passed=len(reports),
        reachable_distribution=dict(Counter(str(r['subsets']) for r in reports)),
        terminals=sum(r['subsets'] for r in reports),orders=sum(r['order_count'] for r in reports),
        all_stop_pending=True,gpu_used=False,model_calls=0,identity=f.binding.identity,
        source_version=f.registry.version,bank_version=f.bank.version,index_version=f.bank.index_version,
        input_tokens_range=[min(o['input_tokens'] for r in reports for o in r['orders']),max(o['input_tokens'] for r in reports for o in r['orders'])],
        qualification='engineering_only; no new B6e experiment sampling'))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
