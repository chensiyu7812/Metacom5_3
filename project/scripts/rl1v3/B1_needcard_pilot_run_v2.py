"""B1 NeedCard writer v2 pilot, plan v2: 20 first calls, NO re-ask (``pmrl1v3-b1-needcard-pilot-v2``).

Alternative to plan v1 (``needcard_pilot_v1_plan/RUN_PLAN.json``, 9a43a79b..., 40 calls), which is kept
unchanged and still verifiable.  Same inputs, model, decode and stop rules; only the call policy differs.
Modes: plan (CPU) / check (CPU, optional --verify-weights) / run (GPU, researcher AUTHORIZATION.json).
Reuses the v1 runner's input builder, GPU gate and HF generator unchanged.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.io import file_sha256, object_sha256, write_json_once  # noqa: E402
from metacom_pm.rl1v3.needs import pilot_v2 as P2  # noqa: E402

_spec = importlib.util.spec_from_file_location("b1_pilot_v1", PROJECT / "scripts/rl1v3/B1_needcard_pilot_run.py")
R1 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(R1)

CODE = tuple(c for c in R1.CODE if c not in ("configs/rl1v3/B1_needcard_pilot_v1.yaml",)) + (
    "scripts/rl1v3/B1_needcard_pilot_run_v2.py", "src/metacom_pm/rl1v3/needs/pilot_v2.py",
    "configs/rl1v3/B1_needcard_pilot_v2.yaml")


def build_plan(cfg, L):
    plan = R1.build_plan(cfg, L)                    # same input checks against the accepted integration preflight
    for r in plan["inputs"]:
        r["status"] = L["packs"][r["prefix_id"]]["status"]
    tot = sum(r["input_tokens"] for r in plan["inputs"])
    rt = cfg["runtime"]
    plan.update(
        pilot_protocol=P2.PILOT_PROTOCOL, inputs_sha256=object_sha256(plan["inputs"]),
        max_first_calls=P2.LIMITS["max_first_calls"], max_retry_calls=P2.LIMITS["max_retry_calls"],
        budget=dict(max_first_calls=20, max_retry_calls=0, total_calls=20, prefill_tokens_max=tot,
                    output_tokens_max=20 * cfg["decode"]["max_new_tokens"], paid_api_calls=0),
        limits=P2.LIMITS, stop_conditions=list(P2.STOP_CONDITIONS),
        commands=dict(check_cpu=f"cd <repo>/project && CUDA_VISIBLE_DEVICES='' PYTHONNOUSERSITE=1 PYTHONPATH=src "
                                f"{rt['python']} scripts/rl1v3/B1_needcard_pilot_run_v2.py --mode check --verify-weights",
                      run_gpu=(f"cd <repo>/project && CUDA_VISIBLE_DEVICES={rt['gpu_uuid']} PYTHONNOUSERSITE=1 PYTHONPATH=src "
                               f"{rt['python']} scripts/rl1v3/B1_needcard_pilot_run_v2.py --mode run "
                               f"--authorization {cfg['plan_dir']}/AUTHORIZATION.json"),
                      audit_prepare="python scripts/rl1v3/B1_needcard_pilot_audit_v2.py --prepare",
                      audit_report="python scripts/rl1v3/B1_needcard_pilot_audit_v2.py --report",
                      checklist_freeze="python scripts/rl1v3/B1_needcard_pilot_audit_v2.py --freeze"),
        authorization_path=f"{cfg['plan_dir']}/AUTHORIZATION.json",
        authorization_fields=["authorized_by", "granted_at", "scope", "plan_sha256", "max_first_calls",
                              "max_retry_calls (=0)", "gpu_uuid", "paid_api_calls (=0)"],
        per_call_record=["pack_sha256", "messages_sha256", "input_tokens", "output_text", "output_sha256", "finish_reason",
                         "output_tokens", "seconds", "peak_bytes", "error", "writer_failed"],
        a0_handoff=P2.WORKLOAD_LABEL,
        alternative_to=dict(plan="needcard_pilot_v1_plan/RUN_PLAN.json",
                            plan_sha256="9a43a79bb76276a30d6c74992d476168240f7cac32bdd3ac14455658dd5b9f59",
                            status="kept unchanged; either plan needs its own authorization"),
        researcher_recommendation_is_not_authorization=True,
        after_run=["B audits all 20 cards with audit protocol v2 (6 preregistered checks, derived verdicts)",
                   "gates: evidence-error rate <= 10% AND each of the 8 B6e-v3 prefixes has a valid card, else B6e paused",
                   "only valid cards get a checklist v3, frozen before any candidate reply"],
        code_files_sha256={p: file_sha256(PROJECT / p) for p in CODE})
    plan.pop("plan_sha256", None)
    plan.pop("written_by_code_head", None)
    plan["plan_sha256"] = P2.plan_sha256(plan)
    plan["written_by_code_head"] = R1.git("rev-parse", "HEAD")
    return plan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PROJECT / "configs/rl1v3/B1_needcard_pilot_v2.yaml"))
    ap.add_argument("--mode", choices=("plan", "check", "run"), default="check")
    ap.add_argument("--authorization", default=None)
    ap.add_argument("--verify-weights", action="store_true")
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    L = R1.load(cfg)
    plan_path = PROJECT / cfg["plan_dir"] / "RUN_PLAN.json"
    if args.mode == "plan":
        plan = build_plan(cfg, L)
        write_json_once(plan_path, plan)
        print(json.dumps(dict(plan_sha256=plan["plan_sha256"], inputs=len(plan["inputs"]), budget=plan["budget"]), indent=1))
        return
    plan = json.loads(plan_path.read_text())
    problems = R1.verify_plan(plan, L, weights=args.verify_weights or args.mode == "run")
    try:
        P2.check_inputs(plan, L["packs"])
    except P2.PilotStopped as exc:
        problems.append(exc.reason)
    print(json.dumps(dict(mode=args.mode, plan_sha256=plan["plan_sha256"], problems=problems,
                          weights_verified=args.verify_weights or args.mode == "run"), indent=1))
    if args.mode == "check" or problems:
        sys.exit(1 if problems else 0)
    if not args.authorization:
        raise SystemExit("S1: no authorization (GPU run needs the researcher's AUTHORIZATION.json)")
    auth = json.loads(Path(args.authorization).read_text())
    P2.check_authorization(auth, plan, gpu_uuid=cfg["runtime"]["gpu_uuid"])
    out = PROJECT / plan["out_dir"]
    gate = R1.gpu_gate(plan["runtime"])
    generate, info = R1.real_generator(L, plan)
    write_json_once(out / "runtime.json", dict(info, gpu_gate=gate, authorization_sha256=object_sha256(auth),
                                               plan_sha256=plan["plan_sha256"], code_head=R1.git("rev-parse", "HEAD"),
                                               workload=P2.WORKLOAD_LABEL))
    summary = P2.run_pilot(plan, L["ctxs"], L["packs"], generate, writer=plan["writer"]["identity"], out=out,
                           max_first_calls=auth["max_first_calls"])
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
