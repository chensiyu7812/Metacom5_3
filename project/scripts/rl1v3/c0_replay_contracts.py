#!/usr/bin/env python3
"""Replay serialized C0 positive/negative fixtures without models or source data."""
import argparse
from pathlib import Path

from metacom_pm.rl1v3.contracts import CONTRACT_TYPES
from metacom_pm.rl1v3.io import canonical_json, decode_contract, parse_json, write_json_once


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--input',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    args=p.parse_args()
    classes={c.__name__:c for c in CONTRACT_TYPES}
    fixtures=parse_json(args.input.read_text())
    results=[]
    for row in fixtures:
        try:
            obj=decode_contract(classes[row['type']],canonical_json(row['value']))
        except ValueError:
            if row['expected']=='valid': raise
            results.append(dict(case=row['case'],status='rejected'))
        else:
            if row['expected']!='valid': raise ValueError('invalid fixture accepted: '+row['case'])
            results.append(dict(case=row['case'],status='accepted',sha256=obj.sha256))
    write_json_once(args.out,results)
    print(canonical_json(dict(accepted=sum(r['status']=='accepted' for r in results),rejected=sum(r['status']=='rejected' for r in results))))


if __name__=='__main__': main()
