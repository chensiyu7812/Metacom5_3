"""Hash only fixed integration inputs; never scan model weights or rebuild outputs."""
import json,hashlib,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);out=Path(sys.argv[2]);head=sys.argv[3]
assert subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip()==head
files={}
def add(p):
 path=root/p
 h=hashlib.sha256()
 with path.open('rb') as stream:
  for block in iter(lambda:stream.read(1024*1024),b''):h.update(block)
 files[str(p)]=dict(bytes=path.stat().st_size,sha256=h.hexdigest())
for d in ('project/outputs/pm_rl1/v3/A1_preparation/final/registry','project/outputs/pm_rl1/v3/A1b_preparation/measured_v1/bank','project/outputs/pm_rl1/v3/B0'):
 for path in (root/d).iterdir():
  if path.is_file():add(path.relative_to(root))
for p in ('project/outputs/pm_rl1/v3/B1/coverage_sample_v1.jsonl','project/outputs/pm_rl1/v3/A1b_crossline_20261118/RS_V0_STRATEGY_CATALOG.json','project/outputs/pm_rl1/v3/A1_reuse/ASSET_REUSE_MANIFEST.json','project/outputs/pm_rl1/v3/integration_c0_freeze_20261117/C0_FREEZE_MANIFEST.json','.github/workflows/pm-v2-tests.yml','project/pyproject.toml'):
 add(Path(p))
for pattern in ('project/configs/rl1v3/*','project/scripts/rl1v3/*.py','project/tests/test_rl1v3_*.py','project/src/metacom_pm/rl1v3/**/*.py','project/schemas/rl1v3/*.json'):
 for p in root.glob(pattern):
  if p.is_file():add(p.relative_to(root))
manifest=dict(protocol='pmrl1v3-integration-s2-inputs-v1',code_sha=head,files=files,model_weights_rehashed=False)
with out.open('x') as f:json.dump(manifest,f,ensure_ascii=False,indent=2);f.write('\n')
print(len(files),'inputs/code files pinned')
