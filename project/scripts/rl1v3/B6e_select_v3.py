"""B6e plan v3: deterministic engineering-coverage selection + frozen identity bindings (CPU, no model).

  select     -> outputs/pm_rl1/v3/B6e_plan/v3/SELECTION.json and PLAN_V3_FROZEN.json (write-once)
  real-keys  -> REAL_KEYS_CHECK.json: rebuild every reachable TerminalKey / ExecutionTrace of the 8
                selected prefixes through WS-A's PrefixPort with the native Gemma tokenizer and require
                each to equal the formal integration replay key (no generation, no reward).
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

from metacom_pm.rl1v3.checklist import writer_v3 as CW3  # noqa: E402
from metacom_pm.rl1v3.evaluate import b6e_select_v3 as SEL, protocol_v2 as EV2, terminal_registry as TR  # noqa: E402
from metacom_pm.rl1v3.io import build_manifest, file_sha256, object_sha256, sha256_text, write_json_once  # noqa: E402
from metacom_pm.rl1v3.judge import aggregate_v3 as AG3, engineering_reward_v3 as ER3, protocol_v3 as JP3  # noqa: E402
from metacom_pm.rl1v3.train import real_instances as RI  # noqa: E402

OUT = PROJECT / "outputs/pm_rl1/v3/B6e_plan/v3"


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True).stdout.strip()


def jl(p):
    return [json.loads(x) for x in Path(p).read_text().splitlines()]


def select(cfg):
    sc = cfg["selection"]
    rep, cov = jl(PROJECT / sc["replay"]), jl(PROJECT / sc["coverage_sample"])
    sel = SEL.select(cov, rep)
    if sel["calls_upper_bound"] != cfg["calls_upper_bound"]:
        raise SystemExit(f"call bounds differ from the plan: {sel['calls_upper_bound']}")
    write_json_once(OUT / "SELECTION.json", sel)
    first = next(r for r in rep if r["prefix_id"] in sel["selected_ids"])
    pilot = PROJECT / cfg["needcard_pilot_plan"]
    pplan = json.loads(pilot.read_text())
    if not set(sel["selected_ids"]) <= {r["prefix_id"] for r in pplan["inputs"]}:
        raise SystemExit("a selected prefix is not inside the NeedCard pilot")
    plan = dict(
        plan_version=SEL.PLAN_VERSION, config_sha256=file_sha256(PROJECT / "configs/rl1v3/B6e_preflight_plan_v3.yaml"),
        rule_sha256=SEL.rule_sha256(), selection_sha256=sel["selection_sha256"], selected=sel["selected_ids"],
        terminals=sel["terminals"], calls_upper_bound=sel["calls_upper_bound"],
        identity_binding=dict(
            source_version="sources:c6ad9b15ba65341f2e5cab26e5451943c9539844f1043964c516b82171286c02",
            **{k: first["identity"][k] for k in ("bank_version", "index_version", "renderer_id", "step2_id")},
            g_id="REQUIRED: versioned initial G0 (weights sha + request renderer) from WS-A",
            decode_id="REQUIRED: G0 decode config id",
            read_port="pmrl1v3-a1b-read-port-v1 (WS-A bank.v0_port.PrefixPort)",
            needcard_pilot_plan_sha256=pplan["plan_sha256"], needcard_writer=pplan["writer"]["identity"],
            rs_v0_catalog=pplan["sources"]["catalog_id"], checklist=CW3.writer_identity(),
            j1=dict(protocol=JP3.JUDGE_PROTOCOL, system_sha256=sha256_text(JP3.SYSTEM_PROMPT),
                    note="JudgeIdentityV3.id (model file-set + decode) fixed before the first call"),
            aggregation=AG3.AGGREGATION_PROTOCOL, engineering_reward=dict(protocol=ER3.PROTOCOL,
                                                                        preregistration_sha256=ER3.preregistration()["sha256"]),
            evaluation=EV2.EVAL_PROTOCOL, terminal_registry=TR.REGISTRY_PROTOCOL, b8e_interface=RI.INTERFACE),
        gates=cfg["gates"], claims_not_allowed=cfg["claims_not_allowed"], history_kept=["plan v1", "plan v2"],
        evidence_tier="engineering_only")
    plan["plan_sha256"] = object_sha256(plan)
    plan["code_head"] = git("rev-parse", "HEAD")
    write_json_once(OUT / "PLAN_V3_FROZEN.json", plan)
    return sel, plan


def real_keys(cfg):
    """Formal real keys/traces for the selected prefixes (native Gemma tokenizer, WS-A PrefixPort)."""
    from metacom_pm.rl1v3.bank import v0_port as AP
    from metacom_pm.rl1v3.env import a1b_port as P
    from metacom_pm.rl1v3.env.c0_binding import C0FiniteHeadEnv, TerminalIdentity, TerminalTable
    sel = json.loads((OUT / "SELECTION.json").read_text())
    rep = {r["prefix_id"]: r for r in jl(PROJECT / cfg["selection"]["replay"])}
    cov = {r["prefix_id"]: r for r in jl(PROJECT / cfg["selection"]["coverage_sample"])}
    fa = AP.make_port_factory(root=REPO)
    rows = []
    for pid in sel["selected_ids"]:
        r = rep[pid]
        b = TR.ReplayBinding.from_report(r)
        port = fa.for_prefix(P.prefix_for(fa.bank.registry, cov[pid]))
        ident = TerminalIdentity(**b.identity)
        env = C0FiniteHeadEnv(prefix=port.prefix, history_sessions=port.prefix.cutoff_rank,
                              availability=dict(port.availability()), read=lambda h, acquired, p=port: p.read(h, acquired=acquired),
                              identity=ident, table=TerminalTable({}, table_id="keys-only"), prefix_tokens=port.base_tokens,
                              read_takes_acquired=True, dynamic_mask=port.action_mask)
        same, n = 0, 0
        for m in b.reachable:
            s = RI._replay(env, m)
            key, trace = env.terminal_key(s), env.execution_trace(s)
            trace.verify_key(key)
            n += 1
            same += key.sha256 == r["key_by_subset"][TR.subset_name(m)] == b.replay_key_sha(port.prefix, key)
        rows.append(dict(prefix_id=pid, reachable=n, keys_equal_formal_replay=same))
    out = dict(protocol="pmrl1v3-b6e-real-keys-check-v1", selection_sha256=sel["selection_sha256"], prefixes=rows,
               terminals=sum(x["reachable"] for x in rows), keys_equal=sum(x["keys_equal_formal_replay"] for x in rows),
               passed=all(x["reachable"] == x["keys_equal_formal_replay"] for x in rows), code_head=git("rev-parse", "HEAD"),
               generation_calls=0, rewards="none (all terminals pending)", evidence_tier="engineering_only")
    write_json_once(OUT / "REAL_KEYS_CHECK.json", out)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default=str(PROJECT / "configs/rl1v3/B6e_preflight_plan_v3.yaml"))
    ap.add_argument("step", choices=("select", "real-keys"))
    args = ap.parse_args()
    cfg = yaml.safe_load(Path(args.config).read_text())
    if args.step == "select":
        sel, plan = select(cfg)
        man = build_manifest(task="B6e_plan_v3", root=PROJECT,
                             inputs={"replay": PROJECT / cfg["selection"]["replay"],
                                     "coverage_sample": PROJECT / cfg["selection"]["coverage_sample"],
                                     "needcard_pilot_plan": PROJECT / cfg["needcard_pilot_plan"]},
                             outputs=[OUT / "SELECTION.json", OUT / "PLAN_V3_FROZEN.json"],
                             code=[PROJECT / "scripts/rl1v3/B6e_select_v3.py",
                                   PROJECT / "src/metacom_pm/rl1v3/evaluate/b6e_select_v3.py",
                                   PROJECT / "configs/rl1v3/B6e_preflight_plan_v3.yaml"], code_sha=plan["code_head"])
        write_json_once(OUT / "manifest.json", dict(man, model_calls=0, gpu_used=False))
        print(json.dumps(dict(selected=sel["selected_ids"], terminals=sel["terminals"], calls=sel["calls_upper_bound"],
                              plan_sha256=plan["plan_sha256"], selection_sha256=sel["selection_sha256"]), indent=1))
    else:
        print(json.dumps(real_keys(cfg), indent=1))


if __name__ == "__main__":
    main()
