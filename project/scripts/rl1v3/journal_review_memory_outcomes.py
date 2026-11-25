#!/usr/bin/env python3
"""CPU-only private review integrity and explicit blind-freeze/key-join stages."""
import argparse
import json
from metacom_pm.rl1v3.journal.memory_outcome_review import freeze, join_key


def main():
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers(dest="command", required=True)
    blind = sub.add_parser("freeze-blind")
    for arg in ("blind", "audit", "manual", "raw", "output"):
        blind.add_argument("--" + arg, required=True)
    join = sub.add_parser("join-key")
    join.add_argument("--output", required=True)
    join.add_argument("--key", required=True)
    args = parser.parse_args()
    if args.command == "freeze-blind":
        result = freeze(args.blind, args.audit, args.manual, args.raw, args.output)
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        result = join_key(args.output, args.key)
        print(json.dumps({k: v for k, v in result.items() if k != "table"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
