#!/usr/bin/env python3
"""Export versioned C0 schemas; --check detects drift without rewriting."""
import argparse
import json
from pathlib import Path

from metacom_pm.rl1v3.contracts import CONTRACT_TYPES, ReadResult, json_schema


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, default=Path("project/schemas/rl1v3"))
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    for name, cls in [(c.__name__, c) for c in CONTRACT_TYPES] + [("ReadResult", ReadResult)]:
        path = args.out / f"{name}.schema.json"
        schema = json_schema(cls)
        if args.check:
            if json.loads(path.read_text()) != schema:
                raise SystemExit(f"schema drift: {path}")
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(f"{len(CONTRACT_TYPES)+1} schemas {'checked' if args.check else 'exported'}")


if __name__ == "__main__":
    main()
