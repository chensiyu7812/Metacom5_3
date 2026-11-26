#!/usr/bin/env python3
"""CPU preparation only. Every output is a proposal, not an approval."""
import argparse
import json
from metacom_pm.rl1v3.journal.pomdp_dynamic_packages import prepare

p = argparse.ArgumentParser()
for key in ('repo', 'prior', 'bundle', 'cpu', 'original-plan', 'constrained-plan', 'asset-manifest', 'out'):
    p.add_argument('--' + key, required=True)
print(json.dumps(prepare(**vars(p.parse_args())), indent=2))
