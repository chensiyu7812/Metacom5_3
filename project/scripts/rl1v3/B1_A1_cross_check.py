"""B1 census adapter vs WS-A A1 source registry: field-by-field cross_check (CPU, no model).

Writes outputs/pm_rl1/v3/B1/A1_cross_check_<source8>/{cross_check.json,manifest.json} (write-once).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.io import build_manifest, write_json_once  # noqa: E402
from metacom_pm.rl1v3.needs.sources import ADAPTER_PROVENANCE, CensusSources, cross_check_full  # noqa: E402
from metacom_pm.rl1v3.sources import source_registry  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--b1-config", default=str(PROJECT / "configs/rl1v3/B1.yaml"))
    ap.add_argument("--b5-config", default=str(PROJECT / "configs/rl1v3/B5_real_replay_v2.yaml"))
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    b1, b5 = yaml.safe_load(Path(args.b1_config).read_text()), yaml.safe_load(Path(args.b5_config).read_text())
    t0 = time.time()
    reg = source_registry.load(REPO / b5["registry_dir"])
    if reg.version != b5["expected_source"]:
        raise SystemExit(f"registry {reg.version} != {b5['expected_source']}")
    adapter = CensusSources(PROJECT / b1["source_artifact"])
    rows = [json.loads(x) for x in (PROJECT / b1["census"]).read_text().splitlines()]
    res = cross_check_full(adapter, reg, rows)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO, capture_output=True, text=True).stdout.strip()
    out = dict(protocol="pmrl1v3-b1-a1-cross-check-v1", source_version=reg.version, adapter=ADAPTER_PROVENANCE,
               adapter_artifact_sha256=adapter.artifact_sha256, code_head=head, **res,
               content_mismatches_sample=res["content_mismatches"][:50],
               prefix_mismatches_sample=res["prefix_mismatches"][:50],
               decision=("B1 switches to A1 sources (needs.sources.a1_context); B0/B1 frames unchanged"
                         if res["zero_content_difference"] else "B1 keeps adapter; mismatches must be resolved"),
               wall_seconds=round(time.time() - t0, 1), model_calls=0, evidence_tier="engineering_only")
    for k in ("content_mismatches", "prefix_mismatches"):
        out[k] = len(out[k])
    d = Path(args.out) if args.out else PROJECT / "outputs/pm_rl1/v3/B1" / f"A1_cross_check_{reg.version.split(':')[1][:8]}"
    write_json_once(d / "cross_check.json", out)
    if not args.out:
        man = build_manifest(task="B1_A1_cross_check", root=PROJECT,
                             inputs={"census": PROJECT / b1["census"], "artifact": PROJECT / b1["source_artifact"],
                                     "registry": REPO / b5["registry_dir"] / "registry.json",
                                     "sources": REPO / b5["registry_dir"] / "sources.jsonl"},
                             outputs=[d / "cross_check.json"],
                             code=[PROJECT / "scripts/rl1v3/B1_A1_cross_check.py",
                                   PROJECT / "src/metacom_pm/rl1v3/needs/sources.py"], code_sha=head)
        write_json_once(d / "manifest.json", dict(man, model_calls=0, gpu_used=False))
    print(json.dumps(out, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
