"""Read-only interface/source audit; writes only this sync's evidence JSON."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[5]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'project/src'))

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def git(*args, root=ROOT):
    return subprocess.check_output(['git', *args], cwd=root, text=True).strip()

parser = argparse.ArgumentParser()
parser.add_argument('--a-preparation', type=Path, required=True)
args = parser.parse_args()
a = args.a_preparation.resolve()
assert git('rev-parse', 'HEAD', root=a) == '01a951143c740697736f396ff449b70e6c909a04'
freeze_path = ROOT / 'project/outputs/pm_rl1/v3/integration_c0_freeze_20261117/C0_FREEZE_MANIFEST.json'
freeze = json.loads(freeze_path.read_text())
checks = [{**r, 'matches': sha(ROOT/r['path']) == r['sha256']} for r in freeze['shared_files']]
assert all(r['matches'] for r in checks)
formal = freeze['b_formal_acceptance']
assert sha(ROOT / formal['path']) == formal['sha256']
protected = ['project/src/metacom_pm/rl1v3/contracts.py', 'project/src/metacom_pm/rl1v3/io.py',
             'project/schemas/rl1v3', 'project/src/metacom_pm/rl1v3/prefixes',
             'project/outputs/pm_rl1/v3/B0', formal['path'],
             'project/docs/plans/pm_rl1_v3_20261116/EXECUTION_STATE.json']
assert not git('diff', '--name-only', 'd67f34ee35f3f69ee82e5973e4b31b6415a302d0', 'HEAD', '--', *protected)
b0dir = ROOT/'project/outputs/pm_rl1/v3/B0'
b0 = json.loads((b0dir/'manifest.json').read_text())
assert all(sha(b0dir/name) == row['sha256'] for name,row in b0['outputs'].items())

# Import the pinned A modules without merging or writing their files.
import metacom_pm.rl1v3 as package
import metacom_pm.rl1v3.sources as source_package
package.__path__.append(str(a/'project/src/metacom_pm/rl1v3'))
source_package.__path__.append(str(a/'project/src/metacom_pm/rl1v3/sources'))
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.needs.sources import CensusSources, cross_check
from metacom_pm.rl1v3.bank import bank_v0
from metacom_pm.rl1v3.retrieve import search
registry = S.load(a/'project/outputs/pm_rl1/v3/A1_preparation/final/registry')
bank = bank_v0.load(a/'project/outputs/pm_rl1/v3/A1b_preparation/measured_v1/bank', registry)
adapter = CensusSources(ROOT/'project/data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json')
personal = [e.source for e in registry.entries if e.availability_scope == 'personal_history']
issues = cross_check(adapter, personal)
assert not issues
rows = [json.loads(x) for x in (b0dir/'prefix_census.jsonl').read_text().splitlines()]
row_by_id = {r['prefix_id']:r for r in rows}
mismatches = []
for row in rows:
    ctx = adapter.context(row)
    pa = registry.prefix(row['owner_id'], row['session_id'], row['cut_turn'])
    if (pa.prefix_id, pa.runtime_sha256) != (ctx.prefix.prefix_id, ctx.prefix.runtime_sha256):
        mismatches.append(row['prefix_id'])
assert not mismatches
coverage = [json.loads(x) for x in (ROOT/'project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl').read_text().splitlines()]
ready_boundary = []
for sample in coverage:
    ctx = adapter.context(row_by_id[sample['prefix_id']])
    for head in ('MP', 'ME', 'MS'):
        result = search(bank, head, ctx.prefix)
        if not result.ranked:
            continue
        rec = bank.by_id[result.ranked[0].record_id]
        if rec.ready_at and rec.ready_at.session_rank == ctx.prefix.cutoff_rank:
            ready_boundary.append(dict(prefix_id=ctx.prefix.prefix_id, head=head, record_id=rec.record_id,
                                       cutoff_rank=ctx.prefix.cutoff_rank, ready_at=rec.ready_at.session_rank))
result = dict(protocol='pmrl1v3-wsb-frozen-sync-interface-check-v1',
    tested_sha=git('rev-parse','HEAD'), frozen_integration_sha='d67f34ee35f3f69ee82e5973e4b31b6415a302d0',
    a_preparation_sha=git('rev-parse','HEAD',root=a),
    shared_identity_sha256=freeze['shared_identity_sha256'], shared_files=checks,
    formal_b_acceptance=formal, b0_output_count=len(b0['outputs']),
    personal_sources=len(personal), all_registry_sources=len(registry.entries),
    source_cross_check_issues=issues, prefixes=len(rows), prefix_identity_mismatches=mismatches,
    real_bank_replay_executed=False, ready_boundary_selected_in_coverage=ready_boundary,
    note='A source/bank read-only audit only; B real-bank runner has not executed; no generated labels or outcomes')
(OUT/'INTERFACE_CHECKS.json').write_text(json.dumps(result, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({k:result[k] for k in ('tested_sha','personal_sources','prefixes','source_cross_check_issues','prefix_identity_mismatches')}))
print('ready_at equality cases among 24 coverage top-ranked personal reads:',len(ready_boundary))
