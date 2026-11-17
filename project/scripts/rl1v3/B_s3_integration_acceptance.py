"""WS-B S3: formal integration acceptance of B5 v2 / B1 cross_check / NeedCard v2 CPU preflight.

Reads the three runs produced UNCHANGED at the real integration HEAD (receipts in
``logs/``), checks the brief's targets and compares field-by-field with
(a) the integration owner's acceptance at merge 16644abb and (b) WS-B's
pre-integration run at 173bed23.  Writes ``ACCEPTANCE.json`` + ``MANIFEST.json``
(SHA256 of inputs, outputs, code files at HEAD).  No model, GPU or paid call.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from math import comb, factorial
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))
from metacom_pm.rl1v3.io import build_manifest, file_sha256, write_json_once  # noqa: E402

V3 = PROJECT / "outputs/pm_rl1/v3"
OWNER = V3 / "integration_a1_a1b_b_s2_20261118/validation/real"
PRE = dict(B5=V3 / "B5/real_replay_v2_aport_02d0a4b1_173bed23", cross=V3 / "B1/A1_cross_check_c6ad9b15",
           pre=V3 / "B1/needcard_cpu_preflight_v2_a1b_catalog")
B5_KEYS = ("key_by_subset", "reachable", "n_reachable", "n_orders", "input_tokens_by_subset", "availability",
           "unreachable_heads", "identity", "head_probe", "base_tokens", "capacity", "masked_probes",
           "static_mask_disagreements", "replay_identical", "passed", "failures", "capacity_stress")
VOLATILE = ("code_head", "wall_seconds")


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines()]


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()


def orders(k):
    return sum(comb(k, j) * factorial(j) for j in range(k + 1))


def cmp_reports(a, b, keys):
    A, B = {r["prefix_id"]: r for r in a}, {r["prefix_id"]: r for r in b}
    diff = {p: [k for k in keys if A[p].get(k) != B[p].get(k)] for p in A if p in B}
    return dict(prefixes_a=len(A), prefixes_b=len(B), same_prefix_set=set(A) == set(B),
                identical_prefixes=sum(not v for v in diff.values()),
                differing={p: v for p, v in diff.items() if v})


def cmp_json(a, b, ignore=VOLATILE):
    a, b = json.loads(Path(a).read_text()), json.loads(Path(b).read_text())
    ks = (set(a) | set(b)) - set(ignore)
    return dict(identical_except=list(ignore), differing_fields=sorted(k for k in ks if a.get(k) != b.get(k)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", default=str(V3 / "WSB_S3/integration_acceptance_320a33d1"))
    args = ap.parse_args()
    run = Path(args.run)
    rec = {p.stem.replace(".receipt", ""): json.loads(p.read_text()) for p in sorted((run / "logs").glob("*.receipt.json"))}
    head = {r["head"] for r in rec.values()}
    rep, s5 = jl(run / "B5/replay_reports.jsonl"), json.loads((run / "B5/summary.json").read_text())
    cc, pf = json.loads((run / "B1_cross_check/cross_check.json").read_text()), json.loads((run / "B1_preflight/summary.json").read_text())
    pins = jl(run / "B1_preflight/pilot_inputs.jsonl")
    # targets from the brief
    terminals = sum(r["n_reachable"] for r in rep)
    n_orders = sum(r["n_orders"] for r in rep)
    k_of = {r["prefix_id"]: max(len(s.split("+")) if s != "OFF" else 0 for s in r["key_by_subset"]) for r in rep}
    order_formula_ok = all(r["n_orders"] == orders(k_of[r["prefix_id"]]) and r["n_reachable"] == 2 ** k_of[r["prefix_id"]]
                           for r in rep)
    pending_ok = all(not any(f.startswith("pending") for f in r["failures"]) for r in rep) and \
        s5["terminal_outcomes"].startswith("all pending")
    checks = dict(
        all_runs_at_one_head=len(head) == 1, head=sorted(head)[0],
        head_is_integration_tip=sorted(head)[0] == git("rev-parse", "origin/pmrl1-v3/integration"),
        merge_pr8_is_ancestor=subprocess.run(["git", "merge-base", "--is-ancestor", "b591863e", sorted(head)[0]], cwd=REPO).returncode == 0,
        merge_pr9_is_ancestor=subprocess.run(["git", "merge-base", "--is-ancestor", "16644abb", sorted(head)[0]], cwd=REPO).returncode == 0,
        code_unchanged_since_pr9_merge=git("diff", "--stat", "16644abb", sorted(head)[0], "--", "project/src", "project/scripts",
                                           "project/configs", "project/tests") == "",
        tracked_tree_clean_during_runs=all(r["dirty_tracked"] == 0 for r in rec.values()),
        exit_codes_zero=all(r["exit_code"] == 0 for r in rec.values()),
        b5_status=s5["status"], b5_a_integrated=s5["a_integrated"],
        b5_passed=f"{s5['passed']}/{s5['prefixes']}", b5_reachable_terminals=terminals, b5_legal_read_orders=n_orders,
        b5_order_count_formula_holds=order_formula_ok,
        b5_reachable_distribution=s5["reachable_distribution"], b5_unreachable=s5["unreachable_reasons"],
        b5_ready_at_equals_cutoff=s5["ready_at_equals_cutoff_records"],
        b5_static_vs_dynamic_mask_disagreements=s5["static_mask_disagreements"],
        b5_capacity_stress=s5["capacity_stress"], b5_replay_identical=sum(bool(r["replay_identical"]) for r in rep),
        b5_identity=s5["reader_identity"], b5_terminals_pending=pending_ok,
        cross_check_zero_content_difference=cc["zero_content_difference"],
        cross_check_counts=dict(sessions=cc["personal_sessions"], prefixes=cc["prefixes"],
                                content_mismatches=cc["content_mismatches"], prefix_mismatches=cc["prefix_mismatches"]),
        preflight_statuses=pf["statuses"], preflight_ready=sum(p["status"] == "ready" for p in pins),
        preflight_tokens=dict(min=min(p["input_tokens"] for p in pins), max=max(p["input_tokens"] for p in pins),
                              total=sum(p["input_tokens"] for p in pins)),
        preflight_writer_calls=pf.get("writer_calls", 0),
    )
    targets = dict(prefixes_24_of_24=s5["passed"] == 24 == s5["prefixes"], terminals_360=terminals == 360,
                   read_orders_1413=n_orders == 1413, sessions_401_prefixes_4119_zero_diff=(
                       cc["zero_content_difference"] and cc["personal_sessions"] == 401 and cc["prefixes"] == 4119),
                   needcard_inputs_20_ready=checks["preflight_ready"] == 20 == len(pins),
                   formal_on_integration=s5["status"] == "formal_on_integration",
                   ready_at_boundary_21=s5["ready_at_equals_cutoff_records"] == 21,
                   pending_semantics=pending_ok, dynamic_capacity_stress_24=s5["capacity_stress"]["passed"] == 24 ==
                   s5["capacity_stress"]["rejected_read_tested"])
    comparisons = dict(
        B5_vs_integration_owner_16644abb=cmp_reports(rep, jl(OWNER / "B5/replay_reports.jsonl"), B5_KEYS),
        B5_vs_wsb_pre_integration_173bed23=cmp_reports(rep, jl(PRE["B5"] / "replay_reports.jsonl"), B5_KEYS),
        B5_summary_vs_owner=cmp_json(run / "B5/summary.json", OWNER / "B5/summary.json"),
        B5_summary_vs_pre=cmp_json(run / "B5/summary.json", PRE["B5"] / "summary.json"),
        cross_check_vs_owner=cmp_json(run / "B1_cross_check/cross_check.json", OWNER / "B1_cross_check/cross_check.json"),
        cross_check_vs_pre=cmp_json(run / "B1_cross_check/cross_check.json", PRE["cross"] / "cross_check.json"),
        preflight_inputs_vs_owner=dict(byte_identical=file_sha256(run / "B1_preflight/pilot_inputs.jsonl") ==
                                       file_sha256(OWNER / "B1_preflight/pilot_inputs.jsonl")),
        preflight_inputs_vs_pre=dict(byte_identical=file_sha256(run / "B1_preflight/pilot_inputs.jsonl") ==
                                     file_sha256(PRE["pre"] / "pilot_inputs.jsonl")),
        preflight_summary_vs_owner=cmp_json(run / "B1_preflight/summary.json", OWNER / "B1_preflight/summary.json"),
        preflight_summary_vs_pre=cmp_json(run / "B1_preflight/summary.json", PRE["pre"] / "summary.json"),
        catalog_vs_owner=dict(byte_identical=file_sha256(run / "B1_preflight/rs_v0_label_catalog.json") ==
                              file_sha256(OWNER / "B1_preflight/rs_v0_label_catalog.json")),
    )
    out = dict(protocol="pmrl1v3-wsb-s3-integration-acceptance-v1", status="formal_integration_acceptance"
               if all(targets.values()) and all(v for k, v in checks.items() if k.endswith(("_ancestor", "clean_during_runs", "zero", "unchanged_since_pr9_merge")))
               else "not_accepted", targets=targets, checks=checks, comparisons=comparisons, receipts=rec,
               scope="engineering runnability + legal sources only; no resource relevance or support benefit measured",
               model_calls=0, gpu_used=False, evidence_tier="engineering_only")
    write_json_once(run / "ACCEPTANCE.json", out)
    files = sorted(p for p in run.rglob("*") if p.is_file() and p.name not in ("ACCEPTANCE.json", "MANIFEST.json"))
    b5 = __import__("yaml").safe_load((PROJECT / "configs/rl1v3/B5_real_replay_v2.yaml").read_text())
    inputs = {"coverage_sample": PROJECT / b5["coverage_sample"], "registry": REPO / b5["registry_dir"] / "registry.json",
              "sources": REPO / b5["registry_dir"] / "sources.jsonl", "bank": REPO / b5["bank_dir"] / "bank.json",
              "records": REPO / b5["bank_dir"] / "records.jsonl", "index": REPO / b5["bank_dir"] / "index.json",
              "census": PROJECT / "outputs/pm_rl1/v3/B0/prefix_census.jsonl",
              "rs_catalog": REPO / "project/outputs/pm_rl1/v3/A1b_crossline_20261118/RS_V0_STRATEGY_CATALOG.json"}
    code = [PROJECT / x for x in (
        "scripts/rl1v3/B5_real_replay_v2.py", "scripts/rl1v3/B1_A1_cross_check.py", "scripts/rl1v3/B1_needcard_cpu_preflight.py",
        "src/metacom_pm/rl1v3/env/bank_replay_v2.py", "src/metacom_pm/rl1v3/env/c0_binding.py", "src/metacom_pm/rl1v3/env/finite_head.py",
        "src/metacom_pm/rl1v3/bank/v0_port.py", "src/metacom_pm/rl1v3/retrieve/v0.py", "src/metacom_pm/rl1v3/needs/sources.py",
        "src/metacom_pm/rl1v3/needs/protocol_v2.py", "configs/rl1v3/B5_real_replay_v2.yaml", "configs/rl1v3/B1_needcard_v2.yaml",
        "scripts/rl1v3/B_s3_integration_acceptance.py")]
    man = build_manifest(task="WSB_S3_integration_acceptance", root=PROJECT, inputs=inputs, outputs=files + [run / "ACCEPTANCE.json"],
                         code=code, code_sha=checks["head"])
    write_json_once(run / "MANIFEST.json", dict(man, model_calls=0, gpu_used=False, status=out["status"]))
    print(json.dumps(dict(status=out["status"], targets=targets,
                          comparisons={k: {kk: vv for kk, vv in v.items() if kk != "differing"} | (
                              {"differing": v["differing"]} if v.get("differing") else {}) for k, v in comparisons.items()}),
                     indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
