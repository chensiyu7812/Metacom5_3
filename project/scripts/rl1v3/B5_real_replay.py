"""B5 real bank-v0 replay over the fixed B1 coverage sample.

Needs a WS-A A1b port: ``--port module:factory`` where ``factory(ctx_sources) ->
callable returning a fresh BankPort`` (see env/bank_replay.py).  Until A1b is on
the branch this script writes nothing and exits 3 with the blocking reason; it
never substitutes a fixture or mock bank for real records.
"""
from __future__ import annotations

import argparse
import importlib
import json
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from metacom_pm.rl1v3.env.bank_replay import REPLAY_PROTOCOL, replay_prefix  # noqa: E402
from metacom_pm.rl1v3.env.c0_binding import TerminalIdentity  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, write_json_once, write_jsonl_once  # noqa: E402
from metacom_pm.rl1v3.needs.sources import CensusSources  # noqa: E402


def resolve_port(spec: str | None, candidates: list[str]):
    tried = []
    for target in ([spec] if spec else candidates):
        mod, _, attr = target.partition(":")
        try:
            return getattr(importlib.import_module(mod), attr), tried
        except (ImportError, AttributeError) as exc:
            tried.append(f"{target}: {type(exc).__name__}: {exc}")
    return None, tried


def failure_kind(f: str) -> str:
    """'MP:rec:foreign_owner' -> 'foreign_owner'; 'order_changed_key:...' -> 'order_changed_key'."""
    parts = f.split(":")
    return parts[2] if parts[0] in ("RS", "MP", "ME", "MS") and len(parts) > 2 else parts[0]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(ROOT / "configs/rl1v3/B5_real_replay.yaml"))
    ap.add_argument("--port", default=None)
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    factory, tried = resolve_port(args.port, cfg["port_candidates"])
    if factory is None:
        print(json.dumps(dict(status="blocked", reason="no WS-A A1b bank-v0 port importable", tried=tried), indent=1))
        sys.exit(3)
    rows = {json.loads(x)["prefix_id"]: json.loads(x) for x in (ROOT / cfg["census"]).read_text().splitlines()}
    cov = [json.loads(x) for x in (ROOT / cfg["coverage_sample"]).read_text().splitlines()]
    src = CensusSources(ROOT / cfg["source_artifact"])
    make = factory(src)
    t0, reports = time.time(), []
    for c in cov:
        ctx = src.context(rows[c["prefix_id"]])
        port = make()
        ident = TerminalIdentity(bank_version=port.bank_version, index_version=port.index_version,
                                 **cfg["terminal_identity"])
        reports.append(replay_prefix(ctx, make, ident))
    bank = reports[0]["bank_version"]
    out = ROOT / cfg["out_root"] / f"real_replay_{bank}"
    summary = dict(
        protocol=REPLAY_PROTOCOL, bank_version=bank, index_version=reports[0]["index_version"],
        prefixes=len(reports), passed=sum(r["passed"] for r in reports),
        reachable_distribution={str(k): v for k, v in sorted(Counter(r["n_reachable"] for r in reports).items())},
        unreachable_reasons=dict(Counter(f"{h}:{why}" for r in reports for h, why in r["unreachable_heads"].items())),
        failure_kinds=dict(Counter(failure_kind(f) for r in reports for f in r["failures"])),
        all_16_reachable=[r["prefix_id"] for r in reports if r["n_reachable"] == 16],
        wall_seconds=round(time.time() - t0, 2), evidence_tier="engineering_only")
    write_jsonl_once(out / "replay_reports.jsonl", reports)
    write_json_once(out / "summary.json", summary)
    code = [ROOT / p for p in ("scripts/rl1v3/B5_real_replay.py", "src/metacom_pm/rl1v3/env/bank_replay.py",
                               "src/metacom_pm/rl1v3/env/c0_binding.py", "src/metacom_pm/rl1v3/env/finite_head.py")]
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True).stdout.strip()
    man = build_manifest(task="B5_real_replay", root=ROOT,
                         inputs={k: ROOT / cfg[k] for k in ("census", "coverage_sample", "source_artifact")},
                         outputs=[out / "replay_reports.jsonl", out / "summary.json"], code=code, code_sha=head)
    write_json_once(out / "manifest.json", dict(man, port=args.port or "auto", model_calls=0, gpu_used=False))
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
