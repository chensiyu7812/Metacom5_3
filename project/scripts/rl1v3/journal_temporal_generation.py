"""CPU-only explicit-date generation materialization and post-freeze evaluation."""
import argparse,json
from metacom_pm.rl1v3.journal.temporal_generation import prepare,evaluate_supply
p=argparse.ArgumentParser();sub=p.add_subparsers(dest='command',required=True)
b=sub.add_parser('prepare')
for name in ('memory','rankings','template','measurements','model','assets','output'):b.add_argument('--'+name,required=True)
e=sub.add_parser('evaluate');e.add_argument('--output',required=True);e.add_argument('--audit',required=True)
a=vars(p.parse_args());command=a.pop('command')
print(json.dumps((prepare if command=='prepare' else evaluate_supply)(**a),indent=2))
