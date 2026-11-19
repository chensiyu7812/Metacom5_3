#!/usr/bin/env python3
"""CPU-only DP v2 preparation; no Generator entrypoint. Real payloads stay on the data disk."""
import argparse
import importlib.util
import json
from pathlib import Path
from metacom_pm.rl1v3.compile import dp_selection_v2 as D
from metacom_pm.rl1v3.io import parse_json, write_json_once, write_jsonl_once


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("action", choices=["prepare", "freeze", "export", "check-start", "check-reviewer"])
    p.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[3])
    for name in ("sample-manifest", "screening", "bundle", "draft", "roles", "receipts", "ret-audit", "baseline", "plan", "requests", "out"):
        p.add_argument("--"+name, type=Path)
    for name in ("prefix-id", "reviewer", "channel"):
        p.add_argument("--"+name)
    a = p.parse_args()
    def read(key):
        path = getattr(a, key)
        if path is None: p.error("--"+key.replace("_", "-")+" required")
        return parse_json(path.read_text())
    def output():
        if a.out is None: p.error("--out required")
        # Do not emit real RAW-derived packages into this public checkout.
        target = a.out.resolve()
        D.require(target.is_relative_to(Path("/opt/tokkio-data0")) and
                  not any((p/".git").exists() for p in (target, *target.parents)),
                  "output must be on the data disk outside the public checkout")
        return target
    if a.action == "prepare":
        bundle, ret = D.prepare_formal(a.root, read("sample_manifest"), read("screening"))
        out = output(); out.mkdir(parents=True, exist_ok=False)
        write_json_once(out/"SELECTOR_BUNDLE.json", bundle)
        write_json_once(out/"AUDIT_RET_NOT_FOR_SELECTOR.json", ret)
        (out/"SELECTOR.html").write_text(D.selection_html(bundle))
    elif a.action == "freeze":
        receipt = D.freeze_choice(read("bundle"), read("draft"), read("roles"), output())
        print(json.dumps({"receipt_sha256":receipt["receipt_sha256"], "authorized":False}))
    else:
        bundle, roles = read("bundle"), read("roles")
        if a.receipts is None: p.error("--receipts required")
        receipts = {e["pool"]["prefix_id"]:parse_json((a.receipts/(e["pool"]["prefix_id"]+".json")).read_text()) for e in bundle["rows"]}
        if a.action == "check-reviewer":
            if not all((a.prefix_id, a.reviewer, a.channel)): p.error("--prefix-id --reviewer --channel required")
            D.check_reviewer(read("plan"), bundle, receipts, roles, a.prefix_id, a.reviewer, a.channel)
            print(json.dumps({"reviewer_assignment":"PASS", "authorized":False}))
            return
        manifest, screening = read("sample_manifest"), read("screening")
        if a.action == "export":
            D.validate_sample(manifest, screening)  # refuse simulated/unconfirmed before tokenizer access
            spec = importlib.util.spec_from_file_location("native_counter", a.root/"project/scripts/rl1v3/prepare_e1_qualification.py")
            m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
            base = read("baseline")
            counter = m.NativeCounter(Path("/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3"), {"common":base["spec"]})
            rows = D.export_candidates(bundle, receipts, roles, read("ret_audit"), base, counter)
            plan = D.bind_plan(bundle, receipts, roles, rows, manifest, screening)
            out = output(); out.mkdir(parents=True, exist_ok=False)
            write_jsonl_once(out/"REQUESTS.jsonl", rows); write_json_once(out/"PLAN_BINDING.json", plan)
            print(json.dumps({"candidate_rows":len(rows), "plan_sha256":plan["plan_sha256"], "authorized":False}))
        else:
            if a.requests is None: p.error("--requests required")
            rows = [parse_json(line) for line in a.requests.read_text().splitlines()]
            print(json.dumps(D.check_start(read("plan"), bundle, receipts, roles, rows, manifest, screening)))


if __name__ == "__main__": main()
