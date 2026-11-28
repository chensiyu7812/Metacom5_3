#!/usr/bin/env python3
import argparse
import json
from metacom_pm.need_aware.data.prefeval import prepare_prefeval

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--repo',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    r=prepare_prefeval(a.repo,a.output);print(json.dumps({k:v for k,v in r.items() if k!='source_files'},indent=2))
