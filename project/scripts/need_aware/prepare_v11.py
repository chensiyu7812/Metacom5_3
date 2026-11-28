#!/usr/bin/env python3
"""CPU-only fixed allocation or materialization, never model execution."""
import argparse
import json
import os
from metacom_pm.need_aware.data.v11 import allocate, materialize

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode',choices=['allocate','materialize'])
    for name in ('source','old','out'):
        p.add_argument('--'+name,required=True)
    p.add_argument('--scored');p.add_argument('--allocation')
    a=p.parse_args();os.umask(0o077)
    if a.mode=='allocate':
        if not a.scored:p.error('--scored required')
        r=allocate(a.source,a.old,a.scored,a.out)
        print(json.dumps(dict(wp3=len(r['wp3_rows']),reserved_wp4=len(r['wp4_reserved_owners']),reserved_future=len(r['future_reserved_owners']),
                             train_split={k:len(v) for k,v in r['training_owners'].items()},review={k:v for k,v in r['review'].items() if isinstance(v,int)}),indent=2))
    else:
        if not a.allocation:p.error('--allocation required')
        print(json.dumps(materialize(a.source,a.old,a.allocation,a.out),indent=2))
