#!/usr/bin/env python3
"""Build actual journal Memory resources/tasks locally, without model inference."""
import argparse
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]/'src'))
from metacom_pm.rl1v3.journal.memory_tasks import build
p=argparse.ArgumentParser()
p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
p.add_argument('--out',type=Path,required=True)
p.add_argument('--asof',type=Path,required=True)
p.add_argument('--model',type=Path,default=Path('/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3'))
a=p.parse_args()
r=build(a.root,a.out,a.asof,a.model)
print(json.dumps({k:r[k] for k in ('status','tasks','per_capability','owners','independent_owner_family_groups','multi_source_tasks','raw_resources','real_prefix_reads','requests','unique_request_materials','unreachable_base_renderer','ret_hit_any','ret_hit_all')},indent=2))
