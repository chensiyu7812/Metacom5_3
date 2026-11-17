"""B5 real bank-v0 replay v2 over the fixed 24-prefix B1 coverage sample (CPU, tokenizer only).

Loads the WS-A A1 source registry and A1b bank-v0 twice (the second, independent
load from disk + a new tokenizer instance drives the determinism pass), runs
``bank_replay_v2.replay_prefix`` per prefix with the real Reader identity and a
diagnostic capacity-stress port, and writes write-once reports + manifest.
Records whether the A1/A1b formal commits are already in the integration branch
(otherwise the run is a pre-integration rehearsal and must be repeated there).
No generator, judge, GPU or paid call; no terminal reward is produced.
"""
from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
import time
from collections import Counter
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.env import a1b_port as P  # noqa: E402
from metacom_pm.rl1v3.env.bank_replay_v2 import REPLAY_PROTOCOL, replay_prefix  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, write_json_once, write_jsonl_once  # noqa: E402


def git(*args) -> str:
    return subprocess.run(["git", *args], cwd=REPO, capture_output=True, text=True).stdout.strip()


def is_ancestor(commit: str, ref: str) -> bool:
    return subprocess.run(["git", "merge-base", "--is-ancestor", commit, ref], cwd=REPO).returncode == 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PROJECT / "configs/rl1v3/B5_real_replay_v2.yaml"))
    ap.add_argument("--out", default=None, help="override output directory (dry runs)")
    ap.add_argument("--port", choices=("a", "b"), default="a",
                    help="a = WS-A bank.v0_port.PrefixPort (formal); b = WS-B thin a1b_port adapter (cross-check)")
    ap.add_argument("--compare", default=None, help="replay_reports.jsonl of another run to compare keys/reachability")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    ident = cfg["reader_identity"]

    def load():
        bank = P.load_bank(REPO, registry_dir=cfg["registry_dir"], bank_dir=cfg["bank_dir"],
                           expected_source=cfg["expected_source"], expected_bank=cfg["expected_bank"])
        if bank.index_version != cfg["expected_index"]:
            raise SystemExit(f"index {bank.index_version} != {cfg['expected_index']}")
        tok = NativeTokenizer(cfg["tokenizer"], PROJECT / cfg["asset_manifest"])
        return bank, tok

    def a_factory():
        from metacom_pm.rl1v3.bank import v0_port as AP
        acfg = json.loads((REPO / AP.CONFIG).read_text())
        for k in ("registry_dir", "bank_dir", "expected_source", "expected_bank", "expected_index"):
            if acfg[k] != cfg[k]:
                raise SystemExit(f"WS-A port config {k} differs from the B5 v2 config")
        if acfg["reader_identity"] != ident:
            raise SystemExit("WS-A port reader identity differs from the B5 v2 config")
        return AP.make_port_factory(root=REPO)

    t0 = time.time()
    if args.port == "a":
        fa, fa2 = a_factory(), a_factory()        # second: independent load from disk + new tokenizer
        bank, bank2, tok, tok2 = fa.bank, fa2.bank, fa.tokenizer, fa2.tokenizer
        port_name = "WS-A bank.v0_port.PrefixPort (pmrl1v3-a1b-read-port-v1)"
    else:
        (bank, tok), (bank2, tok2) = load(), load()
        port_name = f"WS-B {P.ADAPTER}"
    cov = [json.loads(x) for x in (PROJECT / cfg["coverage_sample"]).read_text().splitlines()]
    reports = []
    for row in cov:
        p, p2 = P.prefix_for(bank.registry, row), P.prefix_for(bank2.registry, row)

        def mk(b, pr, tk, reserve=ident["output_reserve_tokens"]):
            if args.port == "a":
                from metacom_pm.rl1v3.bank import v0_port as AP
                f = ((fa if b is bank else fa2) if reserve == ident["output_reserve_tokens"]
                     else AP.PortFactory(b, tk, dict(ident, output_reserve_tokens=reserve)))   # stress: own identity
                return lambda: f.for_prefix(pr)
            return lambda: P.A1bPort(b, pr, tk, g_id=ident["g_id"], decode_id=ident["decode_id"],
                                     step2_id=ident["step2_id"], output_reserve_tokens=reserve)
        port = mk(bank, p, tok)()
        units = []
        for h in ("RS", "MP", "ME", "MS"):
            r = port.read(h, acquired=())
            if hasattr(r, "input_tokens_after"):
                units.append(r.input_tokens_after - r.input_tokens_before)
        stress_cap = port.base_tokens + int(statistics.median(units)) if units else None
        stress = (mk(bank, p, tok, tok.native_context_tokens - stress_cap) if stress_cap else None)
        rep = replay_prefix(mk(bank, p, tok), fresh_factory=mk(bank2, p2, tok2), stress_factory=stress,
                            meta=dict(rank_bucket=row["rank_bucket"], slot=row.get("selection_reason"),
                                      uses=row["uses"]))
        reports.append(rep)
        print(f"{row['prefix_id'][:12]} fold={rep['fold']} reach={rep['n_reachable']} passed={rep['passed']}",
              flush=True)
    a = cfg["a_formal_commits"]
    integrated = all(is_ancestor(c, cfg["integration_ref"]) for c in a.values())
    boundary = sum(len(h.get("ready_at_equals_cutoff", ())) for r in reports for h in r["head_probe"].values())
    full_tok = [r["input_tokens_by_subset"].get("RS+MP+ME+MS") for r in reports]
    full_tok = [x for x in full_tok if x is not None]
    compared = None
    if args.compare:
        other = {json.loads(x)["prefix_id"]: json.loads(x) for x in Path(args.compare).read_text().splitlines()}
        same = [r["prefix_id"] for r in reports if r["prefix_id"] in other and all(
            r[k] == other[r["prefix_id"]][k] for k in ("key_by_subset", "reachable", "input_tokens_by_subset",
                                                        "availability", "unreachable_heads", "identity"))]
        compared = dict(path=str(Path(args.compare).relative_to(PROJECT)) if Path(args.compare).is_relative_to(PROJECT)
                        else args.compare, identical_prefixes=len(same), prefixes=len(reports))
    summary = dict(
        protocol=REPLAY_PROTOCOL, status="formal_on_integration" if integrated else "pre_integration_rehearsal",
        port=port_name, cross_port_comparison=compared,
        a_formal_commits=a, a_integrated=integrated, code_head=git("rev-parse", "HEAD"),
        source_version=bank.registry.version, bank_version=bank.version, index_version=bank.index_version,
        reader_identity=reports[0]["identity"], tokenizer_identity=tok.identity,
        native_context_tokens=tok.native_context_tokens, prefixes=len(reports),
        passed=sum(r["passed"] for r in reports),
        reachable_distribution={str(k): v for k, v in sorted(Counter(r["n_reachable"] for r in reports).items())},
        unreachable_reasons=dict(Counter(f"{h}:{why}" for r in reports for h, why in r["unreachable_heads"].items())),
        head_available_prefixes={h: sum(r["availability"][h] > 0 for r in reports) for h in ("RS", "MP", "ME", "MS")},
        legal_candidates_median={h: statistics.median(r["availability"][h] for r in reports) for h in ("RS", "MP", "ME", "MS")},
        root_reading_tokens_median={h: statistics.median([r["head_probe"][h]["reading_tokens"] for r in reports
                                                          if r["head_probe"][h]["status"] == "ok"] or [0])
                                    for h in ("RS", "MP", "ME", "MS")},
        base_tokens_range=[min(r["base_tokens"] for r in reports), max(r["base_tokens"] for r in reports)],
        all_heads_input_tokens_range=[min(full_tok), max(full_tok)] if full_tok else None,
        ready_at_equals_cutoff_records=boundary,
        static_mask_disagreements=sum(len(r["static_mask_disagreements"]) for r in reports),
        capacity_stress=dict(
            passed=sum(bool(r["capacity_stress"] and r["capacity_stress"]["passed"]) for r in reports),
            rejected_read_tested=sum(bool(r["capacity_stress"] and r["capacity_stress"]["rejected_read_keeps_state"]["tested"]) for r in reports),
            reachable_distribution={str(k): v for k, v in sorted(Counter(r["capacity_stress"]["n_reachable"] for r in reports if r["capacity_stress"]).items())},
            static_mask_disagreements=sum(len(r["capacity_stress"]["static_mask_disagreements"]) for r in reports if r["capacity_stress"])),
        failure_kinds=dict(Counter(f.split(":")[0] for r in reports for f in r["failures"])),
        terminal_outcomes="all pending (no generator output); OFF-only table check passed per prefix" if all(r["passed"] for r in reports) else "see failures",
        model_calls=0, gpu_used=False, wall_seconds=round(time.time() - t0, 1), evidence_tier="engineering_only")
    tag = f"real_replay_v2_{args.port}port_{bank.version.split(':')[1][:8]}_{summary['code_head'][:8]}"
    out = Path(args.out) if args.out else PROJECT / cfg["out_root"] / tag
    write_jsonl_once(out / "replay_reports.jsonl", reports)
    write_json_once(out / "summary.json", summary)
    if not args.out:
        code = [PROJECT / x for x in ("scripts/rl1v3/B5_real_replay_v2.py", "src/metacom_pm/rl1v3/env/bank_replay_v2.py",
                                      "src/metacom_pm/rl1v3/env/a1b_port.py", "src/metacom_pm/rl1v3/env/c0_binding.py",
                                      "src/metacom_pm/rl1v3/env/finite_head.py", "configs/rl1v3/B5_real_replay_v2.yaml",
                                      "src/metacom_pm/rl1v3/bank/v0_port.py", "src/metacom_pm/rl1v3/retrieve/v0.py")]
        inputs = {"coverage_sample": PROJECT / cfg["coverage_sample"],
                  "registry": REPO / cfg["registry_dir"] / "registry.json",
                  "sources": REPO / cfg["registry_dir"] / "sources.jsonl",
                  "bank": REPO / cfg["bank_dir"] / "bank.json", "records": REPO / cfg["bank_dir"] / "records.jsonl",
                  "index": REPO / cfg["bank_dir"] / "index.json"}
        man = build_manifest(task="B5_real_replay_v2", root=PROJECT, inputs=inputs,
                             outputs=[out / "replay_reports.jsonl", out / "summary.json"], code=code,
                             code_sha=summary["code_head"])
        write_json_once(out / "manifest.json", dict(man, model_calls=0, gpu_used=False,
                                                    status=summary["status"]))
    print(json.dumps(summary, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
