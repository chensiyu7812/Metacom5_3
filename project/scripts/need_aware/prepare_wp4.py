#!/usr/bin/env python3
import argparse
import json
from metacom_pm.need_aware.data.training_v11 import build

if __name__=='__main__':
    p=argparse.ArgumentParser(description='CPU source-grounded WP4 candidate construction; no training')
    for name in ('old','source','allocation','prefeval','prefeval-exposed','out'):p.add_argument('--'+name,required=True)
    a=vars(p.parse_args());print(json.dumps(build(**a),indent=2))
