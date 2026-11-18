#!/usr/bin/env python
"""WS-B independent receipt for WS-A PR #18 (pinned HEAD), CPU only.

  check      mechanical axes from git objects at the pinned SHA (no WS-A code imported or executed)
  tokenize   G0e native tokenizer re-tokenisation of every preview (CPU, tokenizer files only, no weights);
             run with the G0e HF interpreter recorded in PR #10's G0e.json
  receipt    combine check + tokenize into the three-axis receipt

Outputs: outputs/pm_rl1/v3/V321_WSB/pr18_receipt/
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

PR18_SHA = "0a91ff3329dc0d091fbb9e234035638efb45146c"
PR18_BASE = "b63635f3621f3a5d252099efcd58ae2d1958dce2"
G0E_REF = "73fdb12f"                      # PR #10 head; G0e identity file
G0E_PATH = "project/configs/rl1v3/G0e.json"
BUNDLE = "project/outputs/pm_rl1/v3/qualification_e1_20261118"
ARTIFACT = PROJECT / "data/paper1_public_memory/es_memeval_public_sanitized_runtime_artifact_v1.json"
CENSUS = PROJECT / "outputs/pm_rl1/v3/B0/prefix_census.jsonl"
SELECTION = PROJECT / "outputs/pm_rl1/v3/B6e_plan/v3/SELECTION.json"
OUT = PROJECT / "outputs/pm_rl1/v3/V321_WSB/pr18_receipt"
MODEL_DIR = Path("/opt/tokkio-data0/tokkio_models/gemma-4-12B-it-707f0a3")
PP1_SHA = "4ac9ab3d23d04cd8ec9435ea239995ae85a3e610"   # WS-A pmrl1-v3/ws-a-ms-pp1-prep-20261119 (no PR yet)
PP1_REQ = "project/outputs/pm_rl1/v3/ms_pp1_prepare_20261119/cpu_v2/REQUESTS_16.jsonl"
PR13_SHA = "ea2f5bde04caba4590b26c80a572d66caa4a2d08"
PR13_JOBS = "project/outputs/pm_rl1/v3/resource_architecture_review_20261118/cpu/PROPOSED_JOBS.json"
ELIG = PROJECT / "outputs/pm_rl1/v3/V32_WSB_P0P2/p2/ELIGIBILITY_54.json"
OUT_PP1 = PROJECT / "outputs/pm_rl1/v3/V321_WSB/pp1_requests_preliminary"


def git_show(ref: str, path: str) -> str:
    return subprocess.run(["git", "show", f"{ref}:{path}"], cwd=REPO, capture_output=True, text=True,
                          check=True).stdout


def git_ls(ref: str, path: str) -> list[str]:
    return subprocess.run(["git", "ls-tree", "-r", "--name-only", ref, path], cwd=REPO, capture_output=True,
                          text=True, check=True).stdout.split()


def bundle_json(rel: str):
    from metacom_pm.rl1v3.asof.e1_receipt import strict_loads
    return strict_loads(git_show(PR18_SHA, f"{BUNDLE}/{rel}"))


def bundle_jsonl(rel: str):
    from metacom_pm.rl1v3.asof.e1_receipt import strict_loads
    return [strict_loads(x) for x in git_show(PR18_SHA, f"{BUNDLE}/{rel}").splitlines() if x.strip()]


def write(name: str, obj, out: Path = OUT) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    p = out / name
    if p.exists():
        raise SystemExit(f"refusing to overwrite {p}")
    p.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=True) + "\n")
    return p


def step_check(_):
    from metacom_pm.rl1v3.asof import e1_receipt as E
    from metacom_pm.rl1v3.io import file_sha256
    raw = E.Raw(json.loads(ARTIFACT.read_text()))
    census = {(c["owner_id"], c["session_id"], c["cut_turn"]): c for c in map(json.loads, CENSUS.read_text().splitlines())}
    selected = set(json.loads(SELECTION.read_text())["selected_ids"])
    g0e = json.loads(git_show(G0E_REF, G0E_PATH))
    vectors = bundle_json("HASH_TEST_VECTORS.json")
    vec_problems = E.check_vectors(vectors)
    bindings = bundle_jsonl("cpu_v3/BINDINGS.jsonl")
    rows, files_by_prefix = [], {}
    agree = 0
    for b in bindings:
        f = {k: bundle_json("cpu_v3/" + b[f"{k}_path"]) for k in ("prefix", "frontier", "reading")}
        f["snapshot_past"] = bundle_json("cpu_v3/" + b["snapshot_past"])
        f["snapshot_future"] = bundle_json("cpu_v3/" + b["snapshot_future"])
        f["ledger_past"] = bundle_jsonl("cpu_v3/" + b["ledger_past"])
        f["ledger_future"] = bundle_jsonl("cpu_v3/" + b["ledger_future"])
        # own encoder vs stdlib json on every hashed object (spec cross-check)
        for s in (f["snapshot_past"], f["snapshot_future"]):
            body = {k: v for k, v in s.items() if k != "snapshot_sha"}
            agree += E.canon(body) == json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        pre = f["prefix"]
        rows.append(E.check_prefix(b, f, raw, census.get((pre["owner_id"], pre["session_id"], pre["cut_turn"])),
                                   selected))
        files_by_prefix[b["prefix_id"]] = f
    # B's existing PR #15 sidecar adapter + X1-X7 checker over all 16 snapshots (horizon pairs)
    side = None
    try:
        from metacom_pm.rl1v3.bank import v0_port as BP
        from metacom_pm.rl1v3.asof import wsa_adapter as WA
        bank, _ = BP.load_bank(REPO)
        snaps = [f[k] for f in files_by_prefix.values() for k in ("snapshot_past", "snapshot_future")]
        side = WA.check_sidecar(snaps, bank.registry, list(census.values()))
        side = {k: v for k, v in side.items() if k != "rows"} | dict(
            row_problems=sorted({p for r in side["rows"] for p in r["problems"]}))
        side["x5a"] = "tested_by_M5 (two horizons per prefix)"
    except Exception as exc:  # recorded, not hidden
        side = dict(error=repr(exc))
    # Generator-visible projection
    props = bundle_jsonl("cpu_v3/E1_PROPOSALS.jsonl")
    off = {r["prefix_id"]: r["preview_messages"] for r in props if r["arm"] == "OFF"}
    proj = []
    for r in props:
        f = files_by_prefix[r["prefix_id"]]
        proj.append(E.check_projection(r, f["prefix"], f["reading"].get("MS"), raw, g0e, off.get(r["prefix_id"])))
    # dual-horizon readings file
    dual = bundle_json("DUAL_HORIZON_READINGS.json")
    dual_p = [x["prefix_id"] for x in dual["rows"] if x.get("future_readings") != x.get("past_readings")]
    dual_vs_bundle = [x["prefix_id"] for x in dual["rows"]
                      if x.get("past_readings") != files_by_prefix[x["prefix_id"]]["reading"]]
    # isolation: RS CASE families vs every owner's family closure
    cases = bundle_jsonl("cpu_v3/RS_CASES.jsonl")
    all_fams = {o: raw.families(o) for o in raw.by_owner}
    case_overlap = sorted({(c["family_id"], o) for c in cases for o, fs in all_fams.items() if c["family_id"] in fs})
    shared = sorted({fam for o, fs in all_fams.items() for fam in fs if fam.startswith("esconv:") and
                     sum(fam in g for g in all_fams.values()) > 1})
    matrix = bundle_jsonl("FINAL_EXECUTABILITY_MATRIX.jsonl")
    res = dict(
        protocol=E.PROTOCOL, pr18_head=PR18_SHA, pr18_base=PR18_BASE, g0e_ref=G0E_REF,
        inputs=dict(artifact_sha256=file_sha256(ARTIFACT), census_sha256=file_sha256(CENSUS),
                    selection_sha256=file_sha256(SELECTION)),
        hash_vectors=dict(n=len(vectors), problems=vec_problems),
        own_encoder_equals_stdlib_on_snapshots=f"{agree}/{2 * len(bindings)}",
        prefixes=rows, prefixes_passed=sum(not r["problems"] for r in rows),
        b_sidecar_adapter=side,
        projection=dict(rows=len(proj), previewed=sum(x["previewed"] for x in proj),
                        passed=sum(x["previewed"] and not x["problems"] for x in proj),
                        problems=Counter(p.split(":")[0] for x in proj for p in x["problems"]),
                        html_escaped_payload=sum(bool(x.get("html_escaped_payload")) for x in proj),
                        metadata_patterns=Counter(t for x in proj for t in x.get("metadata_patterns", [])),
                        renderer_ids=sorted({r["renderer_id"] for r in props}),
                        g_ids=sorted({r["g_id"] for r in props}), arms=Counter(r["arm"] for r in props),
                        by_arm_problems={a: sorted({p for x in proj if x["arm"] == a for p in x["problems"]})
                                         for a in sorted({x["arm"] for x in proj})},
                        token_range=[min(x["input_tokens"] for x in proj if x["previewed"]),
                                     max(x["input_tokens"] for x in proj if x["previewed"])]),
        dual_horizon_readings=dict(pairs=len(dual["rows"]), differ=dual_p, differ_from_bundle=dual_vs_bundle,
                                   generator_calls=dual.get("generator_calls"), weights_loaded=dual.get("weights_loaded")),
        isolation=dict(case_families=sorted({c["family_id"] for c in cases}), case_family_owner_overlap=case_overlap,
                       esconv_families_shared_by_owners=shared),
        matrix=dict(rows=len(matrix), by_status=Counter(json.dumps([m.get("arm"), m.get("native_capacity")])
                                                         for m in matrix)),
        g0e_identity=dict(system_prompt_sha=E.text_sha(g0e["common"]["system_prompt"]), decode=g0e["common"]["decode"],
                          renderer_implementation_sha256=g0e["common"]["renderer_implementation_sha256"]),
    )
    write("MECHANICAL_CHECK.json", res)
    write("PROJECTION_ROWS.json", proj)
    print(json.dumps(dict(prefixes_passed=res["prefixes_passed"], prefix_problems=[r["problems"] for r in rows],
                          projection={k: res["projection"][k] for k in ("previewed", "passed", "problems",
                                                                         "html_escaped_payload", "metadata_patterns")},
                          dual=res["dual_horizon_readings"], isolation=res["isolation"],
                          sidecar=side if "error" in side else dict(passed=side.get("passed"),
                                                                    cutoffs_passed=side.get("cutoffs_passed"),
                                                                    row_problems=side.get("row_problems"))),
                     ensure_ascii=False, indent=1, default=str))


def step_tokenize(_):
    """Run with the G0e HF interpreter: tokenizer files only; never loads weights."""
    import hashlib
    from transformers import AutoTokenizer
    files = {n: hashlib.sha256((MODEL_DIR / n).read_bytes()).hexdigest()
             for n in ("tokenizer.json", "tokenizer_config.json", "chat_template.jinja")}
    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    props = [json.loads(x) for x in git_show(PR18_SHA, f"{BUNDLE}/cpu_v3/E1_PROPOSALS.jsonl").splitlines() if x]
    rows = []
    for r in props:
        if not r["preview_messages"]:
            continue
        variants = {}
        for name, kw in (("gen_prompt", dict(add_generation_prompt=True)),
                         ("gen_prompt_no_think", dict(add_generation_prompt=True, enable_thinking=False))):
            try:
                ids = tok.apply_chat_template(r["preview_messages"], tokenize=True, **kw)
                if isinstance(ids, dict) or hasattr(ids, "keys"):
                    ids = ids["input_ids"]
                variants[name] = list(ids) == r["input_ids"]
            except Exception as exc:
                variants[name] = repr(exc)[:120]
        rows.append(dict(request_id=r["request_id"], arm=r["arm"], n=len(r["input_ids"]), match=variants))
    import transformers
    import tokenizers
    res = dict(model_dir=str(MODEL_DIR), file_sha256=files, transformers=transformers.__version__,
               tokenizers=tokenizers.__version__, weights_loaded=False, rows=rows,
               any_variant_matches=sum(any(v is True for v in x["match"].values()) for x in rows),
               previews=len(rows))
    write("TOKENIZE_CHECK.json", res)
    print(json.dumps({k: v for k, v in res.items() if k != "rows"}, indent=1))


def _pp1_rows():
    from metacom_pm.rl1v3.asof.e1_receipt import strict_loads
    return [strict_loads(x) for x in git_show(PP1_SHA, PP1_REQ).splitlines() if x.strip()]


def step_pp1req(_):
    """Preliminary check of WS-A's 16 PP1 requests (pinned WIP commit; formal receipt follows their Draft PR)."""
    from metacom_pm.rl1v3.asof import e1_receipt as E
    raw = E.Raw(json.loads(ARTIFACT.read_text()))
    g0e = json.loads(git_show(G0E_REF, G0E_PATH))
    prefixes = {}
    for b in bundle_jsonl("cpu_v3/BINDINGS.jsonl"):
        prefixes[b["prefix_id"]] = bundle_json("cpu_v3/" + b["prefix_path"])
    elig = {r["plan_job_id"]: r for r in json.loads(ELIG.read_text())["rows"] if r.get("plan_job_id")}
    jobs = {j["plan_job_id"]: j for j in json.loads(git_show(PR13_SHA, PR13_JOBS))["jobs"]}
    rows = _pp1_rows()
    off = {r["prefix_id"]: r["model_input"]["messages"] for r in rows if r["condition"] == "OFF"}
    res = []
    for r in sorted(rows, key=lambda r: r["order"]):
        x = E.check_pp1_request(r, prefixes[r["prefix_id"]], raw, g0e, off.get(r["prefix_id"]))
        e = elig.get(r["plan_job_id"])
        if e is None or e["joint_eligibility"] != "ELIGIBLE" or e["terminal_key_sha256"] != r["terminal_key_sha256"] \
                or e["existing_request_id"] != r["legacy_request_id"] or \
                {"OFF": "OFF", "MS": "RET-MS"}[e["subset"]] != r["condition"]:
            x["problems"].append("Q9_not_the_B_ELIGIBLE_input")
        if jobs.get(r["plan_job_id"], {}).get("input_tokens") != r["input_tokens"]:
            x["problems"].append("Q9_input_tokens_differ_from_PR13_job")
        if r["renderer_id"] != rows[0]["renderer_id"] or r["g_id"] != g0e_gid():
            x["problems"].append("Q10_renderer_or_g_id_not_single")
        res.append(x)
    out = dict(protocol=E.PROTOCOL + ":pp1-requests", scope="preliminary; WS-A WIP commit without PR",
               ws_a_commit=PP1_SHA, file=PP1_REQ, file_sha256_git=__import__("hashlib").sha256(
                   git_show(PP1_SHA, PP1_REQ).encode()).hexdigest(),
               requests=len(res), passed=sum(not x["problems"] for x in res),
               problems=dict(Counter(p.split(":")[0] for x in res for p in x["problems"])),
               renderer_ids=sorted({r["renderer_id"] for r in rows}), conditions=dict(Counter(r["condition"] for r in rows)),
               html_escaped=sum(x["html_escaped"] for x in res),
               ret_ms_sources=[dict(order=x["order"], owner=x["owner_id"], session=x["ms_source"]["session_id"],
                                    rank=x["ms_source"]["rank"], cutoff=prefixes[r["prefix_id"]]["cutoff_rank"])
                               for x, r in zip(res, sorted(rows, key=lambda r: r["order"])) if x["ms_source"]],
               rows=res)
    write("PP1_REQUESTS_CHECK.json", out, OUT_PP1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}, ensure_ascii=False, indent=1))


def g0e_gid():
    return "G0e:b624c7c3f99ffe6b35eca29e2f93ea9e624e66b31303415e4b9c4b1bc4c6c07e"


def step_pp1tok(_):
    """G0e HF interpreter: tokenizer files only."""
    from transformers import AutoTokenizer
    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    rows = []
    for r in _pp1_rows():
        m = r["model_input"]
        ids = tok.apply_chat_template(m["messages"], tokenize=True, add_generation_prompt=True)
        if hasattr(ids, "keys"):
            ids = ids["input_ids"]
        rows.append(dict(request_id=r["request_id"], order=r["order"], n=len(m["input_ids"]),
                         match=list(ids) == m["input_ids"]))
    out = dict(model_dir=str(MODEL_DIR), weights_loaded=False, rows=rows, matched=sum(x["match"] for x in rows),
               requests=len(rows))
    write("PP1_TOKENIZE_CHECK.json", out, OUT_PP1)
    print(json.dumps({k: v for k, v in out.items() if k != "rows"}))


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("step", choices=("check", "tokenize", "pp1req", "pp1tok"))
    a = ap.parse_args()
    dict(check=step_check, tokenize=step_tokenize, pp1req=step_pp1req, pp1tok=step_pp1tok)[a.step](a)
