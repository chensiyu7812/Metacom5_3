#!/usr/bin/env python3
"""Join actual dynamic endpoints with separately bound development reviews."""
import argparse
import json
from metacom_pm.rl1v3.journal.pomdp_dynamic_analysis import analyze

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--collection', required=True)
    p.add_argument('--reviews', required=True)
    p.add_argument('--out', required=True)
    args = p.parse_args()
    print(json.dumps(analyze(args.collection, args.reviews, args.out), indent=2))
