#!/usr/bin/env python3
"""WS-B B8e-preflight: real CPU training of OneShot / Seq-BC / PPO / NoText on a
fully synthetic programmatic FiniteHead task.  engineering_only.

This is a training-stack preflight, NOT the real B8e and NOT research PPO: no
real prefix, resource, Generator, judge or reward enters it.

    CUDA_VISIBLE_DEVICES='' PYTHONPATH=project/src python \
        project/scripts/rl1v3/B8e_preflight.py --config project/configs/rl1v3/B8e_preflight.yaml \
        --out project/outputs/pm_rl1/v3/B8e_preflight --stage seed --seed 17
    ... --stage aggregate
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import subprocess
import sys
import time
from pathlib import Path

os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")  # never touch the shared A6000

PROJECT = Path(__file__).resolve().parents[2]
REPO = PROJECT.parent
sys.path.insert(0, str(PROJECT / "src"))

import numpy as np  # noqa: E402
import torch  # noqa: E402
import yaml  # noqa: E402

from metacom_pm.rl1v3.env import finite_head as E  # noqa: E402
from metacom_pm.rl1v3.env import programmatic as P  # noqa: E402
from metacom_pm.rl1v3.evaluate import rollout as RO  # noqa: E402
from metacom_pm.rl1v3.policies.encoder import ObservationEncoder  # noqa: E402
from metacom_pm.rl1v3.policies.mlp import ActorCritic  # noqa: E402
from metacom_pm.rl1v3.train import ppo as PPO  # noqa: E402
from metacom_pm.rl1v3.train import supervised as S  # noqa: E402
from metacom_pm.rl1v3.train.common import (JsonlLog, file_sha256, param_sha256,  # noqa: E402
                                           save_checkpoint, seed_everything)

CODE_FILES = (
    "src/metacom_pm/rl1v3/env/finite_head.py", "src/metacom_pm/rl1v3/env/programmatic.py",
    "src/metacom_pm/rl1v3/policies/encoder.py", "src/metacom_pm/rl1v3/policies/mlp.py",
    "src/metacom_pm/rl1v3/train/common.py", "src/metacom_pm/rl1v3/train/supervised.py",
    "src/metacom_pm/rl1v3/train/ppo.py", "src/metacom_pm/rl1v3/evaluate/rollout.py",
    "scripts/rl1v3/B8e_preflight.py",
)
EVAL_SETS = ("test_unseen_paraphrase", "test_seen_paraphrase")


def datasets(cfg):
    d = cfg["data"]
    return {k: P.generate(v["n"], v["seed"], v["paraphrases"], k) for k, v in d.items()}


def bayes_rollout(insts):
    def act(obs, env, s, inst):
        return P.bayes_action(inst, s.mask, {h: P.symbol_of(r.reading_text)
                                             for h, r in zip(s.order, s.readings)})
    out = []
    for i in insts:
        out += RO.run_policy([i], P.make_env, lambda o, env, s, i=i: act(o, env, s, i))
    return out


def references(data) -> dict:
    train = data["train"]
    fixed_train = {m: float(np.mean([RO.execute_subset(i, P.make_env, m)["ret"] for i in train]))
                   for m in range(E.N_SUBSETS)}
    best_fixed = max(range(E.N_SUBSETS), key=lambda m: (fixed_train[m], -m))
    refs = dict(fixed_best_subset=list(E.heads_of(best_fixed)),
                fixed_train_mean={"+".join(E.heads_of(m)) or "OFF": round(v, 6)
                                  for m, v in fixed_train.items()}, sets={})
    for name in ("dev",) + EVAL_SETS:
        insts = data[name]
        bay_runs = bayes_rollout(insts)
        bayes = {r["instance_id"]: r["ret"] for r in bay_runs}
        oracle = {}
        for i in insts:
            dp = P.oracle_dp(i)
            env = P.make_env(i)
            s, tot = env.reset(), 0.0
            while not s.done:
                s, r, _, _ = env.step(s, dp.optimal_actions[s.mask][0])
                tot += r
            if abs(tot - dp.root_value) > 1e-9:
                raise AssertionError("oracle execution != DP value")
            oracle[i.instance_id] = tot
        runs = {
            "OFF": RO.run_policy(insts, P.make_env, lambda o, env, s: E.STOP),
            "ALL": [RO.execute_subset(i, P.make_env, E.FULL) for i in insts],
            "Fixed-best": [RO.execute_subset(i, P.make_env, best_fixed) for i in insts],
            "Bayes-optimal": bay_runs,
            "Oracle-DP (privileged)": [dict(instance_id=k, ret=v, n_gets=0)
                                       for k, v in oracle.items()],
        }
        refs["sets"][name] = {k: RO.summarize(v, insts, bayes=bayes, oracle=oracle)
                              for k, v in runs.items()}
        refs["sets"][name]["Oracle-DP (privileged)"].pop("mean_gets")
        refs["sets"][name]["Oracle-DP (privileged)"].pop("off_rate")
        refs["sets"][name]["_bayes_expected_value"] = round(float(np.mean(
            [P.bayes_expected_value(i) for i in insts])), 6)
    return refs



def eval_actor(model, enc, data, bayes_oracle):
    out = {}
    for name in ("dev",) + EVAL_SETS:
        res = RO.batched_greedy(data[name], P.make_env, enc, S.greedy_choose(model))
        out[name] = RO.summarize(res, data[name], **bayes_oracle[name])
    return out


def eval_oneshot(model, enc, data, bayes_oracle):
    out = {}
    for name in ("dev",) + EVAL_SETS:
        X, M, _ = S.oneshot_dataset(data[name], P.make_env, enc, P.feasible_subsets)
        picks = S.oneshot_choose(model, X, M)
        res = [RO.execute_subset(i, P.make_env, int(m)) for i, m in zip(data[name], picks)]
        out[name] = RO.summarize(res, data[name], **bayes_oracle[name])
    return out


def bayes_oracle_maps(data):
    maps = {}
    for name in ("dev",) + EVAL_SETS:
        insts = data[name]
        maps[name] = dict(bayes={r["instance_id"]: r["ret"] for r in bayes_rollout(insts)},
                          oracle={i.instance_id: P.oracle_dp(i).root_value for i in insts})
    return maps


def run_seed(cfg, out: Path, seed: int) -> None:
    sdir = out / f"seed_{seed}"
    if sdir.exists() and any(sdir.iterdir()):
        raise FileExistsError(f"{sdir} exists; outputs are append-only, use a new --out")
    sdir.mkdir(parents=True)
    ck = out / "checkpoints" / f"seed_{seed}"
    data = datasets(cfg)
    bo = bayes_oracle_maps(data)
    sup, pc = cfg["supervised"], cfg["ppo"]
    ppo_cfg = PPO.PPOConfig(**pc)
    log = JsonlLog(sdir / "curves.jsonl")
    metrics, timing = {}, {}
    text = P.SyntheticTextEncoder()
    enc = ObservationEncoder(text, P.TEXT_DIM, use_text=True)
    enc_nt = ObservationEncoder(text, P.TEXT_DIM, use_text=False)

    def tick(name, t0):
        timing[name] = round(time.time() - t0, 2)

    # OneShot
    t0 = time.time()
    g = seed_everything(seed)
    m, opt, info = S.train_oneshot(data["train"], data["dev"], P.make_env, enc, P.feasible_subsets,
                                   gen=g, epochs=sup["epochs"], lr=sup["lr"], batch=sup["batch"],
                                   log=log, tau=sup["oneshot_tau"])
    info["checkpoint_sha256"] = save_checkpoint(ck / "oneshot.pt", model=m, optimizer=opt,
                                                step=info["optimizer_steps"], torch_gen=g,
                                                np_rng=None, extra=dict(method="OneShot"))
    metrics["OneShot"] = dict(train=info, eval=eval_oneshot(m, enc, data, bo))
    tick("OneShot", t0)

    # Seq-BC and Seq-BC-NoText, then PPO variants initialised from them
    for tag, e in (("", enc), ("-NoText", enc_nt)):
        t0 = time.time()
        g = seed_everything(seed)
        bc, opt, info = S.train_bc(data["train"], data["dev"], P.make_env, e, P.oracle_dp, gen=g,
                                   epochs=sup["epochs"], lr=sup["lr"], batch=sup["batch"],
                                   log=log, method=f"Seq-BC{tag}")
        info["checkpoint_sha256"] = save_checkpoint(ck / f"seq_bc{tag.lower()}.pt", model=bc,
                                                    optimizer=opt, step=info["optimizer_steps"],
                                                    torch_gen=g, np_rng=None,
                                                    extra=dict(method=f"Seq-BC{tag}"))
        metrics[f"Seq-BC{tag}"] = dict(train=info, eval=eval_actor(bc, e, data, bo))
        tick(f"Seq-BC{tag}", t0)

        t0 = time.time()
        g = seed_everything(seed)
        rng = np.random.default_rng(seed)
        init_sha = param_sha256(bc)
        res = PPO.train_ppo(bc, data["train"], data["dev"], P.make_env, e, ppo_cfg, gen=g,
                            rng=rng, log=log, ckpt_dir=ck / f"ppo{tag.lower()}",
                            method=f"PPO{tag}")
        res.pop("opt")
        res["init_param_sha256"] = init_sha
        res["params_changed_from_init"] = res["final_param_sha256"] != init_sha
        final = eval_actor(bc, e, data, bo)
        best_model = ActorCritic(e.dim)
        best_model.load_state_dict(torch.load(ck / f"ppo{tag.lower()}" / "best.pt",
                                              weights_only=False)["model"])
        metrics[f"PPO{tag}"] = dict(train=res, eval=eval_actor(best_model, e, data, bo),
                                    eval_final_round=final)
        tick(f"PPO{tag}", t0)

    # Diagnostic: PPO from random initialisation (no BC)
    t0 = time.time()
    g = seed_everything(seed)
    rng = np.random.default_rng(seed)
    scratch = ActorCritic(enc.dim)
    init_sha = param_sha256(scratch)
    res = PPO.train_ppo(scratch, data["train"], data["dev"], P.make_env, enc, ppo_cfg, gen=g,
                        rng=rng, log=log, ckpt_dir=ck / "ppo_scratch", method="PPO-scratch")
    res.pop("opt")
    res["init_param_sha256"] = init_sha
    res["params_changed_from_init"] = res["final_param_sha256"] != init_sha
    best_model = ActorCritic(enc.dim)
    best_model.load_state_dict(torch.load(ck / "ppo_scratch" / "best.pt",
                                          weights_only=False)["model"])
    metrics["PPO-scratch"] = dict(train=res, eval=eval_actor(best_model, enc, data, bo),
                                  eval_final_round=eval_actor(scratch, enc, data, bo))
    tick("PPO-scratch", t0)

    # Resume check: N rounds straight vs split + resume from checkpoint
    rc = cfg["resume_check"]
    small = PPO.PPOConfig(**dict(pc, rounds=rc["rounds"], ckpt_every=rc["split_at"],
                                 eval_every=rc["rounds"]))
    shas = {}
    for mode in ("straight", "resumed"):
        g = seed_everything(seed)
        rng = np.random.default_rng(seed)
        mdl = ActorCritic(enc.dim)
        d = ck / f"resume_{mode}"
        if mode == "straight":
            r = PPO.train_ppo(mdl, data["train"], data["dev"], P.make_env, enc, small, gen=g,
                              rng=rng, log=JsonlLog(None), ckpt_dir=d, method="resume")
        else:
            PPO.train_ppo(mdl, data["train"], data["dev"], P.make_env, enc, small, gen=g, rng=rng,
                          log=JsonlLog(None), ckpt_dir=d, method="resume",
                          stop_after=rc["split_at"])
            g2 = torch.Generator()
            rng2 = np.random.default_rng(0)
            mdl2 = ActorCritic(enc.dim)
            opt2, start = PPO.resume(d / f"round_{rc['split_at']:04d}.pt", mdl2, small, g2, rng2)
            r = PPO.train_ppo(mdl2, data["train"], data["dev"], P.make_env, enc, small, gen=g2,
                              rng=rng2, log=JsonlLog(None), ckpt_dir=None, method="resume",
                              start_round=start, opt=opt2)
        shas[mode] = r["final_param_sha256"]
    resume = dict(rounds=rc["rounds"], split_at=rc["split_at"], **shas,
                  identical=shas["straight"] == shas["resumed"])

    (sdir / "metrics.json").write_text(json.dumps(dict(
        seed=seed, metrics=metrics, timing_s=timing, resume_check=resume,
        encoder_identity=P.SyntheticTextEncoder.identity, obs_dim=enc.dim,
        torch=torch.__version__, threads=torch.get_num_threads()), indent=2, sort_keys=True))
    print(json.dumps(dict(seed=seed, timing=timing, resume=resume["identical"])), flush=True)


def git(*a):
    return subprocess.run(["git", *a], cwd=REPO, capture_output=True, text=True,
                          check=True).stdout.strip()


def aggregate(cfg, out: Path, config_path: Path) -> None:
    data = datasets(cfg)
    refs = references(data)
    seeds = cfg["seeds"]
    per = {s: json.loads((out / f"seed_{s}" / "metrics.json").read_text()) for s in seeds}
    methods = list(per[seeds[0]]["metrics"])
    table = {}
    for name in ("dev",) + EVAL_SETS:
        table[name] = {}
        for mth in methods:
            vals = [per[s]["metrics"][mth]["eval"][name] for s in seeds]
            agg = {}
            for key in ("mean_return", "regret_vs_bayes", "regret_vs_oracle", "mean_gets",
                        "off_rate"):
                xs = np.array([v[key] for v in vals])
                agg[key] = dict(mean=round(float(xs.mean()), 6), sd=round(float(xs.std(ddof=1)), 6),
                                per_seed=[round(float(x), 6) for x in xs])
            agg["by_cue_mean"] = {c: round(float(np.mean([v["by_cue"][c] for v in vals])), 6)
                                  for c in vals[0]["by_cue"]}
            table[name][mth] = agg
    ckpts = sorted(p for p in (out / "checkpoints").rglob("*.pt"))
    summary = dict(task_id=P.TASK_ID, evidence_tier=P.EVIDENCE_TIER, references=refs,
                   learned=table,
                   resume_checks={s: per[s]["resume_check"] for s in seeds},
                   optimizer_steps={s: {m: per[s]["metrics"][m]["train"]["optimizer_steps"]
                                        for m in methods} for s in seeds},
                   params_changed={s: {m: per[s]["metrics"][m]["train"].get(
                       "params_changed_from_init") for m in methods} for s in seeds},
                   timing_s={s: per[s]["timing_s"] for s in seeds})
    (out / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    head = git("rev-parse", "HEAD")
    dirty = bool(git("status", "--porcelain", "--", *(f"project/{p}" for p in CODE_FILES)))
    (out / "manifest.json").write_text(json.dumps(dict(
        task_id="B8e_preflight", protocol=P.TASK_ID, evidence_tier=P.EVIDENCE_TIER,
        claim_boundary=("training-stack preflight on a synthetic task; not real B8e, not research "
                        "PPO, no natural-support or real-data claim"),
        real_data_reads=0, model_downloads=0, gpu_used=False, paid_calls=0,
        git_head_at_aggregate=head, code_dirty=dirty,
        code_files_sha256={p: file_sha256(PROJECT / p) for p in CODE_FILES},
        config={str(config_path.relative_to(REPO)): file_sha256(config_path)},
        outputs={str(p.relative_to(out)): file_sha256(p) for p in
                 [out / "summary.json"] + [out / f"seed_{s}" / f for s in seeds
                                           for f in ("metrics.json", "curves.jsonl")]},
        checkpoints={str(p.relative_to(out)): dict(sha256=file_sha256(p), bytes=p.stat().st_size)
                     for p in ckpts},
        checkpoints_tracked_in_git=False,
        python=platform.python_version(), torch=torch.__version__,
    ), indent=2, sort_keys=True))
    print(json.dumps({k: {m: table[k][m]["mean_return"]["mean"] for m in methods}
                      for k in table}, indent=1))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--stage", choices=("seed", "aggregate"), required=True)
    ap.add_argument("--seed", type=int)
    a = ap.parse_args()
    if torch.cuda.is_available():
        raise RuntimeError("preflight must run CPU-only; set CUDA_VISIBLE_DEVICES=''")
    config_path = a.config.resolve()
    cfg = yaml.safe_load(config_path.read_text())
    out = a.out.resolve()
    if a.stage == "seed":
        if a.seed not in cfg["seeds"]:
            raise ValueError("seed not declared in config")
        run_seed(cfg, out, a.seed)
    else:
        aggregate(cfg, out, config_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
