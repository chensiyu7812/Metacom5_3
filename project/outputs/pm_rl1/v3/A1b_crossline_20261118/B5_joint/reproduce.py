"""Run A's committed PrefixPort through B's unmodified v2 checker, CPU only."""
from __future__ import annotations
import argparse
from collections import Counter
import hashlib
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time
import traceback


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def git(root, *args):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()


def write(path, value):
    with path.open('x') as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write('\n')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--a-root', type=Path, required=True)
    parser.add_argument('--b-root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    a, b, out = args.a_root.resolve(), args.b_root.resolve(), args.out.resolve()
    out.mkdir(parents=True, exist_ok=False)
    expected_a = '14fd459e473cc3e98ab8b4dbddf73216e9314759'
    expected_b = 'd06715bf6893710c8b21f2c91c7cac42c0111e85'
    assert git(b, 'rev-parse', 'HEAD') == expected_b
    assert not git(b, 'status', '--porcelain=v1'), 'B validation worktree must be clean'
    files = sorted((a/'project/src/metacom_pm/rl1v3').rglob('*.py'))
    files += sorted((b/'project/src/metacom_pm/rl1v3/env').glob('*.py'))
    before = {str(path):dict(sha256=sha(path), bytes=path.stat().st_size) for path in files}
    write(out/'CODE_BEFORE.json', dict(a_head=git(a,'rev-parse','HEAD'), a_dirty=git(a,'status','--porcelain=v1'),
          b_head=expected_b, b_dirty='', a_port_commit=expected_a, files=before))
    start=time.time(); reports=[]; error=None
    try:
        sys.path.insert(0,str(a/'project/src'))
        import metacom_pm.rl1v3.env as env
        env.__path__[:] = [str(b/'project/src/metacom_pm/rl1v3/env')]
        from metacom_pm.rl1v3.env.bank_replay_v2 import replay_prefix, REPLAY_PROTOCOL
        from metacom_pm.rl1v3.bank.v0_port import make_port_factory, PrefixPort, CONFIG
        from metacom_pm.rl1v3 import contracts as K
        assert Path(sys.modules[replay_prefix.__module__].__file__).is_relative_to(b)
        first = make_port_factory(root=a)
        second = make_port_factory(root=a)
        assert first.bank is not second.bank and first.tokenizer is not second.tokenizer
        assert first.bank.version == second.bank.version
        coverage = b/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl'
        rows = [json.loads(line) for line in coverage.read_text().splitlines()]
        assert len(rows)==24 and len({r['prefix_id'] for r in rows})==24
        cfg=json.loads((a/CONFIG).read_text())
        input_files=[a/CONFIG,coverage,a/cfg['asset_manifest']]
        input_files += [a/cfg['registry_dir']/name for name in ('registry.json','sources.jsonl')]
        input_files += [a/cfg['bank_dir']/name for name in ('bank.json','records.jsonl','index.json')]
        input_files += [Path(cfg['tokenizer_model'])/name for name in ('tokenizer.json','tokenizer_config.json','chat_template.jinja','config.json')]
        write(out/'INPUT_FILES_SHA256.json',[dict(path=str(p),sha256=sha(p),bytes=p.stat().st_size) for p in input_files])
        for row in rows:
            prefix=first.prefix(row); prefix2=second.prefix(row)
            port=first(prefix)
            units=[]
            for head in K.HEAD_ORDER:
                result=port.read(head, acquired=())
                if isinstance(result,K.ReadSuccess):
                    units.append(result.input_tokens_after-result.input_tokens_before)
            assert units
            capacity=port.base_tokens+int(statistics.median(units))
            identity=dict(first.identity,output_reserve_tokens=port.native_context_tokens-capacity)
            report=replay_prefix(lambda p=prefix:first(p), fresh_factory=lambda p=prefix2:second(p),
                stress_factory=lambda p=prefix,ident=identity:PrefixPort(first.bank,p,first.tokenizer,**ident),
                meta=dict(rank_bucket=row['rank_bucket'],slot=row.get('selection_reason'),uses=row['uses']))
            reports.append(report)
            with (out/'replay_reports.jsonl').open('a') as stream:
                stream.write(json.dumps(report,ensure_ascii=False,sort_keys=True)+'\n')
            print(f"{len(reports)}/24 {row['prefix_id'][:12]} reachable={report['n_reachable']} passed={report['passed']}",flush=True)
        summary=dict(protocol=REPLAY_PROTOCOL,status='joint_committed_code_pre_integration_rehearsal',
            a_port_commit=expected_a,b_commit=expected_b,source_version=first.registry.version,
            bank_version=first.bank.version,index_version=first.bank.index_version,
            tokenizer_identity=first.tokenizer.identity,prefixes=len(reports),passed=sum(r['passed'] for r in reports),
            reachable_distribution=dict(sorted(Counter(r['n_reachable'] for r in reports).items())),
            total_reachable=sum(r['n_reachable'] for r in reports),total_orders=sum(r['n_orders'] for r in reports),
            unreachable_reasons=dict(Counter(f'{h}:{why}' for r in reports for h,why in r['unreachable_heads'].items())),
            ready_at_equals_cutoff_records=sum(len(p.get('ready_at_equals_cutoff',())) for r in reports for p in r['head_probe'].values()),
            capacity_stress_passed=sum(r['capacity_stress']['passed'] for r in reports),
            rejected_read_state_tested=sum(r['capacity_stress']['rejected_read_keeps_state']['tested'] for r in reports),
            fresh_replay_identical=sum(r['replay_identical'] for r in reports),
            failures=[dict(prefix_id=r['prefix_id'],failures=r['failures']) for r in reports if r['failures']],
            model_calls=0,gpu_used=False,paid_calls=0,seconds=time.time()-start)
        write(out/'summary.json',summary)
        print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
        assert summary['passed']==24 and summary['capacity_stress_passed']==24
        assert summary['fresh_replay_identical']==24 and not summary['failures']
    except BaseException as exc:
        error=dict(type=type(exc).__name__,message=str(exc));traceback.print_exc()
    loaded=[]; changed=[]; mismatches=[]
    for module in list(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if not filename:continue
        p=Path(filename).resolve()
        if not p.is_file() or not (p.is_relative_to(a/'project/src/metacom_pm/rl1v3') or p.is_relative_to(b/'project/src/metacom_pm/rl1v3')):
            continue
        source_root,commit=(b,expected_b) if p.is_relative_to(b) else (a,expected_a)
        relative=str(p.relative_to(source_root))
        blob=subprocess.run(['git','show',commit+':'+relative],cwd=source_root,capture_output=True)
        match=blob.returncode==0 and hashlib.sha256(blob.stdout).hexdigest()==sha(p)
        row=dict(module=module.__name__,path=str(p),sha256=sha(p),expected_commit=commit,commit_blob_matches=match)
        loaded.append(row)
        if not match:mismatches.append(relative)
        if str(p) in before and before[str(p)]['sha256']!=sha(p):changed.append(relative)
    execution=dict(command=sys.argv,a_head_after=git(a,'rev-parse','HEAD'),b_head_after=git(b,'rev-parse','HEAD'),
        a_dirty_after=git(a,'status','--porcelain=v1'),b_dirty_after=git(b,'status','--porcelain=v1'),
        source_files_changed_during_run=changed,commit_blob_mismatches=mismatches,
        loaded_modules=loaded,error=error,seconds=time.time()-start,harness_sha256=sha(Path(__file__)),
        scope='read-only joint pre-integration replay; no business code copied or modified')
    write(out/'EXECUTION.json',execution)
    ok=error is None and not changed and not mismatches and not execution['b_dirty_after']
    write(out/'FILES_SHA256.json',[dict(path=str(p.relative_to(out)),sha256=sha(p),bytes=p.stat().st_size)
          for p in sorted(out.rglob('*')) if p.is_file()])
    print('JOINT_REPLAY_OK='+str(ok),flush=True)
    return 0 if ok else 1

if __name__=='__main__':
    raise SystemExit(main())
