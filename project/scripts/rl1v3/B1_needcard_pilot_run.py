"""B1 NeedCard writer v2 pilot on the fixed 20 fold-1..5 prefixes (``pmrl1v3-b1-needcard-pilot-v1``).

Modes
  plan   CPU. Rebuild the 20 packs from the A1 registry + A's RS-v0 catalog, require them to be
         byte-identical (pack sha) to the accepted integration preflight, and write the write-once
         RUN_PLAN.json (identities, input SHAs, caps, stop conditions, commands, output dir).
  check  CPU. Re-verify an existing plan in the current Python env (tokenizer counts -> pack sha,
         code hashes); ``--verify-weights`` also hashes the model files against the asset audit.
  run    GPU, ONLY with a researcher AUTHORIZATION.json bound to the plan sha.  Loads Qwen3.5-9B
         (bf16, sdpa, greedy, non-thinking, max_new_tokens 800) on the A6000 and runs
         ``needs.pilot.run_pilot``.  Never truncates, never changes the prompt, never reruns.
NeedCards are evaluation-side artefacts; nothing here feeds a PM observation or the generator.
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

from metacom_pm.rl1v3.io import file_sha256, object_sha256, write_json_once  # noqa: E402
from metacom_pm.rl1v3.needs import pilot as PL  # noqa: E402
from metacom_pm.rl1v3.needs import protocol_v2 as W  # noqa: E402
from metacom_pm.rl1v3.needs.sources import a1_context  # noqa: E402

CODE = ("scripts/rl1v3/B1_needcard_pilot_run.py", "src/metacom_pm/rl1v3/needs/pilot.py",
        "src/metacom_pm/rl1v3/needs/protocol_v2.py", "src/metacom_pm/rl1v3/needs/protocol.py",
        "src/metacom_pm/rl1v3/needs/cards.py", "src/metacom_pm/rl1v3/needs/spans.py",
        "src/metacom_pm/rl1v3/needs/sources.py", "src/metacom_pm/rl1v3/retrieve/native_tokens.py",
        "configs/rl1v3/B1_needcard_pilot_v1.yaml")


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()


def load(cfg):
    """Rebuild contexts + ready packs exactly as the accepted preflight did."""
    from metacom_pm.rl1v3.bank import rs_v0_catalog as AC
    from metacom_pm.rl1v3.env import a1b_port as P
    from metacom_pm.rl1v3.retrieve.native_tokens import NativeTokenizer
    pre, b5 = (yaml.safe_load((PROJECT / cfg[k]).read_text()) for k in ("preflight_config", "b5_config"))
    bank = P.load_bank(REPO, registry_dir=b5["registry_dir"], bank_dir=b5["bank_dir"],
                       expected_source=b5["expected_source"], expected_bank=b5["expected_bank"])
    catalog = AC.load(REPO / pre["rs_catalog_path"], root=REPO, bank=bank)
    tok = NativeTokenizer(pre["writer_model"]["path"], PROJECT / pre["asset_manifest"])

    def ids(msgs):
        out = tok.tokenizer.apply_chat_template(msgs, tokenize=True, add_generation_prompt=True,
                                                enable_thinking=False, return_dict=False)
        return list(out)
    census = {json.loads(x)["prefix_id"]: json.loads(x) for x in (PROJECT / pre["census"]).read_text().splitlines()}
    cov = [json.loads(x) for x in (PROJECT / pre["coverage_sample"]).read_text().splitlines()]
    pilots = [c for c in cov if c["uses"].get(pre["pilot_use"]) is True]
    ctxs, packs = {}, {}
    for c in pilots:
        ctx = a1_context(bank.registry, census[c["prefix_id"]])
        packs[c["prefix_id"]] = W.build_pack(ctx, catalog, registry=bank.registry, count_prompt=lambda m: len(ids(m)),
                                             native_context_tokens=tok.native_context_tokens,
                                             operational_max_input_tokens=pre["operational_max_input_tokens"],
                                             tokenizer_identity=tok.identity)
        ctxs[c["prefix_id"]] = ctx
    manifest = json.loads((PROJECT / pre["asset_manifest"]).read_text())
    model_files = sorted((r["path"].split("/")[-1], r["sha256"]) for r in manifest["files"]
                         if r.get("exists") and r["path"].startswith(pre["writer_model"]["path"] + "/"))
    model_sha = object_sha256(model_files)
    writer = W.writer_identity(model_id=pre["writer_model"]["model_id"], model_sha256=model_sha,
                               decode_id=pre["writer_model"]["decode_id"])
    return dict(pre=pre, b5=b5, bank=bank, catalog=catalog, tok=tok, ids=ids, pilots=pilots, ctxs=ctxs, packs=packs,
                model_files=model_files, model_sha=model_sha, writer=writer)


def build_plan(cfg, L):
    accepted = {json.loads(x)["prefix_id"]: json.loads(x) for x in (PROJECT / cfg["accepted_preflight"]).read_text().splitlines()}
    acc = json.loads((PROJECT / cfg["acceptance"]).read_text())
    inputs = []
    for k, c in enumerate(L["pilots"]):
        p, a = L["packs"][c["prefix_id"]], accepted[c["prefix_id"]]
        if p["pack_sha256"] != a["pack_sha256"] or p["status"] != "ready" or p["input_tokens"] != a["input_tokens"]:
            raise SystemExit(f"S1: pack {c['prefix_id']} differs from the accepted integration preflight")
        inputs.append(dict(order=k + 1, prefix_id=c["prefix_id"], owner_id=c["owner_id"], fold=c["fold"],
                           rank_bucket=c["rank_bucket"], pack_sha256=p["pack_sha256"], input_tokens=p["input_tokens"],
                           past_sessions=p["past_sessions"], source_ids_sha256=a["source_ids_sha256"]))
    rt, lim = cfg["runtime"], PL.LIMITS
    run_cmd = (f"cd <repo>/project && CUDA_VISIBLE_DEVICES={rt['gpu_uuid']} PYTHONNOUSERSITE=1 PYTHONPATH=src "
               f"{rt['python']} scripts/rl1v3/B1_needcard_pilot_run.py --mode run "
               f"--authorization {cfg['plan_dir']}/AUTHORIZATION.json")
    tot = sum(r["input_tokens"] for r in inputs)
    plan = dict(
        task_id=cfg["task_id"], pilot_protocol=PL.PILOT_PROTOCOL, evidence_tier="engineering_only",
        acceptance=dict(path=cfg["acceptance"], sha256=file_sha256(PROJECT / cfg["acceptance"]), status=acc["status"],
                        integration_head=acc["checks"]["head"]),
        writer=dict(protocol=W.WRITER_PROTOCOL, prompt_sha256=W.prompt_sha256(), identity=L["writer"],
                    model_id=L["pre"]["writer_model"]["model_id"], model_path=L["pre"]["writer_model"]["path"],
                    model_fileset_sha256=L["model_sha"], model_files=L["model_files"],
                    decode=dict(cfg["decode"], decode_id=L["pre"]["writer_model"]["decode_id"]),
                    tokenizer_identity=L["tok"].identity, native_context_tokens=L["tok"].native_context_tokens,
                    operational_max_input_tokens=L["pre"]["operational_max_input_tokens"]),
        sources=dict(source_version=L["bank"].registry.version, bank_version=L["bank"].version,
                     index_version=L["bank"].index_version, catalog_id=L["catalog"].catalog_id,
                     catalog_sha256=L["catalog"].sha256,
                     input_rule="A1 registry; complete legal strictly-past RAW; current visible window; A RS-v0 labels"),
        inputs=inputs, inputs_sha256=object_sha256(inputs),
        budget=dict(first_calls=lim["first_calls"], reasks=lim["reasks"], total_calls=lim["total_calls"],
                    prefill_tokens_first=tot, prefill_tokens_max=2 * tot,
                    output_tokens_max=lim["total_calls"] * cfg["decode"]["max_new_tokens"], paid_api_calls=0,
                    note="greedy decoding: a verbatim re-ask normally reproduces the same output"),
        limits=lim, stop_conditions=list(PL.STOP_CONDITIONS), runtime=rt,
        commands=dict(check_cpu=f"cd <repo>/project && CUDA_VISIBLE_DEVICES='' PYTHONNOUSERSITE=1 PYTHONPATH=src "
                                f"{rt['python']} scripts/rl1v3/B1_needcard_pilot_run.py --mode check --verify-weights",
                      run_gpu=run_cmd,
                      audit_prepare="python scripts/rl1v3/B1_needcard_pilot_audit.py --prepare",
                      audit_report="python scripts/rl1v3/B1_needcard_pilot_audit.py --report"),
        out_dir=cfg["out_dir"], authorization_path=f"{cfg['plan_dir']}/AUTHORIZATION.json",
        authorization_fields=["authorized_by", "granted_at", "scope", "plan_sha256", "max_calls", "gpu_uuid",
                              "paid_api_calls"],
        after_run=["B audits all 20 envelopes (needs.pilot_audit.CHECKS)", "evidence error rate <= 10% gate",
                   "only audited-valid cards may get a checklist; checklists frozen before any candidate"],
        needcards_enter_pm_or_g_observation=False,
        code_files_sha256={p: file_sha256(PROJECT / p) for p in CODE})
    plan["plan_sha256"] = PL.plan_sha256(plan)
    plan["written_by_code_head"] = git("rev-parse", "HEAD")
    return plan


def verify_plan(plan, L, *, weights=False):
    problems = []
    if PL.plan_sha256(plan) != plan["plan_sha256"]:
        problems.append("plan_sha256")
    for p, h in plan["code_files_sha256"].items():
        if file_sha256(PROJECT / p) != h:
            problems.append(f"code:{p}")
    try:
        PL.check_inputs(plan, L["packs"])
    except PL.PilotStopped as exc:
        problems.append(exc.reason)
    if L["writer"] != plan["writer"]["identity"] or L["tok"].identity != plan["writer"]["tokenizer_identity"]:
        problems.append("writer_or_tokenizer_identity")
    if weights:
        root = Path(plan["writer"]["model_path"])
        got = sorted((n, file_sha256(root / n)) for n, _ in plan["writer"]["model_files"])
        if got != [tuple(x) for x in plan["writer"]["model_files"]]:
            problems.append("model_files")
    if git("status", "--porcelain", "--untracked-files=no"):
        problems.append("tracked_tree_dirty")
    return problems


def gpu_gate(rt):
    q = subprocess.run(["nvidia-smi", "--query-gpu=uuid,name,memory.free", "--format=csv,noheader,nounits"],
                       capture_output=True, text=True).stdout
    rows = {u.strip(): (n.strip(), int(f)) for u, n, f in (x.split(",") for x in q.strip().splitlines())}
    apps = subprocess.run(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory", "--format=csv,noheader"],
                          capture_output=True, text=True).stdout
    busy = [a for a in apps.strip().splitlines() if a.startswith(rt["gpu_uuid"])]
    if rt["gpu_uuid"] not in rows or rows[rt["gpu_uuid"]][0] != rt["gpu_name"]:
        raise PL.PilotStopped("S1:gpu_not_found")
    if rows[rt["gpu_uuid"]][1] < rt["min_free_gib"] * 1024 or busy:
        raise PL.PilotStopped(f"S1:gpu_busy:free_mib={rows[rt['gpu_uuid']][1]}:apps={len(busy)}")
    return dict(nvidia_smi=q, compute_apps=apps)


def real_generator(L, plan):
    import torch
    import transformers
    from transformers import AutoModelForImageTextToText, StoppingCriteria, StoppingCriteriaList
    rt, dec = plan["runtime"], plan["writer"]["decode"]
    if torch.cuda.get_device_name(0) != rt["gpu_name"]:
        raise PL.PilotStopped("S1:device_name")
    t0 = time.monotonic()
    # the checkpoint's own class (Qwen3_5ForConditionalGeneration): no key remapping; text-only input
    model, loading = AutoModelForImageTextToText.from_pretrained(
        plan["writer"]["model_path"], local_files_only=True, trust_remote_code=False, dtype=getattr(torch, rt["dtype"]),
        attn_implementation=rt["attn_implementation"], output_loading_info=True)
    bad = {k: list(v) for k, v in loading.items() if k in ("missing_keys", "unexpected_keys", "mismatched_keys") and v}
    if bad:
        raise PL.PilotStopped(f"S1:weights_not_loaded_exactly:{sorted(bad)}")
    model = model.to("cuda:0").eval()
    # stop tokens pinned in the plan (the text config's eos is <|endoftext|>; chat turns end with <|im_end|>)
    eos = [L["tok"].tokenizer.convert_tokens_to_ids(t) for t in dec["stop_tokens"]]
    pad = L["tok"].tokenizer.convert_tokens_to_ids(dec["pad_token"])
    if any(not isinstance(i, int) or i < 0 for i in eos + [pad]):
        raise PL.PilotStopped("S1:stop_tokens")
    info = dict(torch=torch.__version__, transformers=transformers.__version__, cuda=torch.version.cuda,
                device=torch.cuda.get_device_name(0), model_class=type(model).__name__, eos_ids=eos, pad_id=pad,
                load_seconds=round(time.monotonic() - t0, 1), allocated_after_load=torch.cuda.memory_allocated())

    class TimeGuard(StoppingCriteria):
        def __init__(self):
            self.start, self.hit = time.monotonic(), False

        def __call__(self, input_ids, scores, **kw):
            self.hit = time.monotonic() - self.start >= PL.LIMITS["per_call_seconds"]
            return self.hit

    def generate(msgs, pack):
        ids = L["ids"](msgs)
        x = torch.tensor([ids], device="cuda:0")
        torch.cuda.reset_peak_memory_stats()
        guard, s = TimeGuard(), time.monotonic()
        with torch.inference_mode():
            y = model.generate(input_ids=x, attention_mask=torch.ones_like(x), do_sample=False, temperature=None,
                               top_p=None, top_k=None, max_new_tokens=dec["max_new_tokens"], eos_token_id=eos,
                               pad_token_id=pad, stopping_criteria=StoppingCriteriaList([guard]))
        new = y[0, len(ids):].tolist()
        finish = "stop" if new and new[-1] in eos else "timeout" if guard.hit else "length"
        return dict(text=L["tok"].tokenizer.decode(new, skip_special_tokens=True), output_tokens=len(new),
                    finish_reason=finish, input_tokens=len(ids), seconds=round(time.monotonic() - s, 2),
                    peak_bytes=torch.cuda.max_memory_allocated())
    return generate, info


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PROJECT / "configs/rl1v3/B1_needcard_pilot_v1.yaml"))
    ap.add_argument("--mode", choices=("plan", "check", "run"), default="check")
    ap.add_argument("--authorization", default=None)
    ap.add_argument("--verify-weights", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    L = load(cfg)
    plan_path = PROJECT / cfg["plan_dir"] / "RUN_PLAN.json"
    if args.mode == "plan":
        plan = build_plan(cfg, L)
        write_json_once(plan_path, plan)
        print(json.dumps(dict(plan_sha256=plan["plan_sha256"], inputs=len(plan["inputs"]), budget=plan["budget"]), indent=1))
        return
    plan = json.loads(plan_path.read_text())
    problems = verify_plan(plan, L, weights=args.verify_weights or args.mode == "run")
    print(json.dumps(dict(mode=args.mode, plan_sha256=plan["plan_sha256"], problems=problems,
                          weights_verified=args.verify_weights or args.mode == "run"), indent=1))
    if args.mode == "check" or problems:
        sys.exit(1 if problems else 0)
    if not args.authorization:
        raise SystemExit("S1: no authorization (GPU run needs the researcher's AUTHORIZATION.json)")
    auth = json.loads(Path(args.authorization).read_text())
    PL.check_authorization(auth, plan, gpu_uuid=cfg["runtime"]["gpu_uuid"])
    out = PROJECT / plan["out_dir"]
    gate = gpu_gate(plan["runtime"])
    generate, info = real_generator(L, plan)
    write_json_once(out / "runtime.json", dict(info, gpu_gate=gate, authorization_sha256=object_sha256(auth),
                                               plan_sha256=plan["plan_sha256"], code_head=git("rev-parse", "HEAD")))
    summary = PL.run_pilot(plan, L["ctxs"], L["packs"], generate, writer=plan["writer"]["identity"], out=out,
                           max_calls=auth["max_calls"])
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
