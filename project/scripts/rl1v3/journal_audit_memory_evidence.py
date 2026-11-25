#!/usr/bin/env python3
"""Bind private source-reviewed atoms; no model calls, scoring or source inference."""
import argparse,json
from metacom_pm.rl1v3.journal.evidence_audit import build
p=argparse.ArgumentParser();p.add_argument('--root',required=True);p.add_argument('--memory',required=True);p.add_argument('--review',required=True);p.add_argument('--output',required=True)
a=p.parse_args();print(json.dumps(build(a.root,a.memory,a.review,a.output),indent=2))
