"""CPU-only registry preparation. Does not mark A1 completed or freeze C0."""
from pathlib import Path
import argparse
from metacom_pm.rl1v3.sources import source_registry as S
from metacom_pm.rl1v3.io import write_jsonl_once

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--root',type=Path,default=Path(__file__).resolve().parents[3])
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args();registry=S.build(args.root)
    S.save(registry,args.out)
    write_jsonl_once(args.out/'version_operations.jsonl',S.changes(None,registry))
    print(registry.version,len(registry.entries),'source entries; dependency freeze not asserted')
if __name__=='__main__':main()
