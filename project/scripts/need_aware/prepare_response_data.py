#!/usr/bin/env python3
"""CPU-only official response preparation; see response_data for the source boundary."""
import argparse
import json
from pathlib import Path
from metacom_pm.need_aware.data.response_data import review_packets,build,materialize_official_candidates,freeze_development

if __name__ == '__main__':
    p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--training',required=True)
    p.add_argument('--allocation',required=True);p.add_argument('--out',required=True)
    p.add_argument('--supply');p.add_argument('--annotation',action='append',default=[])
    a=p.parse_args()
    allocation=json.loads(Path(a.allocation).read_text())
    if a.supply:
        print(json.dumps(build(a.source,a.training,allocation,a.supply,a.out,a.annotation)))
    else:
        rows=review_packets(a.source,a.training,allocation,a.out)
        source=materialize_official_candidates(a.source,a.training,allocation,a.out)
        dev=freeze_development(a.source,a.training,allocation,a.out)
        print(json.dumps({'packets':len(rows),'official_source':source,'development':dev}))
