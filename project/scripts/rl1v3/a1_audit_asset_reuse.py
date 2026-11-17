#!/usr/bin/env python3
"""Read/hash prior assets, validate source spans and family overlap; never run a model."""
import argparse
from pathlib import Path
from metacom_pm.rl1v3.sources.asset_reuse import audit, export_audit, read_json
from metacom_pm.rl1v3.io import canonical_json


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--history-root',type=Path,required=True)
    p.add_argument('--config',type=Path,default=Path('project/configs/rl1v3/asset_reuse_v1.json'))
    p.add_argument('--out',type=Path,required=True)
    p.add_argument('--extra-file',type=Path,action='append',default=[])
    args=p.parse_args()
    result=audit(root=args.root.resolve(),history_root=args.history_root.resolve(),config=read_json(args.config),extra_files=args.extra_file)
    manifest=export_audit(result,args.out)
    print(canonical_json(manifest['overview']))


if __name__=='__main__':main()
