"""CPU joint check against B S3 interfaces. Run in a combined, isolated checkout.

No checklist/response fixture is registered. B's ledger must reject registration
before a real checklist is frozen; all real terminal outcomes remain missing.
"""
import argparse
from collections import Counter
import json
from pathlib import Path
import subprocess
import sys
import tempfile
ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT/'project/src'))
from metacom_pm.rl1v3 import contracts as K
from metacom_pm.rl1v3.bank.v0_port import make_port_factory as old_factory
from metacom_pm.rl1v3.generator.g0e_port import make_port_factory
from metacom_pm.rl1v3.generator.replay_binding import rebuild_from_replay
from metacom_pm.rl1v3.io import canonical_json, file_sha256, object_sha256, write_json_once, write_jsonl_once


def run(out):
    # Imports deliberately confined to this acceptance script, never the G runtime.
    from metacom_pm.rl1v3.checklist.ledger import ChecklistLedger, ChecklistOrderError
    from metacom_pm.rl1v3.evaluate import terminal_registry as TR
    from metacom_pm.rl1v3.train import real_instances as RI
    from metacom_pm.rl1v3.env import finite_head as E
    from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity
    import yaml
    base = ROOT/'project/outputs/pm_rl1/v3'
    cfg = yaml.safe_load((ROOT/'project/configs/rl1v3/B6e_preflight_plan_v3.yaml').read_text())
    sel = json.loads((base/'B6e_plan/v3/SELECTION.json').read_text())
    reports = {r['prefix_id']:r for r in map(json.loads,(ROOT/'project'/cfg['selection']['replay']).read_text().splitlines())}
    cov = {r['prefix_id']:r for r in map(json.loads,(ROOT/'project'/cfg['selection']['coverage_sample']).read_text().splitlines())}
    f = make_port_factory(root=ROOT); old = old_factory(root=ROOT)
    mappings=[]; orders=[]; summaries=[]; requests=[]
    with tempfile.TemporaryDirectory(prefix='g0e-empty-ledger-') as tmp:
        for pid in sel['selected_ids']:
            prefix=f.prefix(cov[pid]); port=f.for_prefix(prefix); op=old.for_prefix(prefix)
            binding=TR.ReplayBinding.from_report(reports[pid]); ident=TerminalIdentity(**port.identity)
            reg=TR.TerminalRegistry(identity=ident,ledger=ChecklistLedger(Path(tmp)/pid),table_tag='unrun-G0e-binding')
            reg.bind_prefix(prefix,binding); table,report=reg.table(pid)
            inst=RI.RealInstance(pid,lambda p=prefix:f.for_prefix(p),ident,table,report,binding.reachable)
            env=RI.make_env(inst); keys={}; seen_masks=set(); norders=0
            # The latest B RealInstance drives all actual reads, masks and token bookkeeping.
            def visit(state):
                nonlocal norders
                packet=port.request_packet(env.readings(state)); mask=state.mask
                assert packet.key==env.terminal_key(state) and packet.trace==env.execution_trace(state)
                assert state.input_tokens==packet.token_ledger['billed_input_tokens']
                assert keys.setdefault(mask,(packet.key.sha256,packet.request_sha256))==(packet.key.sha256,packet.request_sha256)
                assert isinstance(port.replay(packet.key),K.ExecutionTrace)
                try:env.step(state,E.STOP)
                except E.PendingTerminal:pass
                else:raise AssertionError('STOP must remain pending')
                payload=packet.payload()
                assert set(payload)=={'messages','input_ids','decode'}
                assert all(set(m)=={'role','content'} for m in payload['messages'])
                assert packet.token_ledger['total_context_bound']<=port.effective_context_tokens
                if mask not in seen_masks:
                    old_results=[]
                    for h in E.heads_of(mask):
                        r=op.read(h,acquired=tuple(r.reading for r in old_results))
                        assert isinstance(r,K.ReadSuccess);old_results.append(r)
                    old_key=op.terminal_key(old_results)
                    assert old_key.sha256==binding.key_by_subset[TR.subset_name(mask)]
                    rebuilt,mapping=rebuild_from_replay(op,port,old_key)
                    assert rebuilt.request_sha256==packet.request_sha256
                    assert binding.replay_key_sha(prefix,packet.key)==old_key.sha256
                    # This reaches B's checklist gate after its key/trace/identity checks.
                    try:reg.register(pid,packet.key,packet.trace,'0'*64)
                    except ChecklistOrderError:pass
                    else:raise AssertionError('unfrozen checklist accepted a candidate')
                    # The sentinel is never persisted or treated as a response.
                    record_ids=[r for group in packet.key.acquired for r in group]
                    private=[pid,*record_ids]
                    for rid in record_ids:
                        private.extend(s.source_key for s in f.bank.by_id[rid].source_refs)
                    text=canonical_json(payload)
                    assert not any(i in text for i in private)
                    mappings.append(dict(mapping,prefix_id=pid,subset=TR.subset_name(mask),
                        old_key=json.loads(canonical_json(old_key)),new_key=json.loads(canonical_json(packet.key)),
                        new_trace=json.loads(canonical_json(rebuilt.trace)),token_ledger=packet.token_ledger))
                    requests.append(dict(prefix_id=pid,owner_id=prefix.owner_id,subset=TR.subset_name(mask),
                        request_id=packet.request_sha256,**payload,max_new_tokens=320,context_limit=port.effective_context_tokens,
                        input_tokens=len(packet.input_ids),terminal_key_sha256=packet.key.sha256))
                    seen_masks.add(mask)
                orders.append(dict(prefix_id=pid,subset=TR.subset_name(mask),key_sha256=packet.key.sha256,
                    request_sha256=packet.request_sha256,trace_sha256=packet.trace.sha256,order=packet.trace.ordered_path))
                norders+=1
                for action in env.legal_actions(state):
                    if action!=E.STOP:visit(env.step(state,action)[0])
            visit(env.reset())
            assert seen_masks==set(binding.reachable)
            for method in (RI.oracle_dp,RI.feasible_subsets):
                try:method(inst)
                except RI.IncompleteTable:pass
                else:raise AssertionError('partial table accepted')
            _,after=reg.table(pid)
            assert after['registered']==after['computed']==0 and not after['complete']
            summaries.append(dict(prefix_id=pid,owner_id=prefix.owner_id,fold=cov[pid]['fold'],
                subsets=len(keys),orders=norders,registry=after))
            print(pid[:12],len(keys),norders,flush=True)
    assert len(summaries)==8 and len(mappings)==120 and len(orders)==471
    write_jsonl_once(out/'KEY_BINDINGS.jsonl',mappings)
    write_jsonl_once(out/'ORDER_CHECKS.jsonl',orders)
    write_jsonl_once(out/'CPU_REQUESTS_ONLY.jsonl',requests)
    files=['project/src/metacom_pm/rl1v3/'+p for p in ('evaluate/terminal_registry.py','train/real_instances.py','env/c0_binding.py','checklist/ledger.py')]
    files+=['project/outputs/pm_rl1/v3/B6e_plan/v3/'+p for p in ('PLAN_V3_FROZEN.json','SELECTION.json')]
    write_json_once(out/'SUMMARY.json',dict(protocol='pmrl1v3-g0e-joint-binding-1',prefixes=summaries,
        terminals=120,orders=471,distribution=dict(Counter(str(r['subsets']) for r in summaries)),
        source_version=f.registry.version,identity=port.identity,binding_sha256=f.binding.sha256,
        b_interfaces={p:file_sha256(ROOT/p) for p in files},selection_sha256=sel['selection_sha256'],
        actual_checkout=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        all_stop_pending=True,model_calls=0,checklists_created=0,candidates_registered=0,
        existing_freeze_modified=False,weight_loads=0))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out',type=Path,required=True);run(p.parse_args().out)
