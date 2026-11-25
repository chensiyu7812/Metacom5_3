#!/usr/bin/env python3
"""Separate retrieval-only run and post-freeze source-group evaluation."""
import argparse
import json
from metacom_pm.rl1v3.journal.temporal_retrieval import run, evaluate

def main():
    p=argparse.ArgumentParser();sub=p.add_subparsers(dest="command",required=True)
    r=sub.add_parser("retrieve")
    for name in ("memory","model","native-model","assets","output"):r.add_argument("--"+name,required=True)
    e=sub.add_parser("evaluate");e.add_argument("--output",required=True);e.add_argument("--audit",required=True)
    a=p.parse_args()
    result=run(a.memory,a.model,a.native_model,a.assets,a.output) if a.command=="retrieve" else evaluate(a.output,a.audit)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=="__main__":main()
