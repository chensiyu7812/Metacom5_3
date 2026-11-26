#!/usr/bin/env python3
"""Read-only CPU collection of frozen DR1–DR4 journals; no model invocation."""
import argparse,json
from metacom_pm.rl1v3.journal.pomdp_dynamic_results import collect

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--catalog',dest='catalog_path',required=True)
    parser.add_argument('--runs-root',required=True)
    parser.add_argument('--out',required=True)
    print(json.dumps(collect(**vars(parser.parse_args())),ensure_ascii=False,indent=2))
